#!/usr/bin/env python3
"""
fetch_wm_odds.py — WM 2026 Odds fetcher via TheOddsAPI.

Fetches h2h (1X2) odds for all WM 2026 group stage fixtures and writes
them to wm2026-data.json under the "odds" key.

Odds key format: "{homeId}-{awayId}"  e.g. "MEX-ZAF"
Odds structure:
  {
    "hw": 1.85,        # home win
    "dr": 3.50,        # draw
    "aw": 4.75,        # away win
    "odds_open": {...} # first-ever snapshot (set once, never overwritten)
    "odds_closing": {} # set at kick-off, preserved
    "updatedAt": "ISO"
  }

Run:   python3 fetch_wm_odds.py
Cron:  Daily from June 1 via fetch-wm-data.yml
"""

import json
import os
import sys
import time
import http.client
import ssl
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
HISTORY_FILE = BASE / "wm2026-odds-history.json"

# Minimale Änderung (in absoluten Odds), damit ein neuer Snapshot geschrieben wird
SNAP_MIN_DELTA = 0.02

ODDS_KEY   = os.environ.get("ODDS_API_KEY", "16154a94ee84482dcd5a4af88d521d73")
ODDS_HOST  = "api.the-odds-api.com"

# TheOddsAPI sport key for FIFA World Cup
# Falls back through list until one returns data
WM_SPORT_KEYS = [
    "soccer_fifa_world_cup",
    "soccer_world_cup",
    "soccer_international_wcq",   # WCQ as fallback
]

# Preferred bookmakers for odds (in priority order)
BOOKMAKERS = ["pinnacle", "bet365", "williamhill", "unibet", "betfair"]

# ── Our team IDs → name variants for fuzzy matching TheOddsAPI team names ──────
TEAM_NAMES: dict[str, list[str]] = {
    "MEX": ["Mexico"],
    "ZAF": ["South Africa"],
    "KOR": ["South Korea"],
    "CZE": ["Czech Republic", "Czechia"],
    "CAN": ["Canada"],
    "BIH": ["Bosnia", "Bosnia and Herzegovina"],
    "QAT": ["Qatar"],
    "SUI": ["Switzerland"],
    "BRA": ["Brazil"],
    "MAR": ["Morocco"],
    "HTI": ["Haiti"],
    "SCO": ["Scotland"],
    "USA": ["United States", "USA"],
    "PRY": ["Paraguay"],
    "AUS": ["Australia"],
    "TUR": ["Turkey", "Türkiye"],
    "GER": ["Germany"],
    "CUW": ["Curaçao", "Curacao"],
    "CIV": ["Ivory Coast", "Cote d'Ivoire", "Côte d'Ivoire"],
    "ECU": ["Ecuador"],
    "NED": ["Netherlands", "Holland"],
    "JPN": ["Japan"],
    "SWE": ["Sweden"],
    "TUN": ["Tunisia"],
    "BEL": ["Belgium"],
    "EGY": ["Egypt"],
    "IRN": ["Iran"],
    "NZL": ["New Zealand"],
    "ESP": ["Spain"],
    "CPV": ["Cape Verde"],
    "SAU": ["Saudi Arabia"],
    "URU": ["Uruguay"],
    "FRA": ["France"],
    "SEN": ["Senegal"],
    "IRQ": ["Iraq"],
    "NOR": ["Norway"],
    "ARG": ["Argentina"],
    "DZA": ["Algeria"],
    "AUT": ["Austria"],
    "JOR": ["Jordan"],
    "POR": ["Portugal"],
    "COD": ["DR Congo", "Congo DR", "Democratic Republic of Congo"],
    "UZB": ["Uzbekistan"],
    "COL": ["Colombia"],
    "ENG": ["England"],
    "CRO": ["Croatia"],
    "GHA": ["Ghana"],
    "PAN": ["Panama"],
}

def _name_to_id(name: str) -> str | None:
    """Reverse-lookup: TheOddsAPI team name → our 3-letter ID."""
    name_low = name.lower().strip()
    for tid, variants in TEAM_NAMES.items():
        for v in variants:
            if v.lower() == name_low or v.lower() in name_low or name_low in v.lower():
                return tid
    return None


def odds_get(path: str) -> dict | None:
    """Single HTTPS GET to TheOddsAPI. Returns parsed JSON or None."""
    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(ODDS_HOST, context=ctx, timeout=20)
        conn.request("GET", path, headers={"User-Agent": "CocoBet/1.0"})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        if resp.status == 422:
            return None   # sport not available yet
        if resp.status == 401:
            print("  ❌  TheOddsAPI: 401 Unauthorized — check ODDS_API_KEY")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  ❌  TheOddsAPI request failed: {e}")
        return None


