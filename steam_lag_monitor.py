#!/usr/bin/env python3
"""
steam_lag_monitor.py — CocoBet Steam Lag Simulator / Trade Logger
===================================================================
Läuft alle 2 Stunden (Cowork Scheduled Task) und:
  1. Fetcht frische Polymarket-Preise (Gamma API, kein API-Key)
  2. Liest aktuelle Pinnacle Fair Probs aus wm_poly_prices.json
  3. Erkennt Steam Lag Signale + Edges ≥ 3pp
  4. Schreibt/aktualisiert steam_lag_log.json
  5. Trackt Konvergenz: schließt sich der Edge? Wann? Wie schnell?

Das Ziel der nächsten 7-10 Tage VOR der WM:
  → Verstehen ob/wann Polymarket nach Pinnacle-Move adjustiert
  → Datenbasierte Grundlage für echte Trades ab 11. Juni

Keine echten Bets — reine Datensimulation.
"""

import json
import os
import math
import re
import urllib.request
import urllib.error

# 01.07.2026 (Lucas: „Poly-Odds die's nie gab"): der GAMMA_URL-Fix (closed=false) holt jetzt auch
# Kind-/Spezialmärkte pro Spiel rein (…-first-to-score, …-second-half-result …), die als Moneyline
# gelabelt Phantom-Edge-Alerts erzeugten. Robuste Allowlist: Basis-Moneyline endet auf …-YYYY-MM-DD;
# Suffix nach dem Datum = Kind-Markt → raus. (Slugs ohne Datum bleiben unberührt → formatsicher.)
_DERIVED_SLUG_RE = re.compile(r"-\d{4}-\d{2}-\d{2}-")
from datetime import datetime, timezone, date
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE          = Path(__file__).parent
LOG_FILE      = BASE / "steam_lag_log.json"
POLY_FILE     = BASE / "wm_poly_prices.json"   # Written by GitHub Action (latest known state)
SELL_DEDUP_FILE = BASE / "steam_lag_sell_dedup.json"

# Telegram
# CHANNEL-FIX 05.06.2026: Steam-Lag-Signale (Pinnacle-vs-Polymarket-Edges)
# in privaten Trades-Channel verschoben — Edge-Alerts gehören zu Lucas'
# Trade-Pipeline, nicht zur öffentlichen Community.
TELEGRAM_TOKEN   = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_TRADES_CHAT_ID") or "").strip()

# ── Refactor 2026-06-06: Konstanten aus cocobet_config.json (Profile-aware) ──
try:
    from cocobet_config import CONFIG as _CFG
except Exception:
    _CFG = {}

def _cfg(section: str, key: str, default):
    """Sicherer Config-Lookup mit Default-Fallback (=aktueller Hardcode-Wert)."""
    if isinstance(_CFG, dict):
        return _CFG.get(section, {}).get(key, default)
    return default

# Sell-alert thresholds
SELL_VELOCITY_PP_H  = _cfg("steam", "sell_velocity_pp_h",  0.3)   # Edge closing ≥ 0.3pp/h → sell alert
SELL_EDGE_THRESHOLD = _cfg("steam", "sell_edge_threshold", 1.5)   # Only alert when edge already below this
SELL_MIN_ENTRY_EDGE = _cfg("steam", "sell_min_entry_edge", 2.5)   # Only alert for signals with meaningful entry edge

# High-confidence threshold
HIGH_CONF_EDGE_MIN  = _cfg("steam", "high_conf_edge_min", 3.0)    # Entry edge ≥ 3pp + steamLag → high confidence
POLY_HIST     = BASE / "wm2026-poly-history.json"
ODDS_HIST     = BASE / "wm2026-odds-history.json"

# Schwellenwerte
MIN_EDGE_PP            = _cfg("steam", "min_edge_pp",        1.5)  # Mindest-Edge für Log-Eintrag
SIGNAL_EDGE_PP         = _cfg("steam", "signal_edge_pp",     2.0)  # Mindest-Edge für echtes Signal
CONVERGED_EDGE_PP      = _cfg("steam", "converged_edge_pp",  1.0)  # Edge gilt als geschlossen wenn < 1pp
# Trackable: muss VOR Konvergenz-Schwelle starten, sonst keine echte Konvergenz möglich.
# Verhindert "Steam Lag mit 0.4pp Entry → sofort CONVERGED mit 0% closed"-Artefakte.
MIN_TRACKABLE_ENTRY    = CONVERGED_EDGE_PP + 1.0   # = 2.0pp absolute Untergrenze auch bei Steam Lag

# Edge-Tier-Klassifikation für Trading-Entscheidungen
# - "trade"   = Auto-Trigger-fähig (>= 5pp) → wird wirklich gewettet
# - "track"   = Beobachtungs-Signal (2-5pp) → wird geloggt aber nicht autotraded
# - "sub_threshold" = unter Tracking-Untergrenze → wird gar nicht erfasst
TRADE_TIER_EDGE_PP     = _cfg("steam", "trade_tier_edge_pp", 5.0)  # entspricht AUTO_TRIGGER_EDGE_PP

MAX_SNAPSHOTS     = _cfg("steam", "max_snapshots",   50)   # Snapshots pro Signal-Entry im Log
SIGNAL_TTL_DAYS   = _cfg("steam", "signal_ttl_days", 30)   # Alte aufgelöste Signale nach N Tagen bereinigen

# Bug-Fix 09.06.2026 — Daten-Lücke-Guard gegen Falsch-Konvergenz.
# Wenn zwischen vorherigem und aktuellem Snapshot > N Stunden liegen (z.B. nach
# Fetcher-Ausfall), darf ein gefallener Edge NICHT direkt als KONVERGIERT
# markiert werden — die Bewegung könnte ein Daten-Sprung sein, nicht echte
# Marktbewegung. Stattdessen: pendingConvergenceConfirm setzen, erst beim
# nächsten Stale-Pass (=2-4h) bestätigen.
SNAPSHOT_GAP_GUARD_HOURS = _cfg("steam", "snapshot_gap_guard_hours", 6.0)


def _classify_entry_tier(entry_edge: float, steam_lag: bool) -> str:
    """Tier-Klassifikation für ein Entry-Signal."""
    if entry_edge >= TRADE_TIER_EDGE_PP:
        return "trade"
    if entry_edge >= MIN_TRACKABLE_ENTRY:
        return "track"
    return "sub_threshold"

