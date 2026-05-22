#!/usr/bin/env python3
"""
telegram_trades.py — Dedizierter Trades-Channel für WM 2026 Polymarket

Sendet Nachrichten an einen SEPARATEN Telegram-Channel nur für Trades.
Dieser Channel ist KEIN User-facing WM-Info-Channel — er loggt nur:
  · Trade Opened  (auto-trigger oder manuell über Dashboard)
  · Sell Alert    (Position im Gewinn → verkaufen empfohlen)
  · Trade Closed  (Position aufgelöst)

Env-Variablen:
  TELEGRAM_TOKEN           — gleicher Bot wie WM-Channel (bereits gesetzt)
  TELEGRAM_TRADES_CHAT_ID  — Chat-ID des NEUEN, separaten Trades-Channels
                             (User legt Channel an, Bot einladen, Chat-ID holen)

Setup für neuen Channel:
  1. Telegram-Channel anlegen (z.B. "CocoBet Trades")
  2. Bot zum Channel hinzufügen (als Admin, damit er posten kann)
  3. Eine Nachricht im Channel schreiben
  4. https://api.telegram.org/bot{TOKEN}/getUpdates aufrufen
  5. chat.id aus der Antwort → als TELEGRAM_TRADES_CHAT_ID Secret speichern

Wird importiert von:
  · auto_wm_poly_trigger.py    → notify_trade_opened()
  · polymarket_bet.py          → notify_trade_opened() (manuell)
  · manage_wm_poly_positions.py → notify_sell_alert() / notify_trade_closed()
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

# ── Env-Variablen ──────────────────────────────────────────────────────────
TELEGRAM_TOKEN          = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_TRADES_CHAT_ID = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "").strip()


# ── Kern-Send-Funktion ─────────────────────────────────────────────────────

def send_trades_message(text: str, disable_preview: bool = True) -> bool:
    """
    Sendet eine Nachricht an den Trades-Channel.
    Gibt True zurück bei Erfolg, False wenn Channel nicht konfiguriert.
    Loggt den Text zur Konsole wenn Channel nicht gesetzt.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_TRADES_CHAT_ID:
        print(f"\n[TradesChannel nicht konfiguriert] Nachricht:\n{text}\n")
        return False

    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":                  TELEGRAM_TRADES_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": disable_preview,
    }).encode()

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            print(f"  📱 Trades-Channel: Nachricht gesendet")
            return True
    except Exception as e:
        print(f"  ⚠️  Trades-Channel Fehler: {e}")
        return False


# ── Flag-Emojis für Teamkürzel ─────────────────────────────────────────────
_FLAGS = {
    "GER": "🇩🇪", "FRA": "🇫🇷", "ESP": "🇪🇸", "POR": "🇵🇹", "ITA": "🇮🇹",
    "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "NED": "🇳🇱", "BEL": "🇧🇪", "ARG": "🇦🇷", "BRA": "🇧🇷",
    "URU": "🇺🇾", "USA": "🇺🇸", "MEX": "🇲🇽", "JPN": "🇯🇵", "KOR": "🇰🇷",
    "AUS": "🇦🇺", "MAR": "🇲🇦", "SEN": "🇸🇳", "NGA": "🇳🇬", "GHA": "🇬🇭",
    "CIV": "🇨🇮", "EGY": "🇪🇬", "TUN": "🇹🇳", "DZA": "🇩🇿", "ZAF": "🇿🇦",
    "SUI": "🇨🇭", "AUT": "🇦🇹", "CRO": "🇭🇷", "SWE": "🇸🇪", "NOR": "🇳🇴",
    "DEN": "🇩🇰", "POL": "🇵🇱", "CZE": "🇨🇿", "SRB": "🇷🇸", "TUR": "🇹🇷",
    "QAT": "🇶🇦", "SAU": "🇸🇦", "IRN": "🇮🇷", "IRQ": "🇮🇶", "JOR": "🇯🇴",
    "UZB": "🇺🇿", "CAN": "🇨🇦", "COL": "🇨🇴", "ECU": "🇪🇨", "PRY": "🇵🇾",
    "CHL": "🇨🇱", "PER": "🇵🇪", "BOL": "🇧🇴", "VEN": "🇻🇪", "PAN": "🇵🇦",
    "HTI": "🇭🇹", "CPV": "🇨🇻", "NZL": "🇳🇿", "FIJ": "🇫🇯", "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "WAL": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "BIH": "🇧🇦", "CUW": "🇨🇼", "COD": "🇨🇩",
}

