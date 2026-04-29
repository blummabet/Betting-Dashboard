#!/usr/bin/env python3
"""
polymarket_bet.py — CocoBet Polymarket Order Placer
=====================================================
Wird via GitHub Action ausgelöst wenn der User im Dashboard auf
"Jetzt platzieren" klickt (repository_dispatch Event).

Liest Orders aus ORDERS_JSON Env-Variable, findet die passenden
CLOB Token IDs via Gamma API, platziert Market Orders via py-clob-client
und loggt Ergebnisse in picks_history.json.

Env-Variablen (werden von GitHub Action gesetzt):
    POLY_PRIVATE_KEY   — Polygon EOA private key (aus GitHub Secret)
    ORDERS_JSON        — JSON-Array der Orders (aus repository_dispatch payload)

Lokales Setup (optional, zum Testen):
    export POLY_PRIVATE_KEY=0x...
    export ORDERS_JSON='[{"home":"Bayern Munich","away":"Dortmund",...}]'
    python3 polymarket_bet.py
"""

import json
import os
import sys
import math
import time
from datetime import datetime, timezone

import requests

# ── Constants ──────────────────────────────────────────────

GAMMA_API    = "https://gamma-api.polymarket.com"
CLOB_HOST    = "https://clob.polymarket.com"
CHAIN_ID     = 137        # Polygon
STAKE_USDC   = 5.5        # €5 ≈ $5.50 USDC flat per bet
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "picks_history.json")

# Market labels → outcome keyword matching
OUTCOME_MAP = {
    "Heimsieg":       {"type": "home_win"},
    "Auswärtssieg":   {"type": "away_win"},
    "Unentschieden":  {"type": "draw"},
    "Over 2.5 Tore":  {"type": "over25"},
    "Under 2.5 Tore": {"type": "under25"},
}

# ── Gamma API helpers ───────────────────────────────────────

def gamma_search_event(home: str, away: str) -> dict | None:
    """Search Gamma API for a match event. Returns the best matching event or None."""
    keyword = f"{home} {away}"
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"keyword": keyword, "active": "true", "limit": 12},
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        print(f"  ⚠️  Gamma API error for '{keyword}': {e}")
        return None

    home_tokens = [t for t in home.lower().split() if len(t) > 3]
    away_tokens = [t for t in away.lower().split() if len(t) > 3]

    for ev in events:
        title = (ev.get("title") or "").lower()
        if any(t in title for t in home_tokens) and any(t in title for t in away_tokens):
            return ev
    return None


def find_clob_token_id(event: dict, market_label: str, home: str, away: str) -> str | None:
    """
    Find the CLOB token ID for the specific outcome in an event's markets.
    Returns the token_id string or None if not found.
    """
    mkt_info = OUTCOME_MAP.get(market_label)
    if not mkt_info:
        return None

    mkt_type = mkt_info["type"]
    is_goals = mkt_type in ("over25", "under25")
    home_first = home.lower().split()[0]
    away_first = away.lower().split()[0]

    for mkt in event.get("markets", []):
        q = (mkt.get("question") or "").lower()
        outcomes_raw    = mkt.get("outcomes") or "[]"
        clob_ids_raw    = mkt.get("clobTokenIds") or "[]"

        try:
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            clob_ids = json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
        except Exception:
            continue

        if not outcomes or len(outcomes) != len(clob_ids):
            continue

        if is_goals:
            # Only match Over/Under 2.5 goals markets
            if "2.5" not in q and "goals" not in q:
                continue

            if mkt_type == "over25":
                # Look for Yes/Over outcome
                idx = next((i for i, o in enumerate(outcomes)
                            if o.lower() in ("yes", "over") or "over" in o.lower()), None)
                if idx is not None:
                    return clob_ids[idx]

            elif mkt_type == "under25":
                # Look for No/Under outcome — usually index 1 in a Yes/No market
                idx = next((i for i, o in enumerate(outcomes)
                            if o.lower() in ("no", "under") or "under" in o.lower()), None)
                if idx is not None:
                    return clob_ids[idx]

        else:
            # 1X2 match winner — need "win" or "winner" or "match" in question
            if not any(kw in q for kw in ("win", "winner", "match")):
                continue

            if mkt_type == "home_win":
                idx = next((i for i, o in enumerate(outcomes)
                            if home_first in o.lower()), None)
                if idx is not None:
                    return clob_ids[idx]

            elif mkt_type == "away_win":
                idx = next((i for i, o in enumerate(outcomes)
                            if away_first in o.lower()), None)
                if idx is not None:
                    return clob_ids[idx]

            elif mkt_type == "draw":
                idx = next((i for i, o in enumerate(outcomes)
                            if "draw" in o.lower()), None)
                if idx is not None:
                    return clob_ids[idx]

    return None


# ── CLOB order placement ────────────────────────────────────

