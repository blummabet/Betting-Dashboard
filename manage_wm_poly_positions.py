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
from datetime import datetime, timezone

BASE          = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE, "wm_poly_positions.json")
PRICES_FILE    = os.path.join(BASE, "wm_poly_prices.json")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Sell-Schwellwerte ─────────────────────────────────────────────────────────
PROFIT_TARGET   = 0.20   # +20% Profit auf Einstiegspreis → Sell
PINN_GAP_PP     = 2.0    # Poly ist innerhalb 2pp von Pinnacle Fair → Sell (konvergiert)
MIN_PROFIT_PP   = 0.03   # Minimaler absoluter Profit (+3pp) bevor Secondary-Regel greift

# ── Gamma API ────────────────────────────────────────────────────────────────
GAMMA_URL = "https://gamma-api.polymarket.com/events?slug={slug}"


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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [Telegram] {text[:120]}")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
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


def fetch_current_price(slug: str, market_key: str) -> float | None:
    """
    Holt aktuellen Polymarket-Preis für ein Spiel via Gamma API.
    market_key: 'hw' | 'dr' | 'aw'
    """
    # Zuerst lokalen Cache (wm_poly_prices.json) prüfen — vermeidet unnötige API-Calls
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        prices = cached.get("prices", {})
        for key, entry in prices.items():
            if entry.get("slug") == slug:
                price = entry.get(market_key)
                if price:
                    return float(price)

    # Fallback: direkt von Gamma API holen
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

    current = fetch_current_price(slug, market_key)
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

    # PRIMARY: +20% Profit
    if entry > 0 and current >= entry * (1 + PROFIT_TARGET):
        sell = True
        reason = f"Profit +{round(pnl_pct, 1)}% ≥ +{PROFIT_TARGET*100:.0f}% Ziel"

    # SECONDARY: Poly konvergiert zu Pinnacle fair (innerhalb PINN_GAP_PP)
    if not sell and pinn_fair and (current - entry) * 100 >= MIN_PROFIT_PP * 100:
        gap = (pinn_fair - current) * 100
        if gap <= PINN_GAP_PP:
            sell = True
            reason = f"Markt konvergiert: Poly {current:.3f} ≈ Pinn fair {pinn_fair:.3f} (Δ{gap:.1f}pp)"

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
    pnl_eur  = round(stake * pos.get("pnlPP", 0) / 100, 2) if pos.get("pnlPP") else 0
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


def main():
    print("=== manage_wm_poly_positions.py ===")
    now = datetime.now(timezone.utc)
    print(f"  {now.strftime('%d.%m.%Y %H:%M UTC')}")

    data = load_positions()
    positions = data.get("positions", [])

    if not positions:
        print("  Keine offenen Positionen.")
        return

    open_pos = [p for p in positions if p.get("status") == "open"]
    print(f"  {len(open_pos)} offene Positionen gefunden")

    alerts_sent = 0
    for pos in open_pos:
        home   = pos.get("home", "?")
        away   = pos.get("away", "?")
        market = pos.get("market", "?")
        print(f"\n  Prüfe: {home} vs {away} — {market}")

        check_position(pos)

        current = pos.get("currentPrice")
        pnl     = pos.get("pnlPct")
        print(f"    Entry: {pos.get('entryPrice')} | Aktuell: {current} | P&L: {pnl}%")

        if pos.get("sellSignal"):
            print(f"    🚨 SELL SIGNAL: {pos['sellReason']}")
            alert = format_sell_alert(pos)
            if send_telegram(alert):
                pos["alertSentAt"] = now.isoformat()
                alerts_sent += 1
            pos["status"] = "sell_signaled"

    # Update file
    save_positions(data)

    print(f"\n✅ Fertig — {alerts_sent} Sell-Alert(s) gesendet")
    if alerts_sent == 0 and open_pos:
        best = max(open_pos, key=lambda p: p.get("pnlPct") or -999)
        print(f"   Beste Position: {best.get('home')} vs {best.get('away')} "
              f"— {best.get('market')} @ {best.get('pnlPct', '?')}%")


if __name__ == "__main__":
    main()