def _flag(team_id: str) -> str:
    return _FLAGS.get(team_id.upper(), "🏳️")


# ── Nachrichten-Formatter ──────────────────────────────────────────────────

def notify_trade_opened(
    home: str, away: str, market: str,
    stake: float, poly_price: float,
    edge_pp: float | None = None,
    pinn_fair: float | None = None,
    order_id: str | None = None,
    source: str = "auto",       # "auto" | "manual"
    home_id: str = "",
    away_id: str = "",
    slug: str = "",
    dry_run: bool = False,
) -> bool:
    """Sendet Trade-Opened Notification an Trades-Channel."""
    now      = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    poly_odds = f"{1/poly_price:.2f}" if poly_price and poly_price > 0 else "?"
    stake_str = f"€{stake:.2f}"
    pct_str   = f"{round(poly_price * 100)}¢"

    icon  = "🤖" if source == "auto" else "👆"
    label = "AUTO-BET" if source == "auto" else "MANUELLER BET"
    if dry_run:
        label = f"[DRY-RUN] {label}"

    flag_h = _flag(home_id) if home_id else ""
    flag_a = _flag(away_id) if away_id else ""

    edge_line = ""
    if edge_pp is not None:
        pinn_str  = f"  |  Pinn-Fair: {pinn_fair*100:.1f}¢" if pinn_fair else ""
        edge_line = f"\n🎯 Edge: <b>+{edge_pp:.1f}pp</b> vs Pinnacle{pinn_str}"

    poly_link = ""
    if slug:
        poly_link = f"\n🔗 <a href='https://polymarket.com/sports/fifa-world-cup/{slug}'>Polymarket öffnen</a>"

    order_line = f"\n🆔 Order: <code>{order_id[:24]}</code>" if order_id else ""

    text = (
        f"{icon} <b>{label} PLATZIERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 WM 2026\n"
        f"{flag_h} {home} vs {away} {flag_a}\n"
        f"📋 Markt: <b>{market}</b>\n"
        f"💰 Einsatz: <b>{stake_str}</b>\n"
        f"📊 Poly: <b>{poly_odds}</b> ({pct_str})"
        f"{edge_line}"
        f"{order_line}"
        f"{poly_link}\n"
        f"🕐 {now}"
    )
    return send_trades_message(text)


def notify_sell_alert(
    home: str, away: str, market: str,
    entry_price: float, current_price: float,
    profit_pct: float, estimated_profit: float,
    stake: float,
    reason: str = "Profit-Target",
    home_id: str = "",
    away_id: str = "",
    slug: str = "",
) -> bool:
    """Sendet Sell-Alert Notification an Trades-Channel."""
    now      = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    flag_h   = _flag(home_id) if home_id else ""
    flag_a   = _flag(away_id) if away_id else ""
    entry_oc = f"{1/entry_price:.2f}" if entry_price > 0 else "?"
    cur_oc   = f"{1/current_price:.2f}" if current_price > 0 else "?"
    profit_sign = "+" if estimated_profit >= 0 else ""

    poly_link = ""
    if slug:
        poly_link = f"\n🔗 <a href='https://polymarket.com/sports/fifa-world-cup/{slug}'>Jetzt verkaufen →</a>"

    text = (
        f"💰 <b>POSITION VERKAUFEN</b>  [{reason}]\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 WM 2026\n"
        f"{flag_h} {home} vs {away} {flag_a}\n"
        f"📋 Markt: <b>{market}</b>\n"
        f"📈 Entry: {entry_oc} → Jetzt: <b>{cur_oc}</b>\n"
        f"💵 Einsatz: €{stake:.2f}  |  Gewinn: <b>{profit_sign}€{abs(estimated_profit):.2f}</b>  ({profit_sign}{profit_pct:.0f}%)"
        f"{poly_link}\n"
        f"🕐 {now}"
    )
    return send_trades_message(text)


