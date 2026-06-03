#!/usr/bin/env python3
"""
fetch_wm_player_props.py — WM 2026 Player Props (Multi-Market)

Fetcht 6 Spieler-Märkte von TheOddsAPI für alle WM-Matches der
nächsten DAYS_AHEAD Tage und speichert sie in wm2026-player-props.json.

Märkte:
  • player_goal_scorer_anytime   → Anytime Scorer
  • player_goal_scorer_first     → First Goalscorer
  • player_shots                 → Total Shots (Over/Under)
  • player_shots_on_target       → Shots on Target (Over/Under)
  • player_assists               → Assists
  • player_to_receive_card       → Card (Yes)

Graceful no-op wenn Märkte noch nicht gelistet sind
(TheOddsAPI öffnet Player-Props bei Fußball typischerweise 1-3 Tage vor Anpfiff).

Struktur wm2026-player-props.json:
{
  "MEX-ZAF": {
    "eventId":   "...",
    "date":      "2026-06-11",
    "updatedAt": "ISO",
    "markets": {
      "anytime_scorer":  [{"name": "...", "odds": 2.50, "bookmaker": "pinnacle"}, ...],
      "first_scorer":    [...],
      "player_shots":    [{"name": "...", "line": 1.5, "over": 1.85, "under": 2.10,
                            "bookmaker": "..."}, ...],
      "player_sot":      [...],
      "player_assists":  [...],
      "player_cards":    [...]
    }
  }
}

Umgebungsvariablen:
  ODDS_API_KEY   — TheOddsAPI Key
  DAYS_AHEAD     — wie viele Tage voraus fetchen (Standard: 4 — Props öffnen sich erst spät)
  POLL_MIN_DAYS  — nur Matches fetchen die in <= N Tagen sind (Standard: 4)
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
DAYS_AHEAD  = int(os.environ.get("DAYS_AHEAD", "4"))

WM_SPORT_KEYS = ["soccer_fifa_world_cup", "soccer_world_cup"]

# Bevorzugte Bookmaker für Player Props (Reihenfolge = Präferenz)
PROP_BOOKS = ["pinnacle", "bet365", "williamhill", "betmgm", "draftkings",
              "fanduel", "unibet_uk", "skybet", "paddypower", "ladbrokes_uk",
              "betfair_ex_uk", "betfair_ex_eu", "betsson", "leovegas"]

# Markt-Definitionen: API-Key → unser internes Key + Typ
# typ = "single" (1 Outcome pro Spieler) oder "ou" (Over/Under mit Line)
PLAYER_MARKETS = [
    {"api": "player_goal_scorer_anytime", "key": "anytime_scorer",  "type": "single"},
    {"api": "player_goal_scorer_first",   "key": "first_scorer",    "type": "single"},
    {"api": "player_shots",               "key": "player_shots",    "type": "ou"},
    {"api": "player_shots_on_target",     "key": "player_sot",      "type": "ou"},
    {"api": "player_assists",             "key": "player_assists",  "type": "single"},
    {"api": "player_to_receive_card",     "key": "player_cards",    "type": "single"},
]
API_KEYS_CSV = ",".join(m["api"] for m in PLAYER_MARKETS)
API_TO_INTERNAL = {m["api"]: m for m in PLAYER_MARKETS}

# Fuzzy name matching: unser ID → TheOddsAPI Teamnamen
TEAM_NAMES: dict[str, list[str]] = {
    "MEX": ["Mexico"], "ZAF": ["South Africa"], "KOR": ["South Korea"],
    "CZE": ["Czech Republic", "Czechia"], "CAN": ["Canada"],
    "BIH": ["Bosnia", "Bosnia and Herzegovina", "Bosnia & Herzegovina"],
    "QAT": ["Qatar"], "SUI": ["Switzerland"], "BRA": ["Brazil"],
    "MAR": ["Morocco"], "HTI": ["Haiti"], "SCO": ["Scotland"],
    "USA": ["United States", "USA"], "PRY": ["Paraguay"], "AUS": ["Australia"],
    "TUR": ["Turkey", "Türkiye"], "GER": ["Germany"],
    "CUW": ["Curaçao", "Curacao"], "CIV": ["Ivory Coast"], "ECU": ["Ecuador"],
    "NED": ["Netherlands"], "JPN": ["Japan"], "SWE": ["Sweden"],
    "TUN": ["Tunisia"], "BEL": ["Belgium"], "EGY": ["Egypt"],
    "IRN": ["Iran"], "NZL": ["New Zealand"], "ESP": ["Spain"],
    "CPV": ["Cape Verde"], "SAU": ["Saudi Arabia"], "URU": ["Uruguay"],
    "FRA": ["France"], "SEN": ["Senegal"], "IRQ": ["Iraq"],
    "NOR": ["Norway"], "ARG": ["Argentina"], "DZA": ["Algeria"],
    "AUT": ["Austria"], "JOR": ["Jordan"], "POR": ["Portugal"],
    "COD": ["DR Congo", "Congo DR"], "UZB": ["Uzbekistan"],
    "COL": ["Colombia"], "ENG": ["England"], "CRO": ["Croatia"],
    "GHA": ["Ghana"], "PAN": ["Panama"],
}

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


def _book_priority(book_key: str) -> int:
    """Niedrigerer Wert = bessere Bookie. Unbekannt = 999."""
    try:
        return PROP_BOOKS.index(book_key)
    except ValueError:
        return 999


def _parse_single_market(market: dict, book_key: str) -> dict[str, dict]:
    """
    Parst einen 'single'-Markt (Anytime Scorer, First Scorer, Assists, Cards).
    Outcome-Struktur: {description=player_name, name="Yes"/player, price=odds}
    """
    out: dict[str, dict] = {}
    for o in market.get("outcomes", []):
        pname = (o.get("description") or o.get("name") or "").strip()
        price = o.get("price")
        if not pname or not price or pname.lower() in ("yes", "no"):
            # Manche APIs liefern "Yes" für Card-Markt — dann steckt Name in description
            if o.get("description"):
                pname = o["description"].strip()
            else:
                continue
        if not pname or not price:
            continue
        out[pname] = {"name": pname, "odds": float(price), "bookmaker": book_key}
    return out


def _parse_ou_market(market: dict, book_key: str) -> dict[str, dict]:
    """
    Parst einen 'ou'-Markt (Player Shots, Shots on Target).
    Outcome-Struktur: {description=player_name, name="Over"|"Under", price, point=line}
    """
    out: dict[str, dict] = {}
    # Erst nach (player, line) gruppieren
    grouped: dict[tuple[str, float], dict] = {}
    for o in market.get("outcomes", []):
        pname = (o.get("description") or "").strip()
        side  = (o.get("name") or "").strip().lower()
        price = o.get("price")
        line  = o.get("point")
        if not pname or not price or line is None or side not in ("over", "under"):
            continue
        try:
            line_f = float(line)
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        gkey = (pname, line_f)
        if gkey not in grouped:
            grouped[gkey] = {"name": pname, "line": line_f, "bookmaker": book_key}
        grouped[gkey][side] = price_f

    # Pro Spieler: nimm die Hauptlinie (die mit beiden Seiten + niedrigster Spread)
    by_player: dict[str, dict] = {}
    for (pname, line_f), entry in grouped.items():
        if "over" not in entry or "under" not in entry:
            continue
        if pname not in by_player:
            by_player[pname] = entry
        else:
            # Wähle Linie näher an 1.85/2.0 (Standard-Markt-Liquidität)
            existing_line = by_player[pname]["line"]
            if abs(line_f - 1.5) < abs(existing_line - 1.5):
                by_player[pname] = entry
    return by_player


def fetch_event_player_props(event_id: str, sport_key: str) -> dict:
    """
    Fetcht alle 6 Player-Märkte für ein Event.
    Gibt dict zurück mit Schlüsseln "anytime_scorer" usw.
    """
    path = (f"/v4/sports/{sport_key}/events/{event_id}/odds"
            f"?apiKey={ODDS_KEY}"
            f"&regions=eu,uk,us"
            f"&markets={API_KEYS_CSV}"
            f"&oddsFormat=decimal")
    data = _odds_get(path)
    if not data or not isinstance(data, dict):
        return {}

    # Pro internem Markt: dict[player_name → entry]
    # Bei Konflikten: bevorzugte Bookie gewinnt
    results: dict[str, dict[str, dict]] = {m["key"]: {} for m in PLAYER_MARKETS}

    for bk in data.get("bookmakers", []):
        bk_key = bk.get("key", "")
        bk_prio = _book_priority(bk_key)
        for mkt in bk.get("markets", []):
            api_key = mkt.get("key")
            if api_key not in API_TO_INTERNAL:
                continue
            meta = API_TO_INTERNAL[api_key]
            ikey = meta["key"]
            if meta["type"] == "single":
                new_entries = _parse_single_market(mkt, bk_key)
            else:
                new_entries = _parse_ou_market(mkt, bk_key)

            for pname, entry in new_entries.items():
                if pname not in results[ikey]:
                    results[ikey][pname] = entry
                else:
                    existing_prio = _book_priority(results[ikey][pname].get("bookmaker", ""))
                    if bk_prio < existing_prio:
                        results[ikey][pname] = entry

    # Auf Listen sortieren
    out: dict[str, list[dict]] = {}
    for ikey, entries in results.items():
        if not entries:
            continue
        items = list(entries.values())
        # Single-Märkte: nach odds aufsteigend (Favoriten oben)
        # OU-Märkte: nach line absteigend (höchste Erwartung oben)
        if "line" in items[0]:
            items.sort(key=lambda x: -x["line"])
        else:
            items.sort(key=lambda x: x["odds"])
        out[ikey] = items

    return out


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"⚽  fetch_wm_player_props.py — WM 2026 Player Props (Multi-Markt)")
    print(f"    Key: {'✅' if ODDS_KEY else '❌'} | Fenster: +{DAYS_AHEAD} Tage")
    print(f"    Märkte: {', '.join(m['key'] for m in PLAYER_MARKETS)}\n")

    if not ODDS_KEY:
        print("  ❌ ODDS_API_KEY nicht gesetzt")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    props_out: dict = {}
    if PROPS_FILE.exists():
        with open(PROPS_FILE, encoding="utf-8") as f:
            try:
                props_out = json.load(f)
            except json.JSONDecodeError:
                props_out = {}

    sport_key = _find_sport_key()
    if not sport_key:
        print("  ℹ️  WM noch nicht in TheOddsAPI — kein Fetch")
        # Trotzdem leeres File schreiben damit Renderer/Pipeline existiert
        if not PROPS_FILE.exists():
            PROPS_FILE.write_text("{}", encoding="utf-8")
        return

    events_data = _odds_get(f"/v4/sports/{sport_key}/events?apiKey={ODDS_KEY}")
    if not events_data or not isinstance(events_data, list):
        print("  ⚠️  Keine Events gefunden")
        return

    print(f"  {len(events_data)} Events in TheOddsAPI\n")

    cutoff = (datetime.now(timezone.utc) + timedelta(days=DAYS_AHEAD)).date()

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
        # Leeres File anlegen falls noch nicht da
        if not PROPS_FILE.exists():
            PROPS_FILE.write_text("{}", encoding="utf-8")
        return

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
        key_rev = f"{a_id}-{h_id}"
        if key_rev in fixture_map:
            matched_events.append({"odds_key": key_rev, "event_id": ev["id"], "fx": fixture_map[key_rev]})

    print(f"  {len(matched_events)} Matches im Fenster gefunden\n")

    fetched = 0
    total_props = 0
    for ev in matched_events:
        odds_key = ev["odds_key"]
        event_id = ev["event_id"]
        fx       = ev["fx"]

        print(f"  🔍 {odds_key} (Event {event_id[:8]}…)…", end="", flush=True)
        markets = fetch_event_player_props(event_id, sport_key)
        time.sleep(1.0)

        if not markets:
            print(" ○ keine Props verfügbar")
            continue

        props_out[odds_key] = {
            "eventId":   event_id,
            "date":      fx["date"],
            "updatedAt": now_iso,
            "markets":   markets,
        }
        n_entries = sum(len(v) for v in markets.values())
        total_props += n_entries
        fetched += 1
        active = [k for k, v in markets.items() if v]
        print(f" ✅ {len(active)} Märkte / {n_entries} Outcomes")
        for mkey in active:
            top = markets[mkey][:3]
            print(f"     [{mkey}]")
            for p in top:
                if "line" in p:
                    print(f"       {p['name']}: O{p['line']} @{p['over']} / U @{p['under']} [{p['bookmaker']}]")
                else:
                    print(f"       {p['name']}: @{p['odds']} [{p['bookmaker']}]")

    # Alte Einträge aufräumen (älter als 7 Tage)
    cutoff_old = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    purged = 0
    for key in list(props_out.keys()):
        try:
            d = datetime.strptime(props_out[key].get("date", ""), "%Y-%m-%d").date()
            if d < cutoff_old:
                del props_out[key]
                purged += 1
        except Exception:
            pass

    with open(PROPS_FILE, "w", encoding="utf-8") as f:
        json.dump(props_out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {fetched} Events fetched, {total_props} Outcomes total → {PROPS_FILE.name}")
    if purged:
        print(f"   🧹 {purged} alte Einträge entfernt")
    if fetched == 0:
        print("   ℹ️  Props erscheinen typischerweise 1-3 Tage vor dem Spiel")


if __name__ == "__main__":
    main()
