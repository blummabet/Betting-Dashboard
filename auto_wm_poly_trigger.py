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

AUTO_TRIGGER_EDGE_PP  = 4.0   # Mindest-Edge in Prozentpunkten (normale Signale)
                              # 01.06.2026: 5.0 → 4.0 nach Backtest (Sweet Spot 3-5pp lag bei +14% ROI)
STEAM_LAG_EDGE_PP    = 3.0   # Niedrigerer Schwellenwert wenn steamLag=True (Pinn bereits bewegt)
                              # 01.06.2026: Backtest zeigt Steam Lag schwächer als Normal, ABER:
                              # Sample n=7 zu klein für definitive Aussage. Lucas-Entscheidung:
                              # bei 3.0 lassen → mit Live-Daten nach 2-3 Wochen WM neu bewerten.
MIN_VOL              = 10000  # Mindest-Volumen auf Polymarket (USDC)
MIN_DAYS_UNTIL_GAME  = 1      # Nicht am Spieltag selbst — zu wenig Zeit für Human Review
MIN_HOURS_BEFORE_MATCH = 4   # Kein Kauf wenn Anpfiff in weniger als N Stunden

# ── Quote/Entry-Price Filter (eingebaut 03.06.2026) ───────────────────────────
# Schützt gegen Extrem-Quoten wo Variance + Spread den theoretischen Edge auffressen:
#   • Entry < 0.15 USD (Quote > 6.67): hohe Variance, 5+ Loser in Folge normal
#   • Entry > 0.85 USD (Quote < 1.18): nur 17% max Upside, ein Loser frisst 5 Wins
# Sweet Spot 0.15-0.85 = Quote 1.18-6.67 — Liquidität dicht, Spread klein.
MIN_ENTRY_PRICE      = 0.15
MAX_ENTRY_PRICE      = 0.85

# Stake: flat €5 ≈ $5.50 USDC pro Pick (entspricht STAKE_USDC in polymarket_bet.py).
# Memory-Eintrag project_poly_integration.md: "€5/Pick, flat" — keine Edge-basierte
# Tier-Logik mehr. Bankroll-Schutz via DAILY_BET_CAP + DAILY_STAKE_CAP_USDC unten.
FLAT_STAKE_USDC = 5.5

def _get_stake_for_edge(edge_pp: float) -> float:
    """Flat €5 ≈ $5.50 USDC pro Bet — Edge ist Schwellwert, nicht Sizing-Faktor."""
    return FLAT_STAKE_USDC

# ── Bankroll-Schutz ────────────────────────────────────────────────────────────
# Tageslimits verhindern dass viele Edges am Spieltag die ganze Bank durchfeuern.
DAILY_BET_CAP        = 8       # max Anzahl Bets pro UTC-Tag
DAILY_STAKE_CAP_USDC = 50.0    # max kumulativer Stake pro UTC-Tag in USDC
MIN_BALANCE_BUFFER   = 1.0     # USDC die nach Bet noch im Wallet bleiben müssen
MAX_POSITIONS_PER_MATCH = 2    # max Bets pro Match (egal welcher Markt)
                               # 2 = z.B. Über 2.5 + Heimsieg sind kompatible Wetten erlaubt.

# Open-Exposure-Cap: max kumulativer Stake in OFFENEN (nicht resolvierten) Positionen.
# Schützt gegen "Pre-Tournament Wallet-Lock": ohne diesen Cap würden Positionen aus 5-7 Tagen
# vor WM-Start die gesamte Bankroll binden, bevor erste Spielergebnisse Liquidität freigeben.
MAX_OPEN_EXPOSURE_USDC = 80.0  # 40% von $200 Test-Wallet bleibt immer als Reserve

# Pre-Tournament-Schwelle: für Spiele >5 Tage entfernt höhere Edge-Schwelle.
# Frühe Linien sind oft noch unsicher — Sharps geben dem Markt Zeit zur Korrektur.
PRE_TOURNAMENT_DAYS         = 5       # ab welcher Distanz zum Spiel "früh" gilt
PRE_TOURNAMENT_EDGE_PP      = 6.0     # höhere Schwelle für frühe Picks (statt 4.0)