# Gamma API (kein API-Key, public)
# 01.07.2026 (Lucas): KO-Events fehlten — limit=100 ohne closed-Filter/Sortierung schnitt die neuesten
# (KO) ab, weil die Serie 100+ Events seit März hat. Siehe fetch_wm_poly_prices.GAMMA_URL. Fix:
# closed=false (nur offene Spiele) + newest-first + Headroom.
GAMMA_URL = (
    "https://gamma-api.polymarket.com/events"
    "?series_slug=soccer-fifwc&limit=300&active=true&closed=false"
    "&order=startDate&ascending=false"
)
SLUG_SUFFIXES_TO_SKIP = (
    "-exact-score", "-halftime-result", "-more-markets",
    "-exact-goals", "-both-teams-to-score",
)

# Polymarket Teamname → WM Team-ID (gleich wie in fetch_wm_poly_prices.py)
POLY_NAME_TO_ID = {
    "Germany":             "GER", "Curaçao":             "CUW",
    "Curacao":             "CUW", "Mexico":              "MEX",
    "South Africa":        "ZAF", "Korea Republic":      "KOR",
    "Czechia":             "CZE", "Czech Republic":      "CZE",
    "Canada":              "CAN", "Bosnia-Herzegovina":  "BIH",
    "Bosnia Herzegovina":  "BIH", "United States":       "USA",
    "USA":                 "USA", "Paraguay":            "PRY",
    "Qatar":               "QAT", "Switzerland":         "SUI",
    "Brazil":              "BRA", "Morocco":             "MAR",
    "Haiti":               "HTI", "Scotland":            "SCO",
    "Australia":           "AUS", "Türkiye":             "TUR",
    "Turkey":              "TUR", "Netherlands":         "NED",
    "Japan":               "JPN", "Côte d'Ivoire":       "CIV",
    "Cote d'Ivoire":       "CIV", "Ivory Coast":         "CIV",
    "Ecuador":             "ECU", "Sweden":              "SWE",
    "Tunisia":             "TUN", "Spain":               "ESP",
    "Cabo Verde":          "CPV", "Cape Verde":          "CPV",
    "Belgium":             "BEL", "Egypt":               "EGY",
    "Saudi Arabia":        "SAU", "Uruguay":             "URU",
    "Argentina":           "ARG", "France":              "FRA",
    "England":             "ENG", "Portugal":            "POR",
    "Algeria":             "DZA", "DR Congo":            "COD",
    "Democratic Republic of Congo": "COD",
    "Croatia":             "CRO", "Norway":              "NOR",
    "New Zealand":         "NZL", "Iran":                "IRN",
    "IR Iran":             "IRN", "Iraq":                "IRQ",
    "Jordan":              "JOR", "Ghana":               "GHA",
    "Senegal":             "SEN", "Colombia":            "COL",
    "Panama":              "PAN", "Uzbekistan":          "UZB",
    "Austria":             "AUT", "Indonesia":           "IDN",
}

MARKET_LABELS = {
    "hw": "Heimsieg", "dr": "Unentschieden", "aw": "Auswärtssieg",
    "o25": "Over 2.5", "u25": "Under 2.5", "btts": "BTTS",
}


# ── Gamma API Fetch ───────────────────────────────────────────────────────────
def fetch_gamma(url: str) -> list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "BetEdge/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️  Gamma fetch fehlgeschlagen: {e}")
        return []


def resolve_team(name: str) -> str | None:
    tid = POLY_NAME_TO_ID.get(name) or POLY_NAME_TO_ID.get(name.strip())
    if tid:
        return tid
    nl = name.lower()
    for k, v in POLY_NAME_TO_ID.items():
        if k.lower() in nl or nl in k.lower():
            return v
    return None


def fetch_fresh_poly() -> dict:
    """
    Fetcht aktuelle 1X2 Poly-Preise für alle WM-Spiele.
    Gibt dict zurück: {matchKey → {hw, dr, aw, slug, date, homeName, awayName}}
    """
    events = fetch_gamma(GAMMA_URL)
    result = {}
    for ev in events:
        slug = ev.get("slug", "")
        if _DERIVED_SLUG_RE.search(slug):
            continue   # Kind-/Spezialmarkt (Suffix nach dem Datum) — nie als Moneyline behandeln
        if any(slug.endswith(sfx) for sfx in SLUG_SUFFIXES_TO_SKIP):
            continue
        # negRisk=False = separate Binary-Markets (kein Neg-Risk-Pool).
        # Polymarket kann das je nach Marktstruktur wechseln — wir akzeptieren beide.
        # Einzige Ausnahme: explizit als "More Markets" oder Spezialmarkt gelabelt
        # → wird bereits durch SLUG_SUFFIXES_TO_SKIP gefiltert.

        teams_arr = ev.get("teams", [])
        if len(teams_arr) < 2:
            continue
        home_name = teams_arr[0].get("name", "")
        away_name = teams_arr[1].get("name", "")
        home_id   = resolve_team(home_name)
        away_id   = resolve_team(away_name)
        if not home_id or not away_id:
            continue

        hw = dr = aw = None
        for m in ev.get("markets", []):
            gt     = m.get("groupItemTitle", "")
            prices = json.loads(m.get("outcomePrices", "[]") or "[]")
            yes_p  = float(prices[0]) if prices else None
            if yes_p is None:
                continue
            gt_l = gt.lower()
            if "draw" in gt_l:
                dr = yes_p
            elif resolve_team(gt) == home_id:
                hw = yes_p
            elif resolve_team(gt) == away_id:
                aw = yes_p
            else:
                thr = str(m.get("groupItemThreshold", ""))
                if thr == "0": hw = yes_p
                elif thr == "1": dr = yes_p
                elif thr == "2": aw = yes_p

        if hw is None or aw is None:
            continue

        key = f"{home_id}-{away_id}"
        result[key] = {
            "hw": round(hw, 4),
            "dr": round(dr, 4) if dr else None,
            "aw": round(aw, 4),
            "slug":     slug,
            "date":     ev.get("eventDate", ""),
            "vol":      round(float(ev.get("volume", 0)), 0),
            "homeName": home_name,
            "awayName": away_name,
            "homeId":   home_id,
            "awayId":   away_id,
        }
    print(f"  🌐 Gamma API: {len(result)} WM-Fixtures geladen")
    return result


