#!/usr/bin/env python3
"""
fetch_results.py — Fetches finished fixtures from API-Football Pro for all
                   tracked leagues (last 14 days) and writes results-cache.json.
                   Also fetches corner kick + card statistics per finished fixture
                   so the browser dashboard can resolve corners/cards picks without
                   any CORS-blocked browser-side API calls.

Run 3× daily via GitHub Actions (04:00, 18:00, 23:00 Vienna / 02:00, 16:00, 21:00 UTC).
The dashboard reads results-cache.json at page load and uses it to resolve picks
without making any browser-side API calls.
"""

import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BASE      = Path(__file__).parent
OUT_FILE  = BASE / "results-cache.json"
API_KEY   = os.environ.get("APISPORTS_KEY", "")
BASE_URL  = "https://v3.football.api-sports.io"
HEADERS   = {"x-apisports-key": API_KEY}

# Same leagues as prematch enrichment + common second divisions
LEAGUES = {
    "ENG": 39,   # Premier League
    "GER": 78,   # Bundesliga
    "ITA": 135,  # Serie A
    "ESP": 140,  # La Liga
    "FRA": 61,   # Ligue 1
    "AUT": 218,  # Österreichische Bundesliga  (144 wäre belgische Jupiler Pro League!)
    "NED": 88,   # Eredivisie
    "POR": 94,   # Primeira Liga
    "SCO": 179,  # Scottish Premiership
    "TUR": 203,  # Süper Lig
    "GER2": 79,  # 2. Bundesliga
    "ENG2": 40,  # Championship
    "ITA2": 136, # Serie B
    "ESP2": 141, # Segunda División
    "FRA2": 62,  # Ligue 2
    "NED2": 89,  # Eerste Divisie
    "POR2": 95,  # Liga Portugal 2
    "SCO2": 180, # Scottish Championship
    "TUR2": 204, # TFF 1. Lig
    "HUN": 271,  # NB I (Hungary)
    "BEL": 55,   # Pro League (Belgium)
    "CRO": 210,  # HNL (Croatia)
    "POL": 106,  # Ekstraklasa (Poland)
}

FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}

# ── API fetch ─────────────────────────────────────────────────────────────────

def api_get(path: str, params: dict) -> dict | None:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url   = f"{BASE_URL}/{path}?{query}"
    req   = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  ⚠ HTTP {e.code} — {url}")
        return None
    except Exception as e:
        print(f"  ⚠ {e} — {url}")
        return None


