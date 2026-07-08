#!/usr/bin/env python3
"""
fetch_wm_odds.py — WM 2026 Odds fetcher via TheOddsAPI.

Fetches h2h (1X2) odds for all WM 2026 group stage fixtures and writes
them to wm2026-data.json under the "odds" key.

Odds key format: "{homeId}-{awayId}"  e.g. "MEX-ZAF"
Odds structure:
  {
    "hw": 1.85,        # home win
    "dr": 3.50,        # draw
    "aw": 4.75,        # away win
    "odds_open": {...} # first-ever snapshot (set once, never overwritten)
    "odds_closing": {} # set at kick-off, preserved
    "updatedAt": "ISO"
  }

Run:   python3 fetch_wm_odds.py
Cron:  Daily from June 1 via fetch-wm-data.yml
"""

import json
import os
import sys
import time
import http.client
import ssl
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path(__file__).parent
WM_FILE      = BASE / "wm2026-data.json"
# Phase 3 (16.06.2026): persistente, minutengenaue Closing-Linien in EIGENER Datei.
# Grund: der Manage-Workflow holt alle 15min frische Odds (→ Closing konvergiert an den
# Anpfiff), committet aber wm2026-data.json NICHT (Race-Vermeidung). Diese kleine Datei
# committet er → die nahe-Anpfiff-Closing überlebt. resolve_wm_results bevorzugt sie.
CLOSING_LINES_FILE = BASE / "wm_closing_lines.json"
HISTORY_FILE = BASE / "wm2026-odds-history.json"

# Config-aware Markt-Skip: wenn alle Corner-Markets im aktiven Profil disabled
# sind, skippen wir Call 3 komplett (API-Quota sparen).
# FIX 11.06.2026: cocobet_config.CONFIG = aufgelöstes Profil OHNE Extra-Sections
# wie disabled_markets (die fallen bei _resolve_active_profile weg). CONFIG.get(
# "disabled_markets") war IMMER None → _SKIP_CORNERS IMMER False → 72 Corner-
# Requests pro Lauf trotz deaktivierter Corners → TheOddsAPI-Quota gesprengt →
# Odds eingefroren. Jetzt roh aus der JSON gelesen (wie generate_wm_picks).
def _corners_disabled() -> bool:
    try:
        import os as _os, json as _json
        from pathlib import Path as _Path
        raw = _json.loads((_Path(__file__).parent / "cocobet_config.json")
                          .read_text(encoding="utf-8"))
        active = _os.environ.get("COCOBET_PROFILE") or raw.get("profiles", {}).get("active", "wm2026")
        disabled = set(raw.get("profiles", {}).get(active, {}).get("disabled_markets") or [])
        corner_keys = {"o_corners85", "o_corners95", "o_corners105"}
        return corner_keys.issubset(disabled)
    except Exception:
        return False
_SKIP_CORNERS = _corners_disabled()


