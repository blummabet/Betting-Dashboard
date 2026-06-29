#!/usr/bin/env python3
"""
fetch_wm_corners.py — WM 2026 Corner Statistics + xG Fetcher via API-Football.

Writes to wm2026-data.json:
  "cornersForm" → {
      "MEX": { "forAvg": 5.2, "againstAvg": 4.1, "games": 10, "updatedAt": "ISO" },
      …
  }
  "xgStats" → {
      "MEX": { "xgForAvg": 1.42, "xgAgainstAvg": 0.91, "games": 7, "updatedAt": "ISO" },
      …
  }

xG is extracted from the same /fixtures/statistics calls as corners — no extra API cost.
API-Football returns "expected_goals" for many international competitions (World Cup
qualifiers, Nations League, major friendlies). If unavailable for a fixture, that
fixture is simply skipped for xG (corners may still count).

Run:   python3 fetch_wm_corners.py [--force]
"""

import json, os, sys, time, http.client
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D   # dataset-aware (28.06.2026): Liga füllt cornersForm/Ecken-Serien

BASE         = Path(__file__).parent
WM_FILE      = D.data_file()   # wm2026-data.json (WM) bzw. liga-data.json (Liga)
CORNER_LINE  = 9.5             # Gesamt-Ecken-Linie für die Ecken-Serie (Streak-Content)
APIF_HOST    = "v3.football.api-sports.io"
APIF_KEY     = os.environ.get("APISPORTS_KEY", "")
DELAY        = 1.5       # seconds between requests (Pro plan: 10 req/min)
MAX_FIXTURES = 15        # Erhöht 08.06.2026 von 10 → 15 für größeres xG-Sample.
                          # (CONMEBOL/AFC-Quali liefert in API-Football kein xG,
                          # daher bleibt 30/48 Teams auch bei höherem Limit ohne xG.)
FORCE        = "--force" in sys.argv

# Cache-TTL pro Profil. Liga: 72h (Saisons spielen ständig). WM: 168h (1 Woche),
# weil NTs keine Test-Spiele zwischen WM-Matches haben — Daten ändern sich nur
# nach echten Spielen. Spart pro Workflow-Run ~12 Minuten wenn Cache greift.
def _stale_hours() -> int:
    try:
        cfg = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or cfg["profiles"].get("active", "wm2026")
        return int(cfg["profiles"].get(active, {}).get("fetch_corners", {}).get("stale_hours", 72))
    except Exception:
        return 72

STALE_H      = _stale_hours()


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

def _parse_float(val) -> float | None:
    """Safely parse a stat value to float. Returns None if not numeric."""
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "."))
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def fetch_fixture_stats(fixture_id: int, team_api_id: int) -> dict:
    """
    Fetch /fixtures/statistics for one fixture.
    Extracts for the given team (and its opponent):
      - Corner Kicks  → c_for, c_against
      - expected_goals → xg_for, xg_against  (None if not in response)

    Returns dict with keys: c_for, c_against, xg_for, xg_against
    All values are int/float or None if unavailable.
    """
    resp = apif_get("fixtures/statistics", {"fixture": fixture_id})
    time.sleep(DELAY)

    result = {"c_for": None, "c_against": None, "xg_for": None, "xg_against": None}

    if not resp:
        return result

    # resp: [{"team": {"id": ...}, "statistics": [{"type": "...", "value": ...}, ...]}, ...]
    corners: dict[int, int]   = {}
    xg:      dict[int, float] = {}
    team_ids: list[int]       = []

    for team_stats in resp:
        t_id = team_stats.get("team", {}).get("id")
        if t_id is None:
            continue
        team_ids.append(t_id)

        for stat in team_stats.get("statistics", []):
            stype = stat.get("type", "")
            val   = stat.get("value")

            if stype == "Corner Kicks":
                try:
                    corners[t_id] = int(val) if val is not None else 0
                except (ValueError, TypeError):
                    corners[t_id] = 0

            elif stype == "expected_goals":
                # API-Football returns e.g. "1.42" or null
                parsed = _parse_float(val)
                if parsed is not None:
                    xg[t_id] = parsed

    # Corners for our team
    if team_api_id in corners:
        result["c_for"] = corners[team_api_id]
        for opp_id in team_ids:
            if opp_id != team_api_id and opp_id in corners:
                result["c_against"] = corners[opp_id]
                break

    # xG for our team
    if team_api_id in xg:
        result["xg_for"] = xg[team_api_id]
        for opp_id in team_ids:
            if opp_id != team_api_id and opp_id in xg:
                result["xg_against"] = xg[opp_id]
                break

    return result


# ── Main computation per team (corners + xG) ────────────────────────────

