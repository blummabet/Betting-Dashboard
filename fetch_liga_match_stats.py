#!/usr/bin/env python3
"""
fetch_liga_match_stats.py — Post-Match-xG ans gespielte Liga-Fixture hängen (26.06.2026, Lucas:
„nach jedem Spiel xG holen und daraus lernen").

Schreibt fixture.result.stats = {xgHome, xgAway, xgTotal, xgSource} für beendete Liga-Spiele. Genau
diese Stats liest build_signal_ledger → resolve_wm_results.process_verdict bewertet den Pick als
verdient / Pech / glücklich → prozess-gewichtetes Bayesian-Update (UNLUCKY-Loss milder bestraft).
Damit lernt die Liga-Engine Können von Varianz zu trennen, von Spiel zu Spiel.

Gecacht (liga_match_stats_cache.json je fixture-id), weil build_liga_data die groups je Lauf neu baut
→ Re-Attach ist billig. Läuft im Liga-Workflow NACH build/resolve, VOR build_signal_ledger.
Reuse: fetch_wm_nt_xg._extract_fixture_stats (echtes xG + xGsim-Fallback aus /fixtures/statistics).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent
LIGA_FILE = BASE / "liga-data.json"
CACHE_FILE = BASE / "liga_match_stats_cache.json"
FINISHED = {"FT", "AET", "PEN"}


def build_match_stats(extract: dict, home_tid: str, away_tid: str) -> dict | None:
    """per-Team-Extract (_extract_fixture_stats) → {xgHome,xgAway,xgTotal,xgSource}. Echtes xG wenn
    da, sonst xGsim-Schuss-Proxy. Reiner Transformer (testbar)."""
    me = extract.get(int(home_tid)) if extract else None
    op = extract.get(int(away_tid)) if extract else None
    if not me or not op:
        return None
    h_real, a_real = me.get("xg"), op.get("xg")
    h = h_real if h_real is not None else me.get("xgsim")
    a = a_real if a_real is not None else op.get("xgsim")
    if h is None or a is None:
        return None
    return {"xgHome": round(h, 2), "xgAway": round(a, 2), "xgTotal": round(h + a, 2),
            "xgSource": "api" if (h_real is not None and a_real is not None) else "sim"}


def main():
    print("=== fetch_liga_match_stats.py ===")
    if not os.environ.get("APISPORTS_KEY"):
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        sys.exit(0)
    if not LIGA_FILE.exists():
        print("  ❌  liga-data.json fehlt.")
        sys.exit(1)
    import fetch_wm_nt_xg as N
    wm = json.loads(LIGA_FILE.read_text(encoding="utf-8"))
    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    import time
    attached = fetched = 0
    for gd in (wm.get("groups") or {}).values():
        for fx in (gd.get("fixtures") or []):
            res = fx.get("result") or {}
            if str(res.get("status", "")).upper() not in FINISHED:
                continue
            fid = fx.get("fid")
            if not fid:
                continue
            key = str(fid)
            stats = cache.get(key)
            if stats is None:
                ex = N._extract_fixture_stats(int(fid))
                stats = build_match_stats(ex, fx["home"], fx["away"]) or {}
                cache[key] = stats
                fetched += 1
                time.sleep(0.25)
            if stats:
                res["stats"] = stats
                fx["result"] = res
                attached += 1
    LIGA_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ Match-xG an {attached} gespielte Spiele gehängt ({fetched} neu geholt)")


if __name__ == "__main__":
    main()
