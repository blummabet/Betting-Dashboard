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

import cocobet_dataset as D   # 29.06.2026: dataset-aware (MLS-Poly-Dry-Run)

BASE           = os.path.dirname(os.path.abspath(__file__))
# Dataset-aware: wm_* | liga_* | mls_* je COCOBET_DATASET. WM unverändert.
POSITIONS_FILE = str(D.file("wm_poly_positions.json",  "liga_poly_positions.json"))
AUTO_BETS_FILE = str(D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json"))
PRICES_FILE    = str(D.file("wm_poly_prices.json",      "liga_poly_prices.json"))

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
PROFIT_TARGET   = _cfg("sell", "profit_target", 0.08)
PINN_GAP_PP     = _cfg("sell", "pinn_gap_pp",   1.5)
MIN_PROFIT_PP   = _cfg("sell", "min_profit_pp", 0.03)
# Spread-Schutz (17.06.2026): nicht in absurd breite Orderbücher verkaufen
MAX_SELL_SPREAD_PP = _cfg("sell", "max_sell_spread_pp", 15.0)

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

# 3. AGE-LOSS: alte Position + im Minus → realisieren bevor Spread alles frisst.
#    KO-GATE (21.06.2026, Lucas): NUR feuern wenn Anpfiff NAH (hours_left <= max).
#    Tage vor dem Spiel ist „alt + im Minus" kein echtes Gegen-Signal — die These hat
#    ihr Event noch komplett vor sich und das −10% ist großteils nur Bid/Ask-Spread.
#    Den Spread zahlt man erst BEIM Verkauf; früh verkaufen REALISIERT ihn, statt ihn
#    zu vermeiden. Erst im Exit-Fenster (nah am KO) ist „alt+Minus+Spread" ein Grund.
AGE_LOSS_HOURS         = _cfg("sell", "age_loss_hours",         36.0)
AGE_LOSS_THRESHOLD_PCT = _cfg("sell", "age_loss_threshold_pct", 0.10)
AGE_LOSS_MAX_HOURS_LEFT = _cfg("sell", "age_loss_max_hours_left", 48.0)

# 4. NEVER IN-PLAY: Live-Phase = kein Loss-Trigger (Polymarket-Live-Liquidität zu mies)
NO_INPLAY_LOSS_SELL    = _cfg("sell", "no_inplay_loss_sell", True)

# ── Auto-Sell Konfiguration ───────────────────────────────────────────────────
# AUTO_SELL_ENABLED bleibt bewusst HARDCODE: Safety-Master-Switch, nur per
# explizitem Code-Edit oder ENV=true aktivierbar (verhindert versehentliches
# Live-Trading durch Config-Tippfehler). Verhalten unverändert.
AUTO_SELL_ENABLED     = False

# Hard-Close Stunden vor Anpfiff — bereits in trade-section (von auto_trigger).
# 05.06.2026: von 6 → 2 verschoben (Lineups 60-90min vor Anpfiff, Sharp-Moves 2-4h vor KO).
# 16.06.2026 (Lucas): von 2h auf 0.67h (40min) gesenkt — wir halten die Gewinner bis kurz
# vor Anpfiff, um die späte Steam (v.a. Aufstellungs-Moves 60-90min vor KO) mitzunehmen.
# 40min (statt der zuerst geplanten 20min), weil GitHubs Scheduler real nur ~30min-Kadenz
# liefert → bei 30min-Läufen landet garantiert einer im Fenster [KO-40,KO-10], sicher
# pre-match. Pre-match-Märkte driften nur, sie springen nicht — erst nach Anpfiff volatil.
PRE_MATCH_CLOSE_HOURS = _cfg("trade", "pre_match_close_hours", 2)

# Früher Stop-Loss (16.06.2026): Da wir jetzt länger halten, kappen wir klare Verlierer
# VOR dem volatilen Aufstellungs-Fenster. Ab EARLY_STOPLOSS_HOURS vor Anpfiff wird jede
# Position, die ≥ EARLY_STOPLOSS_PCT hinten liegt, sofort geschlossen (nur pre-match).
EARLY_STOPLOSS_HOURS = _cfg("trade", "early_stoploss_hours", 2.0)
EARLY_STOPLOSS_PCT   = _cfg("trade", "early_stoploss_pct",   0.15)


def time_based_exit(h_until, pnl_pct):
    """Zeit-basierte Pre-Match-Exits (16.06.2026), reine Funktion → testbar:
      1. Hard-Close: Anpfiff in ≤ PRE_MATCH_CLOSE_HOURS (20min) → alles schliessen.
      2. Stop-Loss: zwischen Hard-Close und EARLY_STOPLOSS_HOURS (2h) Verlierer ≥15%
         kappen, bevor das volatile Aufstellungs-Fenster kommt.
    Beides nur pre-match (h_until > 0). Gibt (should_sell, reason) zurück."""
    if h_until is None:
        return (False, "")
    if 0 <= h_until <= PRE_MATCH_CLOSE_HOURS:
        return (True, f"Pre-Match Close ({h_until:.2f}h vor Anpfiff)")
    if (PRE_MATCH_CLOSE_HOURS < h_until <= EARLY_STOPLOSS_HOURS
            and isinstance(pnl_pct, (int, float))
            and pnl_pct <= -EARLY_STOPLOSS_PCT * 100):
        return (True, f"Stop-Loss {pnl_pct:.1f}% ({h_until:.1f}h vor Anpfiff)")
    return (False, "")

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


# ── Buch-Fetch-Gesundheit (19.06.2026, Lucas: „der Guard muss sowas sehen") ──────
# Zählt pro Prozess-Lauf: Versuche, Transport-Fehler (None aus _http_get = HTTP/Netz,
# z.B. der /books-400er), echte Bücher. write_book_health() schreibt das weg; Guard
# check_book_fetch_healthy schlägt Alarm wenn Versuche>0 aber 0 echte Bücher (= Endpoint/
# Netz tot, genau der stille Totalausfall der das Trading vom 17.→19.06 abgewürgt hat).
_BOOK_HEALTH = {"attempts": 0, "transport_fail": 0, "empty_or_crossed": 0, "ok": 0}
BOOK_HEALTH_FILE = str(D.file("wm_book_health.json", "liga_book_health.json"))


def write_book_health(path: str = None) -> None:
    """Schreibt den Buch-Fetch-Gesundheits-Snapshot — NUR wenn dieser Lauf Bücher abfragte
    (attempts>0), damit ein Leerlauf (0 Positionen/Kandidaten) keine echten Daten überschreibt."""
    if _BOOK_HEALTH["attempts"] <= 0:
        return
    try:
        from datetime import datetime as _dt, timezone as _tz
        snap = dict(_BOOK_HEALTH, ts=_dt.now(_tz.utc).isoformat())
        with open(path or BOOK_HEALTH_FILE, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  write_book_health fehlgeschlagen: {e}")


# 19.06.2026 (Root-Cause „seit 17.06 nichts getradet"): Endpoint war /books (Mehrzahl) →
# das erwartet einen POST-Body, GET ?token_id= gab HTTP 400 Bad Request → fetch_token_book
# scheiterte bei JEDEM Aufruf → REQUIRE_BOOK skippte alles + jede Bewertung fiel auf cache_mid.
# Korrekter Endpoint = /book (Einzahl, GET ?token_id=) für ein einzelnes Token-Orderbuch.
CLOB_BOOK_URL = "https://clob.polymarket.com/book?token_id={token_id}"


def fetch_token_book(token_id: str) -> dict | None:
    """
    Live-Top-of-Book vom Polymarket-CLOB für GENAU den Token, den wir halten.

    17.06.2026 (Geld-Bug USA-TUR): Positionen wurden am MITTELPREIS bewertet
    (`poly_btts_no` = 1 − JA-Mid), nicht am echten realisierbaren VERKAUFSPREIS.
    Kauf lief über den Ask (0.43), Verkauf über den Bid (0.41) → angezeigte +10%
    waren real −4%. Fix: Position immer am **Bid** bewerten (was wir beim Verkauf
    wirklich bekommen), Eintritt am **Ask**.

    ORDER-UNABHÄNGIG: best bid = max(bids), best ask = min(asks) — Polymarket
    sortiert Bücher nicht garantiert; Index [0] anzunehmen wäre der nächste Phantom-Bug.

    Gibt {bid, ask, mid, spreadPP} oder None (→ Caller verkauft NICHT = sicherer Default).
    """
    if not token_id:
        return None
    _BOOK_HEALTH["attempts"] += 1
    data = _http_get(CLOB_BOOK_URL.format(token_id=token_id))
    if not isinstance(data, dict):
        _BOOK_HEALTH["transport_fail"] += 1   # None aus _http_get = HTTP/Netz (z.B. 400)
        return None
    try:
        bids = [(float(b["price"]), float(b.get("size", 0) or 0))
                for b in (data.get("bids") or [])
                if isinstance(b, dict) and b.get("price") is not None]
        asks = [(float(a["price"]), float(a.get("size", 0) or 0))
                for a in (data.get("asks") or [])
                if isinstance(a, dict) and a.get("price") is not None]
    except (TypeError, ValueError):
        _BOOK_HEALTH["transport_fail"] += 1
        return None
    if not bids or not asks:
        _BOOK_HEALTH["empty_or_crossed"] += 1   # echte Antwort, aber einseitig/leer (dünn)
        return None
    best_bid, bid_sz = max(bids, key=lambda x: x[0])
    best_ask, ask_sz = min(asks, key=lambda x: x[0])
    # Sanity: 0 < bid < ask < 1. Gekreuztes/degeneriertes Buch → None (kein Sell).
    if not (0.0 < best_bid < best_ask < 1.0):
        _BOOK_HEALTH["empty_or_crossed"] += 1
        return None
    _BOOK_HEALTH["ok"] += 1
    return {
        "bid":      round(best_bid, 4),
        "ask":      round(best_ask, 4),
        "mid":      round((best_bid + best_ask) / 2, 4),
        "spreadPP": round((best_ask - best_bid) * 100, 1),
        "liqUSD":   round(best_bid * bid_sz + best_ask * ask_sz, 0),
    }


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


def _token_price_from_cache(token_id: str) -> float | None:
    """FIX 16.06.2026 (Geld-Bug): Preis einer AH/BTTS-Position über den EXAKTEN
    Token bewerten, den wir halten — nicht über ein Markt-Label-Fallback.

    Anlass: USA-AUS „AH Heim -1.5" hatte keinen Eintrag in MARKET_TO_PRICE_KEY →
    Fallback "hw" → bewertet mit der USA-Heimsieg-Moneyline (0.615) statt dem
    AH-Token-Preis (0.345) → Schein-Profit +80% → fälschlich auto-verkauft.

    Token-IDs sind global eindeutig. Wir scannen allFixtures nach dem Token in
    ah_edges[].tokens[0] (AH-Yes) bzw. poly_btts_tokens[0/1] (BTTS Ja/Nein) und
    geben den dort gespeicherten Live-Poly-Preis zurück. Mirror-immun.
    Kein Treffer → None → check_position verkauft NICHT (sicherer Default)."""
    if not token_id or not os.path.exists(PRICES_FILE):
        return None
    try:
        with open(PRICES_FILE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        return None
    def _ok(p):
        # Degenerierte/settled Preise (0/None) sind nicht handelbar → None
        # (kein Sell statt Phantom-P&L). Kleine echte Preise wie 0.05 bleiben gültig.
        return p if isinstance(p, (int, float)) and p > 0 else None
    for fx in cache.get("allFixtures", []):
        for e in (fx.get("ah_edges") or []):
            toks = e.get("tokens") or []
            if toks and toks[0] == token_id:
                return _ok(e.get("poly"))
        bt = fx.get("poly_btts_tokens") or []
        if len(bt) >= 1 and bt[0] == token_id:
            return _ok(fx.get("poly_btts"))
        if len(bt) >= 2 and bt[1] == token_id:
            return _ok(fx.get("poly_btts_no"))
    return None


def _is_token_market(market: str) -> bool:
    """AH/BTTS-Märkte werden NICHT über eine Moneyline-Preisspalte bewertet,
    sondern über den exakten Token (siehe _token_price_from_cache)."""
    m = market or ""
    return m.startswith("AH ") or m.startswith("Beide Teams treffen")


def check_position(pos: dict) -> dict:
    """
    Prüft eine offene Position und gibt ein Dict mit Status zurück.
    Setzt pos['currentPrice'], pos['pnlPct'], pos['sellReason'] etc.
    """
    slug       = pos.get("slug", "")
    market     = pos.get("market", "")
    market_key = pos.get("priceKey")        # hw/dr/aw/o25/u25 — None bei AH/BTTS/unbekannt
    entry      = pos.get("entryPrice", 0)
    pinn_fair  = pos.get("pinnFair", None)
    # match_key (homeId-awayId) ist Primär-Lookup im prices-Cache
    match_key  = f"{pos.get('homeId','')}-{pos.get('awayId','')}".strip("-")

    # ── Bewertung am REALISIERBAREN Bid (17.06.2026, universal für ALLE Märkte) ──
    # Jede Position trägt einen tokenId → wir holen das Live-Orderbuch und bewerten
    # am **Bid** (was wir beim Verkauf wirklich bekommen), NICHT am Mittelpreis.
    # Das killt den Spread-Phantom-Gewinn (USA-TUR: Mid +10% war real −4%).
    # Fallback nur wenn das Buch nicht erreichbar ist → Cache-Mid (degradiert,
    # markiert via priceSource, damit Guard + Anzeige es sehen).
    token_id = pos.get("tokenId", "")
    book = fetch_token_book(token_id)
    spread_pp = None
    if book:
        current = book["bid"]
        spread_pp = book["spreadPP"]
        pos["bookBid"]     = book["bid"]
        pos["bookAsk"]     = book["ask"]
        pos["spreadPP"]    = book["spreadPP"]
        pos["priceSource"] = "live_bid"
    else:
        # Degradierter Fallback: Cache-Mid. NICHT der echte Verkaufspreis →
        # P&L ist hier optimistisch; Guard/Anzeige markieren das.
        if _is_token_market(market):
            current = _token_price_from_cache(token_id)
        elif market_key:
            current = fetch_current_price(slug, market_key, match_key)
        else:
            current = None
        pos["priceSource"] = "cache_mid_fallback"
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
    profit_sell = False   # Profit-Mitnahme (vs Loss-Stop) — für den Spread-Guard unten
    if not in_play:
        # PRIMARY: Profit-Ziel erreicht (Cash-Cycle). current = REALER Bid → echter Gewinn.
        if entry > 0 and current >= entry * (1 + PROFIT_TARGET):
            sell = True; profit_sell = True
            reason = f"Profit +{round(pnl_pct, 1)}% ≥ +{PROFIT_TARGET*100:.0f}% Ziel"

        # SECONDARY: Poly konvergiert zu Pinnacle fair (innerhalb PINN_GAP_PP)
        if not sell and pinn_fair and (current - entry) * 100 >= MIN_PROFIT_PP * 100:
            gap = (pinn_fair - current) * 100
            if gap <= PINN_GAP_PP:
                sell = True; profit_sell = True
                reason = f"Markt konvergiert: Poly {current:.3f} ≈ Pinn fair {pinn_fair:.3f} (Δ{gap:.1f}pp)"

        # TERTIARY: Age-Decay — alte Position + kleiner Profit reicht
        if not sell and entry > 0 and age_h is not None and age_h >= AGE_DECAY_HOURS:
            if current >= entry * (1 + AGE_DECAY_PROFIT_TARGET):
                sell = True; profit_sell = True
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

        # LOSS 3: AGE-LOSS — alte Position + im Minus + Anpfiff NAH
        # → Spread frisst sonst Buchwert, lieber realisieren.
        # KO-Gate: NUR wenn hours_left <= AGE_LOSS_MAX_HOURS_LEFT. Tage vor dem Spiel
        # ist die These intakt → halten (kein Frühverkauf eines Spread-Minus).
        elif (age_h is not None
              and age_h >= AGE_LOSS_HOURS
              and loss_pct <= -AGE_LOSS_THRESHOLD_PCT
              and hours_left is not None
              and hours_left <= AGE_LOSS_MAX_HOURS_LEFT):
            sell = True
            reason = (f"Age-Loss: Position {age_h:.0f}h alt, "
                      f"{round(pnl_pct,1)}% im Minus, noch {hours_left:.1f}h bis KO "
                      f"— Spread frisst Buchwert")

    # ── GUARD (17.06.2026): Profit-Sell darf NIE in einen realen Verlust verkaufen ──
    # Belt-and-suspenders gegen die Spread-Phantom-Klasse: eine Profit-Mitnahme ist
    # nur erlaubt, wenn der echte Bid ÜBER dem Einstieg liegt UND der Spread nicht
    # absurd breit ist (sonst frisst der Verkauf den Buchgewinn). Loss-/Kickoff-Stops
    # bleiben unangetastet — da WOLLEN wir raus, egal wie der Spread steht.
    if sell and profit_sell:
        if entry > 0 and current <= entry:
            sell = False
            reason = ""
            pos["sellVetoed"] = f"Profit-Sell geblockt: Bid {current:.3f} ≤ Entry {entry:.3f} (Spread-Phantom)"
        elif pos.get("priceSource") == "cache_mid_fallback":
            # Audit-Fix 18.06.2026: kein Live-Buch → current ist der optimistische Cache-MID,
            # nicht der realisierbare Bid, und spread_pp ist None (Spread-Veto greift nicht).
            # Eine Profit-Mitnahme braucht einen verifizierten Bid → ohne Buch nicht verkaufen.
            # (Loss-/Kickoff-Stops bleiben erlaubt — da wollen wir RAUS, egal wie.)
            sell = False
            reason = ""
            pos["sellVetoed"] = "Profit-Sell geblockt: kein Live-Buch (cache_mid) — Bid nicht verifizierbar"
        elif spread_pp is not None and spread_pp > MAX_SELL_SPREAD_PP:
            sell = False
            reason = ""
            pos["sellVetoed"] = f"Profit-Sell geblockt: Spread {spread_pp:.1f}pp > {MAX_SELL_SPREAD_PP:.0f}pp"

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
        # FIX 16.06.2026: KEIN "hw"-Default mehr. AH/BTTS (+ unbekannte Märkte) haben
        # keine Moneyline-Preisspalte → priceKey=None, Bewertung läuft über den Token
        # (check_position._token_price_from_cache). Der alte Default "hw" bewertete
        # AH-Positionen mit der Heimsieg-Quote → Schein-Profit → Fehl-Sell.
        price_key = MARKET_TO_PRICE_KEY.get(market)
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
            # FIX 16.06.2026: echte Source übernehmen (auto/auto_steam) statt hart "auto"
            "source":         bet.get("source", "auto"),
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


def persist_auto_bet_valuations(positions: list) -> int:
    """Schreibt den ECHTEN (Bid-)Aktuell-Preis + P&L auf die OFFENEN Auto-Bets zurück
    (19.06.2026, Lucas). Vorher zeigte die Betting-Tab nur Totals P&L (client-seitig aus
    Cache-Preisen), AH/BTTS „—" weil es dafür kein flaches Preis-Feld gibt. manage hat den
    echten Bid (fetch_token_book) — wir persistieren ihn je betKey, die Tab zeigt ihn dann.
    Nur status=='placed'-Bets; verkaufte/aufgelöste bleiben unangetastet."""
    by_key = {p.get("_betKey"): p for p in positions
              if p.get("_betKey") and p.get("currentPrice") is not None}
    if not by_key or not os.path.exists(AUTO_BETS_FILE):
        return 0
    try:
        with open(AUTO_BETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  persist_auto_bet_valuations Lesefehler: {e}")
        return 0
    n = 0
    for bet in data.get("bets", []):
        if (bet.get("status") or "").lower() != "placed" or bet.get("soldAt"):
            continue
        p = by_key.get(bet.get("betKey"))
        if not p:
            continue
        bet["currentPrice"] = p.get("currentPrice")
        bet["pnlPct"]       = p.get("pnlPct")
        bet["priceSource"]  = p.get("priceSource")
        bet["valuedAt"]     = datetime.now(timezone.utc).isoformat()
        n += 1
    if n:
        data["updatedAt"] = datetime.now(timezone.utc).isoformat()
        with open(AUTO_BETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return n


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

    # ── Manuelle Eingriffe erkennen (23.06.2026, Lucas) ──────────────────────
    # Hat Lucas direkt auf Polymarket verkauft, hängt der Bet sonst ewig als 'placed'
    # → Dauer-Alerts. Gleicht ZUERST die echten Wallet-Positionen ab und markiert weg-
    # verkaufte (Spiel noch nicht fertig) als 'closed_manual'. load_auto_bets_as_positions
    # lädt danach nur noch 'placed' → keine Alerts mehr auf manuell geschlossene Positionen.
    try:
        import reconcile_poly_positions as _rec
        _rec.run()
    except Exception as _re:
        print(f"  ⚠️  reconcile übersprungen: {_re}")

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
        _wm = json.load(open(str(D.data_file()), encoding="utf-8"))
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

        # ── Zeit-basierte Exits: Hard-Close (20min) + Stop-Loss (16.06.2026) ──
        match_date = pos.get("matchDate", "")
        h_until = hours_until_match(match_date) if match_date else None
        time_sell, time_reason = time_based_exit(h_until, pnl)
        if time_sell:
            print(f"    ⏰ ZEIT-EXIT: {time_reason}")

        # Sell-Signal (aus check_position) oder Zeit-Exit → handeln
        should_sell = pos.get("sellSignal") or time_sell
        sell_reason = pos.get("sellReason") or time_reason

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
    # Echten Bid-Preis + P&L auf offene Auto-Bets persistieren → Betting-Tab zeigt ihn
    # (auch für AH/BTTS, die client-seitig kein Preis-Feld haben).
    _valued = persist_auto_bet_valuations(auto_positions)
    if _valued:
        print(f"  💾 {_valued} offene Auto-Bet(s) mit echtem Bid-P&L aktualisiert")
    write_book_health()   # Buch-Fetch-Gesundheit (nur wenn dieser Lauf Bücher abfragte)

    print(f"\n✅ Fertig — {alerts_sent} Alert(s) | {sells_executed} Auto-Sell(s) ausgeführt")
    if alerts_sent == 0 and sells_executed == 0 and open_pos:
        best = max(open_pos, key=lambda p: p.get("pnlPct") or -999)
        print(f"   Beste Position: {best.get('home')} vs {best.get('away')} "
              f"— {best.get('market')} @ {best.get('pnlPct', '?')}%")


if __name__ == "__main__":
    main()
