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

LEAGUE_MAP = {
    "ENG": "EPL",
    "GER": "Bundesliga",
    "ITA": "Serie_A",
    "ESP": "La_Liga",
    "FRA": "Ligue_1",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Understat name → our HTML team name (only the mismatches) ─────────────────
NAME_MAP = {
    # Premier League
    "Tottenham":                  "Tottenham Hotspur",
    "Wolverhampton Wanderers":    "Wolverhampton",
    "Brighton":                   "Brighton & Hove Albion",
    "West Ham":                   "West Ham United",
    "Leeds":                      "Leeds United",
    "Newcastle United":           "Newcastle United",
    "Leicester":                  "Leicester City",
    "Ipswich":                    "Ipswich Town",
    # Bundesliga
    "Bayern Munich":              "FC Bayern München",
    "Bayer Leverkusen":           "Bayer 04 Leverkusen",
    "RasenBallsport Leipzig":     "RB Leipzig",
    "Greuther Fuerth":            "SpVgg Greuther Fürth",
    "Borussia M.Gladbach":        "Borussia Mönchengladbach",
    "Koeln":                      "1. FC Köln",
    "Kaiserslautern":             "1. FC Kaiserslautern",
    # Serie A
    "Internazionale":             "Inter",
    # La Liga
    "Atletico Madrid":            "Atlético de Madrid",
    "Athletic Club":              "Athletic Bilbao",
    "Celta Vigo":                 "Celta de Vigo",
    "Alaves":                     "Deportivo Alavés",
    "Leganes":                    "CD Leganés",
    "Espanol":                    "RCD Espanyol",
    "Mallorca":                   "RCD Mallorca",
    "Getafe":                     "Getafe CF",
    "Valladolid":                 "Real Valladolid",
    "Osasuna":                    "CA Osasuna",
    "Las Palmas":                 "UD Las Palmas",
    # Ligue 1
    "Marseille":                  "Olympique de Marseille",
    "Lyon":                       "Olympique Lyonnais",
    "Saint-Etienne":              "AS Saint-Étienne",
    "Lens":                       "RC Lens",
    "Rennes":                     "Stade Rennais",
    "Nantes":                     "FC Nantes",
    "Strasbourg":                 "RC Strasbourg",
    "Reims":                      "Stade de Reims",
    "Brest":                      "Stade Brestois 29",
    "Auxerre":                    "AJ Auxerre",
    "Havre":                      "Le Havre AC",
    "Montpellier":                "Montpellier HSC",
    "Toulouse":                   "Toulouse FC",
    "Angers":                     "Angers SCO",
    "Metz":                       "FC Metz",
}

# ── ClubElo name → our HTML team name ─────────────────────────────────────────
# ClubElo uses short English names; this maps them to our Sofascore-based names.
ELO_NAME_MAP = {
    # Premier League
    "Man City":          "Manchester City",
    "Man United":        "Manchester United",
    "Tottenham":         "Tottenham Hotspur",
    "West Ham":          "West Ham United",
    "Brighton":          "Brighton & Hove Albion",
    "Wolves":            "Wolverhampton",
    "Newcastle":         "Newcastle United",
    "Leicester":         "Leicester City",
    "Ipswich":           "Ipswich Town",
    "Nott'm Forest":     "Nottingham Forest",
    # Bundesliga
    "Bayern Munich":     "FC Bayern München",
    "Leverkusen":        "Bayer 04 Leverkusen",
    "Leipzig":           "RB Leipzig",
    "Dortmund":          "Borussia Dortmund",
    "Frankfurt":         "Eintracht Frankfurt",
    "M'gladbach":        "Borussia Mönchengladbach",
    "Koeln":             "1. FC Köln",
    "Kaiserslautern":    "1. FC Kaiserslautern",
    "Greuther Fuerth":   "SpVgg Greuther Fürth",
    "Union Berlin":      "1. FC Union Berlin",
    "Wolfsburg":         "VfL Wolfsburg",
    "Freiburg":          "SC Freiburg",
    "Stuttgart":         "VfB Stuttgart",
    "Hoffenheim":        "TSG Hoffenheim",
    "Augsburg":          "FC Augsburg",
    "Mainz":             "1. FSV Mainz 05",
    "Bremen":            "SV Werder Bremen",
    "St. Pauli":         "FC St. Pauli",
    "Holstein Kiel":     "Holstein Kiel",
    "Heidenheim":        "Heidenheim",
    "Bochum":            "VfL Bochum",
    "Darmstadt":         "SV Darmstadt 98",
    # Serie A
    "Milan":             "AC Milan",
    "Inter":             "Inter",
    "Juventus":          "Juventus",
    "Napoli":            "Napoli",
    "Roma":              "AS Roma",
    "Lazio":             "Lazio",
    "Atalanta":          "Atalanta",
    "Fiorentina":        "Fiorentina",
    "Bologna":           "Bologna",
    "Torino":            "Torino",
    "Monza":             "Monza",
    "Udinese":           "Udinese",
    "Genoa":             "Genoa",
    "Empoli":            "Empoli",
    "Cagliari":          "Cagliari",
    "Lecce":             "Lecce",
    "Verona":            "Hellas Verona",
    "Sassuolo":          "Sassuolo",
    "Salernitana":       "Salernitana",
    "Frosinone":         "Frosinone",
    "Como":              "Como",
    "Venezia":           "Venezia",
    "Parma":             "Parma",
    # La Liga
    "Real Madrid":       "Real Madrid",
    "Barcelona":         "Barcelona",
    "Atletico Madrid":   "Atlético de Madrid",
    "Sevilla":           "Sevilla FC",
    "Valencia":          "Valencia CF",
    "Betis":             "Real Betis",
    "Sociedad":          "Real Sociedad",
    "Athletic Club":     "Athletic Bilbao",
    "Villarreal":        "Villarreal CF",
    "Osasuna":           "CA Osasuna",
    "Celta":             "Celta de Vigo",
    "Mallorca":          "RCD Mallorca",
    "Espanyol":          "RCD Espanyol",
    "Getafe":            "Getafe CF",
    "Girona":            "Girona FC",
    "Las Palmas":        "UD Las Palmas",
    "Alaves":            "Deportivo Alavés",
    "Valladolid":        "Real Valladolid",
    "Leganes":           "CD Leganés",
    # Ligue 1
    "PSG":               "Paris Saint-Germain",
    "Paris SG":          "Paris Saint-Germain",
    "Marseille":         "Olympique de Marseille",
    "Lyon":              "Olympique Lyonnais",
    "Monaco":            "AS Monaco",
    "Lille":             "Lille OSC",
    "Nice":              "OGC Nice",
    "Rennes":            "Stade Rennais",
    "Lens":              "RC Lens",
    "Strasbourg":        "RC Strasbourg",
    "Reims":             "Stade de Reims",
    "Nantes":            "FC Nantes",
    "Montpellier":       "Montpellier HSC",
    "Brest":             "Stade Brestois 29",
    "Toulouse":          "Toulouse FC",
    "Lorient":           "FC Lorient",
    "Angers":            "Angers SCO",
    "Metz":              "FC Metz",
    "Le Havre":          "Le Havre AC",
    "Auxerre":           "AJ Auxerre",
    "St Etienne":        "AS Saint-Étienne",
    "Clermont":          "Clermont Foot",
    # Austrian Bundesliga
    "Salzburg":          "FC Red Bull Salzburg",
    "Sturm Graz":        "Sturm Graz",
    "Austria Wien":      "FK Austria Wien",
    "Rapid Wien":        "SK Rapid Wien",
    "LASK":              "LASK",
    "Wolfsberg":         "Wolfsberger AC",
    "Klagenfurt":        "FC Kärnten",
    "Hartberg":          "TSV Hartberg",
    # Netherlands Eredivisie
    "Ajax":              "Ajax",
    "PSV":               "PSV Eindhoven",
    "Feyenoord":         "Feyenoord",
    "AZ":                "AZ Alkmaar",
    "Utrecht":           "FC Utrecht",
    "Twente":            "FC Twente",
    "Groningen":         "FC Groningen",
    "Heerenveen":        "SC Heerenveen",
    "Sparta Rotterdam":  "Sparta Rotterdam",
    "Go Ahead Eagles":   "Go Ahead Eagles",
    # Scottish Premiership
    "Celtic":            "Celtic",
    "Rangers":           "Rangers",
    "Aberdeen":          "Aberdeen",
    "Hearts":            "Heart of Midlothian",
    "Hibernian":         "Hibernian",
    "Kilmarnock":        "Kilmarnock",
    "Dundee":            "Dundee",
    "Ross County":       "Ross County",
    # Turkish Super Lig
    "Galatasaray":       "Galatasaray",
    "Fenerbahce":        "Fenerbahçe",
    "Besiktas":          "Beşiktaş",
    "Trabzonspor":       "Trabzonspor",
    "Basaksehir":        "İstanbul Başakşehir",
    "Sivasspor":         "Sivasspor",
    # Swiss Super League
    "Young Boys":        "Young Boys",
    "Basel":             "FC Basel",
    "Lugano":            "FC Lugano",
    "Zurich":            "FC Zürich",
    "Zuerich":           "FC Zürich",
    "Servette":          "Servette FC",
    "St. Gallen":        "FC St. Gallen",
    "Luzern":            "FC Luzern",
    "Lausanne":          "Lausanne-Sport",
    "GC Zurich":         "Grasshopper Club Zürich",
    # Portuguese Primeira Liga
    "Porto":             "FC Porto",
    "Benfica":           "SL Benfica",
    "Sporting CP":       "Sporting CP",
    "Braga":             "SC Braga",
    "Guimaraes":         "Vitória SC",
}


# ════════════════════════════════════════════════════════════════════════════════
#  UNDERSTAT
# ════════════════════════════════════════════════════════════════════════════════

def decode_understat(raw: str) -> dict:
    """Understat embeds JSON as a JS string with \\xNN hex-escaped characters."""
    try:
        decoded = raw.encode("raw_unicode_escape").decode("unicode_escape")
        return json.loads(decoded)
    except Exception:
        pass
    try:
        return json.loads(raw)
    except Exception as e:
        raise ValueError(f"Could not decode understat JSON: {e}") from e


def fetch_teams(league_name: str, season: int) -> dict:
    url = f"https://understat.com/league/{league_name}/{season}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    # Understat has changed their embedded-data format over time.
    # Try all known variants in order of likelihood.

    # Pattern 1: classic single-quote JSON.parse (2019–2024)
    m = re.search(r"var\s+teamsData\s*=\s*JSON\.parse\('(.*?)'\)\s*;", html, re.DOTALL)
    if m:
        return decode_understat(m.group(1))

    # Pattern 2: double-quote variant
    m = re.search(r'var\s+teamsData\s*=\s*JSON\.parse\("(.*?)"\)\s*;', html, re.DOTALL)
    if m:
        return decode_understat(m.group(1))

    # Pattern 3: no 'var', direct assignment with single quotes
    m = re.search(r"teamsData\s*=\s*JSON\.parse\('(.*?)'\)", html, re.DOTALL)
    if m:
        return decode_understat(m.group(1))

    # Pattern 4: no 'var', double quotes
    m = re.search(r'teamsData\s*=\s*JSON\.parse\("(.*?)"\)', html, re.DOTALL)
    if m:
        return decode_understat(m.group(1))

    # Pattern 5: direct object literal (not JSON.parse'd string)
    m = re.search(r"var\s+teamsData\s*=\s*(\{.+?\})\s*;", html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Pattern 6: Understat unofficial AJAX endpoint (fallback when HTML scraping fails)
    # POST to /main/getTeamsStats/ with league + season params
    try:
        api_url = "https://understat.com/main/getTeamsStats/"
        api_resp = requests.post(
            api_url,
            data={"league": league_name, "season": str(season)},
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest",
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        api_resp.raise_for_status()
        payload = api_resp.json()
        # Response is {"success": true, "data": {...teams...}}
        if payload.get("success") and payload.get("data"):
            return payload["data"]
    except Exception:
        pass

    # Debug: show what data vars ARE present on the page (helps diagnose format change)
    found_vars = re.findall(r"var\s+(\w+Data)\s*=", html)
    debug_hint = f" (vars on page: {found_vars})" if found_vars else " (no *Data vars found — possible bot-block or format change)"
    raise ValueError(f"teamsData not found on {url}{debug_hint}")


def safe_avg(games: list, key: str) -> Optional[float]:
    vals = [float(g[key]) for g in games if g.get(key) not in (None, "")]
    return round(sum(vals) / len(vals), 3) if vals else None


def win_rate(games: list) -> Optional[float]:
    if not games:
        return None
    wins = sum(1 for g in games if g.get("result") == "w")
    return round(wins / len(games), 3)


def process_league(league_key: str, league_name: str) -> dict:
    print(f"  📊  {league_key}  ({league_name})")
    try:
        teams_data = fetch_teams(league_name, SEASON)
    except Exception as exc:
        print(f"       ⚠️  Failed: {exc}")
        return {}

    stats = {}
    for raw_name, team in teams_data.items():
        our = NAME_MAP.get(raw_name, raw_name)
        hist = team.get("history", [])
        home_g = [g for g in hist if g.get("h_a") == "h"]
        away_g = [g for g in hist if g.get("h_a") == "a"]

        entry = {
            "xG_home":     safe_avg(home_g, "xG"),
            "xGA_home":    safe_avg(home_g, "xGA"),
            "homeWinRate": win_rate(home_g),
            "home_games":  len(home_g),
            "xG_away":     safe_avg(away_g, "xG"),
            "xGA_away":    safe_avg(away_g, "xGA"),
            "awayWinRate": win_rate(away_g),
            "away_games":  len(away_g),
        }
        stats[our] = entry

        print(f"       {our:<32}  "
              f"xG_h={str(entry['xG_home'] or '-'):>5}  "
              f"xG_a={str(entry['xG_away'] or '-'):>5}  "
              f"WR_h={str(entry['homeWinRate'] or '-'):>4}  "
              f"WR_a={str(entry['awayWinRate'] or '-'):>4}")

    print(f"       → {len(stats)} teams\n")
    return stats


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

    # ── Step 1: Understat xG ──────────────────────────────────────────────────
    print("━" * 58)
    print("  UNDERSTAT — real xG + venue win rates")
    print("━" * 58)
    all_stats: dict = {}
    for key, name in LEAGUE_MAP.items():
        all_stats[key] = process_league(key, name)

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
    print(f"   Teams total : {total_teams}")
    print(f"   xG data     : {xg_populated} teams  (Big-5 leagues)")
    print(f"   Elo data    : {elo_populated} teams  (all covered leagues)")
    print(f"   File        : {out}")
    print()
    print("ℹ️  Reload season-finish.html to apply new stats.")
    print("   ENG/GER/ITA/ESP/FRA → real Understat xG + Elo")
    print("   AUT/NED/SCO/TUR/SUI/POR → Elo only (no xG)")


if __name__ == "__main__":
    main()