def _find_sport_key() -> str | None:
    """Try WM sport keys until one returns events."""
    for sk in WM_SPORT_KEYS:
        path = f"/v4/sports/{sk}/events?apiKey={ODDS_KEY}"
        data = odds_get(path)
        if data and isinstance(data, list) and len(data) > 0:
            print(f"  ✅  Sport key: {sk} ({len(data)} events)")
            return sk
        elif data is None:
            print(f"  ⚠️  {sk}: not available yet")
        else:
            print(f"  ⚠️  {sk}: 0 events")
        time.sleep(0.5)
    return None


def _best_odds(bookmakers: list, our_book_prio: list) -> dict | None:
    """
    Extract h2h odds from event bookmaker list.
    Prefers pinnacle, then bet365, then any available.
    Returns {"hw": float, "dr": float, "aw": float, "bookmaker": str}
    """
    candidates = {}
    for bk in bookmakers:
        bk_key = bk.get("key", "")
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            if len(outcomes) < 2:
                continue
            candidates[bk_key] = outcomes
    if not candidates:
        return None
    # Pick preferred bookmaker
    for prio in our_book_prio:
        if prio in candidates:
            oc = candidates[prio]
            vals = list(oc.values())
            if len(vals) == 3:
                # Sort by value: lowest = favourite (home win usually listed first by API)
                return {"_oc": oc, "bookmaker": prio}
            elif len(vals) == 2:
                return {"_oc": oc, "bookmaker": prio}
    # Fall back to any
    for bk_key, oc in candidates.items():
        return {"_oc": oc, "bookmaker": bk_key}
    return None


def _extract_h2h(event: dict, home_id: str, away_id: str) -> dict | None:
    """
    Match event to our fixture and extract h2h odds.
    Event has home_team / away_team / bookmakers.
    We need to find the right outcome for home/draw/away.
    """
    home_names = TEAM_NAMES.get(home_id, [home_id])
    away_names = TEAM_NAMES.get(away_id, [away_id])

    ev_home = event.get("home_team", "")
    ev_away = event.get("away_team", "")

    def _matches(ev_name, our_names):
        ev_l = ev_name.lower()
        for n in our_names:
            if n.lower() in ev_l or ev_l in n.lower():
                return True
        return False

    if not (_matches(ev_home, home_names) and _matches(ev_away, away_names)):
        # Try reversed (in case API has teams swapped)
        if not (_matches(ev_home, away_names) and _matches(ev_away, home_names)):
            return None
        # Swapped
        home_id, away_id = away_id, home_id

    bk_result = _best_odds(event.get("bookmakers", []), BOOKMAKERS)
    if not bk_result:
        return None

    oc = bk_result["_oc"]
    home_win = draw = away_win = None

    # Match outcomes by name
    for name, price in oc.items():
        name_id = _name_to_id(name)
        if name_id == home_id:
            home_win = price
        elif name_id == away_id:
            away_win = price
        elif name.lower() in ("draw", "tie", "x"):
            draw = price

    # Fallback: if 3 values and no draw found, the middle is draw
    if draw is None and len(oc) == 3:
        prices = sorted(oc.values())
        # In 1X2 odds, draw is typically middle
        remaining = [p for p in prices if p != home_win and p != away_win]
        if remaining:
            draw = remaining[0]

    if home_win is None or away_win is None:
        return None

    return {
        "hw": round(home_win, 3),
        "dr": round(draw, 3) if draw else None,
        "aw": round(away_win, 3),
        "bookmaker": bk_result["bookmaker"],
    }


