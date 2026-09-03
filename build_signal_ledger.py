#!/usr/bin/env python3
"""
build_signal_ledger.py — dauerhaftes Lern-Gedächtnis für den Bayesian-Loop.

WARUM (12.06.2026): update_signal_weights.py las wm_results.json — das ist aber
der TRADE-P&L der platzierten Polymarket-Bets (Key `bets`, ohne signals[], oft
PENDING). Die aufgelösten CARD-Picks mit signals[] + WIN/LOSS leben in
wm2026-data.json["picks"], wo der Updater nie hinsah → 0 Beobachtungen → alle
Gewichte ewig 1.0. Trade-P&L und Signal-Lernen sind zwei verschiedene Dinge.

Dieses Script kapselt die Beobachtungs-Erfassung (Single-Responsibility):
  · Liest aufgelöste Card-Picks (result ∈ WIN/LOSS/VOID) MIT signals[] aus
    wm2026-data.json.
  · UPSERT (append-only, dedup nach matchKey|market) in wm_signal_ledger.json.
    Idempotent: erneutes Laufen überschreibt denselben Eintrag, dupliziert nie.
  · Snapshot der Signale (name+score) zum Auflöse-Zeitpunkt — so überlebt die
    Beobachtung jede spätere Picks-Neugenerierung (robust gegen signal[]-Verlust).

Der Updater (update_signal_weights.py) liest danach den Ledger statt wm_results.

Run:  python3 build_signal_ledger.py [--write]   (Default: DRY-RUN)
Workflow: läuft NACH resolve_wm_results.py, VOR update_signal_weights.py.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE        = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → eigener Liga-Ledger.
_IS_LIGA    = D.is_liga()
WM_FILE     = D.data_file()
LEDGER_FILE = D.file("wm_signal_ledger.json", "liga_signal_ledger.json")

LEARNABLE_RESULTS = {"WIN", "LOSS", "VOID"}   # VOID wird aufgenommen, vom Updater aber ignoriert

# Prozess-Verdict (verdient/Pech/Glück aus echten Match-xG) wiederverwenden — eine
# Quelle, dieselbe Logik wie in der Performance-Anzeige.
try:
    from resolve_wm_results import process_verdict as _process_verdict
except Exception:
    _process_verdict = None


def _build_stats_lookup(wm: dict) -> dict:
    """{matchKey → result.stats} aus den gespielten Fixtures (Gruppe UND K.-o.)."""
    out = {}
    for g, gd in (wm.get("groups") or {}).items():
        for fx in (gd.get("fixtures") or []):
            stats = (fx.get("result") or {}).get("stats")
            if stats:
                _h, _a = fx.get("home"), fx.get("away")
                out[f"{g}-{fx.get('matchday')}-{_h}-{_a}"] = stats
                out.setdefault(f"{g}-{_h}-{_a}", stats)   # 27.07.2026: spieltag-agnostisch (Off-by-one-Fix)
    # 04.07.2026 (Lucas: „wurden die 1/16-Picks nachträglich als lucky/unlucky bewertet?"):
    # KO-Spiele liegen in koFixtures mit Key „KO-{round}-{home}-{away}" (wie der Pick-Key in
    # generate_wm_picks). Ohne sie fand _build_stats_lookup nie die KO-xG → das Prozess-Verdict
    # (verdient/Pech) blieb für ALLE K.-o.-Picks leer → verlorene-aber-verdiente KO-Picks wurden
    # voll bestraft statt milder. Jetzt xG-Coverage auch für die K.-o.-Runden.
    for kf in (wm.get("koFixtures") or []):
        stats = (kf.get("result") or {}).get("stats")
        if stats and kf.get("home") and kf.get("away"):
            out[f"KO-{kf.get('round')}-{kf['home']}-{kf['away']}"] = stats
            out.setdefault(f"KO-{kf['home']}-{kf['away']}", stats)
    return out


def _lookup_stats(stats_lookup: dict, match_key: str):
    """Stats zum Pick holen — exakt, sonst spieltag-agnostisch ({liga}-{home}-{away}).
    27.07.2026 (Lucas: „lernt MLS?"): Pick-Key und Fixture-Key divergieren im Matchday
    (Pick MLS-17-… vs Fixture MLS-16-…) → Verdict fiel für ~70% der fertigen Picks weg."""
    s = stats_lookup.get(match_key)
    if s is not None:
        return s
    parts = str(match_key).split("-")
    if len(parts) >= 4:
        g = "-".join(parts[:-3]); h, a = parts[-2], parts[-1]
        return stats_lookup.get(f"{g}-{h}-{a}")
    return None


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  {path.name} laden fehlgeschlagen: {e}")
        return default


def _save_ledger(ledger: dict) -> None:
    tmp = LEDGER_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LEDGER_FILE)


def _slim_signals(signals: list) -> list:
    """Nur das, was der Bayesian-Loop braucht: name + score (score≠0 = gefeuert)."""
    out = []
    for s in signals or []:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        score = s.get("score", 0.0)
        if name and score not in (0, 0.0, None):
            out.append({"name": name, "score": round(float(score), 3)})
    return out


def collect_observations(wm: dict) -> list[dict]:
    """Aufgelöste Card-Picks mit gefeuerten Signalen → Ledger-Records.
    Inkl. Prozess-Verdict (verdient/Pech/Glück aus echten Match-xG, 14.06.2026),
    damit der Updater verlorene-aber-verdiente Picks milder bestraft."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats_lookup = _build_stats_lookup(wm)
    records = []
    for match_key, plist in (wm.get("picks") or {}).items():
        for p in (plist or []):
            if p.get("verdict") == "NOBET":
                continue   # 23.06.2026: NOBET ist kein Bet → nie ins Lern-Ledger (nur Schatten-Info)
            result = str(p.get("result") or "").upper()
            if result not in LEARNABLE_RESULTS:
                continue
            sigs = _slim_signals(p.get("signals"))
            if not sigs:
                continue   # ohne gefeuerte Signale nichts zu lernen
            market = p.get("market") or "?"
            rec = {
                "key":        f"{match_key}|{market}",
                "matchKey":   match_key,
                "market":     market,
                "result":     result,
                "signals":    sigs,
                "resolvedAt": p.get("resolvedAt") or now_iso,
                # Segment-Felder für die Kalibrierung (20.06.2026): Quelle (steam/model),
                # Conviction + Late-Entry → compute_pick_calibration lernt pro Segment.
                "source":           p.get("source") or "model",
                "convictionScore":  p.get("convictionScore"),
                "lateEntry":        bool(p.get("lateEntry")),
                # 04.07.2026 (Lucas): Engine-Version mitschreiben → der Loop lernt nur auf der
                # aktuellen Version. Legacy-Picks ohne Stempel → None (Matchday-Fallback greift).
                "engineVersion":    p.get("engineVersion"),
                # 18.07.2026 — CLV als ZWEITER Lernstrom (siehe update_signal_weights).
                # Ein aufgelöster Pick liefert bisher genau EINE won/lost-Beobachtung je Signal;
                # bei ~100 Picks auf 30 Signale bewegt sich der Loop deshalb kaum. clvPP ist
                # stetig, hat viel kleinere Varianz und steht schon beim Anpfiff fest — gleiche
                # Pick-Zahl, deutlich mehr Information. Muss hier durchgereicht werden, sonst
                # sieht der Updater es nie (der liest NUR den Ledger, nicht die Picks).
                "clvPP":            p.get("clvPP"),
                # 03.09.2026 (Lucas-Checkup der Uebersicht): `clvPP` steht auf JEDEM Pick — es
                # wird mit 0.0 angelegt und erst gefuellt, wenn eine Closing-Linie da ist. Ohne
                # `clvResolved` ist eine 0.0 im Ledger nicht von einer gemessenen Null zu
                # unterscheiden. Gemessen an den Pick-Dateien: 122 von 264 Liga-Picks tragen
                # clvPP==0, und davon hat KEIN EINZIGER clvResolved. compute_clv_summary kennt die
                # Unterscheidung seit jeher („kein Closing erfasst → zaehlt nur in die Abdeckung"),
                # der Ledger reichte sie nur nie durch — und der Uebersichts-Puls rechnete die
                # Platzhalter-Nullen deshalb voll in den Ø CLV und in den Nenner von
                # „schlaegt Close". Eine Datei, die nur die Haelfte weiss, darf nicht so tun.
                "clvResolved":      bool(p.get("clvResolved")),
            }
            if _process_verdict:
                pv = _process_verdict(market, result, _lookup_stats(stats_lookup, match_key))
                if pv.get("processVerdict"):
                    rec["processVerdict"] = pv["processVerdict"]
            records.append(rec)
    return records


def upsert(ledger: dict, observations: list[dict]) -> tuple[int, int]:
    """Mergt Beobachtungen in den Ledger. Returns (neu, aktualisiert)."""
    by_key = {r["key"]: r for r in ledger.get("records", [])}
    new, upd = 0, 0
    for obs in observations:
        if obs["key"] in by_key:
            # Nur überschreiben wenn sich was Relevantes geändert hat (idempotent).
            old = by_key[obs["key"]]
            if (old.get("result") != obs["result"] or old.get("signals") != obs["signals"]
                    or old.get("processVerdict") != obs.get("processVerdict")):
                upd += 1
            by_key[obs["key"]] = {**old, **obs}
        else:
            by_key[obs["key"]] = obs
            new += 1
    ledger["records"] = sorted(by_key.values(), key=lambda r: r["key"])
    return new, upd


def main() -> int:
    write = "--write" in sys.argv[1:]
    print(f"=== build_signal_ledger.py === ({'WRITE' if write else 'DRY-RUN'})\n")

    wm = _load_json(WM_FILE, {})
    ledger = _load_json(LEDGER_FILE, None)
    if not isinstance(ledger, dict):
        ledger = {
            "_meta": {
                "description": "Append-only Lern-Gedächtnis: je aufgelöster Card-Pick "
                               "ein Snapshot der gefeuerten Signale + Outcome. Quelle für "
                               "update_signal_weights.py (Bayesian-Loop). Dedup nach matchKey|market.",
                "version": "1.0",
            },
            "records": [],
        }

    obs = collect_observations(wm)
    print(f"   {len(obs)} aufgelöste Picks mit gefeuerten Signalen gefunden")
    new, upd = upsert(ledger, obs)
    ledger["_meta"]["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger["_meta"]["total_records"] = len(ledger["records"])

    print(f"   → {new} neu, {upd} aktualisiert · Ledger gesamt: {len(ledger['records'])} Records")
    # kleine Outcome-Übersicht
    from collections import Counter
    c = Counter(r["result"] for r in ledger["records"])
    print(f"   Outcomes: {dict(c)}")

    if write:
        _save_ledger(ledger)
        print(f"\n✅ {LEDGER_FILE.name} geschrieben")
    else:
        print("\nℹ️  DRY-RUN — mit --write anwenden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
