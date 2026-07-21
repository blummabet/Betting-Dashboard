#!/usr/bin/env python3
"""
fetch_squads.py — Weekly squad stats fetcher for BetEdge Dashboard.

For every stake team (= team with a relegation / title / European label),
fetches full player statistics from API-Football, identifies the top-11
starters by minutes played, and computes an "importance score" per player
using position-specific metrics:

  GK  → minutes only (any GK absence is serious)
  DEF → tackles + interceptions + blocks + minor goal contribution
  MID → key passes + tackles + goals + assists
  FWD → goals × 4 + assists × 2 + shots (normalised)
  All → 50% minutes + 35% contribution + 15% Whoscored-style rating

Saves result to squad_cache.json.  update_dashboard.py reads this cache
daily, cross-references with the injury list fetched from SofaScore, and
computes a Squad Strength Score (0–10) for each stake fixture.

Run:    python3 fetch_squads.py
Cron:   Weekly — every Monday 03:00 Vienna / 01:00 UTC (GitHub Actions)
"""

import json
import re
import os
import sys
import time
import http.client
from datetime import datetime, timezone
from pathlib import Path

# ── Shared config — must stay in sync with update_dashboard.py ────────────────

BASE      = Path(__file__).parent
CACHE_FILE = BASE / "squad_cache.json"

APIF_HOST  = "v3.football.api-sports.io"
APIF_KEY   = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2   # seconds between calls (Pro plan rate limit)

