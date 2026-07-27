#!/usr/bin/env python3
"""
check_learning_loop_alive.py — Guard gegen einen STILL sterbenden Lern-Loop (20.07.2026, MLS-Audit).

ANLASS: Der MLS-Lern-Loop war leer (`mls_signal_ledger` 0 Records, `mls_clv_summary` n=0/withClosing=0),
obwohl die ganze Kette (build_signal_ledger → compute_clv_summary → update_signal_weights) in
update-mls.yml verdrahtet ist. Aktuell ist das ERWARTBAR (die MLS-Engine ist jung, es gibt noch keine
aufgelösten BET-Picks). Gefährlich wird es, sobald Picks auflösen: dann MUSS der Ledger wachsen und
Closing/CLV ankommen — tut es das nicht, ist es dieselbe Klasse wie [[project_clv_dead_liga_mls]]
(wochenlang unbemerkt tot, weil alle prüften ob es verdrahtet ist, keiner ob DATEN ankommen).

## Semantik — die Unterscheidung ist der Wert
  · noch KEINE aufgelösten Picks  → GRÜN (Loop ist jung, hat schlicht noch nichts zu lernen).
  · aufgelöste Picks vorhanden, aber Ledger LEER → ROT (Loop resolved, aber die Beobachtung kommt nie an).
  · aufgelöste Picks vorhanden, aber Closing/CLV FEHLT durchgängig → ROT (CLV-Zweitstrom tot).

Prüft also NICHT „ist verdrahtet", sondern „kommen bei vorhandenen Resolves auch Beobachtungen an".
Reiner Kern (`evaluate`) ohne Disk testbar. Läuft in der Integritäts-Batterie (Status-Panel, warn).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Ab so vielen aufgelösten Picks erwarten wir einen wachsenden Ledger. Darunter ist Leere kein Signal.
MIN_RESOLVED = 8


def evaluate(resolved: int, ledger_records: int, with_closing: int,
             graded: int | None = None, finished: int | None = None,
             finished_with_xg: int | None = None, min_resolved: int = MIN_RESOLVED) -> list:
    """REIN/testbar. Gibt Probleme zurück (leer = Loop gesund oder legitim jung).

    resolved         : Anzahl aufgelöster Picks (haben ein Ergebnis).
    ledger_records   : Einträge im Signal-Ledger (Bayesian-Lernstrom).
    with_closing     : aufgelöste Picks MIT erfasster Closing-Line (CLV-Zweitstrom).
    graded           : Ledger-Einträge MIT processVerdict (xG-prozess-bewertet). None = nicht geprüft.
    finished         : fertige Spiele im Datensatz. None = nicht geprüft.
    finished_with_xg : fertige Spiele MIT Match-xG am Fixture. None = nicht geprüft.
    """
    problems = []
    if resolved < min_resolved:
        return problems   # jung → nichts zu erwarten
    if ledger_records == 0:
        problems.append(
            f"{resolved} aufgelöste Picks, aber Signal-Ledger LEER — Bayesian-Loop lernt nicht "
            f"(build_signal_ledger erfasst die Resolves nicht).")
    if with_closing == 0:
        problems.append(
            f"{resolved} aufgelöste Picks, aber 0 mit Closing-Line — CLV-Zweitstrom tot "
            f"(Closing-Capture landet nicht; vgl. CLV-für-Liga+MLS-war-tot).")
    # 27.07.2026 (Lucas: „lernt MLS wirklich?"): NEU — Ledger hat Einträge, aber KEINER ist
    # prozess-bewertet. Genau der stille Bruch (xG-Feldname / Match-Key-Spieltag), der 253 fertige
    # Spiele mit 0 Verdicts erzeugte. „ledger_records>0" hat das VERSTECKT statt gemeldet.
    if ledger_records > 0 and graded == 0:
        problems.append(
            f"{ledger_records} Ledger-Einträge, aber 0 prozess-bewertet (verdient/Glück/Pech) — "
            f"der xG-Grader erreicht den Ledger nicht (Feldname xgHome/homeXg oder Match-Key-"
            f"Spieltag). Loop lernt nur binär statt prozess-justiert.")
    # NEU: fertige Spiele ohne Match-xG → Post-Match-xG-Fetch landet nicht am Fixture.
    if finished is not None and finished >= min_resolved and finished_with_xg == 0:
        problems.append(
            f"{finished} fertige Spiele, aber 0 mit Match-xG am Fixture — Post-Match-xG landet nicht "
            f"(fetch_liga_match_stats / Feldname). Prozess-Bewertung unmöglich.")
    return problems


def _load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _xg_present(stats: dict) -> bool:
    """Match-xG am Fixture? Tolerant über beide Konventionen (WM homeXg / Liga+MLS xgHome)."""
    st = stats or {}
    xh = st.get("homeXg") if st.get("homeXg") is not None else st.get("xgHome")
    return isinstance(xh, (int, float))


def collect(ledger_file: str, clv_file: str, data_file: str | None = None) -> dict:
    """Kennzahlen von Disk lesen → evaluate-Eingabe. Datei-Namen datensatz-aware übergeben."""
    ledger = _load(ledger_file)
    clv = _load(clv_file)
    recs = ledger.get("records") if isinstance(ledger, dict) else None
    recs = recs if isinstance(recs, list) else []
    ledger_records = len(recs) if recs else (ledger.get("total_records", 0) or 0)
    graded = sum(1 for r in recs if r.get("processVerdict"))
    overall = (clv.get("overall") or {}) if isinstance(clv, dict) else {}
    cov = overall.get("coverage") or {}
    finished = finished_with_xg = None
    if data_file:
        data = _load(data_file)
        if isinstance(data, dict) and (data.get("groups") or data.get("koFixtures")):
            finished = finished_with_xg = 0
            fxs = []
            for g in (data.get("groups") or {}).values():
                fxs += (g.get("fixtures") or [])
            fxs += (data.get("koFixtures") or [])
            for fx in fxs:
                r = fx.get("result") or {}
                if str(r.get("status", "")).upper() in ("FT", "AET", "PEN"):
                    finished += 1
                    if _xg_present(r.get("stats")):
                        finished_with_xg += 1
    return {
        "resolved": int(cov.get("resolved") or overall.get("n") or 0),
        "ledger_records": int(ledger_records or 0),
        "with_closing": int(cov.get("withClosing") or 0),
        "graded": graded,
        "finished": finished,
        "finished_with_xg": finished_with_xg,
    }


def main() -> int:
    import cocobet_dataset as D
    ledger_file = D.file("wm_signal_ledger.json", "liga_signal_ledger.json").name
    clv_file = D.file("wm_clv_summary.json", "liga_clv_summary.json").name
    data_file = D.data_file().name
    m = collect(ledger_file, clv_file, data_file)
    problems = evaluate(m["resolved"], m["ledger_records"], m["with_closing"],
                        graded=m["graded"], finished=m["finished"],
                        finished_with_xg=m["finished_with_xg"])
    if not problems:
        print(f"✅ Lern-Loop gesund/jung (resolved={m['resolved']}, ledger={m['ledger_records']}, "
              f"graded={m['graded']}, withClosing={m['with_closing']}, "
              f"xG {m['finished_with_xg']}/{m['finished']}).")
        return 0
    print("⚠️  Lern-Loop-Problem:")
    for p in problems:
        print("   ·", p)
    return 0   # nicht-blockierend; Panel meldet warn


if __name__ == "__main__":
    sys.exit(main())
