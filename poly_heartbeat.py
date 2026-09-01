#!/usr/bin/env python3
"""
poly_heartbeat.py — Tägliches Status-Update für CocoBet Polymarket Trading
============================================================================

Sendet morgens auf den Trades-Channel:
  · Trading-Status (active/paused via kill_switch)
  · Bankroll: Balance, Open Exposure, verfügbar
  · Heute platziert: Anzahl + Stake
  · Offene Positionen: Anzahl + aktueller Live-PNL
  · Letzte 24h: Bets, Win/Loss, ROI
  · System-Health: Letzter Trigger-Lauf, letzter Sell-Lauf

So weiß man jeden Morgen sofort dass alles läuft — ohne Dashboard öffnen.

Env:
  TELEGRAM_TOKEN
  TELEGRAM_TRADES_CHAT_ID

Run: python3 poly_heartbeat.py
Cron: .github/workflows/daily-heartbeat.yml — 06:00 UTC
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE              = Path(__file__).parent
PLACED_FILE       = BASE / "wm_auto_bets_placed.json"
BALANCE_FILE      = BASE / "wm_poly_balance.json"
KILL_SWITCH_FILE  = BASE / "wm_kill_switch.json"
PRICES_FILE       = BASE / "wm_poly_prices.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TRADES_CHAT_ID   = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()

# Schwellen aus auto_wm_poly_trigger.py / manage_wm_poly_positions.py
DAILY_BET_CAP            = 8
DAILY_STAKE_CAP_USDC     = 50.0
ADAPTIVE_DAILY_FRACTION  = 0.40
MAX_OPEN_EXPOSURE_USDC   = 80.0


def load_json(p: Path, default=None):
    if not p.exists(): return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def current_price_for(bet: dict, poly_data: dict) -> float | None:
    """Aktueller Polymarket-Preis für eine offene Position."""
    home_id = bet.get("homeId", "")
    away_id = bet.get("awayId", "")
    market  = bet.get("market", "")
    key = f"{home_id}-{away_id}"
    fx = next((f for f in poly_data.get("allFixtures", []) if f.get("key") == key), None)
    if not fx: return None
    mkt_to_field = {
        "Heimsieg": "hw", "Auswärtssieg": "aw", "Unentschieden": "dr",
        "Über 2.5 Tore": "o25", "Unter 2.5 Tore": "u25",
    }
    field = mkt_to_field.get(market)
    if not field: return None
    return fx.get(f"poly_{field}")


def main():
    now      = datetime.now(timezone.utc)
    today_s  = now.strftime("%Y-%m-%d")
    yest_s   = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    placed_data = load_json(PLACED_FILE, {"bets": [], "updatedAt": ""})
    balance_data = load_json(BALANCE_FILE, {"usdc": 0.0, "updatedAt": ""})
    kill = load_json(KILL_SWITCH_FILE, {"enabled": True})
    poly_data = load_json(PRICES_FILE, {})

    placed_bets = placed_data.get("bets", [])

    # Status-Felder
    trading_state = "🟢 ACTIVE" if kill.get("enabled", True) else "🛑 PAUSED"
    kill_reason = kill.get("reason", "")

    balance = float(balance_data.get("usdc") or 0)
    adaptive_cap = min(DAILY_STAKE_CAP_USDC, balance * ADAPTIVE_DAILY_FRACTION)

    # Heute
    bets_today = [b for b in placed_bets if (b.get("placedAt") or "")[:10] == today_s]
    stake_today = sum(float(b.get("stake") or 0) for b in bets_today)

    # Gestern (für Tagesvergleich)
    bets_yest = [b for b in placed_bets if (b.get("placedAt") or "")[:10] == yest_s]

    # Open Positions
    open_bets = [b for b in placed_bets if not b.get("resolved") and b.get("result") is None and not b.get("soldAt")]
    open_exposure = sum(float(b.get("stake") or 0) for b in open_bets)

    # Live-PNL für offene Positionen
    open_pnl = 0.0
    open_with_pnl = 0
    for b in open_bets:
        entry = float(b.get("polyPrice") or 0)
        if entry <= 0: continue
        cur = current_price_for(b, poly_data)
        if cur is None: continue
        stake = float(b.get("stake") or 0)
        shares = stake / entry
        cur_val = shares * cur
        open_pnl += (cur_val - stake)
        open_with_pnl += 1

    # Letzte 24h resolved Bets
    cutoff = (now - timedelta(hours=24)).isoformat()
    resolved_24h = [b for b in placed_bets if b.get("resolvedAt", "") >= cutoff and b.get("result") in ("WIN", "LOSS", "VOID")]
    wins_24h = sum(1 for b in resolved_24h if b["result"] == "WIN")
    losses_24h = sum(1 for b in resolved_24h if b["result"] == "LOSS")
    pnl_24h = sum(float(b.get("pnl") or 0) for b in resolved_24h)

    # Letzter Trade
    last_trade = None
    if placed_bets:
        last_trade = max(placed_bets, key=lambda b: b.get("placedAt", ""))
    last_trade_str = "—"
    if last_trade:
        last_ts = last_trade.get("placedAt", "")
        try:
            last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            hours_ago = (now - last_dt).total_seconds() / 3600
            last_trade_str = f"{last_trade.get('home','?')} vs {last_trade.get('away','?')} — vor {hours_ago:.1f}h"
        except Exception:
            last_trade_str = last_ts

    # Cap-Warnungen
    warnings = []
    if adaptive_cap < 11:
        warnings.append(f"⚠️ Adaptive Cap nur ${adaptive_cap:.2f} — Balance auflаden")
    if open_exposure >= MAX_OPEN_EXPOSURE_USDC * 0.9:
        warnings.append(f"⚠️ Open-Exposure-Cap fast voll ({open_exposure:.0f}/${MAX_OPEN_EXPOSURE_USDC:.0f})")
    if balance < 10:
        warnings.append(f"🚨 Balance kritisch niedrig: ${balance:.2f}")

    # Heartbeat-Nachricht zusammensetzen
    msg_lines = [
        f"🤖 <b>CocoBet · Auto-Trader Heartbeat</b>",
        f"<i>{now.strftime('%d.%m.%Y %H:%M')} UTC</i>",
        "",
        f"<b>Status:</b> {trading_state}",
    ]
    if not kill.get("enabled", True) and kill_reason:
        msg_lines.append(f"  <i>Grund: {kill_reason}</i>")

    msg_lines += [
        "",
        f"💼 <b>Bankroll</b>",
        f"  Balance:        ${balance:>7.2f}",
        f"  Open Exposure:  ${open_exposure:>7.2f} ({len(open_bets)} Pos.)",
        f"  Adaptive Cap:   ${adaptive_cap:>7.2f}/Tag",
        "",
        f"📅 <b>Heute</b>",
        f"  Bets:           {len(bets_today)} / {DAILY_BET_CAP}",
        f"  Stake:          ${stake_today:>7.2f} / ${adaptive_cap:.2f}",
        "",
    ]

    if open_with_pnl > 0:
        pnl_color = "🟢" if open_pnl >= 0 else "🔴"
        pnl_pct = (open_pnl / open_exposure * 100) if open_exposure > 0 else 0
        msg_lines += [
            f"📊 <b>Offene Positionen — Live</b>",
            f"  {pnl_color} Unrealisiert: ${open_pnl:+.2f} ({pnl_pct:+.1f}%)",
            "",
        ]

    if resolved_24h:
        pnl_24h_color = "🟢" if pnl_24h >= 0 else "🔴"
        msg_lines += [
            f"📈 <b>Letzte 24h</b>",
            f"  Resolved:       {wins_24h}W / {losses_24h}L",
            f"  {pnl_24h_color} P&L:          ${pnl_24h:+.2f}",
            "",
        ]

    msg_lines += [
        f"⚡ <b>Letzter Trade</b>",
        f"  {last_trade_str}",
    ]

    if warnings:
        msg_lines += ["", "<b>Warnings</b>"] + [f"  {w}" for w in warnings]

    msg_lines += [
        "",
        # 01.09.2026: stand hier als „cocobet.github.io" — diesen Pages-Host gibt es nicht.
        # Der Pages-Host kommt vom Kontonamen, und das Repo ist blummabet/Betting-Dashboard;
        # jede andere Stelle im Projekt (results-v2.js, polymarket-tab.js, season-finish-v2.html)
        # nutzt blummabet.github.io. Der Hinweis lief also seit jeher ins Leere.
        f"<i>Dashboard: blummabet.github.io/Betting-Dashboard/season-finish-v2.html</i>",
    ]

    msg = "\n".join(msg_lines)
    print(msg)

    if not TELEGRAM_TOKEN or not TRADES_CHAT_ID:
        print("\n(Telegram skip — Token/Chat-ID fehlt)")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TRADES_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = json.loads(r.read()).get("ok", False)
            print(f"\n{'✓ gesendet' if ok else '✗ Telegram-Fehler'}")
    except Exception as e:
        print(f"\n✗ Telegram-Fehler: {e}")


if __name__ == "__main__":
    main()
