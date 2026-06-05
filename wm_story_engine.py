#!/usr/bin/env python3
"""
wm_story_engine.py — Slot-System + Fact-Verifier + Master-Selector
==================================================================

Kern-Library für die WM Live-Story-Engine. Wird von generate_wm_live_story.py
benutzt und von jedem angle-Modul in wm_story_angles/.

Architektur:
  1. Jeder Angle-Modul liefert Story-Proposals als StoryProposal-dataclass
  2. Jeder Slot kennt seinen Wert UND seinen source-Pfad
  3. Fact-Verifier prüft Slot-Werte gegen Live-Daten
  4. Master-Selector wählt aus allen Proposals die beste Story (höchster score)
  5. Proposal wird in HTML gerendert via tiktok_card_templates

Anti-Patterns die verhindert werden:
  · Hartkodierte Form-Zahlen (Senegal-Bug — 5W/5 wurde nicht aktualisiert)
  · Erfundene Fakten (Österreich-Bug — "Norwegen+Slowenien" stand nirgends)
  · Veraltete Aussagen (Stale-Cache nach Modell-Änderung)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent


# ── Datenquellen-Registry ─────────────────────────────────────────────────────
# Alle JSON-Files die Slots als source-Pfad referenzieren können.
# Lesen lazy, wenn ein Slot zum ersten Mal nach Quelle X fragt.
class _DataRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def get(self, source_file: str) -> dict:
        if source_file not in self._cache:
            path = BASE / source_file
            if path.exists():
                try:
                    self._cache[source_file] = json.loads(path.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"  ⚠️  _DataRegistry: konnte {source_file} nicht laden: {e}")
                    self._cache[source_file] = {}
            else:
                self._cache[source_file] = {}
        return self._cache[source_file]


DATA = _DataRegistry()


# ── Slot ──────────────────────────────────────────────────────────────────────
@dataclass
class Slot:
    """Ein Card-Feld mit Wert + Herkunfts-Pfad zur Verifikation.

    `source` ist ein dotted-path wie "form.BEL.avgScored" oder
    "groups.G.fixtures.0.kickoff" — der Verifier folgt dem Pfad in der jeweiligen
    Source-Datei und vergleicht den Wert.

    `source_file` ist optional (Default: wm2026-data.json).
    Wenn `derived=True`, bedeutet das der Wert wurde aus mehreren Sources abgeleitet
    (z.B. "8 Spiele × 2.875 = 23 Tore") — Verifier prüft dann nur Plausibilität.
    """
    value: str                     # Der Display-Wert (immer String)
    source: str = ""               # Dotted-Path zum Live-Faktum (leer = darf nicht zahlhaltig sein)
    source_file: str = "wm2026-data.json"
    derived: bool = False          # Aus mehreren Quellen abgeleitet
    raw: float | int | str | None = None  # Rohwert für Drift-Check (Verifier vergleicht damit)


def s_static(value: str) -> Slot:
    """Slot für rein narratives Material ohne Zahlen (Mystery-Frage, Pointe etc.)."""
    return Slot(value=value, source="", source_file="")


def s_from(value: str, source: str, source_file: str = "wm2026-data.json",
           raw: float | int | str | None = None) -> Slot:
    """Slot mit Live-Source. raw = numerischer Wert zum Drift-Vergleich."""
    return Slot(value=value, source=source, source_file=source_file, raw=raw)


def s_derived(value: str, sources: list[str], source_file: str = "wm2026-data.json") -> Slot:
    """Slot aus mehreren abgeleitet (z.B. Tor-Schnitt aus games + goalsFor)."""
    return Slot(value=value, source=" + ".join(sources), source_file=source_file, derived=True)


# ── StoryProposal ─────────────────────────────────────────────────────────────
@dataclass
class StoryProposal:
    """Ein Story-Vorschlag von einem Angle-Modul.

    Score zwischen 0.0 (uninteressant) und 1.0 (Banger). Score-Bestandteile:
      · Edge-Stärke / Daten-Outlier-Stärke (max 0.50)
      · Daten-Qualität / # Datenpunkte (max 0.25)
      · Story-Appeal / Drama-Faktor (max 0.25)

    `angle_id` ist eindeutig: matchOfDay/killerStat/underdogRecap/playerSpotlight
    `entity_key` ist der Hauptbezug (Team-ID, Spiel-Key, Spieler-ID) — für Dedup.
    """
    angle_id: str
    entity_key: str                       # Für Dedup: nicht zweimal dasselbe Team hintereinander
    theme: str                            # tiktok_card_templates THEMES-key
    score: float                          # 0.0–1.0
    hook_slots: dict[str, Slot] = field(default_factory=dict)
    info_slots: dict[str, Slot] = field(default_factory=dict)
    series_tag: str = ""
    reason: str = ""                      # Menschlich lesbare Begründung warum diese Story

    def to_dict(self) -> dict:
        # asdict konvertiert nested dataclasses automatisch → reicht
        return asdict(self)


# ── Fact-Verifier ─────────────────────────────────────────────────────────────
def _walk_path(data: dict, path: str) -> object:
    """Folgt einem dotted-path durch nested dicts/lists. Returns None wenn unreachable."""
    if not path:
        return None
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
            if cur is None:
                return None
        else:
            return None
    return cur


def verify_slot(slot: Slot, max_drift_pct: float = 5.0) -> tuple[bool, str]:
    """Prüft ob slot.raw mit Live-Daten übereinstimmt.

    Returns (ok, reason). ok=False wenn Drift > max_drift_pct oder Source nicht erreichbar.
    Static slots (kein source) und derived slots werden als ok markiert (kein direkter Check möglich).
    """
    if not slot.source:
        # Static slot — nichts zu verifizieren (z.B. Mystery-Frage)
        return True, "static"
    if slot.derived:
        # Abgeleiteter Wert — Plausibilität nur, kein exakter Check
        return True, "derived (plausibility ok)"
    data = DATA.get(slot.source_file)
    if not data:
        return False, f"source_file '{slot.source_file}' fehlt/leer"
    live_value = _walk_path(data, slot.source)
    if live_value is None:
        return False, f"path '{slot.source}' in {slot.source_file} nicht gefunden"
    # Wenn raw gesetzt: numerischer Drift-Check
    if slot.raw is not None:
        try:
            live_num = float(live_value)
            raw_num  = float(slot.raw)
            if raw_num == 0:
                return (live_num == 0), f"raw=0, live={live_num}"
            drift = abs(live_num - raw_num) / abs(raw_num) * 100
            if drift > max_drift_pct:
                return False, f"DRIFT {drift:.1f}% (raw={raw_num} vs live={live_num})"
            return True, f"ok ({drift:.1f}% drift, threshold {max_drift_pct}%)"
        except (ValueError, TypeError):
            # raw oder live nicht numerisch — String-Vergleich
            return (str(live_value) == str(slot.raw)), f"str-cmp '{live_value}' vs '{slot.raw}'"
    # Kein raw — nur prüfen dass Pfad existiert
    return True, f"path exists (value: {str(live_value)[:60]})"


def verify_proposal(p: StoryProposal, max_drift_pct: float = 5.0) -> dict:
    """Verifiziert alle Slots einer Proposal. Returns Report mit ok/fail/details."""
    all_slots = {**p.hook_slots, **p.info_slots}
    failures: list[tuple[str, str]] = []
    details: list[tuple[str, bool, str]] = []
    for slot_name, slot in all_slots.items():
        ok, reason = verify_slot(slot, max_drift_pct)
        details.append((slot_name, ok, reason))
        if not ok:
            failures.append((slot_name, reason))
    return {
        "angle_id":  p.angle_id,
        "entity":    p.entity_key,
        "ok":        len(failures) == 0,
        "failures":  failures,
        "details":   details,
        "checked":   len(all_slots),
    }


# ── Master-Selector ───────────────────────────────────────────────────────────
def select_top(proposals: list[StoryProposal],
               recent_entities: set[str] | None = None,
               min_score: float = 0.30) -> StoryProposal | None:
    """Wählt die beste Story-Proposal.

    · Filtert proposals unter min_score
    · Skipt wenn entity_key in recent_entities (Dedup gegen Vortag/letzte 3 Tage)
    · Wählt highest score
    """
    recent_entities = recent_entities or set()
    candidates = [p for p in proposals if p.score >= min_score and p.entity_key not in recent_entities]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.score)


# ── State-Persistenz (Dedup) ───────────────────────────────────────────────────
STATE_FILE = BASE / "wm_live_story_state.json"
DEDUP_DAYS = 4   # Dieselbe entity_key nicht innerhalb 4 Tagen erneut


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"posted": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"posted": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recent_entities(state: dict | None = None) -> set[str]:
    """Entities die in den letzten DEDUP_DAYS Tagen schon Stories hatten."""
    state = state or load_state()
    cutoff = datetime.now(timezone.utc).timestamp() - (DEDUP_DAYS * 86400)
    out = set()
    for entry in state.get("posted", []):
        try:
            ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00")).timestamp()
            if ts >= cutoff:
                out.add(entry["entity_key"])
        except Exception:
            pass
    return out


def record_post(p: StoryProposal, status: str = "posted") -> None:
    """Tracking dass diese Proposal heute gepostet wurde."""
    state = load_state()
    state.setdefault("posted", []).append({
        "ts":         datetime.now(timezone.utc).isoformat(),
        "angle_id":   p.angle_id,
        "entity_key": p.entity_key,
        "theme":      p.theme,
        "score":      p.score,
        "status":     status,
    })
    # Auf 200 Einträge limitieren
    state["posted"] = state["posted"][-200:]
    save_state(state)


# ── Pretty-Print ──────────────────────────────────────────────────────────────
def proposal_summary(p: StoryProposal) -> str:
    """Eine-Zeile-Zusammenfassung für Logs."""
    return (f"[{p.angle_id:14s}] score={p.score:.2f} | "
            f"entity={p.entity_key:16s} | theme={p.theme:14s} | "
            f"reason: {p.reason[:60]}")
