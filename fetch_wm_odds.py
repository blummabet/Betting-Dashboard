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
    Returns {"_oc": {...}, "bookmaker": str, "_public_oc": {...}, "_public_bk": str}
    Wenn pinnacle gewählt wird, wird bet365 als public-Bookie zusätzlich extrahiert
    (für Public-vs-Sharp Bias-Berechnung).
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

    # Public-Proxy: bet365 wenn vorhanden, sonst williamhill/unibet/betfair
    PUBLIC_PRIO = ["bet365", "williamhill", "unibet", "betfair"]
    public_oc = None
    public_bk = None
    for pp in PUBLIC_PRIO:
        if pp in candidates:
            public_oc = candidates[pp]
            public_bk = pp
            break

    # Pick preferred bookmaker (Pinnacle als Sharp)
    for prio in our_book_prio:
        if prio in candidates:
            oc = candidates[prio]
            # Public-Bookie sollte nicht derselbe wie Sharp sein
            if public_bk == prio:
                public_oc = None
                public_bk = None
                for pp in PUBLIC_PRIO:
                    if pp != prio and pp in candidates:
                        public_oc = candidates[pp]
                        public_bk = pp
                        break
            return {
                "_oc": oc, "bookmaker": prio,
                "_public_oc": public_oc, "_public_bk": public_bk,
            }
    # Fall back to any
    for bk_key, oc in candidates.items():
        return {"_oc": oc, "bookmaker": bk_key, "_public_oc": None, "_public_bk": None}
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

    out = {
        "hw": round(home_win, 3),
        "dr": round(draw, 3) if draw else None,
        "aw": round(away_win, 3),
        "bookmaker": bk_result["bookmaker"],
    }

    # Public-Bookie (bet365 oder Fallback) für Public-vs-Sharp-Vergleich
    public_oc = bk_result.get("_public_oc")
    if public_oc:
        p_home = p_draw = p_away = None
        for name, price in public_oc.items():
            name_id = _name_to_id(name)
            if name_id == home_id:
                p_home = price
            elif name_id == away_id:
                p_away = price
            elif name.lower() in ("draw", "tie", "x"):
                p_draw = price
        if p_draw is None and len(public_oc) == 3:
            prices = sorted(public_oc.values())
            remaining = [p for p in prices if p != p_home and p != p_away]
            if remaining:
                p_draw = remaining[0]
        if p_home is not None and p_away is not None:
            out["public_hw"] = round(p_home, 3)
            out["public_dr"] = round(p_draw, 3) if p_draw else None
            out["public_aw"] = round(p_away, 3)
            out["public_bookmaker"] = bk_result["_public_bk"]

    return out


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


