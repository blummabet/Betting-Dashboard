#!/usr/bin/env python3
"""
fetch_wm_corners.py — WM 2026 Team Corner Statistics fetcher via API-Football.

Writes to wm2026-data.json:
  "cornersForm" → {
      "MEX": { "forAvg": 5.2, "againstAvg": 4.1, "games": 10, "updatedAt": "ISO" },
      …
  }

Run:   python3 fetch_wm_corners.py [--force]
"""

import json, os, sys, time, http.client
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
APIF_HOST    = "v3.football.api-sports.io"
APIF_KEY     = os.environ.get("APISPORTS_KEY", "")
DELAY        = 1.5       # seconds between requests (Pro plan: 10 req/min)
MAX_FIXTURES = 10        # cap stats calls per team to stay within API budget
FORCE        = "--force" in sys.argv
STALE_H      = 72        # re-fetch after 72 hours


# ── HTTP helper ───────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> list:
    """Single API-Football GET. Returns response list or []."""
    if not APIF_KEY:
        return []
    import urllib.parse
    query = urllib.parse.urlencode(params)
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", f"/{endpoint}?{query}",
                     headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        data = json.loads(raw)
        errs = data.get("errors", {})
        if errs and errs not in ({}, []):
            print(f"  API error /{endpoint}: {errs}")
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  Request failed /{endpoint}?{query}: {e}")
        return []


# ── Staleness check ───────────────────────────────────────────────────────

def is_stale(updated_at: str | None, hours: int) -> bool:
    if not updated_at or FORCE:
        return True
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() > hours * 3600
    except Exception:
        return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Fetch last fixtures for a team ───────────────────────────────────────

def fetch_fixtures(api_id: int) -> list:
    """
    Fetch last MAX_FIXTURES completed fixtures for a team.
    Tries international type first, falls back to all competitions.
    """
    # Fetch last fixtures — kein type-Filter (API-Football unterstützt type nicht)
    resp = apif_get("fixtures", {"team": api_id, "last": MAX_FIXTURES, "status": "FT"})
    time.sleep(DELAY)

    return resp


# ── Extract corner data from fixture statistics ───────────────────────────

def fetch_corner_stats(fixture_id: int, team_api_id: int) -> tuple[int | None, int | None]:
    """
    Fetch fixture statistics and extract corner kicks for the given team.
    Returns (corners_for, corners_against) or (None, None) if not available.
    """
    resp = apif_get("fixtures/statistics", {"fixture": fixture_id})
    time.sleep(DELAY)

    if not resp:
        return None, None

    # resp is a list of team stats objects: [{"team": {...}, "statistics": [...]}, ...]
    corners: dict[int, int] = {}
    teams_in_fixture: list[int] = []

    for team_stats in resp:
        t_id = team_stats.get("team", {}).get("id")
        if t_id is None:
            continue
        teams_in_fixture.append(t_id)
        for stat in team_stats.get("statistics", []):
            if stat.get("type") == "Corner Kicks":
                val = stat.get("value")
                try:
                    corners[t_id] = int(val) if val is not None else 0
                except (ValueError, TypeError):
                    corners[t_id] = 0
                break

    if team_api_id not in corners:
        return None, None

    corners_for = corners[team_api_id]

    # Find the opponent's corners
    opponent_corners: int | None = None
    for t_id in teams_in_fixture:
        if t_id != team_api_id and t_id in corners:
            opponent_corners = corners[t_id]
            break

    if opponent_corners is None:
        return None, None

    return corners_for, opponent_corners


# ── Main corner computation per team ─────────────────────────────────────

def compute_corners_for_team(tid: str, api_id: int) -> dict | None:
    """
    Fetch fixtures and their corner statistics for one team.
    Returns a cornersForm dict or None if no data found.
    """
    print(f"  Fixtures {tid} (ID {api_id})...", end=" ", flush=True)
    fixtures = fetch_fixtures(api_id)

    if not fixtures:
        print("keine Fixtures")
        return None

    print(f"{len(fixtures)} Fixtures gefunden, hole Corner-Stats...", flush=True)

    totals_for: list[int] = []
    totals_against: list[int] = []

    for fx in fixtures[:MAX_FIXTURES]:
        fx_id = fx.get("fixture", {}).get("id")
        if not fx_id:
            continue

        c_for, c_against = fetch_corner_stats(fx_id, api_id)
        if c_for is None or c_against is None:
            continue

        totals_for.append(c_for)
        totals_against.append(c_against)

    games = len(totals_for)
    if games == 0:
        print(f"  -> {tid}: keine Corner-Daten in Fixtures")
        return None

    for_avg     = round(sum(totals_for)     / games, 2)
    against_avg = round(sum(totals_against) / games, 2)

    print(f"  -> {tid}: {games} Spiele | Ecken fuer={for_avg:.2f}, gegen={against_avg:.2f}")

    return {
        "forAvg":     for_avg,
        "againstAvg": against_avg,
        "games":      games,
        "updatedAt":  now_iso(),
    }


# ── MAIN ──────────────────────────────────────────────────────────────────

def main():
    if not APIF_KEY:
        print("APISPORTS_KEY nicht gesetzt — fetch uebersprungen.")
        return

    print("=== fetch_wm_corners.py ===")
    print(f"Force: {FORCE}  |  MAX_FIXTURES: {MAX_FIXTURES}  |  STALE_H: {STALE_H}\n")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    team_ids: dict[str, int] = wm.get("teamIds", {})
    if not team_ids:
        print("Keine teamIds in wm2026-data.json — bitte zuerst fetch_wm_form.py ausfuehren.")
        return

    wm.setdefault("cornersForm", {})
    corners_form: dict = wm["cornersForm"]

    updated  = 0
    skipped  = 0
    no_data  = 0

    for tid in sorted(team_ids.keys()):
        api_id = team_ids[tid]

        existing = corners_form.get(tid, {})
        if not is_stale(existing.get("updatedAt"), STALE_H):
            skipped += 1
            continue

        try:
            result = compute_corners_for_team(tid, api_id)
            if result:
                corners_form[tid] = result
                updated += 1
            else:
                no_data += 1
        except Exception as e:
            print(f"  Fehler bei {tid}: {e}")
            no_data += 1

    wm["cornersForm"] = corners_form
    wm.setdefault("_meta", {})["cornersUpdatedAt"] = now_iso()

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n[cornersForm] {updated} aktualisiert, {skipped} uebersprungen, {no_data} ohne Daten.")
    print("wm2026-data.json gespeichert.")


if __name__ == "__main__":
    main()
