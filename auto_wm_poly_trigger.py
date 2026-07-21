#!/usr/bin/env python3
"""
auto_wm_poly_trigger.py — WM 2026 Auto-Bet Trigger
====================================================
Lädt wm_poly_prices.json, findet Fixtures mit ausreichend Edge,
filtert bereits platzierte Bets, und löst neue Bets aus.

Konfiguration:
    ENABLED = False          → Skript läuft durch aber platziert keine Bets (sicher!)
    AUTO_TRIGGER_EDGE_PP     → Mindest-Edge in Prozentpunkten (Standard: 4.0; war 5.0,
                               am 01.06.2026 gesenkt — Sweet Spot 3-5pp). Steam-Lag: 3.0.
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
import re
import time
import requests
from datetime import datetime, timezone, date

# ── Konfiguration ──────────────────────────────────────────────────────────────

# SICHERHEITSSCHALTER: False = Skript läuft aber platziert KEINE Bets
# Auf True setzen (oder AUTO_TRIGGER_ENABLED=true in Env) wenn bereit für Live-Trading
ENABLED = False

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
# Backwards-compatible: wenn cocobet_config fehlt, greift der Fallback-Default
# pro Konstante — Verhalten bleibt identisch zur Pre-Refactor-Version.
# WICHTIG: bei jeder Konstante ist der Default-Wert == aktueller hardcoded-Wert.
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# ── Edge-Schwellen ────────────────────────────────────────────────────────────
# Backtest 01.06.2026: AUTO_TRIGGER 5.0→4.0 (Sweet Spot 3-5pp = +14% ROI)
# STEAM_LAG 3.0: Backtest n=7 zu klein — bei 3.0 lassen, mit Live-Daten nachjustieren
AUTO_TRIGGER_EDGE_PP   = _cfg("trade", "auto_trigger_edge_pp",   4.0)
STEAM_LAG_EDGE_PP      = _cfg("trade", "steam_lag_edge_pp",      3.0)

# ── Match-Filter ──────────────────────────────────────────────────────────────
MIN_VOL                = _cfg("trade", "min_vol_usdc",           1500)
MIN_DAYS_UNTIL_GAME    = _cfg("trade", "min_days_until_game",       1)
MIN_HOURS_BEFORE_MATCH = _cfg("trade", "min_hours_before_match",    4)

# ── Quote/Entry-Price Filter (eingebaut 03.06.2026) ───────────────────────────
# Schützt gegen Extrem-Quoten wo Variance + Spread den theoretischen Edge auffressen:
#   • Entry < 0.15 USD (Quote > 6.67): hohe Variance, 5+ Loser in Folge normal
#   • Entry > 0.85 USD (Quote < 1.18): nur 17% max Upside, ein Loser frisst 5 Wins
# Sweet Spot 0.15-0.85 = Quote 1.18-6.67 — Liquidität dicht, Spread klein.
MIN_ENTRY_PRICE        = _cfg("trade", "min_entry_price",        0.15)
MAX_ENTRY_PRICE        = _cfg("trade", "max_entry_price",        0.85)

# Handicap-Trading (15.06.2026): Poly-Spreads vs Pinnacle-AH-Leiter.
AH_TRADE_ENABLED       = _cfg("trade", "ah_trade_enabled",       False)
# Plausibilitäts-Cap (Guard): ein echter AH-Edge vs Pinnacle ist klein. Alles
# darüber ist fast sicher ein Datenfehler (z.B. Mirror-Bug: Poly-Spread der
# falschen Seite). Solche „Edges" NIE traden. Fängt 30–56pp-Phantome sofort.
AH_MAX_EDGE_PP         = _cfg("trade", "ah_max_edge_pp",         12.0)
# AH-Preis-Floor (19.06.2026, Lucas): tiefe Handicaps unter ~20¢ sind rauschige Longshots —
# der „Edge" dort ist oft ein Polymarket-Dünnmarkt-Artefakt, nicht echter Wert, und die
# Pinnacle-Fair an extremen Linien ist unsicherer. Bis der AH-Tracker (analyze_ah_outcomes)
# zeigt, dass tiefe Linien +EV sind, kappen wir sie. Strenger als der allgemeine MIN_ENTRY_PRICE.
AH_MIN_ENTRY_PRICE     = _cfg("trade", "ah_min_entry_price",     0.20)
BTTS_TRADE_ENABLED     = _cfg("trade", "btts_trade_enabled",     True)
BTTS_MAX_EDGE_PP       = _cfg("trade", "btts_max_edge_pp",       12.0)

# ── Stake (flat) ──────────────────────────────────────────────────────────────
# €5 ≈ $5.50 USDC pro Pick. Bankroll-Schutz via DAILY_BET_CAP + DAILY_STAKE_CAP_USDC.
FLAT_STAKE_USDC        = _cfg("trade", "stake_usdc_flat",         5.5)

def _get_stake_for_edge(edge_pp: float) -> float:
    """Flat €5 ≈ $5.50 USDC pro Bet — Edge ist Schwellwert, nicht Sizing-Faktor."""
    return FLAT_STAKE_USDC

# ── Bankroll-Schutz ────────────────────────────────────────────────────────────
# Tageslimits verhindern dass viele Edges am Spieltag die ganze Bank durchfeuern.
DAILY_BET_CAP          = _cfg("trade", "daily_bet_cap",             8)
DAILY_STAKE_CAP_USDC   = _cfg("trade", "daily_stake_cap_usdc",   50.0)
MIN_BALANCE_BUFFER     = _cfg("trade", "min_balance_buffer",      1.0)
MAX_POSITIONS_PER_MATCH = _cfg("trade", "max_positions_per_match",  2)
                               # 2 = z.B. Über 2.5 + Heimsieg sind kompatible Wetten erlaubt.

# Open-Exposure-Cap: max kumulativer Stake in OFFENEN (nicht resolvierten) Positionen.
# Schützt gegen "Pre-Tournament Wallet-Lock": ohne diesen Cap würden Positionen aus 5-7 Tagen
# vor WM-Start die gesamte Bankroll binden, bevor erste Spielergebnisse Liquidität freigeben.
MAX_OPEN_EXPOSURE_USDC  = _cfg("trade", "max_open_exposure_usdc", 80.0)

# Pre-Tournament-Schwelle: für Spiele >5 Tage entfernt höhere Edge-Schwelle.
# Frühe Linien sind oft noch unsicher — Sharps geben dem Markt Zeit zur Korrektur.
#
# Hebel 2 (08.06.2026): GESTAFFELT statt binär.
# Vorher: >5 Tage = 6pp hart. Folge: vor WM-Start praktisch keine Trades,
# weil alle Spiele 3-14 Tage entfernt waren → 6pp ist Killer-Schwelle.
# Neu: linear interpoliert zwischen PRE_TOURNAMENT_DAYS (5 → AUTO_TRIGGER_EDGE_PP)
# und PRE_TOURNAMENT_FAR_DAYS (10 → PRE_TOURNAMENT_EDGE_PP).
#   d=5  → 4.0pp
#   d=7  → 4.8pp
#   d=10 → 6.0pp
#   d≥10 → 6.0pp
PRE_TOURNAMENT_DAYS    = _cfg("trade", "pre_tournament_days",       5)
PRE_TOURNAMENT_FAR_DAYS = _cfg("trade", "pre_tournament_far_days", 10)
PRE_TOURNAMENT_EDGE_PP = _cfg("trade", "pre_tournament_edge_pp",  6.0)

# Hebel 3 (08.06.2026): Engine-Hi-Confidence-Bonus.
# Wenn Signal-Engine SEHR positiv steht (≥3 positive Signale UND
# signalAdj ≥ +HI_CONF_ADJ_PP), senke Edge-Schwelle um HI_CONF_BONUS_PP.
# Logik: drei unabhängige positive Signale rechtfertigen aggressivere
# Stellungnahme. Symmetrisch zum Block-Gate (≤-3pp).
ENGINE_HI_CONF_POS_MIN = _cfg("trade", "engine_hi_conf_pos_min",     3)
ENGINE_HI_CONF_ADJ_PP  = _cfg("trade", "engine_hi_conf_adj_pp",    3.0)
ENGINE_HI_CONF_BONUS_PP = _cfg("trade", "engine_hi_conf_bonus_pp", 1.0)

# Adaptive Daily-Cap: skaliert mit verfügbarer Balance.
# effective_cap = min(DAILY_STAKE_CAP_USDC, available_balance × ADAPTIVE_DAILY_FRACTION)
# Bei $200 → $50 Cap. Bei $40 Balance → $16 Cap. Verhindert Restbankroll-Burn.
ADAPTIVE_DAILY_FRACTION = _cfg("trade", "adaptive_daily_fraction", 0.40)

import cocobet_dataset as D   # 29.06.2026: dataset-aware (MLS-Poly-Dry-Run)

BASE_DIR              = os.path.dirname(os.path.abspath(__file__))
# Dataset-aware: wm_* | liga_* | mls_* je COCOBET_DATASET. WM unverändert.
PRICES_FILE           = str(D.file("wm_poly_prices.json",      "liga_poly_prices.json"))
PLACED_FILE           = str(D.file("wm_auto_bets_placed.json", "liga_auto_bets_placed.json"))
BALANCE_FILE          = str(D.file("wm_poly_balance.json",     "liga_poly_balance.json"))
KILL_SWITCH_FILE      = str(D.file("wm_kill_switch.json",      "liga_kill_switch.json"))
WM_DATA_FILE          = str(D.data_file())

# Stale-Odds-Circuit-Breaker (11.06.2026): Der Edge = Pinnacle-Fair vs Live-Poly.
# Sind die Pinnacle-Odds eingefroren (fetch_wm_odds tot), wird Edge gegen alte
# Preise gerechnet → gefährliche Fehl-Trades. Bei zu alten Odds: KEIN Auto-Trade.
MAX_ODDS_AGE_HOURS    = _cfg("trade", "max_odds_age_hours", 24.0)


def newest_pinnacle_odds_age_h() -> float | None:
    """Alter (Stunden) der frischesten Pinnacle-Odds in wm2026-data.json.
    None wenn keine updatedAt-Timestamps gefunden werden."""
    try:
        from datetime import datetime as _dt, timezone as _tz
        with open(WM_DATA_FILE, encoding="utf-8") as f:
            odds = (json.load(f).get("odds") or {})
        newest = None
        for v in odds.values():
            ts = v.get("updatedAt") if isinstance(v, dict) else None
            if not ts:
                continue
            try:
                t = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=_tz.utc)
            except Exception:
                continue
            if newest is None or t > newest:
                newest = t
        if newest is None:
            return None
        return (_dt.now(_tz.utc) - newest).total_seconds() / 3600.0
    except Exception:
        return None


def is_kill_switch_active() -> tuple[bool, str]:
    """Liest wm_kill_switch.json. Returns (paused, reason).
    paused=True wenn Trading pausiert ist (enabled: false).

    K5 Fix 05.06.2026 — FAIL-CLOSED:
    Bei Lese-/Parse-Fehler wird Trading PAUSIERT (paused=True), nicht weitergelaufen.
    Begründung: Wenn ein Angreifer oder Bug die Kill-Switch-Datei korrumpieren würde,
    war der alte Code zahnlos — Korruption = grünes Licht. Jetzt: Korruption = Stop.
    Lucas muss die Datei dann manuell reparieren (= bewusste Entscheidung), bevor
    Trading wieder läuft. Fehlende Datei != Korruption — leer/fehlend ist "aktiv erlaubt".
    """
    if not os.path.exists(KILL_SWITCH_FILE):
        return False, ""
    try:
        with open(KILL_SWITCH_FILE, encoding="utf-8") as f:
            ks = json.load(f)
        if ks.get("enabled") is False:
            return True, ks.get("reason", "manuell pausiert")
        return False, ""
    except Exception as e:
        # FAIL-CLOSED: Bei Lese-Fehler PAUSIEREN, nicht weiterlaufen.
        print(f"  🚨  Kill-Switch lesefehler: {e} — fail-closed, Trading PAUSIERT")
        return True, f"Kill-Switch-Datei korrupt ({e}) — manuelle Prüfung nötig"

# Welche Edge-Keys → Polymarket-Market-Label (muss OUTCOME_MAP in polymarket_bet.py matchen)
# Field-Suffix wird auch für Engine-Felder genutzt: signalAdj_<field>, signalPos_<field>,
# effectiveEdge_<field>, engineDowngrade_<field>.
EDGE_MARKET_MAP = {
    "edge_hw":  ("poly_hw",  "Heimsieg",           "fair_hw",  "verdict_hw",  "hw"),
    "edge_dr":  ("poly_dr",  "Unentschieden",       "fair_dr",  "verdict_dr",  "dr"),
    "edge_aw":  ("poly_aw",  "Auswärtssieg",        "fair_aw",  "verdict_aw",  "aw"),
    "edge_o25": ("poly_o25", "Over 2.5 Tore",       "fair_o25", "verdict_o25", "o25"),
    "edge_u25": ("poly_u25", "Under 2.5 Tore",      "fair_u25", "verdict_u25", "u25"),
    # BTTS (15.06.2026): binär Ja/Nein, beide Seiten getrennt. Engine-Hook via
    # Card-Verdict/Conviction (wie O/U). Token aus Candidate (poly_btts_tokens).
    "edge_btts":    ("poly_btts",    "Beide Teams treffen — Ja",   "fair_btts",    "verdict_btts",    "btts"),
    "edge_btts_no": ("poly_btts_no", "Beide Teams treffen — Nein", "fair_btts_no", "verdict_btts_no", "btts_no"),
}

# BTTS-Trade-Schalter (15.06.2026) — wie AH ein Kill-Switch auf Markt-Ebene.
# Default an (BTTS ist ein normaler Pick-Markt wie O/U), aber separat abschaltbar.

# Nur diese Verdicts lösen Auto-Bets aus
# SKIP und None (kein Pick für diesen Markt) werden übersprungen
AUTO_TRIGGER_VERDICTS = {"BET", "ABWÄGEN"}

# ── Signal-Engine-Gates (eingebaut 08.06.2026) ────────────────────────────
# Bisher hat Auto-Trigger raw edgePP genutzt und die Engine komplett ignoriert.
# Folge: BET → ABWÄGEN-Downgrades durch Engine wirkten nicht, weil Auto-Trigger
# beide Verdicts traded. Jetzt: Engine-Warnungen blockieren Auto-Trades.
#   * Wenn signalAdj <= ENGINE_BLOCK_ADJ_PP  → Trade blocken (Engine warnt deutlich)
#   * Wenn engineDowngrade Feld gesetzt UND verdict==ABWÄGEN → Trade blocken
#     (die Engine hat einen BET aktiv auf ABWÄGEN heruntergestuft)
#   * Wenn signalPos < ENGINE_MIN_POS_FOR_ABWAEGEN UND verdict==ABWÄGEN → blocken
#   * Edge-Threshold wird gegen effectiveEdge geprüft (Engine-justierter Edge)
#     falls vorhanden, sonst Fallback auf raw edge.
ENGINE_BLOCK_ADJ_PP        = _cfg("trade", "engine_block_adj_pp",        -3.0)
ENGINE_MIN_POS_FOR_ABWAEGEN = _cfg("trade", "engine_min_pos_for_abwaegen", 2)

# Defense-in-Depth-Gates (09.06.2026, nach Niedrig-Edge-Incident).
# Hintergrund: 4 Trades wurden bei raw_edge +1.1pp/+1.4pp platziert,
# weil Engine-signalAdj den effectiveEdge über die 4pp-Schwelle pumpte.
# Card-Conviction war jedoch 2/10 — System war sich selbst nicht sicher.
#
# Gate A: Raw-Edge-Floor. Engine darf eine schwache Pinnacle-Edge nicht
# allein auf "tradeable" boosten. Der Polymarket-vs-Pinnacle Edge muss
# selbst mindestens MIN_RAW_EDGE_PP betragen.
MIN_RAW_EDGE_PP        = _cfg("trade", "min_raw_edge_pp",         2.0)
# Spread-Gate (17.06.2026): Eintritt wird gegen den ECHTEN Ask geprüft, nicht den
# Mid. real_edge = fair − ask muss MIN_RAW_EDGE_PP überleben, der Spread eng genug
# sein und das Buch liquide. Verhindert Trades, deren Mid-Edge der Spread auffrisst
# (USA-TUR: +5.2pp Mid-Edge war real nur +2.2pp gegen den 43¢-Ask).
MAX_ENTRY_SPREAD_PP    = _cfg("trade", "max_entry_spread_pp",     6.0)
# Post-Only-Retry (19.06.2026, Lucas): Polymarkets CLOB geht zeitweise in „post-only mode"
# (nur Maker-Orders erlaubt) → unsere Market-Order wird mit retry_after_seconds abgelehnt.
# Statt bis zum nächsten Cron zu warten, EINMAL im selben Lauf nach dem Backoff erneut
# probieren (gecappt). Fängt kurze Fenster ab (05:11 blockiert → 05:26 durch).
POST_ONLY_RETRY_MAX_S  = _cfg("trade", "post_only_retry_max_s",   120)
MIN_BOOK_LIQ_USDC      = _cfg("trade", "min_book_liq_usdc",      50.0)
# 17.06.2026 (Lucas): kein beidseitiges Orderbuch → KEIN Trade (statt blind zum Mid).
# Genau die dünnen AH/BTTS-Longshots (CPV-SAU BTTS Nein @+3.5pp Mid) hatten kein Buch →
# Spread-Gate übersprungen → real fast keine Edge nach dem Ask. Sicherer Default True.
REQUIRE_BOOK_FOR_ENTRY = _cfg("trade", "require_book_for_entry", True)
# 17.06.2026 (Lucas): der ENTSCHEIDENDE Floor auf der ECHTEN Ask-Edge (fair − ask, nach
# Spread) — entkoppelt vom Mid-Vorfilter. Die alten 5pp waren Mid (~3pp real); 4pp ECHT
# ist sauberer + strenger und schneidet dünne Longshots raus. MIN_RAW_EDGE_PP (2.0) bleibt
# der Mid-Sanity-Vorfilter.
MIN_ASK_EDGE_PP        = _cfg("trade", "min_ask_edge_pp",         4.0)
#
# Gate B: Conviction-Score-Floor. Wenn der Pick auf der Card weniger als
# MIN_CONVICTION_FOR_AUTO/10 Punkte hat, blockt der Auto-Trigger.
# Picks ohne Conviction-Feld (pre-Engine-Daten) werden NICHT geblockt —
# Backwards-compat. Synthetische saferAlt-Picks bekommen einen Bonus von +1
# (sie sind designed um "ABWÄGEN mit Insurance" zu sein).
MIN_CONVICTION_FOR_AUTO = _cfg("trade", "min_conviction_for_auto",   3)

# elo_only = noch keine Form-/H2H-Daten (Pre-Tournament) → konservativerer Edge-Schwellenwert
# Erhöhter Schwellenwert verhindert Bets auf schwache Datenbasis
AUTO_TRIGGER_EDGE_ELO_ONLY = _cfg("trade", "auto_trigger_edge_elo_only", 8.0)


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


# ── Gemeinsame Wallet über alle Datensätze (18.07.2026) ─────────────────────────────────────
# WM, Liga und MLS traden auf DERSELBEN Polymarket-Wallet. Balance und Limits sind deshalb
# wallet-weit, nicht datensatz-weit. Die Dateien liegen aber pro Datensatz vor.
_DATASET_PREFIXES = ("wm_", "liga_", "mls_")


def _load_wallet_balance():
    """Frischeste Balance über ALLE Datensatz-Dateien. → (data, quelle)

    Der eigene Datensatz hat Vorrang, wenn er aktuell ist; sonst zählt der jüngste Stand aus
    einer anderen Datei. Es ist physisch dieselbe Wallet — welcher Lauf sie zuletzt abgefragt
    hat, ist für den Kontostand egal.
    """
    best, best_ts, best_src = None, "", "—"
    for pfx in _DATASET_PREFIXES:
        p = os.path.join(BASE_DIR, f"{pfx}poly_balance.json")
        d = load_json(p, None)
        if not isinstance(d, dict) or d.get("usdc") is None:
            continue
        ts = str(d.get("updatedAt") or "")
        if best is None or ts > best_ts:
            best, best_ts, best_src = d, ts, os.path.basename(p)
    return (best or {"usdc": 0.0}), best_src


def _cross_dataset_exposure(today_str: str):
    """Offene + heutige Stakes der ANDEREN Datensätze. → (offen, heute, anzahl)

    Ohne das würde jeder Datensatz sein Tages-/Exposure-Limit auf die volle gemeinsame Balance
    rechnen — WM, Liga und MLS könnten zusammen ein Vielfaches des gewollten Einsatzes platzieren.
    """
    eigen = os.path.basename(PLACED_FILE)
    offen = heute = 0.0
    n = 0
    for pfx in _DATASET_PREFIXES:
        name = f"{pfx}auto_bets_placed.json"
        if name == eigen:
            continue                      # eigener Datensatz ist schon gezählt
        d = load_json(os.path.join(BASE_DIR, name), None)
        for b in ((d or {}).get("bets") or []):
            if not isinstance(b, dict):
                continue
            stake = float(b.get("stake") or 0)
            if not b.get("resolved") and not b.get("soldAt"):
                offen += stake
                n += 1
            if (b.get("placedAt") or "")[:10] == today_str:
                heute += stake
    return offen, heute, n


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

def is_homeaway_swap_suspect(fix: dict) -> bool:
    """Spiegelt die Integritäts-Guard-Logik (homeaway_consistent): wenn die Pinnacle-
    Favorit-Seite der Poly-Favorit-Seite widerspricht (bei merklicher Differenz), ist die
    1X2-Orientierung fragwürdig → der 1X2-Edge ist phantom/invertiert. Befund 16.06.2026:
    CPV-SAU lieferte +4.6pp auf CPV-Heimsieg, obwohl Poly SAU favorisiert (Swap-Verdacht).
    Dann KEIN Auto-Trade auf hw/dr/aw. O/U/BTTS/AH sind orientierungs-unabhängig → erlaubt."""
    hw, aw = fix.get("pinn_hw"), fix.get("pinn_aw")
    phw, paw = fix.get("poly_hw"), fix.get("poly_aw")
    if not all(isinstance(x, (int, float)) for x in (hw, aw, phw, paw)):
        return False
    if not (hw > 1 and aw > 1 and 0 < phw < 1 and 0 < paw < 1):
        return False
    return abs(hw - aw) > 0.15 and (hw < aw) != (phw > paw)


def _is_transient_exchange_error(err: str) -> bool:
    e = (err or "").lower()
    return ("post_only" in e or "post-only" in e or "retry_after" in e
            or "status_code=503" in e or "503" in e)


def _parse_retry_after_s(err: str) -> int:
    m = re.search(r"retry_after_seconds['\"]?\s*[:=]\s*(\d+)", err or "")
    return int(m.group(1)) if m else 0


def place_order_with_retry(place_fn, token_id, stake, private_key, fill_price):
    """Market-Order platzieren; bei TRANSIENTEM Börsen-Fehler (Post-Only-Modus / 503) EINMAL
    nach dem von der Börse genannten Backoff (gecappt auf POST_ONLY_RETRY_MAX_S) erneut
    versuchen. Andere Fehler (Creds, FOK, Balance) werden NICHT geretryt — die löst der
    Retry nicht. place_fn = polymarket_bet.place_market_order (injiziert für Testbarkeit)."""
    result = place_fn(token_id, float(stake), private_key, price_hint=float(fill_price))
    if result.get("status") in ("placed", "dry-run"):
        return result
    err = str(result.get("error") or "")
    if not _is_transient_exchange_error(err):
        return result
    wait = min((_parse_retry_after_s(err) or 100) + 5, POST_ONLY_RETRY_MAX_S)
    print(f"    ⏳ Post-Only/503 (transient) — warte {wait}s und versuche EINMAL erneut…")
    time.sleep(wait)
    return place_fn(token_id, float(stake), private_key, price_hint=float(fill_price))


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
        # B1 Fix 05.06.2026: elo+form_asym = nur ein Team hat Form-Daten →
        # genauso unsicher wie elo_only, höhere Edge-Schwelle anwenden.
        is_asym = fix.get("dataQuality") == "elo+form_asym"
        has_steam_lag = bool(fix.get("steamLag"))

        # Effektiver Edge-Schwellenwert (Basis):
        #  - steamLag=True: niedrigere Hürde (Pinn hat bereits bewegt → Signal ist valide)
        #  - elo_only / asym: höhere Hürde (schwache/asymmetrische Datenbasis)
        #  - normal: AUTO_TRIGGER_EDGE_PP
        if has_steam_lag:
            base_threshold = STEAM_LAG_EDGE_PP
        elif is_elo_only or is_asym:
            base_threshold = AUTO_TRIGGER_EDGE_ELO_ONLY
        else:
            base_threshold = AUTO_TRIGGER_EDGE_PP

        # Pre-Tournament Edge-Verschärfung — Hebel 1+2 (08.06.2026)
        #
        # Hebel 1: Steam-Lag ist IMMUN gegen Pre-Tournament-Anhebung.
        # Steam-Lag IST das Sharp-Signal — Pinnacle hat sich bereits bewegt,
        # Polymarket hinkt hinterher. Vor WM-Start auf Konvergenz warten
        # widerspricht der Logik des Signals.
        #
        # Hebel 2: Gestaffelte Schwelle statt binär.
        # d=PRE_TOURNAMENT_DAYS → AUTO_TRIGGER_EDGE_PP (4pp)
        # d=PRE_TOURNAMENT_FAR_DAYS → PRE_TOURNAMENT_EDGE_PP (6pp)
        # Linear interpoliert dazwischen, geclamped darüber.
        if (d is not None and d > PRE_TOURNAMENT_DAYS
                and not has_steam_lag):
            span = max(PRE_TOURNAMENT_FAR_DAYS - PRE_TOURNAMENT_DAYS, 1)
            if d >= PRE_TOURNAMENT_FAR_DAYS:
                pre_thr = PRE_TOURNAMENT_EDGE_PP
            else:
                ratio = (d - PRE_TOURNAMENT_DAYS) / span
                pre_thr = AUTO_TRIGGER_EDGE_PP + ratio * (
                    PRE_TOURNAMENT_EDGE_PP - AUTO_TRIGGER_EDGE_PP)
            base_threshold = max(base_threshold, pre_thr)

        # Edge-Check für jeden Markt
        for edge_key, (price_key, market_label, fair_key, verdict_key, fld) in EDGE_MARKET_MAP.items():
            # BTTS-Markt-Schalter (15.06.2026): separat abschaltbar.
            if fld in ("btts", "btts_no") and not BTTS_TRADE_ENABLED:
                continue
            # Home/Away-Swap-Schutz (16.06.2026): bei fragwürdiger 1X2-Orientierung
            # (Pinn-Fav ≠ Poly-Fav) ist der 1X2-Edge phantom → KEIN Trade auf hw/dr/aw.
            if fld in ("hw", "dr", "aw") and is_homeaway_swap_suspect(fix):
                print(f"  🛑 Home/Away-Swap-Verdacht (Pinn-Fav ≠ Poly-Fav) — "
                      f"{fix['home']} vs {fix['away']} {market_label} (1X2 BLOCKED)")
                continue
            stored_edge = fix.get(edge_key)

            # ── Stale-Edge-Schutz (11.06.2026) ──────────────────────────────
            # Das gespeicherte edge_X kann veralten: bewegt sich Pinnacle, werden
            # fair_X/poly_X frisch geschrieben, edge_X aber u.U. aus einem alten
            # Lauf mitgeschleppt (real beobachtet bei JPN-SWE: edge_aw=-1.4 obwohl
            # fair_aw-poly_aw=+7.1pp). Kanonische Quelle ist IMMER fair_X - poly_X.
            # Wenn beide Rohwerte da sind, rechnen wir die Edge live und ignorieren
            # das gespeicherte Feld. Bei Abweichung: lauter Hinweis (Stale-Guard).
            fair_now = fix.get(fair_key)
            poly_now = fix.get(price_key)
            if isinstance(fair_now, (int, float)) and isinstance(poly_now, (int, float)) and poly_now > 0:
                raw_edge = round((fair_now - poly_now) * 100, 1)
                if isinstance(stored_edge, (int, float)) and abs(raw_edge - stored_edge) > 0.5:
                    print(f"  ⚠️  Stale edge_{fld}: gespeichert {stored_edge:+.1f}pp ≠ live "
                          f"{raw_edge:+.1f}pp — nutze live (fair {fair_now:.4f} − poly {poly_now:.4f}) "
                          f"[{fix['home']} vs {fix['away']}]")
            else:
                raw_edge = stored_edge

            # BTTS-Phantom-Cap (15.06.2026): unplausibel großer Edge → Datenfehler-
            # Verdacht (z.B. settled-Markt poly 0/1) → NIE traden. Defense-in-Depth
            # analog zum AH-Cap; Entry-Price-Filter fängt das meiste, der Cap den Rest.
            if fld in ("btts", "btts_no") and isinstance(raw_edge, (int, float)) and abs(raw_edge) > BTTS_MAX_EDGE_PP:
                print(f"  🛑 BTTS-Edge {raw_edge:+.1f}pp > {BTTS_MAX_EDGE_PP}pp Cap "
                      f"(Datenfehler-Verdacht) — {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # Poly-Strang ist Pinnacle-vs-Poly-Edge-getrieben (11.06.2026):
            # Für die TRADE-Entscheidung zählt die Edge zu Polymarket, NICHT unser
            # Modell. effectiveEdge (= raw + signalAdj) stammt aus generate_wm_picks
            # und kann ebenfalls veralten — daher Entscheidungs-Edge = live raw edge.
            # Die Signal-Engine bleibt nur als BREMSE aktiv (Block-Gates unten).
            edge = raw_edge

            # Hebel 3 (08.06.2026): Engine-Hi-Conf-Bonus pro Markt.
            # ≥3 positive Signale + signalAdj ≥ +3pp → Schwelle -1pp.
            # Lower-bound auf STEAM_LAG_EDGE_PP — nie unter den Sharp-Floor.
            sig_adj_pre = fix.get(f"signalAdj_{fld}")
            sig_pos_pre = fix.get(f"signalPos_{fld}")
            market_threshold = base_threshold
            if (isinstance(sig_pos_pre, int) and sig_pos_pre >= ENGINE_HI_CONF_POS_MIN
                    and isinstance(sig_adj_pre, (int, float))
                    and sig_adj_pre >= ENGINE_HI_CONF_ADJ_PP):
                market_threshold = max(
                    base_threshold - ENGINE_HI_CONF_BONUS_PP,
                    STEAM_LAG_EDGE_PP,
                )

            if edge is None or edge < market_threshold:
                continue

            # ── Defense-in-Depth Gate A (09.06.2026): Raw-Edge-Floor ─────────
            # Engine darf eine schwache raw Edge nicht allein über die Schwelle
            # boosten. raw_edge muss selbst MIN_RAW_EDGE_PP erreichen.
            # Wenn raw_edge fehlt (None): konservativ blocken — Pre-Engine-Daten
            # gibt es bei WM 2026 nicht mehr.
            if raw_edge is None or raw_edge < MIN_RAW_EDGE_PP:
                raw_str = f"{raw_edge:+.1f}pp" if isinstance(raw_edge, (int, float)) else "fehlt"
                print(f"  🛑 Raw-Edge {raw_str} < {MIN_RAW_EDGE_PP}pp Floor "
                      f"(eff={edge:+.1f}pp) — {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # ── Defense-in-Depth Gate B (09.06.2026): Conviction-Floor ───────
            # Wenn Card-Conviction < MIN_CONVICTION_FOR_AUTO, kein Auto-Trade.
            # Engine soll nicht traden was sich selbst nicht überzeugt.
            # Picks ohne Conviction-Feld (alte Daten) werden NICHT geblockt.
            conv = fix.get(f"conviction_{fld}")
            if isinstance(conv, (int, float)) and conv < MIN_CONVICTION_FOR_AUTO:
                print(f"  🛑 Conviction {conv}/10 < {MIN_CONVICTION_FOR_AUTO} "
                      f"— {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # ── Defense-in-Depth Gate C (09.06.2026): trackingExcluded ───────
            # Cross-Market-Konflikt-Filter hat diesen Pick aus Card+Tracking
            # geworfen — der Auto-Trigger soll ihn dann auch nicht traden.
            if fix.get(f"trackingExcluded_{fld}"):
                print(f"  🛑 trackingExcluded gesetzt "
                      f"— {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # Verdict-Check (11.06.2026 überarbeitet): Der Poly-Strang braucht KEIN
            # Modell-Verdict. Die Funktion handelt auf der Edge zu Polymarket
            # (Pinnacle-fair vs Poly) — unser Modell ist hier irrelevant. Darum ist
            # verdict=None (kein Modell-Pick auf diesem Outcome, z.B. JPN-SWE
            # Schweden) ausdrücklich ERLAUBT.
            # Einzige Ausnahme: verdict=SKIP = aktives Veto unseres Modells (z.B.
            # Cross-Market-Konflikt) → bleibt geblockt. ABWÄGEN/BET laufen normal,
            # ihre zusätzlichen Signal-Gates unten greifen weiterhin.
            verdict = fix.get(verdict_key)
            if verdict == "SKIP":
                print(f"  🚫 Verdict=SKIP (Modell-Veto) — {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # ── Signal-Engine Gates (08.06.2026) ─────────────────────────────
            sig_adj  = fix.get(f"signalAdj_{fld}")
            sig_pos  = fix.get(f"signalPos_{fld}")
            sig_dwn  = fix.get(f"engineDowngrade_{fld}")

            # Gate 1: Engine warnt deutlich (Summe der Signale ≤ -3pp)
            if isinstance(sig_adj, (int, float)) and sig_adj <= ENGINE_BLOCK_ADJ_PP:
                print(f"  🛑 Engine-Warnung ({sig_adj:+.1f}pp ≤ {ENGINE_BLOCK_ADJ_PP}pp) "
                      f"— {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # Gate 2: Engine hat BET → ABWÄGEN heruntergestuft → KEIN Trade
            # (sig_dwn ist nur gesetzt wenn der Pick wirklich downgegraded wurde)
            if verdict == "ABWÄGEN" and sig_dwn:
                print(f"  🛑 Engine-Downgrade aktiv: {sig_dwn} "
                      f"— {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
                continue

            # Gate 3: Bei ABWÄGEN ohne explizites Downgrade — wenig positive Signale
            # → vorsichtshalber nicht traden. BETs ohne sig_pos werden NICHT geblockt
            # (Backwards-compat für Picks ohne Engine-Output).
            if (verdict == "ABWÄGEN" and isinstance(sig_pos, int)
                    and sig_pos < ENGINE_MIN_POS_FOR_ABWAEGEN):
                print(f"  🛑 Nur {sig_pos} positive Engine-Signale für ABWÄGEN-Pick "
                      f"(min {ENGINE_MIN_POS_FOR_ABWAEGEN}) — {fix['home']} vs {fix['away']} {market_label} (BLOCKED)")
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

            # Slug: für O/U + BTTS den moreMktSlug verwenden, sonst den Moneyline-Slug
            is_more_mkt = fld in ("o25", "u25", "btts", "btts_no")
            slug = (fix.get("moreMktSlug") or fix.get("slug")) if is_more_mkt else fix.get("slug")
            event_url = (
                f"https://polymarket.com/sports/fifa-world-cup/{slug}"
                if slug else None
            )

            # BTTS-Token direkt aus den geparsten clobTokenIds (15.06.2026):
            # poly_btts_tokens = [Yes-Token, No-Token]. find_clob_token_id kennt
            # den BTTS-Markt nicht zuverlässig → Token-Fast-Path wie bei AH.
            _btts_tokens = fix.get("poly_btts_tokens") or []
            _btts_token = None
            if fld == "btts" and len(_btts_tokens) >= 1:
                _btts_token = _btts_tokens[0]
            elif fld == "btts_no" and len(_btts_tokens) >= 2:
                _btts_token = _btts_tokens[1]
            if fld in ("btts", "btts_no") and not _btts_token:
                print(f"  🚫 BTTS ohne Token — {fix['home']} vs {fix['away']} {market_label} (nicht platzierbar)")
                continue

            candidates.append({
                "home":        fix["home"],
                "away":        fix["away"],
                "homeId":      fix.get("homeId", ""),
                "awayId":      fix.get("awayId", ""),
                "market":      market_label,
                "league":      "WM2026",
                "stake":       _get_stake_for_edge(edge),
                **({"tokens": [_btts_token], "_isBtts": True} if _btts_token else {}),
                "polyPrice":   poly_price,
                "slug":        slug,
                "eventUrl":    event_url,
                "edgePP":           raw_edge,            # raw Pinnacle vs Polymarket
                "effectiveEdgePP":  edge,                # Engine-justiert
                "signalAdjPP":      sig_adj,             # Engine-Signal-Summe
                "signalCountPos":   sig_pos,             # positive Signale
                "pinnFair":    fix.get(fair_key),
                "verdict":     verdict,
                "dataQuality": fix.get("dataQuality", "elo_only"),
                "isSteamLag":  has_steam_lag,
                "matchDate":   (fix.get("date") or "")[:10],
                "kickoff":     fix.get("kickoff"),   # echte Anpfiffzeit (UTC) für 2h-Pre-Match-Close
                "_betKey":     key,   # intern, wird vor Übergabe an polymarket_bet entfernt
            })

        # ── Handicap-Edges (15.06.2026): Poly-Spreads vs Pinnacle-AH-Leiter ──────
        # Edge-getrieben (ah.edge = fair − poly, vorberechnet in fetch_wm_poly_prices).
        # Schlanke Gates: Edge-Floor (max base/Raw) + Entry-Price + Dedup + Token da.
        # Keine per-Outcome-Signal-Felder (AH hat keine) → konservativ rein auf der
        # Pinnacle-vs-Poly-Edge. Default-AUS bis Token-Platzierung verifiziert.
        if AH_TRADE_ENABLED:
            for ah in (fix.get("ah_edges") or []):
                ah_edge    = ah.get("edge")
                poly_price = ah.get("poly")
                tokens     = ah.get("tokens") or []
                if ah_edge is None or ah_edge < max(base_threshold, MIN_RAW_EDGE_PP):
                    continue
                # Guard: unplausibel großer Edge → Datenfehler (z.B. Mirror) → NIE traden
                if ah_edge > AH_MAX_EDGE_PP:
                    print(f"  🛑 AH-Edge {ah_edge:+.1f}pp > {AH_MAX_EDGE_PP}pp Cap "
                          f"(Datenfehler-Verdacht) — {fix['home']} vs {fix['away']} {ah.get('side')} {ah.get('line')} (BLOCKED)")
                    continue
                # AH-Preis-Floor: tiefe/dünne Longshot-Linien (< ~20¢) kappen, bis der
                # AH-Tracker beweist, dass sie +EV sind (Lucas 19.06.2026).
                if poly_price is not None and poly_price < AH_MIN_ENTRY_PRICE:
                    print(f"  🚫 AH {ah.get('side')} {ah.get('line')} @ {round((poly_price or 0)*100)}¢ "
                          f"< {round(AH_MIN_ENTRY_PRICE*100)}¢ AH-Floor — Longshot übersprungen "
                          f"({fix['home']} vs {fix['away']})")
                    continue
                if not poly_price or poly_price < MIN_ENTRY_PRICE or poly_price > MAX_ENTRY_PRICE:
                    continue
                if not tokens:
                    continue   # ohne Spread-Token nicht platzierbar
                side_lbl     = "Heim" if ah.get("side") == "home" else "Auswärts"
                market_label = f"AH {side_lbl} {ah['line']:+g}"
                key = bet_key(fix, market_label)
                if key in placed_keys:
                    continue
                _slug = fix.get("moreMktSlug") or fix.get("slug")
                candidates.append({
                    "home":        fix["home"],
                    "away":        fix["away"],
                    "homeId":      fix.get("homeId", ""),
                    "awayId":      fix.get("awayId", ""),
                    "market":      market_label,
                    "league":      "WM2026",
                    "stake":       _get_stake_for_edge(ah_edge),
                    "polyPrice":   poly_price,
                    "slug":        _slug,
                    "eventUrl":    f"https://polymarket.com/sports/fifa-world-cup/{_slug}" if _slug else None,
                    "edgePP":          ah_edge,
                    "effectiveEdgePP": ah_edge,
                    "pinnFair":    ah.get("fair"),
                    "tokens":      tokens,          # Spread-Token (Yes) für Platzierung
                    "verdict":     None,
                    "dataQuality": fix.get("dataQuality", "elo_only"),
                    "isSteamLag":  has_steam_lag,
                    "matchDate":   (fix.get("date") or "")[:10],
                    "kickoff":     fix.get("kickoff"),
                    "_betKey":     key,
                    "_isHandicap": True,
                })

    return candidates


def main():
    print(f"\n{'='*55}")
    # Datensatz im Header zeigen (12.07.2026): im MLS-Lauf stand hier „WM 2026" → verwirrend.
    print(f"  🤖 {D.active_dataset().upper()} Auto-Trigger — "
          f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}\n")

    # Kill-Switch zuerst prüfen — hat Vorrang vor allen anderen Schaltern
    killed, kill_reason = is_kill_switch_active()
    if killed:
        print(f"🛑 KILL-SWITCH AKTIV — Trading pausiert.")
        print(f"   Grund: {kill_reason}")
        print(f"   Resume via GitHub Action 'Kill-Switch' → action=resume\n")
        return

    # 21.07.2026 (WM-Winterisierung): Ist das Turnier beendet, sind die Pinnacle-Odds ERWARTET
    # veraltet (fetch_wm_odds ist bewusst still gelegt) — dann NICHT traden und vor allem NICHT
    # den Stale-Odds-Circuit-Breaker gegen ein totes Turnier feuern lassen. Der spammte sonst den
    # Trades-Channel („STALE-ODDS-STOP … 32h alt"), egal welcher Runner den Trigger noch anstößt.
    # Universell: eine laufende Liga/MLS ist NIE „over" → normaler Betrieb bleibt unberührt.
    try:
        if D.tournament_is_over(load_json(WM_DATA_FILE, {}) or {}):
            print(f"🏁 {D.active_dataset().upper()} beendet — kein Auto-Trade, kein Stale-Alarm (winterisiert).\n")
            return
    except Exception:
        pass

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

    # ── Stale-Odds-Circuit-Breaker (11.06.2026) ──────────────────────────
    # Edge = Pinnacle-Fair vs Live-Poly. Wenn die Pinnacle-Odds eingefroren sind
    # (fetch_wm_odds tot), wäre jeder Edge gegen veraltete Preise gerechnet →
    # gefährliche Fehl-Trades. Dann lieber gar nicht traden.
    odds_age = newest_pinnacle_odds_age_h()
    if odds_age is not None and odds_age > MAX_ODDS_AGE_HOURS:
        msg = (f"🛑 STALE-ODDS-STOP: frischeste Pinnacle-Odds {odds_age:.1f}h alt "
               f"(> {MAX_ODDS_AGE_HOURS:.0f}h Limit) — fetch_wm_odds eingefroren? "
               f"KEIN Auto-Trade, Edge gegen veraltete Preise wäre gefährlich.")
        print("  " + msg + "\n")
        _tok  = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
        _chat = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()
        if _tok and _chat:
            send_telegram(_tok, _chat, "⚠️ <b>Auto-Trade gestoppt</b>\n" + msg)
        return
    if odds_age is not None:
        print(f"  🕐 Pinnacle-Odds {odds_age:.1f}h alt (Limit {MAX_ODDS_AGE_HOURS:.0f}h) — ok\n")

    # 2. Bereits platzierte Bets laden
    placed_data = load_json(PLACED_FILE, {"bets": [], "updatedAt": ""})
    placed_bets = placed_data.get("bets", [])
    placed_keys = {b["betKey"] for b in placed_bets if b.get("betKey")}
    # Match-Level Dedup: zähle wie viele Bets schon auf jedes Match liegen
    # (egal welcher Markt). Verhindert gegenläufige Heim+Auswärts-Positionen.
    # Audit-Fix 18.06.2026: nur OFFENE Positionen zählen (resolved/verkaufte raus). Das
    # MAX_POSITIONS_PER_MATCH-Limit cappt die gleichzeitige Exposure pro Match, nicht die
    # Lebenszeit. Vorher zählten aufgelöste UND verkaufte Bets mit → nach 2 frühen Sells
    # vor Anpfiff blockierte ein legitimer Re-Entry fälschlich (gleiche Logik wie open_bets).
    match_position_count = {}
    for b in placed_bets:
        if b.get("resolved") or b.get("soldAt"):
            continue
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

    # ── 18.07.2026 (Lucas: „Auto-Trading muss für MLS/Liga laufen") ──────────────────────────
    # EINE WALLET, MEHRERE DATENSÄTZE. Die Balance wurde pro Datensatz gelesen
    # (mls_poly_balance.json). Existiert die Datei nicht — weil der self-hosted MLS-Workflow noch
    # nicht lief — sah der Trigger $0.00, kappte seinen Daily-Cap auf 0 und brach ab, obwohl die
    # Wallet real $162 hatte (in wm_poly_balance.json). Genau das blockierte MLS komplett.
    #
    # Fix: Balance über ALLE Datensatz-Dateien suchen und die FRISCHESTE nehmen — es ist physisch
    # dieselbe Wallet, egal welcher Lauf sie zuletzt abgefragt hat.
    balance_data, _bal_src = _load_wallet_balance()
    available_balance = float(balance_data.get("usdc") or 0)
    print(f"  💼 Verfügbare Balance: ${available_balance:.2f} USDC  (Quelle: {_bal_src})")

    # ⚠️ KEHRSEITE derselben Medaille: Wenn alle Datensätze dieselbe Wallet teilen, darf NICHT
    # jeder sein Tages-/Exposure-Limit auf die volle Balance rechnen — sonst setzen WM+Liga+MLS
    # zusammen ein Vielfaches ein. Limits deshalb über ALLE Datensätze summieren.
    _fremd_open, _fremd_today, _fremd_n = _cross_dataset_exposure(today_str)
    if _fremd_open or _fremd_today:
        open_exposure += _fremd_open
        stake_today += _fremd_today
        print(f"  🔗 Andere Datensätze: +${_fremd_open:.2f} offen, +${_fremd_today:.2f} heute "
              f"({_fremd_n} Bets) — gemeinsame Wallet, Limits gelten global")

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
        eff_str  = (f", eff {c['effectiveEdgePP']:+.1f}pp"
                    if isinstance(c.get('effectiveEdgePP'), (int, float))
                    and c.get('effectiveEdgePP') != c.get('edgePP') else "")
        sig_str  = (f"  |  Signale: {c['signalAdjPP']:+.1f}pp ({c.get('signalCountPos') or 0}+)"
                    if isinstance(c.get('signalAdjPP'), (int, float)) else "")
        print(f"    • {c['home']} vs {c['away']} — {c['market']}")
        print(f"      Edge: +{c['edgePP']}pp{eff_str}  |  Poly: {odds_str}  |  Einsatz: ${c['stake']:.2f} USDC{sig_str}")

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

        # ── Token-Auflösung ──────────────────────────────────────────────────
        # HANDICAP (15.06.2026): Spread-Token wurde in fetch_wm_poly_prices EXAKT
        # erfasst (Poly clobTokenIds) und im Candidate mitgegeben. find_clob_token_id
        # kennt Spread-Märkte NICHT → würde falschen Token treffen. Daher für AH den
        # Token direkt nehmen: tokens[0] = YES = „Team deckt das Handicap".
        token_id = None
        if order.get("_isHandicap") and order.get("tokens"):
            token_id = order["tokens"][0]
            print(f"    🎯 Handicap — Spread-Token direkt aus Candidate: {token_id[:16]}…")
        elif order.get("_isBtts") and order.get("tokens"):
            # BTTS-Token (Yes bzw. No) wurde in fetch_wm_poly_prices exakt erfasst.
            token_id = order["tokens"][0]
            print(f"    🎯 BTTS — Outcome-Token direkt aus Candidate: {token_id[:16]}…")

        if not token_id:
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

        print(f"    📍 Token: {token_id[:16]}…  |  Mid-Preis: {round(poly_p*100)}¢")

        # ── Spread-Gate (17.06.2026): gegen den ECHTEN Ask prüfen ──────────────
        # Der Candidate hat die Mid-Edge bestanden. Aber gekauft wird über den Ask,
        # verkauft über den Bid — auf dünnen Märkten frisst der Spread die Edge.
        # Hier der letzte Check vor echtem Geld: echte Edge = fair − ask, Spread eng,
        # Buch liquide. Buch nicht erreichbar → Fallback Mid (Exit-Guard schützt dann).
        fill_price   = poly_p   # Fallback = Mid (bisheriges Verhalten)
        entry_ask    = None
        entry_spread = None
        try:
            from manage_wm_poly_positions import fetch_token_book
            _book = fetch_token_book(token_id)
        except Exception:
            _book = None
        if _book:
            entry_ask    = _book["ask"]
            entry_spread = _book["spreadPP"]
            liq          = _book.get("liqUSD")
            fair         = order.get("pinnFair")
            real_edge_pp = ((fair - entry_ask) * 100
                            if isinstance(fair, (int, float)) else None)
            if entry_spread > MAX_ENTRY_SPREAD_PP:
                print(f"    🛑 Spread {entry_spread:.1f}pp > {MAX_ENTRY_SPREAD_PP:.0f}pp — übersprungen (Spread frisst Edge)")
                continue
            if liq is not None and liq < MIN_BOOK_LIQ_USDC:
                print(f"    🛑 Buch-Liquidität ${liq:.0f} < ${MIN_BOOK_LIQ_USDC:.0f} — übersprungen")
                continue
            if real_edge_pp is not None and real_edge_pp < MIN_ASK_EDGE_PP:
                print(f"    🛑 Echte Ask-Edge {real_edge_pp:.1f}pp (fair−ask {entry_ask:.3f}) < {MIN_ASK_EDGE_PP}pp Floor — übersprungen")
                continue
            fill_price = entry_ask   # ehrlicher Eintrittspreis = Ask (was wir zahlen)
            _re = f" · echte Edge {real_edge_pp:.1f}pp" if real_edge_pp is not None else ""
            print(f"    ✅ Spread-Gate ok: Ask {entry_ask:.3f} · Spread {entry_spread:.1f}pp{_re}")
        elif REQUIRE_BOOK_FOR_ENTRY:
            # Kein beidseitiges Buch (dünner Markt / Endpoint-Hänger) → NICHT blind zum Mid
            # einsteigen. Genau diese dünnen Märkte tragen den breitesten realen Spread.
            print(f"    🛑 Kein beidseitiges Orderbuch (dünner Markt) — übersprungen statt blind zum Mid")
            continue
        else:
            print(f"    ⚠️  Orderbuch nicht abrufbar — Eintritt zum Mid {poly_p:.3f} (Spread-Gate übersprungen)")

        # Schätze Anzahl der Tokens (Stake / Fill-Preis) — wird für Sell gebraucht
        shares_estimate = round(stake / fill_price, 4) if fill_price > 0 else 0.0

        # Order platzieren (price_hint = realer Ask wenn verfügbar, sonst Mid).
        # Mit Post-Only-/503-Retry: kurze Börsen-Sperren werden im selben Lauf abgefangen.
        result = place_order_with_retry(
            place_market_order, token_id, stake, private_key, fill_price,
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
                    stake=stake, poly_price=fill_price,
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
                "polyPrice":      fill_price,        # ehrlicher Eintritt = Ask (17.06.2026)
                "polyMid":        poly_p,            # Mid zum Vergleich/Audit
                "entryAsk":       entry_ask,         # echter Ask (None wenn Buch fehlte)
                "entrySpreadPP":  entry_spread,
                "pinnFair":       order.get("pinnFair"),
                "edgePP":         order["edgePP"],
                "stake":          stake,
                "orderId":        result.get("orderId"),
                "status":         result["status"],
                "placedAt":       datetime.now(timezone.utc).isoformat(),
                # ── Fields needed for auto-sell ──────────────────────
                "tokenId":        token_id,
                "matchDate":      order.get("matchDate", ""),
                "kickoff":        order.get("kickoff"),   # echte Anpfiffzeit (UTC) → 2h-Pre-Match-Close
                "sharesEstimate": shares_estimate,
                "isSteamLag":     is_steam,
                # FIX 14.06.2026: source explizit taggen (vorher fehlte es → Frontend/Resolve
                # mussten auf "default=auto" vertrauen). Betting-Seite filtert auf source.
                "source":         "auto_steam" if is_steam else "auto",
            })
        else:
            _err = str(result.get("error") or "")
            if "post_only" in _err or "post-only" in _err:
                # Börsenseitig + transient: Polymarkets CLOB nimmt gerade nur Maker-Orders
                # (Post-Only-Modus, retry_after_seconds). UNSERE Market-Order wird abgelehnt —
                # kein Bug, kein Phantom-Record. Nächster Cron-Lauf retryt automatisch.
                print(f"    ⏳ Polymarket im POST-ONLY-Modus (nimmt nur Maker-Orders) — "
                      f"vorübergehend, kein Trade. Retry beim nächsten Lauf.")
            elif "503" in _err or "retry_after" in _err:
                print(f"    ⏳ Börse vorübergehend nicht annahmebereit (503) — Retry nächster Lauf.")
            else:
                print(f"    ❌ Fehlgeschlagen: {_err}")

    # 5. Ergebnisse speichern
    if new_placed:
        placed_bets.extend(new_placed)
        placed_data["bets"] = placed_bets
        placed_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
        save_json(PLACED_FILE, placed_data)
        print(f"\n  💾 {len(new_placed)} neue Bet(s) in {PLACED_FILE} gespeichert")

        save_history(history)
        print(f"  💾 picks_history.json aktualisiert")

    # Buch-Fetch-Gesundheit wegschreiben (19.06.2026): der Trigger ist der zuverlässige
    # Buch-Prober (Spread-Gate je Kandidat). Guard check_book_fetch_healthy liest das und
    # schlägt Alarm, falls der CLOB-Endpoint/Netz tot ist (Versuche>0 aber 0 echte Bücher).
    try:
        from manage_wm_poly_positions import write_book_health, _BOOK_HEALTH
        write_book_health()
        if _BOOK_HEALTH["attempts"] > 0:
            print(f"  📕 Buch-Fetch: {_BOOK_HEALTH['ok']}/{_BOOK_HEALTH['attempts']} ok "
                  f"(Transport-Fehler {_BOOK_HEALTH['transport_fail']}, dünn {_BOOK_HEALTH['empty_or_crossed']})")
    except Exception as _bh:
        print(f"  ⚠️  Buch-Health-Write fehlgeschlagen: {_bh}")

    print(f"\n{'='*55}")
    print(f"  Fertig — {len(new_placed)} Bet(s) platziert")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
