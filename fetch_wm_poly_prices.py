#!/usr/bin/env python3
"""
fetch_wm_poly_prices.py
Fetches all WM 2026 Polymarket prices from the Gamma API.
  - Moneyline (1X2) via series_slug=soccer-fifwc
  - Totals (O/U) + BTTS + Spreads via {slug}-more-markets child events
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
GAMMA_SLUG_URL = "https://gamma-api.polymarket.com/events?slug={slug}&markets=true"

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


def fetch_more_markets(slug: str) -> dict:
    """
    Fetch the {slug}-more-markets child event and return extracted prices.
    Returns dict with keys: totals (by line), btts, spreads. Empty dict on failure.
    """
    mm_slug = f"{slug}-more-markets"
    url = GAMMA_SLUG_URL.format(slug=mm_slug)
    try:
        data = fetch_gamma(url)
    except Exception:
        return {}

    if not data or not isinstance(data, list):
        return {}

    event = data[0]
    result = {"totals": {}, "btts": None, "btts_no": None, "spreads": {}}

    for m in event.get("markets", []):
        smt    = m.get("sportsMarketType", "")
        line   = m.get("line")
        prices = json.loads(m.get("outcomePrices", "[]") or "[]")
        if len(prices) < 2:
            continue
        over_price = float(prices[0])
        under_price = float(prices[1])

        if smt == "totals" and line is not None:
            result["totals"][float(line)] = {
                "over":  round(over_price, 4),
                "under": round(under_price, 4),
            }
        elif smt == "both_teams_to_score":
            result["btts"]    = round(over_price, 4)   # Yes price
            result["btts_no"] = round(under_price, 4)  # No price

    return result


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

    # ── Filter: only process pure moneyline events (negRisk=true, no suffix in slug) ──
    # The Gamma batch API can return exact-score, halftime-result, more-markets
    # child events mixed in. We only want the root 1X2 moneyline events.
    SLUG_SUFFIXES_TO_SKIP = (
        "-exact-score", "-halftime-result", "-more-markets",
        "-exact-goals", "-both-teams-to-score",
    )

    for ev in events:
        slug_raw = ev.get("slug", "")
        if any(slug_raw.endswith(sfx) for sfx in SLUG_SUFFIXES_TO_SKIP):
            print(f"  SKIP non-moneyline event: {slug_raw}")
            skip += 1
            continue
        # Also skip events without negRisk (= they're child/more-markets events)
        if ev.get("negRisk") is False:
            print(f"  SKIP negRisk=False event: {slug_raw}")
            skip += 1
            continue

        result = parse_event(ev)
        if result:
            key  = f"{result['homeId']}-{result['awayId']}"
            slug = result["slug"]

            # Fetch more-markets (O/U, BTTS, Spreads) — separate child event
            mm = fetch_more_markets(slug)
            totals = mm.get("totals", {})

            # Standard soccer totals — O/U 2.5 is the reference market
            result["poly_o25"]    = totals.get(2.5, {}).get("over")
            result["poly_u25"]    = totals.get(2.5, {}).get("under")
            result["poly_o15"]    = totals.get(1.5, {}).get("over")
            result["poly_u15"]    = totals.get(1.5, {}).get("under")
            result["poly_o35"]    = totals.get(3.5, {}).get("over")
            result["poly_u35"]    = totals.get(3.5, {}).get("under")
            result["poly_btts"]   = mm.get("btts")
            result["poly_btts_no"] = mm.get("btts_no")
            result["moreMktSlug"] = f"{slug}-more-markets" if mm else None

            prices[key] = result
            ou_str = f" | O2.5={result['poly_o25']}" if result["poly_o25"] else ""
            print(f"  ✓ {result['homeName']} vs {result['awayName']}  [{key}]"
                  f"  hw={result['hw']:.3f} dr={result['dr']} aw={result['aw']:.3f}"
                  f"  vol=${result['vol']:,.0f}{ou_str}")
            ok += 1
        else:
            skip += 1

    # ── Patch wm2026-data.json + compute CLV Radar ───────────────────────────
    clv_radar = []
    wm = None

    if ok > 0 and os.path.exists(WM_FILE):
        with open(WM_FILE, encoding="utf-8") as f:
            wm = json.load(f)

        wm_odds = wm.setdefault("odds", {})

        # Build team name lookup: id → German name
        team_names: dict[str, str] = {}
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                team_names[t["id"]] = t.get("name", t["id"])

        patched = 0
        for key, p in prices.items():
            existing = wm_odds.get(key, {})
            existing["poly_hw"]   = p["hw"]
            existing["poly_dr"]   = p["dr"]
            existing["poly_aw"]   = p["aw"]
            existing["poly_vol"]  = p["vol"]
            existing["poly_slug"] = p["slug"]
            wm_odds[key] = existing
            patched += 1

            # ── CLV Radar: Pinnacle fair odds vs Polymarket price ─────────────
            # Edge = pinnacle_devigged_prob - polymarket_prob (in pp)
            # Positive edge → Polymarket underpriced vs sharp Pinnacle line
            pinn_hw = existing.get("hw")
            pinn_dr = existing.get("dr")
            pinn_aw = existing.get("aw")

            if pinn_hw and pinn_dr and pinn_aw and pinn_hw > 1:
                margin = 1/pinn_hw + 1/pinn_dr + 1/pinn_aw
                fair_hw = (1/pinn_hw) / margin
                fair_dr = (1/pinn_dr) / margin
                fair_aw = (1/pinn_aw) / margin

                home_id, away_id = key.split("-", 1)
                opportunities = []

                for label, mkey, fair, poly in [
                    ("Heimsieg",      "hw", fair_hw, p["hw"]),
                    ("Unentschieden", "dr", fair_dr, p.get("dr")),
                    ("Auswärtssieg",  "aw", fair_aw, p["aw"]),
                ]:
                    if poly is None:
                        continue
                    edge_pp = round((fair - poly) * 100, 1)
                    if edge_pp > 0:   # Any positive edge vs Pinnacle fair
                        opportunities.append({
                            "market":     label,
                            "priceKey":   mkey,
                            "polyPrice":  round(poly, 4),
                            "polyOdds":   round(1 / poly, 2) if poly > 0 else None,
                            "pinnFair":   round(fair, 4),
                            "pinnOdds":   round(pinn_hw if mkey == "hw" else
                                               pinn_dr if mkey == "dr" else pinn_aw, 2),
                            "edgePP":     edge_pp,
                        })

                if opportunities:
                    # Sort by edge descending
                    opportunities.sort(key=lambda x: -x["edgePP"])
                    clv_radar.append({
                        "key":       key,
                        "homeId":    home_id,
                        "awayId":    away_id,
                        "home":      team_names.get(home_id, p["homeName"]),
                        "away":      team_names.get(away_id, p["awayName"]),
                        "homeName":  p["homeName"],
                        "awayName":  p["awayName"],
                        "date":      p["date"],
                        "slug":      p["slug"],
                        "vol":       p["vol"],
                        "opportunities": opportunities,
                        # Best edge of this fixture
                        "bestEdge":  opportunities[0]["edgePP"],
                    })

        # Sort radar by best edge descending
        clv_radar.sort(key=lambda x: -x["bestEdge"])

    # ── Apply entry filters to CLV Radar ─────────────────────────────────────
    # Only include opportunities worth trading:
    #   Edge ≥ 5pp       — below this it's market noise / Pinnacle margin artifact
    #   Poly odds ≥ 1.25 — price < 0.80 (don't trade extreme favorites, no upside)
    #   Volume ≥ $5,000  — ensure liquidity for entry AND exit
    MIN_EDGE_PP    = 5.0
    MIN_POLY_ODDS  = 1.25   # polyPrice < 0.80
    MIN_VOLUME     = 5_000

    for fix in clv_radar:
        fix["opportunities"] = [
            o for o in fix["opportunities"]
            if (o["edgePP"] >= MIN_EDGE_PP
                and (o["polyOdds"] or 0) >= MIN_POLY_ODDS
                and fix.get("vol", 0) >= MIN_VOLUME)
        ]
        fix["opportunities"].sort(key=lambda x: -x["edgePP"])
        if fix["opportunities"]:
            fix["bestEdge"] = fix["opportunities"][0]["edgePP"]

    clv_radar = [f for f in clv_radar if f["opportunities"]]
    clv_radar.sort(key=lambda x: -x["bestEdge"])

    print(f"  CLV Radar (nach Filter): {len(clv_radar)} handelbare Fixtures "
          f"(Edge≥{MIN_EDGE_PP}pp, Odds≥{MIN_POLY_ODDS}, Vol≥${MIN_VOLUME:,.0f})")

    if wm is not None:
        with open(WM_FILE, "w", encoding="utf-8") as f:
            json.dump(wm, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  Patched {patched} fixtures in wm2026-data.json (poly_hw/dr/aw fields)")
        print(f"  CLV Radar: {len(clv_radar)} fixtures with Pinnacle edge vs Polymarket")

    # ── Build allFixtures (all 72 games, Pinnacle + Poly + Edge — for dashboard table) ──
    # Unlike clvRadar (filtered ≥5pp), allFixtures shows everything so the
    # dashboard can apply its own filters and display all markets.
    all_fixtures: list[dict] = []

    wm_odds_ref = wm.get("odds", {}) if wm is not None else {}
    team_names_ref: dict[str, str] = {}
    if wm is not None:
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                team_names_ref[t["id"]] = t.get("name", t["id"])

    # ── Build picks lookup: {match_key: {market_label: {verdict, edgePP, dataQuality}}} ──
    # Used to enrich allFixtures with pick verdicts so auto-trigger respects pick logic.
    picks_lookup: dict[str, dict] = {}
    if wm is not None:
        for match_key, pick_list in wm.get("picks", {}).items():
            picks_lookup[match_key] = {}
            for pk in pick_list:
                mkt = pk.get("market", "")
                picks_lookup[match_key][mkt] = {
                    "verdict":     pk.get("verdict"),
                    "edgePP":      pk.get("edgePP"),
                    "dataQuality": pk.get("dataQuality", "elo_only"),
                }

    # Market label → edge_key / allFixtures field name
    _MARKET_TO_FIELD = {
        "Heimsieg":       "hw",
        "Unentschieden":  "dr",
        "Auswärtssieg":   "aw",
        "Over 2.5 Tore":  "o25",
        "Under 2.5 Tore": "u25",
        "Beide Teams treffen": "btts",
    }

    for key, p in prices.items():
        home_id, away_id = key.split("-", 1)
        pinn = wm_odds_ref.get(key, {})

        pinn_hw  = pinn.get("hw")
        pinn_dr  = pinn.get("dr")
        pinn_aw  = pinn.get("aw")
        pinn_o25 = pinn.get("o25")   # available once TheOddsAPI lists WM totals
        pinn_u25 = pinn.get("u25")

        fair_hw = fair_dr = fair_aw = None
        edge_hw = edge_dr = edge_aw = None
        best_edge      = None
        best_edge_key  = None

        if pinn_hw and pinn_dr and pinn_aw and pinn_hw > 1:
            margin  = 1/pinn_hw + 1/pinn_dr + 1/pinn_aw
            fair_hw = round((1/pinn_hw) / margin, 4)
            fair_dr = round((1/pinn_dr) / margin, 4)
            fair_aw = round((1/pinn_aw) / margin, 4)
            edge_hw = round((fair_hw - p["hw"]) * 100, 1)
            edge_dr = round((fair_dr - (p["dr"] or 0)) * 100, 1) if p["dr"] else None
            edge_aw = round((fair_aw - p["aw"]) * 100, 1)
            # Best positive edge across outcomes
            edges = {
                "hw": edge_hw,
                "dr": edge_dr,
                "aw": edge_aw,
            }
            pos_edges = {k: v for k, v in edges.items() if v is not None and v > 0}
            if pos_edges:
                best_edge_key = max(pos_edges, key=pos_edges.get)
                best_edge     = pos_edges[best_edge_key]

        # ── O/U Pinnacle edge vs Polymarket (when pinn_o25 available) ──────────
        poly_o25   = p.get("poly_o25")
        poly_u25   = p.get("poly_u25")
        edge_o25   = None
        edge_u25   = None
        fair_o25   = None
        fair_u25   = None

        if pinn_o25 and pinn_u25 and pinn_o25 > 1 and poly_o25:
            ou_margin  = 1/pinn_o25 + 1/pinn_u25
            fair_o25   = round((1/pinn_o25) / ou_margin, 4)
            fair_u25   = round((1/pinn_u25) / ou_margin, 4)
            edge_o25   = round((fair_o25 - poly_o25) * 100, 1)
            edge_u25   = round((fair_u25 - (poly_u25 or 0)) * 100, 1) if poly_u25 else None

        all_fixtures.append({
            "key":          key,
            "homeId":       home_id,
            "awayId":       away_id,
            "home":         team_names_ref.get(home_id, p["homeName"]),
            "away":         team_names_ref.get(away_id, p["awayName"]),
            "homeName":     p["homeName"],
            "awayName":     p["awayName"],
            "date":         p["date"],
            "slug":         p["slug"],
            "moreMktSlug":  p.get("moreMktSlug"),
            "vol":          round(p["vol"], 0),
            # Polymarket 1X2 (probability 0-1, convert to decimal odds with 1/p)
            "poly_hw":      p["hw"],
            "poly_dr":      p.get("dr"),
            "poly_aw":      p["aw"],
            # Polymarket O/U + BTTS (from -more-markets child event)
            "poly_o25":     poly_o25,
            "poly_u25":     poly_u25,
            "poly_o15":     p.get("poly_o15"),
            "poly_u15":     p.get("poly_u15"),
            "poly_o35":     p.get("poly_o35"),
            "poly_u35":     p.get("poly_u35"),
            "poly_btts":    p.get("poly_btts"),
            "poly_btts_no": p.get("poly_btts_no"),
            # Pinnacle 1X2 (decimal odds, e.g. 1.85)
            "pinn_hw":      pinn_hw,
            "pinn_dr":      pinn_dr,
            "pinn_aw":      pinn_aw,
            # Pinnacle O/U reference (when TheOddsAPI provides WM totals)
            "pinn_o25":     pinn_o25,
            "pinn_u25":     pinn_u25,
            # Pinnacle devigged fair probabilities (1X2)
            "fair_hw":      fair_hw,
            "fair_dr":      fair_dr,
            "fair_aw":      fair_aw,
            # Pinnacle devigged fair probabilities (O/U)
            "fair_o25":     fair_o25,
            "fair_u25":     fair_u25,
            # Edge per outcome in percentage points (positive = Poly underpriced)
            "edge_hw":      edge_hw,
            "edge_dr":      edge_dr,
            "edge_aw":      edge_aw,
            "edge_o25":     edge_o25,
            "edge_u25":     edge_u25,
            # Best positive edge of this fixture
            "bestEdge":     best_edge,
            "bestEdgeKey":  best_edge_key,
            "hasPinnacle":  bool(pinn_hw),
            "hasMoreMarkets": bool(p.get("poly_o25")),
            # ── Pick verdicts from generate_wm_picks.py ─────────────────────────
            # verdict_hw/dr/aw/o25/u25: "BET" | "ABWÄGEN" | "SKIP" | null
            # auto_wm_poly_trigger.py filters to BET/ABWÄGEN only
            **{
                f"verdict_{field}": picks_lookup.get(key, {}).get(mkt_label, {}).get("verdict")
                for mkt_label, field in _MARKET_TO_FIELD.items()
                if field in ("hw", "dr", "aw", "o25", "u25")
            },
            "dataQuality": next(
                (v.get("dataQuality") for v in picks_lookup.get(key, {}).values()), "elo_only"
            ),
        })

    # Sort: fixtures with positive edge first (desc), then by date
    all_fixtures.sort(key=lambda x: (
        -(x["bestEdge"] or -999),
        x["date"] or ""
    ))
    n_pinn = sum(1 for f in all_fixtures if f['hasPinnacle'])
    n_edge = sum(1 for f in all_fixtures if (f['bestEdge'] or 0) >= 3)
    n_ou   = sum(1 for f in all_fixtures if f.get('poly_o25'))
    n_btts = sum(1 for f in all_fixtures if f.get('poly_btts'))
    print(f"  allFixtures: {len(all_fixtures)} total"
          f" | {n_pinn} with Pinnacle | edge≥3pp: {n_edge}"
          f" | O/U 2.5: {n_ou} | BTTS: {n_btts}")

    # ── Write output JSON ─────────────────────────────────────────────────────
    out = {
        "prices":      prices,
        "clvRadar":    clv_radar,    # Filtered ≥5pp — for quick radar view
        "allFixtures": all_fixtures, # All 72 games — for full dashboard table
        "count":       ok,
        "generatedAt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {ok} matches written → wm_poly_prices.json  ({skip} skipped)")


if __name__ == "__main__":
    main()
