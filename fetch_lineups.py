#!/usr/bin/env python3
"""
fetch_lineups.py — Fetches confirmed starting lineups for today's fixtures.

Runs hourly (07:00–21:00 UTC) via GitHub Actions.  Lineups become available
~60–75 minutes before kickoff.  Writes lineup_cache.json which is read by
prematch-server.js and injected into prematch-data.json fixtures.

API: API-Football /fixtures/lineups?fixture={id}
     1 call per fixture · only same-day games with no confirmed lineup yet
     Typical daily cost: 30–60 calls (subset of today's fixtures)

Output: lineup_cache.json
  { "<fixtureId>": {
      "fetchedAt": "ISO timestamp",
      "confirmed": true/false,    # true when API returns at least 1 XI
      "home": {
        "formation": "4-3-3",
        "startXI": [
          {"name": "M. Neuer", "pos": "G", "number": 1, "grid": "1:1"},
          ...
        ],
        "subs": [{"name": "T. Müller", "pos": "F", "number": 25}, ...]
      },
      "away": { ... same structure ... }
    }
  }
"""

import json
import os
import sys
import time
import http.client
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE        = Path(__file__).parent
CACHE_FILE  = BASE / "lineup_cache.json"
PREMATCH    = BASE / "prematch-data.json"

APIF_HOST   = "v3.football.api-sports.io"
APIF_KEY    = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY  = 1.2   # seconds between calls

# Only fetch lineups for games kicking off within this window (hours from now)
WINDOW_START_H = -2    # include games that started up to 2h ago (lineup already confirmed)
WINDOW_END_H   = 12    # look ahead up to 12h (lineups released ~1h before KO)

# ── API helper ────────────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> dict | list | None:
    if not APIF_KEY:
        print("⚠  APISPORTS_KEY not set — skipping API calls")
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


# ── Load existing cache ───────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Parse API response for one fixture ───────────────────────────────────────

def parse_lineup(resp_item: dict) -> dict:
    """Convert one entry from /fixtures/lineups response to our format."""
    team     = resp_item.get("team", {})
    formation = resp_item.get("formation") or ""
    start_xi = resp_item.get("startXI") or []
    subs     = resp_item.get("substitutes") or []

    def parse_player(p):
        pl = p.get("player", {})
        return {
            "name":   pl.get("name") or "",
            "pos":    pl.get("pos") or "",
            "number": pl.get("number") or 0,
            "grid":   pl.get("grid") or "",
        }

    return {
        "teamId":    team.get("id"),
        "teamName":  team.get("name") or "",
        "formation": formation,
        "startXI":   [parse_player(p) for p in start_xi],
        "subs":      [parse_player(p) for p in subs],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not APIF_KEY:
        print("⚠  APISPORTS_KEY not set — nothing to do")
        return

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Load prematch fixtures to know which fixture IDs to check
    if not PREMATCH.exists():
        print("⚠  prematch-data.json not found — cannot determine fixture IDs")
        return

    with open(PREMATCH) as f:
        prematch = json.load(f)

    fixtures = prematch.get("fixtures", [])

    # Filter: only same-day fixtures within time window
    window_start = now + timedelta(hours=WINDOW_START_H)
    window_end   = now + timedelta(hours=WINDOW_END_H)

    candidates = []
    for fix in fixtures:
        if fix.get("isFinished"):
            continue
        date_str = fix.get("date", "")   # "YYYY-MM-DD" or "DD.MM.YYYY"
        time_str = fix.get("time", "")   # "HH:MM"

        # Parse date (handle both formats)
        try:
            if "-" in date_str and len(date_str) == 10:
                d = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            elif "." in date_str:
                d = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            else:
                continue
        except Exception:
            continue

        ko_utc = d.replace(tzinfo=timezone.utc)

        if window_start <= ko_utc <= window_end:
            fid = fix.get("fixtureId")
            if fid:
                candidates.append((fid, fix.get("homeTeamName", ""), fix.get("awayTeamName", "")))

    print(f"🔍  {len(candidates)} fixtures in lineup window ({WINDOW_START_H}h to +{WINDOW_END_H}h from now)")

    if not candidates:
        print("   No fixtures in window — nothing to fetch")
        return

    # Load existing cache
    cache = load_cache()

    # Skip fixtures already confirmed in cache (lineups don't change after confirmation)
    to_fetch = []
    for fid, home, away in candidates:
        existing = cache.get(str(fid), {})
        if existing.get("confirmed"):
            print(f"  ✓ {home} vs {away} — lineup already confirmed, skipping")
        else:
            to_fetch.append((fid, home, away))

    print(f"📡  Fetching lineups for {len(to_fetch)} fixtures...")

    fetched = 0
    for fid, home, away in to_fetch:
        resp = apif_get("fixtures/lineups", {"fixture": fid})
        if not resp:
            print(f"  ✗ {home} vs {away} (ID {fid}): no data")
            continue

        if len(resp) < 2:
            # Lineup not yet released (empty response or only 1 team)
            cache[str(fid)] = {
                "fetchedAt": now.isoformat(),
                "confirmed": False,
                "home":      None,
                "away":      None,
            }
            print(f"  ⏳ {home} vs {away} — lineup not yet released")
            continue

        # Parse home/away (API returns home first, away second)
        home_data = parse_lineup(resp[0])
        away_data = parse_lineup(resp[1])
        confirmed = len(home_data["startXI"]) >= 11 and len(away_data["startXI"]) >= 11

        cache[str(fid)] = {
            "fetchedAt": now.isoformat(),
            "confirmed": confirmed,
            "home": home_data,
            "away": away_data,
        }

        start_h = len(home_data["startXI"])
        start_a = len(away_data["startXI"])
        fmt_h   = home_data["formation"] or "?"
        fmt_a   = away_data["formation"] or "?"
        status  = "✅ confirmed" if confirmed else "⚠ partial"
        print(f"  {status}  {home} ({fmt_h}, {start_h} pl.) vs {away} ({fmt_a}, {start_a} pl.)")
        fetched += 1

    # Write updated cache
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n✅  lineup_cache.json updated: {fetched} new fetches, {len(cache)} total entries")


if __name__ == "__main__":
    main()