# Adaptive Daily-Cap: skaliert mit verfügbarer Balance.
# effective_cap = min(DAILY_STAKE_CAP_USDC, available_balance × ADAPTIVE_DAILY_FRACTION)
# Bei $200 → $50 Cap. Bei $40 Balance → $16 Cap. Verhindert Restbankroll-Burn.
ADAPTIVE_DAILY_FRACTION     = 0.40    # max 40% der verfügbaren Balance pro Tag

BASE_DIR              = os.path.dirname(os.path.abspath(__file__))
PRICES_FILE           = os.path.join(BASE_DIR, "wm_poly_prices.json")
PLACED_FILE           = os.path.join(BASE_DIR, "wm_auto_bets_placed.json")
BALANCE_FILE          = os.path.join(BASE_DIR, "wm_poly_balance.json")
KILL_SWITCH_FILE      = os.path.join(BASE_DIR, "wm_kill_switch.json")


def is_kill_switch_active() -> tuple[bool, str]:
    """Liest wm_kill_switch.json. Returns (paused, reason).
    paused=True wenn Trading pausiert ist (enabled: false)."""
    if not os.path.exists(KILL_SWITCH_FILE):
        return False, ""
    try:
        with open(KILL_SWITCH_FILE, encoding="utf-8") as f:
            ks = json.load(f)
        if ks.get("enabled") is False:
            return True, ks.get("reason", "manuell pausiert")
        return False, ""
    except Exception as e:
        # Bei Lese-Fehler safer fallback: NICHT pausieren (sonst totes System bei Korruption)
        print(f"  ⚠️  Kill-Switch lesefehler: {e} — laufe trotzdem")
        return False, ""

# Welche Edge-Keys → Polymarket-Market-Label (muss OUTCOME_MAP in polymarket_bet.py matchen)
EDGE_MARKET_MAP = {
    "edge_hw":  ("poly_hw",  "Heimsieg",           "fair_hw",  "verdict_hw"),
    "edge_dr":  ("poly_dr",  "Unentschieden",       "fair_dr",  "verdict_dr"),
    "edge_aw":  ("poly_aw",  "Auswärtssieg",        "fair_aw",  "verdict_aw"),
    "edge_o25": ("poly_o25", "Over 2.5 Tore",       "fair_o25", "verdict_o25"),
    "edge_u25": ("poly_u25", "Under 2.5 Tore",      "fair_u25", "verdict_u25"),
}

# Nur diese Verdicts lösen Auto-Bets aus
# SKIP und None (kein Pick für diesen Markt) werden übersprungen
AUTO_TRIGGER_VERDICTS = {"BET", "ABWÄGEN"}

# elo_only = noch keine Form-/H2H-Daten (Pre-Tournament) → konservativerer Edge-Schwellenwert
# Erhöhter Schwellenwert verhindert Bets auf schwache Datenbasis
AUTO_TRIGGER_EDGE_ELO_ONLY = 8.0  # Strengerer Schwellenwert wenn nur Elo vorhanden


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


