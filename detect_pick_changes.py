#!/usr/bin/env python3
"""
detect_pick_changes.py — Erkennt Pick-Änderungen zwischen Pipeline-Runs

Läuft NACH generate_wm_picks.py im Workflow.

Datenfluss:
  picks_snapshot.json       ← vorheriger Zustand der Picks pro Match
  wm2026-data.json          ← aktueller Zustand
  pick_changes_log.json     ← chronologisches Log (letzte 7 Tage rollend)

Was zählt als Change (relevant=True):
  • Verdict-Wechsel: SKIP/missing → BET/ABWÄGEN  oder  BET ↔ ABWÄGEN  oder  BET/ABWÄGEN → SKIP/removed
  • Edge-Delta ≥ 3pp (gleicher Pick, Quote bewegt)
  • Quote-Delta ≥ 0.10 ohne Verdict-Change (signalisiert Markt-Bewegung)

Was als "Reason" geschrieben wird (lesbar in einem Satz):
  • "Quote 1.85 → 1.92 (+4pp Edge)"
  • "Edge zurück (Quote 2.10 → 1.95)"
  • "Aufgewertet: ABWÄGEN → BET (Form-Update nach ST1)"
  • "Entfernt: Edge weg"
  • "Neuer Pick: +6pp Edge auf 2.05"
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
SNAPSHOT     = BASE / "picks_snapshot.json"
CHANGES_LOG  = BASE / "pick_changes_log.json"

LOG_TTL_DAYS = 7
EDGE_DELTA_TG = 3           # Telegram-Schwelle: nur ≥3pp Edge-Delta
ODDS_DELTA_TG = 0.10        # oder Quote-Delta ≥0.10

VERBOSE = os.environ.get("VERBOSE", "0") == "1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick_key(p: dict) -> str:
    """Stabiler Identifier für einen einzelnen Pick innerhalb eines Matches."""
    return (p.get("market") or "?").strip()


def _fixture_label(wm: dict, match_key: str) -> tuple[str, str]:
    """Liefert (label, kickoff_iso) für ein match_key wie G-3-IRN-NZL."""
    parts = match_key.split("-", 3)
    if len(parts) < 4:
        return match_key, ""
    gkey, md, home, away = parts
    gdata = (wm.get("groups") or {}).get(gkey) or {}
    home_t = next((t for t in gdata.get("teams", []) if t.get("id") == home), {})
    away_t = next((t for t in gdata.get("teams", []) if t.get("id") == away), {})
    home_name = home_t.get("name", home)
    away_name = away_t.get("name", away)
    home_flag = home_t.get("flag", "")
    away_flag = away_t.get("flag", "")
    label = f"{home_flag} {home_name} vs {away_flag} {away_name} · ST{md}"
    for fx in gdata.get("fixtures", []):
        if fx.get("home") == home and fx.get("away") == away:
            return label, f"{fx.get('date','')}T{fx.get('time','19:00')}:00"
    return label, ""


def _make_reason(old: dict | None, new: dict | None) -> tuple[str, str]:
    """Liefert (delta_kind, reason_text) für eine Pick-Änderung."""
    # Neuer Pick (war vorher nicht da)
    if old is None and new is not None:
        v = new.get("verdict", "?")
        e = new.get("edgePP")
        o = new.get("odds")
        e_str = f"+{e}pp" if e is not None else "?"
        o_str = f"@{o:.2f}" if isinstance(o, (int, float)) else ""
        return ("new_pick", f"Neuer {v}: {e_str} Edge {o_str}")

    # Entfernter Pick
    if old is not None and new is None:
        v_old = old.get("verdict", "?")
        return ("removed", f"Entfernt — {v_old} verschwunden (Edge weg oder Quote weg)")

    # Verdict-Wechsel
    v_old = old.get("verdict")
    v_new = new.get("verdict")
    e_old = old.get("edgePP")
    e_new = new.get("edgePP")
    o_old = old.get("odds")
    o_new = new.get("odds")

    edge_delta = (e_new or 0) - (e_old or 0)
    try:
        odds_delta = (o_new or 0) - (o_old or 0)
    except Exception:
        odds_delta = 0

    if v_old != v_new:
        # Upgrade vs Downgrade
        rank = {"SKIP": 0, "ABWÄGEN": 1, "BET": 2}
        kind = "upgrade" if rank.get(v_new, 0) > rank.get(v_old, 0) else "downgrade"
        e_str = f" · Edge {e_new:+d}pp" if isinstance(e_new, (int, float)) else ""
        return (kind, f"{v_old} → {v_new}{e_str}")

    # Verdict gleich → reine Quoten/Edge-Bewegung
    if abs(edge_delta) >= EDGE_DELTA_TG:
        sign = "+" if edge_delta > 0 else ""
        kind = "edge_up" if edge_delta > 0 else "edge_down"
        return (kind, f"Edge {sign}{int(edge_delta)}pp ({o_old:.2f} → {o_new:.2f})"
                       if isinstance(o_old, (int, float)) and isinstance(o_new, (int, float))
                       else f"Edge {sign}{int(edge_delta)}pp")
    if abs(odds_delta) >= ODDS_DELTA_TG and isinstance(o_old, (int, float)) and isinstance(o_new, (int, float)):
        return ("odds_swing", f"Quote {o_old:.2f} → {o_new:.2f}")

    return ("noop", "")


def _is_relevant(delta_kind: str) -> bool:
    return delta_kind in {"upgrade", "downgrade", "new_pick", "removed", "edge_up", "edge_down"}


def diff_picks(old_picks: dict, new_picks: dict, wm: dict) -> list[dict]:
    """Erzeugt Change-Liste pro Match × Pick."""
    out: list[dict] = []
    all_match_keys = set(old_picks.keys()) | set(new_picks.keys())
    now = _now_iso()

    for mk in sorted(all_match_keys):
        old_list = old_picks.get(mk, [])
        new_list = new_picks.get(mk, [])
        old_by_market = {_pick_key(p): p for p in old_list}
        new_by_market = {_pick_key(p): p for p in new_list}
        all_markets = set(old_by_market.keys()) | set(new_by_market.keys())

        # Skip past matches (kein Wert mehr)
        label, kickoff_iso = _fixture_label(wm, mk)
        try:
            ko = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
            if ko < datetime.now(timezone.utc):
                continue
        except Exception:
            pass

        for mkt in sorted(all_markets):
            old_p = old_by_market.get(mkt)
            new_p = new_by_market.get(mkt)
            kind, reason = _make_reason(old_p, new_p)
            if kind == "noop":
                continue

            entry = {
                "matchKey":   mk,
                "fixture":    label,
                "kickoff":    kickoff_iso,
                "market":     mkt,
                "deltaKind":  kind,
                "reason":     reason,
                "ts":         now,
                "relevant":   _is_relevant(kind),
                "before":     {
                    "verdict": (old_p or {}).get("verdict"),
                    "odds":    (old_p or {}).get("odds"),
                    "edgePP":  (old_p or {}).get("edgePP"),
                } if old_p else None,
                "after":      {
                    "verdict": (new_p or {}).get("verdict"),
                    "odds":    (new_p or {}).get("odds"),
                    "edgePP":  (new_p or {}).get("edgePP"),
                } if new_p else None,
            }
            out.append(entry)
    return out


def _trim_log(log: list[dict]) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOG_TTL_DAYS)).isoformat()
    return [e for e in log if e.get("ts", "") >= cutoff]


def main():
    if not WM_FILE.exists():
        print("⚠️  wm2026-data.json fehlt")
        return

    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    new_picks = wm.get("picks") or {}

    # Erster Lauf: kein Snapshot → nur Baseline anlegen, KEIN Log
    # (verhindert dass beim allerersten Workflow-Run alle 60+ Picks als "neu" gemeldet werden)
    if not SNAPSHOT.exists():
        _save(SNAPSHOT, {"savedAt": _now_iso(), "picks": new_picks})
        # Leeres Log-File sicherstellen
        if not CHANGES_LOG.exists():
            _save(CHANGES_LOG, {"lastUpdate": _now_iso(), "changes": []})
        print(f"🆕 Baseline-Snapshot angelegt ({sum(len(v) for v in new_picks.values())} Picks) — kein Diff beim Erst-Lauf")
        return

    old_snapshot = _load(SNAPSHOT, {})
    old_picks = old_snapshot.get("picks") or {}

    changes = diff_picks(old_picks, new_picks, wm)
    relevant = [c for c in changes if c["relevant"]]

    print(f"🔄 detect_pick_changes.py — {len(changes)} Changes total, {len(relevant)} relevant")
    if VERBOSE:
        for c in changes[:20]:
            print(f"  [{c['deltaKind']:10s}] {c['matchKey']} {c['market']}: {c['reason']}")

    # Log laden, neue relevante anhängen, alte trimmen
    log_data = _load(CHANGES_LOG, {"changes": []})
    log = log_data.get("changes", [])
    log.extend(relevant)
    log = _trim_log(log)
    # Auf max 200 Einträge limitieren
    if len(log) > 200:
        log = log[-200:]

    _save(CHANGES_LOG, {
        "lastUpdate": _now_iso(),
        "changes":    log,
    })

    # Aktuellen Picks-State als neuen Snapshot speichern
    _save(SNAPSHOT, {
        "savedAt": _now_iso(),
        "picks":   new_picks,
    })

    print(f"💾 {len(log)} Changes im Rolling-Log ({LOG_TTL_DAYS}-Tage-Fenster)")


if __name__ == "__main__":
    main()
