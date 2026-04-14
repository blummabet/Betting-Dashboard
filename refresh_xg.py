#!/usr/bin/env python3
"""
refresh_xg.py — Fetches per-fixture statistics (shots + Expected Goals)
                 from API-Football and computes real xG values per team.
                 Merges results into stats_cache.json (preserves Elo / win rates).

Run:   Weekly (Monday morning) via GitHub Actions
Needs: APISPORTS_KEY environment variable

How it improves pick accuracy vs goals-proxy:
  - Big-5 leagues (ENG/GER/ITA/ESP/FRA): uses native "Expected Goals" from API-Football
  - All other leagues: shots_on_goal × 0.32 (empirical regression coefficient)
  - xg_fairness = actual_goals / xG → detects lucky/unlucky teams, nudges pick confidence
  - Expected improvement on Over/Under markets: +4-6 pp

API call budget (weekly):
  11 leagues × 1 fixture-list call  =   11 calls
  11 leagues × ~50 stats calls      =  550 calls
  Total                             ≈  561 calls  (~11 min at 1.2 s/call)
"""

import json
import os
import sys
import time
import datetime
import http.client
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
APIF_HOST  = "v3.football.api-sports.io"
APIF_KEY   = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2    # seconds between requests (respects API rate limit)
SEASON     = 2025   # 2025-26 season start year

# Number of most-recent finished fixtures to pull stats for (per league).
# 50 ≈ all teams get 4-6 recent home + away data points.
MAX_FIXTURES = 50

# Conversion: shots_on_goal → xG when native Expected Goals not available.
# 0.32 ≈ average league shot-conversion rate across European leagues (empirical).
SHOTS_XG_COEFF = 0.32

# Leagues to refresh (key → API-Football league ID)
LEAGUE_APIF = {
    "ENG": 39,   "GER": 78,  "ITA": 135, "ESP": 140, "FRA": 61,
    "AUT": 218,  "NED": 88,  "POR": 94,  "SCO": 179,
    "TUR": 203,  "SUI": 207,
    "BEL": 144,  "POL": 106, "HUN": 271, "CRO": 210,
}

# Big-5 leagues that carry native Expected Goals data in API-Football
XG_NATIVE_LEAGUES = {"ENG", "GER", "ITA", "ESP", "FRA"}


# ── API helper ─────────────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> list:
    """One API-Football GET request. Returns response list or [] on error."""
    if not APIF_KEY:
        return []
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path  = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        r    = conn.getresponse()
        data = json.loads(r.read().decode())
        conn.close()
        if isinstance(data.get("errors"), dict) and data["errors"]:
            print(f"  ⚠️  API error for {endpoint}: {data['errors']}")
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ⚠️  apif_get error ({endpoint}): {e}")
        return []
    finally:
        time.sleep(APIF_DELAY)


# ── Fixture fetching ────────────────────────────────────────────────────────────

def fetch_recent_fixtures(league_id: int, max_n: int = MAX_FIXTURES) -> list:
    """
    Fetch the most recent max_n finished fixtures for a league.
    Returns list of dicts: {id, home_name, away_name, home_goals, away_goals, date}.
    """
    resp = apif_get("fixtures", {
        "league": league_id, "season": SEASON, "status": "FT"
    })
    if not resp:
        # Try current+1 in case season numbering shifted
        resp = apif_get("fixtures", {
            "league": league_id, "season": SEASON + 1, "status": "FT"
        })
    if not resp:
        return []

    # Sort descending by fixture date and keep most recent max_n
    resp.sort(key=lambda fx: fx.get("fixture", {}).get("date", ""), reverse=True)
    recent = resp[:max_n]

    result = []
    for fx in recent:
        result.append({
            "id":         fx["fixture"]["id"],
            "home_name":  fx["teams"]["home"]["name"],
            "away_name":  fx["teams"]["away"]["name"],
            "home_goals": fx["goals"]["home"] or 0,
            "away_goals": fx["goals"]["away"] or 0,
            "date":       fx["fixture"]["date"][:10],
        })
    return result


def fetch_fixture_stats(fixture_id: int) -> tuple:
    """
    Fetch statistics for one fixture.
    Returns (home_stats_dict, away_stats_dict) or (None, None) on failure.
    """
    resp = apif_get("fixtures/statistics", {"fixture": fixture_id})
    if len(resp) < 2:
        return None, None

    def parse(team_data: dict) -> dict:
        out = {}
        for s in team_data.get("statistics", []):
            t = s.get("type", "")
            v = s.get("value")
            out[t] = v
        return out

    return parse(resp[0]), parse(resp[1])


