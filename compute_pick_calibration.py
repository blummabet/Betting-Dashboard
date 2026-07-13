#!/usr/bin/env python3
"""
compute_pick_calibration.py — Lern-Ebene 2: Segment-Kalibrierung (20.06.2026, Lucas)

Die Bayesian-Weights (update_signal_weights.py) lernen pro SIGNAL. Diese Ebene lernt pro
PICK-SEGMENT: wie gut läuft z.B. „Steam/Late-Entry" gegenüber dem Schnitt? Looking at der
Tracking-Auswertung lief Late-Entry-Steam (37%) schwächer als früh/Modell (43%).

Quelle: wm_signal_ledger.json (append-only, prozess-justiert via processVerdict — verdient/
Pech/Glück aus echten Match-xG). Outcome ∈ [0,1] genau wie im Weight-Updater, damit ein
Pech-Loss ein Segment nur teilweise abstraft.

Ausgabe: pick_calibration.json mit je Segment {n, procWin, delta=procWin−Baseline} + Conviction-
Bucket-Stats (Transparenz: ist Conviction überhaupt trennscharf?). generate_wm_picks wendet daraus
einen SEHR KLEINEN, gedeckelten Conviction-Nudge an — erst ab min_picks (WM: 50), Liga später
hochschraubbar. Wirkt bewusst kaum, bis genug Sample da ist.

Run:  python3 compute_pick_calibration.py [--write]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
# 13.07.2026 (MLS-Audit): beide waren hart → die Kalibrierung wurde NUR aus dem WM-Ledger gebaut,
# aber von generate_wm_picks für JEDEN Datensatz gelesen. MLS-/Liga-Conviction wurde also von der
# WM-Performance genudged (Cross-Dataset-Leck in Lern-Ebene 2).
LEDGER_FILE = D.file("wm_signal_ledger.json", "liga_signal_ledger.json")
OUT_FILE    = D.file("pick_calibration.json", "liga_pick_calibration.json")

# Prozess-Outcome — identisch zu update_signal_weights (eine Quelle der Wahrheit im Geist).
PROCESS_OUTCOME = {"JUSTIFIED": 1.0, "LUCKY": 0.65, "UNLUCKY": 0.35, "DESERVED_LOSS": 0.0}
CONV_BUCKETS = [("low", 0, 3), ("mid", 4, 6), ("high", 7, 10)]


def _outcome(rec: dict):
    """Prozess-justierter Outcome ∈ [0,1] oder None (nicht aufgelöst)."""
    pv = rec.get("processVerdict")
    if pv in PROCESS_OUTCOME:
        return PROCESS_OUTCOME[pv]
    r = str(rec.get("result") or "").upper()
    if r == "WIN":
        return 1.0
    if r == "LOSS":
        return 0.0
    return None   # VOID / unklar → nicht werten


def _segment(rec: dict) -> str:
    """Pick-Segment. Bewusst GROB (mehr Sample je Segment): Quelle steam vs model."""
    return "steam" if (rec.get("source") == "steam") else "model"


def _agg(vals: list[float]) -> dict:
    n = len(vals)
    return {"n": n, "procWin": round(sum(vals) / n, 3) if n else None}


# 23.06.2026 (Lucas): Runde 1 (alte Engine) aus der Kalibrierung ausschließen — wie im
# Bayesian-Updater. Ledger behält die Historie, Lernen startet ab MD2.
MIN_LEARN_MATCHDAY = 2


def _matchday_of(rec: dict):
    md = rec.get("matchday")
    if isinstance(md, int):
        return md
    parts = str(rec.get("matchKey") or rec.get("key") or "").split("-")
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None


def compute(ledger: dict) -> dict:
    recs = ledger.get("records", []) if isinstance(ledger, dict) else []
    recs = [r for r in recs
            if (_matchday_of(r) is None or _matchday_of(r) >= MIN_LEARN_MATCHDAY)]
    scored = [(r, _outcome(r)) for r in recs]
    scored = [(r, o) for r, o in scored if o is not None]
    all_vals = [o for _, o in scored]
    baseline = round(sum(all_vals) / len(all_vals), 3) if all_vals else None

    # Segmente
    seg_vals: dict[str, list] = {}
    for r, o in scored:
        seg_vals.setdefault(_segment(r), []).append(o)
    segments = {}
    for seg, vals in seg_vals.items():
        a = _agg(vals)
        a["delta"] = round(a["procWin"] - baseline, 3) if (a["procWin"] is not None and baseline is not None) else 0.0
        segments[seg] = a

    # Conviction-Buckets (nur Transparenz — ist die Conviction trennscharf?)
    conv = {}
    for label, lo, hi in CONV_BUCKETS:
        vals = [o for r, o in scored
                if isinstance(r.get("convictionScore"), (int, float)) and lo <= r["convictionScore"] <= hi]
        conv[label] = _agg(vals)

    return {
        "_meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "totalN": len(all_vals),
            "baseline": baseline,
            "note": "Lern-Ebene 2: Segment-Performance vs Baseline (prozess-justiert). "
                    "generate_wm_picks nudged Conviction gedeckelt ab min_picks.",
        },
        "segments": segments,
        "convictionBuckets": conv,
    }


def main() -> int:
    write = "--write" in sys.argv[1:]
    try:
        ledger = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  {LEDGER_FILE.name} nicht lesbar: {e} — schreibe leere Kalibrierung.")
        ledger = {"records": []}
    cal = compute(ledger)
    m = cal["_meta"]
    print(f"📐 Kalibrierung: {m['totalN']} Picks · Baseline {m['baseline']}")
    for seg, a in cal["segments"].items():
        print(f"   {seg:6}: n={a['n']:3} procWin={a['procWin']} Δ={a['delta']:+}")
    print("   Conviction-Buckets: " + " · ".join(
        f"{k} {v['procWin']} (n={v['n']})" for k, v in cal["convictionBuckets"].items()))
    if write:
        OUT_FILE.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 → {OUT_FILE.name}")
    else:
        print("   (Dry-Run — --write zum Speichern)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
