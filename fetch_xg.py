#!/usr/bin/env python3
"""
fetch_xg.py — Heim/Auswärts-spezifische Tore-Statistiken pro Team.

Fetcht via API-Football /teams/statistics die Saison-Durchschnitte getrennt
nach Heim- und Auswärtsspielen:
  - Tore erzeugt/Spiel (Heim)   → homeGfAvg
  - Tore kassiert/Spiel (Heim)  → homeGaAvg
  - Tore erzeugt/Spiel (Auswärts) → awayGfAvg
  - Tore kassiert/Spiel (Auswärts) → awayGaAvg
  - Heimsieg-Rate                → homeWinRate
  - Auswärtssieg-Rate            → awayWinRate
  - Clean-Sheet-Rate Heim/Auswärts
  - Failed-to-Score-Rate Heim/Auswärts

Diese Werte ersetzen im pick-engine.js die bisherigen Saison-Gesamtschnitte
durch venue-spezifische Werte — Basis für das einheitliche Poisson-Modell.

API-Credits: 1 Call pro Team (~160–190 Calls total).
Laufzeit:    ~4–5 Min (inkl. Rate-Limiting 1.2s/Call).

Run:   python3 fetch_xg.py
Cron:  Täglich (zusammen mit fetch_squads.py in fetch-squads.yml)
"""

import json
import os
import sys
import time
import http.client
from datetime import datetime, timezone


def _current_season(dt=None):   # (02.08.2026, Lucas) Saison-Rollover-Fix
    dt = dt or datetime.now(timezone.utc)
    return dt.year if dt.month >= 6 else dt.year - 1
from pathlib import Path

BASE       = Path(__file__).parent
CACHE_FILE = BASE / "xg_cache.json"

APIF_HOST  = "v3.football.api-sports.io"
APIF_KEY   = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2   # seconds between calls

# League key → API-Football league ID (must stay in sync with update_dashboard.py)
LEAGUES = {
    "ENG": 39,  "GER": 78,  "ITA": 135, "ESP": 140, "FRA": 61,
    "AUT": 218, "NED": 88,  "POR": 94,  "SCO": 179, "TUR": 203,
    "SUI": 207, "BEL": 144, "POL": 106, "HUN": 271, "CRO": 210,
}

# ── API helper ────────────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> dict | list | None:
    if not APIF_KEY:
        return None
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path  = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        errors = data.get("errors", {})
        if isinstance(errors, dict) and errors:
            print(f"  ⚠ API error /{endpoint}: {errors}")
            return None
        return data.get("response")
    except Exception as e:
        print(f"  ⚠ apif_get /{endpoint} error: {e}")
        return None
    finally:
        time.sleep(APIF_DELAY)


# ── Fetch one team's stats ────────────────────────────────────────────────────

