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
    "Heimsieg":               {"type": "home_win"},
    "Auswärtssieg":           {"type": "away_win"},
    "Unentschieden":          {"type": "draw"},
    "Over 2.5 Tore":          {"type": "over25"},
    "Under 2.5 Tore":         {"type": "under25"},
    "Beide Teams treffen":    {"type": "btts_yes"},
    "BTTS: Ja":               {"type": "btts_yes"},
    "Beide Teams treffen: Nein": {"type": "btts_no"},
    "BTTS: Nein":             {"type": "btts_no"},
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


def _parse_json_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            r = json.loads(val)
            return r if isinstance(r, list) else []
        except Exception:
            return []
    return []


def find_clob_token_id(event: dict, market_label: str, home: str, away: str) -> str | None:
    """
    Find the CLOB token ID for the specific outcome in an event's markets.
    Searches both event-level outcomes (moneyline) AND nested sub-markets.
    Returns the token_id string or None if not found.
    """
    mkt_info = OUTCOME_MAP.get(market_label)
    if not mkt_info:
        return None

    mkt_type  = mkt_info["type"]
    is_goals  = mkt_type in ("over25", "under25")
    is_btts   = mkt_type in ("btts_yes", "btts_no")
    # Use first meaningful token of each team name for fuzzy matching
    home_tokens = [t for t in home.lower().split() if len(t) >= 3]
    away_tokens = [t for t in away.lower().split() if len(t) >= 3]
    home_first  = home_tokens[0] if home_tokens else home.lower()
    away_first  = away_tokens[0] if away_tokens else away.lower()

    def _is_binary_yes_no(outcomes: list) -> bool:
        """True if this is a binary Yes/No market."""
        return len(outcomes) == 2 and {o.lower() for o in outcomes} == {"yes", "no"}

    def _match_outcome(mkt_type_: str, outcomes: list, clob_ids: list, question: str = "") -> str | None:
        """Return CLOB token ID for the desired outcome, or None."""
        if not outcomes or len(outcomes) != len(clob_ids):
            return None

        q_lower = question.lower()

        # ── Binary Yes/No markets (e.g. "Will Real Betis win?") ─────────────────
        # Polymarket Winner events use separate binary markets per outcome.
        # Team names appear in the question, not in outcome labels ("Yes"/"No").
        if _is_binary_yes_no(outcomes):
            yes_idx = next((i for i, o in enumerate(outcomes) if o.lower() == "yes"), None)
            no_idx  = next((i for i, o in enumerate(outcomes) if o.lower() == "no"),  None)
            if yes_idx is None:
                return None
            if mkt_type_ == "home_win" and any(t in q_lower for t in home_tokens) and any(w in q_lower for w in ("win", "beat", "defeat")):
                return clob_ids[yes_idx]
            if mkt_type_ == "away_win" and any(t in q_lower for t in away_tokens) and any(w in q_lower for w in ("win", "beat", "defeat")):
                return clob_ids[yes_idx]
            if mkt_type_ == "draw" and "draw" in q_lower:
                return clob_ids[yes_idx]
            # Goals binary: "Will there be over 2.5 goals?"
            if mkt_type_ == "over25" and "over" in q_lower and "2.5" in q_lower:
                return clob_ids[yes_idx]
            if mkt_type_ == "under25" and ("under" in q_lower or "fewer" in q_lower) and "2.5" in q_lower:
                return clob_ids[yes_idx]
            # BTTS binary: "Will both teams score?" / "Both Teams to Score?"
            is_btts_q = any(kw in q_lower for kw in ("both teams", "both team", "btts", "both score"))
            if mkt_type_ == "btts_yes" and is_btts_q:
                return clob_ids[yes_idx]
            if mkt_type_ == "btts_no" and is_btts_q and no_idx is not None:
                return clob_ids[no_idx]
            return None

        # ── Multi-outcome markets (e.g. ["Real Betis", "Draw", "Real Oviedo"]) ──
        if mkt_type_ == "home_win":
            idx = next((i for i, o in enumerate(outcomes) if any(t in o.lower() for t in home_tokens)), None)
        elif mkt_type_ == "away_win":
            idx = next((i for i, o in enumerate(outcomes) if any(t in o.lower() for t in away_tokens)), None)
        elif mkt_type_ == "draw":
            idx = next((i for i, o in enumerate(outcomes) if "draw" in o.lower()), None)
        elif mkt_type_ == "over25":
            idx = next((i for i, o in enumerate(outcomes)
                        if o.lower() in ("yes", "over") or "over" in o.lower()), None)
        elif mkt_type_ == "under25":
            idx = next((i for i, o in enumerate(outcomes)
                        if o.lower() in ("no", "under") or "under" in o.lower()), None)
        else:
            idx = None
        return clob_ids[idx] if idx is not None else None

    # ── 1. Event-level outcomes (simple moneyline / 3-way markets) ───────────
    ev_outcomes = _parse_json_list(event.get('outcomes') or '[]')
    ev_clob_ids = _parse_json_list(event.get('clobTokenIds') or '[]')
    if os.environ.get('POLY_DEBUG'):
        print(f"    [dbg] ev_outcomes={ev_outcomes}  ev_clob_ids={ev_clob_ids[:1] if ev_clob_ids else []}")
        print(f"    [dbg] markets count={len(event.get('markets') or [])}")
    ev_question = event.get("question") or event.get("title") or ""
    token = _match_outcome(mkt_type, ev_outcomes, ev_clob_ids, question=ev_question)
    if token:
        return token

    # ── 2. Nested sub-markets ────────────────────────────────────────────────
    for mkt in event.get("markets", []):
        q        = (mkt.get("question") or "")
        outcomes = _parse_json_list(mkt.get("outcomes") or "[]")
        clob_ids = _parse_json_list(mkt.get("clobTokenIds") or "[]")

        if not outcomes or len(outcomes) != len(clob_ids):
            continue

        q_lower = q.lower()
        if is_goals:
            if "2.5" not in q_lower and "goal" not in q_lower:
                continue
        elif is_btts:
            if not any(kw in q_lower for kw in ("both teams", "both team", "btts", "both score")):
                continue
        else:
            # Binary Yes/No markets: accept if question references a team or winner/draw context
            if _is_binary_yes_no(outcomes):
                has_home = any(t in q_lower for t in home_tokens)
                has_away = any(t in q_lower for t in away_tokens)
                has_draw_kw = "draw" in q_lower
                has_win_kw  = any(w in q_lower for w in ("win", "beat", "defeat"))
                if not ((has_home or has_away) and (has_win_kw or has_draw_kw)) and not has_draw_kw:
                    continue
            else:
                # Multi-outcome: relaxed filter
                has_draw = any("draw" in str(o).lower() for o in outcomes)
                has_kw   = any(kw in q_lower for kw in ("win", "winner", "match", "beat", "draw", "vs", "moneyline"))
                if not has_kw and not has_draw:
                    continue

        token = _match_outcome(mkt_type, outcomes, clob_ids, question=q)
        if token:
            return token

    return None