def fetch_stats(fixture_id: int) -> dict | None:
    """Fetch corner kicks and card statistics for a single finished fixture."""
    time.sleep(1.2)
    data = api_get("fixtures/statistics", {"fixture": fixture_id})
    if not data:
        return None
    response = data.get("response", [])
    if not isinstance(response, list) or len(response) < 2:
        return None

    def extract(team_stats: dict, stat_name: str) -> int | None:
        for s in team_stats.get("statistics", []):
            if s.get("type", "").lower() == stat_name.lower():
                v = s.get("value")
                try:
                    return int(v) if v is not None else None
                except (ValueError, TypeError):
                    return None
        return None

    home = response[0]
    away = response[1]

    corners_home  = extract(home, "Corner Kicks")
    corners_away  = extract(away, "Corner Kicks")
    yellow_home   = extract(home, "Yellow Cards")
    yellow_away   = extract(away, "Yellow Cards")
    red_home      = extract(home, "Red Cards")
    red_away      = extract(away, "Red Cards")

    # Only return if we got at least corners data
    if corners_home is None and corners_away is None:
        return None

    return {
        "cornersHome": corners_home,
        "cornersAway": corners_away,
        "yellowHome":  yellow_home,
        "yellowAway":  yellow_away,
        "redHome":     red_home,
        "redAway":     red_away,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        print("❌  APISPORTS_KEY nicht gesetzt — Abbruch")
        return

    now = datetime.now(timezone.utc)
    print(f"🔄  Starte fetch_results.py — {now.strftime('%Y-%m-%d %H:%M UTC')}")

    # Fetch past 14 days to cover older picks and timezone drift
    dates = [(now - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(0, 14)]
    print(f"   Daten: {', '.join(dates)}")

    all_fixtures = []
    total_calls  = 0

    for date in dates:
        for lkey, league_id in LEAGUES.items():
            time.sleep(1.2)  # ≤1 req/sec — safely within API-Football rate limit
            total_calls += 1

            # Try season=2025 first, fall back to season=2026 if empty
            fixtures_raw = []
            for season in [2025, 2026]:
                data = api_get("fixtures", {
                    "date":     date,
                    "league":   league_id,
                    "season":   season,
                    "timezone": "Europe/Vienna",
                })
                if not data:
                    continue
                if not isinstance(data, dict):
                    print(f"  ⚠ Unerwartete Antwort [{lkey} {date}]: {str(data)[:200]}")
                    break
                errors = data.get("errors", {})
                if isinstance(errors, dict) and errors.get("rateLimit"):
                    print(f"  ⚠ Rate limit [{lkey} {date}] — warte 10s…")
                    time.sleep(10)
                    break
                fixtures_raw = data.get("response", [])
                if fixtures_raw:
                    break  # found data — no need to try next season

            for fx in fixtures_raw:
                status = fx.get("fixture", {}).get("status", {}).get("short", "")
                if status not in FINISHED_STATUSES:
                    continue

                goals    = fx.get("goals", {})
                score    = fx.get("score", {})
                halftime = score.get("halftime", {})
                teams    = fx.get("teams", {})
                fix_id   = fx["fixture"]["id"]

                all_fixtures.append({
                    "id":          fix_id,
                    "date":        (fx["fixture"].get("date") or "")[:10],
                    "leagueKey":   lkey,
                    "leagueId":    league_id,
                    "home":        teams.get("home", {}).get("name", ""),
                    "away":        teams.get("away", {}).get("name", ""),
                    "status":      status,
                    "goalsHome":   goals.get("home"),
                    "goalsAway":   goals.get("away"),
                    "htHome":      halftime.get("home"),
                    "htAway":      halftime.get("away"),
                    "homeTeamId":  teams.get("home", {}).get("id"),
                    "awayTeamId":  teams.get("away", {}).get("id"),
                    # Stats will be filled in below (or null if unavailable)
                    "cornersHome": None,
                    "cornersAway": None,
                    "yellowHome":  None,
                    "yellowAway":  None,
                    "redHome":     None,
                    "redAway":     None,
                })

    # Deduplicate by fixture ID
    seen = set()
    unique = []
    for fx in all_fixtures:
        if fx["id"] not in seen:
            seen.add(fx["id"])
            unique.append(fx)

    print(f"\n📋  {len(unique)} unique finished fixtures — hole jetzt Statistiken…")

    # ── Fetch statistics for each finished fixture ────────────────────────────
    stats_ok   = 0
    stats_fail = 0
    for i, fx in enumerate(unique):
        fix_id = fx["id"]
        print(f"  📊 [{i+1}/{len(unique)}] Stats für Fixture {fix_id} ({fx['home']} vs {fx['away']})…", end=" ")
        stats = fetch_stats(fix_id)
        total_calls += 1
        if stats:
            fx.update(stats)
            stats_ok += 1
            print(f"✅  Ecken {stats.get('cornersHome')}-{stats.get('cornersAway')} | Gelb {stats.get('yellowHome')}-{stats.get('yellowAway')}")
        else:
            stats_fail += 1
            print("—")

    cache = {
        "generated":   now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dates":       dates,
        "leagueCount": len(LEAGUES),
        "fixtures":    unique,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅  {len(unique)} Fixtures · {stats_ok} mit Stats · {stats_fail} ohne Stats")
    print(f"   Gesamt API-Calls: {total_calls}")
    print(f"   Gespeichert: {OUT_FILE}")


if __name__ == "__main__":
    main()
