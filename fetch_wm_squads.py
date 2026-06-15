#!/usr/bin/env python3
"""
fetch_wm_squads.py — WM 2026 Squad Spotlight fetcher.

Fetches the key attacking player for all 48 WM 2026 teams from API-Football
and writes them to wm2026-data.json under the "squads" key.

Each entry: { name, position, goals, assists, minutes }

Fixes vs v1:
  - Multi-page fetching (up to 6 pages) → catches Mbappé, Kane, Ronaldo etc.
  - Relaxed min-minutes to 60 for national teams (fewer games than clubs)
  - Include all field players (no defender hard-skip) — pure goal-contribution rank
  - Position bonus for ATTACKER, smaller bonus for MIDFIELDER
  - Name overrides expanded: Türkiye, Bosnia, DR Congo, United States
  - Force-refresh flag: pass --force to re-fetch already populated entries
  - Better logging: show top-3 candidates per team for transparency

Run:   python3 fetch_wm_squads.py [--force]
Cron:  Weekly via fetch-wm-data.yml
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
APIF_DELAY  = 1.2   # seconds between calls (Pro plan: 10 req/min)
MAX_PAGES   = 6     # fetch up to 6 pages per team (120 players)
FORCE       = "--force" in sys.argv

# ── Name overrides: our 3-letter ID → what API-Football calls the team ─────────
# API-Football uses FIFA official names — we need exact (fuzzy) matches.
APIF_NAME_OVERRIDE: dict[str, str] = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "BIH": "Bosnia",          # API-Football: "Bosnia" not "Bosnia and Herzegovina"
    "BRA": "Brazil",
    "CAN": "Canada",
    "CIV": "Ivory Coast",
    "COD": "Congo DR",         # API-Football: "Congo DR"
    "COL": "Colombia",
    "CPV": "Cape Verde",
    "CRO": "Croatia",
    "CUW": "Curacao",          # Without accent in API
    "CZE": "Czech Republic",
    "DZA": "Algeria",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ENG": "England",
    "ESP": "Spain",
    "FRA": "France",
    "GER": "Germany",
    "GHA": "Ghana",
    "HTI": "Haiti",
    "IRN": "Iran",
    "IRQ": "Iraq",
    "JOR": "Jordan",
    "JPN": "Japan",
    "KOR": "South Korea",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "NED": "Netherlands",
    "NOR": "Norway",
    "NZL": "New Zealand",
    "PAN": "Panama",
    "POR": "Portugal",
    "PRY": "Paraguay",
    "QAT": "Qatar",
    "SAU": "Saudi Arabia",
    "SCO": "Scotland",
    "SEN": "Senegal",
    "SUI": "Switzerland",
    "SWE": "Sweden",
    "TUN": "Tunisia",
    "TUR": "Türkiye",          # FIFA switched to Türkiye
    "URU": "Uruguay",
    "USA": "United States",
    "UZB": "Uzbekistan",
    "ZAF": "South Africa",
}


def apif_get(endpoint: str, params: dict) -> tuple[list, int]:
    """
    Single API-Football request.
    Returns (response_list, total_pages).
    """
    if not APIF_KEY:
        return [], 0
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path  = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", f"/{endpoint}?{query}", headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        data = json.loads(raw)
        if data.get("errors"):
            errs = data["errors"]
            if errs and errs != [] and errs != {}:
                print(f"  ⚠️  API error on /{endpoint}: {errs}")
                return [], 0
        paging = data.get("paging", {})
        total_pages = paging.get("total", 1)
        return data.get("response", []), total_pages
    except Exception as e:
        print(f"  ❌  Request failed /{endpoint}: {e}")
        return [], 0

def normalize(s):
    return s.lower().strip().replace("é","e").replace("ü","u").replace("ô","o").replace("ö","o")

def _normalize(name: str) -> str:
    """Lowercase + strip accents for fuzzy comparison."""
    return (name.lower().strip()
            .replace("é", "e").replace("ê", "e").replace("è", "e")
            .replace("ô", "o").replace("ö", "o").replace("ó", "o")
            .replace("ü", "u").replace("ú", "u")
            .replace("á", "a").replace("â", "a").replace("ä", "a")
            .replace("ç", "c").replace("ñ", "n").replace("ı", "i"))


def _match_team(our_id: str, apif_teams: list) -> dict | None:
    """Fuzzy-match our team ID to an API-Football team entry."""
    target = _normalize(APIF_NAME_OVERRIDE.get(our_id, our_id))
    for t in apif_teams:
        apif_name = _normalize(t.get("team", {}).get("name", ""))
        if apif_name == target or target in apif_name or apif_name in target:
            return t
    return None


def _score_player(stats: dict, pos: str) -> float:
    """
    Compute attacking contribution score.
    All field positions are eligible — GK excluded in caller.
    Formula: goals×6 + assists×3 + shots×0.2 + position_bonus
    No minimum minutes requirement (handled separately).
    """
    goals   = stats.get("goals", {}).get("total")   or 0
    assists = stats.get("goals", {}).get("assists")  or 0
    shots   = stats.get("shots", {}).get("total")    or 0

    score = goals * 6 + assists * 3 + shots * 0.2
    if pos == "ATTACKER":
        score += 8    # Strong preference for actual forwards
    elif pos == "MIDFIELDER":
        score += 2    # Slight preference over defenders
    return score


def _best_attacker(players: list) -> dict | None:
    """
    Find the best attacking player from a full squad list.
    Returns the top scorer/assister, excluding goalkeepers.
    Falls back to most-minutes non-GK if nobody has goals.
    """
    candidates = []
    fallback_minutes = None
    fallback_player  = None

    for p_obj in players:
        player = p_obj.get("player", {})
        stats  = (p_obj.get("statistics") or [{}])[0]
        pos    = (stats.get("games", {}).get("position") or "").upper()

        if pos == "GOALKEEPER":
            continue

        goals   = stats.get("goals", {}).get("total")   or 0
        assists = stats.get("goals", {}).get("assists")  or 0
        shots   = stats.get("shots", {}).get("total")    or 0
        minutes = stats.get("games", {}).get("minutes")  or 0

        score = _score_player(stats, pos)

        shots_on    = stats.get("shots", {}).get("on")              or 0
        key_passes  = stats.get("passes", {}).get("key")            or 0
        yellow      = stats.get("cards", {}).get("yellow")          or 0
        red         = stats.get("cards", {}).get("red")             or 0
        fouls       = stats.get("fouls", {}).get("committed")       or 0
        rating      = float(stats.get("games", {}).get("rating")    or 0)
        dribbles    = stats.get("dribbles", {}).get("success")      or 0
        appearances = stats.get("games", {}).get("appearences")     or 1

        # Require at least one contribution (goal or assist) OR 60+ minutes
        if goals == 0 and assists == 0 and minutes < 60:
            continue

        candidates.append({
            "name":        player.get("name", "—"),
            "position":    pos,
            "goals":       goals,
            "assists":     assists,
            "shots":       shots,
            "shotsOn":     shots_on,
            "keyPasses":   key_passes,
            "yellowCards": yellow,
            "redCards":    red,
            "fouls":       fouls,
            "rating":      rating,
            "dribbles":    dribbles,
            "appearances": appearances,
            "minutes":     minutes,
            "score":       score,
        })

        # Track fallback: most minutes regardless of contribution
        if fallback_minutes is None or minutes > fallback_minutes:
            fallback_minutes = minutes
            fallback_player  = {
                "name":        player.get("name", "—"),
                "position":    pos,
                "goals":       goals,
                "assists":     assists,
                "shots":       shots,
                "shotsOn":     shots_on,
                "keyPasses":   key_passes,
                "yellowCards": yellow,
                "redCards":    red,
                "fouls":       fouls,
                "rating":      rating,
                "dribbles":    dribbles,
                "appearances": appearances,
                "minutes":     minutes,
            }

    if not candidates:
        return fallback_player   # Last resort: most-minutes non-GK

    # Sort by score desc
    candidates.sort(key=lambda c: -c["score"])

    # Log top-3 for transparency
    for i, c in enumerate(candidates[:3]):
        marker = "⭐" if i == 0 else "  "
        print(f"      {marker} #{i+1}: {c['name']} ({c['position']}) "
              f"{c['goals']}G {c['assists']}A {c['minutes']}min [score {c['score']:.1f}]")

    best = candidates[0]
    pos_label = {"ATTACKER": "ST", "MIDFIELDER": "CAM",
                 "DEFENDER": "DEF", "FORWARD": "ST"}.get(best["position"], best["position"])

    def _fmt(c: dict) -> dict:
        """Return a clean extended player dict (no internal score field)."""
        lbl = {"ATTACKER": "ST", "MIDFIELDER": "CAM",
               "DEFENDER": "DEF", "FORWARD": "ST"}.get(c["position"], c["position"])
        return {
            "name":        c["name"],
            "position":    lbl,
            "goals":       c["goals"],
            "assists":     c["assists"],
            "shots":       c["shots"],
            "shotsOn":     c["shotsOn"],
            "keyPasses":   c["keyPasses"],
            "yellowCards": c["yellowCards"],
            "redCards":    c["redCards"],
            "fouls":       c["fouls"],
            "rating":      c["rating"],
            "dribbles":    c["dribbles"],
            "appearances": c["appearances"],
            "minutes":     c["minutes"],
        }

    top3 = [_fmt(c) for c in candidates[:3]]
    result = _fmt(best)
    result["top3"] = top3
    return result


def _role_from_apif_pos(pos: str) -> str:
    """API-Football Position → grobe Rolle {GK, DEF, MID, ATT}."""
    p = (pos or "").upper()
    if p == "GOALKEEPER":              return "GK"
    if p == "DEFENDER":                return "DEF"
    if p == "MIDFIELDER":              return "MID"
    if p in ("ATTACKER", "FORWARD"):   return "ATT"
    return "MID"


def _build_key_players(players: list, top_outfield: int = 6) -> list:
    """Schlüsselspieler je Team über ALLE Positionen (15.06.2026, volle Ausfall-
    Wertung statt nur Top-Scorer). Top-N Feldspieler nach Beitrag + der wichtigste
    Keeper. Pro Spieler: id (robustes Lineup-Matching), Rolle, importance 0–1.
    importance = Mix aus Einsatzminuten (Verfügbarkeit) + Rating."""
    outfield, keepers = [], []
    for p_obj in players:
        player = p_obj.get("player", {})
        stats  = (p_obj.get("statistics") or [{}])[0]
        pos    = (stats.get("games", {}).get("position") or "").upper()
        role   = _role_from_apif_pos(pos)
        minutes = stats.get("games", {}).get("minutes") or 0
        rating  = float(stats.get("games", {}).get("rating") or 0)
        goals   = stats.get("goals", {}).get("total")   or 0
        assists = stats.get("goals", {}).get("assists")  or 0
        if minutes < 200:           # Rand-Spieler raus
            continue
        importance = round(min(1.0, 0.55 * (minutes / 2700.0) + 0.45 * (rating / 8.0)), 3)
        entry = {
            "id":         player.get("id"),
            "name":       player.get("name", "—"),
            "role":       role,
            "goals":      goals,
            "assists":    assists,
            "minutes":    minutes,
            "rating":     rating,
            "importance": importance,
        }
        if role == "GK":
            keepers.append(entry)
        else:
            entry["_score"] = _score_player(stats, pos) + rating * 2 + minutes / 600.0
            outfield.append(entry)

    outfield.sort(key=lambda c: -c["_score"])
    for c in outfield:
        c.pop("_score", None)
    keepers.sort(key=lambda c: -(c["minutes"] + c["rating"] * 100))
    return outfield[:top_outfield] + keepers[:1]


def fetch_all_players(apif_team_id: int) -> list:
    """
    Fetch all pages of players for a team (up to MAX_PAGES).
    Season order: 2026 → 2025 → 2024
    """
    for season in (2026, 2025, 2024):
        all_players = []
        for page in range(1, MAX_PAGES + 1):
            time.sleep(APIF_DELAY)
            players, total_pages = apif_get("players", {
                "team": apif_team_id, "season": season, "page": page,
            })
            all_players.extend(players)
            if not players or page >= total_pages:
                break

        if all_players:
            print(f"      → {len(all_players)} players (season {season}, "
                  f"{min(page, total_pages)}/{total_pages} pages)")
            return all_players
        else:
            print(f"      → season {season}: no data")

    return []


def main():
    print("⚽  fetch_wm_squads.py v2 — WM 2026 Squad Spotlight")
    print(f"    Key:   {'✅ set' if APIF_KEY else '❌ missing'}")
    print(f"    Force: {'✅ yes (re-fetch all)' if FORCE else '❌ no (skip existing)'}")

    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY not set — cannot fetch")
        sys.exit(1)

    if not WM_FILE.exists():
        print("  ❌  wm2026-data.json not found")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    squads_out: dict[str, dict] = {} if FORCE else (wm.get("squads") or {})
    all_team_ids = sorted(
        t["id"]
        for g in wm.get("groups", {}).values()
        for t in g.get("teams", [])
    )
    print(f"    Teams: {len(all_team_ids)}\n")

    # ── Step 1: Resolve API-Football team IDs ─────────────────
    print("  📡  Fetching WM 2026 team list from API-Football…")
    time.sleep(APIF_DELAY)
    apif_teams, _ = apif_get("teams", {"league": 1, "season": 2026})
    print(f"  → {len(apif_teams)} teams returned\n")

    if not apif_teams:
        print("  ❌  No team data — API-Football may not have WM 2026 yet")
        sys.exit(0)

    # ── Step 2: Per-team player fetch ─────────────────────────
    found   = 0
    skipped = 0
    failed  = []

    for our_id in all_team_ids:
        if not FORCE and squads_out.get(our_id, {}).get("name"):
            print(f"  ⏭  {our_id} already set: {squads_out[our_id]['name']} — skip")
            skipped += 1
            continue

        apif_entry = _match_team(our_id, apif_teams)
        if not apif_entry:
            print(f"  ⚠️  {our_id} — no API-Football match "
                  f"(tried: '{APIF_NAME_OVERRIDE.get(our_id, our_id)}')")
            failed.append(our_id)
            continue

        apif_id   = apif_entry["team"]["id"]
        apif_name = apif_entry["team"]["name"]
        print(f"  🔍  {our_id} → {apif_name} (ID {apif_id})")

        players = fetch_all_players(apif_id)
        if not players:
            print(f"      ⚠️  No player data found")
            failed.append(our_id)
            continue

        best = _best_attacker(players)
        if best:
            best["key_players"] = _build_key_players(players)
            squads_out[our_id] = best
            print(f"      ✅ Picked: {best['name']} ({best['position']}) "
                  f"— {best['goals']}G {best['assists']}A {best['minutes']}min")
            found += 1
        else:
            print(f"      ⚠️  No suitable player found")
            failed.append(our_id)

    # ── Step 3: Write back ────────────────────────────────────
    wm["squads"] = squads_out
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*50}")
    print(f"✅  {found} fetched  ⏭ {skipped} skipped  ⚠️  {len(failed)} failed")
    if failed:
        print(f"   Failed: {', '.join(failed)}")
    print(f"   Total in squads: {len(squads_out)}/48")
    print(f"   Saved: {WM_FILE}")


if __name__ == "__main__":
    main()
