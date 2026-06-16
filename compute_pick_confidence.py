#!/usr/bin/env python3
"""
compute_pick_confidence.py — WM 2026 Pick-Confidence-Backtest
================================================================

Liest aufgelöste Picks aus wm2026-data.json["picks"] und aggregiert
historische Hit-Rates + ROI pro Cluster:

  - byMarket     ("Über 2.5 Tore", "Unentschieden", ...)
  - byAngle      ("torfest", "defshow", "pflicht", ...)
  - byEdgeRange  ("0-5pp", "5-10pp", "10pp+")
  - byDataQuality ("elo_only", "elo+form", "full")
  - byCluster    Kombination aller 4 Dimensionen
  - global       Overall-Stats

Output: pick_confidence_stats.json

Der Renderer fragt dieses File ab um pro Card "Vergleichbare Picks:
67% Hit-Rate (n=23)" anzuzeigen.

Run: python3 compute_pick_confidence.py
Cron: nach resolve_wm_picks.py in fetch-wm-data.yml
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

# Refactor 2026-06-06: zentraler Helper für trackingExcluded-Filter
try:
    from pick_helpers import is_legitimate_pick
except ImportError:
    def is_legitimate_pick(p):
        return p is not None and not (isinstance(p, dict) and p.get("trackingExcluded"))

BASE        = os.path.dirname(os.path.abspath(__file__))
WM_FILE     = os.path.join(BASE, "wm2026-data.json")
STATS_FILE  = os.path.join(BASE, "pick_confidence_stats.json")
MIN_SAMPLES = 3   # Mindest-Cluster-Größe damit Hit-Rate angezeigt wird


def edge_bucket(epp: float | int | None) -> str:
    """Edge in pp → Range-Bucket."""
    if epp is None:
        return "n/a"
    e = float(epp)
    if e < 5:   return "0-5pp"
    if e < 10:  return "5-10pp"
    return "10pp+"


def derive_angle(market: str, dq: str = "") -> str:
    """
    Light-Version des _deriveAngle aus wm2026-renderer.js — gibt den
    Angle-Key zurück basierend auf Market-Label.
    """
    m = (market or "").lower()
    if ("über" in m or "over" in m) and "2.5" in m:    return "torfest"
    if ("unter" in m or "under" in m) and "2.5" in m:  return "defshow"
    if "beide teams treffen" in m or "btts" in m:
        if "nein" in m or "no" in m: return "defshow"
        return "torfest"
    # AH zuerst (16.06.2026): 'AH Heim/Auswärts' enthält 'heim'/'ausw' → würde sonst
    # fälschlich als 1X2 „pflicht" geclustert und dessen Trefferquote verfälschen.
    if m.startswith("ah ") or "handicap" in m:         return "handicap"
    if "heim" in m or "home" in m or m == "1":         return "pflicht"
    if "auswärt" in m or "away" in m or m == "2":      return "pflicht"
    if "unentsch" in m or "draw" in m:                 return "duell"
    if "dnb" in m:                                      return "pflicht"
    return "other"


def init_bucket() -> dict:
    return {"n": 0, "wins": 0, "losses": 0, "voids": 0, "roi_sum": 0.0}


def finalize(bucket: dict) -> dict:
    """Wandelt internen Bucket in Ausgabe-Format mit rate/roi um."""
    n = bucket["n"]
    if n == 0:
        return {"n": 0}
    decisive = n - bucket["voids"]  # Voids zählen weder W noch L
    rate = round((bucket["wins"] / decisive) * 100, 1) if decisive > 0 else 0
    roi  = round((bucket["roi_sum"] / n) * 100, 1)
    out = {
        "n":      n,
        "wins":   bucket["wins"],
        "losses": bucket["losses"],
        "rate":   rate,
        "roi":    roi,
    }
    if bucket["voids"] > 0:
        out["voids"] = bucket["voids"]
    return out


def main():
    if not os.path.exists(WM_FILE):
        print(f"❌ {WM_FILE} fehlt")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    picks = wm.get("picks", {})

    # Aggregate Buckets
    by_market   = {}
    by_angle    = {}
    by_edge     = {}
    by_dq       = {}
    by_cluster  = {}
    global_b    = init_bucket()

    for pick_list in picks.values():
        if not isinstance(pick_list, list):
            continue
        for p in pick_list:
            # is_legitimate_pick filtert trackingExcluded automatisch.
            # Diese Picks sind direktional widersprüchlich (Cross-Market-Filter
            # vom Tracker) — wir wetten sie nicht, also dürfen sie die Hit-Rate-
            # Cluster-Stats nicht verfälschen.
            if not is_legitimate_pick(p):
                continue

            r = p.get("result")
            if r not in ("WIN", "LOSS", "VOID"):
                continue  # noch nicht aufgelöst

            market  = p.get("market", "?")
            angle   = derive_angle(market, p.get("dataQuality", ""))
            edge_b  = edge_bucket(p.get("edgePP"))
            dq      = p.get("dataQuality", "?")
            odds    = float(p.get("odds") or 0)

            # Unit-Stake: bei WIN → odds-1, LOSS → -1, VOID → 0
            if r == "WIN":   roi_delta =  (odds - 1.0) if odds > 0 else 0.0
            elif r == "LOSS": roi_delta = -1.0
            else:             roi_delta = 0.0   # VOID

            for bk_dict, bk_key in [
                (by_market,  market),
                (by_angle,   angle),
                (by_edge,    edge_b),
                (by_dq,      dq),
            ]:
                if bk_key not in bk_dict:
                    bk_dict[bk_key] = init_bucket()
                bk = bk_dict[bk_key]
                bk["n"] += 1
                bk["roi_sum"] += roi_delta
                if r == "WIN":   bk["wins"] += 1
                elif r == "LOSS": bk["losses"] += 1
                else:             bk["voids"] += 1

            # Cluster — 4-dim
            cluster_key = f"{market}|{angle}|{edge_b}|{dq}"
            if cluster_key not in by_cluster:
                by_cluster[cluster_key] = init_bucket()
            cb = by_cluster[cluster_key]
            cb["n"] += 1
            cb["roi_sum"] += roi_delta
            if r == "WIN":   cb["wins"] += 1
            elif r == "LOSS": cb["losses"] += 1
            else:             cb["voids"] += 1

            # Global
            global_b["n"] += 1
            global_b["roi_sum"] += roi_delta
            if r == "WIN":   global_b["wins"] += 1
            elif r == "LOSS": global_b["losses"] += 1
            else:             global_b["voids"] += 1

    out = {
        "byMarket":      {k: finalize(v) for k, v in by_market.items()},
        "byAngle":       {k: finalize(v) for k, v in by_angle.items()},
        "byEdgeRange":   {k: finalize(v) for k, v in by_edge.items()},
        "byDataQuality": {k: finalize(v) for k, v in by_dq.items()},
        "byCluster":     {k: finalize(v) for k, v in by_cluster.items()
                          if v["n"] >= MIN_SAMPLES},
        "global":        finalize(global_b),
        "minSamples":    MIN_SAMPLES,
        "updatedAt":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    g = out["global"]
    print(f"=== compute_pick_confidence.py ===")
    print(f"  Global: n={g.get('n',0)} · {g.get('wins',0)}W/{g.get('losses',0)}L · "
          f"Hit-Rate {g.get('rate','—')}% · ROI {g.get('roi','—')}%")
    print(f"  byMarket Cluster: {len(out['byMarket'])}")
    print(f"  byAngle  Cluster: {len(out['byAngle'])}")
    print(f"  byCluster (≥{MIN_SAMPLES}): {len(out['byCluster'])}")
    print(f"  → {STATS_FILE}")


if __name__ == "__main__":
    main()
