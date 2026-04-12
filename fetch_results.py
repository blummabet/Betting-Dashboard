#!/usr/bin/env python3
"""
fetch_results.py — Fetches finished fixtures from API-Football Pro for all
                   tracked leagues (last 4 days) and writes results-cache.json.

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
    "AUT": 144,  # Österreichische Bundesliga
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        print("❌  APISPORTS_KEY nicht gesetzt — Abbruch")
        return

    now = datetime.now(timezone.utc)
    print(f"🔄  Starte fetch_results.py — {now.strftime('%Y-%m-%d %H:%M UTC')}")

    # Fetch past 4 days to cover timezone drift and delayed entries
    dates = [(now - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(0, 4)]
    print(f"   Daten: {', '.join(dates)}")

    all_fixtures = []
    total_calls  = 0

    for date in dates:
        for lkey, league_id in LEAGUES.items():
            time.sleep(0.15)  # ~400 req/min — safe for Pro plan rate limits
            total_calls += 1

            data = api_get("fixtures", {
                "date":     date,
                "league":   league_id,
                "season":   2025,
                "timezone": "Europe/Vienna",
            })
            if not data:
                continue

            # API sometimes returns a list on error instead of a dict
            if not isinstance(data, dict):
                print(f"  ⚠ Unerwartete Antwort [{lkey} {date}]: {str(data)[:200]}")
                continue

            errors = data.get("errors", {})
            if isinstance(errors, dict) and errors.get("rateLimit"):
                print(f"  ⚠ Rate limit [{lkey} {date}] — warte 5s…")
                time.sleep(5)
                continue

            for fx in data.get("response", []):
                status = fx.get("fixture", {}).get("status", {}).get("short", "")
                if status not in FINISHED_STATUSES:
                    continue

                goals   = fx.get("goals", {})
                score   = fx.get("score", {})
                halftime = score.get("halftime", {})
                teams   = fx.get("teams", {})

                all_fixtures.append({
                    "id":          fx["fixture"]["id"],
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
                })

    # Deduplicate by fixture ID
    seen = set()
    unique = []
    for fx in all_fixtures:
        if fx["id"] not in seen:
            seen.add(fx["id"])
            unique.append(fx)

    cache = {
        "generated":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dates":      dates,
        "leagueCount": len(LEAGUES),
        "fixtures":   unique,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅  {len(unique)} Fixtures aus {total_calls} API-Calls")
    print(f"   Gespeichert: {OUT_FILE}")


if __name__ == "__main__":
    main()
