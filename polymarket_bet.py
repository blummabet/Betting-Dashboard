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

import argparse
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

def gamma_fetch_by_slug(slug: str) -> dict | None:
    """Fetch a single event from Gamma API using its slug. Returns the event or None."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": slug, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("events", [])
        return events[0] if events else None
    except Exception as e:
        print(f"  ⚠️  Gamma API error for slug '{slug}': {e}")
        return None


def gamma_find_event(order: dict) -> dict | None:
    """
    Find the Polymarket event for an order.
    1. Prefer the eventUrl from the pre-fetched JSON cache (most reliable).
    2. Fallback: keyword search (less reliable, kept as safety net).
    """
    event_url = order.get("eventUrl") or ""
    if event_url and "/event/" in event_url:
        slug = event_url.rstrip("/").split("/event/")[-1]
        ev = gamma_fetch_by_slug(slug)
        if ev:
            return ev
        print(f"  ⚠️  Slug lookup failed for '{slug}', trying keyword fallback…")

    # Fallback: keyword search with raw team names
    home = order.get("home", "")
    away = order.get("away", "")
    keyword = f"{home} {away}"
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"keyword": keyword, "active": "true", "limit": 12},
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json()
        if isinstance(events, dict):
            events = events.get("events", [])
    except Exception as e:
        print(f"  ⚠️  Gamma keyword search error for '{keyword}': {e}")
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
    Place a market buy order on Polymarket CLOB v2.
    Uses create_and_post_market_order (py-clob-client-v2 API).
    Returns dict with orderId and status.
    """
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import (
            MarketOrderArgs, OrderType, ApiCreds, PartialCreateOrderOptions
        )
        from py_clob_client_v2 import Side, SignatureTypeV2
    except ImportError as e:
        print(f"  ❌ py-clob-client-v2 import error: {e}")
        sys.exit(1)

    # POLY_FUNDER_ADDRESS = Proxy-Wallet Adresse (optional, wenn auto-Derivierung scheitert)
    # Zu finden auf polymarket.com/profile → URL enthält die Proxy-Wallet-Adresse
    funder_addr = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()

    # POLY_PROXY = 1 in v2 — das Proxy-Wallet des Users (dort liegt das USDC-Guthaben)
    # funder = Proxy-Wallet-Adresse; wenn nicht gesetzt versucht ClobClient sie selbst zu derivieren
    client_kwargs: dict = dict(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=SignatureTypeV2.POLY_PROXY,
    )
    if funder_addr:
        client_kwargs["funder"] = funder_addr

    client = ClobClient(**client_kwargs)

    # API Credentials für das Proxy-Wallet derivieren (deterministisch aus Private Key)
    # NICHT gespeicherte EOA-Creds verwenden — die passen nicht zum Proxy-Wallet-Kontext
    api_key = os.environ.get("POLY_API_KEY", "").strip()
    creds = None

    if api_key:
        # Gespeicherte Creds vorhanden — verwenden (müssen für Proxy-Wallet generiert worden sein)
        api_secret     = os.environ.get("POLY_API_SECRET", "").strip()
        api_passphrase = os.environ.get("POLY_API_PASSPHRASE", "").strip()
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        print(f"  🔑 Verwende gespeicherte API Creds (Key: {api_key[:8]}…)")
    else:
        # Keine gespeicherten Creds → frisch aus Private Key derivieren
        print(f"  🔑 Deriviere API Creds aus Private Key…")
        try:
            creds_raw = client.derive_api_key()
            if isinstance(creds_raw, ApiCreds):
                creds = creds_raw
            elif isinstance(creds_raw, dict):
                creds = ApiCreds(
                    api_key=creds_raw.get("key", creds_raw.get("apiKey", "")),
                    api_secret=creds_raw.get("secret", ""),
                    api_passphrase=creds_raw.get("passphrase", ""),
                )
            if creds:
                print(f"  ✅ API Creds deriviert (Key: {creds.api_key[:8] if hasattr(creds, 'api_key') else '?'}…)")
        except Exception as e:
            print(f"  ⚠️  derive_api_key fehlgeschlagen: {e} — fahre ohne Creds fort")

    if creds:
        try:
            client.set_api_creds(creds)
        except AttributeError:
            # In einigen v2-Versionen werden Creds direkt im Constructor gesetzt
            client_kwargs["creds"] = creds
            client = ClobClient(**client_kwargs)

    # create_and_post_market_order — offizieller v2-Weg
    try:
        from py_clob_client_v2.exceptions import PolyApiException
    except ImportError:
        PolyApiException = Exception

    try:
        resp = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=token_id,
                amount=amount_usdc,
                side=Side.BUY,
                order_type=OrderType.FOK,
            ),
            options=PartialCreateOrderOptions(tick_size="0.01"),
        )
    except PolyApiException as e:
        return {"status": "failed", "orderId": None, "error": str(e)}
    except Exception as e:
        return {"status": "failed", "orderId": None, "error": str(e)}

    if resp and resp.get("success"):
        return {
            "status":  "placed",
            "orderId": resp.get("orderID") or resp.get("id") or "unknown",
            "error":   None,
        }
    err = (resp or {}).get("errorMsg") or (resp or {}).get("error") or str(resp)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Alles durchlaufen aber keine echte Order absenden")
    args = parser.parse_args()
    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    # 1. Read env vars
    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    orders_raw  = os.environ.get("ORDERS_JSON", "[]").strip()

    if not private_key:
        print("❌ POLY_PRIVATE_KEY nicht gesetzt")
        print("   export POLY_PRIVATE_KEY=0x...")
        sys.exit(1)

    try:
        orders = json.loads(orders_raw)
    except json.JSONDecodeError as e:
        print(f"❌ Ungültiges ORDERS_JSON: {e}")
        sys.exit(1)

    if not orders:
        print("ℹ️  Keine Orders.")
        sys.exit(0)

    mode = "🔍 DRY-RUN (keine echten Orders)" if dry_run else "🟣 LIVE"
    print(f"\n{mode} — {len(orders)} Order(s)\n{'─'*50}")

    history = load_history()
    placed  = 0
    failed  = 0

    for i, order in enumerate(orders, 1):
        home       = order.get("home", "")
        away       = order.get("away", "")
        market     = order.get("market", "")
        poly_price = order.get("polyPrice")
        stake      = order.get("stake", STAKE_USDC)

        print(f"\n[{i}/{len(orders)}] {home} vs {away} — {market}")

        # 2. Gamma API: Event via Slug (aus Cache-URL) oder Keyword-Fallback
        event = gamma_find_event(order)
        if not event:
            print(f"  ❌ Kein Polymarket-Event gefunden — übersprungen")
            log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": "no event found"})
            failed += 1
            continue

        print(f"  ✅ Event: {event.get('title')}")

        # 3. CLOB Token ID für den Outcome finden
        token_id = find_clob_token_id(event, market, home, away)
        if not token_id:
            print(f"  ❌ CLOB Token ID für '{market}' nicht gefunden — übersprungen")
            log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": "token_id not found"})
            failed += 1
            continue

        print(f"  📍 Token ID: {token_id[:16]}…")
        if poly_price:
            print(f"  💰 Preis: {round(poly_price * 100)}¢  |  Einsatz: ${stake:.2f} USDC")

        # 4. Order absenden (oder simulieren)
        if dry_run:
            print(f"  🔍 DRY-RUN: Order würde jetzt abgesendet werden — übersprungen")
            result = {"status": "dry-run", "orderId": "dry-run", "error": None}
            placed += 1
        else:
            result = place_market_order(token_id, float(stake), private_key)
            if result["status"] == "placed":
                print(f"  ✅ Order platziert — ID: {result['orderId']}")
                placed += 1
            else:
                print(f"  ❌ Order fehlgeschlagen: {result['error']}")
                failed += 1

        # 5. In History loggen
        log_bet_to_history(history, order, result)

        if i < len(orders):
            time.sleep(1.0)

    # 6. History speichern
    save_history(history)

    print(f"\n{'─'*50}")
    if dry_run:
        print(f"🔍 Dry-Run abgeschlossen: {placed}/{len(orders)} würden platziert werden")
        print(f"   Wenn alles aussieht, nochmal OHNE --dry-run ausführen.\n")
    else:
        print(f"✅ Platziert: {placed}   ❌ Fehlgeschlagen: {failed}")
        print(f"📝 picks_history.json aktualisiert\n")

    if not dry_run and failed > 0 and placed == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