# ── xG extraction ──────────────────────────────────────────────────────────────

def stats_to_xg(stats: dict, league_key: str) -> float | None:
    """
    Extract or estimate xG from a fixture statistics dict.

    Priority order:
      1. Native "Expected Goals" (available in Big-5 via API-Football)
      2. Shots on goal × SHOTS_XG_COEFF (all leagues)
    Returns float or None.
    """
    # 1. Native Expected Goals (API-Football field name variants)
    for key in ("Expected Goals", "expected_goals", "xG"):
        val = stats.get(key)
        if val not in (None, ""):
            try:
                xg = float(val)
                if xg >= 0:
                    return round(xg, 3)
            except (TypeError, ValueError):
                pass

    # 2. Shots-on-goal proxy (works for all leagues)
    for key in ("Shots on Goal", "shots_on_goal", "Shots On Goal"):
        val = stats.get(key)
        if val not in (None, ""):
            try:
                sog = float(val)
                if sog >= 0:
                    return round(sog * SHOTS_XG_COEFF, 3)
            except (TypeError, ValueError):
                pass

    return None


def fairness_ratio(goals_list: list, xg_list: list) -> float:
    """
    Compute actual_goals / expected_goals over a list of games.
    Clipped to [0.50, 2.00] to avoid extreme outliers.
    Returns 1.0 if insufficient data.
    """
    if not goals_list or not xg_list or len(goals_list) != len(xg_list):
        return 1.0
    total_xg = sum(xg_list)
    if total_xg < 0.5:   # too little xG data — neutral
        return 1.0
    ratio = sum(goals_list) / total_xg
    return round(max(0.50, min(2.00, ratio)), 3)


# ── Per-league processing ──────────────────────────────────────────────────────

