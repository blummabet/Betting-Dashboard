#!/usr/bin/env python3
"""
analyze_ah_outcomes.py — Handicap-Performance nach Linien-Tiefe (19.06.2026, Lucas)

Beantwortet: traden wir tiefe Handicaps (-3.5/-4.5) am Ende POSITIV raus, oder ist die
Pinnacle-Fair dort zu ungenau / der Polymarket-Markt zu dünn → Verlust? Bucketet aufgelöste
+ verkaufte AH-Bets nach |Linie| und zeigt Win-Rate + echtes ROI (am Bid). Plus offene Anzahl.

WICHTIG: P&L VOR dem 19.06.2026-Endpoint-Fix ist Phantom-kontaminiert (Entry am Mid, Sells am
Cache-Mid) — erst die NEU aufgelösten Bets sind sauber (echter Bid). Sample wächst mit der Zeit;
unter ~15 entschiedenen Bets je Linie sagt das wenig. Liga-ready: Datei-Argumente, kein WM-Spezifikum.

Usage:
  python3 analyze_ah_outcomes.py [results.json] [placed.json]
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_LINE_RE = re.compile(r"AH\s+\w+\s+([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)
DECIDED = {"WIN", "LOSS", "SOLD", "VOID"}


def _line_bucket(market: str):
    m = _LINE_RE.search(market or "")
    if not m:
        return None
    return abs(float(m.group(1)))   # Tiefe, vorzeichen-los: 1.5 / 2.5 / 3.5 / 4.5


def analyze(results_path: str, placed_path: str) -> dict:
    buckets: dict = defaultdict(lambda: {
        "decided": 0, "win": 0, "loss": 0, "sold": 0, "void": 0,
        "stake": 0.0, "pnl": 0.0, "open": 0})
    try:
        res = json.loads(Path(results_path).read_text(encoding="utf-8")).get("bets", [])
    except Exception:
        res = []
    for b in res:
        lb = _line_bucket(b.get("market"))
        if lb is None:
            continue
        r = str(b.get("result") or "").upper()
        if r not in DECIDED:
            continue
        d = buckets[lb]
        d["decided"] += 1
        d["stake"] += float(b.get("stake") or 0)
        d["pnl"] += float(b.get("pnl") or 0)
        if r == "WIN":
            d["win"] += 1
        elif r == "LOSS":
            d["loss"] += 1
        elif r == "SOLD":
            d["sold"] += 1
        elif r == "VOID":
            d["void"] += 1
    try:
        placed = json.loads(Path(placed_path).read_text(encoding="utf-8")).get("bets", [])
    except Exception:
        placed = []
    for b in placed:
        if (b.get("status") or "").lower() != "placed" or b.get("soldAt"):
            continue
        lb = _line_bucket(b.get("market"))
        if lb is not None:
            buckets[lb]["open"] += 1
    return buckets


def main():
    rp = sys.argv[1] if len(sys.argv) > 1 else "wm_results.json"
    pp = sys.argv[2] if len(sys.argv) > 2 else "wm_auto_bets_placed.json"
    buckets = analyze(rp, pp)
    print(f"📊 Handicap-Performance nach Linien-Tiefe ({rp})\n")
    if not buckets:
        print("  Keine AH-Bets gefunden.")
        return buckets
    total_decided = 0
    for line in sorted(buckets):
        d = buckets[line]
        total_decided += d["decided"]
        roi = (100.0 * d["pnl"] / d["stake"]) if d["stake"] else float("nan")
        roi_s = f"{roi:+5.1f}%" if d["stake"] else "  —  "
        print(f"  -{line:<4} entschieden {d['decided']:2d} "
              f"(win {d['win']} · loss {d['loss']} · sold {d['sold']}) "
              f"· P&L {d['pnl']:+6.2f}€ · ROI {roi_s} · offen {d['open']}")
    print()
    if total_decided < 15:
        print(f"  ⚠️  Nur {total_decided} entschiedene AH-Bets — zu wenig für ein Urteil. "
              f"Erst saubere (Post-Endpoint-Fix-)Auflösungen sammeln, dann je Linie bewerten.")
    return buckets


if __name__ == "__main__":
    main()
