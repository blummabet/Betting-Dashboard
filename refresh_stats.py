#!/usr/bin/env python3
"""
refresh_stats.py — Fetches real xG / venue stats from understat.com
                   AND Elo ratings from clubelo.com,
                   then writes stats_cache.json next to the dashboard HTML.

This enriches the betting picks with:
  - Real home/away xG per game  (replaces goals-based formula)
  - Real home win rate & away win rate  (replaces proxy formula)
  - Elo rating per team  (improves result-pick confidence, match score)
  - When the dashboard loads stats_cache.json, pick reasons show
    "📐 X.X xG (Understat)" instead of "Ø X.X Expected Goals"

Covered leagues:
  Understat xG : ENG, GER, ITA, ESP, FRA  (Big-5)
  ClubElo      : ENG, GER, ITA, ESP, FRA + AUT, NED, SCO, TUR, SUI, POR

Usage:
  python3 refresh_stats.py

Only stdlib + requests required.
If missing: pip install requests
"""

import json
import re
import sys
import datetime
from pathlib import Path
from typing import Optional

# ── Auto-install requests if missing ──────────────────────────────────────────
try:
    import requests
except ImportError:
    import subprocess
    print("Installing requests…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── Config ─────────────────────────────────────────────────────────────────────
SEASON = 2025   # 2025-26 season (understat uses start year)

import http.client
import os
import time as _time

# ── API-Football config ────────────────────────────────────────────────────────
APIF_HOST  = "v3.football.api-sports.io"
APIF_KEY   = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2   # seconds between calls

# League key → API-Football league ID
LEAGUE_APIF = {
    "ENG": 39,   "GER": 78,  "ITA": 135, "ESP": 140, "FRA": 61,
    "AUT": 144,  "NED": 88,  "POR": 94,  "SCO": 179,
    "TUR": 203,  "SUI": 207,
}


def apif_get(endpoint: str, params: dict) -> list:
    """Fetch from API-Football with rate limiting. Returns response list."""
    if not APIF_KEY:
        return []
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path  = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=15)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        errors = data.get("errors", {})
        if isinstance(errors, dict) and errors:
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ⚠️  apif_get error ({endpoint}): {e}")
        return []
    finally:
        _time.sleep(APIF_DELAY)


def fetch_league_stats(league_id: int, season: int = 2025) -> dict:
    """
    Fetch all finished fixtures for a league season, compute per-team
    home/away win rates and goals/game averages (used as xG proxy).
    Returns {team_name: {xG_home, xGA_home, homeWinRate, ..., xg_fairness*}}
    """
    resp = apif_get("fixtures", {
        "league": league_id, "season": season,
        "status": "FT-AET-PEN",
    })
    if not resp:
        # Try next season as fallback
        resp = apif_get("fixtures", {
            "league": league_id, "season": season + 1,
            "status": "FT-AET-PEN",
        })
    if not resp:
        return {}

    # Aggregate per team
    teams: dict = {}
    for fx in resp:
        h_id   = fx["teams"]["home"]["id"]
        a_id   = fx["teams"]["away"]["id"]
        h_name = fx["teams"]["home"]["name"]
        a_name = fx["teams"]["away"]["name"]
        h_win  = fx["teams"]["home"].get("winner")
        a_win  = fx["teams"]["away"].get("winner")
        h_gf   = fx["goals"]["home"] or 0
        a_gf   = fx["goals"]["away"] or 0

        def _ensure(name):
            if name not in teams:
                teams[name] = {"home_gf": [], "home_ga": [], "home_wins": 0, "home_games": 0,
                               "away_gf": [], "away_ga": [], "away_wins": 0, "away_games": 0}

        _ensure(h_name)
        teams[h_name]["home_gf"].append(h_gf)
        teams[h_name]["home_ga"].append(a_gf)
        teams[h_name]["home_games"] += 1
        if h_win: teams[h_name]["home_wins"] += 1

        _ensure(a_name)
        teams[a_name]["away_gf"].append(a_gf)
        teams[a_name]["away_ga"].append(h_gf)
        teams[a_name]["away_games"] += 1
        if a_win: teams[a_name]["away_wins"] += 1

    result = {}
    for name, d in teams.items():
        hg = len(d["home_gf"]); ag = len(d["away_gf"])
        xg_h  = round(sum(d["home_gf"]) / hg, 3) if hg else None
        xga_h = round(sum(d["home_ga"]) / hg, 3) if hg else None
        xg_a  = round(sum(d["away_gf"]) / ag, 3) if ag else None
        xga_a = round(sum(d["away_ga"]) / ag, 3) if ag else None
        result[name] = {
            "xG_home":          xg_h,
            "xGA_home":         xga_h,
            "homeWinRate":      round(d["home_wins"] / hg, 3) if hg else None,
            "home_games":       hg,
            "xG_away":          xg_a,
            "xGA_away":         xga_a,
            "awayWinRate":      round(d["away_wins"] / ag, 3) if ag else None,
            "away_games":       ag,
            # xG fairness not computable from goals alone — set neutral
            "xg_fairness":      1.0,
            "xg_fairness_home": 1.0,
            "xg_fairness_away": 1.0,
        }
    return result