def gamma_find_winner_event(order: dict, mm_event: dict) -> dict | None:
    """
    For a 'More Markets' event, find the corresponding winner/moneyline event.
    1. Strip '-more-markets' from the slug and try that.
    2. Keyword search, preferring events without 'More Markets' in title.
    """
    import re as _re
    slug = (mm_event.get('slug') or '').rstrip('/')
    winner_slug = _re.sub(r'-more-markets?$', '', slug)
    if winner_slug and winner_slug != slug:
        ev = gamma_fetch_by_slug(winner_slug)
        if ev:
            return ev

    # Keyword search fallback
    home = order.get("home", "")
    away = order.get("away", "")
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"keyword": f"{home} {away}", "active": "true", "limit": 20},
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json()
        if isinstance(events, dict):
            events = events.get("events", [])
    except Exception as e:
        print(f"  ⚠️  Winner-Event Keyword-Suche fehlgeschlagen: {e}")
        return None

    home_t = [t for t in home.lower().split() if len(t) >= 3]
    away_t = [t for t in away.lower().split() if len(t) >= 3]
    for ev in events:
        title = (ev.get("title") or "").lower()
        if "more market" in title:
            continue  # skip More Markets events
        if any(t in title for t in home_t) and any(t in title for t in away_t):
            # Keyword results are lightweight (no clobTokenIds).
            # Re-fetch by slug to get the full event with market data.
            slug = (ev.get("slug") or "").rstrip("/")
            if slug:
                full_ev = gamma_fetch_by_slug(slug)
                if full_ev:
                    return full_ev
            return ev  # fallback: return lightweight if slug re-fetch fails
    return None


# ── CLOB order placement ────────────────────────────────────