def place_market_order(token_id: str, amount_usdc: float, private_key: str) -> dict:
    """
    Place a market buy order on Polymarket CLOB.
    Returns dict with orderId and status.
    """
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
    except ImportError:
        print("  ❌ py-clob-client not installed. Run: pip install py-clob-client")
        sys.exit(1)

    client = ClobClient(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=0,   # EOA (non-Safe wallet)
    )

    # Derive or create API credentials (idempotent)
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)

    order_args = MarketOrderArgs(
        token_id=token_id,
        amount=amount_usdc,   # USDC amount to spend
    )
    signed_order = client.create_market_order(order_args)
    resp = client.post_order(signed_order, OrderType.FOK)  # Fill or Kill

    if resp and resp.get("success"):
        return {
            "status":  "placed",
            "orderId": resp.get("orderID") or resp.get("id") or "unknown",
            "error":   None,
        }
    else:
        err = resp.get("errorMsg") or resp.get("error") or str(resp)
        return {"status": "failed", "orderId": None, "error": err}


# ── picks_history.json logging ──────────────────────────────

def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_history(data: list) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_bet_to_history(history: list, order: dict, result: dict) -> None:
    """
    Add a polymarket bet log entry to the relevant fixture in picks_history.json.
    Falls back to appending a standalone entry if no match found.
    """
    home    = order.get("home", "")
    away    = order.get("away", "")
    market  = order.get("market", "")
    today   = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    for fixture in history:
        if fixture.get("home") == home or fixture.get("away") == away:
            if not fixture.get("polyBets"):
                fixture["polyBets"] = []
            fixture["polyBets"].append({
                "market":    market,
                "stake":     order.get("stake", STAKE_USDC),
                "polyPrice": order.get("polyPrice"),
                "orderId":   result.get("orderId"),
                "status":    result.get("status"),
                "error":     result.get("error"),
                "placedAt":  datetime.now(timezone.utc).isoformat(),
                "result":    None,  # filled in later by polySetResult()
            })
            return

    # No existing fixture found — append a standalone log entry
    history.append({
        "id":      f"poly-{today}-{home}-{away}-{market}".replace(" ", "_"),
        "date":    today,
        "home":    home,
        "away":    away,
        "league":  order.get("league", ""),
        "polyBets": [{
            "market":    market,
            "stake":     order.get("stake", STAKE_USDC),
            "polyPrice": order.get("polyPrice"),
            "orderId":   result.get("orderId"),
            "status":    result.get("status"),
            "error":     result.get("error"),
            "placedAt":  datetime.now(timezone.utc).isoformat(),
            "result":    None,
        }],
    })


# ── Main ────────────────────────────────────────────────────

def main():
    # 1. Read env vars
    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    orders_raw  = os.environ.get("ORDERS_JSON", "[]").strip()

    if not private_key:
        print("❌ POLY_PRIVATE_KEY not set")
        sys.exit(1)

    try:
        orders = json.loads(orders_raw)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid ORDERS_JSON: {e}")
        sys.exit(1)

    if not orders:
        print("ℹ️  No orders to place.")
        sys.exit(0)

    print(f"\n🟣 Polymarket Bet Placer — {len(orders)} order(s)\n{'─'*50}")

    history = load_history()
    placed  = 0
    failed  = 0

    for i, order in enumerate(orders, 1):
        home      = order.get("home", "")
        away      = order.get("away", "")
        market    = order.get("market", "")
        poly_price = order.get("polyPrice")

        print(f"\n[{i}/{len(orders)}] {home} vs {away} — {market}")

        # 2. Find Gamma event
        event = gamma_search_event(home, away)
        if not event:
            print(f"  ❌ No Polymarket event found — skipping")
            log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": "no event found"})
            failed += 1
            continue

        print(f"  ✅ Event: {event.get('title')}")

        # 3. Get CLOB token ID for the outcome
        token_id = find_clob_token_id(event, market, home, away)
        if not token_id:
            print(f"  ❌ CLOB token ID not found for '{market}' — skipping")
            log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": "token_id not found"})
            failed += 1
            continue

        print(f"  📍 Token ID: {token_id}")
        if poly_price:
            print(f"  💰 Price: {round(poly_price * 100)}¢ (implied {round(1/poly_price, 2):.2f})")

        # 4. Place order
        stake = order.get("stake", STAKE_USDC)
        result = place_market_order(token_id, float(stake), private_key)

        if result["status"] == "placed":
            print(f"  ✅ Order placed — ID: {result['orderId']}")
            placed += 1
        else:
            print(f"  ❌ Order failed: {result['error']}")
            failed += 1

        # 5. Log to history
        log_bet_to_history(history, order, result)

        # Rate limit: brief pause between orders
        if i < len(orders):
            time.sleep(1.0)

    # 6. Save updated history
    save_history(history)

    print(f"\n{'─'*50}")
    print(f"✅ Placed: {placed}   ❌ Failed/Skipped: {failed}")
    print(f"📝 picks_history.json updated\n")

    if failed > 0 and placed == 0:
        sys.exit(1)  # Signal error to GitHub Action


if __name__ == "__main__":
    main()