def process_league(league_key: str) -> dict:
    league_id = LEAGUE_APIF.get(league_key)
    if not league_id:
        return {}
    print(f"  📊  {league_key}  (API-Football ID {league_id})")
    try:
        stats = fetch_league_stats(league_id)
        if stats:
            sample = list(stats.items())[:2]
            for name, s in sample:
                print(f"       {name:<30}  xG_h={s['xG_home'] or '-':>4}  "
                      f"xG_a={s['xG_away'] or '-':>4}  "
                      f"WR_h={s['homeWinRate'] or '-':>4}  "
                      f"WR_a={s['awayWinRate'] or '-':>4}")
            print(f"       → {len(stats)} teams")
        else:
            print(f"       ⚠️  No data returned")
        return stats
    except Exception as exc:
        print(f"       ⚠️  Failed: {exc}")
        return {}


# ════════════════════════════════════════════════════════════════════════════════
#  CLUB ELO
# ════════════════════════════════════════════════════════════════════════════════

def fetch_elo_snapshot(date_str: str) -> dict[str, tuple]:
    """
    Fetch Elo ratings for all clubs from clubelo.com for a given date.
    Returns {club_elo_name: (elo_float, country_code)}.
    CSV format: Rank,Club,Country,Level,Elo,From,To
    """
    url = f"http://api.clubelo.com/{date_str}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    elo_map: dict[str, tuple] = {}
    for line in resp.text.strip().splitlines()[1:]:   # skip header
        parts = line.split(",")
        if len(parts) >= 5:
            club    = parts[1].strip()
            country = parts[2].strip().upper()
            try:
                elo_map[club] = (round(float(parts[4].strip()), 1), country)
            except ValueError:
                pass
    return elo_map


# Supported league keys (must match all_stats keys)
SUPPORTED_LEAGUES = {"ENG", "GER", "ITA", "ESP", "FRA", "AUT", "NED", "SCO", "TUR", "SUI", "POR"}


def merge_elo_into_stats(all_stats: dict, elo_raw: dict[str, tuple]) -> int:
    """
    Merge Elo ratings into all_stats[league_key][team_name].
    Creates stub entries {elo: value} for teams not yet in all_stats
    (e.g. when Understat failed and all leagues are empty).
    Returns number of teams matched/created.
    """
    # Build lookup: our_name → (elo_value, country_code)
    our_to_elo: dict[str, tuple] = {}
    for elo_name, (elo_val, country) in elo_raw.items():
        our_name = ELO_NAME_MAP.get(elo_name)
        if our_name:
            our_to_elo[our_name] = (elo_val, country)
        else:
            # Direct match: maybe our HTML name == ClubElo name
            our_to_elo[elo_name] = (elo_val, country)

    # Ensure all supported league keys exist
    for key in SUPPORTED_LEAGUES:
        all_stats.setdefault(key, {})

    matched = 0

    # Pass 1: update existing team entries
    for league_key, teams in all_stats.items():
        for team_name, entry in teams.items():
            if team_name in our_to_elo:
                entry["elo"] = our_to_elo[team_name][0]
                matched += 1
            else:
                entry.setdefault("elo", None)

    # Pass 2: create stub entries for teams not yet present
    # (happens when Understat failed — ensures Elo is always populated)
    for our_name, (elo_val, country) in our_to_elo.items():
        if country not in SUPPORTED_LEAGUES:
            continue
        league_teams = all_stats.get(country, {})
        if our_name not in league_teams:
            # Only add to the correct league bucket
            all_stats[country][our_name] = {
                "xG_home": None, "xGA_home": None, "homeWinRate": None, "home_games": 0,
                "xG_away": None, "xGA_away": None, "awayWinRate": None, "away_games": 0,
                "elo": elo_val,
            }
            matched += 1

    return matched


