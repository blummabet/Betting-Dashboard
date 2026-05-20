#!/usr/bin/env python3
"""
fetch_wm_player_props.py — WM 2026 Player Props (Anytime Scorer)

Fetcht Anytime Scorer Quoten von TheOddsAPI für alle WM-Matches
der nächsten DAYS_AHEAD Tage und speichert sie in wm2026-player-props.json.

Graceful no-op wenn Player Props noch nicht gelistet sind
(TheOddsAPI listet diese typischerweise 1-7 Tage vor dem Spiel).

Struktur wm2026-player-props.json:
{
  "MEX-ZAF": {
    "eventId":   "...",
    "date":      "2026-06-11",
    "updatedAt": "ISO",
    "players": [
      {"name": "R. Jiménez", "teamId": "MEX", "odds": 2.50, "bookmaker": "pinnacle"},
      ...
    ]
  }
}

Umgebungsvariablen:
  ODDS_API_KEY   — TheOddsAPI Key
  DAYS_AHEAD     — wie viele Tage voraus fetchen (Standard: 7)
"""

import json
import os
import sys
import time
import http.client
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
PROPS_FILE  = BASE / "wm2026-player-props.json"

ODDS_KEY    = os.environ.get("ODDS_API_KEY", "16154a94ee84482dcd5a4af88d521d73")
ODDS_HOST   = "api.the-odds-api.com"
DAYS_AHEAD  = int(os.environ.get("DAYS_AHEAD", "7"))

WM_SPORT_KEYS = ["soccer_fifa_world_cup", "soccer_world_cup"]

# Bevorzugte Bookmaker für Player Props
PROP_BOOKS = ["pinnacle", "bet365", "williamhill", "unibet"]

# Fuzzy name matching: unser ID → TheOddsAPI Teamnamen
TEAM_NAMES: dict[str, list[str]] = {
    "MEX": ["Mexico"], "ZAF": ["South Africa"], "KOR": ["South Korea"],
    "CZE": ["Czech Republic", "Czechia"], "CAN": ["Canada"],
    "BIH": ["Bosnia", "Bosnia and Herzegovina"], "QAT": ["Qatar"],
    "SUI": ["Switzerland"], "BRA": ["Brazil"], "MAR": ["Morocco"],
    "HTI": ["Haiti"], "SCO": ["Scotland"], "USA": ["United States", "USA"],
    "PRY": ["Paraguay"], "AUS": ["Australia"], "TUR": ["Turkey", "Türkiye"],
    "GER": ["Germany"], "CUW": ["Curaçao", "Curacao"], "CIV": ["Ivory Coast"],
    "ECU": ["Ecuador"], "NED": ["Netherlands"], "JPN": ["Japan"],
    "SWE": ["Sweden"], "TUN": ["Tunisia"], "BEL": ["Belgium"],
    "EGY": ["Egypt"], "IRN": ["Iran"], "NZL": ["New Zealand"],
    "ESP": ["Spain"], "CPV": ["Cape Verde"], "SAU": ["Saudi Arabia"],
    "URU": ["Uruguay"], "FRA": ["France"], "SEN": ["Senegal"],
    "IRQ": ["Iraq"], "NOR": ["Norway"], "ARG": ["Argentina"],
    "DZA": ["Algeria"], "AUT": ["Austria"], "JOR": ["Jordan"],
    "POR": ["Portugal"], "COD": ["DR Congo", "Congo DR"],
    "UZB": ["Uzbekistan"], "COL": ["Colombia"], "ENG": ["England"],
    "CRO": ["Croatia"], "GHA": ["Ghana"], "PAN": ["Panama"],
}

# Reverse map: name fragment → team ID
_NAME_TO_ID: dict[str, str] = {}
for tid, names in TEAM_NAMES.items():
    for n in names:
        _NAME_TO_ID[n.lower()] = tid


def _name_to_id(name: str) -> str | None:
    nl = name.lower().strip()
    for key, tid in _NAME_TO_ID.items():
        if key in nl or nl in key:
            return tid
    return None


def _odds_get(path: str) -> list | dict | None:
    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(ODDS_HOST, context=ctx, timeout=25)
        conn.request("GET", path, headers={"User-Agent": "CocoBet/1.0"})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        if resp.status in (422, 404):
            return None
        if resp.status == 401:
            print(f"  ❌ TheOddsAPI 401 — check ODDS_API_KEY")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
        return None


def _find_sport_key() -> str | None:
    for sk in WM_SPORT_KEYS:
        data = _odds_get(f"/v4/sports/{sk}/events?apiKey={ODDS_KEY}")
        if data and isinstance(data, list) and len(data) > 0:
            print(f"  ✅ Sport key: {sk}")
            return sk
        time.sleep(0.5)
    return None


def _best_price(bookmakers: list, player_name: str) -> tuple[float | None, str]:
    """Extrahiert besten Anytime-Scorer-Preis für einen Spieler."""
    best_price = None
    best_book  = ""
    for bk in bookmakers:
        bk_key = bk.get("key", "")
        for mkt in bk.get("markets", []):
            if mkt.get("key") not in ("player_goal_scorer", "player_anytime_scorer",
                                       "player_to_score_anytime"):
                continue
            for outcome in mkt.get("outcomes", []):
                if outcome.get("description", "").lower() == player_name.lower():
                    price = outcome.get("price")
                    if price and (best_price is None or
                                  (bk_key in PROP_BOOKS and price > best_price)):
                        best_price = price
                        best_book  = bk_key
    return best_price, best_book