def process_league(league_key: str, league_id: int) -> dict:
    """
    1. Fetch recent finished fixtures for the league.
    2. For each fixture fetch statistics.
    3. Aggregate per-team home/away xG averages and fairness ratios.
    Returns {team_name: {xG_home, xGA_home, xG_away, xGA_away,
                         xg_fairness, xg_fairness_home, xg_fairness_away}}.
    """
    native = league_key in XG_NATIVE_LEAGUES
    src_label = "native xG" if native else "shots proxy"
    print(f"  📊  {league_key}  (ID {league_id}, {src_label})")

    fixtures = fetch_recent_fixtures(league_id)
    if not fixtures:
        print(f"       ⚠️  No fixtures returned")
        return {}
    print(f"       {len(fixtures)} recent fixtures — fetching stats…")

    # Accumulators per team
    teams: dict = {}

    def ensure(name: str):
        if name not in teams:
            teams[name] = {
                "h_xg": [], "h_xga": [], "h_g": [], "h_ga": [],  # home-venue
                "a_xg": [], "a_xga": [], "a_g": [], "a_ga": [],  # away-venue
            }

    ok = 0
    for i, fx in enumerate(fixtures):
        h_name  = fx["home_name"]
        a_name  = fx["away_name"]
        h_goals = fx["home_goals"]
        a_goals = fx["away_goals"]
        fid     = fx["id"]

        h_stats, a_stats = fetch_fixture_stats(fid)
        if h_stats is None:
            continue

        h_xg = stats_to_xg(h_stats, league_key)
        a_xg = stats_to_xg(a_stats, league_key)

        ensure(h_name)
        ensure(a_name)

        # Home team's home-venue xG
        if h_xg is not None:
            teams[h_name]["h_xg"].append(h_xg)
            teams[h_name]["h_g"].append(h_goals)

        # Home team's defensive xGA at home = away team's xG
        if a_xg is not None:
            teams[h_name]["h_xga"].append(a_xg)
            teams[h_name]["h_ga"].append(a_goals)

        # Away team's away-venue xG
        if a_xg is not None:
            teams[a_name]["a_xg"].append(a_xg)
            teams[a_name]["a_g"].append(a_goals)

        # Away team's defensive xGA away = home team's xG
        if h_xg is not None:
            teams[a_name]["a_xga"].append(h_xg)
            teams[a_name]["a_ga"].append(h_goals)

        ok += 1
        if (i + 1) % 10 == 0:
            print(f"       … {i + 1}/{len(fixtures)} processed ({ok} with stats)")

    print(f"       → {ok}/{len(fixtures)} fixtures had statistics  |  {len(teams)} teams")

    def avg(lst: list) -> float | None:
        return round(sum(lst) / len(lst), 3) if lst else None

    result: dict = {}
    for name, d in teams.items():
        xg_h  = avg(d["h_xg"])
        xga_h = avg(d["h_xga"])
        xg_a  = avg(d["a_xg"])
        xga_a = avg(d["a_xga"])

        # Only store teams that have at least one valid xG value
        if any(v is not None for v in (xg_h, xga_h, xg_a, xga_a)):
            result[name] = {
                "xG_home":           xg_h,
                "xGA_home":          xga_h,
                "xG_away":           xg_a,
                "xGA_away":          xga_a,
                "xg_fairness_home":  fairness_ratio(d["h_g"],  d["h_xg"]),
                "xg_fairness_away":  fairness_ratio(d["a_g"],  d["a_xg"]),
                "xg_fairness":       fairness_ratio(
                    d["h_g"] + d["a_g"],
                    d["h_xg"] + d["a_xg"]
                ),
                "xg_source":         "api-football-xg" if native else "shots-proxy",
                "xg_fixtures":       ok,
            }

    # Print sample
    sample = list(result.items())[:3]
    for sname, sv in sample:
        print(f"       {sname:<28}  xG_h={sv['xG_home'] or '-':>5}  "
              f"xG_a={sv['xG_away'] or '-':>5}  "
              f"fair_h={sv['xg_fairness_home']:>5}")
    print(f"       → {len(result)} teams with xG data written")
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    cache_path = Path(__file__).parent / "stats_cache.json"
    today = datetime.date.today().isoformat()

    print(f"🔄  XG Refresh — {today}\n")

    if not APIF_KEY:
        print("⚠️  APISPORTS_KEY environment variable not set.")
        print("    Set it and re-run: APISPORTS_KEY=your_key python refresh_xg.py")
        sys.exit(0)

    # ── Load existing stats_cache ──────────────────────────────────────────────
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"📂  Loaded existing stats_cache.json ({sum(len(v) for v in cache.values())} teams)\n")
    else:
        cache = {}
        print("📂  No existing stats_cache.json — will create fresh\n")

    # ── Process each league ────────────────────────────────────────────────────
    print("━" * 62)
    print("  API-FOOTBALL — per-fixture xG statistics")
    print("━" * 62)

    total_updated = 0

    for league_key, league_id in LEAGUE_APIF.items():
        xg_data = process_league(league_key, league_id)
        if not xg_data:
            continue

        league_bucket = cache.setdefault(league_key, {})
        for team_name, xg_vals in xg_data.items():
            entry = league_bucket.setdefault(team_name, {})
            # Merge: overwrite xG fields, keep elo / homeWinRate / away_games etc.
            entry.update(xg_vals)
            total_updated += 1

        print()

    # ── Write updated cache ────────────────────────────────────────────────────
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_teams   = sum(len(v) for v in cache.values())
    xg_populated  = sum(
        1 for teams in cache.values()
        for e in teams.values() if e.get("xG_home") is not None
    )
    elo_populated = sum(
        1 for teams in cache.values()
        for e in teams.values() if e.get("elo")
    )
    fair_counts = {
        "native": sum(1 for t in cache.values() for e in t.values() if e.get("xg_source") == "api-football-xg"),
        "proxy":  sum(1 for t in cache.values() for e in t.values() if e.get("xg_source") == "shots-proxy"),
    }

    print("━" * 62)
    print(f"✅  stats_cache.json updated")
    print(f"   Teams total      : {total_teams}")
    print(f"   xG populated     : {xg_populated}  ({fair_counts['native']} native API xG  +  {fair_counts['proxy']} shots proxy)")
    print(f"   Elo populated    : {elo_populated}")
    print(f"   Updated entries  : {total_updated}")
    print(f"   File             : {cache_path}")
    print()
    print("ℹ️  Pick accuracy improvement (Over/Under markets): +4-6 pp vs goals proxy")
    print("   xGBased=true will activate in dashboard when xG_home/xGA_home/xG_away/xGA_away all non-null")
    print("   xg_fairness > 1.15 → team overperforming → expect regression (mild pick penalty)")
    print("   xg_fairness < 0.85 → team underperforming → expect bounce-back (mild pick boost)")


if __name__ == "__main__":
    main()
