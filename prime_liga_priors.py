#!/usr/bin/env python3
"""
prime_liga_priors.py — Backtest-als-Prior (26.06.2026, Lucas „starte mit 1").

Wandelt die Backtest-Trefferquoten (liga_backtest_report.json → perSignal) in einen echten
Bayesian-Prior für den Liga-Lern-Loop: pro Signal eine GEDECKELTE Zahl Pseudo-Beobachtungen
(nPrior) mit winsPrior = hitRate·nPrior. update_signal_weights addiert die zu den Live-Beobachtungen
→ die Liga startet informiert statt bei weight 1.0, und der Prior VERBLASST mit wachsender
Live-Stichprobe (nach ~PRIOR_STRENGTH Live-Picks zählt Live gleich viel, danach mehr).

Warum gedeckelt: der Backtest hat tausende Calls auf EINER Vorsaison mit ANDEREM Quoten-Kontext.
Ungedeckelt würde der Prior das Live-Lernen für immer dominieren. PRIOR_STRENGTH (Default 25) macht
ihn zum Vorsprung, nicht zum Beton. Nur Trefferquote (Richtungs-Korrektheit) wird übernommen —
NICHT der ROI (der ist closing-bezogen und für die Gewichte irrelevant, s. CLV-Befund).

Schreibt liga_signal_priors.json. Einmalig laufen lassen (oder nach jedem neuen Backtest).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE = Path(__file__).parent
import cocobet_dataset as D
# 13.07.2026: datensatz-eigen. Vorher hätte ein MLS-Lauf die LIGA-Priors überschrieben — und
# update_signal_weights liest längst D.file(...) → mls_signal_priors.json, hätte also nie etwas
# gefunden. Beide Enden müssen zusammenpassen.
REPORT = D.file("wm_backtest_report.json", "liga_backtest_report.json")
OUT    = D.file("signal_priors.json",      "liga_signal_priors.json")
PRIOR_STRENGTH = float(os.environ.get("PRIOR_STRENGTH") or 25)   # max Pseudo-Obs je Signal
MIN_CALLS = 50          # unter so wenig Backtest-Calls kein Prior (zu verrauscht)


def build_priors(report: dict, strength: float = PRIOR_STRENGTH) -> dict:
    """report['perSignal'] {sig:{hitRate,calls,correct}} → {sig:{nPrior,winsPrior,hitRate,calls}}.
    Reine Funktion (testbar). nPrior = min(strength, calls); winsPrior = hitRate·nPrior."""
    out = {}
    for sig, d in (report.get("perSignal") or {}).items():
        hr, calls = d.get("hitRate"), d.get("calls") or 0
        if hr is None or calls < MIN_CALLS:
            continue
        n_prior = round(min(strength, calls), 2)
        out[sig] = {"nPrior": n_prior, "winsPrior": round(hr * n_prior, 2),
                    "hitRate": hr, "calls": calls}
    return out


def main():
    print("=== prime_liga_priors.py (Backtest → Prior) ===")
    if not REPORT.exists():
        print(f"  ❌  {REPORT.name} fehlt — erst den Backtest laufen lassen.")
        return
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    priors = build_priors(report)
    payload = {"_meta": {"strength": PRIOR_STRENGTH,
                         "season": (report.get("_meta") or {}).get("season"),
                         "leagues": (report.get("_meta") or {}).get("leagues")},
               **priors}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for sig, p in priors.items():
        print(f"    {sig:18} hitRate {p['hitRate']}  → Prior {p['winsPrior']}/{p['nPrior']} "
              f"(aus {p['calls']} Backtest-Calls)")
    if not priors:
        print("  (kein Signal über MIN_CALLS — kein Prior geschrieben)")
    print(f"  ✅ → {OUT.name}")


if __name__ == "__main__":
    main()