def notify_trade_closed(
    home: str, away: str, market: str,
    entry_price: float, close_price: float,
    pnl: float, clv_pp: float | None = None,
    result: str = "?",
    score: str = "",
    home_id: str = "",
    away_id: str = "",
) -> bool:
    """Sendet Trade-Closed Notification wenn Spiel abgeschlossen und Bet resolved."""
    now      = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    flag_h   = _flag(home_id) if home_id else ""
    flag_a   = _flag(away_id) if away_id else ""

    result_icon = {"WIN": "✅", "LOSS": "❌", "VOID": "⬜"}.get(result, "❓")
    pnl_sign    = "+" if pnl >= 0 else ""
    pnl_col     = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⬜"

    clv_line = ""
    if clv_pp is not None:
        clv_sign = "+" if clv_pp >= 0 else ""
        clv_line = f"\n📐 CLV: <b>{clv_sign}{clv_pp:.1f}pp</b> (Closing Line Value)"

    score_line = f"\n⚽ Endstand: <b>{score}</b>" if score else ""

    text = (
        f"{result_icon} <b>BET RESOLVED — {result}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 WM 2026\n"
        f"{flag_h} {home} vs {away} {flag_a}\n"
        f"📋 Markt: <b>{market}</b>"
        f"{score_line}\n"
        f"{pnl_col} P&L: <b>{pnl_sign}€{abs(pnl):.2f}</b>"
        f"{clv_line}\n"
        f"🕐 {now}"
    )
    return send_trades_message(text)


def notify_system_start(mode: str = "dry-run") -> bool:
    """Sendet eine Startup-Nachricht wenn Auto-Trigger läuft (optional, zum Testen)."""
    now  = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    icon = "🤖" if mode == "live" else "🧪"
    text = (
        f"{icon} <b>Auto-Trigger gestartet</b>  [{mode.upper()}]\n"
        f"WM 2026 Polymarket System\n"
        f"🕐 {now}"
    )
    return send_trades_message(text)


# ── Test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Teste Trades-Channel Nachrichten…\n")

    print("1. Trade Opened (Auto):")
    notify_trade_opened(
        home="Deutschland", away="Elfenbeinküste",
        market="Heimsieg", stake=10.0, poly_price=0.52,
        edge_pp=3.3, pinn_fair=0.556,
        order_id="abc123def456", source="auto",
        home_id="GER", away_id="CIV",
        slug="fifwc-ger-civ-2026-06-12",
    )

    print("\n2. Trade Opened (Manuell):")
    notify_trade_opened(
        home="Spanien", away="Kap Verde",
        market="Heimsieg", stake=5.0, poly_price=0.735,
        edge_pp=3.5, pinn_fair=0.77,
        order_id="xyz789", source="manual",
        home_id="ESP", away_id="CPV",
        slug="fifwc-esp-cpv-2026-06-14",
    )

    print("\n3. Sell Alert:")
    notify_sell_alert(
        home="Deutschland", away="Elfenbeinküste",
        market="Heimsieg", entry_price=0.52, current_price=0.65,
        profit_pct=25.0, estimated_profit=2.50, stake=10.0,
        reason="Profit-Target +20%",
        home_id="GER", away_id="CIV",
        slug="fifwc-ger-civ-2026-06-12",
    )

    print("\n4. Trade Closed (WIN):")
    notify_trade_closed(
        home="Deutschland", away="Elfenbeinküste",
        market="Heimsieg", entry_price=0.52, close_price=0.60,
        pnl=9.23, clv_pp=2.8, result="WIN", score="2-1",
        home_id="GER", away_id="CIV",
    )
