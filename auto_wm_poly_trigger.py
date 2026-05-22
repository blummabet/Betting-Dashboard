#!/usr/bin/env python3
"""
auto_wm_poly_trigger.py — WM 2026 Auto-Bet Trigger
====================================================
Lädt wm_poly_prices.json, findet Fixtures mit ausreichend Edge,
filtert bereits platzierte Bets, und löst neue Bets aus.

Konfiguration:
    ENABLED = False          → Skript läuft durch aber platziert keine Bets (sicher!)
    AUTO_TRIGGER_EDGE_PP     → Mindest-Edge in Prozentpunkten (Standard: 5.0)
    MIN_VOL                  → Mindest-Liquidity auf Polymarket (Standard: 10000 USDC)
    MIN_DAYS_UNTIL_GAME      → Nicht am Spieltag selbst wetten (Standard: 1)

Verwendung:
    python auto_wm_poly_trigger.py              # dry-run wegen ENABLED=False
    AUTO_TRIGGER_ENABLED=true python ...       # echte Bets (nur wenn bereit!)

Env-Variablen (für echte Ausführung):
    POLY_PRIVATE_KEY     — Polygon EOA private key (aus GitHub Secret)
    TELEGRAM_TOKEN       — Telegram Bot Token
    TELEGRAM_CHAT_ID     — Telegram Chat ID
    AUTO_TRIGGER_ENABLED — "true" um live zu gehen (Standard: false)
"""

import json
import os
import sys
import math
import requests
from datetime import datetime, timezone, date

# ── Konfiguration ──────────────────────────────────────────────────────────────

# SICHERHEITSSCHALTER: False = Skript läuft aber platziert KEINE Bets
# Auf True setzen (oder AUTO_TRIGGER_ENABLED=true in Env) wenn bereit für Live-Trading
ENABLED = False

AUTO_TRIGGER_EDGE_PP = 5.0   # Mindest-Edge in Prozentpunkten
MIN_VOL              = 10000  # Mindest-Volumen auf Polymarket (USDC)
MIN_DAYS_UNTIL_GAME  = 1      # Nicht am Spieltag selbst — zu wenig Zeit für Human Review

# Stake-Tiers: Edge ≥ minEdge → stake in USDC
# Spiegelt die Dashboard-Konfiguration (wmStakeConfig in localStorage).
# Manuell hier anpassen wenn Dashboard-Config geändert wird.
STAKE_TIERS = [
    {"minEdge": 7.0, "stake": 15.0},
    {"minEdge": 5.0, "stake": 10.0},
    {"minEdge": 3.0, "stake":  5.0},
]

def _get_stake_for_edge(edge_pp: float) -> float:
    """Gibt den Einsatz für den gegebenen Edge-Wert zurück (höchster passender Tier)."""
    for tier in sorted(STAKE_TIERS, key=lambda t: -t["minEdge"]):
        if edge_pp >= tier["minEdge"]:
            return tier["stake"]
    return STAKE_TIERS[-1]["stake"] if STAKE_TIERS else 5.0  # fallback

BASE_DIR              = os.path.dirname(os.path.abspath(__file__))
PRICES_FILE           = os.path.join(BASE_DIR, "wm_poly_prices.json")
PLACED_FILE           = os.path.join(BASE_DIR, "wm_auto_bets_placed.json")

# Welche Edge-Keys → Polymarket-Market-Label (muss OUTCOME_MAP in polymarket_bet.py matchen)
EDGE_MARKET_MAP = {
    "edge_hw":  ("poly_hw",  "Heimsieg",           "fair_hw"),
    "edge_dr":  ("poly_dr",  "Unentschieden",       "fair_dr"),
    "edge_aw":  ("poly_aw",  "Auswärtssieg",        "fair_aw"),
    "edge_o25": ("poly_o25", "Over 2.5 Tore",       "fair_o25"),
    "edge_u25": ("poly_u25", "Under 2.5 Tore",      "fair_u25"),
}


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️  Fehler beim Laden von {path}: {e}")
        return default


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def days_until(date_str: str) -> int | None:
    """Tage bis zum Spieltag (negativ = in der Vergangenheit)."""
    if not date_str:
        return None
    try:
        game_date = date.fromisoformat(date_str[:10])
        return (game_date - date.today()).days
    except Exception:
        return None


def bet_key(fix: dict, market: str) -> str:
    """Eindeutiger Schlüssel für Fixture+Markt-Kombination."""
    return f"{fix.get('homeId','')}-{fix.get('awayId','')}-{market}"


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Sendet eine Telegram-Nachricht. Gibt True bei Erfolg zurück."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"  ⚠️  Telegram-Fehler: {e}")
        return False


# ── Hauptlogik ─────────────────────────────────────────────────────────────────