def print_elo_summary(all_stats: dict):
    print("  🏆  Elo merge summary by league:")
    for league_key, teams in all_stats.items():
        found  = sum(1 for e in teams.values() if e.get("elo"))
        total  = len(teams)
        sample = [(n, e["elo"]) for n, e in teams.items() if e.get("elo")][:3]
        s_str  = "  ".join(f"{n} {v}" for n, v in sample)
        print(f"       {league_key}: {found}/{total} matched   eg. {s_str}")


# ════════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════════

def main():
    out = Path(__file__).parent / "stats_cache.json"
    today = datetime.date.today().isoformat()
    print(f"🔄  Stats refresh — season {SEASON}/{SEASON + 1}  ({today})\n")

    # ── Step 1: API-Football — goals/game + win rates (xG proxy) ────────────
    print("━" * 58)
    print("  API-FOOTBALL — goals/game + venue win rates (xG proxy)")
    print("━" * 58)
    all_stats: dict = {}
    for key in LEAGUE_APIF:
        all_stats[key] = process_league(key)

    # ── Step 2: ClubElo ratings ───────────────────────────────────────────────
    print("━" * 58)
    print("  CLUBELO — Elo ratings")
    print("━" * 58)
    elo_ok = False
    # Try today, then yesterday as fallback (ClubElo updates daily but sometimes lags)
    for attempt_date in [today, (datetime.date.today() - datetime.timedelta(days=1)).isoformat()]:
        try:
            print(f"  Fetching http://api.clubelo.com/{attempt_date} …")
            elo_raw = fetch_elo_snapshot(attempt_date)
            print(f"  → {len(elo_raw)} clubs found in snapshot")
            matched = merge_elo_into_stats(all_stats, elo_raw)
            print_elo_summary(all_stats)
            print(f"  → {matched} team Elo values merged into stats_cache\n")
            elo_ok = True
            break
        except Exception as exc:
            print(f"  ⚠️  ClubElo fetch failed for {attempt_date}: {exc}")

    if not elo_ok:
        print("  ⚠️  ClubElo unavailable — Elo fields will be null (picks fall back to form-only)\n")
        for teams in all_stats.values():
            for entry in teams.values():
                entry.setdefault("elo", None)

    # ── Step 3: (handled inside merge_elo_into_stats — stubs auto-created) ──────

    # ── Step 4: Write output ──────────────────────────────────────────────────
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)

    total_teams   = sum(len(v) for v in all_stats.values())
    elo_populated = sum(
        1 for teams in all_stats.values()
        for e in teams.values() if e.get("elo")
    )
    xg_populated  = sum(
        1 for teams in all_stats.values()
        for e in teams.values() if e.get("xG_home")
    )

    print("━" * 58)
    print(f"✅  stats_cache.json written")
    fair_populated = sum(
        1 for teams in all_stats.values()
        for e in teams.values() if e.get("xg_fairness") is not None
    )

    print(f"   Teams total : {total_teams}")
    print(f"   Goals/game  : {xg_populated} teams  (all leagues, as xG proxy)")
    print(f"   Win rates   : {xg_populated} teams  (home/away)")
    print(f"   Elo data    : {elo_populated} teams  (all covered leagues)")
    print(f"   File        : {out}")
    print()
    print("ℹ️  Reload season-finish.html to apply new stats.")
    print("   All leagues → Goals/game (xG proxy) + Win rates + Elo")


if __name__ == "__main__":
    main()
