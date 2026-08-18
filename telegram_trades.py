#!/usr/bin/env python3
"""
telegram_trades.py — Dedizierter Trades-Channel für Polymarket-Auto-Trades (Wettbewerb aus Slug abgeleitet)

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
    return _FLAGS.get(team_id.upper(), "")   # 18.08.2026 (Lucas): Klub-Teams (MLS/Liga) ohne Laender-Match -> kein Flag statt weisse Fahne


# -- Wettbewerb aus dem Polymarket-Slug ableiten ---------------------------
# Slug-Praefix (fifwc-/mls-/epl-/lal-/sea-/fl1-/bun-...) -> (Label, Poly-URL-Pfad).
# 18.08.2026 (Lucas): frueher waren Header + Poly-Link fest auf den WM-Wettbewerb verdrahtet,
# sodass MLS-/Liga-Auto-Bets falsch gelabelt wurden. Jetzt pro Bet aus dem Slug bestimmt.
_COMP_BY_SLUG: dict[str, tuple[str, str]] = {
    "fifwc":        ("WM 2026",         "fifa-world-cup"),
    "mls":          ("MLS",             "mls"),
    "epl":          ("Premier League",  "epl"),
    "lal":          ("La Liga",         "laliga"),
    "sea":          ("Serie A",         "serie-a"),
    "fl1":          ("Ligue 1",         "ligue-1"),
    "bun":          ("Bundesliga",      "bundesliga"),
    "championship": ("Championship",    "championship"),
    "eredivisie":   ("Eredivisie",      "eredivisie"),
}

def _competition(slug: str | None) -> tuple[str, str | None]:
    """(Label, Poly-URL-Pfad) fuer den Wettbewerb dieses Slugs. Fallback: 'Fussball' + kein Pfad."""
    pfx = (slug or "").split("-", 1)[0].lower()
    return _COMP_BY_SLUG.get(pfx, ("Fussball", None))

def _poly_url(slug: str | None) -> str | None:
    """Korrekter Polymarket-Link je Wettbewerb (nicht mehr fest verdrahtet)."""
    if not slug:
        return None
    _, path = _competition(slug)
    return (f"https://polymarket.com/sports/{path}/{slug}" if path
            else f"https://polymarket.com/event/{slug}")


def is_auto_source(source: str | None) -> bool:
    """Single Source of Truth: gilt ein Bet als Auto-Trade?

    Der Auto-Trader taggt sich als "auto" ODER "auto_steam" (Steam-Lag). Frühere
    exakte ==-Vergleiche liessen auto_steam durchrutschen → Telegram zeigte
    "MANUELLER BET" (NED-TUN 15.06.) und manage_wm_poly_positions verkaufte
    Steam-Lag-Positionen nie automatisch. startswith deckt jede auto_*-Variante.
    """
    return (source or "").startswith("auto")


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
    comp_label, _ = _competition(slug)

    is_auto = is_auto_source(source)
    icon  = "🤖" if is_auto else "👆"
    label = "AUTO-BET" if is_auto else "MANUELLER BET"
    if dry_run:
        label = f"[DRY-RUN] {label}"

    flag_h = _flag(home_id) if home_id else ""
    flag_a = _flag(away_id) if away_id else ""

    edge_line = ""
    if edge_pp is not None:
        pinn_str  = f"  |  Pinn-Fair: {pinn_fair*100:.1f}¢" if pinn_fair else ""
        edge_line = f"\n🎯 Edge: <b>+{edge_pp:.1f}pp</b> vs Pinnacle{pinn_str}"

    poly_link = ""
    _url = _poly_url(slug)
    if _url:
        poly_link = f"\n🔗 <a href='{_url}'>Polymarket öffnen</a>"

    order_line = f"\n🆔 Order: <code>{order_id[:24]}</code>" if order_id else ""

    text = (
        f"{icon} <b>{label} PLATZIERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 {comp_label}\n"
        f"{(flag_h+' ') if flag_h else ''}{home} vs {away}{(' '+flag_a) if flag_a else ''}\n"
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
    comp_label, _ = _competition(slug)
    cur_oc   = f"{1/current_price:.2f}" if current_price > 0 else "?"
    profit_sign = "+" if estimated_profit >= 0 else ""

    poly_link = ""
    _url = _poly_url(slug)
    if _url:
        poly_link = f"\n🔗 <a href='{_url}'>Jetzt verkaufen →</a>"

    text = (
        f"💰 <b>POSITION VERKAUFEN</b>  [{reason}]\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 {comp_label}\n"
        f"{(flag_h+' ') if flag_h else ''}{home} vs {away}{(' '+flag_a) if flag_a else ''}\n"
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
    comp_label = "CocoBet Trade"   # closed hat keinen Slug -> neutral
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
        f"🏆 {comp_label}\n"
        f"{(flag_h+' ') if flag_h else ''}{home} vs {away}{(' '+flag_a) if flag_a else ''}\n"
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
        f"CocoBet Polymarket System\n"
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
