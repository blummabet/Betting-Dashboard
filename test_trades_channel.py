#!/usr/bin/env python3
"""
test_trades_channel.py — Schnelltest für den Trades-Telegram-Channel

Sendet EINEN Testbericht und alle 4 Nachrichtentypen an TELEGRAM_TRADES_CHAT_ID.

Run:
  TELEGRAM_TOKEN="..." TELEGRAM_TRADES_CHAT_ID="..." python test_trades_channel.py

Oder wenn Secrets bereits als Env gesetzt:
  python test_trades_channel.py
"""

import os, sys, time

TOKEN    = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID  = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()

print("🧪  Trades-Channel Test")
print(f"    Token:   {'✅ gesetzt' if TOKEN else '❌ FEHLT — TELEGRAM_TOKEN setzen'}")
print(f"    Chat-ID: {'✅ ' + CHAT_ID if CHAT_ID else '❌ FEHLT — TELEGRAM_TRADES_CHAT_ID setzen'}")
print()

if not TOKEN or not CHAT_ID:
    print("❌  Bitte beide Env-Variablen setzen und nochmal laufen:")
    print("    export TELEGRAM_TOKEN='...'")
    print("    export TELEGRAM_TRADES_CHAT_ID='...'")
    sys.exit(1)

from telegram_trades import (
    send_trades_message,
    notify_trade_opened,
    notify_sell_alert,
    notify_trade_closed,
)

results = []

# ── 0. Ping ────────────────────────────────────────────────────────────────
print("0️⃣  Sende Ping…")
ok = send_trades_message(
    "🧪 <b>Trades-Channel Test</b>\n"
    "━━━━━━━━━━━━━━━━━━━\n"
    "Kanal erfolgreich verbunden! ✅\n"
    "Gleich kommen 4 Beispiel-Nachrichten."
)
results.append(("Ping", ok))
time.sleep(1)

# ── 1. Auto-Bet ────────────────────────────────────────────────────────────
print("1️⃣  Auto-Bet Notification…")
ok = notify_trade_opened(
    home="Deutschland", away="Elfenbeinküste",
    market="Heimsieg", stake=10.0, poly_price=0.52,
    edge_pp=3.3, pinn_fair=0.556,
    order_id="TEST-abc123def456",
    source="auto",
    home_id="GER", away_id="CIV",
    slug="fifwc-ger-civ-2026-06-12",
    dry_run=True,
)
results.append(("Auto-Bet", ok))
time.sleep(1)

# ── 2. Manueller Bet ──────────────────────────────────────────────────────
print("2️⃣  Manueller Bet Notification…")
ok = notify_trade_opened(
    home="Spanien", away="Kap Verde",
    market="Heimsieg", stake=5.0, poly_price=0.735,
    edge_pp=3.5, pinn_fair=0.77,
    order_id="TEST-xyz789",
    source="manual",
    home_id="ESP", away_id="CPV",
    slug="fifwc-esp-cpv-2026-06-14",
)
results.append(("Manueller Bet", ok))
time.sleep(1)

# ── 3. Sell Alert ─────────────────────────────────────────────────────────
print("3️⃣  Sell Alert Notification…")
ok = notify_sell_alert(
    home="Deutschland", away="Elfenbeinküste",
    market="Heimsieg",
    entry_price=0.52, current_price=0.65,
    profit_pct=25.0, estimated_profit=2.50,
    stake=10.0,
    reason="Profit-Target +20%",
    home_id="GER", away_id="CIV",
    slug="fifwc-ger-civ-2026-06-12",
)
results.append(("Sell Alert", ok))
time.sleep(1)

# ── 4. Trade Resolved ─────────────────────────────────────────────────────
print("4️⃣  Trade Resolved (WIN) Notification…")
ok = notify_trade_closed(
    home="Deutschland", away="Elfenbeinküste",
    market="Heimsieg",
    entry_price=0.52, close_price=0.60,
    pnl=9.23, clv_pp=2.8,
    result="WIN", score="2-1",
    home_id="GER", away_id="CIV",
)
results.append(("Trade Resolved", ok))

# ── Ergebnis ─────────────────────────────────────────────────────────────
print()
print("─" * 40)
all_ok = all(r[1] for r in results)
for name, ok in results:
    print(f"  {'✅' if ok else '❌'} {name}")
print()
if all_ok:
    print("✅  Alle 5 Nachrichten erfolgreich gesendet!")
    print("   Schau in deinen Trades-Channel.")
else:
    failed = [r[0] for r in results if not r[1]]
    print(f"⚠️  Fehler bei: {', '.join(failed)}")
    print("   Prüfe Token + Chat-ID + Bot-Berechtigung im Channel.")