def hours_until(date_str: str) -> float | None:
    """Stunden bis zum Anpfiff (negativ = bereits angepfiffen)."""
    if not date_str:
        return None
    try:
        # Try full ISO datetime first (e.g. "2026-06-11T15:00:00Z")
        s = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        now = datetime.now(timezone.utc)
        return (dt - now).total_seconds() / 3600
    except Exception:
        # Fallback: date-only string → treat as midnight UTC
        try:
            game_date = date.fromisoformat(date_str[:10])
            days = (game_date - date.today()).days
            return days * 24.0
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

        # Timing-Check: kein Kauf am Spieltag selbst
        d = days_until(fix.get("date", ""))
        if d is None or d < MIN_DAYS_UNTIL_GAME:
            continue

        # Feineres Timing: kein Kauf wenn Anpfiff in < MIN_HOURS_BEFORE_MATCH Stunden
        h = hours_until(fix.get("date", ""))
        if h is not None and h < MIN_HOURS_BEFORE_MATCH:
            print(f"  ⏰ Zu nah am Anpfiff ({h:.1f}h): {fix.get('home')} vs {fix.get('away')} — übersprungen")
            continue

        # Data quality: elo_only → strengerer Edge-Schwellenwert
        is_elo_only = fix.get("dataQuality") == "elo_only"
        has_steam_lag = bool(fix.get("steamLag"))

        # Effektiver Edge-Schwellenwert:
        #  - steamLag=True: niedrigere Hürde (Pinn hat bereits bewegt → Signal ist valide)
        #  - elo_only: höhere Hürde (schwache Datenbasis)
        #  - normal: AUTO_TRIGGER_EDGE_PP
        if has_steam_lag:
            effective_edge_threshold = STEAM_LAG_EDGE_PP
        elif is_elo_only:
            effective_edge_threshold = AUTO_TRIGGER_EDGE_ELO_ONLY
        else:
            effective_edge_threshold = AUTO_TRIGGER_EDGE_PP

        # Pre-Tournament Edge-Verschärfung: wenn Spiel >5 Tage entfernt → höhere Schwelle
        if d is not None and d > PRE_TOURNAMENT_DAYS:
            effective_edge_threshold = max(effective_edge_threshold, PRE_TOURNAMENT_EDGE_PP)

        # Edge-Check für jeden Markt
        for edge_key, (price_key, market_label, fair_key, verdict_key) in EDGE_MARKET_MAP.items():
            edge = fix.get(edge_key)
            if edge is None or edge < effective_edge_threshold:
                continue

            # Verdict-Check: nur BET und ABWÄGEN — kein SKIP, kein None (kein Pick)
            verdict = fix.get(verdict_key)
            if verdict not in AUTO_TRIGGER_VERDICTS:
                if verdict is not None:
                    print(f"  🚫 Verdict={verdict} für {fix['home']} vs {fix['away']} — {market_label} (kein Trigger)")
                continue

            poly_price = fix.get(price_key)
            if not poly_price or poly_price <= 0:
                continue

            # ── Entry-Price-Filter ────────────────────────────────────────
            # Schutz gegen Extrem-Quoten: < 0.15 = zu viel Variance,
            # > 0.85 = zu wenig Upside, Spread frisst Edge.
            if poly_price < MIN_ENTRY_PRICE:
                print(f"  🚫 Entry-Price {poly_price:.3f} < {MIN_ENTRY_PRICE} (zu hohe Variance) "
                      f"— {fix['home']} vs {fix['away']} {market_label}")
                continue
            if poly_price > MAX_ENTRY_PRICE:
                print(f"  🚫 Entry-Price {poly_price:.3f} > {MAX_ENTRY_PRICE} (Upside zu klein) "
                      f"— {fix['home']} vs {fix['away']} {market_label}")
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
                "home":        fix["home"],
                "away":        fix["away"],
                "homeId":      fix.get("homeId", ""),
                "awayId":      fix.get("awayId", ""),
                "market":      market_label,
                "league":      "WM2026",
                "stake":       _get_stake_for_edge(edge),
                "polyPrice":   poly_price,
                "slug":        slug,
                "eventUrl":    event_url,
                "edgePP":      edge,
                "pinnFair":    fix.get(fair_key),
                "verdict":     verdict,
                "dataQuality": fix.get("dataQuality", "elo_only"),
                "isSteamLag":  has_steam_lag,
                "matchDate":   (fix.get("date") or "")[:10],
                "_betKey":     key,   # intern, wird vor Übergabe an polymarket_bet entfernt
            })

    return candidates


