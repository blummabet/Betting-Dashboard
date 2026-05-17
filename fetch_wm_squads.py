#!/usr/bin/env python3
"""
fetch_wm_squads.py — WM 2026 Squad Spotlight fetcher.

Fetches key attacking players for all 48 WM 2026 teams from API-Football
and writes them to wm2026-data.json under the "squads" key.

Each entry: { name, position, goals, assists, caps }
Position: "ST", "CAM", "LW", "RW", "MF" etc.

The "squad spotlight" shows in WM cards — one key attacker per team.

API-Football:
  - League 1 = FIFA World Cup
  - Season 2026
  - Endpoint: GET /teams?league=1&season=2026  → get all team IDs
  - Endpoint: GET /players?team={id}&season=2024&page=1  → get player stats

Run:   python3 fetch_wm_squads.py
Cron:  Once before WM starts, then weekly during tournament
"""

import json
import os
import sys
import time
import http.client
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
APIF_HOST   = "v3.football.api-sports.io"
APIF_KEY    = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")
APIF_DELAY  = 1.5   # seconds between API calls (rate limit: 10/min on free plan)

# ── Our 3-letter IDs → API-Football team names (fuzzy matching fallbacks) ──────
# Primary match: normalize name → check if API name contains/equals ours.
# Secondary:     manual override for edge cases.
APIF_NAME_OVERRIDE = {
    # Our ID  : exact API-Football team name (as returned by /teams endpoint)
    "USA":  "United States",
    "KOR":  "South Korea",
    "ZAF":  "South Africa",
    "CZE":  "Czech Republic",
    "BIH":  "Bosnia and Herzegovina",
    "QAT":  "Qatar",
    "HTI":  "Haiti",
    "SCO":  "Scotland",
    "PRY":  "Paraguay",
    "AUS":  "Australia",
    "TUR":  "Turkey",
    "BRA":  "Brazil",
    "MAR":  "Morocco",
    "COD":  "DR Congo",
    "CPV":  "Cape Verde",
    "SAU":  "Saudi Arabia",
    "URU":  "Uruguay",
    "SEN":  "Senegal",
    "IRQ":  "Iraq",
    "NOR":  "Norway",
    "DZA":  "Algeria",
    "AUT":  "Austria",
    "JOR":  "Jordan",
    "POR":  "Portugal",
    "UZB":  "Uzbekistan",
    "COL":  "Colombia",
    "ENG":  "England",
    "CRO":  "Croatia",
    "GHA":  "Ghana",
    "PAN":  "Panama",
    "GER":  "Germany",
    "CUW":  "Curaçao",
    "CIV":  "Ivory Coast",
    "ECU":  "Ecuador",
    "NED":  "Netherlands",
    "JPN":  "Japan",
    "SWE":  "Sweden",
    "TUN":  "Tunisia",
    "BEL":  "Belgium",
    "EGY":  "Egypt",
    "IRN":  "Iran",
    "NZL":  "New Zealand",
    "ESP":  "Spain",
    "FRA":  "France",
    "ARG":  "Argentina",
    "MEX":  "Mexico",
    "CAN":  "Canada",
    "SUI":  "Switzerland",
}

# ── API-Football position mapping → our simplified position labels ─────────────
def _simplify_pos(pos_raw: str) -> str:
    p = (pos_raw or "").upper()
    if p in ("ATTACKER",): return "ST"
    if p in ("MIDFIELDER",): return "CAM"
    if p in ("DEFENDER",): return "DEF"
    if p in ("GOALKEEPER",): return "GK"
    return pos_raw or "—"


def apif_get(endpoint: str, params: dict) -> list:
    """Single API-Football request. Returns response[] or []."""
    if not APIF_KEY:
        print("  ⚠️  APISPORTS_KEY not set — skipping API calls")
        return []
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path  = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        data = json.loads(raw)
        if data.get("errors"):
            errs = data["errors"]
            if errs:
                print(f"  ⚠️  API error on /{endpoint}: {errs}")
                return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ❌  Request failed /{endpoint}: {e}")
        return []


def _normalize(name: str) -> str:
    """Lowercase, remove accents-ish, strip whitespace for fuzzy matching."""
    return name.lower().strip().replace("é", "e").replace("ô", "o").replace("ü", "u")


def _match_team(our_id: str, apif_teams: list) -> dict | None:
    """Find the API-Football team entry for a given 3-letter ID."""
    target_name = _normalize(APIF_NAME_OVERRIDE.get(our_id, our_id))
    for t in apif_teams:
        apif_name = _normalize(t.get("team", {}).get("name", ""))
        if apif_name == target_name or target_name in apif_name or apif_name in target_name:
            return t
    return None