def _extract_totals_btts(bookmakers: list, our_book_prio: list, home_name: str = "", away_name: str = "") -> dict:
    """
    Extract Over/Under (1.5/2.5/3.5), BTTS, Corner totals, Asian Handicap und Double Chance.
    Prefers same bookmaker priority as h2h.
    Returns {o15, o25, o35, u15, u25, u35, bttsY, bttsN, cornerLine, cOver, cUnder,
             dc1X, dc12, dcX2, ahH_n050, ahA_p050, ahH_n075, ahA_p075, ahH_n100, ahA_p100}
    """
    # totals lines: bk_key → {line: (over, under)}
    totals_lines_by_bk: dict[str, dict] = {}
    btts_cands:   dict[str, tuple] = {}
    corner_cands: dict[str, tuple] = {}
    dc_cands:     dict[str, tuple] = {}    # bk_key → (1X, 12, X2)
    ah_lines_by_bk: dict[str, dict] = {}   # bk_key → {line: (home_price, away_price)}

    CORNER_PREFERRED_LINES = [9.5, 10.5, 9.0, 10.0, 8.5, 11.5]
    home_l = (home_name or "").lower()
    away_l = (away_name or "").lower()

    for bk in bookmakers:
        bk_key = bk.get("key", "")
        for market in bk.get("markets", []):
            mkey = market.get("key", "")

            if mkey in ("totals", "alternate_totals"):
                # Sammle alle Linien
                if bk_key not in totals_lines_by_bk:
                    totals_lines_by_bk[bk_key] = {}
                for o in market.get("outcomes", []):
                    point = o.get("point")
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    if point not in totals_lines_by_bk[bk_key]:
                        totals_lines_by_bk[bk_key][point] = [None, None]
                    if name == "over":
                        totals_lines_by_bk[bk_key][point][0] = price
                    elif name == "under":
                        totals_lines_by_bk[bk_key][point][1] = price

            elif mkey in ("btts", "both_teams_to_score"):
                yes = no = None
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if price and name in ("yes", "ja"):
                        yes = price
                    elif price and name in ("no", "nein"):
                        no = price
                if yes:
                    btts_cands[bk_key] = (yes, no)

            elif mkey == "corners":
                lines: dict[float, list] = {}
                for o in market.get("outcomes", []):
                    point = o.get("point")
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    if point not in lines:
                        lines[point] = [None, None]
                    if name == "over":
                        lines[point][0] = price
                    elif name == "under":
                        lines[point][1] = price
                best_line = best_over = best_under = None
                for preferred in CORNER_PREFERRED_LINES:
                    if preferred in lines and lines[preferred][0] and lines[preferred][1]:
                        best_line, best_over, best_under = preferred, lines[preferred][0], lines[preferred][1]
                        break
                if not best_line:
                    for line, (ov, un) in sorted(lines.items()):
                        if ov and un:
                            best_line, best_over, best_under = line, ov, un
                            break
                if best_line and best_over:
                    corner_cands[bk_key] = (best_line, best_over, best_under)

            elif mkey == "double_chance":
                # Outcomes: "Home or Draw" (1X), "Away or Draw" (X2), "Home or Away" (12)
                dc_1x = dc_x2 = dc_12 = None
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if not price:
                        continue
                    has_home = home_l and home_l in name
                    has_away = away_l and away_l in name
                    has_draw = "draw" in name or "remis" in name or "unentsch" in name
                    if has_home and has_draw:
                        dc_1x = price
                    elif has_away and has_draw:
                        dc_x2 = price
                    elif has_home and has_away:
                        dc_12 = price
                if dc_1x or dc_x2 or dc_12:
                    dc_cands[bk_key] = (dc_1x, dc_12, dc_x2)

            elif mkey == "spreads":
                # Asian Handicap: jedes Outcome hat name=Team + point=Line
                if bk_key not in ah_lines_by_bk:
                    ah_lines_by_bk[bk_key] = {}
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    point = o.get("point")
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    is_home = home_l and home_l in name
                    is_away = away_l and away_l in name
                    if not is_home and not is_away:
                        continue
                    # Speichere Heim-Linie (negativ = Heim-Favorit)
                    # AH-Heim -0.5 ↔ AH-Auswärts +0.5 ist dieselbe Linie, andere Seite
                    line_key = round(point, 2) if is_home else round(-point, 2)
                    if line_key not in ah_lines_by_bk[bk_key]:
                        ah_lines_by_bk[bk_key][line_key] = [None, None]
                    if is_home:
                        ah_lines_by_bk[bk_key][line_key][0] = price
                    elif is_away:
                        ah_lines_by_bk[bk_key][line_key][1] = price

    def _pick_bk(cands: dict):
        for prio in our_book_prio:
            if prio in cands:
                return cands[prio]
        for v in cands.values():
            return v
        return None

    # Total-Linien aus bevorzugtem Bookie
    def _pick_total_line(line: float) -> tuple | None:
        for prio in our_book_prio:
            if prio in totals_lines_by_bk and line in totals_lines_by_bk[prio]:
                ov, un = totals_lines_by_bk[prio][line]
                if ov and un:
                    return (ov, un)
        for bk_data in totals_lines_by_bk.values():
            if line in bk_data and bk_data[line][0] and bk_data[line][1]:
                return tuple(bk_data[line])
        return None

    t15 = _pick_total_line(1.5)
    t25 = _pick_total_line(2.5)
    t35 = _pick_total_line(3.5)

    # AH-Linien aus bevorzugtem Bookie
    def _pick_ah(line: float) -> tuple | None:
        for prio in our_book_prio:
            if prio in ah_lines_by_bk and line in ah_lines_by_bk[prio]:
                hm, aw = ah_lines_by_bk[prio][line]
                if hm and aw:
                    return (hm, aw)
        for bk_data in ah_lines_by_bk.values():
            if line in bk_data and bk_data[line][0] and bk_data[line][1]:
                return tuple(bk_data[line])
        return None

    ah_05 = _pick_ah(-0.5)
    ah_075 = _pick_ah(-0.75)
    ah_10 = _pick_ah(-1.0)

    b = _pick_bk(btts_cands)
    c = _pick_bk(corner_cands)
    dc = _pick_bk(dc_cands)

    return {
        "o15":     round(t15[0], 3) if t15 else None,
        "u15":     round(t15[1], 3) if t15 else None,
        "o25":     round(t25[0], 3) if t25 else None,
        "u25":     round(t25[1], 3) if t25 else None,
        "o35":     round(t35[0], 3) if t35 else None,
        "u35":     round(t35[1], 3) if t35 else None,
        "bttsY":   round(b[0], 3) if b else None,
        "bttsN":   round(b[1], 3) if b and b[1] else None,
        "cornerLine": c[0] if c else None,
        "cOver":   round(c[1], 3) if c and c[1] else None,
        "cUnder":  round(c[2], 3) if c and c[2] else None,
        "dc1X":    round(dc[0], 3) if dc and dc[0] else None,
        "dc12":    round(dc[1], 3) if dc and dc[1] else None,
        "dcX2":    round(dc[2], 3) if dc and dc[2] else None,
        "ahH_n050": round(ah_05[0], 3)  if ah_05  else None,
        "ahA_p050": round(ah_05[1], 3)  if ah_05  else None,
        "ahH_n075": round(ah_075[0], 3) if ah_075 else None,
        "ahA_p075": round(ah_075[1], 3) if ah_075 else None,
        "ahH_n100": round(ah_10[0], 3)  if ah_10  else None,
        "ahA_p100": round(ah_10[1], 3)  if ah_10  else None,
    }


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

    # Build teams Elo map for sanity checks + Team-Name-Map für DC/AH-Parsing
    teams_elo:   dict[str, float] = {}
    team_names:  dict[str, str]   = {}
    for gdata in groups.values():
        for t in gdata.get("teams", []):
            if t.get("elo"):
                teams_elo[t["id"]] = t["elo"]
            if t.get("name"):
                team_names[t["id"]] = t["name"]

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

    # ── Fetch 1: h2h von Pinnacle & Co (bevorzugte Bookmaker) ───
    print(f"\n  📥  Fetching h2h odds for {sport_key}…")
    path_h2h = (f"/v4/sports/{sport_key}/odds"
                f"?apiKey={ODDS_KEY}"
                f"&regions=eu,uk"
                f"&markets=h2h"
                f"&oddsFormat=decimal"
                f"&bookmakers={','.join(BOOKMAKERS)}")
    events = odds_get(path_h2h)

    if not events or not isinstance(events, list):
        print("  ⚠️  No events returned from TheOddsAPI")
        return

    print(f"  → {len(events)} h2h events fetched")

    # ── Fetch 2: totals + btts per Event-ID ──────────────────
    # Der Batch-Endpoint (/odds?markets=totals) gibt für WM 0 Events zurück,
    # weil TheOddsAPI den WM-Totals-Batch nicht befüllt (Coverage-Lücke).
    # Lösung: per-Event-Endpoint /events/{id}/odds — gleicher Ansatz wie
    # test-cards-api.js für Cards/Corners. Pinnacle O/U ist dort verfügbar.
    # WICHTIG (Fix 04.06.2026): TheOddsAPI liefert für WM-Events leere bookmakers wenn
    # zu viele Markets in einem Call. 4 Markets pro Call ist das Limit. Daher 2 Calls:
    #   Call 1: totals,btts,double_chance,spreads (Standard + DC + AH)
    #   Call 2: alternate_totals (für O1.5/O3.5/U1.5/U3.5)
    # corners wird raus weil TheOddsAPI für WM noch keine Corner-Quoten listet.
    print(f"\n  📥  Fetching totals+btts+DC+spreads per event (Call 1/2)…")
    event_ids = [ev["id"] for ev in events if ev.get("id")]
    totals_by_id: dict[str, dict] = {}

    for i, eid in enumerate(event_ids):
        path_ev = (f"/v4/sports/{sport_key}/events/{eid}/odds"
                   f"?apiKey={ODDS_KEY}"
                   f"&regions=eu,uk,us"
                   f"&markets=totals,btts,double_chance,spreads"
                   f"&oddsFormat=decimal")
        ev_data = odds_get(path_ev)
        if isinstance(ev_data, dict) and ev_data.get("bookmakers"):
            totals_by_id[eid] = ev_data
        if i < len(event_ids) - 1:
            time.sleep(0.25)

    # ── Call 2: alternate_totals (für O1.5/O3.5/U1.5/U3.5) — mergen ──
    print(f"  📥  Fetching alternate_totals per event (Call 2/2)…")
    alt_added = 0
    for i, eid in enumerate(event_ids):
        path_alt = (f"/v4/sports/{sport_key}/events/{eid}/odds"
                    f"?apiKey={ODDS_KEY}"
                    f"&regions=eu,uk,us"
                    f"&markets=alternate_totals"
                    f"&oddsFormat=decimal")
        alt_data = odds_get(path_alt)
        if isinstance(alt_data, dict) and alt_data.get("bookmakers"):
            # Bookmaker-Markets in das Haupt-Event mergen
            existing = totals_by_id.get(eid)
            if existing:
                existing_bk_keys = {b["key"]: b for b in existing.get("bookmakers", [])}
                for new_bk in alt_data["bookmakers"]:
                    bk_key = new_bk.get("key")
                    if bk_key in existing_bk_keys:
                        # Markets in bestehendem Bookmaker anhängen
                        existing_bk_keys[bk_key]["markets"].extend(new_bk.get("markets", []))
                    else:
                        existing["bookmakers"].append(new_bk)
                alt_added += 1
            else:
                totals_by_id[eid] = alt_data
        if i < len(event_ids) - 1:
            time.sleep(0.25)
    print(f"  → alternate_totals: {alt_added} events mit zusätzlichen O/U-Linien")

    t_ok = sum(1 for v in totals_by_id.values() if v.get("bookmakers"))
    print(f"  → {len(event_ids)} events abgefragt, {t_ok} mit Totals-Daten")
    # Kein teams-Fallback nötig da wir per ID matchen
    totals_by_teams: list[dict] = []

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

        # ── Totals + BTTS: erst im selben Event suchen, dann im Totals-Fetch ──
        # Merge Bookmakers: Pinnacle-Event (h2h) + separater Totals-Fetch
        merged_bks = list(ev.get("bookmakers", []))
        # Totals-Event by ID (gleiche Event-ID falls TheOddsAPI matcht)
        if ev.get("id") and ev["id"] in totals_by_id:
            t_ev = totals_by_id[ev["id"]]
            for bk in t_ev.get("bookmakers", []):
                if not any(b.get("key") == bk.get("key") for b in merged_bks):
                    merged_bks.append(bk)
        else:
            # Fallback: Team-Namen Matching im Totals-Fetch
            for t_ev in totals_by_teams:
                t_h2h = _extract_h2h(t_ev, home_id, away_id)
                if t_h2h:
                    for bk in t_ev.get("bookmakers", []):
                        if not any(b.get("key") == bk.get("key") for b in merged_bks):
                            merged_bks.append(bk)
                    break
        # Team-Namen mitgeben für DC/AH-Outcome-Parsing
        # TheOddsAPI verwendet Klar-Namen (z.B. "Mexico", "South Africa")
        tb = _extract_totals_btts(merged_bks, BOOKMAKERS,
                                   home_name=team_names.get(home_id, ""),
                                   away_name=team_names.get(away_id, ""))

        # ── Elo sanity check: detect reversed hw/aw ──────────────────────
        # If Elo strongly favors the home team (diff > 200 pts) but market
        # has them as a big underdog (hw > 2.5× aw), the odds are reversed.
        # This happens when TheOddsAPI lists the match in the wrong direction.
        elo_h = teams_elo.get(home_id)
        elo_a = teams_elo.get(away_id)
        if elo_h and elo_a and h2h.get("hw") and h2h.get("aw"):
            elo_diff = elo_h - elo_a
            hw_raw, aw_raw = h2h["hw"], h2h["aw"]
            # Sanity-Check 1 (strikt): bei >200 Elo-Diff sollte Favorit klar im Markt sein
            # Sanity-Check 2 (mild): bei >150 Elo-Diff darf der Favorit nicht der Underdog im Markt sein
            #   Threshold: aw < 0.85 × hw bedeutet Auswärts ist klarer Markt-Favorit als Heim
            #   Bei FRA(1972)-NOR(1709) ist hw=4.28/aw=1.80 — Verhältnis 0.42 — eindeutig invertiert.
            if elo_diff > 200 and hw_raw > 2.5 * aw_raw:
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[strikt]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff > 150 and aw_raw < 0.85 * hw_raw:
                # Heimteam laut Elo deutlich stärker, aber Markt sieht Auswärts klar als Favorit
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[mild]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff < -200 and aw_raw > 2.5 * hw_raw:
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[strikt]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff < -150 and hw_raw < 0.85 * aw_raw:
                # Auswärts laut Elo deutlich stärker, aber Markt sieht Heim klar als Favorit
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[mild]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")

        existing = odds_out.get(key, {})

        # Preserve opening line (first-ever snapshot) — never overwrite
        odds_open = existing.get("odds_open")
        if not odds_open and h2h:
            odds_open = {
                "hw": h2h["hw"], "dr": h2h["dr"], "aw": h2h["aw"],
                **({"o25": tb["o25"]} if tb["o25"] else {}),
                **({"u25": tb["u25"]} if tb["u25"] else {}),
                **({"bttsY": tb["bttsY"]} if tb["bttsY"] else {}),
            }
        elif odds_open:
            # Backfill totals/btts into existing odds_open if not yet set
            if tb["o25"] and not odds_open.get("o25"):
                odds_open["o25"] = tb["o25"]
            if tb["u25"] and not odds_open.get("u25"):
                odds_open["u25"] = tb["u25"]
            if tb["bttsY"] and not odds_open.get("bttsY"):
                odds_open["bttsY"] = tb["bttsY"]

        new_entry = {
            "hw":         h2h["hw"],
            "dr":         h2h["dr"],
            "aw":         h2h["aw"],
            "bookmaker":  h2h["bookmaker"],
            "odds_open":  odds_open,
            "updatedAt":  now_iso,
        }
        # Add totals/btts if available
        for k in ("o15", "u15", "o25", "u25", "o35", "u35"):
            if tb.get(k):
                new_entry[k] = tb[k]
        if tb.get("bttsY"):
            new_entry["bttsY"] = tb["bttsY"]
            if tb.get("bttsN"):
                new_entry["bttsN"] = tb["bttsN"]
        if tb.get("cOver"):
            new_entry["cornerLine"] = tb["cornerLine"]
            new_entry["cOver"]      = tb["cOver"]
            new_entry["cUnder"]     = tb["cUnder"]
            print(f"    🟦 Corners {home_id}-{away_id}: "
                  f"O{tb['cornerLine']} {tb['cOver']} / U{tb['cornerLine']} {tb['cUnder']}")
        # Doppelte Chance
        for k in ("dc1X", "dc12", "dcX2"):
            if tb.get(k):
                new_entry[k] = tb[k]
        # Asian Handicap (alle 3 Linien wenn verfügbar)
        for k in ("ahH_n050", "ahA_p050", "ahH_n075", "ahA_p075", "ahH_n100", "ahA_p100"):
            if tb.get(k):
                new_entry[k] = tb[k]

        # ── Closing Odds einfrieren wenn Anpfiff vorbei ──────────────────────
        # CLV-Basis: die letzten Pinnacle-Odds VOR dem Anpfiff.
        # Sobald fx["date"] + fx["time"] in der Vergangenheit liegt →
        # aktuelle Odds als Closing einfrieren (einmalig, nie überschreiben).
        existing_closing = existing.get("odds_closing")
        if existing_closing:
            # Bereits eingefroren — nie überschreiben
            new_entry["odds_closing"] = existing_closing
        else:
            # Prüfen ob Anpfiff schon vorbei
            fx_date = fx.get("date", "")
            fx_time = fx.get("time", "21:00")
            if fx_date:
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    # Spiele laufen in der Zeitzone des Austragungsortes, aber für die
                    # Closing-Linie reicht UTC-Annäherung: +2h buffer (CEST / UTC+2)
                    kickoff_str = f"{fx_date}T{fx_time}:00+02:00"
                    kickoff_dt  = _dt.fromisoformat(kickoff_str)
                    now_dt      = _dt.now(_tz.utc).astimezone(kickoff_dt.tzinfo)
                    if now_dt >= kickoff_dt:
                        # Anpfiff vorbei → aktuelle Odds als Closing einfrieren
                        new_entry["odds_closing"] = {
                            "hw":  h2h["hw"],
                            "dr":  h2h["dr"],
                            "aw":  h2h["aw"],
                            **({"o25": tb["o25"]} if tb.get("o25") else {}),
                            **({"u25": tb["u25"]} if tb.get("u25") else {}),
                            **({"bttsY": tb["bttsY"]} if tb.get("bttsY") else {}),
                            "frozenAt": now_iso,
                        }
                        print(f"  🔒  Closing eingefroren: {home_id} vs {away_id}")
                except Exception:
                    pass

        odds_out[key] = new_entry
        updated += 1

        # ── Odds History Snapshot ─────────────────────────────
        snaps = history.setdefault(key, [])
        last_snap = snaps[-1] if snaps else None
        if _snap_changed(last_snap, h2h["hw"], h2h["dr"], h2h["aw"]):
            snap_entry = {
                "ts":  now_iso,
                "hw":  h2h["hw"],
                "dr":  h2h["dr"],
                "aw":  h2h["aw"],
                "bk":  h2h["bookmaker"],
            }
            if tb["o25"]:
                snap_entry["o25"]   = tb["o25"]
                snap_entry["u25"]   = tb["u25"]
            if tb["bttsY"]:
                snap_entry["bttsY"] = tb["bttsY"]
            snaps.append(snap_entry)

        # Track snapshot count + log
        if snaps and snaps[-1].get("ts") == now_iso:
            snaps_added += 1
        ou_str   = f" | O/U {tb['o25']}/{tb['u25']}" if tb["o25"] else ""
        btts_str = f" | BTTS {tb['bttsY']}" if tb["bttsY"] else ""
        home_display = TEAM_NAMES.get(home_id, [home_id])[0]
        away_display = TEAM_NAMES.get(away_id, [away_id])[0]
        print(f"  ✅  {home_display} vs {away_display}: "
              f"H {h2h['hw']} / X {h2h['dr']} / A {h2h['aw']}"
              f"{ou_str}{btts_str} [{h2h['bookmaker']}]")

    # ── Fallback-Freeze: post-kickoff Spiele die TheOddsAPI nicht mehr listet ──
    # Wenn ein Spiel bereits angepfiffen wurde und odds_closing noch nicht gesetzt ist
    # (weil TheOddsAPI das Event schon entfernt hat), frieren wir die zuletzt bekannten
    # Odds ein — gekennzeichnet mit frozenFrom: "last_known".
    freeze_count = 0
    for fx in all_fixtures:
        home_id = fx["home"]
        away_id = fx["away"]
        key     = f"{home_id}-{away_id}"
        entry   = odds_out.get(key)
        if not entry or entry.get("odds_closing"):
            continue  # kein Eintrag oder bereits eingefroren

        fx_date = fx.get("date", "")
        fx_time = fx.get("time", "21:00")
        if not fx_date:
            continue

        try:
            from datetime import datetime as _dt, timezone as _tz
            kickoff_str = f"{fx_date}T{fx_time}:00+02:00"
            kickoff_dt  = _dt.fromisoformat(kickoff_str)
            now_dt      = _dt.now(_tz.utc).astimezone(kickoff_dt.tzinfo)
            if now_dt >= kickoff_dt and entry.get("hw") and entry.get("aw"):
                entry["odds_closing"] = {
                    "hw":  entry["hw"],
                    "dr":  entry.get("dr"),
                    "aw":  entry["aw"],
                    **({"o25": entry["o25"]} if entry.get("o25") else {}),
                    **({"u25": entry["u25"]} if entry.get("u25") else {}),
                    **({"bttsY": entry["bttsY"]} if entry.get("bttsY") else {}),
                    "frozenAt":   now_iso,
                    "frozenFrom": "last_known",  # TheOddsAPI hat Event nicht mehr geliefert
                }
                freeze_count += 1
                home_display = TEAM_NAMES.get(home_id, [home_id])[0]
                away_display = TEAM_NAMES.get(away_id, [away_id])[0]
                print(f"  🔒  Fallback-Freeze (last_known): {home_display} vs {away_display}")
        except Exception:
            pass

    if freeze_count:
        print(f"   → {freeze_count} Closing(s) via Fallback eingefroren")

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