def _tg_alert(text: str) -> None:
    """Laut alarmieren wenn der Odds-Fetch versagt — niemals still alte Odds behalten."""
    tok  = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_TRADES_CHAT_ID")
            or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not (tok and chat):
        print("  ⚠️  (kein TELEGRAM-Setup — Alert nur im Log)")
        return
    try:
        import urllib.request
        body = json.dumps({"chat_id": chat, "text": text,
                           "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"  ⚠️  Telegram-Alert fehlgeschlagen: {e}")

# Minimale Änderung (in absoluten Odds), damit ein neuer Snapshot geschrieben wird
SNAP_MIN_DELTA = 0.02

ODDS_KEY   = os.environ.get("ODDS_API_KEY", "16154a94ee84482dcd5a4af88d521d73")
ODDS_HOST  = "api.the-odds-api.com"

# TheOddsAPI-Kosten = Märkte × Regionen pro Request. Die per-Event-Calls liefen auf
# eu,uk,us — wir ankern aber NUR auf Pinnacle (eu) + bet365 (uk, soft). Die us-Region
# (DraftKings/FanDuel…) nutzt unser Modell nicht → war reiner Quota-Verbrauch. Auf eu,uk
# gesenkt (16.06.2026, nach 100K-Verbrauch). Der h2h-Call lief eh schon auf eu,uk.
PER_EVENT_REGIONS = "eu,uk"

# CLV-Closing: in diesem Fenster vor Anpfiff werden die aktuellen Odds laufend als
# (vorläufige) Closing-Linie mitgeschrieben → der letzte pre-match Snapshot wird final.
# 9h (21.06.2026, Lucas-Write-Side-Fix): der fetch-wm-data-Cron (0 4,8,12,16,20 UTC) hat
# nachts eine 8h-Lücke (20:00→04:00). Mit 6h bekamen Spiele, die in dieser Lücke anpfeifen
# (z.B. 02:00-03:00 UTC), KEINEN Pre-Match-Snapshot → der last_known-Fallback fror In-Play-
# Quoten ein → CLV verworfen (7 Spiele im Status-Panel). 9h ≥ größte Cron-Lücke (8h) +
# Marge → der letzte Fetch VOR jedem Anpfiff liegt im Fenster → jedes Spiel kriegt einen
# echten Pre-Match-Snapshot, der bei Anpfiff final wird. Schließt die CLV-Abdeckungs-Lücke.
CLOSING_CAPTURE_WINDOW_H = 9.0

# In-Play-Schutz für den last_known-Fallback (16.06.2026 → QAT-SUI-Phantom):
# Ein Spiel ohne pre-match Snapshot, das schon LÄNGER läuft, liefert über TheOddsAPI
# Live-Quoten (QAT-SUI o25=21.0 / hw=81.0). Die als „Closing" einzufrieren erzeugt
# −55pp CLV-Phantome. Daher nur einfrieren, wenn der Anpfiff noch keine TOL-Minuten
# her ist — danach lieber KEIN Closing (CLV=None) als ein erfundenes.
CLOSING_FALLBACK_INPLAY_TOL_MIN = 15.0


def dc_contradicts_1x2(hw, aw, dc1X, dcX2) -> bool:
    """True wenn die Doppelte Chance dem 1X2-Favoriten widerspricht (dc1X/dcX2 verdreht).
    1X2-Favorit = kleinere Quote; DC-Favorit-Seite = kleinere DC. Stimmen die Seiten nicht überein,
    ist die DC-Orientierung kaputt (29.06.2026, Lucas: BRA-JPN E_HOMEAWAY_SWAP). Anker = 1X2."""
    if not all(isinstance(x, (int, float)) for x in (hw, aw, dc1X, dcX2)):
        return False
    return (aw < hw) != (dcX2 < dc1X)


def merge_closing_lines(existing: dict, odds_out: dict) -> dict:
    """Phase 3 (16.06.2026): spiegelt die odds_closing aus wm2026-data in die persistente
    wm_closing_lines.json. Regel: ein bereits FINALES Closing nie überschreiben/downgraden;
    sonst die FRISCHERE provisional übernehmen (näher am Anpfiff = besseres CLV). Rein/testbar."""
    out = dict(existing or {})
    for key, entry in (odds_out or {}).items():
        cl = (entry or {}).get("odds_closing")
        if not cl:
            continue
        prev = out.get(key)
        if prev and prev.get("final"):
            continue
        if cl.get("final") or not prev or str(cl.get("frozenAt", "")) >= str(prev.get("frozenAt", "")):
            out[key] = cl
    return out


def compute_closing(existing, cur_odds, hours_to_ko, now_iso):
    """Reine CLV-Closing-Logik (16.06.2026, testbar). Gibt das neue odds_closing zurück.
      - final → nie ändern (return existing)
      - pre-match (hours_to_ko > 0) im Capture-Fenster → aktuelle Odds als provisional
      - pre-match außerhalb Fenster → existing behalten
      - post-kickoff (hours_to_ko <= 0) + provisional vorhanden → final machen (NIE In-Play
        überschreiben); ohne pre-match Snapshot → None (Caller nutzt last_known-Fallback)."""
    if existing and existing.get("final"):
        return existing
    if hours_to_ko is None:
        return existing
    if hours_to_ko > 0:
        if hours_to_ko <= CLOSING_CAPTURE_WINDOW_H:
            return {**cur_odds, "frozenAt": now_iso, "provisional": True}
        return existing
    if existing:
        return {**existing, "provisional": False, "final": True}
    return None


# Soft-Konsens-Eröffnung (public_*_open) — wird von fetch_wm_multibook_odds.py „set-once-if-None"
# gesetzt. MUSS wie odds_open über Läufe hinweg erhalten bleiben.
_SOFT_OPEN_KEYS = (
    "public_hw_open", "public_dr_open", "public_aw_open",
    "public_o25_open", "public_u25_open", "public_bttsY_open", "public_bttsN_open",
)


def carry_soft_open(existing: dict, new_entry: dict) -> dict:
    """FIX 22.06.2026 (Lucas: „Opening==Jetzt auf fast jeder Card"): new_entry wird je Lauf frisch
    gebaut und odds_out[key]=new_entry ersetzt den Eintrag KOMPLETT. odds_open wurde explizit aus
    existing übernommen, public_*_open aber NICHT → war danach None → fetch_wm_multibook_odds (läuft
    danach, set-once-if-None) re-initialisierte das Soft-Opening auf den AKTUELLEN Konsens → 0pp
    Soft-Bewegung überall. Lösung: Soft-Opening genau wie odds_open mitschleppen."""
    for k in _SOFT_OPEN_KEYS:
        if existing.get(k) is not None:
            new_entry[k] = existing[k]
    return new_entry


# TheOddsAPI sport key for FIFA World Cup
# Falls back through list until one returns data
WM_SPORT_KEYS = [
    "soccer_fifa_world_cup",
    "soccer_world_cup",
    "soccer_international_wcq",   # WCQ as fallback
]

# Preferred bookmakers for odds (in priority order)
BOOKMAKERS = ["pinnacle", "bet365", "williamhill", "unibet", "betfair"]

# ── Our team IDs → name variants for fuzzy matching TheOddsAPI team names ──────
TEAM_NAMES: dict[str, list[str]] = {
    "MEX": ["Mexico"],
    "ZAF": ["South Africa"],
    "KOR": ["South Korea"],
    "CZE": ["Czech Republic", "Czechia"],
    "CAN": ["Canada"],
    "BIH": ["Bosnia", "Bosnia and Herzegovina"],
    "QAT": ["Qatar"],
    "SUI": ["Switzerland"],
    "BRA": ["Brazil"],
    "MAR": ["Morocco"],
    "HTI": ["Haiti"],
    "SCO": ["Scotland"],
    "USA": ["United States", "USA"],
    "PRY": ["Paraguay"],
    "AUS": ["Australia"],
    "TUR": ["Turkey", "Türkiye"],
    "GER": ["Germany"],
    "CUW": ["Curaçao", "Curacao"],
    "CIV": ["Ivory Coast", "Cote d'Ivoire", "Côte d'Ivoire"],
    "ECU": ["Ecuador"],
    "NED": ["Netherlands", "Holland"],
    "JPN": ["Japan"],
    "SWE": ["Sweden"],
    "TUN": ["Tunisia"],
    "BEL": ["Belgium"],
    "EGY": ["Egypt"],
    "IRN": ["Iran"],
    "NZL": ["New Zealand"],
    "ESP": ["Spain"],
    "CPV": ["Cape Verde"],
    "SAU": ["Saudi Arabia"],
    "URU": ["Uruguay"],
    "FRA": ["France"],
    "SEN": ["Senegal"],
    "IRQ": ["Iraq"],
    "NOR": ["Norway"],
    "ARG": ["Argentina"],
    "DZA": ["Algeria"],
    "AUT": ["Austria"],
    "JOR": ["Jordan"],
    "POR": ["Portugal"],
    "COD": ["DR Congo", "Congo DR", "Democratic Republic of Congo"],
    "UZB": ["Uzbekistan"],
    "COL": ["Colombia"],
    "ENG": ["England"],
    "CRO": ["Croatia"],
    "GHA": ["Ghana"],
    "PAN": ["Panama"],
}

def _name_to_id(name: str) -> str | None:
    """Reverse-lookup: TheOddsAPI team name → our 3-letter ID."""
    name_low = name.lower().strip()
    for tid, variants in TEAM_NAMES.items():
        for v in variants:
            if v.lower() == name_low or v.lower() in name_low or name_low in v.lower():
                return tid
    return None


def odds_get(path: str) -> dict | None:
    """Single HTTPS GET to TheOddsAPI. Returns parsed JSON or None."""
    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(ODDS_HOST, context=ctx, timeout=20)
        conn.request("GET", path, headers={"User-Agent": "CocoBet/1.0"})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        if resp.status == 422:
            return None   # sport not available yet
        if resp.status == 401:
            print("  ❌  TheOddsAPI: 401 Unauthorized — check ODDS_API_KEY")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  ❌  TheOddsAPI request failed: {e}")
        return None


def _find_sport_key() -> str | None:
    """Try WM sport keys until one returns events."""
    for sk in WM_SPORT_KEYS:
        path = f"/v4/sports/{sk}/events?apiKey={ODDS_KEY}"
        data = odds_get(path)
        if data and isinstance(data, list) and len(data) > 0:
            print(f"  ✅  Sport key: {sk} ({len(data)} events)")
            return sk
        elif data is None:
            print(f"  ⚠️  {sk}: not available yet")
        else:
            print(f"  ⚠️  {sk}: 0 events")
        time.sleep(0.5)
    return None


def _best_odds(bookmakers: list, our_book_prio: list) -> dict | None:
    """
    Extract h2h odds from event bookmaker list.
    Prefers pinnacle, then bet365, then any available.
    Returns {"_oc": {...}, "bookmaker": str, "_public_oc": {...}, "_public_bk": str}
    Wenn pinnacle gewählt wird, wird bet365 als public-Bookie zusätzlich extrahiert
    (für Public-vs-Sharp Bias-Berechnung).
    """
    candidates = {}
    for bk in bookmakers:
        bk_key = bk.get("key", "")
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            if len(outcomes) < 2:
                continue
            candidates[bk_key] = outcomes
    if not candidates:
        return None

    # Public-Proxy: bet365 wenn vorhanden, sonst williamhill/unibet/betfair
    PUBLIC_PRIO = ["bet365", "williamhill", "unibet", "betfair"]
    public_oc = None
    public_bk = None
    for pp in PUBLIC_PRIO:
        if pp in candidates:
            public_oc = candidates[pp]
            public_bk = pp
            break

    # Pick preferred bookmaker (Pinnacle als Sharp)
    for prio in our_book_prio:
        if prio in candidates:
            oc = candidates[prio]
            # Public-Bookie sollte nicht derselbe wie Sharp sein
            if public_bk == prio:
                public_oc = None
                public_bk = None
                for pp in PUBLIC_PRIO:
                    if pp != prio and pp in candidates:
                        public_oc = candidates[pp]
                        public_bk = pp
                        break
            return {
                "_oc": oc, "bookmaker": prio,
                "_public_oc": public_oc, "_public_bk": public_bk,
            }
    # Fall back to any
    for bk_key, oc in candidates.items():
        return {"_oc": oc, "bookmaker": bk_key, "_public_oc": None, "_public_bk": None}
    return None


def _extract_h2h(event: dict, home_id: str, away_id: str) -> dict | None:
    """
    Match event to our fixture and extract h2h odds.
    Event has home_team / away_team / bookmakers.
    We need to find the right outcome for home/draw/away.
    """
    home_names = TEAM_NAMES.get(home_id, [home_id])
    away_names = TEAM_NAMES.get(away_id, [away_id])

    ev_home = event.get("home_team", "")
    ev_away = event.get("away_team", "")

    def _matches(ev_name, our_names):
        ev_l = ev_name.lower()
        for n in our_names:
            if n.lower() in ev_l or ev_l in n.lower():
                return True
        return False

    if not (_matches(ev_home, home_names) and _matches(ev_away, away_names)):
        # API listet die Teams evtl. umgekehrt (ev_home = unser Auswärtsteam).
        # Das ist OK, solange beide Teams zur Fixture passen — die Outcome-
        # Zuordnung unten matcht per Team-IDENTITÄT (name_id == home_id), nicht
        # per Reihenfolge.
        # FIX 10.06.2026 (Audit): KEIN home_id/away_id-Swap mehr! Der alte Swap
        # vertauschte hw↔aw (+ public_/odds_open-1X2) für jede Fixture, die die
        # API umgekehrt listete → 5+ Spiele spiegelverkehrt (Mexiko als Heim-
        # Außenseiter etc.). DC/AH/O-U waren nie betroffen (andere Funktion,
        # matcht ebenfalls per Identität). Validierung reicht, Swap schädlich.
        if not (_matches(ev_home, away_names) and _matches(ev_away, home_names)):
            return None

    bk_result = _best_odds(event.get("bookmakers", []), BOOKMAKERS)
    if not bk_result:
        return None

    oc = bk_result["_oc"]
    home_win = draw = away_win = None

    # Match outcomes by name
    for name, price in oc.items():
        name_id = _name_to_id(name)
        if name_id == home_id:
            home_win = price
        elif name_id == away_id:
            away_win = price
        elif name.lower() in ("draw", "tie", "x"):
            draw = price

    # Fallback: if 3 values and no draw found, the middle is draw
    if draw is None and len(oc) == 3:
        prices = sorted(oc.values())
        # In 1X2 odds, draw is typically middle
        remaining = [p for p in prices if p != home_win and p != away_win]
        if remaining:
            draw = remaining[0]

    if home_win is None or away_win is None:
        return None

    out = {
        "hw": round(home_win, 3),
        "dr": round(draw, 3) if draw else None,
        "aw": round(away_win, 3),
        "bookmaker": bk_result["bookmaker"],
    }

    # Public-Bookie (bet365 oder Fallback) für Public-vs-Sharp-Vergleich
    public_oc = bk_result.get("_public_oc")
    if public_oc:
        p_home = p_draw = p_away = None
        for name, price in public_oc.items():
            name_id = _name_to_id(name)
            if name_id == home_id:
                p_home = price
            elif name_id == away_id:
                p_away = price
            elif name.lower() in ("draw", "tie", "x"):
                p_draw = price
        if p_draw is None and len(public_oc) == 3:
            prices = sorted(public_oc.values())
            remaining = [p for p in prices if p != p_home and p != p_away]
            if remaining:
                p_draw = remaining[0]
        if p_home is not None and p_away is not None:
            out["public_hw"] = round(p_home, 3)
            out["public_dr"] = round(p_draw, 3) if p_draw else None
            out["public_aw"] = round(p_away, 3)
            out["public_bookmaker"] = bk_result["_public_bk"]

    return out


def _load_history() -> dict:
    """Lädt wm2026-odds-history.json oder gibt leeres Dict zurück."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_history(history: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── Team-Name Aliases (DE → EN/Alt für TheOddsAPI Matching) ──────────────────
# TheOddsAPI nutzt englische Namen ("Canada"), unser wm2026-data.json deutsche ("Kanada").
# Beim DC/AH-Parsing müssen wir BEIDE Varianten prüfen.
TEAM_NAME_ALIASES = {
    "MEX": ["mexiko", "mexico"], "ZAF": ["südafrika", "south africa"],
    "KOR": ["südkorea", "south korea"], "CZE": ["tschechien", "czech republic", "czechia"],
    "CAN": ["kanada", "canada"], "BIH": ["bosnien", "bosnia", "bosnia and herzegovina", "bosnia & herzegovina"],
    "QAT": ["katar", "qatar"], "SUI": ["schweiz", "switzerland"],
    "BRA": ["brasilien", "brazil"], "MAR": ["marokko", "morocco"],
    "HTI": ["haiti"], "SCO": ["schottland", "scotland"],
    "USA": ["usa", "united states"], "PRY": ["paraguay"], "AUS": ["australien", "australia"],
    "TUR": ["türkei", "turkey", "türkiye"], "GER": ["deutschland", "germany"],
    "CUW": ["curaçao", "curacao"], "CIV": ["elfenbeinküste", "ivory coast", "cote d'ivoire"],
    "ECU": ["ecuador"], "NED": ["niederlande", "netherlands"], "JPN": ["japan"],
    "SWE": ["schweden", "sweden"], "TUN": ["tunesien", "tunisia"],
    "BEL": ["belgien", "belgium"], "EGY": ["ägypten", "egypt"],
    "IRN": ["iran"], "NZL": ["neuseeland", "new zealand"],
    "ESP": ["spanien", "spain"], "CPV": ["kap verde", "cabo verde", "cape verde"],
    "SAU": ["saudi-arabien", "saudi arabia"], "URU": ["uruguay"],
    "FRA": ["frankreich", "france"], "SEN": ["senegal"], "IRQ": ["irak", "iraq"],
    "NOR": ["norwegen", "norway"], "ARG": ["argentinien", "argentina"],
    "DZA": ["algerien", "algeria"], "AUT": ["österreich", "austria"], "JOR": ["jordanien", "jordan"],
    "POR": ["portugal"], "COD": ["dr kongo", "dr congo", "congo dr"],
    "UZB": ["usbekistan", "uzbekistan"], "COL": ["kolumbien", "colombia"],
    "ENG": ["england"], "CRO": ["kroatien", "croatia"], "GHA": ["ghana"], "PAN": ["panama"],
}


def _name_matches(name_lower: str, team_id: str) -> bool:
    """Prüft ob ein TheOddsAPI-Outcome-Name zu unserem team_id passt (alle Aliases)."""
    if not team_id: return False
    aliases = TEAM_NAME_ALIASES.get(team_id, [])
    for a in aliases:
        if a and a in name_lower:
            return True
    return False


def _extract_totals_btts(bookmakers: list, our_book_prio: list, home_id: str = "", away_id: str = "") -> dict:
    """
    Extract Over/Under (1.5/2.5/3.5), BTTS, Corner totals, Asian Handicap und Double Chance.
    Prefers same bookmaker priority as h2h.
    NB: home_id/away_id (3-letter codes wie 'CAN'/'BIH') werden via TEAM_NAME_ALIASES gegen die
    TheOddsAPI-Outcome-Namen geprüft, die in jeder Sprachvariante existieren können.
    Returns {o15, o25, o35, u15, u25, u35, bttsY, bttsN, cornerLine, cOver, cUnder,
             dc1X, dc12, dcX2, ahH_n050, ahA_p050, ahH_n075, ahA_p075, ahH_n100, ahA_p100}
    """
    # totals lines: bk_key → {line: (over, under)}
    totals_lines_by_bk: dict[str, dict] = {}
    btts_cands:   dict[str, tuple] = {}
    corner_cands: dict[str, tuple] = {}
    dc_cands:     dict[str, tuple] = {}    # bk_key → (1X, 12, X2)
    ah_lines_by_bk: dict[str, dict] = {}   # bk_key → {line: (home_price, away_price)}

    CORNER_PREFERRED_LINES = [9.5, 10.5, 9.0, 10.0, 8.5, 11.5]

    for bk in bookmakers:
        bk_key = bk.get("key", "")
        for market in bk.get("markets", []):
            mkey = market.get("key", "")

            if mkey in ("totals", "alternate_totals"):
                # Sammle alle Linien
                if bk_key not in totals_lines_by_bk:
                    totals_lines_by_bk[bk_key] = {}
                for o in market.get("outcomes", []):
                    point = o.get("point")
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    if point not in totals_lines_by_bk[bk_key]:
                        totals_lines_by_bk[bk_key][point] = [None, None]
                    if name == "over":
                        totals_lines_by_bk[bk_key][point][0] = price
                    elif name == "under":
                        totals_lines_by_bk[bk_key][point][1] = price

            elif mkey in ("btts", "both_teams_to_score"):
                yes = no = None
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if price and name in ("yes", "ja"):
                        yes = price
                    elif price and name in ("no", "nein"):
                        no = price
                if yes:
                    btts_cands[bk_key] = (yes, no)

            elif mkey in ("corners", "alternate_totals_corners"):
                lines: dict[float, list] = {}
                for o in market.get("outcomes", []):
                    point = o.get("point")
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    if point not in lines:
                        lines[point] = [None, None]
                    if name == "over":
                        lines[point][0] = price
                    elif name == "under":
                        lines[point][1] = price
                best_line = best_over = best_under = None
                for preferred in CORNER_PREFERRED_LINES:
                    if preferred in lines and lines[preferred][0] and lines[preferred][1]:
                        best_line, best_over, best_under = preferred, lines[preferred][0], lines[preferred][1]
                        break
                if not best_line:
                    for line, (ov, un) in sorted(lines.items()):
                        if ov and un:
                            best_line, best_over, best_under = line, ov, un
                            break
                if best_line and best_over:
                    corner_cands[bk_key] = (best_line, best_over, best_under)

            elif mkey == "double_chance":
                # Outcomes: "Home or Draw" (1X), "Away or Draw" (X2), "Home or Away" (12)
                dc_1x = dc_x2 = dc_12 = None
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    price = o.get("price")
                    if not price:
                        continue
                    has_home = _name_matches(name, home_id)
                    has_away = _name_matches(name, away_id)
                    has_draw = "draw" in name or "remis" in name or "unentsch" in name
                    if has_home and has_draw:
                        dc_1x = price
                    elif has_away and has_draw:
                        dc_x2 = price
                    elif has_home and has_away:
                        dc_12 = price
                if dc_1x or dc_x2 or dc_12:
                    dc_cands[bk_key] = (dc_1x, dc_12, dc_x2)

            elif mkey in ("spreads", "alternate_spreads"):
                # Asian Handicap: jedes Outcome hat name=Team + point=Line
                # alternate_spreads (13.06.2026) liefert die volle Linien-Leiter →
                # ah_lines_by_bk sammelt jetzt ALLE Linien, nicht nur die Hauptlinie.
                if bk_key not in ah_lines_by_bk:
                    ah_lines_by_bk[bk_key] = {}
                for o in market.get("outcomes", []):
                    name  = (o.get("name", "") or "").lower()
                    point = o.get("point")
                    price = o.get("price")
                    if point is None or not price:
                        continue
                    is_home = _name_matches(name, home_id)
                    is_away = _name_matches(name, away_id)
                    if not is_home and not is_away:
                        continue
                    # Speichere Heim-Linie (negativ = Heim-Favorit)
                    # AH-Heim -0.5 ↔ AH-Auswärts +0.5 ist dieselbe Linie, andere Seite
                    line_key = round(point, 2) if is_home else round(-point, 2)
                    if line_key not in ah_lines_by_bk[bk_key]:
                        ah_lines_by_bk[bk_key][line_key] = [None, None]
                    if is_home:
                        ah_lines_by_bk[bk_key][line_key][0] = price
                    elif is_away:
                        ah_lines_by_bk[bk_key][line_key][1] = price

    # Hängt die QUELLE (Buchmacher-Key) als letztes Tupel-Element an (Fix 15.06.2026):
    # damit der Tor-Anker nachvollziehbar ist und ein Guard warnen kann, wenn er NICHT
    # von Pinnacle stammt (stiller Soft-Fallback). Bestehende Indizes [0]/[1] bleiben.
    def _pick_bk(cands: dict):
        for prio in our_book_prio:
            if prio in cands:
                return (*cands[prio], prio)
        for k, v in cands.items():
            return (*v, k)
        return None

    # Total-Linien aus bevorzugtem Bookie
    def _pick_total_line(line: float) -> tuple | None:
        for prio in our_book_prio:
            if prio in totals_lines_by_bk and line in totals_lines_by_bk[prio]:
                ov, un = totals_lines_by_bk[prio][line]
                if ov and un:
                    return (ov, un, prio)
        for bk_key, bk_data in totals_lines_by_bk.items():
            if line in bk_data and bk_data[line][0] and bk_data[line][1]:
                ov, un = bk_data[line]
                return (ov, un, bk_key)
        return None

    t15 = _pick_total_line(1.5)
    t25 = _pick_total_line(2.5)
    t35 = _pick_total_line(3.5)

    # AH-Linien aus bevorzugtem Bookie
    def _pick_ah(line: float) -> tuple | None:
        for prio in our_book_prio:
            if prio in ah_lines_by_bk and line in ah_lines_by_bk[prio]:
                hm, aw = ah_lines_by_bk[prio][line]
                if hm and aw:
                    return (hm, aw)
        for bk_data in ah_lines_by_bk.values():
            if line in bk_data and bk_data[line][0] and bk_data[line][1]:
                return tuple(bk_data[line])
        return None

    ah_05 = _pick_ah(-0.5)
    ah_075 = _pick_ah(-0.75)
    ah_10 = _pick_ah(-1.0)
    # Breitere Linien für Mismatches (13.06.2026) — „sicherere" Underdog-Linien
    # (z.B. QAT +1.5/+2) jetzt verfügbar dank alternate_spreads.
    ah_15 = _pick_ah(-1.5)
    ah_20 = _pick_ah(-2.0)

    # Volle AH-Leiter (13.06.2026): Pinnacle bietet AH als schmale Bande um die faire
    # Linie — KEINE festen Buckets. Bei Blowouts (GER-CUW) ist die Bande z.B. −2.75…−3.75.
    # Daher die KOMPLETTE angebotene Leiter speichern, damit generate_wm_picks die
    # passende/sicherste Linie dynamisch wählen kann. {str(home_line): [home_odds, away_odds]}.
    def _ah_ladder() -> dict:
        for prio in our_book_prio:
            d = ah_lines_by_bk.get(prio)
            if d:
                out = {str(k): [v[0], v[1]] for k, v in sorted(d.items()) if v[0] and v[1]}
                if out:
                    return out
        for d in ah_lines_by_bk.values():
            out = {str(k): [v[0], v[1]] for k, v in sorted(d.items()) if v[0] and v[1]}
            if out:
                return out
        return {}
    ah_ladder = _ah_ladder()

    b = _pick_bk(btts_cands)
    c = _pick_bk(corner_cands)
    dc = _pick_bk(dc_cands)

    # ── Public-Bookmaker O/U + BTTS (NEU 09.06.2026) ─────────────────────
    # public_static_bias + lead_lag_bias brauchen Public-Quoten auch für O/U
    # und BTTS — bisher nur 1X2 verfügbar. Pick public-bookie nach gleichem
    # Schema wie h2h-Public (bet365 → williamhill → unibet → betfair).
    PUBLIC_PRIO = ["bet365", "williamhill", "unibet", "betfair"]
    # Public-Bookie darf nicht derselbe wie unser Sharp-Anker sein
    our_sharp = our_book_prio[0] if our_book_prio else None
    public_bk = None
    for pp in PUBLIC_PRIO:
        if pp != our_sharp and (pp in totals_lines_by_bk or pp in btts_cands):
            public_bk = pp
            break

    pub_o25 = pub_u25 = pub_bttsY = pub_bttsN = None
    if public_bk:
        # Public O/U 2.5
        pub_totals = totals_lines_by_bk.get(public_bk, {})
        if 2.5 in pub_totals and pub_totals[2.5][0] and pub_totals[2.5][1]:
            pub_o25, pub_u25 = pub_totals[2.5]
        # Public BTTS
        if public_bk in btts_cands:
            pub_bttsY, pub_bttsN = btts_cands[public_bk]

    return {
        "o15":     round(t15[0], 3) if t15 else None,
        "u15":     round(t15[1], 3) if t15 else None,
        "o25":     round(t25[0], 3) if t25 else None,
        "u25":     round(t25[1], 3) if t25 else None,
        "o35":     round(t35[0], 3) if t35 else None,
        "u35":     round(t35[1], 3) if t35 else None,
        "bttsY":   round(b[0], 3) if b else None,
        "bttsN":   round(b[1], 3) if b and b[1] else None,
        # Quelle des TOR-Ankers je Markt (Fix 15.06.2026): erlaubt dem Integritäts-Guard
        # zu warnen, wenn der de-viggte „Pinnacle-Anker" in Wahrheit ein Soft-Fallback ist.
        "o15_src":  t15[2] if t15 else None,
        "o25_src":  t25[2] if t25 else None,
        "o35_src":  t35[2] if t35 else None,
        "btts_src": b[2]  if b   else None,
        # Public-Bookmaker O/U 2.5 + BTTS für public_static_bias / lead_lag (NEU 09.06.2026)
        "public_o25":   round(pub_o25, 3) if pub_o25 else None,
        "public_u25":   round(pub_u25, 3) if pub_u25 else None,
        "public_bttsY": round(pub_bttsY, 3) if pub_bttsY else None,
        "public_bttsN": round(pub_bttsN, 3) if pub_bttsN else None,
        "public_ou_bookmaker": public_bk if (pub_o25 or pub_bttsY) else None,
        "cornerLine": c[0] if c else None,
        "cOver":   round(c[1], 3) if c and c[1] else None,
        "cUnder":  round(c[2], 3) if c and c[2] else None,
        "dc1X":    round(dc[0], 3) if dc and dc[0] else None,
        "dc12":    round(dc[1], 3) if dc and dc[1] else None,
        "dcX2":    round(dc[2], 3) if dc and dc[2] else None,
        "ahH_n050": round(ah_05[0], 3)  if ah_05  else None,
        "ahA_p050": round(ah_05[1], 3)  if ah_05  else None,
        "ahH_n075": round(ah_075[0], 3) if ah_075 else None,
        "ahA_p075": round(ah_075[1], 3) if ah_075 else None,
        "ahH_n100": round(ah_10[0], 3)  if ah_10  else None,
        "ahA_p100": round(ah_10[1], 3)  if ah_10  else None,
        "ahH_n150": round(ah_15[0], 3)  if ah_15  else None,
        "ahA_p150": round(ah_15[1], 3)  if ah_15  else None,
        "ahH_n200": round(ah_20[0], 3)  if ah_20  else None,
        "ahA_p200": round(ah_20[1], 3)  if ah_20  else None,
        "ahLadder": ah_ladder,          # volle angebotene Leiter (dynamische Linien-Wahl)
    }


def _snap_changed(last: dict | None, new_hw: float, new_dr: float | None, new_aw: float) -> bool:
    """True wenn sich mindestens eine Odds um SNAP_MIN_DELTA geändert hat."""
    if last is None:
        return True
    return (
        abs((last.get("hw") or 0) - new_hw) >= SNAP_MIN_DELTA
        or abs((last.get("aw") or 0) - new_aw) >= SNAP_MIN_DELTA
        or (new_dr is not None and abs((last.get("dr") or 0) - new_dr) >= SNAP_MIN_DELTA)
    )


def _has_imminent_kickoff(wm: dict, lo_min: float = -20.0, hi_min: float = 90.0) -> bool:
    """True, wenn ein bothResolved-Spiel (Gruppe ODER KO) im Fenster [jetzt+lo … jetzt+hi] Minuten
    anpfeift und noch KEIN finales Closing hat. Steuert die quota-schonende Nah-am-Anpfiff-Capture:
    nur dann feuert fetch_wm_odds im CLOSING_CAPTURE_ONLY-Modus TheOddsAPI an."""
    from datetime import datetime as _d, timezone as _t
    now = _d.now(_t.utc)
    odds = wm.get("odds") or {}
    fixtures = []
    for gd in (wm.get("groups") or {}).values():
        fixtures += gd.get("fixtures", [])
    fixtures += [f for f in (wm.get("koFixtures") or []) if f.get("home") and f.get("away")]
    for fx in fixtures:
        if not (fx.get("home") and fx.get("away")):
            continue
        if ((odds.get(f"{fx['home']}-{fx['away']}") or {}).get("odds_closing") or {}).get("final"):
            continue   # Closing schon final → nicht mehr nötig
        dt = None
        if fx.get("kickoff"):
            try:
                dt = _d.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
            except Exception:
                dt = None
        if dt is None and fx.get("date"):
            try:
                dt = _d.fromisoformat(f"{fx['date']}T{(fx.get('time') or '21:00')}:00+02:00")
            except Exception:
                dt = None
        if dt is None:
            continue
        if lo_min <= (dt - now).total_seconds() / 60.0 <= hi_min:
            return True
    return False


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"💰  fetch_wm_odds.py — WM 2026 Odds")
    print(f"    Key: {'✅ set' if ODDS_KEY else '❌ missing'}")
    print(f"    Time: {now_iso[:19]} UTC\n")

    if not ODDS_KEY:
        print("  ❌  ODDS_API_KEY not set")
        sys.exit(1)

    # ── Load wm2026-data.json ─────────────────────────────────
    if not WM_FILE.exists():
        print("  ❌  wm2026-data.json not found")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    # ── Nah-am-Anpfiff Closing-Capture (07.07.2026, Lucas: CLV-Messung war kaputt) ──
    # Der 4h-Cron verpasst die letzten Stunden vor Anpfiff → „Closing" war 1-7h veraltet → CLV
    # gegen tote Linie gemessen. capture-closing.yml ruft dieses Skript alle 15 min in Anpfiff-
    # Bändern mit CLOSING_CAPTURE_ONLY=1. Guard: NUR fetchen (API-Quota!), wenn ein Spiel im Fenster
    # [jetzt-20min … jetzt+90min] steht — sonst sofort raus. So ist die Closing-Linie ≤15min alt.
    if os.environ.get("CLOSING_CAPTURE_ONLY") == "1" and not _has_imminent_kickoff(wm):
        print("  ⏭️  Kein Spiel in [-20 … +90] min — Closing-Capture übersprungen (spart API).")
        return

    odds_out: dict[str, dict] = wm.get("odds") or {}
    groups = wm.get("groups", {})

    # Build teams Elo map for sanity checks + Team-Name-Map für DC/AH-Parsing
    teams_elo:   dict[str, float] = {}
    team_names:  dict[str, str]   = {}
    for gdata in groups.values():
        for t in gdata.get("teams", []):
            if t.get("elo"):
                teams_elo[t["id"]] = t["elo"]
            if t.get("name"):
                team_names[t["id"]] = t["name"]

    # Collect all fixtures
    all_fixtures: list[dict] = []
    for gkey, gdata in groups.items():
        for fx in gdata.get("fixtures", []):
            all_fixtures.append({**fx, "groupKey": gkey})

    # ── KO-Paarungen mit-bepreisen (25.06.2026, Lucas) ───────────────────────────
    # Sobald eine Gruppe komplett ist, stehen R32-Paarungen fest → auch deren Quoten holen, damit die
    # Card vom Vorschau- in den Pick-Zustand wechselt (zweistufig). Bracket hier frisch auflösen
    # (idempotent), damit Quoten same-cycle landen statt erst nach dem nächsten generate-Lauf.
    try:
        import wm_standings as _wmst
        import resolve_wm_bracket as _wmko
        _wmst.apply_to_wm(wm)
        _ko = _wmko.apply_to_wm(wm)
        _ko_n = 0
        for _kf in _ko:
            if _kf.get("bothResolved") and _kf.get("home") and _kf.get("away"):
                all_fixtures.append({
                    "home": _kf["home"], "away": _kf["away"],
                    "matchday": _kf["round"], "date": _kf.get("date"),
                    "kickoff": _kf.get("kickoff"), "venue": _kf.get("venue"),
                    "groupKey": "KO",
                })
                _ko_n += 1
        if _ko_n:
            print(f"  🏆 {_ko_n} KO-Paarungen werden mit-bepreist")
    except Exception as _e:
        print(f"  ⚠️  KO-Quoten-Sammlung übersprungen: {_e}")

    print(f"  Fixtures to price: {len(all_fixtures)}")

    # ── Find working sport key ────────────────────────────────
    print("\n  🔍  Looking for WM sport key in TheOddsAPI…")
    sport_key = _find_sport_key()

    if not sport_key:
        print("\n  ℹ️  WM 2026 odds not available in TheOddsAPI yet.")
        print("      Odds typically appear 2–3 weeks before the tournament.")
        # Write back unchanged (update meta only)
        wm["_meta"]["oddsUpdatedAt"] = now_iso
        with open(WM_FILE, "w", encoding="utf-8") as f:
            json.dump(wm, f, ensure_ascii=False, indent=2)
        # Während des Turniers ist "kein Sport-Key" ein echter Fehler (Key/Quota/
        # API-Umbenennung), kein harmloses Pre-Tournament-Warten → alarmieren.
        try:
            from datetime import date as _date
            wm_started = any(
                (fx.get("date") or "")[:10] <= datetime.now(timezone.utc).strftime("%Y-%m-%d")
                for g in wm.get("groups", {}).values() for fx in g.get("fixtures", []))
        except Exception:
            wm_started = True
        if wm_started:
            _tg_alert("🛑 <b>Odds-Fetch: kein WM-Sport-Key bei TheOddsAPI</b>\n"
                      "Mitten im Turnier — Key/Quota erschöpft oder API-Umbenennung? "
                      "Odds bleiben eingefroren. Actions-Log + ODDS_API_KEY prüfen.")
            print("  🛑  ALARM gesendet: kein Sport-Key trotz laufendem Turnier")
            sys.exit(1)
        return

    # ── Fetch 1: h2h von Pinnacle & Co (bevorzugte Bookmaker) ───
    print(f"\n  📥  Fetching h2h odds for {sport_key}…")
    path_h2h = (f"/v4/sports/{sport_key}/odds"
                f"?apiKey={ODDS_KEY}"
                f"&regions=eu,uk"
                f"&markets=h2h"
                f"&oddsFormat=decimal"
                f"&bookmakers={','.join(BOOKMAKERS)}")
    events = odds_get(path_h2h)

    if not events or not isinstance(events, list):
        print("  ⚠️  No events returned from TheOddsAPI")
        return

    print(f"  → {len(events)} h2h events fetched")

    # ── Fetch 2: totals + btts per Event-ID ──────────────────
    # Der Batch-Endpoint (/odds?markets=totals) gibt für WM 0 Events zurück,
    # weil TheOddsAPI den WM-Totals-Batch nicht befüllt (Coverage-Lücke).
    # Lösung: per-Event-Endpoint /events/{id}/odds — gleicher Ansatz wie
    # test-cards-api.js für Cards/Corners. Pinnacle O/U ist dort verfügbar.
    # WICHTIG (Fix 04.06.2026): TheOddsAPI liefert für WM-Events leere bookmakers wenn
    # zu viele Markets in einem Call. 4 Markets pro Call ist das Limit. Daher 3 Calls:
    #   Call 1: totals,btts,double_chance,spreads (Standard + DC + AH)
    #   Call 2: alternate_totals (für O1.5/O3.5/U1.5/U3.5)
    #   Call 3: alternate_totals_corners,corners (09.06.2026 — Pinnacle hat Corners drin)
    print(f"\n  📥  Fetching totals+btts+DC+spreads per event (Call 1/3)…")
    event_ids = [ev["id"] for ev in events if ev.get("id")]
    totals_by_id: dict[str, dict] = {}

    for i, eid in enumerate(event_ids):
        # `spreads` (Hauptlinie) ENTFERNT 16.06.2026: redundant, da Call 2
        # `alternate_spreads` die VOLLE Leiter inkl. Hauptlinie liefert (gleicher
        # Parser-Zweig). Spart 1 Markt × Regionen × Events × Läufe an Quota.
        path_ev = (f"/v4/sports/{sport_key}/events/{eid}/odds"
                   f"?apiKey={ODDS_KEY}"
                   f"&regions={PER_EVENT_REGIONS}"
                   f"&markets=totals,btts,double_chance"
                   f"&oddsFormat=decimal")
        ev_data = odds_get(path_ev)
        if isinstance(ev_data, dict) and ev_data.get("bookmakers"):
            totals_by_id[eid] = ev_data
        if i < len(event_ids) - 1:
            time.sleep(0.25)

    # ── Call 2: alternate_totals + alternate_spreads — mergen ──
    # FIX 13.06.2026: `spreads` (Call 1) liefert pro Buchmacher nur EINE Linie (die
    # Hauptlinie). Bei Mismatches (z.B. SUI -2 Favorit) ist die −2.0 → fällt durch
    # unser Raster ±0.5/0.75/1.0 → AH blieb leer (34/72 Fixtures ohne AH, u.a. QAT-SUI).
    # `alternate_spreads` gibt die GANZE Handicap-Leiter pro Book (auch ±0.5/1.0 bei
    # Favoriten + ±1.5/2/2.5 bei Mismatches) → füllt die AH-Felder für fast alle Spiele.
    print(f"  📥  Fetching alternate_totals + alternate_spreads per event (Call 2/3)…")
    alt_added = 0
    for i, eid in enumerate(event_ids):
        path_alt = (f"/v4/sports/{sport_key}/events/{eid}/odds"
                    f"?apiKey={ODDS_KEY}"
                    f"&regions={PER_EVENT_REGIONS}"
                    f"&markets=alternate_totals,alternate_spreads"
                    f"&oddsFormat=decimal")
        alt_data = odds_get(path_alt)
        if isinstance(alt_data, dict) and alt_data.get("bookmakers"):
            # Bookmaker-Markets in das Haupt-Event mergen
            existing = totals_by_id.get(eid)
            if existing:
                existing_bk_keys = {b["key"]: b for b in existing.get("bookmakers", [])}
                for new_bk in alt_data["bookmakers"]:
                    bk_key = new_bk.get("key")
                    if bk_key in existing_bk_keys:
                        # Markets in bestehendem Bookmaker anhängen
                        existing_bk_keys[bk_key]["markets"].extend(new_bk.get("markets", []))
                    else:
                        existing["bookmakers"].append(new_bk)
                alt_added += 1
            else:
                totals_by_id[eid] = alt_data
        if i < len(event_ids) - 1:
            time.sleep(0.25)
    print(f"  → alternate_totals: {alt_added} events mit zusätzlichen O/U-Linien")

    # ── Call 3: corners — Pinnacle hat Corner-Quoten 1-3 Tage vor Anpfiff ──
    # Wir probieren mehrere Market-Keys (TheOddsAPI hat das Schema mehrfach geändert):
    #   alternate_totals_corners → bevorzugt (gibt Linie + over/under)
    #   corners                  → einfacher Single-Line-Markt
    # Defensiv: wenn beide 0 events liefern, läuft Pipeline normal weiter (Picks
    # auf Corner-Markets entstehen nur wenn cornerLine im odds-Snapshot vorhanden).
    # WM-Profil deaktiviert Corner-Markets komplett (keine Signal-Coverage) →
    # Call 3 skip, spart 72+ API-Calls pro Run.
    if _SKIP_CORNERS:
        print(f"  ⏭️  Corners-Fetch skipped (Profil disabled alle Corner-Markets)")
        corn_added = 0
    else:
        print(f"  📥  Fetching corners per event (Call 3/3)…")
        corn_added = 0
        for i, eid in enumerate(event_ids):
            path_corn = (f"/v4/sports/{sport_key}/events/{eid}/odds"
                         f"?apiKey={ODDS_KEY}"
                         f"&regions={PER_EVENT_REGIONS}"
                         f"&markets=alternate_totals_corners,corners"
                         f"&oddsFormat=decimal")
            try:
                corn_data = odds_get(path_corn)
            except Exception as _e:
                corn_data = None
            if isinstance(corn_data, dict) and corn_data.get("bookmakers"):
                existing = totals_by_id.get(eid)
                if existing:
                    existing_bk_keys = {b["key"]: b for b in existing.get("bookmakers", [])}
                    for new_bk in corn_data["bookmakers"]:
                        bk_key = new_bk.get("key")
                        if bk_key in existing_bk_keys:
                            existing_bk_keys[bk_key]["markets"].extend(new_bk.get("markets", []))
                        else:
                            existing["bookmakers"].append(new_bk)
                    corn_added += 1
                else:
                    totals_by_id[eid] = corn_data
            if i < len(event_ids) - 1:
                time.sleep(0.25)
        print(f"  → corners: {corn_added} events mit Corner-Quoten")

    t_ok = sum(1 for v in totals_by_id.values() if v.get("bookmakers"))
    print(f"  → {len(event_ids)} events abgefragt, {t_ok} mit Totals-Daten")
    # Kein teams-Fallback nötig da wir per ID matchen
    totals_by_teams: list[dict] = []

    # ── Load odds history ─────────────────────────────────────
    history = _load_history()
    snaps_added = 0

    # ── Match fixtures to events ──────────────────────────────
    matched = 0
    updated = 0
    for fx in all_fixtures:
        home_id = fx["home"]
        away_id = fx["away"]
        key     = f"{home_id}-{away_id}"

        # Find matching event
        matched_event = None
        for ev in events:
            result = _extract_h2h(ev, home_id, away_id)
            if result:
                matched_event = (ev, result)
                break

        if not matched_event:
            continue

        ev, h2h = matched_event
        matched += 1

        # ── Totals + BTTS: erst im selben Event suchen, dann im Totals-Fetch ──
        # Merge Bookmakers: Pinnacle-Event (h2h) + separater Totals-Fetch
        merged_bks = list(ev.get("bookmakers", []))
        # Totals-Event by ID (gleiche Event-ID falls TheOddsAPI matcht)
        if ev.get("id") and ev["id"] in totals_by_id:
            t_ev = totals_by_id[ev["id"]]
            for bk in t_ev.get("bookmakers", []):
                if not any(b.get("key") == bk.get("key") for b in merged_bks):
                    merged_bks.append(bk)
        else:
            # Fallback: Team-Namen Matching im Totals-Fetch
            for t_ev in totals_by_teams:
                t_h2h = _extract_h2h(t_ev, home_id, away_id)
                if t_h2h:
                    for bk in t_ev.get("bookmakers", []):
                        if not any(b.get("key") == bk.get("key") for b in merged_bks):
                            merged_bks.append(bk)
                    break
        # Team-IDs mitgeben — der Parser nutzt TEAM_NAME_ALIASES für DE/EN Matching
        tb = _extract_totals_btts(merged_bks, BOOKMAKERS,
                                   home_id=home_id, away_id=away_id)

        # ── Elo sanity check: detect reversed hw/aw ──────────────────────
        # If Elo strongly favors the home team (diff > 200 pts) but market
        # has them as a big underdog (hw > 2.5× aw), the odds are reversed.
        # This happens when TheOddsAPI lists the match in the wrong direction.
        elo_h = teams_elo.get(home_id)
        elo_a = teams_elo.get(away_id)
        if elo_h and elo_a and h2h.get("hw") and h2h.get("aw"):
            elo_diff = elo_h - elo_a
            hw_raw, aw_raw = h2h["hw"], h2h["aw"]
            # Sanity-Check 1 (strikt): bei >200 Elo-Diff sollte Favorit klar im Markt sein
            # Sanity-Check 2 (mild): bei >150 Elo-Diff darf der Favorit nicht der Underdog im Markt sein
            #   Threshold: aw < 0.85 × hw bedeutet Auswärts ist klarer Markt-Favorit als Heim
            #   Bei FRA(1972)-NOR(1709) ist hw=4.28/aw=1.80 — Verhältnis 0.42 — eindeutig invertiert.
            if elo_diff > 200 and hw_raw > 2.5 * aw_raw:
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[strikt]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff > 150 and aw_raw < 0.85 * hw_raw:
                # Heimteam laut Elo deutlich stärker, aber Markt sieht Auswärts klar als Favorit
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[mild]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff < -200 and aw_raw > 2.5 * hw_raw:
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[strikt]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")
            elif elo_diff < -150 and hw_raw < 0.85 * aw_raw:
                # Auswärts laut Elo deutlich stärker, aber Markt sieht Heim klar als Favorit
                h2h["hw"], h2h["aw"] = h2h["aw"], h2h["hw"]
                print(f"  ⚠️  Elo-Sanity[mild]: {home_id}-{away_id} hw/aw korrigiert "
                      f"(Elo Δ={elo_diff:.0f}, {hw_raw}→{h2h['hw']} / {aw_raw}→{h2h['aw']})")

        # DC-Orientierungs-Selbstheilung (29.06.2026, Lucas: BRA-JPN E_HOMEAWAY_SWAP). Das 1X2 ist
        # der verlässliche Anker. Widerspricht die Doppelte Chance dem 1X2-Favoriten (dc1X/dcX2
        # verdreht — egal warum: DC-Outcome-Name-Matching, API-Orientierung), gleichen wir sie ans
        # 1X2 an. dc12 (Heim-oder-Auswärts) ist symmetrisch → unberührt. War 2/78 Fixtures (KO).
        if dc_contradicts_1x2(h2h.get("hw"), h2h.get("aw"), tb.get("dc1X"), tb.get("dcX2")):
            _d1, _d2 = tb.get("dc1X"), tb.get("dcX2")
            tb["dc1X"], tb["dcX2"] = _d2, _d1
            print(f"  ⚠️  DC-Orientierung {home_id}-{away_id}: dc1X/dcX2 ans 1X2 angeglichen "
                  f"({_d1}/{_d2} → {_d2}/{_d1})")

        existing = odds_out.get(key, {})

        # Preserve opening line (first-ever snapshot) — never overwrite.
        # FIX 13.06.2026: VORHER fror odds_open nur hw/dr/aw/o25/u25/bttsY ein →
        # ALLE Alt-Linien (o15/o35/u15/u35, DC, AH) hatten KEINE Eröffnungsquote →
        # der CLV-Sharp-Move-Check in compute_verdict (generate_wm_picks) konnte für
        # sie nie feuern (mkt_sig=0) → Alt-Line-Picks entgingen dem Line-Movement-
        # Filter. Konkret BEL-EGY: Über 3.5 wurde BET, obwohl die korrelierte Über-
        # 2.5-Linie eine starke Sharp-Bewegung GEGEN Over zeigte (1.74→1.98, CLV
        # −7pp) — nur weil Über 3.5 keine Open-Quote hatte. Jetzt: ALLE Linien
        # einfrieren, damit CLV auf jeder Linie greift.
        _OPEN_TB_KEYS = (
            "o15", "u15", "o25", "u25", "o35", "u35",
            "bttsY", "bttsN",
            "dc1X", "dc12", "dcX2",
            "ahH_n050", "ahA_p050", "ahH_n075", "ahA_p075", "ahH_n100", "ahA_p100",
            "ahH_n150", "ahA_p150", "ahH_n200", "ahA_p200",
            "cornerLine", "cOver", "cUnder",
        )
        odds_open = existing.get("odds_open")
        if not odds_open and h2h:
            odds_open = {"hw": h2h["hw"], "dr": h2h["dr"], "aw": h2h["aw"]}
            for k in _OPEN_TB_KEYS:
                if tb.get(k):
                    odds_open[k] = tb[k]
            if tb.get("ahLadder"):
                odds_open["ahLadder"] = tb["ahLadder"]
        elif odds_open:
            # Backfill: jede Linie, die beim ersten Open noch fehlte (Alt-Totals/AH
            # kommen erst per alternate_* Call), nachtragen — aber nie überschreiben.
            for k in _OPEN_TB_KEYS:
                if tb.get(k) and not odds_open.get(k):
                    odds_open[k] = tb[k]
            if tb.get("ahLadder") and not odds_open.get("ahLadder"):
                odds_open["ahLadder"] = tb["ahLadder"]

        new_entry = {
            "hw":         h2h["hw"],
            "dr":         h2h["dr"],
            "aw":         h2h["aw"],
            "bookmaker":  h2h["bookmaker"],
            "odds_open":  odds_open,
            "updatedAt":  now_iso,
        }
        # Fix 08.06.2026: Public-Bookie-Quoten durchreichen.
        # _extract_h2h_odds() liefert die als public_hw/dr/aw/public_bookmaker
        # für den PublicStaticBias-Signal (Sharp vs Public-Konsens).
        # Vorher wurden sie hier weggeworfen → Signal feuerte NIE für 234 Picks.
        for pk in ("public_hw", "public_dr", "public_aw", "public_bookmaker"):
            if h2h.get(pk) is not None:
                new_entry[pk] = h2h[pk]
        # Soft-Opening (public_*_open) aus dem alten Eintrag übernehmen — sonst setzt
        # fetch_wm_multibook_odds.py es je Lauf neu auf den aktuellen Konsens (Opening==Jetzt-Bug).
        carry_soft_open(existing, new_entry)
        # Add totals/btts if available
        for k in ("o15", "u15", "o25", "u25", "o35", "u35"):
            if tb.get(k):
                new_entry[k] = tb[k]
        if tb.get("bttsY"):
            new_entry["bttsY"] = tb["bttsY"]
            if tb.get("bttsN"):
                new_entry["bttsN"] = tb["bttsN"]
        # Public-Bookmaker O/U + BTTS (NEU 09.06.2026 — Signal-O/U-Coverage)
        for pk in ("public_o25", "public_u25", "public_bttsY", "public_bttsN",
                   "public_ou_bookmaker"):
            if tb.get(pk) is not None:
                new_entry[pk] = tb[pk]
        if tb.get("cOver"):
            new_entry["cornerLine"] = tb["cornerLine"]
            new_entry["cOver"]      = tb["cOver"]
            new_entry["cUnder"]     = tb["cUnder"]
            print(f"    🟦 Corners {home_id}-{away_id}: "
                  f"O{tb['cornerLine']} {tb['cOver']} / U{tb['cornerLine']} {tb['cUnder']}")
        # Doppelte Chance
        for k in ("dc1X", "dc12", "dcX2"):
            if tb.get(k):
                new_entry[k] = tb[k]
        # Asian Handicap — feste Linien + breitere Mismatch-Linien.
        # FIX 13.06.2026: ahH_n150/200 + ahLadder fehlten in dieser Kopier-Liste →
        # wurden zwar von get_match_odds zurückgegeben, aber nie ins gespeicherte
        # new_entry übernommen (DARUM blieb ahLadder ewig leer trotz neuem Code).
        for k in ("ahH_n050", "ahA_p050", "ahH_n075", "ahA_p075", "ahH_n100", "ahA_p100",
                  "ahH_n150", "ahA_p150", "ahH_n200", "ahA_p200"):
            if tb.get(k):
                new_entry[k] = tb[k]
        # Volle AH-Leiter für die dynamische Linien-Wahl in generate_wm_picks.
        if tb.get("ahLadder"):
            new_entry["ahLadder"] = tb["ahLadder"]

        # ── Closing Odds: letzter PRE-Anpfiff-Snapshot (CLV-Basis) ───────────
        # FIX 16.06.2026: Vorher wurden beim ERSTEN Fetch NACH Anpfiff die aktuellen
        # Odds eingefroren — die sind dann In-Play (volatil, falsche Closing-Basis →
        # verfälschtes CLV). Jetzt: solange pre-match, laufend die aktuellen Odds als
        # (vorläufige) Closing mitschreiben → konvergiert zur echten Closing-Linie, je
        # näher am Anpfiff der letzte Fetch war (mit dichtem Fetchen minutengenau).
        # Sobald Anpfiff vorbei: den letzten pre-match Snapshot als final behalten,
        # NIE mit In-Play-Odds überschreiben.
        existing_closing = existing.get("odds_closing")
        fx_date = fx.get("date", "")
        fx_time = fx.get("time", "21:00")
        _hours_to_ko = None
        if fx_date:
            try:
                from datetime import datetime as _dt, timezone as _tz
                _kickoff_dt  = _dt.fromisoformat(f"{fx_date}T{fx_time}:00+02:00")
                _now_dt      = _dt.now(_tz.utc).astimezone(_kickoff_dt.tzinfo)
                _hours_to_ko = (_kickoff_dt - _now_dt).total_seconds() / 3600
            except Exception:
                _hours_to_ko = None
        _cur = {"hw": h2h["hw"], "dr": h2h["dr"], "aw": h2h["aw"],
                **({"o25": tb["o25"]} if tb.get("o25") else {}),
                **({"u25": tb["u25"]} if tb.get("u25") else {}),
                **({"bttsY": tb["bttsY"]} if tb.get("bttsY") else {}),
                **({"bttsN": tb["bttsN"]} if tb.get("bttsN") else {}),
                # 23.06.2026 (Lucas): AH-Leiter mit-einfrieren → CLV für AH-Trades (bisher 0/8,
                # weil die Closing-Linie die Leiter nie enthielt). resolve_wm_results de-viggt sie.
                **({"ahLadder": tb["ahLadder"]} if tb.get("ahLadder") else {})}
        _closing = compute_closing(existing_closing, _cur, _hours_to_ko, now_iso)
        if _closing is not None:
            new_entry["odds_closing"] = _closing
            if _closing.get("final") and not (existing_closing or {}).get("final"):
                print(f"  🔒  Closing final (letzter pre-match Snapshot): {home_id} vs {away_id}")

        odds_out[key] = new_entry
        updated += 1

        # ── Odds History Snapshot ─────────────────────────────
        # (28.06.2026, Lucas) Anpfiff-Freeze: KEINE History-Snapshots nach Anpfiff anhängen.
        # Sonst landen In-Play-Linien (Tor → Quote schießt Richtung Spielstand) in der Zeitreihe
        # und verfälschen den Sharp Radar. odds_closing wird oben separat sauber (pre-match) gefroren.
        _post_ko = (_hours_to_ko is not None and _hours_to_ko <= 0)
        snaps = history.setdefault(key, [])
        # FIX 13.06.2026: letzten PINNACLE-Snap suchen (nicht irgendeinen) — seit wir
        # auch Public-Snaps in dieselbe Liste schreiben, wäre snaps[-1] sonst evtl. ein
        # Public-Eintrag und der _snap_changed-Vergleich falsch.
        last_snap = next((s for s in reversed(snaps) if s.get("bk") != "public"), None)
        pinn_changed = _snap_changed(last_snap, h2h["hw"], h2h["dr"], h2h["aw"])
        if pinn_changed and not _post_ko:
            snap_entry = {
                "ts":  now_iso,
                "hw":  h2h["hw"],
                "dr":  h2h["dr"],
                "aw":  h2h["aw"],
                "bk":  h2h["bookmaker"],
            }
            if tb["o25"]:
                snap_entry["o25"]   = tb["o25"]
                snap_entry["u25"]   = tb["u25"]
            if tb["bttsY"]:
                snap_entry["bttsY"] = tb["bttsY"]
            snaps.append(snap_entry)

        # ── Soft-Book (bet365)-Snapshot für lead_lag_bias ────────────────────────
        # Quelle ist bet365 (PUBLIC_PRIO/regions uk; 2.-schärfster Buchmacher, Lucas 14.06.).
        # lead_lag vergleicht „Pinnacle bewegt sich, bet365 hinkt nach".
        # FIX 14.06.2026: bet365-Snap wird jetzt geschrieben wenn ENTWEDER Pinnacle sich
        # bewegt (→ wir brauchen genau dann eine bet365-Vergleichslesung, um den Lag zu
        # sehen — auch wenn bet365 flach ist) ODER bet365 sich selbst bewegt. Vorher nur an
        # Pinnacle gekoppelt → bei flachen Pre-Match-Linien fast keine Snaps → _compute_move_pp
        # (braucht ≥2 Snaps) gab None → Signal feuerte 0×. Union maximiert die Zeitreihe;
        # feuert, sobald sich überhaupt etwas bewegt (kein Move = korrekt kein Signal).
        ph = h2h.get("public_hw")
        pd = h2h.get("public_dr")
        pa = h2h.get("public_aw")
        if ph and pa and not _post_ko:
            last_pub = next((s for s in reversed(snaps) if s.get("bk") == "public"), None)
            if pinn_changed or _snap_changed(last_pub, ph, pd, pa):
                pub_entry = {
                    "ts":  now_iso,
                    "hw":  ph,
                    "dr":  pd,
                    "aw":  pa,
                    "bk":  "public",
                    "bookmaker": h2h.get("public_bookmaker"),   # i.d.R. bet365
                }
                if tb.get("public_o25"):
                    pub_entry["o25"] = tb["public_o25"]
                    pub_entry["u25"] = tb.get("public_u25")
                snaps.append(pub_entry)

        # Track snapshot count + log
        if snaps and snaps[-1].get("ts") == now_iso:
            snaps_added += 1
        ou_str   = f" | O/U {tb['o25']}/{tb['u25']}" if tb["o25"] else ""
        btts_str = f" | BTTS {tb['bttsY']}" if tb["bttsY"] else ""
        home_display = TEAM_NAMES.get(home_id, [home_id])[0]
        away_display = TEAM_NAMES.get(away_id, [away_id])[0]
        print(f"  ✅  {home_display} vs {away_display}: "
              f"H {h2h['hw']} / X {h2h['dr']} / A {h2h['aw']}"
              f"{ou_str}{btts_str} [{h2h['bookmaker']}]")

    # ── Fallback-Freeze: post-kickoff Spiele die TheOddsAPI nicht mehr listet ──
    # Wenn ein Spiel bereits angepfiffen wurde und odds_closing noch nicht gesetzt ist
    # (weil TheOddsAPI das Event schon entfernt hat), frieren wir die zuletzt bekannten
    # Odds ein — gekennzeichnet mit frozenFrom: "last_known".
    freeze_count = 0
    for fx in all_fixtures:
        home_id = fx["home"]
        away_id = fx["away"]
        key     = f"{home_id}-{away_id}"
        entry   = odds_out.get(key)
        if not entry:
            continue
        # Schon final eingefroren → nichts tun.
        if (entry.get("odds_closing") or {}).get("final"):
            continue

        fx_date = fx.get("date", "")
        fx_time = fx.get("time", "21:00")
        if not fx_date:
            continue

        try:
            from datetime import datetime as _dt, timezone as _tz
            kickoff_str = f"{fx_date}T{fx_time}:00+02:00"
            kickoff_dt  = _dt.fromisoformat(kickoff_str)
            now_dt      = _dt.now(_tz.utc).astimezone(kickoff_dt.tzinfo)
            # Spiel angepfiffen + ein vorläufiger pre-match Snapshot existiert → final machen
            # (NICHT mit In-Play überschreiben). TheOddsAPI hat das Event evtl. schon entfernt.
            if now_dt >= kickoff_dt and (entry.get("odds_closing") or {}).get("provisional"):
                entry["odds_closing"] = {**entry["odds_closing"], "provisional": False, "final": True}
                freeze_count += 1
                continue
            mins_since_ko = (now_dt - kickoff_dt).total_seconds() / 60.0
            if (now_dt >= kickoff_dt and mins_since_ko <= CLOSING_FALLBACK_INPLAY_TOL_MIN
                    and not entry.get("odds_closing") and entry.get("hw") and entry.get("aw")):
                entry["odds_closing"] = {
                    "hw":  entry["hw"],
                    "dr":  entry.get("dr"),
                    "aw":  entry["aw"],
                    **({"o25": entry["o25"]} if entry.get("o25") else {}),
                    **({"u25": entry["u25"]} if entry.get("u25") else {}),
                    **({"bttsY": entry["bttsY"]} if entry.get("bttsY") else {}),
                    "frozenAt":   now_iso,
                    "frozenFrom": "last_known",  # TheOddsAPI hat Event nicht mehr geliefert
                    "final":      True,
                }
                freeze_count += 1
                home_display = TEAM_NAMES.get(home_id, [home_id])[0]
                away_display = TEAM_NAMES.get(away_id, [away_id])[0]
                print(f"  🔒  Fallback-Freeze (last_known): {home_display} vs {away_display}")
        except Exception:
            pass

    if freeze_count:
        print(f"   → {freeze_count} Closing(s) via Fallback eingefroren")

    # ── Write back ────────────────────────────────────────────
    wm["odds"] = odds_out
    wm["_meta"]["oddsUpdatedAt"] = now_iso

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    # ── Persistente Closing-Linien (Phase 3) ──────────────────
    # Eigene Datei, die der 15min-Manage-Workflow committet → minutengenaue CLV-Basis.
    try:
        _existing_cl = {}
        if CLOSING_LINES_FILE.exists():
            _existing_cl = json.loads(CLOSING_LINES_FILE.read_text(encoding="utf-8")) or {}
        _merged_cl = merge_closing_lines(_existing_cl, odds_out)
        CLOSING_LINES_FILE.write_text(
            json.dumps(_merged_cl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   🎯  {sum(1 for v in _merged_cl.values() if v.get('final'))} finale / "
              f"{len(_merged_cl)} Closing-Linien → {CLOSING_LINES_FILE.name}")
    except Exception as _e:
        print(f"   ⚠️  Closing-Lines-Persistenz fehlgeschlagen: {_e}")

    # ── Write history ─────────────────────────────────────────
    # FIX 16.06.2026: Fetch-Zeitstempel IMMER schreiben (auch ohne Move), damit der
    # Sharp-Radar-Badge „zuletzt geholt" zeigt — sonst stand er bei flachen Linien ewig
    # auf der letzten Bewegung und meldete fälschlich STALE, obwohl wir alle 15-30min
    # frisch holen (Manage-Zyklus). `_meta` ist kein Fixture-Array → von allen
    # Snapshot-Iterationen (py: per-Key-Zugriff, js: Array.isArray) ignoriert.
    history.setdefault("_meta", {})
    history["_meta"]["oddsFetchedAt"] = now_iso
    if snaps_added > 0:
        history["_meta"]["lastMovementAt"] = now_iso
    _save_history(history)
    if snaps_added > 0:
        print(f"   📸  {snaps_added} neue Snapshots → {HISTORY_FILE.name}")
    else:
        print(f"   📸  Keine Odds-Änderung — Fetch-Zeitstempel aktualisiert")

    remaining = len(all_fixtures) - matched
    print(f"\n✅  {updated} fixtures priced, {remaining} not yet available")
    print(f"   Saved: {WM_FILE}")

    # ── Loud-Failure-Guard (11.06.2026) ──────────────────────────────────
    # Wenn 0 Fixtures gepreist wurden, ist der Fetch effektiv tot (API-Fehler,
    # 401, Quota erschöpft) und behält still die ALTEN Odds → genau der Fall der
    # den Feed seit 08.06 eingefroren hat. NIE wieder still: laut alarmieren.
    if updated == 0 and len(all_fixtures) > 0:
        _tg_alert(
            "🛑 <b>Odds-Fetch hat 0 Fixtures aktualisiert</b>\n"
            f"{len(all_fixtures)} Fixtures, aber keine neue Quote geschrieben — "
            "TheOddsAPI-Fehler/401/Quota? Cards &amp; Trading laufen sonst auf "
            "veralteten Odds (Auto-Trade-Stale-Guard greift, aber Feed muss "
            "repariert werden). fetch_wm_odds-Actions-Log prüfen.")
        print("  🛑  ALARM gesendet: 0 Fixtures aktualisiert (Odds-Feed tot?)")
        sys.exit(1)


if __name__ == "__main__":
    main()