def compute_stats_for_team(tid: str, api_id: int) -> tuple[dict | None, dict | None]:
    """
    Fetch fixtures and their statistics for one team.
    Returns (corners_form, xg_stats) — either may be None if no data found.
    Both are computed from the same /fixtures/statistics API calls.
    """
    print(f"  Fixtures {tid} (ID {api_id})...", end=" ", flush=True)
    fixtures = fetch_fixtures(api_id)

    if not fixtures:
        print("keine Fixtures")
        return None, None

    print(f"{len(fixtures)} Fixtures, hole Stats...", flush=True)

    c_for_list:    list[int]   = []
    c_against_list: list[int]  = []
    c_total_dated: list[tuple]  = []   # (fixture_date, gesamt_ecken) für die Streak-Sequenz
    xg_for_list:   list[float] = []
    xg_against_list: list[float] = []

    for fx in fixtures[:MAX_FIXTURES]:
        fx_id = fx.get("fixture", {}).get("id")
        if not fx_id:
            continue

        stats = fetch_fixture_stats(fx_id, api_id)

        # Corners (both sides must be present)
        if stats["c_for"] is not None and stats["c_against"] is not None:
            c_for_list.append(stats["c_for"])
            c_against_list.append(stats["c_against"])
            c_total_dated.append((fx.get("fixture", {}).get("date", ""),
                                  stats["c_for"] + stats["c_against"]))

        # xG (both sides must be present)
        if stats["xg_for"] is not None and stats["xg_against"] is not None:
            xg_for_list.append(stats["xg_for"])
            xg_against_list.append(stats["xg_against"])

    # ── Build cornersForm ─────────────────────────────────────────────────
    corners_result = None
    c_games = len(c_for_list)
    if c_games > 0:
        # Ecken-Serie (28.06.2026, Lucas): Gesamt-Ecken pro Spiel > Linie, most-recent-first (nach
        # Fixture-Datum sortiert). overLineRate = Grundrate dafür (Continuation im Streak).
        _seq_src = sorted(c_total_dated, key=lambda x: x[0], reverse=True)[:15]
        corner_over_seq = [bool(tot > CORNER_LINE) for (_d, tot) in _seq_src]
        over_rate = round(sum(corner_over_seq) / len(corner_over_seq), 3) if corner_over_seq else None
        corners_result = {
            "forAvg":     round(sum(c_for_list)     / c_games, 2),
            "againstAvg": round(sum(c_against_list) / c_games, 2),
            "games":      c_games,
            "cornerLine":     CORNER_LINE,
            "cornerOverSeq":  corner_over_seq,
            "overLineRate":   over_rate,
            "updatedAt":  now_iso(),
        }

    # ── Build xgStats ─────────────────────────────────────────────────────
    xg_result = None
    xg_games = len(xg_for_list)
    if xg_games > 0:
        xg_result = {
            "xgForAvg":     round(sum(xg_for_list)     / xg_games, 3),
            "xgAgainstAvg": round(sum(xg_against_list) / xg_games, 3),
            "games":        xg_games,
            "updatedAt":    now_iso(),
        }

    # Log
    corner_str = f"Ecken {corners_result['forAvg']:.1f}/{corners_result['againstAvg']:.1f} ({c_games}G)" if corners_result else "keine Ecken"
    xg_str     = f"xG {xg_result['xgForAvg']:.2f}/{xg_result['xgAgainstAvg']:.2f} ({xg_games}G)"     if xg_result     else "kein xG"
    print(f"  -> {tid}: {corner_str} | {xg_str}")

    return corners_result, xg_result


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
    wm.setdefault("xgStats",     {})
    corners_form: dict = wm["cornersForm"]
    xg_stats:     dict = wm["xgStats"]

    c_updated = c_skipped = c_no_data = 0
    x_updated = x_no_data = 0

    for tid in sorted(team_ids.keys()):
        api_id = team_ids[tid]

        # Skip if both corners AND xG are fresh.
        # Schema-stale (28.06.2026): fehlt die neue cornerOverSeq, trotz Zeit-Frische neu holen —
        # sonst schreibt der Cache die Ecken-Serie nie (wie beim Form-o25Seq-Fix).
        _c_entry = corners_form.get(tid, {})
        c_stale = is_stale(_c_entry.get("updatedAt"), STALE_H) or ("cornerOverSeq" not in _c_entry)
        x_stale = is_stale(xg_stats.get(tid,     {}).get("updatedAt"), STALE_H)

        if not c_stale and not x_stale:
            c_skipped += 1
            continue

        try:
            corners_result, xg_result = compute_stats_for_team(tid, api_id)

            if corners_result:
                corners_form[tid] = corners_result
                c_updated += 1
            else:
                c_no_data += 1

            if xg_result:
                xg_stats[tid] = xg_result
                x_updated += 1
            else:
                x_no_data += 1

        except Exception as e:
            print(f"  Fehler bei {tid}: {e}")
            c_no_data += 1
            x_no_data += 1

    wm["cornersForm"] = corners_form
    wm["xgStats"]     = xg_stats
    wm.setdefault("_meta", {})["cornersUpdatedAt"] = now_iso()
    wm["_meta"]["xgUpdatedAt"] = now_iso()

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n[cornersForm] {c_updated} aktualisiert, {c_skipped} uebersprungen, {c_no_data} ohne Daten.")
    print(f"[xgStats]     {x_updated} aktualisiert, {c_skipped} uebersprungen, {x_no_data} ohne Daten.")
    print("wm2026-data.json gespeichert.")


if __name__ == "__main__":
    main()
