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

# ── HTTP headers for external requests (ClubElo) ──────────────────────────────
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BettingDashboard/1.0)"}

# ── ClubElo → dashboard name overrides ────────────────────────────────────────
# Maps ClubElo team names (right side) that differ from API-Football names (left side).
# Add entries here when a team's Elo data isn't being matched automatically.
# Example: "Man United" (our name) → ClubElo calls them "ManUnited"
ELO_NAME_MAP: dict[str, str] = {
    # ClubElo name → our (API-Football) name
    "ManUnited":      "Manchester United",
    "ManCity":        "Manchester City",
    "Ncastle":        "Newcastle United",
    "Wolves":         "Wolverhampton Wanderers",
    "WestHam":        "West Ham United",
    "Nottm Forest":   "Nottingham Forest",
    "Leverkusen":     "Bayer Leverkusen",
    "Gladbach":       "Borussia M'gladbach",
    "Dortmund":       "Borussia Dortmund",
    "Eintr Frankfurt": "Eintracht Frankfurt",
    "Bayern":         "Bayern Munich",
    "Paris":          "Paris Saint Germain",
    "St Etienne":     "Saint-Etienne",
    "Atletico":       "Atletico Madrid",
    "Betis":          "Real Betis",
    "Sociedad":       "Real Sociedad",
    "Villareal":      "Villarreal",
    "Inter":          "Inter Milan",
    "Spal":           "SPAL",
    "Verona":         "Hellas Verona",
    "PSV":            "PSV Eindhoven",
    "Ajax":           "Ajax",
    "Brugge":         "Club Brugge",
    "Anderlecht":     "R.S.C. Anderlecht",
    "Gent":           "KAA Gent",
    "Leuven":         "OH Leuven",
    "Red Bull Salzburg": "RB Salzburg",
    "Austria Wien":   "FK Austria Wien",
    "LASK":           "LASK",
    "Rapid":          "SK Rapid Wien",
}

# ── API-Football config ────────────────────────────────────────────────────────
APIF_HOST  = "v3.football.api-sports.io"
APIF_KEY   = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2   # seconds between calls