def place_market_order(token_id: str, amount_usdc: float, private_key: str,
                       price_hint: float = None) -> dict:
    """
    Place a BUY order on Polymarket CLOB v2.

    Strategy (FOK-safe):
      1. Try create_and_post_market_order (GTC market order).
         NOTE: Polymarket's CLOB engine treats market orders as FOK internally —
         if there isn't enough liquidity at the current price the order is killed.
      2. If the market order fails with a FOK/fill error, automatically retry as a
         GTC *limit* order at price_hint + 2pp buffer (or fetched midpoint + 2pp).
         A limit order sits in the book until filled — no FOK rejection possible.

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

    try:
        from py_clob_client_v2.exceptions import PolyApiException
    except ImportError:
        PolyApiException = Exception

    def _parse_resp(resp):
        """Extract (orderId, error) from a CLOB API response dict."""
        if resp and resp.get("success"):
            return resp.get("orderID") or resp.get("id") or "unknown", None
        err = (resp or {}).get("errorMsg") or (resp or {}).get("error") or str(resp)
        return None, err

    def _is_fok_error(err_str: str) -> bool:
        """True when the error is a FOK/fill rejection (not a creds/network problem)."""
        s = (err_str or "").lower()
        return "fok" in s or "fully filled" in s or "fill" in s

    # ── STEP 1: Market order (fast path) ──────────────────────────────────────
    market_err = None
    try:
        resp = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=token_id,
                amount=amount_usdc,
                side=Side.BUY,
                order_type=OrderType.GTC,
            ),
            options=PartialCreateOrderOptions(tick_size="0.01"),
        )
        oid, err = _parse_resp(resp)
        if oid:
            return {"status": "placed", "orderId": oid, "error": None,
                    "method": "market"}
        market_err = err
    except PolyApiException as e:
        market_err = str(e)
    except Exception as e:
        market_err = str(e)

    # ── STEP 2: GTC limit order fallback (FOK-safe) ───────────────────────────
    # Only retry as limit order if it was a FOK/liquidity problem.
    # For auth/creds errors we fail immediately so the user knows.
    if not _is_fok_error(market_err):
        return {"status": "failed", "orderId": None, "error": market_err}

    print(f"  ⚠️  Market order FOK — retry als GTC Limit Order…")

    # Determine limit price: use price_hint (from dashboard) if available,
    # otherwise fetch current midpoint from CLOB REST API.
    limit_price = None
    if price_hint and 0.01 <= price_hint <= 0.99:
        limit_price = price_hint
    else:
        try:
            r = requests.get(
                f"{CLOB_HOST}/midpoint",
                params={"token_id": token_id},
                timeout=8,
            )
            if r.ok:
                mid = float(r.json().get("mid", 0))
                if 0.01 <= mid <= 0.99:
                    limit_price = mid
        except Exception:
            pass

    if not limit_price:
        return {"status": "failed", "orderId": None,
                "error": f"Market order failed (FOK) and no price available for limit fallback. "
                         f"Original: {market_err}"}

    # Add 2pp buffer so the limit order crosses the spread and gets priority in the book.
    # Round to Polymarket's 0.01 tick size.
    limit_price_buffered = min(0.99, round(limit_price + 0.02, 2))
    # Number of YES-tokens to buy = USDC_spend / price_per_token
    # Round size to 4 decimal places (Polymarket norm).
    size = round(amount_usdc / limit_price_buffered, 4)

    print(f"  📋 Limit Order: {limit_price_buffered:.2f} (mid {limit_price:.2f} +2pp)  ×  {size} tokens")

    try:
        from py_clob_client_v2.clob_types import OrderArgs
        resp2 = client.create_and_post_order(
            order_args=OrderArgs(
                token_id=token_id,
                price=limit_price_buffered,
                size=size,
                side=Side.BUY,
            ),
            options=PartialCreateOrderOptions(tick_size="0.01"),
        )
        oid2, err2 = _parse_resp(resp2)
        if oid2:
            return {"status": "placed", "orderId": oid2, "error": None,
                    "method": "limit_gtc"}
        return {"status": "failed", "orderId": None,
                "error": f"Limit fallback fehlgeschlagen: {err2} (ursprüngl: {market_err})"}
    except Exception as e:
        return {"status": "failed", "orderId": None,
                "error": f"Limit fallback Exception: {e} (ursprüngl: {market_err})"}


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
            # "More Markets" events enthalten keine 1X2/Moneyline Token IDs.
            # → Separates Winner-Event suchen und nochmal versuchen.
            print(f"  ⚠️  Token nicht in '{event.get('title')}' — suche Winner-Event …")
            winner_event = gamma_find_winner_event(order, event)
            if winner_event:
                print(f"  🔄 Winner-Event: {winner_event.get('title')}")
                token_id = find_clob_token_id(winner_event, market, home, away)
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
            result = place_market_order(
                token_id, float(stake), private_key,
                price_hint=float(poly_price) if poly_price else None,
            )
            if result["status"] == "placed":
                method = result.get("method", "market")
                label  = "Limit GTC" if method == "limit_gtc" else "Market"
                print(f"  ✅ Order platziert ({label}) — ID: {result['orderId']}")
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