def find_trigger_candidates(fixtures: list, placed_keys: set) -> list:
    """
    Findet alle Fixture+Markt-Kombinationen die die Trigger-Kriterien erfüllen.
    Gibt eine Liste von Order-Dicts zurück (kompatibel mit polymarket_bet.py).
    """
    candidates = []

    for fix in fixtures:
        # Liquiditätscheck
        vol = fix.get("vol") or 0
        if vol < MIN_VOL:
            continue

        # Pinnacle-Daten notwendig für Edge-Berechnung
        if not fix.get("hasPinnacle"):
            continue

        # Timing-Check
        d = days_until(fix.get("date", ""))
        if d is None or d < MIN_DAYS_UNTIL_GAME:
            continue

        # Edge-Check für jeden Markt
        for edge_key, (price_key, market_label, fair_key) in EDGE_MARKET_MAP.items():
            edge = fix.get(edge_key)
            if edge is None or edge < AUTO_TRIGGER_EDGE_PP:
                continue

            poly_price = fix.get(price_key)
            if not poly_price or poly_price <= 0:
                continue

            key = bet_key(fix, market_label)
            if key in placed_keys:
                print(f"  ⏭️  Bereits platziert: {fix['home']} vs {fix['away']} — {market_label}")
                continue

            # Slug: für O/U den moreMktSlug verwenden, sonst den Moneyline-Slug
            is_ou = market_label in ("Over 2.5 Tore", "Under 2.5 Tore")
            slug = (fix.get("moreMktSlug") or fix.get("slug")) if is_ou else fix.get("slug")
            event_url = (
                f"https://polymarket.com/sports/fifa-world-cup/{slug}"
                if slug else None
            )

            candidates.append({
                "home":      fix["home"],
                "away":      fix["away"],
                "homeId":    fix.get("homeId", ""),
                "awayId":    fix.get("awayId", ""),
                "market":    market_label,
                "league":    "WM2026",
                "stake":     _get_stake_for_edge(edge),
                "polyPrice": poly_price,
                "slug":      slug,
                "eventUrl":  event_url,
                "edgePP":    edge,
                "pinnFair":  fix.get(fair_key),
                "_betKey":   key,   # intern, wird vor Übergabe an polymarket_bet entfernt
            })

    return candidates