def main():
    print(f"\n{'='*55}")
    print(f"  🤖 WM 2026 Auto-Trigger — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}\n")

    # Kill-Switch zuerst prüfen — hat Vorrang vor allen anderen Schaltern
    killed, kill_reason = is_kill_switch_active()
    if killed:
        print(f"🛑 KILL-SWITCH AKTIV — Trading pausiert.")
        print(f"   Grund: {kill_reason}")
        print(f"   Resume via GitHub Action 'Kill-Switch' → action=resume\n")
        return

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
    # Match-Level Dedup: zähle wie viele Bets schon auf jedes Match liegen
    # (egal welcher Markt). Verhindert gegenläufige Heim+Auswärts-Positionen.
    match_position_count = {}
    for b in placed_bets:
        mkey = f"{b.get('homeId','')}-{b.get('awayId','')}"
        match_position_count[mkey] = match_position_count.get(mkey, 0) + 1
    print(f"  ✅ {len(placed_keys)} bereits platzierte Bets geladen "
          f"(auf {len(match_position_count)} verschiedenen Matches)")

    # 2b. Bankroll-Schutz: heutige Bets zählen + Balance prüfen
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bets_today = [b for b in placed_bets if (b.get("placedAt") or "")[:10] == today_str]
    stake_today = sum(float(b.get("stake") or 0) for b in bets_today)
    print(f"  💰 Heute bereits platziert: {len(bets_today)} Bet(s), ${stake_today:.2f} USDC")

    # Open-Exposure: kumulativer Stake aller noch nicht aufgelösten Positionen
    open_bets = [b for b in placed_bets
                 if not b.get("resolved") and not b.get("soldAt")]
    open_exposure = sum(float(b.get("stake") or 0) for b in open_bets)
    print(f"  📈 Open Exposure: {len(open_bets)} Position(en), ${open_exposure:.2f} USDC")

    # Aktuelle Balance laden (wird vor diesem Skript via fetch_wm_poly_balance.py geholt)
    balance_data = load_json(BALANCE_FILE, {"usdc": 0.0})
    available_balance = float(balance_data.get("usdc") or 0)
    print(f"  💼 Verfügbare Balance: ${available_balance:.2f} USDC")

    # Adaptive Daily-Cap: skaliert mit Balance — schützt letzte Reserven
    adaptive_daily_cap = min(
        DAILY_STAKE_CAP_USDC,
        available_balance * ADAPTIVE_DAILY_FRACTION
    )
    print(f"  ⚙️  Adaptive Daily-Cap: ${adaptive_daily_cap:.2f} USDC ({int(ADAPTIVE_DAILY_FRACTION*100)}% × Balance)\n")

    if len(bets_today) >= DAILY_BET_CAP:
        print(f"  🛑 Tageslimit erreicht ({len(bets_today)}/{DAILY_BET_CAP} Bets) — Abbruch.\n")
        return
    if stake_today >= adaptive_daily_cap:
        print(f"  🛑 Adaptive Stake-Cap erreicht (${stake_today:.2f}/${adaptive_daily_cap:.2f}) — Abbruch.\n")
        return
    if open_exposure >= MAX_OPEN_EXPOSURE_USDC:
        print(f"  🛑 Open-Exposure-Cap erreicht (${open_exposure:.2f}/${MAX_OPEN_EXPOSURE_USDC:.2f}) — warte auf Close.\n")
        return


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

    telegram_token   = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    # Privacy-Fix 05.06.2026 (K2): Auto-Bet-Alerts mit Stake-Größen + Order-IDs
    # gehen NUR an den Trades-Channel (privat), nicht an den öffentlichen Channel.
    telegram_chat_id = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()

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

    # Running tally für Bankroll-Schutz innerhalb dieses Runs
    running_count    = len(bets_today)
    running_stake    = stake_today
    running_balance  = available_balance
    running_exposure = open_exposure

    for order in candidates:
        bet_key_val = order.pop("_betKey")  # intern, nicht an CLOB übergeben
        home   = order["home"]
        away   = order["away"]
        market = order["market"]
        stake  = order["stake"]
        poly_p = order["polyPrice"]

        print(f"\n  ▶ {home} vs {away} — {market}")

        # ── Match-Level Dedup ────────────────────────────────────────────────
        # Prüft ob auf dieses Match (egal welcher Markt) bereits genug Positionen
        # liegen. Verhindert z.B. Heimsieg+Auswärtssieg auf dasselbe Match.
        match_key = f"{order.get('homeId','')}-{order.get('awayId','')}"
        if match_position_count.get(match_key, 0) >= MAX_POSITIONS_PER_MATCH:
            print(f"    🚫 Bereits {match_position_count[match_key]}/{MAX_POSITIONS_PER_MATCH} Position(en) auf diesem Match — übersprungen")
            continue

        # ── Bankroll-Schutz pro Iteration ────────────────────────────────────
        if running_count >= DAILY_BET_CAP:
            print(f"    🛑 Tages-Bet-Cap erreicht ({running_count}/{DAILY_BET_CAP}) — Rest übersprungen")
            break
        if running_stake + stake > adaptive_daily_cap:
            print(f"    🛑 Adaptive Stake-Cap würde überschritten (${running_stake + stake:.2f} > ${adaptive_daily_cap:.2f}) — übersprungen")
            continue
        if running_exposure + stake > MAX_OPEN_EXPOSURE_USDC:
            print(f"    🛑 Open-Exposure-Cap würde überschritten (${running_exposure + stake:.2f} > ${MAX_OPEN_EXPOSURE_USDC:.2f}) — übersprungen")
            continue
        if running_balance - stake < MIN_BALANCE_BUFFER:
            print(f"    🛑 Balance zu niedrig (${running_balance:.2f} - ${stake:.2f} < ${MIN_BALANCE_BUFFER:.2f}) — Abbruch")
            if telegram_token and telegram_chat_id:
                send_telegram(
                    telegram_token, telegram_chat_id,
                    f"⚠️ <b>Polymarket Bankroll niedrig</b>\n"
                    f"Balance: ${running_balance:.2f} USDC — bitte nachladen.\n"
                    f"{len(candidates) - len(new_placed)} Bet(s) übersprungen."
                )
            break

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

        # Schätze Anzahl der YES-Tokens (Stake / Preis) — wird für Sell gebraucht
        shares_estimate = round(stake / poly_p, 4) if poly_p > 0 else 0.0

        # Order platzieren
        result = place_market_order(
            token_id, float(stake), private_key,
            price_hint=float(poly_p),
        )

        log_bet_to_history(history, order, result)

        is_steam = order.get("isSteamLag", False)
        steam_tag = " 🔥 SteamLag" if is_steam else ""

        if result["status"] in ("placed", "dry-run"):
            print(f"    ✅ Platziert — Order ID: {result.get('orderId')}{steam_tag}")

            # Bankroll-Tally + Match-Position-Tally updaten
            running_count    += 1
            running_stake    += stake
            running_balance  -= stake
            running_exposure += stake
            match_position_count[match_key] = match_position_count.get(match_key, 0) + 1

            # Privacy-Fix 05.06.2026 (K2): Der frühere doppelte Push an Haupt+Trades
            # ist entfernt. Auto-Bet-Bestätigungen gehen NUR über telegram_trades
            # an den privaten Trades-Channel. Keine Stake/Order-Daten im Public-Channel.
            try:
                from telegram_trades import notify_trade_opened
                notify_trade_opened(
                    home=home, away=away, market=market,
                    stake=stake, poly_price=poly_p,
                    edge_pp=order.get("edgePP"),
                    pinn_fair=order.get("pinnFair"),
                    order_id=result.get("orderId"),
                    source="auto_steam" if is_steam else "auto",
                    home_id=order.get("homeId", ""),
                    away_id=order.get("awayId", ""),
                    slug=order.get("slug", ""),
                    dry_run=(result["status"] == "dry-run"),
                )
            except Exception as e:
                print(f"    ⚠️  Trades-Channel Fehler: {e}")

            new_placed.append({
                "betKey":         bet_key_val,
                "home":           home,
                "away":           away,
                "homeId":         order.get("homeId", ""),
                "awayId":         order.get("awayId", ""),
                "market":         market,
                "polyPrice":      poly_p,
                "pinnFair":       order.get("pinnFair"),
                "edgePP":         order["edgePP"],
                "stake":          stake,
                "orderId":        result.get("orderId"),
                "status":         result["status"],
                "placedAt":       datetime.now(timezone.utc).isoformat(),
                # ── Fields needed for auto-sell ──────────────────────
                "tokenId":        token_id,
                "matchDate":      order.get("matchDate", ""),
                "sharesEstimate": shares_estimate,
                "isSteamLag":     is_steam,
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