def _load_history() -> dict:
    """Lädt wm2026-odds-history.json oder gibt leeres Dict zurück."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_history(history: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _snap_changed(last: dict | None, new_hw: float, new_dr: float | None, new_aw: float) -> bool:
    """True wenn sich mindestens eine Odds um SNAP_MIN_DELTA geändert hat."""
    if last is None:
        return True
    return (
        abs((last.get("hw") or 0) - new_hw) >= SNAP_MIN_DELTA
        or abs((last.get("aw") or 0) - new_aw) >= SNAP_MIN_DELTA
        or (new_dr is not None and abs((last.get("dr") or 0) - new_dr) >= SNAP_MIN_DELTA)
    )


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"💰  fetch_wm_odds.py — WM 2026 Odds")
    print(f"    Key: {'✅ set' if ODDS_KEY else '❌ missing'}")
    print(f"    Time: {now_iso[:19]} UTC\n")

    if not ODDS_KEY:
        print("  ❌  ODDS_API_KEY not set")
        sys.exit(1)

    # ── Load wm2026-data.json ─────────────────────────────────
    if not WM_FILE.exists():
        print("  ❌  wm2026-data.json not found")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    odds_out: dict[str, dict] = wm.get("odds") or {}
    groups = wm.get("groups", {})

    # Build teams Elo map for sanity checks
    teams_elo: dict[str, float] = {}
    for gdata in groups.values():
        for t in gdata.get("teams", []):
            if t.get("elo"):
                teams_elo[t["id"]] = t["elo"]

    # Collect all fixtures
    all_fixtures: list[dict] = []
    for gkey, gdata in groups.items():
        for fx in gdata.get("fixtures", []):
            all_fixtures.append({**fx, "groupKey": gkey})

    print(f"  Fixtures to price: {len(all_fixtures)}")

    # ── Find working sport key ────────────────────────────────
    print("\n  🔍  Looking for WM sport key in TheOddsAPI…")
    sport_key = _find_sport_key()

    if not sport_key:
        print("\n  ℹ️  WM 2026 odds not available in TheOddsAPI yet.")
        print("      Odds typically appear 2–3 weeks before the tournament.")
        print("      Script will succeed silently — no changes to odds data.")
        # Write back unchanged (update meta only)
        wm["_meta"]["oddsUpdatedAt"] = now_iso
        with open(WM_FILE, "w", encoding="utf-8") as f:
            json.dump(wm, f, ensure_ascii=False, indent=2)
        return

    # ── Fetch all odds ────────────────────────────────────────
    print(f"\n  📥  Fetching odds for {sport_key}…")
    path = (f"/v4/sports/{sport_key}/odds"
            f"?apiKey={ODDS_KEY}"
            f"&regions=eu,uk"
            f"&markets=h2h"
            f"&oddsFormat=decimal"
            f"&bookmakers={','.join(BOOKMAKERS)}")
    events = odds_get(path)

    if not events or not isinstance(events, list):
        print("  ⚠️  No events returned from TheOddsAPI")
        return

    print(f"  → {len(events)} events fetched")

    # ── Load odds history ─────────────────────────────────────
    history = _load_history()
    snaps_added = 0

    # ── Match fixtures to events ──────────────────────────────
    matched = 0
    updated = 0
    for fx in all_fixtures:
        home_id = fx["home"]
        away_id = fx["away"]
        key     = f"{home_id}-{away_id}"

        # Find matching event
        matched_event = None
        for ev in events:
            result = _extract_h2h(ev, home_id, away_id)
            if result:
                matched_event = (ev, result)
                break

        if not matched_event:
            continue

        ev, h2h = matched_event
        matched += 1

        # ── Elo sanity check: detect reversed hw/aw ──────────────────────
        # If Elo strongly favors the home team (diff > 200 pts) but market
        # has them as a big underdog (hw > 2.5× aw), the odds are reversed.
        # This happens when TheOddsAPI lists the match in the wrong direction.
        elo_h = teams_elo.get(home_id)
        elo_a = teams_elo.get(away_id)
        if elo_h and elo_a and h2h.get("hw") and h2h.get("aw"):
            elo_diff = elo_h - elo_a
            hw_raw, aw_raw = h2h["hw"], h2h["aw"]
            if elo_diff > 200 and hw_raw > 2.5 * aw_raw:
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff < -200 and aw_raw > 2.5 * hw_raw:
                # Away team strongly favored by Elo but market has it backward
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")

        existing = odds_out.get(key, {})

        # Preserve opening line (first-ever snapshot) — never overwrite
        odds_open = existing.get("odds_open")
        if not odds_open and h2h:
            odds_open = {"hw": h2h["hw"], "dr": h2h["dr"], "aw": h2h["aw"]}

        new_entry = {
            "hw":         h2h["hw"],
            "dr":         h2h["dr"],
            "aw":         h2h["aw"],
            "bookmaker":  h2h["bookmaker"],
            "odds_open":  odds_open,
            "updatedAt":  now_iso,
        }
        # Preserve closing odds if already set
        if existing.get("odds_closing"):
            new_entry["odds_closing"] = existing["odds_closing"]

        odds_out[key] = new_entry
        updated += 1

        # ── Odds History Snapshot ─────────────────────────────
        snaps = history.setdefault(key, [])
        last_snap = snaps[-1] if snaps else None
        if _snap_changed(last_snap, h2h["hw"], h2h["dr"], h2h["aw"]):
            snaps.append({
                "ts":  now_iso,
                "hw":  h2h["hw"],
                "dr":  h2h["dr"],
                "aw":  h2h["aw"],
                "bk":  h2h["bookmaker"],
            })
            snaps_added += 1

        home_names = TEAM_NAMES.get(home_id, [home_id])
        print(f"  ✅  {home_names[0]} vs {TEAM_NAMES.get(away_id, [away_id])[0]}: "
              f"H {h2h['hw']} / X {h2h['dr']} / A {h2h['aw']} [{h2h['bookmaker']}]")

    # ── Write back ────────────────────────────────────────────
    wm["odds"] = odds_out
    wm["_meta"]["oddsUpdatedAt"] = now_iso

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    # ── Write history ─────────────────────────────────────────
    if snaps_added > 0:
        _save_history(history)
        print(f"   📸  {snaps_added} neue Snapshots → {HISTORY_FILE.name}")
    else:
        print(f"   📸  Keine Odds-Änderung — kein neuer Snapshot")

    remaining = len(all_fixtures) - matched
    print(f"\n✅  {updated} fixtures priced, {remaining} not yet available")
    print(f"   Saved: {WM_FILE}")


if __name__ == "__main__":
    main()
