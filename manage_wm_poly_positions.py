#!/usr/bin/env python3
"""
manage_wm_poly_positions.py
Überwacht offene WM 2026 Polymarket-Positionen und löst Sell-Alerts aus.

Workflow:
  1. Lädt wm_poly_positions.json (manuell geloggte Positionen)
  2. Holt aktuelle Preise via Gamma API für jede Position
  3. Berechnet P&L und prüft Sell-Schwellwerte
  4. Sendet Telegram-Alert mit Sell-Link wenn Schwellwert erreicht
  5. Aktualisiert wm_poly_positions.json mit Status

Sell-Logik:
  PRIMARY:   currentPrice >= entryPrice × (1 + PROFIT_TARGET)      [+20% Profit]
  SECONDARY: currentPrice >= pinnFair - PINN_GAP_PP / 100          [Poly konvergiert]
  HARD-HOLD: Wenn Spiel noch nicht gestartet und kein Profit → halten

Run:  python3 manage_wm_poly_positions.py
Cron: .github/workflows/manage-wm-poly.yml — 5x täglich
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, date

from telegram_trades import is_auto_source  # Single Source: auto vs manual (deckt auto_steam)

BASE           = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE, "wm_poly_positions.json")
AUTO_BETS_FILE = os.path.join(BASE, "wm_auto_bets_placed.json")
PRICES_FILE    = os.path.join(BASE, "wm_poly_prices.json")

# Auto-Bet market label → Gamma API price key
MARKET_TO_PRICE_KEY = {
    "Heimsieg":        "hw",
    "Auswärtssieg":    "aw",
    "Unentschieden":   "dr",
    "Over 2.5 Tore":   "o25",
    "Under 2.5 Tore":  "u25",
}

TELEGRAM_TOKEN          = (os.getenv("TELEGRAM_TOKEN") or "").strip()
# WICHTIG: Sell-Alerts mit P&L-Daten gehen NUR an Trades-Channel (privat),
# NICHT an den öffentlichen CocoBet-Hauptchannel. Privacy-Fix 05.06.2026 (K1).
# AUDIT-Fix 08.06.2026: Legacy-Alias TELEGRAM_CHAT_ID entfernt — alle Sender hier
# nutzen explizit TELEGRAM_TRADES_CHAT_ID. Keine Verwechslungs-Gefahr mehr.
TELEGRAM_TRADES_CHAT_ID = (os.getenv("TELEGRAM_TRADES_CHAT_ID") or "").strip()

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
# Backwards-compatible: Code-Defaults greifen wenn cocobet_config crash.
# WM2026-Profil liefert exakt die Pre-Refactor-Werte — verifiziert per Test.
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# ── Sell-Schwellwerte ─────────────────────────────────────────────────────────
# 01.06.2026: PROFIT_TARGET 0.20 → 0.10 (schnellerer Cash-Cycle, gemessen).
# PINN_GAP von 2.0 → 1.5 angepasst, MIN_PROFIT_PP als Schutz für Secondary.
PROFIT_TARGET   = _cfg("sell", "profit_target", 0.10)
PINN_GAP_PP     = _cfg("sell", "pinn_gap_pp",   1.5)
MIN_PROFIT_PP   = _cfg("sell", "min_profit_pp", 0.03)

# Age-Decay: ältere Positionen sollen Cash freimachen — auch bei kleinem Profit schließen
AGE_DECAY_HOURS         = _cfg("sell", "age_decay_hours",         48)
AGE_DECAY_PROFIT_TARGET = _cfg("sell", "age_decay_profit_target", 0.05)

# ── LOSS-Trigger ──────────────────────────────────────────────────────────────
# Eingebaut 03.06.2026 — verhindert dass Positionen ins Minus ausgesessen werden.
# Profi-Konsens: event-getriebene Loss-Stops, keine Panik bei normalem Marktrauschen.

# 1. SHARP-AGAINST: Pinnacle pricet die Wahrscheinlichkeit ≥7pp UNTER unserem Entry
#    → Sharps denken das Outcome ist deutlich unwahrscheinlicher als wir gekauft haben
#    → wahrscheinlich gibt's neue Info die wir nicht eingepreist haben → raus
SHARP_AGAINST_GAP_PP   = _cfg("sell", "sharp_against_gap_pp", 7.0)

# 2. DEEP-LOSS + viel Zeit: Position 40% unter Entry, Match noch ≥12h weg
#    → Opportunitätskosten: Bankroll besser anderswo allokieren
LOSS_DEEP_PCT          = _cfg("sell", "loss_deep_pct",         0.40)
LOSS_DEEP_HOURS_AHEAD  = _cfg("sell", "loss_deep_hours_ahead", 12.0)

# 3. AGE-LOSS: alte Position + im Minus → realisieren bevor Spread alles frisst
AGE_LOSS_HOURS         = _cfg("sell", "age_loss_hours",         36.0)
AGE_LOSS_THRESHOLD_PCT = _cfg("sell", "age_loss_threshold_pct", 0.10)

# 4. NEVER IN-PLAY: Live-Phase = kein Loss-Trigger (Polymarket-Live-Liquidität zu mies)
NO_INPLAY_LOSS_SELL    = _cfg("sell", "no_inplay_loss_sell", True)

# ── Auto-Sell Konfiguration ───────────────────────────────────────────────────
# AUTO_SELL_ENABLED bleibt bewusst HARDCODE: Safety-Master-Switch, nur per
# explizitem Code-Edit oder ENV=true aktivierbar (verhindert versehentliches
# Live-Trading durch Config-Tippfehler). Verhalten unverändert.
AUTO_SELL_ENABLED     = False

# Hard-Close Stunden vor Anpfiff — bereits in trade-section (von auto_trigger).
# 05.06.2026: von 6 → 2 verschoben (Lineups 60-90min vor Anpfiff, Sharp-Moves 2-4h vor KO).
PRE_MATCH_CLOSE_HOURS = _cfg("trade", "pre_match_close_hours", 2)

# ── Gamma API ────────────────────────────────────────────────────────────────
GAMMA_URL = "https://gamma-api.polymarket.com/events?slug={slug}"


def hours_until_match(match_date_str: str) -> float | None:
    """Stunden bis zum Anpfiff. Negativ = bereits gespielt."""
    if not match_date_str:
        return None
    try:
        s = match_date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    except Exception:
        try:
            game_date = date.fromisoformat(match_date_str[:10])
            return (game_date - date.today()).days * 24.0
        except Exception:
            return None


def _http_get(url: str) -> dict | list | None:
    headers = {"User-Agent": "BetEdge/1.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  HTTP error {url}: {e}")
        return None


def send_telegram(text: str) -> bool:
    """
    Sendet eine Nachricht an den TRADES-Channel (privat).
    Sell-Alerts enthalten P&L-Daten — diese DÜRFEN NIE an den öffentlichen
    CocoBet-Hauptchannel gehen. Privacy-Fix 05.06.2026 (K1).
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_TRADES_CHAT_ID:
        print(f"  [Telegram-Trades] {text[:120]}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_TRADES_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


def load_positions() -> dict:
    if not os.path.exists(POSITIONS_FILE):
        return {"positions": [], "updatedAt": ""}
    with open(POSITIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_positions(data: dict):
    data["updatedAt"] = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_current_price(slug: str, market_key: str, match_key: str = "") -> float | None:
    """
    Holt aktuellen Polymarket-Preis für ein Spiel via Gamma API.
    market_key: 'hw' | 'dr' | 'aw' | 'o25' | 'u25'
    match_key:  'GHA-PAN' (homeId-awayId) — Primär-Lookup im prices-Cache.

    FIX 09.06.2026 — vier Bugs hintereinander:
      (1) Cache-Lookup nutzte `entry.get(market_key)`, aber die Cache-Keys
          sind `poly_hw/poly_dr/poly_aw/poly_o25/poly_u25` — Präfix nötig.
      (2) Slug-Match scheitert bei O/U, weil Auto-Bets `moreMktSlug` haben
          (separater Polymarket-Event), nicht den Moneyline-Slug.
      (3) Leerer Slug → kein API-Call mit slug="", sondern None.
      (4) Auto-Bets aus 09.06. haben weder slug noch moreMktSlug gespeichert
          (Schreib-Bug im Trigger). Daher Primär-Lookup via match_key
          (homeId-awayId), das ist der Dict-Key in prices.
    """
    cache_key = f"poly_{market_key}"

    # Primär: direkter Lookup via match_key in prices-Dict
    if match_key and os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        entry = cached.get("prices", {}).get(match_key)
        if entry:
            price = entry.get(cache_key) or entry.get(market_key)
            if price:
                return float(price)

    # Sekundär: Slug-basierte Suche (für ältere Bets mit slug aber ohne match_key)
    if slug and os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        prices = cached.get("prices", {})
        for key, entry in prices.items():
            if entry.get("slug") == slug or entry.get("moreMktSlug") == slug:
                price = entry.get(cache_key) or entry.get(market_key)
                if price:
                    return float(price)

    if not slug:
        return None

    # Fallback: direkt von Gamma API holen — nur für moneyline, O/U-Endpoint
    # hat anderes Schema und wird vom Cache abgedeckt
    if market_key not in ("hw", "dr", "aw"):
        return None
    data = _http_get(GAMMA_URL.format(slug=slug))
    if not data or not isinstance(data, list) or not data:
        return None

    event = data[0]
    key_to_threshold = {"hw": "0", "dr": "1", "aw": "2"}
    target = key_to_threshold.get(market_key)

    for m in event.get("markets", []):
        if str(m.get("groupItemThreshold", "")) == target:
            prices = json.loads(m.get("outcomePrices", "[]") or "[]")
            return float(prices[0]) if prices else None
    return None


def check_position(pos: dict) -> dict:
    """
    Prüft eine offene Position und gibt ein Dict mit Status zurück.
    Setzt pos['currentPrice'], pos['pnlPct'], pos['sellReason'] etc.
    """
    slug       = pos.get("slug", "")
    market_key = pos.get("priceKey", "hw")  # hw/dr/aw
    entry      = pos.get("entryPrice", 0)
    pinn_fair  = pos.get("pinnFair", None)
    # match_key (homeId-awayId) ist Primär-Lookup im prices-Cache
    match_key  = f"{pos.get('homeId','')}-{pos.get('awayId','')}".strip("-")

    current = fetch_current_price(slug, market_key, match_key)
    if current is None:
        pos["currentPrice"] = None
        pos["pnlPct"] = None
        pos["sellSignal"] = False
        pos["sellReason"] = "Preis nicht abrufbar"
        return pos

    pos["currentPrice"] = round(current, 4)

    # P&L
    if entry and entry > 0:
        pnl_pct  = (current - entry) / entry * 100
        pnl_pp   = (current - entry) * 100
        pos["pnlPct"] = round(pnl_pct, 1)
        pos["pnlPP"]  = round(pnl_pp, 1)
    else:
        pnl_pct = 0
        pos["pnlPct"] = None
        pos["pnlPP"]  = None

    # Sell-Check
    sell  = False
    reason = ""

    # ── Hilfs-Variablen für alle Trigger ──────────────────────────────────────
    # Age (Stunden seit placed)
    age_h = None
    placed_at = pos.get("placedAt") or ""
    if placed_at:
        try:
            from datetime import datetime as _dt
            placed_dt = _dt.fromisoformat(placed_at.replace("Z", "+00:00"))
            age_h = (_dt.now(timezone.utc) - placed_dt).total_seconds() / 3600
        except Exception:
            age_h = None

    # Hours bis Kickoff (negativ = bereits gestartet)
    hours_left = hours_until_match(pos.get("matchDate", ""))
    in_play = hours_left is not None and hours_left <= 0

    # ── PROFIT-Trigger (PRIMARY/SECONDARY/TERTIARY) ───────────────────────────
    # Pre-Match-only-Guard (11.06.2026): Profit-Mitnahme nur VOR Anpfiff. Sobald
    # ein Spiel läuft (in_play), schließt Auto-Sell keine Positionen mehr zu
    # volatilen In-Game-Preisen — konsistent mit dem Loss-Trigger (NO_INPLAY_LOSS_SELL)
    # und der Pre-Match-Close-Logik. Einziger erlaubter KO-naher Exit bleibt der
    # 2h-Hard-Close (is_pre_match_close, stoppt bei h_until=0).
    if not in_play:
        # PRIMARY: +10% Profit (Cash-Cycle Optimierung)
        if entry > 0 and current >= entry * (1 + PROFIT_TARGET):
            sell = True
            reason = f"Profit +{round(pnl_pct, 1)}% ≥ +{PROFIT_TARGET*100:.0f}% Ziel"

        # SECONDARY: Poly konvergiert zu Pinnacle fair (innerhalb PINN_GAP_PP)
        if not sell and pinn_fair and (current - entry) * 100 >= MIN_PROFIT_PP * 100:
            gap = (pinn_fair - current) * 100
            if gap <= PINN_GAP_PP:
                sell = True
                reason = f"Markt konvergiert: Poly {current:.3f} ≈ Pinn fair {pinn_fair:.3f} (Δ{gap:.1f}pp)"

        # TERTIARY: Age-Decay — alte Position + kleiner Profit reicht
        if not sell and entry > 0 and age_h is not None and age_h >= AGE_DECAY_HOURS:
            if current >= entry * (1 + AGE_DECAY_PROFIT_TARGET):
                sell = True
                reason = f"Age-Decay: Position {age_h:.0f}h alt, +{round(pnl_pct, 1)}% ≥ +{AGE_DECAY_PROFIT_TARGET*100:.0f}% reicht"

    # ── LOSS-Trigger (NUR wenn kein Profit-Sell + nicht In-Play) ──────────────
    skip_loss = sell or (NO_INPLAY_LOSS_SELL and in_play) or entry <= 0
    if not skip_loss:
        loss_pct = (current / entry - 1)   # negativ wenn underwater

        # LOSS 1: SHARP-AGAINST
        # Pinnacle pricet jetzt ≥7pp UNTER unserem Entry-Preis
        # → Sharps haben ihre Erwartung deutlich gesenkt → neue Info
        if pinn_fair and (entry - pinn_fair) * 100 >= SHARP_AGAINST_GAP_PP and current < entry:
            sell = True
            gap = (entry - pinn_fair) * 100
            reason = (f"Sharps gegen uns: Pinnacle fair {pinn_fair:.3f} "
                      f"ist {gap:.1f}pp UNTER unserem Entry {entry:.3f} "
                      f"({round(pnl_pct,1)}% PnL)")

        # LOSS 2: DEEP-LOSS + viel Zeit zum Kickoff
        # → Position ist 40%+ underwater UND noch genug Zeit zur Re-Allokation
        elif (loss_pct <= -LOSS_DEEP_PCT
              and hours_left is not None
              and hours_left >= LOSS_DEEP_HOURS_AHEAD):
            sell = True
            reason = (f"Deep-Loss: {round(pnl_pct,1)}% ≤ -{LOSS_DEEP_PCT*100:.0f}%, "
                      f"noch {hours_left:.1f}h bis Kickoff — Bankroll re-allokieren")

        # LOSS 3: AGE-LOSS — alte Position + im Minus
        # → Spread frisst sonst Buchwert, lieber realisieren
        elif (age_h is not None
              and age_h >= AGE_LOSS_HOURS
              and loss_pct <= -AGE_LOSS_THRESHOLD_PCT):
            sell = True
            reason = (f"Age-Loss: Position {age_h:.0f}h alt, "
                      f"{round(pnl_pct,1)}% im Minus — Spread frisst Buchwert")

    pos["sellSignal"] = sell
    pos["sellReason"] = reason if sell else ""
    return pos


def format_sell_alert(pos: dict) -> str:
    home     = pos.get("home", "")
    away     = pos.get("away", "")
    market   = pos.get("market", "")
    stake    = pos.get("stake", 0)
    entry    = pos.get("entryPrice", 0)
    current  = pos.get("currentPrice", 0)
    pnl_pct  = pos.get("pnlPct", 0)
    entry_p  = pos.get("entryPrice") or 0
    pnl_eur  = round(stake * (current / entry_p - 1), 2) if (entry_p > 0 and current) else 0
    reason   = pos.get("sellReason", "")
    slug     = pos.get("slug", "")
    url      = f"https://polymarket.com/de/sports/fifa-world-cup/{slug}" if slug else ""

    sign     = "🟢" if (pnl_pct or 0) > 0 else "🔴"
    sell_link = f'<a href="{url}">🔗 Auf Polymarket verkaufen →</a>' if url else ""
    return (
        f"🏆 <b>WM 2026 Polymarket — SELL SIGNAL</b>\n"
        f"{sign} <b>{home} vs {away} — {market}</b>\n\n"
        f"📈 Einstieg: {entry:.3f} ({round(1/entry,2)}x)\n"
        f"💹 Aktuell:  {current:.3f} ({round(1/current,2) if current else '?'}x)\n"
        f"💰 P&L: <b>{'+' if (pnl_pct or 0)>=0 else ''}{pnl_pct}%"
        f" (~{'+' if pnl_eur>=0 else ''}{pnl_eur}€)</b>\n\n"
        f"✅ Grund: {reason}\n\n"
        f"{sell_link}"
    )


def load_auto_bets_as_positions() -> list:
    """
    Lädt wm_auto_bets_placed.json und konvertiert 'placed'-Bets
    in das Positions-Format (kompatibel mit check_position).
    Nur Bets mit status='placed' werden mitgezogen (nicht dry-run).
    """
    if not os.path.exists(AUTO_BETS_FILE):
        return []
    try:
        with open(AUTO_BETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  Fehler beim Laden von wm_auto_bets_placed.json: {e}")
        return []

    positions = []
    for bet in data.get("bets", []):
        if bet.get("status") != "placed":
            continue
        market = bet.get("market", "")
        price_key = MARKET_TO_PRICE_KEY.get(market, "hw")
        positions.append({
            "home":           bet.get("home", ""),
            "away":           bet.get("away", ""),
            "homeId":         bet.get("homeId", ""),
            "awayId":         bet.get("awayId", ""),
            "market":         market,
            "slug":           bet.get("slug", ""),
            "priceKey":       price_key,
            "entryPrice":     bet.get("polyPrice", 0),
            "pinnFair":       bet.get("pinnFair"),
            "stake":          bet.get("stake", 0),
            "status":         "open",
            "source":         "auto",
            "_betKey":        bet.get("betKey", ""),
            "placedAt":       bet.get("placedAt", ""),
            # ── Auto-sell fields ─────────────────────────────────
            "tokenId":        bet.get("tokenId", ""),
            "sharesEstimate": bet.get("sharesEstimate", 0.0),
            "matchDate":      bet.get("matchDate", ""),
            "isSteamLag":     bet.get("isSteamLag", False),
        })
    return positions


def execute_auto_sell(pos: dict, private_key: str, reason: str) -> dict:
    """
    Führt einen automatischen Sell-Order via CLOB aus.
    Nutzt place_sell_order() aus polymarket_bet.py.
    Gibt result-dict zurück: {"status": "placed"/"failed", "orderId": ..., "error": ...}
    """
    token_id = pos.get("tokenId", "")
    shares   = pos.get("sharesEstimate", 0.0)
    current  = pos.get("currentPrice") or pos.get("entryPrice") or 0.0

    if not token_id:
        return {"status": "failed", "orderId": None,
                "error": "tokenId fehlt — kann nicht verkaufen"}
    if shares <= 0:
        return {"status": "failed", "orderId": None,
                "error": f"sharesEstimate ungültig ({shares})"}

    try:
        from polymarket_bet import place_sell_order
    except ImportError as e:
        return {"status": "failed", "orderId": None,
                "error": f"polymarket_bet import fehlgeschlagen: {e}"}

    print(f"    💸 AUTO-SELL: {shares} Tokens @ {current:.3f} — Grund: {reason}")
    result = place_sell_order(
        token_id=token_id,
        size=shares,
        private_key=private_key,
        price_hint=float(current) if current else None,
    )
    return result


def update_auto_bet_status(bet_key: str, new_status: str,
                           sell_result: dict, current_price: float,
                           sell_reason: str) -> None:
    """
    Aktualisiert den Status eines Auto-Bets in wm_auto_bets_placed.json nach einem Sell.
    """
    if not os.path.exists(AUTO_BETS_FILE):
        return
    try:
        with open(AUTO_BETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  Fehler beim Lesen von wm_auto_bets_placed.json: {e}")
        return

    for bet in data.get("bets", []):
        if bet.get("betKey") == bet_key:
            bet["status"]      = new_status
            bet["soldAt"]      = datetime.now(timezone.utc).isoformat()
            bet["sellPrice"]   = current_price
            bet["sellOrderId"] = sell_result.get("orderId")
            bet["sellError"]   = sell_result.get("error")
            bet["sellReason"]  = sell_reason
            break

    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    with open(AUTO_BETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=== manage_wm_poly_positions.py ===")
    now = datetime.now(timezone.utc)
    print(f"  {now.strftime('%d.%m.%Y %H:%M UTC')}")

    # Sicherheitsschalter: Auto-Sell aktiviert?
    env_sell = os.getenv("AUTO_SELL_ENABLED", "").strip().lower()
    auto_sell_on = AUTO_SELL_ENABLED or env_sell in ("true", "1", "yes")

    private_key = os.getenv("POLY_PRIVATE_KEY", "").strip()
    if auto_sell_on and not private_key:
        print("⚠️  AUTO_SELL_ENABLED=true aber POLY_PRIVATE_KEY fehlt — Auto-Sell deaktiviert!")
        auto_sell_on = False

    if auto_sell_on:
        print(f"  🟢 Auto-Sell AKTIV (Pre-Match Close ≤ {PRE_MATCH_CLOSE_HOURS}h)")
    else:
        print(f"  🔴 Auto-Sell INAKTIV (nur Alerts)")

    data = load_positions()
    positions = data.get("positions", [])

    # Auto-Bets aus wm_auto_bets_placed.json dazuladen
    auto_positions = load_auto_bets_as_positions()
    if auto_positions:
        print(f"  {len(auto_positions)} Auto-Bet(s) aus wm_auto_bets_placed.json geladen")

    all_positions = positions + auto_positions

    # ── FIX 13.06.2026: echte Anpfiffzeit auflösen (KRITISCH) ────────────────
    # Auto-Bets speichern nur `matchDate` (Datum, 00:00 Uhr), kein kickoff. Dadurch
    # hielt hours_until_match JEDES Abendspiel schon ab Mitternacht für „bereits
    # gestartet" (h_until negativ) → der 2h-Pre-Match-Hard-Close feuerte NIE und der
    # In-Play-Guard blockte den Verkauf → Trade rutschte LIVE ins In-Play (QAT-SUI
    # 13.06., offen während des Spiels). Lösung: Kickoff (UTC) aus wm2026-data.json je
    # HOME-AWAY ziehen und matchDate damit überschreiben — wirkt für check_position
    # (in_play) UND den Pre-Match-Close. Deckt bestehende offene Bets + künftige ab.
    try:
        _wm = json.load(open(os.path.join(BASE, "wm2026-data.json"), encoding="utf-8"))
        _ko_map = {}
        for _g in (_wm.get("groups") or {}).values():
            for _fx in (_g.get("fixtures") or []):
                _k = _fx.get("kickoff")
                if _k:
                    _ko_map[f"{_fx.get('home')}-{_fx.get('away')}"] = _k
        _fixed = 0
        for p in all_positions:
            rk = p.get("kickoff") or _ko_map.get(f"{p.get('homeId')}-{p.get('awayId')}")
            if rk and rk != p.get("matchDate"):
                p["matchDate"] = rk
                _fixed += 1
        if _fixed:
            print(f"  🕐 {_fixed} Position(en) auf echte Anpfiffzeit normalisiert")
    except Exception as _e:
        print(f"  ⚠️  Kickoff-Auflösung fehlgeschlagen (nutze matchDate): {_e}")

    if not all_positions:
        print("  Keine offenen Positionen.")
        return

    open_pos = [p for p in all_positions if p.get("status") == "open"]
    print(f"  {len(open_pos)} offene Positionen gefunden")

    alerts_sent = 0
    sells_executed = 0

    for pos in open_pos:
        home   = pos.get("home", "?")
        away   = pos.get("away", "?")
        market = pos.get("market", "?")
        # FIX 15.06.2026: Steam-Lag-Auto-Bets haben source="auto_steam" — der frühere
        # exakte ==-Vergleich schloss sie vom Auto-Sell aus (blieben ewig sell_signaled,
        # nie beim Pre-Match-Close verkauft). is_auto_source deckt jede auto_*-Variante.
        is_auto = is_auto_source(pos.get("source"))
        print(f"\n  Prüfe: {home} vs {away} — {market}")

        check_position(pos)

        current = pos.get("currentPrice")
        pnl     = pos.get("pnlPct")
        print(f"    Entry: {pos.get('entryPrice')} | Aktuell: {current} | P&L: {pnl}%")

        # ── Pre-match close check ─────────────────────────────────────────────
        match_date = pos.get("matchDate", "")
        h_until = hours_until_match(match_date) if match_date else None
        is_pre_match_close = (
            h_until is not None and 0 <= h_until <= PRE_MATCH_CLOSE_HOURS
        )
        if is_pre_match_close:
            print(f"    ⏰ PRE-MATCH CLOSE: Anpfiff in {h_until:.1f}h — schließe Position")

        # Sell-Signal oder Pre-Match Close → handeln
        should_sell = pos.get("sellSignal") or is_pre_match_close
        sell_reason = pos.get("sellReason") or (
            f"Pre-Match Close ({h_until:.1f}h vor Anpfiff)" if is_pre_match_close else ""
        )

        if should_sell:
            print(f"    🚨 SELL: {sell_reason}")

            # ── Auto-Sell ausführen (wenn aktiviert + tokenId vorhanden) ─────
            sell_executed = False
            if auto_sell_on and is_auto and pos.get("tokenId"):
                sell_result = execute_auto_sell(pos, private_key, sell_reason)
                if sell_result["status"] == "placed":
                    print(f"    ✅ AUTO-SELL ausgeführt — Order: {sell_result.get('orderId')}")
                    sell_executed = True
                    sells_executed += 1
                    pos["status"] = "sold"
                    update_auto_bet_status(
                        bet_key=pos.get("_betKey", ""),
                        new_status="sold",
                        sell_result=sell_result,
                        current_price=current or 0,
                        sell_reason=sell_reason,
                    )
                else:
                    print(f"    ❌ AUTO-SELL fehlgeschlagen: {sell_result.get('error')}")
                    pos["status"] = "sell_signaled"
            else:
                pos["status"] = "sell_signaled"

            # ── Telegram Alert mit H3-Dedup ───────────────────────────────────
            # H3 Fix 05.06.2026: Sell-Alert wurde alle 4h erneut gesendet wenn
            # Position weiterhin sell_signaled war → Telegram-Spam.
            # Jetzt: Dedup auf (sellReason, sellExecuted) — nur erneut senden
            # wenn (a) > SELL_ALERT_DEDUP_H Stunden vergangen UND Position
            # weiterhin offen, ODER (b) sellReason sich materiell geändert hat
            # (z.B. von "DEEP_LOSS" zu "PRE_MATCH_CLOSE"), ODER (c) Auto-Sell
            # gerade ausgeführt wurde (das ist eine neue Info, immer senden).
            SELL_ALERT_DEDUP_H = 6
            last_alert_at  = pos.get("alertSentAt")
            last_alert_for = pos.get("alertSentForReason")
            should_alert   = True
            if last_alert_at and not sell_executed:
                try:
                    last_dt = datetime.fromisoformat(last_alert_at.replace("Z", "+00:00"))
                    hours_since = (now - last_dt).total_seconds() / 3600
                    if hours_since < SELL_ALERT_DEDUP_H and last_alert_for == sell_reason:
                        should_alert = False
                        print(f"    🔇 Alert-Dedup: bereits vor {hours_since:.1f}h gesendet "
                              f"(reason='{sell_reason}')")
                except Exception:
                    pass

            if should_alert:
                alert = format_sell_alert(pos)
                if sell_executed:
                    alert += f"\n\n✅ <b>Auto-Sell ausgeführt</b>"
                elif auto_sell_on and is_auto and not pos.get("tokenId"):
                    alert += f"\n\n⚠️ tokenId fehlt — manueller Sell nötig!"
                if send_telegram(alert):
                    pos["alertSentAt"]        = now.isoformat()
                    pos["alertSentForReason"] = sell_reason
                    alerts_sent += 1

                # ── Dedizierter Trades-Channel — nur wenn Alert gesendet ─────
                try:
                    from telegram_trades import notify_sell_alert
                    entry   = pos.get("entryPrice", 0)
                    current = pos.get("currentPrice", 0)
                    stake   = pos.get("stake", 0)
                    pnl_pct = pos.get("pnlPct", 0) or 0
                    pnl_eur = round(stake * (current / entry - 1), 2) if (entry and entry > 0 and current) else 0
                    notify_sell_alert(
                        home=pos.get("home", ""), away=pos.get("away", ""),
                        market=pos.get("market", ""),
                        entry_price=entry, current_price=current,
                        profit_pct=pnl_pct, estimated_profit=pnl_eur,
                        stake=stake,
                        reason=sell_reason,
                        home_id=pos.get("homeId", ""),
                        away_id=pos.get("awayId", ""),
                        slug=pos.get("slug", ""),
                    )
                except Exception as e:
                    print(f"    ⚠️  Trades-Channel Fehler: {e}")

    # Update file — nur manuelle Positionen zurückschreiben (auto-bets kommen aus eigenem File)
    save_positions(data)

    print(f"\n✅ Fertig — {alerts_sent} Alert(s) | {sells_executed} Auto-Sell(s) ausgeführt")
    if alerts_sent == 0 and sells_executed == 0 and open_pos:
        best = max(open_pos, key=lambda p: p.get("pnlPct") or -999)
        print(f"   Beste Position: {best.get('home')} vs {best.get('away')} "
              f"— {best.get('market')} @ {best.get('pnlPct', '?')}%")


if __name__ == "__main__":
    main()