def fetch_event_player_props(event_id: str, sport_key: str) -> list[dict]:
    """
    Fetcht alle Anytime-Scorer-Quoten für ein Event.
    Gibt Liste von {name, odds, bookmaker} zurück.
    """
    path = (f"/v4/sports/{sport_key}/events/{event_id}/odds"
            f"?apiKey={ODDS_KEY}"
            f"&regions=eu,uk"
            f"&markets=player_goal_scorer,player_anytime_scorer"
            f"&oddsFormat=decimal")
    data = _odds_get(path)
    if not data or not isinstance(data, dict):
        return []

    players: dict[str, dict] = {}

    for bk in data.get("bookmakers", []):
        bk_key = bk.get("key", "")
        for mkt in bk.get("markets", []):
            if mkt.get("key") not in ("player_goal_scorer", "player_anytime_scorer",
                                       "player_to_score_anytime"):
                continue
            for outcome in mkt.get("outcomes", []):
                pname = outcome.get("description") or outcome.get("name", "")
                price = outcome.get("price")
                if not pname or not price:
                    continue
                if pname not in players or (
                    bk_key in PROP_BOOKS and
                    PROP_BOOKS.index(bk_key) < PROP_BOOKS.index(players[pname].get("bookmaker", PROP_BOOKS[-1]))
                ):
                    players[pname] = {"name": pname, "odds": price, "bookmaker": bk_key}

    return sorted(players.values(), key=lambda x: x["odds"])


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"⚽  fetch_wm_player_props.py — WM 2026 Player Props")
    print(f"    Key: {'✅' if ODDS_KEY else '❌'} | Window: +{DAYS_AHEAD} Tage\n")

    if not ODDS_KEY:
        print("  ❌ ODDS_API_KEY nicht gesetzt")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    # Lade bestehende Props
    props_out: dict = {}
    if PROPS_FILE.exists():
        with open(PROPS_FILE, encoding="utf-8") as f:
            props_out = json.load(f)

    # Sport Key finden
    sport_key = _find_sport_key()
    if not sport_key:
        print("  ℹ️  WM noch nicht in TheOddsAPI — kein Fetch")
        return

    # Alle Events holen
    events_data = _odds_get(f"/v4/sports/{sport_key}/events?apiKey={ODDS_KEY}")
    if not events_data or not isinstance(events_data, list):
        print("  ⚠️  Keine Events gefunden")
        return

    print(f"  {len(events_data)} Events in TheOddsAPI\n")

    # Cutoff: nur Spiele in den nächsten DAYS_AHEAD Tagen
    cutoff = (datetime.now(timezone.utc) + timedelta(days=DAYS_AHEAD)).date()

    # Gruppen → Fixture-Map aufbauen
    fixture_map: dict[str, dict] = {}
    for gkey, gdata in wm.get("groups", {}).items():
        for fx in gdata.get("fixtures", []):
            try:
                fx_date = datetime.strptime(fx["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            if fx_date > cutoff:
                continue
            odds_key = f"{fx['home']}-{fx['away']}"
            fixture_map[odds_key] = {**fx, "groupKey": gkey}

    if not fixture_map:
        print(f"  ℹ️  Keine Fixtures in den nächsten {DAYS_AHEAD} Tagen")
        return

    # Events mit Fixtures matchen
    matched_events: list[dict] = []
    for ev in events_data:
        ev_home = ev.get("home_team", "")
        ev_away = ev.get("away_team", "")
        h_id = _name_to_id(ev_home)
        a_id = _name_to_id(ev_away)
        if not h_id or not a_id:
            continue
        key = f"{h_id}-{a_id}"
        if key in fixture_map:
            matched_events.append({"odds_key": key, "event_id": ev["id"], "fx": fixture_map[key]})
        # Auch reversed versuchen
        key_rev = f"{a_id}-{h_id}"
        if key_rev in fixture_map:
            matched_events.append({"odds_key": key_rev, "event_id": ev["id"], "fx": fixture_map[key_rev]})

    print(f"  {len(matched_events)} Matches im Fenster gefunden\n")

    fetched = 0
    for ev in matched_events:
        odds_key = ev["odds_key"]
        event_id = ev["event_id"]
        fx       = ev["fx"]

        print(f"  🔍 {odds_key} (Event {event_id[:8]}…)…", end="", flush=True)
        players = fetch_event_player_props(event_id, sport_key)
        time.sleep(1.0)   # Rate limit

        if not players:
            print(" ○ keine Props verfügbar")
            continue

        props_out[odds_key] = {
            "eventId":   event_id,
            "date":      fx["date"],
            "updatedAt": now_iso,
            "players":   players,
        }
        fetched += 1
        print(f" ✅ {len(players)} Spieler")
        for p in players[:5]:
            print(f"     {p['name']}: @{p['odds']} [{p['bookmaker']}]")

    # Speichern
    with open(PROPS_FILE, "w", encoding="utf-8") as f:
        json.dump(props_out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {fetched} Events mit Player Props → {PROPS_FILE.name}")
    if fetched == 0:
        print("   ℹ️  Props erscheinen typischerweise 1-7 Tage vor dem Spiel")


if __name__ == "__main__":
    main()
