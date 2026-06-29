#!/usr/bin/env python3
"""
fetch_liga_xg.py — echtes Klub-xG (+ Schuss-Stats) für die Top-5-Ligen (25.06.2026, Lucas:
„xG in Liga viel aussagekräftiger"). Schreibt liga-data.json["xgStats"][teamId].

Reuse statt Neubau: ruft `fetch_wm_nt_xg.aggregate_team_stats(api_id, our_id)` pro Liga-Team auf —
das aggregiert ECHTES `expected_goals` aus /fixtures/statistics (+ xGsim-Schuss-Proxy + shotsInside/
sot/keyPasses/rating) über die letzten N Spiele. Geht direkt, weil die Liga-Team-`id` schon die
API-Football-ID ist (anders als WM, das per Name auflösen muss). Speist gleichzeitig die Signale
xg_strength, chance_creation und form_rating.

xgStats-Eintrag: {xgForAvg, xgAgainstAvg, xgGames, xgSimForAvg, shotsInsideForAvg, sotForAvg,
keyPassesForAvg, ratingAvg, games, source:"apif_real", updatedAt}. `source="apif_real"` → von
xg_strength als zählbares xG akzeptiert. Staleness: Teams mit frischem xG (< 24h) übersprungen
(spart API-Quota; läuft 2×/Tag im Liga-Workflow). Live braucht APISPORTS_KEY.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
import cocobet_dataset as D  # 29.06.2026: dataset-aware (MLS)
LIGA_FILE = D.data_file()   # 29.06.2026: liga-data.json ODER mls-data.json je COCOBET_DATASET
STALE_H = 24


def _is_fresh(updated_at: str | None, hours: int = STALE_H) -> bool:
    if not updated_at:
        return False
    try:
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts) < timedelta(hours=hours)
    except Exception:
        return False


def build_xg_entry(stats: dict | None) -> dict | None:
    """Aggregat aus aggregate_team_stats → xgStats-Eintrag. source→'apif_real' wenn echtes xG da
    (xg_strength akzeptiert nur understat/apif_real als zählbares xG). Reiner Transformer (testbar)."""
    if not stats:
        return None
    entry = dict(stats)
    if entry.get("xgForAvg") is not None and entry.get("xgGames"):
        entry["source"] = "apif_real"
    entry.setdefault("updatedAt", datetime.now(timezone.utc).isoformat())
    return entry


def apply_to_wm(wm: dict, aggregate_fn) -> int:
    """Iteriert Liga-Teams, ruft aggregate_fn(api_id:int, our_id:str), schreibt wm['xgStats'].
    Gibt Anzahl aktualisierter Teams zurück. aggregate_fn injizierbar → testbar."""
    wm.setdefault("xgStats", {})
    teams = []
    seen = set()
    for g in (wm.get("groups") or {}).values():
        for t in (g.get("teams") or []):
            tid = t.get("id")
            if tid and tid not in seen:
                seen.add(tid)
                teams.append(tid)
    updated = 0
    for tid in teams:
        if _is_fresh((wm["xgStats"].get(tid) or {}).get("updatedAt")):
            continue
        try:
            stats = aggregate_fn(int(tid), tid)
        except Exception as e:
            print(f"   ⚠️  {tid}: {e}")
            continue
        entry = build_xg_entry(stats)
        if entry:
            wm["xgStats"][tid] = entry
            updated += 1
            print(f"   ✓ {tid}: xGfor {entry.get('xgForAvg')} / xGag {entry.get('xgAgainstAvg')} "
                  f"({entry.get('xgGames')} Spiele echtes xG)")
    return updated


def main():
    print("=== fetch_liga_xg.py ===")
    if not os.environ.get("APISPORTS_KEY"):
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen (läuft nur im Workflow).")
        sys.exit(0)
    if not LIGA_FILE.exists():
        print("  ❌  liga-data.json fehlt — erst build_liga_data.py.")
        sys.exit(1)
    import fetch_wm_nt_xg as N   # aggregate_team_stats + API-Helper (APISPORTS_KEY)
    wm = json.loads(LIGA_FILE.read_text(encoding="utf-8"))
    n = apply_to_wm(wm, N.aggregate_team_stats)
    LIGA_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ xGStats für {n} Liga-Teams aktualisiert.")


if __name__ == "__main__":
    main()