# ── Pinnacle Fair Probs aus wm_poly_prices.json ───────────────────────────────
def load_pinn_fair() -> dict:
    """
    Liest wm_poly_prices.json (vom letzten GitHub Action Run) und gibt
    pro matchKey die Pinnacle-devigged Fair Probs zurück.
    Auch: steamLag, pinnSteamMove, edgeTrend aus letztem Run.
    """
    if not POLY_FILE.exists():
        print("  ⚠️  wm_poly_prices.json nicht gefunden — kein Pinnacle-Kontext")
        return {}
    try:
        with open(POLY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for fx in data.get("allFixtures", []):
            key = fx.get("key", "")
            if not key:
                continue
            result[key] = {
                "fair_hw":      fx.get("fair_hw"),
                "fair_dr":      fx.get("fair_dr"),
                "fair_aw":      fx.get("fair_aw"),
                "fair_o25":     fx.get("fair_o25"),
                "fair_u25":     fx.get("fair_u25"),
                "steamLag":     fx.get("steamLag", False),
                "pinnSteamMove": fx.get("pinnSteamMove"),
                "edgeTrend":    fx.get("edgeTrend", "stable"),
                "hasPinnacle":  fx.get("hasPinnacle", False),
                "generatedAt":  data.get("generatedAt", ""),
            }
        print(f"  📁 Pinnacle-Daten geladen: {len(result)} Fixtures "
              f"(Stand: {data.get('generatedAt', '?')})")
        return result
    except Exception as e:
        print(f"  ⚠️  wm_poly_prices.json lesen fehlgeschlagen: {e}")
        return {}


# ── Team-Infos aus wm2026-data.json ──────────────────────────────────────────
def load_team_info() -> dict:
    """Gibt {teamId → {name, flag}} zurück."""
    wm_file = BASE / "wm2026-data.json"
    if not wm_file.exists():
        return {}
    try:
        with open(wm_file, encoding="utf-8") as f:
            wm = json.load(f)
        result = {}
        for gdata in wm.get("groups", {}).values():
            for t in gdata.get("teams", []):
                result[t["id"]] = {
                    "name": t.get("name", t["id"]),
                    "flag": t.get("flag", "🏳"),
                }
        return result
    except Exception:
        return {}


# ── Kickoff-Map: Live/beendete Spiele aus dem Steam-Lag fernhalten ───────────
def load_kickoffs() -> dict:
    """
    {matchKey → kickoff ISO (UTC)} aus wm_poly_prices.json (Polymarket Gamma
    startTime), Fallback wm2026-data.json. Steam-Lag ist ein PRE-MATCH-Edge
    (Pinnacle-Move den Polymarket noch nicht eingepreist hat) — sobald ein
    Spiel läuft, ist das kein handelbares Lag mehr, sondern In-Game-Bewegung.
    Bug 11.06.2026: MEX-ZAF (heute, 19:00 UTC angestoßen) blieb OFFEN, weil der
    alte Resolve-Pass nur `matchDate < today` prüfte — same-day-live fiel durch.
    """
    ko: dict = {}
    try:
        if POLY_FILE.exists():
            with open(POLY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for fx in data.get("allFixtures", []):
                k, kt = fx.get("key"), fx.get("kickoff")
                if k and kt:
                    ko[k] = kt
    except Exception as e:
        print(f"  ⚠️  load_kickoffs (poly) fehlgeschlagen: {e}")
    try:
        wm_file = BASE / "wm2026-data.json"
        if wm_file.exists():
            with open(wm_file, encoding="utf-8") as f:
                wm = json.load(f)
            for gdata in wm.get("groups", {}).values():
                for fx in gdata.get("fixtures", []):
                    k = f"{fx.get('home')}-{fx.get('away')}"
                    if k not in ko and fx.get("kickoff"):
                        ko[k] = fx["kickoff"]
    except Exception as e:
        print(f"  ⚠️  load_kickoffs (wm) fehlgeschlagen: {e}")
    return ko


def _kickoff_passed(kickoffs: dict, key: str, now_dt) -> bool:
    """
    True wenn der Anpfiff vorbei ist (Spiel läuft oder beendet). Fehlender/
    unparsebarer Kickoff → False (lieber als upcoming behandeln als ein echtes
    Pre-Match-Signal versehentlich verstecken).
    """
    kt = kickoffs.get(key)
    if not kt:
        return False
    try:
        return datetime.fromisoformat(str(kt).replace("Z", "+00:00")) <= now_dt
    except Exception:
        return False


# ── Cache-Fallback: Poly-Preise aus wm_poly_prices.json ──────────────────────
def fetch_poly_from_cache() -> dict:
    """
    Fallback wenn Gamma API nicht erreichbar (z.B. Proxy-Block im Sandbox).
    Liest wm_poly_prices.json (letzter GitHub Action Run) und gibt Poly-Preise
    im gleichen Format wie fetch_fresh_poly() zurück.
    Kein neues Fetch — nutzt den Stand des letzten GitHub Action Runs (3x/Tag).
    """
    if not POLY_FILE.exists():
        print("  ⚠️  Cache-Fallback: wm_poly_prices.json nicht gefunden")
        return {}
    try:
        with open(POLY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for fx in data.get("allFixtures", []):
            key = fx.get("key", "")
            if not key:
                continue
            # Brauchen Poly-Preise — fair_hw wird separat von load_pinn_fair() geladen.
            # fair_hw NICHT hier prüfen: wenn Pinnacle-Daten fehlen (API-Limit etc.),
            # würde der Cache leer zurückgeben → früher Abbruch → kein Commit.
            if not fx.get("poly_hw"):
                continue
            result[key] = {
                "hw":       fx.get("poly_hw"),
                "dr":       fx.get("poly_dr"),
                "aw":       fx.get("poly_aw"),
                "slug":     fx.get("slug", ""),
                "date":     fx.get("date", ""),
                "vol":      fx.get("vol", 0),
                "homeName": fx.get("homeName") or fx.get("home", ""),
                "awayName": fx.get("awayName") or fx.get("away", ""),
                "homeId":   fx.get("homeId", ""),
                "awayId":   fx.get("awayId", ""),
            }
        age = data.get("generatedAt", "?")
        print(f"  📦 Cache-Fallback: {len(result)} Fixtures geladen (Stand: {age})")
        return result
    except Exception as e:
        print(f"  ⚠️  Cache-Fallback fehlgeschlagen: {e}")
        return {}


# ── Telegram ─────────────────────────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ℹ️  Kein TELEGRAM_TOKEN/CHAT_ID — Vorschau:")
        print(f"  {text[:200]}")
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"  ⚠️  Telegram fehlgeschlagen: {e}")
        return False


# ── Sell-Alert Dedup ──────────────────────────────────────────────────────────
def load_sell_dedup() -> dict:
    try:
        if SELL_DEDUP_FILE.exists():
            with open(SELL_DEDUP_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_sell_dedup(store: dict) -> None:
    with open(SELL_DEDUP_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


# ── Edge-Berechnung ───────────────────────────────────────────────────────────
def compute_edges(poly: dict, pinn: dict) -> list[dict]:
    """
    Vergleicht frische Poly-Preise mit Pinnacle Fair Probs.
    Gibt Liste von Fixtures zurück mit allen Edge-Feldern.
    """
    signals = []
    for key, p in poly.items():
        pf = pinn.get(key, {})
        if not pf.get("hasPinnacle") and not pf.get("fair_hw"):
            continue

        fair_hw = pf.get("fair_hw")
        fair_dr = pf.get("fair_dr")
        fair_aw = pf.get("fair_aw")

        edges = {}
        if fair_hw and p.get("hw"):
            edges["hw"] = round((fair_hw - p["hw"]) * 100, 1)
        if fair_dr and p.get("dr"):
            edges["dr"] = round((fair_dr - p["dr"]) * 100, 1)
        if fair_aw and p.get("aw"):
            edges["aw"] = round((fair_aw - p["aw"]) * 100, 1)

        pos_edges = {k: v for k, v in edges.items() if v is not None and v > 0}
        best_key  = max(pos_edges, key=pos_edges.get) if pos_edges else None
        best_edge = pos_edges.get(best_key, 0) if best_key else 0

        signals.append({
            "key":          key,
            "homeId":       p["homeId"],
            "awayId":       p["awayId"],
            "homeName":     p["homeName"],
            "awayName":     p["awayName"],
            "matchDate":    p["date"][:10] if p.get("date") else "",
            "slug":         p.get("slug", ""),
            "poly_hw":      p.get("hw"),
            "poly_dr":      p.get("dr"),
            "poly_aw":      p.get("aw"),
            "fair_hw":      fair_hw,
            "fair_dr":      fair_dr,
            "fair_aw":      fair_aw,
            "edge_hw":      edges.get("hw"),
            "edge_dr":      edges.get("dr"),
            "edge_aw":      edges.get("aw"),
            "bestEdge":     best_edge,
            "bestEdgeKey":  best_key,
            "steamLag":     pf.get("steamLag", False),
            "pinnSteamMove": pf.get("pinnSteamMove"),
            "edgeTrend":    pf.get("edgeTrend", "stable"),
        })
    return signals


# ── Signal-ID generieren ──────────────────────────────────────────────────────
def make_signal_id(key: str, market: str, ts: str | None = None) -> str:
    # 23.06.2026 (Lucas: „jede Wette mit 1 Position"): ID STABIL pro (Match, Markt) — NICHT mehr
    # tages-getaggt. Vorher gab das tages-Tag derselben Wette bei Re-Detektion an einem neuen Tag
    # eine neue ID → Duplikat-Positionen (JOR-DZA hw 6×). Anderer Markt im selben Spiel = eigene ID.
    return f"{key}_{market}"


# ── Log laden/speichern ───────────────────────────────────────────────────────
def load_log() -> dict:
    if not LOG_FILE.exists():
        return {"signals": [], "updatedAt": "", "runCount": 0}
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"signals": [], "updatedAt": "", "runCount": 0}


def save_log(log: dict) -> None:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── Konvergenz berechnen ──────────────────────────────────────────────────────
def calc_convergence(entry_edge: float, current_edge: float) -> float:
    """Wie viel % der ursprünglichen Lücke ist geschlossen?"""
    if entry_edge <= 0:
        return 0.0
    closed = entry_edge - max(current_edge, 0)
    return round(min(100.0, max(0.0, closed / entry_edge * 100)), 1)


# ── Hauptlogik: Log aktualisieren ────────────────────────────────────────────
def _snapshot_gap_hours(snaps: list, now_dt) -> float | None:
    """
    Bug-Fix 09.06.2026 — Gap zwischen vorletztem und aktuell-angehängtem
    Snapshot in Stunden. Der zuletzt-angehängte Snapshot ist snaps[-1]
    (gerade neu hinzugefügt); vorletzter ist snaps[-2]. Returns None wenn
    nicht genug Snapshots oder Parsing fehlschlägt.
    """
    if not snaps or len(snaps) < 2:
        return None
    try:
        prev_ts = snaps[-2].get("ts")
        if not prev_ts:
            return None
        prev_dt = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
        return (now_dt - prev_dt).total_seconds() / 3600
    except Exception:
        return None


def update_log(log: dict, signals: list[dict], team_info: dict, now_ts: str,
               kickoffs: dict | None = None) -> dict:
    """
    1. Für jedes Signal mit edge >= MIN_EDGE_PP: prüfe ob bereits im Log
       - Neu → neuen Entry anlegen
       - Vorhanden → Snapshot anhängen, Konvergenz prüfen
    2. Für Entries im Log die nicht mehr in den Signalen → als aufgelöst markieren
    """
    existing = {e["id"]: e for e in log.get("signals", [])}
    now_dt   = datetime.fromisoformat(now_ts.replace("Z", "+00:00"))
    kickoffs = kickoffs or {}

    # Tracke (matchKey, market) Paare, die tatsächlich einen Snapshot im Main-Loop
    # bekommen haben. Wird unten im Stale-Pass benutzt, um Doppel-Updates zu
    # vermeiden — OHNE Signale zu überspringen, die nur via compute_signals()
    # zurückgegeben wurden aber dann durch den MIN_EDGE_PP-Filter rausgeflogen sind.
    # Bug-Fix 07.06.2026: Vorher war signal_keys_market aus der UNGEFILTERTEN
    # signals-Liste gebaut → Matches mit Edge < MIN_EDGE_PP fielen in einen
    # toten Winkel (Main-Loop skippt, Stale-Pass denkt Main-Loop hat updated).
    snapshotted_in_main: set = set()

    for fx in signals:
        # Live/beendet → kein Pre-Match-Steam-Lag mehr: weder neuen Eintrag anlegen
        # noch ein offenes Signal weiter snapshotten. (Schließen passiert im
        # Resolve-Pass unten.)
        if _kickoff_passed(kickoffs, fx["key"], now_dt):
            continue
        if (fx["bestEdge"] or 0) < MIN_EDGE_PP and not fx["steamLag"]:
            continue

        best_key = fx["bestEdgeKey"]
        if not best_key:
            continue

        # EINE Position pro (Match, Markt): bestehenden Eintrag finden, egal welcher Status
        # (außer RESOLVED — abgepfiffenes Spiel, kein Re-Open). Vorher nur status=="OPEN" → nach
        # Konvergenz wurde bei Re-Detektion ein DUPLIKAT angelegt (Lucas 23.06.).
        open_entry = None
        for e in log.get("signals", []):
            if (e["matchKey"] == fx["key"]
                    and e["market"] == best_key
                    and e["status"] != "RESOLVED"):
                open_entry = e
                break

        current_edge = fx["bestEdge"] or 0
        current_poly = fx.get(f"poly_{best_key}")
        current_fair = fx.get(f"fair_{best_key}")

        snap = {
            "ts":        now_ts,
            "edgePp":    current_edge,
            "polyPrice": current_poly,
            "pinnFair":  current_fair,
            "steamLag":  fx["steamLag"],
        }

        if open_entry is None:
            # ── Neues Signal ──────────────────────────────────────────────
            if current_edge < SIGNAL_EDGE_PP and not fx["steamLag"]:
                continue   # Zu klein für echten Log-Eintrag

            # Tracking-Untergrenze: auch bei Steam Lag muss ein Signal über
            # CONVERGED_EDGE_PP starten, sonst keine echte Konvergenz möglich.
            # Verhindert das "0% closed → CONVERGED"-Artefakt im Dashboard.
            if current_edge < MIN_TRACKABLE_ENTRY:
                if fx["steamLag"]:
                    print(f"  ⏭️  Steam Lag aber Entry {current_edge:.1f}pp < {MIN_TRACKABLE_ENTRY}pp "
                          f"→ nicht trackbar (kein Konvergenz-Raum)")
                continue

            home_info = team_info.get(fx["homeId"], {})
            away_info = team_info.get(fx["awayId"], {})
            entry_tier = _classify_entry_tier(current_edge, fx["steamLag"])
            is_high_conf = (
                fx["steamLag"] and
                current_edge >= HIGH_CONF_EDGE_MIN
            )
            new_entry = {
                "id":               make_signal_id(fx["key"], best_key, now_ts),
                "matchKey":         fx["key"],
                "homeId":           fx["homeId"],
                "awayId":           fx["awayId"],
                "home":             home_info.get("name", fx["homeName"]),
                "away":             away_info.get("name", fx["awayName"]),
                "homeFlag":         home_info.get("flag", "🏳"),
                "awayFlag":         away_info.get("flag", "🏳"),
                "matchDate":        fx["matchDate"],
                "market":           best_key,
                "marketLabel":      MARKET_LABELS.get(best_key, best_key),
                "signalTs":         now_ts,
                "entryEdgePp":      current_edge,
                "entryPolyPrice":   current_poly,
                "entryPinnFair":    current_fair,
                "entryVol":         fx.get("vol", 0),
                "steamLagAtSignal": fx["steamLag"],
                "pinnMoveAtSignal": fx.get("pinnSteamMove"),
                "edgeTrendAtSignal":fx.get("edgeTrend", "stable"),
                "highConfidence":   is_high_conf,
                "entryTier":        entry_tier,   # "trade" / "track" / "sub_threshold"
                "snapshots":        [snap],
                "currentEdgePp":    current_edge,
                "currentPolyPrice": current_poly,
                "edgeVelocityPPH":  None,
                "convergencePct":   0.0,
                "convergenceTs":    None,
                "convergenceHours": None,
                "status":           "OPEN",
                "outcome":          None,
            }
            log.setdefault("signals", []).append(new_entry)
            snapshotted_in_main.add((fx["key"], best_key))
            flag = "🔥" if fx["steamLag"] else "🆕"
            print(f"  {flag} NEU: {new_entry['home']} vs {new_entry['away']}"
                  f" · {new_entry['marketLabel']} · +{current_edge:.1f}pp")

        else:
            # ── Existierendes offenes Signal updaten ─────────────────────
            snaps = open_entry.setdefault("snapshots", [])
            snaps.append(snap)
            snapshotted_in_main.add((fx["key"], best_key))
            if len(snaps) > MAX_SNAPSHOTS:
                snaps[:] = snaps[-MAX_SNAPSHOTS:]

            open_entry["currentEdgePp"]    = current_edge
            open_entry["currentPolyPrice"] = current_poly
            open_entry["convergencePct"]   = calc_convergence(
                open_entry["entryEdgePp"], current_edge)

            # ── Edge velocity: pp/h over last 2+ snapshots ───────────────────
            snaps_for_vel = open_entry.get("snapshots", [])
            if len(snaps_for_vel) >= 2:
                snap_old = snaps_for_vel[-2]
                try:
                    t_old = datetime.fromisoformat(snap_old["ts"].replace("Z", "+00:00"))
                    t_new = datetime.fromisoformat(now_ts.replace("Z", "+00:00"))
                    hours_diff = max(0.1, (t_new - t_old).total_seconds() / 3600)
                    vel = round((current_edge - (snap_old.get("edgePp") or current_edge)) / hours_diff, 3)
                    open_entry["edgeVelocityPPH"] = vel   # negative = closing
                except Exception:
                    pass

            # Konvergenz erreicht?
            if (current_edge < CONVERGED_EDGE_PP
                    and open_entry["status"] == "OPEN"
                    and not open_entry.get("convergenceTs")):
                # Bug-Fix 09.06.2026 — Daten-Lücke-Guard.
                # Wenn vorletzter Snapshot zu alt → kein Auto-CONVERGED.
                gap_h = _snapshot_gap_hours(snaps, now_dt)
                if gap_h is not None and gap_h > SNAPSHOT_GAP_GUARD_HOURS:
                    if open_entry.get("pendingConvergenceConfirm"):
                        # Bestätigung beim 2. Run nach Lücke → echt konvergiert
                        sig_dt = datetime.fromisoformat(
                            open_entry["signalTs"].replace("Z", "+00:00"))
                        hours = round((now_dt - sig_dt).total_seconds() / 3600, 1)
                        open_entry["convergenceTs"]    = now_ts
                        open_entry["convergenceHours"] = hours
                        open_entry["status"]           = "CONVERGED"
                        open_entry.pop("pendingConvergenceConfirm", None)
                        print(f"  ✅ KONVERGIERT (nach Daten-Lücke-Bestätigung) nach {hours}h: "
                              f"{open_entry['home']} vs {open_entry['away']}"
                              f" · {open_entry['marketLabel']}")
                    else:
                        open_entry["pendingConvergenceConfirm"] = True
                        print(f"  ⏳ Daten-Lücke {gap_h:.1f}h → Konvergenz nicht bestätigt: "
                              f"{open_entry['home']} vs {open_entry['away']}"
                              f" · {open_entry['marketLabel']} ({current_edge:+.1f}pp)")
                else:
                    sig_dt = datetime.fromisoformat(
                        open_entry["signalTs"].replace("Z", "+00:00"))
                    hours = round((now_dt - sig_dt).total_seconds() / 3600, 1)
                    open_entry["convergenceTs"]    = now_ts
                    open_entry["convergenceHours"] = hours
                    open_entry["status"]           = "CONVERGED"
                    open_entry.pop("pendingConvergenceConfirm", None)
                    print(f"  ✅ KONVERGIERT nach {hours}h: "
                          f"{open_entry['home']} vs {open_entry['away']}"
                          f" · {open_entry['marketLabel']}")
            else:
                print(f"  📊 UPDATE: {open_entry['home']} vs {open_entry['away']}"
                      f" · {open_entry['marketLabel']}"
                      f" · {open_entry['entryEdgePp']:+.1f}pp → {current_edge:+.1f}pp"
                      f" · {open_entry['convergencePct']:.0f}% geschlossen")

    # ── Stale-Snapshot-Pass für OPEN-Signale die NICHT im Main-Loop landen ──
    # Bug-Fix 05.06.2026: Wenn ein Match seinen Edge unter MIN_EDGE_PP verliert,
    # wird es in find_signals() gefiltert und das OPEN-Signal bleibt forever auf
    # altem currentEdgePp hängen. Dashboard zeigt dann veraltete Werte als aktuell.
    # → Wir hängen einen frischen Snapshot mit dem aktuellen (niedrigeren) Edge an
    #   und markieren bei Edge < CONVERGED_EDGE_PP als CONVERGED.
    #
    # Bug-Fix 07.06.2026: Vorher wurde signal_keys_market aus der ungefilterten
    # `signals`-Liste gebaut. Das umfasst auch Matches, deren bestEdge < MIN_EDGE_PP
    # ist — die im Main-Loop wegen des early-continue NIE einen Snapshot kriegen.
    # Beispiel: MEX-ZAF aw mit bestEdge=0.9 → im signal_keys_market drin, aber im
    # Main-Loop ge-continued → Stale-Pass skipte fälschlich → 64h kein Update.
    # Fix: snapshotted_in_main wird oben ausschließlich befüllt, wenn ein Snapshot
    # auch wirklich angehängt wurde.
    # Lade alle aktuellen Fixtures aus wm_poly_prices.json für Stale-Check
    fx_lookup: dict = {}
    try:
        if POLY_FILE.exists():
            with open(POLY_FILE, encoding="utf-8") as _f:
                _poly_data = json.load(_f)
            for _fx in _poly_data.get("allFixtures", []):
                _k = _fx.get("key")
                if _k:
                    fx_lookup[_k] = _fx
    except Exception as _e:
        print(f"  ⚠️  Stale-Pass: poly_lookup laden fehlgeschlagen: {_e}")
    stale_updated = 0
    stale_converged = 0
    for entry in log.get("signals", []):
        if entry["status"] != "OPEN":
            continue
        # Live/beendet → nicht weiter snapshotten (wird im Resolve-Pass geschlossen)
        if _kickoff_passed(kickoffs, entry["matchKey"], now_dt):
            continue
        mk_key = entry["matchKey"]
        market_key = entry["market"]
        if (mk_key, market_key) in snapshotted_in_main:
            continue   # bereits durch reguläre Loop aktualisiert
        # Such aktuellen Stand für diesen Markt
        fx_now = fx_lookup.get(mk_key)
        if not fx_now:
            continue
        cur_edge = fx_now.get(f"edge_{market_key}")
        cur_poly = fx_now.get(f"poly_{market_key}")
        cur_fair = fx_now.get(f"fair_{market_key}")
        if cur_edge is None:
            continue
        # Snapshot anhängen
        snaps = entry.setdefault("snapshots", [])
        snaps.append({
            "ts": now_ts,
            "edgePp": cur_edge,
            "polyPrice": cur_poly,
            "pinnFair": cur_fair,
            "steamLag": fx_now.get("steamLag", False),
        })
        if len(snaps) > MAX_SNAPSHOTS:
            snaps[:] = snaps[-MAX_SNAPSHOTS:]
        entry["currentEdgePp"]    = cur_edge
        entry["currentPolyPrice"] = cur_poly
        entry["convergencePct"]   = calc_convergence(entry["entryEdgePp"], cur_edge)
        stale_updated += 1

        # Bei Edge < CONVERGED_EDGE_PP als KONVERGIERT markieren
        # Bug-Fix 09.06.2026 — Daten-Lücke-Guard (siehe Konstante SNAPSHOT_GAP_GUARD_HOURS).
        # Vorletzter Snapshot ist snaps[-2] (vor dem eben angehängten).
        if cur_edge < CONVERGED_EDGE_PP and not entry.get("convergenceTs"):
            gap_h = _snapshot_gap_hours(snaps, now_dt)
            if gap_h is not None and gap_h > SNAPSHOT_GAP_GUARD_HOURS:
                if entry.get("pendingConvergenceConfirm"):
                    sig_dt = datetime.fromisoformat(entry["signalTs"].replace("Z", "+00:00"))
                    hours = round((now_dt - sig_dt).total_seconds() / 3600, 1)
                    entry["convergenceTs"]    = now_ts
                    entry["convergenceHours"] = hours
                    entry["status"]           = "CONVERGED"
                    entry.pop("pendingConvergenceConfirm", None)
                    stale_converged += 1
                    print(f"  ✅ KONVERGIERT (stale-pass, bestätigt nach Lücke) nach {hours}h: "
                          f"{entry['home']} vs {entry['away']} · {entry['marketLabel']}")
                else:
                    entry["pendingConvergenceConfirm"] = True
                    print(f"  ⏳ Stale-Pass Daten-Lücke {gap_h:.1f}h → Konvergenz nicht bestätigt: "
                          f"{entry['home']} vs {entry['away']}"
                          f" · {entry['marketLabel']} ({cur_edge:+.1f}pp)")
                continue
            sig_dt = datetime.fromisoformat(entry["signalTs"].replace("Z", "+00:00"))
            hours = round((now_dt - sig_dt).total_seconds() / 3600, 1)
            entry["convergenceTs"]    = now_ts
            entry["convergenceHours"] = hours
            entry["status"]           = "CONVERGED"
            entry.pop("pendingConvergenceConfirm", None)
            stale_converged += 1
            print(f"  ✅ KONVERGIERT (stale-pass) nach {hours}h: "
                  f"{entry['home']} vs {entry['away']} · {entry['marketLabel']} "
                  f"· {entry['entryEdgePp']:+.1f}pp → {cur_edge:+.1f}pp")

    if stale_updated:
        print(f"  🔄 Stale-Pass: {stale_updated} Signale aktualisiert "
              f"({stale_converged} als KONVERGIERT markiert)")

    # ── Aufgelöste Spiele markieren (Spieldatum vorbei) ───────────────────────
    today = date.today()
    current_keys = {fx["key"] for fx in signals}

    for entry in log.get("signals", []):
        # 23.06.2026: auch hängende non-OPEN-Stati (Legacy PRE_CONVERGED) nach Anpfiff schließen —
        # CONVERGED bleibt CONVERGED (erfolgreiche Konvergenz), RESOLVED ist schon zu.
        if entry["status"] in ("RESOLVED", "CONVERGED"):
            continue
        # Kickoff vorbei (auch same-day-live) → Pre-Match-Edge nicht mehr handelbar.
        # Schließen statt OFFEN lassen, sonst stehen laufende Spiele im aktiven Steam-Lag.
        if _kickoff_passed(kickoffs, entry["matchKey"], now_dt):
            entry["status"]       = "RESOLVED"
            entry["resolvedAt"]   = now_ts
            entry["resolveReason"] = "kickoff_passed"
            print(f"  ⏱️  GESCHLOSSEN (Anpfiff vorbei): {entry['home']} vs {entry['away']}"
                  f" · {entry['marketLabel']}")
            continue
        match_date_str = entry.get("matchDate", "")
        if match_date_str:
            try:
                match_dt = date.fromisoformat(match_date_str)
                if match_dt < today and entry["matchKey"] not in current_keys:
                    entry["status"] = "RESOLVED"
                    entry["resolvedAt"] = now_ts
                    print(f"  ⚽ AUFGELÖST: {entry['home']} vs {entry['away']}"
                          f" · {entry['marketLabel']}")
            except ValueError:
                pass

    # ── Alte aufgelöste Signale bereinigen (> SIGNAL_TTL_DAYS) ───────────────
    cutoff_dt = datetime.now(timezone.utc).timestamp() - SIGNAL_TTL_DAYS * 86400
    before = len(log.get("signals", []))
    log["signals"] = [
        e for e in log.get("signals", [])
        if not (e["status"] in ("RESOLVED", "CONVERGED")
                and _parse_ts(e.get("signalTs", "")) is not None
                and _parse_ts(e["signalTs"]).timestamp() < cutoff_dt)
    ]
    cleaned = before - len(log["signals"])
    if cleaned:
        print(f"  🧹 {cleaned} alte Einträge bereinigt")

    log["updatedAt"] = now_ts
    log["runCount"]  = log.get("runCount", 0) + 1
    return log


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Summary ausgeben ──────────────────────────────────────────────────────────
def print_summary(log: dict) -> None:
    signals = log.get("signals", [])
    n_open      = sum(1 for s in signals if s["status"] == "OPEN")
    n_conv      = sum(1 for s in signals if s["status"] == "CONVERGED")
    n_resolved  = sum(1 for s in signals if s["status"] == "RESOLVED")
    n_steam     = sum(1 for s in signals if s.get("steamLagAtSignal"))
    conv_times  = [s["convergenceHours"] for s in signals
                   if s["status"] == "CONVERGED" and s.get("convergenceHours")]

    avg_conv = round(sum(conv_times) / len(conv_times), 1) if conv_times else None
    conv_rate = round(n_conv / max(1, n_conv + n_open) * 100) if (n_conv + n_open) > 0 else 0

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║  🔥 Steam Lag Monitor — Zusammenfassung          ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  Signale gesamt:    {len(signals):<30}║")
    print(f"║  🟡 OFFEN:          {n_open:<30}║")
    print(f"║  ✅ KONVERGIERT:    {n_conv:<30}║")
    print(f"║  ⚫ AUFGELÖST:      {n_resolved:<30}║")
    print(f"║  🔥 Steam Lag:      {n_steam:<30}║")
    print(f"║  Konvergenzrate:    {conv_rate}%{'':<28}║")
    if avg_conv:
        print(f"║  Ø Konvergenzzeit: {avg_conv}h{'':<28}║")
    print("╚══════════════════════════════════════════════════╝")

    if n_open > 0:
        print("\n🟡 Offene Signale:")
        for s in signals:
            if s["status"] != "OPEN":
                continue
            steam_tag = " 🔥" if s.get("steamLagAtSignal") else ""
            delta = s["currentEdgePp"] - s["entryEdgePp"]
            delta_str = f"+{delta:.1f}pp" if delta >= 0 else f"{delta:.1f}pp"
            print(f"   {s['homeFlag']} {s['home']} vs {s['away']} {s['awayFlag']}"
                  f" · {s['marketLabel']}"
                  f" · Entry: +{s['entryEdgePp']:.1f}pp → Now: +{s['currentEdgePp']:.1f}pp"
                  f" ({delta_str}){steam_tag}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== steam_lag_monitor.py ===")
    print(f"    {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}")
    print()

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Frische Poly-Preise holen (Gamma API → Fallback: wm_poly_prices.json)
    print("📡 Fetche Polymarket-Preise…")
    fresh_poly = fetch_fresh_poly()
    if not fresh_poly:
        print("  🔄 Fallback: verwende Poly-Preise aus wm_poly_prices.json …")
        fresh_poly = fetch_poly_from_cache()
    if not fresh_poly:
        # Kein frühes Abbrechen — Log trotzdem speichern (runCount + updatedAt müssen sich
        # ändern damit der GitHub Action Commit immer etwas zu committen hat).
        print("  ⚠️  Keine Poly-Preise — speichere leeren Log-Update (Heartbeat)")
        log = load_log()
        log["updatedAt"] = now_ts
        log["runCount"]  = log.get("runCount", 0) + 1
        log["lastError"] = "no_poly_prices"
        save_log(log)
        return

    # 2. Pinnacle Fair Probs + Steam Lag Kontext laden
    print("📁 Lade Pinnacle-Kontext…")
    pinn_fair = load_pinn_fair()

    # 3. Team-Infos + Kickoff-Map (Live/beendete Spiele aus Steam-Lag fernhalten)
    team_info = load_team_info()
    kickoffs  = load_kickoffs()

    # 4. Edges berechnen
    print("⚡ Berechne Edges…")
    signals = compute_edges(fresh_poly, pinn_fair)
    n_edge  = sum(1 for s in signals if (s["bestEdge"] or 0) >= SIGNAL_EDGE_PP)
    n_steam = sum(1 for s in signals if s["steamLag"])
    print(f"  Fixtures analysiert: {len(signals)}"
          f" | Edge≥{SIGNAL_EDGE_PP}pp: {n_edge}"
          f" | 🔥 Steam Lag: {n_steam}")

    # 5. Log laden und aktualisieren
    print("\n📝 Aktualisiere Log…")
    log = load_log()
    log = update_log(log, signals, team_info, now_ts, kickoffs)

    # 6. Speichern
    save_log(log)
    print(f"\n✅ steam_lag_log.json gespeichert ({len(log.get('signals', []))} Einträge)")

    # 7. Summary
    print_summary(log)

    # 8. Telegram Alerts ──────────────────────────────────────────────────────
    print("\n📱 Prüfe Telegram Alerts…")
    sell_dedup = load_sell_dedup()
    signals    = log.get("signals", [])
    alerts_sent = 0
    now_dt_alert = datetime.fromisoformat(now_ts.replace("Z", "+00:00"))

    for sig in signals:
        # Keine Alerts für laufende/beendete Spiele (kein Pre-Match-Edge mehr)
        if _kickoff_passed(kickoffs, sig.get("matchKey", ""), now_dt_alert):
            continue
        home  = sig.get("home", sig.get("homeId", "?"))
        away  = sig.get("away", sig.get("awayId", "?"))
        hf    = sig.get("homeFlag", "")
        af    = sig.get("awayFlag", "")
        mkt   = sig.get("marketLabel", sig.get("market", ""))
        entry = sig.get("entryEdgePp", 0)
        curr  = sig.get("currentEdgePp", 0)
        vel   = sig.get("edgeVelocityPPH")
        sig_id = sig.get("id", "")

        # ── Neu: High-Confidence Signal-Alert ────────────────────────────────
        hc_key = f"hc::{sig_id}"
        if (sig.get("highConfidence")
                and sig.get("status") == "OPEN"
                and hc_key not in sell_dedup):
            steam_pp = sig.get("pinnMoveAtSignal", 0) or 0
            vol_str  = f"${sig.get('entryVol', 0):,.0f}" if sig.get("entryVol") else "?"
            msg = (
                f"⭐ <b>HIGH CONFIDENCE Steam Lag</b>\n"
                f"{hf} <b>{home}</b> vs {af} <b>{away}</b>\n"
                f"Markt: <b>{mkt}</b>\n"
                f"\n"
                f"🔥 Pinn-Move: <b>+{steam_pp:.1f}pp</b> (Pinnacle hat sich bewegt)\n"
                f"💹 Poly-Edge: <b>+{entry:.1f}pp</b> (Poly noch nicht reagiert)\n"
                f"Vol: {vol_str}\n"
                f"\n"
                f"✅ Beide Bedingungen erfüllt: Pinn-Move + Poly-Lag\n"
                f"📅 Spiel: {sig.get('matchDate', '?')}\n"
                f"\n🤖 CocoBet Steam Lag Monitor"
            )
            ok = tg_send(msg)
            if ok:
                sell_dedup[hc_key] = {"ts": now_ts, "type": "high_conf"}
                alerts_sent += 1
                print(f"  ⭐ HIGH CONF Alert: {home} vs {away} · {mkt}")

        # ── Sell Alert: Edge schließt sich schnell ────────────────────────────
        sell_key = f"sell::{sig_id}"
        if (sig.get("status") == "OPEN"
                and entry >= SELL_MIN_ENTRY_EDGE
                and curr <= SELL_EDGE_THRESHOLD
                and vel is not None
                and vel <= -SELL_VELOCITY_PP_H
                and sell_key not in sell_dedup):
            captured = round(100 * (entry - curr) / entry) if entry > 0 else 0
            msg = (
                f"📉 <b>EXIT SIGNAL — Edge konvergiert!</b>\n"
                f"{hf} <b>{home}</b> vs {af} <b>{away}</b>\n"
                f"Markt: <b>{mkt}</b>\n"
                f"\n"
                f"Entry: <b>+{entry:.1f}pp</b> → Jetzt: <b>+{curr:.1f}pp</b>\n"
                f"⚡ Velocity: <b>{vel:+.2f}pp/h</b> (schließt sich)\n"
                f"✅ {captured}% der Lücke geschlossen\n"
                f"\n"
                f"💡 Erwäge Position zu verkaufen — Konvergenz läuft\n"
                f"📅 Spiel: {sig.get('matchDate', '?')}\n"
                f"\n🤖 CocoBet Steam Lag Monitor"
            )
            ok = tg_send(msg)
            if ok:
                sell_dedup[sell_key] = {"ts": now_ts, "type": "sell", "vel": vel, "curr": curr}
                alerts_sent += 1
                print(f"  📉 SELL Alert: {home} vs {away} · {mkt} · {vel:+.2f}pp/h")

    save_sell_dedup(sell_dedup)
    if alerts_sent:
        print(f"  ✅ {alerts_sent} Alert(s) gesendet")
    else:
        print(f"  ℹ️  Keine neuen Alerts (alle bereits gesendet oder Schwellen nicht erreicht)")


if __name__ == "__main__":
    main()
