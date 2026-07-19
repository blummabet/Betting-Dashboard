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

# ── Refactor 2026-06-06: Stake + Bankroll-Limits aus cocobet_config.json ──
# Bewusst dieselbe Profile-Quelle wie auto_wm_poly_trigger.py, damit manuell
# platzierte Bets und Auto-Bets garantiert dieselben Limits sehen.
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

GAMMA_API    = "https://gamma-api.polymarket.com"
CLOB_HOST    = "https://clob.polymarket.com"
CHAIN_ID     = 137        # Polygon — Netzwerk-Konstante, bleibt hardcoded
STAKE_USDC   = _cfg("trade", "stake_usdc_flat", 5.5)  # €5 ≈ $5.50 USDC flat per bet
import cocobet_dataset as D   # 29.06.2026: dataset-aware (MLS-Poly-Dry-Run)
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "picks_history.json")
BALANCE_FILE = str(D.file("wm_poly_balance.json",     "liga_poly_balance.json"))
PLACED_FILE  = str(D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json"))

# Bankroll-Schutz — gleiche Limits wie in auto_wm_poly_trigger.py.
# Schützt sowohl manuelle ("Jetzt platzieren") als auch Auto-Bets.
DAILY_BET_CAP        = _cfg("trade", "daily_bet_cap",         8)     # max Bets pro UTC-Tag
DAILY_STAKE_CAP_USDC = _cfg("trade", "daily_stake_cap_usdc",  50.0)  # max kumulativer Stake pro UTC-Tag
MIN_BALANCE_BUFFER   = _cfg("trade", "min_balance_buffer",     1.0)  # USDC die nach Bet im Wallet bleiben müssen

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
    """Fetch a single event from Gamma API using its slug. Returns the event or None.

    M4 Fix 05.06.2026: Timeouts in Trade-Pfad von 10s/8s auf 20s/15s erhöht.
    Gamma-API hat gelegentliche Latency-Spikes (5-12s). Bei timeout=10s könnte
    der Lookup fehlschlagen kurz vor Kickoff → kein Trade obwohl Edge vorhanden.
    20s gibt mehr Headroom, ohne das Auto-Trigger-Workflow (max 15min/Job)
    zu gefährden.
    """
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": slug, "limit": 1},
            timeout=20,
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
    # Unterstützt beide URL-Formate:
    #   /event/{slug}  (klassisch)
    #   /sports/fifa-world-cup/{slug}  (WM 2026)
    if event_url:
        slug = None
        for marker in ("/event/", "/sports/fifa-world-cup/", "/sports/"):
            if marker in event_url:
                slug = event_url.rstrip("/").split(marker)[-1].split("/")[0]
                break
        if slug:
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
            timeout=20,
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
            # H4 Fix: home/away/draw binary muss BEIDE Team-Tokens im Question haben
            # (sonst matchen z.B. "Will Brazil win vs Morocco?" und "Will Brazil
            # win vs Argentina?" beide für home="Brazil" — eindeutige Spielzuordnung)
            both_teams_in_q = (
                any(t in q_lower for t in home_tokens)
                and any(t in q_lower for t in away_tokens)
            )
            if mkt_type_ == "home_win" and both_teams_in_q and any(w in q_lower for w in ("win", "beat", "defeat")):
                # Außerdem: home muss VOR "win/beat/defeat" stehen (Brazil beat Argentina != Argentina beat Brazil)
                home_pos = min((q_lower.find(t) for t in home_tokens if t in q_lower), default=999)
                away_pos = min((q_lower.find(t) for t in away_tokens if t in q_lower), default=999)
                if home_pos < away_pos:
                    return clob_ids[yes_idx]
            if mkt_type_ == "away_win" and both_teams_in_q and any(w in q_lower for w in ("win", "beat", "defeat")):
                home_pos = min((q_lower.find(t) for t in home_tokens if t in q_lower), default=999)
                away_pos = min((q_lower.find(t) for t in away_tokens if t in q_lower), default=999)
                if away_pos < home_pos:
                    return clob_ids[yes_idx]
            if mkt_type_ == "draw" and "draw" in q_lower and both_teams_in_q:
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
        # H4 Fix 05.06.2026 — AND-match statt OR-Match:
        # Vorher: Heimsieg matched ERSTES Outcome mit ANY home_token →
        # Bei Outcomes ["Real Betis", "Draw", "Real Oviedo"] mit home="Real Betis"
        # und home_tokens=["real","betis"] hätte das Outcome "Real Oviedo"
        # genauso gematched, weil "real" auch dort vorkommt. Wenn die Outcomes-
        # Reihenfolge zufällig Oviedo zuerst hat → falscher Token gekauft.
        # Jetzt: Outcome muss ALLE home_tokens enthalten UND keine away_tokens.
        def _outcome_score(outcome: str, my_tokens: list, other_tokens: list) -> int:
            """Higher = better match. Negative wenn other_tokens drin sind."""
            o_lower = outcome.lower()
            my_hits    = sum(1 for t in my_tokens if t in o_lower)
            other_hits = sum(1 for t in other_tokens if t in o_lower)
            # Wenn beide Token-Sets matchen, geht's nicht eindeutig → -1
            if my_hits > 0 and other_hits > 0:
                # Wenn other_hits ≥ my_hits → eindeutig falsches Outcome
                if other_hits >= my_hits:
                    return -1
            return my_hits - other_hits

        if mkt_type_ == "home_win":
            # Score jedes Outcome — wähle das mit höchstem Score (>0)
            best = max(
                enumerate(outcomes),
                key=lambda io: _outcome_score(io[1], home_tokens, away_tokens),
                default=None,
            )
            idx = best[0] if best and _outcome_score(best[1], home_tokens, away_tokens) > 0 else None
        elif mkt_type_ == "away_win":
            best = max(
                enumerate(outcomes),
                key=lambda io: _outcome_score(io[1], away_tokens, home_tokens),
                default=None,
            )
            idx = best[0] if best and _outcome_score(best[1], away_tokens, home_tokens) > 0 else None
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
            timeout=20,
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

def _hours_to_kickoff_safe(kickoff_iso):
    """Stunden bis Anpfiff aus ISO-Zeit. None bei fehlend/kaputt → decide_entry fällt auf Taker."""
    if not kickoff_iso:
        return None
    try:
        ko = datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
        return (ko - datetime.now(timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


def _maker_intent(price_hint, best_bid=None, best_ask=None, hours_to_ko=None):
    """19.07.2026 — Maker-Vorentscheid VOR der Market-Order (Lucas: „Poly ausnutzen, Spread sparen").

    Reine Delegation an poly_entry.decide_entry. Trennt die Entscheidung (testbar, kein Netzwerk)
    von der Ausführung. Gibt {mode, price, reason} zurück; bei mode=='maker' legt place_market_order
    direkt eine ruhende Limit-Order statt zu crossen. Default (maker_enabled=false) → immer 'taker'
    → das bestehende Live-Verhalten bleibt Bit für Bit gleich, bis Lucas es einschaltet."""
    try:
        import poly_entry
        cfg = poly_entry.EntryConfig(
            maker_enabled=bool(_cfg("trade", "maker_enabled", False)),
            maker_min_hours=float(_cfg("trade", "maker_min_hours", 3.0)),
            maker_min_spread_pp=float(_cfg("trade", "maker_min_spread_pp", 3.0)),
        )
        return poly_entry.decide_entry(price_hint, best_bid, best_ask, hours_to_ko, cfg)
    except Exception as e:
        # Entscheidungs-Logik darf einen Trade NIE kippen — im Zweifel Taker (bestehendes Verhalten).
        return {"mode": "taker", "price": None, "reason": f"decide_entry-Fehler: {e}"}


def place_market_order(token_id: str, amount_usdc: float, private_key: str,
                       price_hint: float = None,
                       best_bid: float = None, best_ask: float = None,
                       hours_to_ko: float = None) -> dict:
    """
    Place a BUY order on Polymarket CLOB v2.

    Strategy (FOK-safe):
      0. Maker-Vorentscheid (19.07.2026): Ist maker_enabled gesetzt UND genug Zeit UND Spread breit,
         wird direkt eine ruhende GTC-Limit-Order oben aufs Gebot gelegt (Spread einsparen statt
         zahlen). Default AUS → Schritt 1 wie bisher.
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

    # ── STEP 0: Maker-Vorentscheid (19.07.2026) ───────────────────────────────
    # Ist maker_enabled gesetzt UND genug Zeit UND Spread breit, legen wir eine RUHENDE Limit-Order
    # oben aufs Gebot — Spread einsparen statt zahlen. Default (maker_enabled=false) → übersprungen,
    # Verhalten unverändert. Nutzt denselben Post-Mechanismus wie der FOK-Fallback (create_and_post_order).
    _intent = _maker_intent(price_hint, best_bid, best_ask, hours_to_ko)
    if _intent.get("mode") == "maker" and _intent.get("price"):
        mk_price = _intent["price"]
        mk_size  = round(amount_usdc / mk_price, 4)
        print(f"  🅼 Maker: {mk_price:.2f} × {mk_size} tokens — {_intent['reason']}")
        try:
            from py_clob_client_v2.clob_types import OrderArgs
            resp0 = client.create_and_post_order(
                order_args=OrderArgs(token_id=token_id, price=mk_price, size=mk_size, side=Side.BUY),
                options=PartialCreateOrderOptions(tick_size="0.01"),
            )
            oid0, err0 = _parse_resp(resp0)
            if oid0:
                return {"status": "placed", "orderId": oid0, "error": None,
                        "method": "maker_limit", "makerPrice": mk_price}
            # Maker abgelehnt → NICHT scheitern, sondern als Taker weiter (Fill-Sicherheit).
            print(f"  ⚠️  Maker abgelehnt ({err0}) — weiter als Taker")
        except Exception as e:
            print(f"  ⚠️  Maker-Order-Exception ({e}) — weiter als Taker")

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
                timeout=15,
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


def place_sell_order(token_id: str, size: float, private_key: str,
                     price_hint: float = None) -> dict:
    """
    Place a SELL order on Polymarket CLOB v2.

    Args:
        token_id:    CLOB token ID (stored at buy time).
        size:        Number of YES tokens to sell (NOT USDC).
        private_key: Polygon EOA private key.
        price_hint:  Current Poly price for the outcome (0-1). Used to anchor
                     the limit fallback. Fetched from CLOB midpoint if None.

    Strategy (FOK-safe, mirror of place_market_order):
      1. Try create_and_post_market_order with Side.SELL (GTC market order).
      2. If FOK-rejected → GTC limit at price_hint - 0.02 (lower = more aggressive,
         ensures fill even when spread is wide).

    Returns dict: {"status": "placed"/"failed", "orderId": ..., "error": ..., "method": ...}
    """
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import (
            MarketOrderArgs, OrderType, ApiCreds, PartialCreateOrderOptions
        )
        from py_clob_client_v2 import Side, SignatureTypeV2
    except ImportError as e:
        print(f"  ❌ py-clob-client-v2 import error: {e}")
        return {"status": "failed", "orderId": None, "error": str(e)}

    funder_addr = os.environ.get("POLY_FUNDER_ADDRESS", "").strip()
    client_kwargs: dict = dict(
        host=CLOB_HOST,
        key=private_key,
        chain_id=CHAIN_ID,
        signature_type=SignatureTypeV2.POLY_PROXY,
    )
    if funder_addr:
        client_kwargs["funder"] = funder_addr

    client = ClobClient(**client_kwargs)

    api_key = os.environ.get("POLY_API_KEY", "").strip()
    creds = None
    if api_key:
        api_secret     = os.environ.get("POLY_API_SECRET", "").strip()
        api_passphrase = os.environ.get("POLY_API_PASSPHRASE", "").strip()
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
        print(f"  🔑 SELL — gespeicherte API Creds (Key: {api_key[:8]}…)")
    else:
        print(f"  🔑 SELL — deriviere API Creds aus Private Key…")
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
            print(f"  ⚠️  derive_api_key fehlgeschlagen: {e}")

    if creds:
        try:
            client.set_api_creds(creds)
        except AttributeError:
            client_kwargs["creds"] = creds
            client = ClobClient(**client_kwargs)

    try:
        from py_clob_client_v2.exceptions import PolyApiException
    except ImportError:
        PolyApiException = Exception

    def _parse_resp(resp):
        if resp and resp.get("success"):
            return resp.get("orderID") or resp.get("id") or "unknown", None
        err = (resp or {}).get("errorMsg") or (resp or {}).get("error") or str(resp)
        return None, err

    def _is_fok_error(err_str: str) -> bool:
        s = (err_str or "").lower()
        return "fok" in s or "fully filled" in s or "fill" in s

    def _market_sell(sz: float):
        """Einzelner Market-SELL-Versuch → (orderId|None, err|None)."""
        try:
            resp = client.create_and_post_market_order(
                order_args=MarketOrderArgs(
                    token_id=token_id,
                    amount=sz,          # For SELL: amount = tokens (not USDC)
                    side=Side.SELL,
                    order_type=OrderType.GTC,
                ),
                options=PartialCreateOrderOptions(tick_size="0.01"),
            )
            return _parse_resp(resp)
        except PolyApiException as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

    # ── STEP 1: Market SELL order ─────────────────────────────────────────────
    oid, market_err = _market_sell(size)
    if oid:
        return {"status": "placed", "orderId": oid, "error": None, "method": "market_sell"}

    # ── STEP 1b: Balance-Shortfall-Retry (FIX 13.06.2026) ─────────────────────
    # sharesEstimate (Kaufzeit) ist oft ~2% höher als die tatsächlich gehaltenen
    # Tokens (Fees/Slippage/Rundung) → CLOB lehnt mit "not enough balance: balance:
    # <micro>, order amount: <micro>" ab. Das ist KEIN FOK-Fehler → STEP 2 würde
    # sonst sofort abbrechen und gar nicht verkaufen. Fix: echte Balance aus der
    # Fehlermeldung parsen (Mikro-Einheiten, 6 Dezimalstellen) und EINMAL mit der
    # tatsächlich verfügbaren Menge neu verkaufen (auf 2 Dezimalstellen abgerundet,
    # damit garantiert ≤ Balance).
    if market_err and "balance" in market_err.lower() and "enough" in market_err.lower():
        import re as _re, math as _math
        m = _re.search(r"balance:\s*(\d+)", market_err)
        if m:
            bal_tokens = int(m.group(1)) / 1_000_000.0
            safe_size  = _math.floor(bal_tokens * 100) / 100.0  # 2 Dezimal, abgerundet
            if 0 < safe_size < size:
                print(f"  ♻️  Balance-Shortfall: nur {bal_tokens:.4f} Tokens da (Order war {size}) "
                      f"— Retry SELL mit {safe_size}")
                size = safe_size   # auch der Limit-Fallback (STEP 2) nutzt die gekappte Menge
                oid_b, err_b = _market_sell(size)
                if oid_b:
                    return {"status": "placed", "orderId": oid_b, "error": None,
                            "method": "market_sell_balance_capped"}
                market_err = err_b or market_err

    # ── STEP 2: GTC limit SELL fallback ──────────────────────────────────────
    if not _is_fok_error(market_err):
        return {"status": "failed", "orderId": None, "error": market_err}

    print(f"  ⚠️  SELL market order FOK — retry als GTC Limit Sell…")

    # Determine limit price for sell: use price_hint or fetch midpoint.
    limit_price = None
    if price_hint and 0.01 <= price_hint <= 0.99:
        limit_price = price_hint
    else:
        try:
            r = requests.get(
                f"{CLOB_HOST}/midpoint",
                params={"token_id": token_id},
                timeout=15,
            )
            if r.ok:
                mid = float(r.json().get("mid", 0))
                if 0.01 <= mid <= 0.99:
                    limit_price = mid
        except Exception:
            pass

    if not limit_price:
        return {"status": "failed", "orderId": None,
                "error": f"SELL market order FOK und kein Preis für Limit-Fallback. Original: {market_err}"}

    # Subtract 2pp so our limit order sits just below mid — gets priority over other sellers.
    # Round to 0.01 tick size.
    limit_price_buffered = max(0.01, round(limit_price - 0.02, 2))

    print(f"  📋 Limit SELL: {limit_price_buffered:.2f} (mid {limit_price:.2f} -2pp)  ×  {size} tokens")

    try:
        from py_clob_client_v2.clob_types import OrderArgs
        resp2 = client.create_and_post_order(
            order_args=OrderArgs(
                token_id=token_id,
                price=limit_price_buffered,
                size=size,
                side=Side.SELL,
            ),
            options=PartialCreateOrderOptions(tick_size="0.01"),
        )
        oid2, err2 = _parse_resp(resp2)
        if oid2:
            return {"status": "placed", "orderId": oid2, "error": None, "method": "limit_sell_gtc"}
        return {"status": "failed", "orderId": None,
                "error": f"Limit SELL fallback fehlgeschlagen: {err2} (ursprüngl: {market_err})"}
    except Exception as e:
        return {"status": "failed", "orderId": None,
                "error": f"Limit SELL Exception: {e} (ursprüngl: {market_err})"}


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
                "polyClose": None,       # ← Polymarket-Preis ~1h vor Anpfiff
                                          #   wird von resolve_wm_results.py gesetzt
                "polyClvPP": None,       # ← (polyClose - polyPrice) × 100
                                          #   positiv = wir haben günstiger eingekauft als Closing
                "isSteamLag": order.get("isSteamLag", False),  # für Backtest "Steam-Lag-Trades vs Normal"
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
    skipped_bankroll = 0

    # ── Bankroll-Schutz vorbereiten ───────────────────────────────────────────
    # Heutige Bets aus wm_auto_bets_placed.json zählen (deckt Auto + Manual ab).
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(PLACED_FILE, encoding="utf-8") as f:
            placed_db = json.load(f)
        placed_bets_today = [b for b in placed_db.get("bets", [])
                             if (b.get("placedAt") or "")[:10] == today_str]
    except Exception:
        placed_bets_today = []
    bets_today_count = len(placed_bets_today)
    stake_today      = sum(float(b.get("stake") or 0) for b in placed_bets_today)

    # Balance laden (kann veraltet sein — fetch_wm_poly_balance.py läuft via Cron)
    try:
        with open(BALANCE_FILE, encoding="utf-8") as f:
            balance_data = json.load(f)
        available_balance = float(balance_data.get("usdc") or 0)
    except Exception:
        available_balance = 0.0

    running_count   = bets_today_count
    running_stake   = stake_today
    running_balance = available_balance
    print(f"  💰 Heute bereits: {bets_today_count} Bet(s), ${stake_today:.2f} | Balance: ${available_balance:.2f}")

    for i, order in enumerate(orders, 1):
        home       = order.get("home", "")
        away       = order.get("away", "")
        market     = order.get("market", "")
        poly_price = order.get("polyPrice")
        stake      = order.get("stake", STAKE_USDC)

        print(f"\n[{i}/{len(orders)}] {home} vs {away} — {market}")

        # ── Bankroll-Schutz pro Order ─────────────────────────────────────────
        if not dry_run:
            if running_count >= DAILY_BET_CAP:
                print(f"  🛑 Tages-Bet-Cap erreicht ({running_count}/{DAILY_BET_CAP}) — Rest übersprungen")
                log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": f"daily bet cap {DAILY_BET_CAP}"})
                skipped_bankroll += 1
                continue
            if running_stake + stake > DAILY_STAKE_CAP_USDC:
                print(f"  🛑 Stake-Cap überschritten (${running_stake + stake:.2f} > ${DAILY_STAKE_CAP_USDC:.2f}) — übersprungen")
                log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": f"daily stake cap ${DAILY_STAKE_CAP_USDC}"})
                skipped_bankroll += 1
                continue
            if running_balance - stake < MIN_BALANCE_BUFFER:
                print(f"  🛑 Balance zu niedrig (${running_balance:.2f} - ${stake:.2f} < ${MIN_BALANCE_BUFFER:.2f}) — Abbruch")
                log_bet_to_history(history, order, {"status": "skipped", "orderId": None, "error": "balance insufficient"})
                skipped_bankroll += 1
                break

        # ── Token-Auflösung ──────────────────────────────────────────────────
        # HANDICAP (15.06.2026): Der Spread-Token wurde in fetch_wm_poly_prices
        # EXAKT erfasst (Poly clobTokenIds des Spread-Markts) und im Candidate
        # mitgegeben. find_clob_token_id kennt Spread-Märkte NICHT → würde den
        # falschen Token treffen. Daher für AH direkt verwenden: tokens[0] = YES-
        # Token = „Team deckt das Handicap".
        token_id = None
        if order.get("_isHandicap") and order.get("tokens"):
            token_id = order["tokens"][0]
            print(f"  🎯 Handicap-Markt — Spread-Token direkt aus Candidate")

        if not token_id:
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
            # 19.07.2026: Orderbuch-Tiefe + Zeit bis Anpfiff durchreichen, damit der Maker-
            # Vorentscheid überhaupt greifen kann (sonst fiele er mangels Daten immer auf Taker
            # zurück). Beide Felder sind optional — der Dispatch liefert sie mit, wenn der
            # Fetcher CLOB-Tiefe erfasst hat (nur für Edge≥3pp). Fehlen sie → Taker, wie bisher.
            _depth = order.get("depth") or {}
            result = place_market_order(
                token_id, float(stake), private_key,
                price_hint=float(poly_price) if poly_price else None,
                best_bid=_depth.get("bid"), best_ask=_depth.get("ask"),
                hours_to_ko=_hours_to_kickoff_safe(order.get("kickoff")),
            )
            if result["status"] == "placed":
                method = result.get("method", "market")
                label  = {"limit_gtc": "Limit GTC", "maker_limit": "Maker (ruht)"}.get(method, "Market")
                print(f"  ✅ Order platziert ({label}) — ID: {result['orderId']}")
                placed += 1

                # Bankroll-Tally updaten
                running_count   += 1
                running_stake   += stake
                running_balance -= stake

                # Trades-Channel: Manuellen Bet melden
                try:
                    from telegram_trades import notify_trade_opened
                    notify_trade_opened(
                        home=order.get("home", ""), away=order.get("away", ""),
                        market=order.get("market", ""),
                        stake=float(order.get("stake", 0)),
                        poly_price=float(order.get("polyPrice") or poly_price or 0),
                        edge_pp=order.get("edgePP"),
                        pinn_fair=order.get("pinnFair"),
                        order_id=result.get("orderId"),
                        source="manual",
                        home_id=order.get("homeId", ""),
                        away_id=order.get("awayId", ""),
                        slug=order.get("slug", ""),
                        dry_run=False,
                    )
                except Exception as _te:
                    print(f"  ⚠️  Trades-Channel: {_te}")
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
        print(f"✅ Platziert: {placed}   ❌ Fehlgeschlagen: {failed}   🛑 Bankroll-Skip: {skipped_bankroll}")
        print(f"📝 picks_history.json aktualisiert\n")

    if not dry_run and failed > 0 and placed == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