LEAGUES = {
    "ENG": dict(apif_id=39,  total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "GER": dict(apif_id=78,  total=18, rounds=34, ucl=4, el=2, uecl=1, rel_playoff=1, rel=2),
    "ITA": dict(apif_id=135, total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "ESP": dict(apif_id=140, total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "FRA": dict(apif_id=61,  total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "AUT": dict(apif_id=218, total=12, rounds=32, ucl=2, el=1, uecl=0, rel_playoff=1, rel=2),
    "NED": dict(apif_id=88,  total=18, rounds=34, ucl=2, el=2, uecl=0, rel_playoff=2, rel=1),
    "POR": dict(apif_id=94,  total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "SCO": dict(apif_id=179, total=12, rounds=38, ucl=2, el=2, uecl=0, rel_playoff=1, rel=1),
    "TUR": dict(apif_id=203, total=19, rounds=38, ucl=2, el=2, uecl=1, rel_playoff=0, rel=3),
    "SUI": dict(apif_id=207, total=10, rounds=36, ucl=1, el=1, uecl=0, rel_playoff=1, rel=1),
    "BEL": dict(apif_id=144, total=16, rounds=40, ucl=2, el=1, uecl=1, rel_playoff=3, rel=1),
    "POL": dict(apif_id=106, total=18, rounds=34, ucl=1, el=1, uecl=1, rel_playoff=2, rel=2),
    "HUN": dict(apif_id=271, total=12, rounds=33, ucl=1, el=1, uecl=1, rel_playoff=0, rel=2),
    "CRO": dict(apif_id=210, total=10, rounds=36, ucl=1, el=1, uecl=1, rel_playoff=1, rel=1),
    # 21.07.2026 (Lucas): MLS aufgenommen, damit die Verletzten Positionen bekommen (der
    # /injuries-Endpoint liefert keine). Keine EU-Wettbewerbe → ucl/el/rel = 0; MLS läuft im
    # FULL_FETCH (alle Teams), daher werden die stake-Felder ohnehin nicht ausgewertet.
    "MLS": dict(apif_id=253, total=30, rounds=34, ucl=0, el=0, uecl=0, rel_playoff=0, rel=0),
}

# Big-5 leagues fetch ALL teams (not just stake teams) so that opponents of stake
# teams (e.g. Real Madrid playing vs a relegation side) also have squad data.
# Secondary leagues (NED, BEL, AUT, CRO) are now also full-fetch so that opponents
# of stake teams (e.g. Rotterdam away vs a title contender) are also covered.
FULL_FETCH_LEAGUES = {"ENG", "ESP", "GER", "ITA", "FRA", "NED", "BEL", "AUT", "CRO"}

# ── API helpers ───────────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> list:
    """Fetch response[] from API-Football (rate-limited)."""
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
            print(f"  ⚠ API error /{endpoint}: {errors}")
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ⚠ apif_get error /{endpoint}: {e}")
        return []
    finally:
        time.sleep(APIF_DELAY)


def apif_get_full(endpoint: str, params: dict) -> dict | None:
    """Fetch full API response (including paging) — needed for paginated endpoints."""
    if not APIF_KEY:
        return None
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
            print(f"  ⚠ API error /{endpoint}: {errors}")
            return None
        return data
    except Exception as e:
        print(f"  ⚠ apif_get_full error /{endpoint}: {e}")
        return None
    finally:
        time.sleep(APIF_DELAY)

# ── Standings + label helpers (mirrors update_dashboard.py) ──────────────────

def pts_at_pos(standings: list, pos: int) -> int:
    for t in standings:
        if t["pos"] == pos:
            return t["pts"]
    return 0


def has_stake_label(team: dict, standings: list, cfg: dict) -> bool:
    """Return True if this team has any stake label (gold/red/blue/orange)."""
    pos   = team["pos"]
    pts   = team["pts"]
    played = team["played"]
    total  = cfg["total"]

    leader_pts = pts_at_pos(standings, 1)
    gap_leader = leader_pts - pts

    # Title
    if pos == 1 or (pos <= 3 and gap_leader <= 6):
        return True

    ucl = cfg["ucl"]
    pts_ucl       = pts_at_pos(standings, ucl)
    pts_below_ucl = pts_at_pos(standings, ucl + 1)
    if pos <= ucl and (pts - pts_below_ucl) <= 3:
        return True
    if pos > ucl and (pts_ucl - pts) <= 4:
        return True

    el = cfg.get("el", 0)
    if el > 0:
        el_cutoff = ucl + el
        pts_el = pts_at_pos(standings, el_cutoff)
        if pos <= el_cutoff and abs(pts - pts_el) <= 3:
            return True
        if pos > el_cutoff and (pts_el - pts) <= 3:
            return True

    rel       = cfg["rel"]
    rel_ply   = cfg.get("rel_playoff", 0)
    rel_start = total - rel + 1
    ply_pos   = rel_start - rel_ply
    safe_pos  = ply_pos - 1
    pts_safe  = pts_at_pos(standings, safe_pos) if safe_pos > 0 else 999

    if pos >= ply_pos:
        return True
    if (pts_safe - pts) <= 6 and pos >= safe_pos - 2:
        return True

    return False

# ── Player stats fetch ────────────────────────────────────────────────────────

def fetch_team_players(team_id: int, season: int = 2025) -> list:
    """
    Fetch all players for a team with full pagination.
    Returns a flat list of raw API player objects.
    """
    all_players = []
    for s in [season, season + 1]:
        page = 1
        while True:
            data = apif_get_full("players", {"team": team_id, "season": s, "page": page})
            if not data:
                break
            players = data.get("response", [])
            if not players:
                break
            all_players.extend(players)
            paging = data.get("paging", {})
            total_pages = paging.get("total", 1)
            if page >= total_pages:
                break
            page += 1
        if all_players:
            break  # found data for this season — stop trying

    return all_players

# ── Importance scoring ────────────────────────────────────────────────────────

def player_importance(stats: dict, pos: str) -> float:
    """
    Returns importance score 0.0–1.0 for one player.
    Higher = harder to replace when missing.

    Formula: 50% minutes + 35% positional contribution + 15% Whoscored rating.
    """
    games   = stats.get("games",   {})
    goals   = stats.get("goals",   {})
    shots   = stats.get("shots",   {})
    passes  = stats.get("passes",  {})
    tackles = stats.get("tackles", {})

    minutes  = games.get("minutes")  or 0
    rating   = float(games.get("rating") or 0) or 6.5

    # ── Minutes component (0→1, capped at 2700 = ~full season as starter) ──
    min_score = min(minutes / 2700, 1.0)

    # ── Positional contribution (0→1) ─────────────────────────────────────
    if pos == "G":
        # Any GK absence is serious — contribution is purely minutes-based
        contrib = min_score

    elif pos == "D":
        tack = tackles.get("total")          or 0
        intr = tackles.get("interceptions")  or 0
        blk  = tackles.get("blocks")         or 0
        g    = goals.get("total")            or 0
        a    = goals.get("assists")          or 0
        # Defensive work + minor contribution bonus
        contrib = min((tack + intr + blk) / 80 + (g + a) * 0.1, 1.0)

    elif pos == "M":
        kp   = passes.get("key")   or 0
        tack = tackles.get("total") or 0
        g    = goals.get("total")  or 0
        a    = goals.get("assists") or 0
        contrib = min((kp * 2 + tack + g * 5 + a * 3) / 80, 1.0)

    else:  # Forward / Attacker
        g  = goals.get("total")  or 0
        a  = goals.get("assists") or 0
        sh = shots.get("total")  or 0
        contrib = min((g * 4 + a * 2 + sh * 0.3) / 30, 1.0)

    # ── Rating component (7.0+ = above average, capped at 10) ──────────
    rating_score = max(0.0, min(1.0, (rating - 6.5) / 3.0))

    return round(0.50 * min_score + 0.35 * contrib + 0.15 * rating_score, 3)


def _full_position_map(players_raw: list) -> dict:
    """21.07.2026 (Lucas): {nachname: G/D/M/F} über ALLE Spieler (auch Ersatz/wenig Minuten), nicht
    nur die Start-11. Für die Injury-Positions-Anreicherung — Verletzte sind oft KEINE Starter, sonst
    matchen die meisten nicht. Nachnamen-Key teilt sich die Normalisierung mit injury_positions (eine
    Quelle). Ambige Nachnamen (mehrfach im Team) → weggelassen (nicht raten)."""
    try:
        from injury_positions import _lastname as _ln
    except Exception:
        return {}
    norm = {"Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Attacker": "F"}
    counts, pos = {}, {}
    for p in (players_raw or []):
        player = p.get("player") or {}
        stats_list = p.get("statistics") or []
        stats = stats_list[0] if stats_list else {}
        api_pos = (stats.get("games") or {}).get("position") or player.get("position")
        pc = norm.get(api_pos)
        ln = _ln(player.get("name"))
        if not ln or not pc:
            continue
        counts[ln] = counts.get(ln, 0) + 1
        pos[ln] = pc
    return {ln: pc for ln, pc in pos.items() if counts[ln] == 1}


def identify_starters(players_raw: list) -> list:
    """
    From the raw API player list, extract the top-11 starters by minutes
    (with position-based caps to keep the lineup realistic), compute
    importance scores, and return a clean list of starter dicts.
    """
    processed = []
    for item in players_raw:
        player = item.get("player", {})
        stats_list = item.get("statistics", [])
        if not stats_list:
            continue
        # Use stats entry with MOST minutes (not [0]) — stats[0] is often CL/Cup
        # stats, not the domestic league where players accumulate most playing time.
        stats = max(stats_list, key=lambda s: s.get("games", {}).get("minutes") or 0)

        minutes  = stats.get("games", {}).get("minutes") or 0
        lineups  = stats.get("games", {}).get("lineups") or 0
        if minutes < 180:   # ignore players with very little game time
            continue

        # Position lives in statistics[x].games.position, NOT in player.position
        api_pos = stats.get("games", {}).get("position", "") or player.get("position", "Midfielder")
        # Normalise position to G / D / M / F
        pos_map = {
            "Goalkeeper": "G", "Defender": "D",
            "Midfielder": "M", "Attacker": "F",
        }
        pos = pos_map.get(api_pos, "M")

        processed.append({
            "id":         player.get("id"),
            "name":       player.get("name", ""),
            "pos":        pos,
            "minutes":    minutes,
            "lineups":    lineups,
            "goals":      stats.get("goals", {}).get("total")     or 0,
            "assists":    stats.get("goals", {}).get("assists")    or 0,
            "shots":      stats.get("shots", {}).get("total")      or 0,
            "keyPasses":  stats.get("passes", {}).get("key")       or 0,
            "tackles":    stats.get("tackles", {}).get("total")    or 0,
            "interceptions": stats.get("tackles", {}).get("interceptions") or 0,
            "blocks":     stats.get("tackles", {}).get("blocks")   or 0,
            "rating":     float(stats.get("games", {}).get("rating") or 0) or 6.5,
            "importance": player_importance(stats, pos),
        })

    # Sort by minutes descending
    processed.sort(key=lambda p: p["minutes"], reverse=True)

    # Position caps: realistic starting lineup
    POS_CAPS = {"G": 1, "D": 5, "M": 5, "F": 4}
    pos_counts = {"G": 0, "D": 0, "M": 0, "F": 0}
    starters   = []

    for p in processed:
        if len(starters) >= 11:
            break
        pos = p["pos"]
        if pos_counts.get(pos, 0) < POS_CAPS.get(pos, 3):
            starters.append(p)
            pos_counts[pos] = pos_counts.get(pos, 0) + 1

    # If we didn't fill 11 spots (unusual squad compositions), just take top-N by minutes
    if len(starters) < 8:
        starters = processed[:11]

    return starters

# ── Squad strength (also used standalone, mirrors update_dashboard logic) ─────

def norm(name: str) -> str:
    n = name.lower()
    return re.sub(r"[^a-z0-9 ]", " ", n).strip()


def names_match(a: str, b: str) -> bool:
    """Fuzzy match two player names (handles 'Saka' vs 'Bukayo Saka' etc.)."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    # Substring: last name match
    wa = [w for w in na.split() if len(w) > 2]
    wb = [w for w in nb.split() if len(w) > 2]
    if not wa or not wb:
        return False
    # Any word from last-name portion overlap (skip first token = first name)
    last_a = wa[-1]
    last_b = wb[-1]
    return last_a == last_b or last_a in nb or last_b in na


def compute_squad_strength(starters: list, missing_names: list) -> tuple[float, list]:
    """
    Cross-reference starters with missing player names (from injury data).
    Returns (strength_score 0-10, list_of_missing_starters).

    Deduction per missing starter (calibrated for importance scores 0.5–0.9):
      GK  → imp × 2.5, cap 1.2  (any GK absence seriously weakens the team)
      FWD → imp × 1.6, cap 1.0  (star striker ≈ -1.0, regular ≈ -0.7)
      MID → imp × 1.0, cap 0.7  (key midfielder ≈ -0.7)
      DEF → imp × 1.2, cap 0.9  (key defender ≈ -0.8)

    Reference benchmarks (realistic importance ~0.75):
      1 key player out  → ~8.5–9.0/10
      3 key players out → ~7.0–7.5/10
      5 key players out → ~5.5–6.0/10  (genuine squad crisis)
    """
    pos_mult  = {"G": 2.5, "F": 1.6, "M": 1.0, "D": 1.2}
    pos_floor = {"G": 0.4, "F": 0.15, "M": 0.1, "D": 0.15}
    pos_ceil  = {"G": 1.2, "F": 1.0, "M": 0.7, "D": 0.9}

    score   = 10.0
    missing = []

    for starter in starters:
        for mname in missing_names:
            if names_match(starter["name"], mname):
                pos    = starter["pos"]
                imp    = starter["importance"]
                # No * 3.5 multiplier — importance scores are now realistic (0.5–0.9)
                # so direct multiplication gives sensible deductions
                deduct = max(pos_floor[pos],
                             min(pos_ceil[pos], imp * pos_mult[pos]))
                score -= deduct
                missing.append(starter)
                break  # don't double-count

    score = max(0.0, round(score * 2) / 2)  # snap to nearest 0.5
    return score, missing

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not APIF_KEY:
        print("❌  APISPORTS_KEY not set — abort")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    print("=" * 60)
    print("  BetEdge — Weekly Squad Fetch")
    print(f"  {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    cache = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season":    2025,
        "teams":     {},
    }

    total_teams = 0
    total_calls = 0

    for key, cfg in LEAGUES.items():
        apif_id = cfg["apif_id"]
        print(f"\n  {key} (league {apif_id})…")

        # ── 1. Fetch standings to identify stake teams ──────────────────────
        standings = []
        for season in [2025, 2026]:
            resp = apif_get("standings", {"league": apif_id, "season": season})
            total_calls += 1
            if resp:
                # 21.07.2026 (Lucas): NICHT nur standings[0]. Ligen mit mehreren Tabellen-Gruppen
                # (MLS = Eastern + Western Conference) hatten sonst nur die halbe Liga (15/30 Teams).
                # Europäische Ein-Tabellen-Ligen haben genau eine Gruppe → Verhalten unverändert.
                _groups = resp[0].get("league", {}).get("standings", [[]]) or [[]]
                rows = [r for grp in _groups for r in (grp or [])]
                standings = [
                    {"pos": r["rank"], "team": r["team"]["name"],
                     "teamId": r["team"]["id"], "pts": r["points"],
                     "played": r["all"]["played"], "gd": r["goalsDiff"]}
                    for r in rows
                ]
                if standings:
                    break

        if not standings:
            print(f"  ⚠ Keine Standings — übersprungen")
            continue

        # ── 2. Identify teams to fetch ─────────────────────────────────────
        if key in FULL_FETCH_LEAGUES:
            # Big-5: fetch ALL teams so opponents of stake teams are also covered
            teams_to_fetch = standings
            print(f"    {len(standings)} teams, alle werden gefetcht (Big-5-Liga)")
        else:
            teams_to_fetch = [t for t in standings if has_stake_label(t, standings, cfg)]
            print(f"    {len(standings)} teams, {len(teams_to_fetch)} mit Stake-Label")

        # ── 3. Fetch players for each team ─────────────────────────────────
        for team in teams_to_fetch:
            tid  = team["teamId"]
            name = team["team"]
            print(f"    👥 {name} (ID {tid})… ", end="", flush=True)

            players_raw = fetch_team_players(tid)
            total_calls += (2 if players_raw else 1)  # approx (pagination)

            if not players_raw:
                print("keine Daten")
                continue

            starters = identify_starters(players_raw)
            if not starters:
                print("keine Starter erkannt")
                continue

            # Pre-compute squad strength without injuries (baseline = full squad)
            cache["teams"][str(tid)] = {
                "name":     name,
                "leagueKey": key,
                "starters": starters,
                "posMap":   _full_position_map(players_raw),   # ALLE Spieler → Injury-Positionen
            }
            total_teams += 1
            top3 = ", ".join(
                f"{s['name']} ({s['pos']},{s['minutes']}min,imp={s['importance']})"
                for s in starters[:3]
            )
            print(f"✅  {len(starters)} Starter · Top3: {top3}")

    # ── Save cache ────────────────────────────────────────────────────────────
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {total_teams} Teams gecacht")
    print(f"   API-Calls: ~{total_calls}")
    print(f"   Cache: {CACHE_FILE}")
    print(f"   Nächster Lauf: nächsten Montag 03:00 Vienna\n")


if __name__ == "__main__":
    main()
