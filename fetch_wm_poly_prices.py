#!/usr/bin/env python3
"""
fetch_wm_poly_prices.py
Fetches all 72 WM 2026 Moneyline prices from the Polymarket Gamma API.
Output: wm_poly_prices.json  — keyed by "{HOME_ID}-{AWAY_ID}"

Runs daily via GitHub Action to keep Polymarket prices current.
No API key required — Gamma API is public.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_FILE  = os.path.join(BASE, "wm_poly_prices.json")
WM_FILE   = os.path.join(BASE, "wm2026-data.json")

GAMMA_URL = (
    "https://gamma-api.polymarket.com/events"
    "?series_slug=soccer-fifwc&limit=100&active=true"
)

# ── Polymarket English team name → our WM team ID ─────────────────────────────
POLY_NAME_TO_ID = {
    "Germany":             "GER",
    "Curaçao":             "CUW",
    "Curacao":             "CUW",
    "Mexico":              "MEX",
    "South Africa":        "ZAF",
    "Korea Republic":      "KOR",
    "Czechia":             "CZE",
    "Czech Republic":      "CZE",
    "Canada":              "CAN",
    "Bosnia-Herzegovina":  "BIH",
    "Bosnia Herzegovina":  "BIH",
    "United States":       "USA",
    "USA":                 "USA",
    "Paraguay":            "PRY",
    "Qatar":               "QAT",
    "Switzerland":         "SUI",
    "Brazil":              "BRA",
    "Morocco":             "MAR",
    "Haiti":               "HTI",
    "Scotland":            "SCO",
    "Australia":           "AUS",
    "Türkiye":             "TUR",
    "Turkey":              "TUR",
    "Netherlands":         "NED",
    "Japan":               "JPN",
    "Côte d'Ivoire":       "CIV",
    "Cote d'Ivoire":       "CIV",
    "Ivory Coast":         "CIV",
    "Ecuador":             "ECU",
    "Sweden":              "SWE",
    "Tunisia":             "TUN",
    "Spain":               "ESP",
    "Cabo Verde":          "CPV",
    "Cape Verde":          "CPV",
    "Belgium":             "BEL",
    "Egypt":               "EGY",
    "Saudi Arabia":        "SAU",
    "Uruguay":             "URU",
    "Argentina":           "ARG",
    "France":              "FRA",
    "England":             "ENG",
    "Portugal":            "POR",
    "Algeria":             "DZA",
    "DR Congo":            "COD",
    "Democratic Republic of Congo": "COD",
    "Croatia":             "CRO",
    "Norway":              "NOR",
    "New Zealand":         "NZL",
    "Iran":                "IRN",
    "IR Iran":             "IRN",
    "Iraq":                "IRQ",
    "Jordan":              "JOR",
    "Ghana":               "GHA",
    "Senegal":             "SEN",
    "Colombia":            "COL",
    "Panama":              "PAN",
    "Uzbekistan":          "UZB",
    "Austria":             "AUT",
    "Indonesia":           "IDN",
}


def fetch_gamma(url: str) -> list:
    headers = {
        "User-Agent": "BetEdge/1.0 (+https://github.com/blummabet)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        raise
    except urllib.error.URLError as e:
        print(f"  URL error: {e.reason}")
        raise


def resolve_team_id(name: str) -> str | None:
    """Map Polymarket team name → our WM team ID. Tries exact then stripped."""
    tid = POLY_NAME_TO_ID.get(name)
    if tid:
        return tid
    # Try stripping diacritics / trailing whitespace
    stripped = name.strip()
    tid = POLY_NAME_TO_ID.get(stripped)
    if tid:
        return tid
    # Partial match (last resort)
    name_lower = name.lower()
    for poly_name, wm_id in POLY_NAME_TO_ID.items():
        if poly_name.lower() in name_lower or name_lower in poly_name.lower():
            return wm_id
    return None


def parse_event(event: dict) -> dict | None:
    """
    Parse one Polymarket event into our format.
    Returns dict or None if parsing fails.
    """
    slug  = event.get("slug", "")
    title = event.get("title", "")
    date  = event.get("eventDate", "")
    vol   = event.get("volume", 0)

    # Identify home and away teams from teams array
    teams_arr = event.get("teams", [])
    if len(teams_arr) < 2:
        print(f"  SKIP {slug}: only {len(teams_arr)} team(s)")
        return None

    home_name = teams_arr[0].get("name", "")
    away_name = teams_arr[1].get("name", "")
    home_id   = resolve_team_id(home_name)
    away_id   = resolve_team_id(away_name)

    if not home_id or not away_id:
        print(f"  SKIP {slug}: unresolved team(s) '{home_name}' → {home_id}, '{away_name}' → {away_id}")
        return None

    key = f"{home_id}-{away_id}"

    # Parse markets
    hw = dr = aw = None
    hw_tokens = dr_tokens = aw_tokens = []
    neg_risk_market_id = event.get("negRiskMarketID")

    for m in event.get("markets", []):
        gt     = m.get("groupItemTitle", "")
        prices = json.loads(m.get("outcomePrices", "[]") or "[]")
        tokens = json.loads(m.get("clobTokenIds", "[]") or "[]")
        yes_price = float(prices[0]) if prices else None

        if yes_price is None:
            continue

        gt_lower = gt.lower()
        if "draw" in gt_lower:
            dr = yes_price
            dr_tokens = tokens
        elif resolve_team_id(gt) == home_id:
            hw = yes_price
            hw_tokens = tokens
        elif resolve_team_id(gt) == away_id:
            aw = yes_price
            aw_tokens = tokens
        else:
            # Fallback: try by groupItemThreshold (0=home,1=draw,2=away) if present
            threshold = str(m.get("groupItemThreshold", ""))
            if threshold == "0":
                hw = yes_price; hw_tokens = tokens
            elif threshold == "1":
                dr = yes_price; dr_tokens = tokens
            elif threshold == "2":
                aw = yes_price; aw_tokens = tokens

    if hw is None or aw is None:
        print(f"  WARN {slug}: missing hw={hw} aw={aw} dr={dr}")
        return None

    return {
        "homeId":    home_id,
        "awayId":    away_id,
        "homeName":  home_name,
        "awayName":  away_name,
        "hw":        round(hw, 4),
        "dr":        round(dr, 4) if dr is not None else None,
        "aw":        round(aw, 4),
        "slug":      slug,
        "title":     title,
        "date":      date,
        "vol":       round(vol, 2),
        "negRiskMarketId": neg_risk_market_id,
        "hwTokens":  hw_tokens,
        "drTokens":  dr_tokens,
        "awTokens":  aw_tokens,
    }


def main():
    print("=== fetch_wm_poly_prices.py ===")

    print(f"  Fetching {GAMMA_URL}")
    try:
        events = fetch_gamma(GAMMA_URL)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print(f"  {len(events)} events received from Gamma API")

    prices: dict[str, dict] = {}
    ok = 0
    skip = 0

    for ev in events:
        result = parse_event(ev)
        if result:
            key = f"{result['homeId']}-{result['awayId']}"
            prices[key] = result
            print(f"  ✓ {result['homeName']} vs {result['awayName']}  [{key}]"
                  f"  hw={result['hw']:.3f} dr={result['dr']} aw={result['aw']:.3f}"
                  f"  vol=${result['vol']:,.0f}")
            ok += 1
        else:
            skip += 1

    # Write output
    out = {
        "prices":      prices,
        "count":       ok,
        "generatedAt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {ok} matches written → wm_poly_prices.json  ({skip} skipped)")

    # ── Patch wm2026-data.json so pick generator sees Polymarket prices ────────
    if ok == 0:
        print("  No prices to patch into wm2026-data.json")
        return

    if not os.path.exists(WM_FILE):
        print("  wm2026-data.json not found — skipping patch")
        return

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    patched = 0
    wm_odds = wm.setdefault("odds", {})
    for key, p in prices.items():
        existing = wm_odds.get(key, {})
        # Only set hw/dr/aw from Polymarket if no bookmaker odds present yet
        # (bookmaker odds = odds_open is set from Pinnacle via TheOddsAPI)
        # Keep bookmaker odds as primary; store Poly prices separately
        existing["poly_hw"] = p["hw"]
        existing["poly_dr"] = p["dr"]
        existing["poly_aw"] = p["aw"]
        existing["poly_vol"] = p["vol"]
        existing["poly_slug"] = p["slug"]
        wm_odds[key] = existing
        patched += 1

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, separators=(",", ":"))

    print(f"  Patched {patched} fixtures in wm2026-data.json (poly_hw/dr/aw fields)")


if __name__ == "__main__":
    main()