def main():
    print(f"\n{'='*55}")
    print(f"  🤖 WM 2026 Auto-Trigger — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}\n")

    # Sicherheitsschalter: Env-Variable hat Vorrang vor ENABLED-Konstante
    env_enabled = os.environ.get("AUTO_TRIGGER_ENABLED", "").strip().lower()
    is_enabled = ENABLED or env_enabled in ("true", "1", "yes")

    if not is_enabled:
        print("⚠️  Auto-Trigger ist DEAKTIVIERT (ENABLED=False).")
        print("   Setze ENABLED=True oder AUTO_TRIGGER_ENABLED=true um live zu gehen.\n")

    # 1. Preise laden
    prices_data = load_json(PRICES_FILE, None)
    if not prices_data:
        print(f"❌ {PRICES_FILE} nicht gefunden oder leer.")
        sys.exit(1)

    fixtures = prices_data.get("allFixtures", [])
    generated_at = prices_data.get("generatedAt", "")
    print(f"  📋 {len(fixtures)} Fixtures geladen (Stand: {generated_at})")

    # 2. Bereits platzierte Bets laden
    placed_data = load_json(PLACED_FILE, {"bets": [], "updatedAt": ""})
    placed_bets = placed_data.get("bets", [])
    placed_keys = {b["betKey"] for b in placed_bets if b.get("betKey")}
    print(f"  ✅ {len(placed_keys)} bereits platzierte Bets geladen\n")

    # 3. Kandidaten finden
    print(f"  🔍 Suche nach Edge ≥ {AUTO_TRIGGER_EDGE_PP}pp, Vol ≥ {MIN_VOL:,}, Tage ≥ {MIN_DAYS_UNTIL_GAME}…")
    candidates = find_trigger_candidates(fixtures, placed_keys)

    if not candidates:
        print("  ℹ️  Keine neuen Trigger-Kandidaten gefunden.\n")
        return

    print(f"\n  🎯 {len(candidates)} Kandidat(en) gefunden:\n")
    for c in candidates:
        odds_str = f"{1/c['polyPrice']:.2f}" if c['polyPrice'] else "?"
        print(f"    • {c['home']} vs {c['away']} — {c['market']}")
        print(f"      Edge: +{c['edgePP']}pp  |  Poly: {odds_str}  |  Einsatz: ${c['stake']:.2f} USDC")

    if not is_enabled:
        print(f"\n⏸️  DEAKTIVIERT — {len(candidates)} Bet(s) würden platziert werden wenn aktiv.\n")
        return

    # 4. Bets platzieren via polymarket_bet.py
    private_key = os.environ.get("POLY_PRIVATE_KEY", "").strip()
    if not private_key:
        print("❌ POLY_PRIVATE_KEY nicht gesetzt — kann keine Bets platzieren.")
        sys.exit(1)

    telegram_token   = os.environ.get("TELEGRAM_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # Import der Betting-Funktionen aus polymarket_bet.py
    try:
        from polymarket_bet import (
            gamma_find_event,
            find_clob_token_id,
            gamma_find_winner_event,
            place_market_order,
            load_history,
            save_history,
            log_bet_to_history,
            # STAKE_USDC unused (per-bet stake comes from _get_stake_for_edge)
        )
    except ImportError as e:
        print(f"❌ Konnte polymarket_bet.py nicht importieren: {e}")
        sys.exit(1)

    history = load_history()
    new_placed = []

    for order in candidates:
        bet_key_val = order.pop("_betKey")  # intern, nicht an CLOB übergeben
        home   = order["home"]
        away   = order["away"]
        market = order["market"]
        stake  = order["stake"]
        poly_p = order["polyPrice"]

        print(f"\n  ▶ {home} vs {away} — {market}")

        # Gamma Event finden
        event = gamma_find_event(order)
        if not event:
            print(f"    ❌ Kein Polymarket-Event gefunden — übersprungen")
            continue

        print(f"    ✅ Event: {event.get('title')}")

        # CLOB Token ID
        token_id = find_clob_token_id(event, market, home, away)
        if not token_id:
            print(f"    ⚠️  Token nicht in Event — suche Winner-Event…")
            winner_event = gamma_find_winner_event(order, event)
            if winner_event:
                token_id = find_clob_token_id(winner_event, market, home, away)
        if not token_id:
            print(f"    ❌ CLOB Token ID nicht gefunden — übersprungen")
            continue

        print(f"    📍 Token: {token_id[:16]}…  |  Preis: {round(poly_p*100)}¢")

        # Order platzieren
        result = place_market_order(
            token_id, float(stake), private_key,
            price_hint=float(poly_p),
        )

        log_bet_to_history(history, order, result)

        if result["status"] in ("placed", "dry-run"):
            print(f"    ✅ Platziert — Order ID: {result.get('orderId')}")

            # 1. Bestehender WM-Channel (Operations-Info)
            if telegram_token and telegram_chat_id:
                odds_str = f"{1/poly_p:.2f}" if poly_p else "?"
                msg = (
                    f"🤖 <b>Auto-Bet ausgelöst</b>\n"
                    f"{home} vs {away} — {market}\n"
                    f"@ {odds_str} (edge +{order['edgePP']}pp)\n"
                    f"Einsatz: ${stake:.2f} USDC  |  Order: {result.get('orderId','?')}"
                )
                sent = send_telegram(telegram_token, telegram_chat_id, msg)
                if not sent:
                    print(f"    ⚠️  WM-Channel Nachricht konnte nicht gesendet werden")

            # 2. Dedizierter Trades-Channel (detailliert)
            try:
                from telegram_trades import notify_trade_opened
                notify_trade_opened(
                    home=home, away=away, market=market,
                    stake=stake, poly_price=poly_p,
                    edge_pp=order.get("edgePP"),
                    pinn_fair=order.get("pinnFair"),
                    order_id=result.get("orderId"),
                    source="auto",
                    home_id=order.get("homeId", ""),
                    away_id=order.get("awayId", ""),
                    slug=order.get("slug", ""),
                    dry_run=(result["status"] == "dry-run"),
                )
            except Exception as e:
                print(f"    ⚠️  Trades-Channel Fehler: {e}")

            new_placed.append({
                "betKey":    bet_key_val,
                "home":      home,
                "away":      away,
                "homeId":    order.get("homeId", ""),
                "awayId":    order.get("awayId", ""),
                "market":    market,
                "polyPrice": poly_p,
                "pinnFair":  order.get("pinnFair"),
                "edgePP":    order["edgePP"],
                "stake":     stake,
                "orderId":   result.get("orderId"),
                "status":    result["status"],
                "placedAt":  datetime.now(timezone.utc).isoformat(),
            })
        else:
            print(f"    ❌ Fehlgeschlagen: {result.get('error')}")

    # 5. Ergebnisse speichern
    if new_placed:
        placed_bets.extend(new_placed)
        placed_data["bets"] = placed_bets
        placed_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
        save_json(PLACED_FILE, placed_data)
        print(f"\n  💾 {len(new_placed)} neue Bet(s) in {PLACED_FILE} gespeichert")

        save_history(history)
        print(f"  💾 picks_history.json aktualisiert")

    print(f"\n{'='*55}")
    print(f"  Fertig — {len(new_placed)} Bet(s) platziert")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