def fetch_team_stats(team_id: int, league_id: int, season: int) -> dict | None:
    """
    Fetches /teams/statistics for one team.
    Returns a dict with home/away goals, win-rates, clean sheets — or None.
    """
    resp = apif_get("teams/statistics", {
        "team":   team_id,
        "league": league_id,
        "season": season,
    })

    # Response is a single dict (not a list) for this endpoint
    if isinstance(resp, list) and resp:
        resp = resp[0]
    if not isinstance(resp, dict):
        return None

    fixtures = resp.get("fixtures", {})
    goals    = resp.get("goals", {})
    cs       = resp.get("clean_sheet", {})
    fts      = resp.get("failed_to_score", {})

    played_h = fixtures.get("played", {}).get("home") or 0
    played_a = fixtures.get("played", {}).get("away") or 0
    wins_h   = fixtures.get("wins",   {}).get("home") or 0
    wins_a   = fixtures.get("wins",   {}).get("away") or 0
    draws_h  = fixtures.get("draws",  {}).get("home") or 0
    draws_a  = fixtures.get("draws",  {}).get("away") or 0

    def _avg(node, venue):
        """Parse goals.for.average.home — returns float or None."""
        v = node.get("average", {}).get(venue)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _rate(count, played):
        return round(count / played, 3) if played > 0 else None

    home_gf  = _avg(goals.get("for",     {}), "home")
    home_ga  = _avg(goals.get("against", {}), "home")
    away_gf  = _avg(goals.get("for",     {}), "away")
    away_ga  = _avg(goals.get("against", {}), "away")

    # Fallback: compute from totals when average string is absent
    if home_gf is None:
        total_home_gf = goals.get("for",     {}).get("total", {}).get("home")
        if total_home_gf and played_h:
            home_gf = round(total_home_gf / played_h, 2)
    if home_ga is None:
        total_home_ga = goals.get("against", {}).get("total", {}).get("home")
        if total_home_ga and played_h:
            home_ga = round(total_home_ga / played_h, 2)
    if away_gf is None:
        total_away_gf = goals.get("for",     {}).get("total", {}).get("away")
        if total_away_gf and played_a:
            away_gf = round(total_away_gf / played_a, 2)
    if away_ga is None:
        total_away_ga = goals.get("against", {}).get("total", {}).get("away")
        if total_away_ga and played_a:
            away_ga = round(total_away_ga / played_a, 2)

    cs_h  = cs.get("home")
    cs_a  = cs.get("away")
    fts_h = fts.get("home")
    fts_a = fts.get("away")

    return {
        # Venue-specific goals averages — primary inputs for Poisson FV
        "homeGfAvg":     home_gf,           # avg goals scored per home game
        "homeGaAvg":     home_ga,           # avg goals conceded per home game
        "awayGfAvg":     away_gf,           # avg goals scored per away game
        "awayGaAvg":     away_ga,           # avg goals conceded per away game
        # Venue-specific win/draw rates — for Poisson calibration & DC FV
        "homeWinRate":   _rate(wins_h,  played_h),
        "awayWinRate":   _rate(wins_a,  played_a),
        "homeDrawRate":  _rate(draws_h, played_h),
        "awayDrawRate":  _rate(draws_a, played_a),
        # Defensive solidity signals (used in under-pick & FV calibration)
        "csRateHome":    _rate(cs_h  or 0, played_h),
        "csRateAway":    _rate(cs_a  or 0, played_a),
        "ftsRateHome":   _rate(fts_h or 0, played_h),
        "ftsRateAway":   _rate(fts_a or 0, played_a),
        # Metadata
        "playedHome":    played_h,
        "playedAway":    played_a,
        "season":        season,
        "fetchedAt":     datetime.now(timezone.utc).isoformat(),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not APIF_KEY:
        print("❌  APISPORTS_KEY not set — aborting.")
        sys.exit(1)

    # Load squad_cache.json to get team IDs + leagueKey
    squad_cache_path = BASE / "squad_cache.json"
    if not squad_cache_path.exists():
        print("❌  squad_cache.json not found — run fetch_squads.py first.")
        sys.exit(1)

    with open(squad_cache_path) as f:
        squad_cache = json.load(f)

    teams = squad_cache.get("teams", {})
    season = squad_cache.get("season") or _current_season()   # aus Squad-Cache (jetzt dynamisch gestempelt), sonst laufende Saison

    # Load existing cache to allow incremental updates
    existing: dict = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # Build list: (team_id_int, league_key, league_apif_id)
    todo = []
    for tid_str, tdata in teams.items():
        league_key = tdata.get("leagueKey")
        apif_id    = LEAGUES.get(league_key)
        if not apif_id:
            continue
        todo.append((int(tid_str), league_key, apif_id))

    print(f"🔍  {len(todo)} Teams — fetche Heim/Auswärts-Statistiken (Saison {season})…")

    results = dict(existing)  # start from existing cache
    ok, skipped, failed = 0, 0, 0

    for idx, (team_id, league_key, apif_id) in enumerate(todo, 1):
        tid_str = str(team_id)
        team_name = teams[tid_str].get("name", f"ID:{team_id}")

        # Skip if already fresh (fetched today)
        cached = existing.get(tid_str, {})
        fetched_at = cached.get("fetchedAt", "")
        if fetched_at and fetched_at[:10] == datetime.now().strftime("%Y-%m-%d"):
            skipped += 1
            continue

        print(f"  [{idx}/{len(todo)}] {team_name} ({league_key}, team={team_id})…", end=" ", flush=True)

        stats = fetch_team_stats(team_id, apif_id, season)

        if stats is None:
            # Try previous season as fallback
            stats = fetch_team_stats(team_id, apif_id, season - 1)

        if stats and (stats.get("homeGfAvg") is not None or stats.get("awayGfAvg") is not None):
            results[tid_str] = stats
            ok += 1
            print(f"✓  hGf={stats['homeGfAvg']} hGa={stats['homeGaAvg']}  aGf={stats['awayGfAvg']} aGa={stats['awayGaAvg']}")
        else:
            failed += 1
            # Keep existing entry if present
            if tid_str in existing:
                results[tid_str] = existing[tid_str]
            print("✗  keine Daten")

    # Write cache
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅  Fertig — {ok} aktualisiert · {skipped} übersprungen (heute schon) · {failed} fehlgeschlagen")
    print(f"💾  Gespeichert: {CACHE_FILE}")


if __name__ == "__main__":
    main()