# League key → API-Football league ID
LEAGUE_APIF = {
    "ENG": 39,   "GER": 78,  "ITA": 135, "ESP": 140, "FRA": 61,
    "AUT": 218,  "NED": 88,  "POR": 94,  "SCO": 179,
    "TUR": 203,  "SUI": 207,
    "BEL": 144,  "POL": 106, "HUN": 271, "CRO": 210,
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


def fetch_league_stats(league_id: int, season: int = 2025) -> tuple[dict, dict]:
    """
    Fetch all finished fixtures for a league season, compute per-team
    home/away win rates and goals/game averages (used as xG proxy).
    Also computes currentStreak from fixture timestamps.
    Returns:
      - stats dict: {team_name: {xG_home, xGA_home, homeWinRate, ..., currentStreak}}
      - team_ids:   {team_name: team_id}  (used for teams/statistics batch calls)
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
        return {}, {}

    # Aggregate per team
    teams: dict = {}
    team_ids: dict[str, int] = {}

    def _ensure(name, tid):
        if name not in teams:
            teams[name] = {
                "home_gf": [], "home_ga": [], "home_wins": 0, "home_games": 0,
                "away_gf": [], "away_ga": [], "away_wins": 0, "away_games": 0,
                # Clean sheet + failed-to-score counts
                "home_clean_sheets": 0, "home_failed_score": 0,
                "away_clean_sheets": 0, "away_failed_score": 0,
                # For streak computation: list of (unix_ts, 'W'|'D'|'L')
                "_results_ts": [],
            }
        if tid:
            team_ids[name] = tid

    for fx in resp:
        h_id   = fx["teams"]["home"]["id"]
        a_id   = fx["teams"]["away"]["id"]
        h_name = fx["teams"]["home"]["name"]
        a_name = fx["teams"]["away"]["name"]
        h_win  = fx["teams"]["home"].get("winner")
        a_win  = fx["teams"]["away"].get("winner")
        h_gf   = fx["goals"]["home"] or 0
        a_gf   = fx["goals"]["away"] or 0
        ts     = fx.get("fixture", {}).get("timestamp") or 0

        _ensure(h_name, h_id)
        teams[h_name]["home_gf"].append(h_gf)
        teams[h_name]["home_ga"].append(a_gf)
        teams[h_name]["home_games"] += 1
        if h_win: teams[h_name]["home_wins"] += 1
        if a_gf == 0: teams[h_name]["home_clean_sheets"] += 1   # clean sheet at home
        if h_gf == 0: teams[h_name]["home_failed_score"] += 1   # failed to score at home
        h_result = "W" if h_win else ("L" if a_win else "D")
        teams[h_name]["_results_ts"].append((ts, h_result))

        _ensure(a_name, a_id)
        teams[a_name]["away_gf"].append(a_gf)
        teams[a_name]["away_ga"].append(h_gf)
        teams[a_name]["away_games"] += 1
        if a_win: teams[a_name]["away_wins"] += 1
        if h_gf == 0: teams[a_name]["away_clean_sheets"] += 1   # clean sheet away
        if a_gf == 0: teams[a_name]["away_failed_score"] += 1   # failed to score away
        a_result = "W" if a_win else ("L" if h_win else "D")
        teams[a_name]["_results_ts"].append((ts, a_result))

    result = {}
    for name, d in teams.items():
        hg = len(d["home_gf"]); ag = len(d["away_gf"])
        xg_h  = round(sum(d["home_gf"]) / hg, 3) if hg else None
        xga_h = round(sum(d["home_ga"]) / hg, 3) if hg else None
        xg_a  = round(sum(d["away_gf"]) / ag, 3) if ag else None
        xga_a = round(sum(d["away_ga"]) / ag, 3) if ag else None

        # Compute currentStreak: sort by timestamp, count consecutive W/L/D from end
        sorted_results = [r for _, r in sorted(d["_results_ts"], key=lambda x: x[0])]
        current_streak = 0
        if sorted_results:
            streak_type = sorted_results[-1]  # last result type
            for r in reversed(sorted_results):
                if r == streak_type:
                    current_streak += 1
                else:
                    break
            if streak_type == "L":
                current_streak = -current_streak  # negative = losing streak

        result[name] = {
            "xG_home":            xg_h,
            "xGA_home":           xga_h,
            "homeWinRate":        round(d["home_wins"]         / hg, 3) if hg else None,
            "cleanSheetHome":     round(d["home_clean_sheets"] / hg, 3) if hg else None,
            "failedToScoreHome":  round(d["home_failed_score"] / hg, 3) if hg else None,
            "home_games":         hg,
            "xG_away":            xg_a,
            "xGA_away":           xga_a,
            "awayWinRate":        round(d["away_wins"]         / ag, 3) if ag else None,
            "cleanSheetAway":     round(d["away_clean_sheets"] / ag, 3) if ag else None,
            "failedToScoreAway":  round(d["away_failed_score"] / ag, 3) if ag else None,
            "away_games":         ag,
            "currentStreak":      current_streak,   # +N = N-game win streak, -N = N-game loss streak
            # xG fairness not computable from goals alone — set neutral
            "xg_fairness":        1.0,
            "xg_fairness_home":   1.0,
            "xg_fairness_away":   1.0,
        }
    # Collect fixture info for corner stats batch fetch (sorted oldest→newest)
    fixture_info = sorted(
        [
            (fx.get("fixture", {}).get("timestamp", 0),
             fx.get("fixture", {}).get("id"),
             fx["teams"]["home"]["name"],
             fx["teams"]["away"]["name"])
            for fx in resp
            if fx.get("fixture", {}).get("id")
        ],
        key=lambda x: x[0]
    )

    return result, team_ids, fixture_info


def fetch_team_season_stats_extra(team_id: int, league_id: int, season: int = 2025) -> dict:
    """
    Fetch teams/statistics for a single team → extract:
      - lineups[0].formation  (most-used formation this season)
      - biggest.streak.wins/loses/draws
      - shots.home/away.total + shots.home/away.on → shots-based xG (replaces goals proxy)
        Formula: xG = SoT/game × 0.35 + (Shots - SoT)/game × 0.055
        This gives a much better attack-strength estimate than goals/game.
    Returns partial dict to merge into team entry, or {} on failure.
    """
    resp = apif_get("teams/statistics", {
        "team": team_id, "league": league_id, "season": season,
    })
    if not resp:
        return {}

    stat = resp if isinstance(resp, dict) else (resp[0] if isinstance(resp, list) and resp else None)
    if not stat:
        return {}

    # Most-used formation
    lineups = stat.get("lineups") or []
    formation = None
    if lineups:
        sorted_lineups = sorted(lineups, key=lambda x: x.get("played", 0), reverse=True)
        formation = sorted_lineups[0].get("formation")

    # Biggest streaks
    biggest = stat.get("biggest", {})
    streak  = biggest.get("streak", {})
    biggest_win_streak  = streak.get("wins")  or 0
    biggest_lose_streak = streak.get("loses") or 0
    biggest_draw_streak = streak.get("draws") or 0

    # Shots-based xG — much better attack proxy than goals/game
    # shots.home = team's own shots in HOME games (attack at home)
    # shots.away = team's own shots in AWAY games (attack away)
    shots   = stat.get("shots", {})
    fx_pl   = stat.get("fixtures", {}).get("played", {})
    h_games = fx_pl.get("home", 0) or 0
    a_games = fx_pl.get("away", 0) or 0

    def _xg_from_shots(total, on_goal, games):
        """Compute xG/game from season-aggregate shot counts."""
        if not games or not total:
            return None
        sot_pg  = (on_goal or 0) / games
        soff_pg = max(0, total - (on_goal or 0)) / games
        return round(sot_pg * 0.35 + soff_pg * 0.055, 3)

    sh = shots.get("home", {})
    sa = shots.get("away", {})
    xg_h_shots = _xg_from_shots(sh.get("total"), sh.get("on"), h_games)
    xg_a_shots = _xg_from_shots(sa.get("total"), sa.get("on"), a_games)

    out: dict = {}
    if formation:
        out["formation"] = formation
    if biggest_win_streak:
        out["biggestWinStreak"]  = biggest_win_streak
    if biggest_lose_streak:
        out["biggestLoseStreak"] = biggest_lose_streak
    if biggest_draw_streak:
        out["biggestDrawStreak"] = biggest_draw_streak
    # Shots-based xG — stored separately so caller can decide to upgrade xG fields
    if xg_h_shots is not None:
        out["xG_home_shots"] = xg_h_shots
    if xg_a_shots is not None:
        out["xG_away_shots"] = xg_a_shots
    return out


# ── Fixture-level stats for corner averages ────────────────────────────────────
STAT_TYPES = {
    "Shots on Goal": "sot",
    "Total Shots":   "shots",
    "Corner Kicks":  "corners",
}

def fetch_fixture_stats_batch(
    fixture_info: list[tuple],
    max_fixtures: int = 25,
) -> dict[str, dict]:
    """
    Fetch GET /fixtures/statistics for the last `max_fixtures` finished fixtures.
    Extracts per-fixture: corner kicks, shots on goal, total shots for home and away team.
    Also tracks corners conceded (opponent's corners) and shots off-target per venue.

    fixture_info: [(timestamp, fixture_id, home_name, away_name), ...] sorted oldest→newest
    Returns: {team_name: {"home_corners": [list], "away_corners": [list],
                          "home_corners_against": [list], "away_corners_against": [list],
                          "home_shots_off_target": [list], "away_shots_off_target": [list],
                          "home_sot": [list], "away_sot": [list],
                          "home_shots": [list], "away_shots": [list]}}
    """
    if not APIF_KEY:
        return {}

    recent = fixture_info[-max_fixtures:]
    result: dict[str, dict] = {}

    def _ensure_team(name):
        if name not in result:
            result[name] = {
                "home_corners": [],         "away_corners": [],
                "home_corners_against": [], "away_corners_against": [],
                "home_shots_off_target": [], "away_shots_off_target": [],
                "home_sot": [],             "away_sot": [],
                "home_shots": [],           "away_shots": [],
            }

    def _resolve_side(tname, h_name, a_name):
        """Return 'home', 'away', or None."""
        if tname == h_name: return "home"
        if tname == a_name: return "away"
        # Fuzzy: first 6 chars prefix match
        tl = tname.lower(); hl = h_name.lower(); al = a_name.lower()
        if tl[:6] == hl[:6] or hl[:6] == tl[:6]: return "home"
        if tl[:6] == al[:6] or al[:6] == tl[:6]: return "away"
        return None

    for ts, fid, h_name, a_name in recent:
        if not fid:
            continue
        stats_resp = apif_get("fixtures/statistics", {"fixture": fid})
        if not stats_resp:
            continue

        # Parse both sides in one pass, then cross-assign corners_against
        sides: dict[str, dict] = {}  # "home" or "away" → parsed stats
        for team_stat in stats_resp:
            tname = team_stat.get("team", {}).get("name", "")
            side = _resolve_side(tname, h_name, a_name)
            if not side:
                continue

            parsed: dict = {}
            for s in team_stat.get("statistics", []):
                key = STAT_TYPES.get(s.get("type", ""))
                if key:
                    try:
                        parsed[key] = int(s.get("value") or 0)
                    except (ValueError, TypeError):
                        parsed[key] = 0
            sides[side] = parsed

        # Assign FOR stats to each team, AGAINST stats to the opponent
        for side, parsed in sides.items():
            tgt      = h_name if side == "home" else a_name
            opp      = a_name if side == "home" else h_name
            opp_side = "away"  if side == "home" else "home"
            _ensure_team(tgt)
            _ensure_team(opp)

            if "corners" in parsed:
                result[tgt][f"{side}_corners"].append(parsed["corners"])
                # Opponent concedes these corners at their {opp_side} venue
                result[opp][f"{opp_side}_corners_against"].append(parsed["corners"])

            if "sot" in parsed:
                result[tgt][f"{side}_sot"].append(parsed["sot"])

            if "shots" in parsed:
                result[tgt][f"{side}_shots"].append(parsed["shots"])
                # Shots off-target = total shots − shots on goal (corner generation proxy)
                sot = parsed.get("sot", 0)
                off_target = max(0, parsed["shots"] - sot)
                result[tgt][f"{side}_shots_off_target"].append(off_target)

    return result


def process_league(league_key: str, fetch_fixture_stats: bool = True) -> dict:
    league_id = LEAGUE_APIF.get(league_key)
    if not league_id:
        return {}
    print(f"  📊  {league_key}  (API-Football ID {league_id})")
    try:
        stats, team_ids, fixture_info = fetch_league_stats(league_id)
        if not stats:
            print(f"       ⚠️  No data returned")
            return {}

        sample = list(stats.items())[:2]
        for name, s in sample:
            print(f"       {name:<30}  xG_h={s['xG_home'] or '-':>4}  "
                  f"xG_a={s['xG_away'] or '-':>4}  "
                  f"WR_h={s['homeWinRate'] or '-':>4}  "
                  f"WR_a={s['awayWinRate'] or '-':>4}  "
                  f"CS_h={s['cleanSheetHome'] or '-':>4}  "
                  f"FTS_a={s['failedToScoreAway'] or '-':>4}  "
                  f"streak={s['currentStreak']:+d}")
        print(f"       → {len(stats)} teams, {len(fixture_info)} fixtures")

        # ── Step A: teams/statistics → formation + biggestStreak + shots-based xG ──
        print(f"       Fetching teams/statistics (formation + biggestStreak + shots-xG)…")
        extra_ok = shots_ok = 0
        for tname, entry in stats.items():
            tid = team_ids.get(tname)
            if not tid:
                continue
            extra = fetch_team_season_stats_extra(tid, league_id)
            if not extra:
                continue
            entry.update({k: v for k, v in extra.items()
                          if k not in ("xG_home_shots", "xG_away_shots")})
            # Upgrade xG fields from shots (better attack proxy than goals/game)
            if extra.get("xG_home_shots"):
                entry["xG_home"] = extra["xG_home_shots"]
                entry["xgSource"] = "shots"
            if extra.get("xG_away_shots"):
                entry["xG_away"] = extra["xG_away_shots"]
                entry.setdefault("xgSource", "shots")
            if extra.get("xG_home_shots") or extra.get("xG_away_shots"):
                shots_ok += 1
            extra_ok += 1

        print(f"       → {extra_ok}/{len(stats)} teams: formation+streaks · "
              f"{shots_ok} upgraded to shots-based xG")

        # ── Step B: fixtures/statistics → corner averages ─────────────────────────
        if fetch_fixture_stats and fixture_info:
            n_fix = min(50, len(fixture_info))  # Business plan: doubled from 25 → 50
            print(f"       Fetching fixture stats for last {n_fix} fixtures (corners)…")
            corner_data = fetch_fixture_stats_batch(fixture_info, max_fixtures=n_fix)
            corners_ok = 0
            for tname, cdata in corner_data.items():
                if tname not in stats:
                    continue
                enriched = False

                if cdata["home_corners"]:
                    raw_avg = sum(cdata["home_corners"]) / len(cdata["home_corners"])
                    if raw_avg > 9.5:
                        print(f"       ⚠ {tname} cornersHome={raw_avg:.1f} capped at 9.5 (n={len(cdata['home_corners'])})")
                    stats[tname]["cornersHome"] = round(min(raw_avg, 9.5), 1)
                    enriched = True

                if cdata["away_corners"]:
                    raw_avg = sum(cdata["away_corners"]) / len(cdata["away_corners"])
                    if raw_avg > 8.5:
                        print(f"       ⚠ {tname} cornersAway={raw_avg:.1f} capped at 8.5 (n={len(cdata['away_corners'])})")
                    stats[tname]["cornersAway"] = round(min(raw_avg, 8.5), 1)

                # Corners conceded (opponent earns) at each venue
                if cdata["home_corners_against"]:
                    raw_avg = sum(cdata["home_corners_against"]) / len(cdata["home_corners_against"])
                    stats[tname]["cornersAgainstHome"] = round(min(raw_avg, 9.5), 1)

                if cdata["away_corners_against"]:
                    raw_avg = sum(cdata["away_corners_against"]) / len(cdata["away_corners_against"])
                    stats[tname]["cornersAgainstAway"] = round(min(raw_avg, 8.5), 1)

                # Shots off-target per venue (proxy for corner generation rate)
                if cdata["home_shots_off_target"]:
                    stats[tname]["shotsOffTargetHome"] = round(
                        sum(cdata["home_shots_off_target"]) / len(cdata["home_shots_off_target"]), 1)

                if cdata["away_shots_off_target"]:
                    stats[tname]["shotsOffTargetAway"] = round(
                        sum(cdata["away_shots_off_target"]) / len(cdata["away_shots_off_target"]), 1)

                if enriched:
                    corners_ok += 1

            print(f"       → {corners_ok} teams enriched with corner averages (for + against + shots-off-target)")
        else:
            print(f"       ⚙️  Fixture stats skipped (--fast mode)")

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
SUPPORTED_LEAGUES = {"ENG", "GER", "ITA", "ESP", "FRA", "AUT", "NED", "SCO", "TUR", "SUI", "POR",
                     "BEL", "POL", "HUN", "CRO"}


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
    fast_mode = "--fast" in sys.argv   # skip fixture-level stats (corners) for a quicker run

    print(f"🔄  Stats refresh — season {SEASON}/{SEASON + 1}  ({today})")
    if fast_mode:
        print("⚡  Fast mode: fixture stats (corners) skipped")
    print()

    # ── Step 1: API-Football — goals/game + win rates + shots-xG + corners ──
    print("━" * 58)
    print("  API-FOOTBALL — stats per league (shots-xG · corners · streaks)")
    print("━" * 58)
    all_stats: dict = {}
    for key in LEAGUE_APIF:
        all_stats[key] = process_league(key, fetch_fixture_stats=not fast_mode)

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
    # WIPE-SCHUTZ (12.07.2026, Wipe-Audit): process_league() gibt bei API-Fehler {} zurück →
    # bei abgelaufenem Key/Quota wäre stats_cache.json zu {"BL1": {}, "PL": {}, …} geworden.
    # Das ist eine STILLE Qualitäts-Degradierung (Picks fallen auf Tor-Proxy statt xG/Elo zurück).
    # write_json_guarded bricht LAUT ab (roter Workflow), wenn die Team-Zahl einbricht.
    from safe_write import write_json_guarded
    write_json_guarded(
        out, all_stats,
        count=lambda d: sum(len(v) for v in d.values() if isinstance(v, dict)),
        min_ratio=0.5, label="stats_cache.json",
    )

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

    shots_populated  = sum(1 for teams in all_stats.values()
                           for e in teams.values() if e.get("xgSource") == "shots")
    corners_populated = sum(1 for teams in all_stats.values()
                            for e in teams.values() if e.get("cornersHome") is not None)

    print(f"   Teams total     : {total_teams}")
    print(f"   Goals/game (xG) : {xg_populated} teams  (all leagues)")
    print(f"   Shots-based xG  : {shots_populated} teams  (upgraded from goals proxy)")
    print(f"   Corner averages : {corners_populated} teams  (home/away Ecken pro Spiel)")
    print(f"   Win rates       : {xg_populated} teams  (home/away)")
    print(f"   Elo data        : {elo_populated} teams  (all covered leagues)")
    print(f"   File            : {out}")
    print()
    print("ℹ️  Reload season-finish.html to apply new stats.")
    print("   All leagues → Goals/game (xG proxy) + Win rates + Elo")


if __name__ == "__main__":
    main()