def _best_attacker(players: list) -> dict | None:
    """
    From a list of player-stat objects, find the best attacking player:
    Priority: goals*4 + assists*2 + shots. Prefer ATT/MID positions.
    """
    best     = None
    best_sc  = -1
    for p_obj in players:
        player = p_obj.get("player", {})
        stats  = (p_obj.get("statistics") or [{}])[0]
        pos    = (stats.get("games", {}).get("position") or "").upper()

        # Skip keepers and defenders
        if pos in ("GOALKEEPER", "DEFENDER"):
            continue

        goals   = stats.get("goals", {}).get("total") or 0
        assists = stats.get("goals", {}).get("assists") or 0
        shots   = stats.get("shots", {}).get("total") or 0
        minutes = stats.get("games", {}).get("minutes") or 0

        # Require at least 200 minutes played to count
        if minutes < 200:
            continue

        score = goals * 4 + assists * 2 + shots * 0.1
        # Bonus for attackers
        if pos == "ATTACKER":
            score += 5

        if score > best_sc:
            best_sc = score
            best = {
                "name":     player.get("name", "—"),
                "position": _simplify_pos(pos),
                "goals":    goals,
                "assists":  assists,
                "minutes":  minutes,
            }

    return best


def main():
    print("⚽  fetch_wm_squads.py — WM 2026 Squad Spotlight")
    print(f"    Key: {'✅ set' if APIF_KEY else '❌ missing'}")

    # ── Load wm2026-data.json ─────────────────────────────────
    if not WM_FILE.exists():
        print("  ❌  wm2026-data.json not found")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    squads_out: dict[str, dict] = wm.get("squads") or {}
    all_team_ids = set()
    for g in wm.get("groups", {}).values():
        for t in g.get("teams", []):
            all_team_ids.add(t["id"])

    print(f"    Teams to process: {len(all_team_ids)}")

    # ── Step 1: Get all WM 2026 teams from API-Football ───────
    print("\n  📡  Fetching WM 2026 teams from API-Football (league=1, season=2026)…")
    time.sleep(APIF_DELAY)
    apif_teams = apif_get("teams", {"league": 1, "season": 2026})
    print(f"  → {len(apif_teams)} teams returned by API")

    if not apif_teams:
        print("  ⚠️  No teams returned — will try to use existing squad data")
        print("      (WM 2026 fixtures may not be in API-Football yet before tournament)")

    # ── Step 2: For each of our 48 teams, fetch players ───────
    found = 0
    skipped = 0
    for our_id in sorted(all_team_ids):
        # Already have fresh data → skip (unless --force)
        existing = squads_out.get(our_id)
        if existing and existing.get("name"):
            print(f"  ⏭  {our_id} already has squad data: {existing['name']} ({existing.get('position','?')})")
            skipped += 1
            continue

        # Find API-Football team entry
        apif_entry = _match_team(our_id, apif_teams) if apif_teams else None
        if not apif_entry:
            if apif_teams:
                print(f"  ⚠️  {our_id} — no match in API-Football team list")
            continue

        apif_team_id = apif_entry.get("team", {}).get("id")
        apif_team_name = apif_entry.get("team", {}).get("name", "")
        print(f"  🔍  {our_id} → {apif_team_name} (ID {apif_team_id})")

        # Fetch players — try 2026 first, fall back to 2025, then 2024
        players = []
        for season in (2026, 2025, 2024):
            time.sleep(APIF_DELAY)
            players = apif_get("players", {
                "team":   apif_team_id,
                "season": season,
                "page":   1,
            })
            if players:
                print(f"      → {len(players)} players (season {season})")
                break
            print(f"      → season {season}: no data")

        if not players:
            print(f"      ⚠️  No player data found for {our_id}")
            continue

        # Pick best attacker
        attacker = _best_attacker(players)
        if attacker:
            squads_out[our_id] = attacker
            print(f"      ⭐ {attacker['name']} ({attacker['position']}) — "
                  f"{attacker['goals']}G {attacker['assists']}A {attacker['minutes']}min")
            found += 1
        else:
            print(f"      ⚠️  No attacker with ≥200 min found for {our_id}")

    # ── Step 3: Write back ────────────────────────────────────
    wm["squads"] = squads_out
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n✅  Done — {found} new entries, {skipped} skipped (total: {len(squads_out)})")
    print(f"   Saved: {WM_FILE}")


if __name__ == "__main__":
    main()
