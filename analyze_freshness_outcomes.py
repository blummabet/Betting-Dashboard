#!/usr/bin/env python3
"""
analyze_freshness_outcomes.py — Trefferquote nach Frische-Zustand (18.06.2026, Lucas)

Bucketet aufgelöste Steam-Card-Picks nach freshnessState (confirm / drift / reverse) und
zeigt Win-Rate + Sample-Size je Bucket. Macht SICHTBAR, ob das Frische-Modell trägt:
  · confirm sollte besser laufen als drift
  · reverse sollte schlechter laufen (frisches Geld lag richtig — gegen uns)

Das ist die Mensch-lesbare Seite des Lern-Loops; das Bayesian-Gewicht von `freshness_leg`
(signal_weights.json) lernt dasselbe automatisch und richtungs-bewusst. Auf WM ist das
Sample winzig (Werkbank) — die Aussagekraft kommt mit der Liga.

Liga-ready: Datei als Argument (default wm2026-data.json), kein WM-Spezifikum.

Usage:
  python3 analyze_freshness_outcomes.py [data.json]
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path

WIN = {"WIN"}
LOSS = {"LOSS"}
COUNTED = {"WIN", "LOSS"}            # VOID/PENDING zählen nicht zur Quote


def analyze(data_path: str) -> dict:
    wm = json.loads(Path(data_path).read_text(encoding="utf-8"))
    buckets: dict[str, dict] = defaultdict(lambda: {"win": 0, "loss": 0, "void": 0, "pending": 0})
    for _key, plist in (wm.get("picks") or {}).items():
        for p in (plist or []):
            if p.get("source") != "steam":
                continue
            state = p.get("freshnessState") or "n/a"
            res = str(p.get("result") or "").upper()
            b = buckets[state]
            if res in WIN:
                b["win"] += 1
            elif res in LOSS:
                b["loss"] += 1
            elif res == "VOID":
                b["void"] += 1
            else:
                b["pending"] += 1
    return buckets


def _fmt(b: dict) -> str:
    decided = b["win"] + b["loss"]
    wr = (100.0 * b["win"] / decided) if decided else float("nan")
    wr_s = f"{wr:5.1f}%" if decided else "  —  "
    return (f"win {b['win']:2d}  loss {b['loss']:2d}  → {wr_s} "
            f"(void {b['void']}, offen {b['pending']})")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "wm2026-data.json"
    buckets = analyze(path)
    order = ["confirm", "drift", "reverse", "n/a"]
    print(f"📊 Frische-Outcomes ({path})\n")
    for state in order:
        if state in buckets:
            print(f"  {state:8s} {_fmt(buckets[state])}")
    decided = sum(buckets[s]["win"] + buckets[s]["loss"] for s in buckets)
    if decided < 20:
        print(f"\n  ⚠️  Nur {decided} entschiedene Picks — zu wenig für Aussagekraft "
              f"(WM = Werkbank). Erst die Liga liefert Sample-Size.")
    return buckets


if __name__ == "__main__":
    main()
