#!/usr/bin/env python3
"""
fetch_liga_odds.py — Pinnacle-Quoten für die Top-5-Ligen in liga-data.json (25.06.2026, Lucas).

Phase 1 des Liga-auf-WM-Stack-Umbaus: holt 1X2 + Über/Unter 2.5 + BTTS via TheOddsAPI und schreibt
sie in EXAKT die Odds-Form, die die WM-Pick-Engine + der WM-Renderer erwarten (key "{homeId}-{awayId}",
Felder hw/dr/aw/odds_open/o25/u25/bttsY/bttsN/odds_closing). Opening-Carry + Closing-Snapshot werden
aus fetch_wm_odds wiederverwendet → identisches CLV-Verhalten.

Der KERN ist das Liga-Team-NAMENS-MATCHING (TheOddsAPI-Namen ↔ unsere API-Football-Teamnamen) — genau
das hat das alte Liga-Frontend dauernd zerschossen. Darum hier robust + unit-getestet (match_event_to_
fixture / _norm_name). Live-Fetch braucht ODDS_API_KEY (läuft im Workflow).
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import unicodedata
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
# 01.07.2026 (Lucas: „holen wir MLS-Odds für Sharp Radar/Steam/CLV?"): DATASET-AWARE. Bei der
# Dataset-Migration wurde AUSGERECHNET fetch_liga_odds übersehen — LIGA_FILE/LIGA_HISTORY waren hart
# auf liga-*.json → der MLS-Lauf (COCOBET_DATASET=mls) las liga-data.json + schrieb liga-odds-history
# statt mls-*. Folge: die MLS-Konsumenten (detect_wm_sharp_moves + CLV lesen mls-odds-history.json via
# D.file) hätten NIE Odds gesehen. Jetzt: D.data_file() (mls-data.json) + D.file(…) (mls-odds-history).
import cocobet_dataset as D  # noqa: E402
LIGA_FILE = str(D.data_file())
# Zeitreihe der Pinnacle-/Public-Snapshots (für Sharp Radar + detect_wm_sharp_moves, 26.06.2026).
# Format identisch zu wm2026-odds-history.json: {key: [{ts,bk,hw,dr,aw}...], _meta:{oddsFetchedAt}}.
LIGA_HISTORY = str(D.file("wm2026-odds-history.json", "liga-odds-history.json"))
# Minutengenaue Closing-Linien (vom 15min-Capture-Job nahe Anpfiff) — Parität zur WM
# (wm_closing_lines.json). resolve_wm_results.build_result_lookup liest sie bevorzugt.
LIGA_CLOSING = str(D.file("wm_closing_lines.json", "liga_closing_lines.json"))

# TheOddsAPI-Sport-Keys der Top 5 (stabil etabliert) + MLS (Brücken-Liga nach WM, 29.06.2026).
LEAGUE_SPORT_KEYS = {
    "ENG": "soccer_epl",
    "ESP": "soccer_spain_la_liga",
    "GER": "soccer_germany_bundesliga",
    "ITA": "soccer_italy_serie_a",
    "FRA": "soccer_france_ligue_one",
    "MLS": "soccer_usa_mls",
}
BOOK_PRIORITY = ["pinnacle", "betfair_ex_eu", "marathonbet", "williamhill"]
# Soft-/Public-Buchmacher für den Konsens (public_hw/dr/aw → public_static_bias-Signal +
# „Soft-Konsens folgte"-Bestätigung im Steam). Bewusst NICHT pinnacle (das ist der Sharp-Anker).
SOFT_PRIORITY = ["bet365", "williamhill", "unibet", "betclic", "marathonbet", "betfair_ex_eu"]

# Bekannte harte Alias-Fälle (TheOddsAPI ↔ API-Football). Erweiterbar bei Fehlmatches.
NAME_ALIASES = {
    "internazionale": "inter", "inter milan": "inter",
    "wolverhampton wanderers": "wolves",
    "paris saint germain": "psg", "paris saint-germain": "psg",
    "brighton and hove albion": "brighton", "brighton & hove albion": "brighton",
    "tottenham hotspur": "tottenham", "spurs": "tottenham",
    "borussia monchengladbach": "gladbach", "borussia mgladbach": "gladbach",
    "1899 hoffenheim": "hoffenheim", "tsg hoffenheim": "hoffenheim",
    # Sprach-Varianten (TheOddsAPI englisch ↔ API-Football lokal)
    "bayern munich": "bayern", "bayern munchen": "bayern", "fc bayern munchen": "bayern",
    "fc bayern munich": "bayern",
    # ── MLS (12.07.2026, Lucas: „MLS ist auf Polymarket da") ──────────────────────────────
    # Polymarket UND TheOddsAPI nennen MLS-Klubs anders als API-Football. Ohne diese Aliase
    # läuft die Zuordnung still ins Leere (keine Odds, keine Poly-Edges, keine Signale).
    # ⚠️ LA-KOLLISION: „Los Angeles FC" normalisiert zu „los angeles" (FC ist Stoppwort) und
    # würde per Substring auf „Los Angeles Galaxy" matchen → wir hätten auf das FALSCHE LA-Team
    # gewettet. Darum beide auf eigene, kollisionsfreie Kerne mappen (lafc ≠ galaxy).
    "los angeles fc": "lafc", "lafc": "lafc", "la fc": "lafc",
    "los angeles galaxy": "galaxy", "la galaxy": "galaxy",
    "sporting kansas city": "sporting kc", "sporting kc": "sporting kc",
    "new york city fc": "nycfc", "nycfc": "nycfc", "new york city": "nycfc",
    # „D.C. United SC" (so nennt Polymarket es real, 12.07. Live-Lauf) — der Punkt-Split macht aus
    # „d.c." die Tokens {d,c}, die gegen unser {dc} nicht überlappen → Alias auf einen gemeinsamen Kern.
    "d.c. united": "dc united", "d.c. united sc": "dc united", "dc united sc": "dc united",
    "dc united": "dc united", "washington dc united": "dc united",
    "cf montreal": "montreal", "cf montreal impact": "montreal", "montreal impact": "montreal",
    "st. louis city sc": "st louis city", "st louis city sc": "st louis city",
    "san diego fc": "san diego", "charlotte fc": "charlotte", "austin fc": "austin",
    "inter miami cf": "inter miami", "columbus crew sc": "columbus crew",
    "vancouver whitecaps fc": "vancouver whitecaps", "seattle sounders fc": "seattle sounders",
    "houston dynamo fc": "houston dynamo", "chicago fire fc": "chicago fire",
    "minnesota united": "minnesota united", "orlando city": "orlando city",
    "ny red bulls": "new york red bulls", "new york red bulls": "new york red bulls",
}
# Tokens, die bei der Normalisierung wegfallen (Rechtsform/Präfixe).
_STOP = {"fc", "cf", "ac", "sc", "ssc", "as", "rc", "cd", "ud", "sd", "afc", "bsc",
         "club", "calcio", "1", "1846", "1899", "1900", "04", "05", "09", "the", "de"}


def _norm_name(name: str) -> str:
    """Teamname → vergleichbarer Kern: ohne Akzente, Rechtsform, Kleinschreibung, Alias aufgelöst."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    if s in NAME_ALIASES:
        s = NAME_ALIASES[s]
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t and t not in _STOP]
    return " ".join(toks) or s.strip()


def _names_match(a: str, b: str) -> bool:
    """Zwei Teamnamen gleich? Normalisiert; Treffer bei Gleichheit, Substring oder Token-Überlapp."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    # signifikanter Überlapp (z.B. „real madrid" vs „real madrid cf" / „athletic" vs „athletic club")
    inter = ta & tb
    return bool(inter) and len(inter) >= min(len(ta), len(tb))


def match_event_to_fixture(event: dict, home_name: str, away_name: str) -> str | None:
    """TheOddsAPI-Event ↔ unsere Paarung. Gibt 'direct' (Event-Home==unser Home),
    'swapped' (vertauscht) oder None zurück — orientierungs-bewusst (wie beim WM-Result-Fix)."""
    eh, ea = event.get("home_team", ""), event.get("away_team", "")
    if _names_match(eh, home_name) and _names_match(ea, away_name):
        return "direct"
    if _names_match(eh, away_name) and _names_match(ea, home_name):
        return "swapped"
    return None


MATCH_DATE_TOL_DAYS = 4   # Event-Datum muss ±4 Tage am Fixture-Datum liegen (s. pick_event_for_fixture)


def _event_date(ev: dict) -> str:
    return (ev.get("commence_time") or "")[:10]


def _days_apart(d1: str, d2: str):
    from datetime import date
    try:
        return abs((date.fromisoformat(d1[:10]) - date.fromisoformat(d2[:10])).days)
    except Exception:
        return None


def pick_event_for_fixture(events: list, home_name: str, away_name: str, fx_date: str,
                           tol_days: int = MATCH_DATE_TOL_DAYS):
    """Bestes TheOddsAPI-Event für unsere Paarung: Team-Match UND nächstes Datum (±tol_days).
    KRITISCH für Liga (Bug 26.06.2026 „Spieltag 1 dann 20"): jede Paarung spielt zweimal
    (Hin/Rück). match_event_to_fixture akzeptiert 'swapped' → ein Hinrunden-Event („A vs B")
    matchte sonst auch das Rückspiel-Fixture („B-A", andere Runde, Monate später) → Odds landeten
    auf der falschen Runde. Datum-Nähe trennt die beiden eindeutig. Reine Funktion (testbar)."""
    best = None
    for ev in events:
        o = match_event_to_fixture(ev, home_name, away_name)
        if not o:
            continue
        dd = _days_apart(_event_date(ev), fx_date) if fx_date else 0
        if fx_date and (dd is None or dd > tol_days):
            continue
        d = dd if dd is not None else 0
        if best is None or d < best[0]:
            best = (d, ev, o)
    return (best[1], best[2]) if best else None


def _best_book(bookmakers: list, market_key: str, priority: list | None = None):
    """Erstes Bookmaker-Market nach Prioritäten. Gibt (bk_key, outcomes). priority=None → Sharp."""
    prio = priority or BOOK_PRIORITY
    by_key = {b.get("key"): b for b in (bookmakers or [])}
    # Bei expliziter Soft-Priorität NUR diese Bücher (sonst fiele es auf Sharp/Pinnacle zurück).
    order = prio if priority else (prio + [k for k in by_key if k not in prio])
    for bk in order:
        b = by_key.get(bk)
        if not b:
            continue
        for m in (b.get("markets") or []):
            if m.get("key") == market_key and m.get("outcomes"):
                return bk, m["outcomes"]
    return None, None


def _map_1x2(outs: list, home_name: str, away_name: str):
    """h2h-Outcomes → (hw, dr, aw), per Name zugeordnet (orientierungs-agnostisch).
    Einmal definiert, von Sharp/Public/Betfair genutzt (28.06.2026: Entdopplung)."""
    hw = dr = aw = None
    for o in (outs or []):
        nm, price = o.get("name", ""), o.get("price")
        if (nm or "").lower() == "draw":
            dr = price
        elif _names_match(nm, home_name):
            hw = price
        elif _names_match(nm, away_name):
            aw = price
    return hw, dr, aw


_OU_LINES = (("15", 1.5), ("25", 2.5), ("35", 3.5))


def _extract_ou(outs: list, prefix: str = "") -> dict:
    """totals-Outcomes → {f'{prefix}o15': .., f'{prefix}u15': .., …} für 1.5/2.5/3.5."""
    res = {}
    for o in (outs or []):
        pt = o.get("point")
        if pt is None:
            continue
        for suf, line in _OU_LINES:
            if abs(pt - line) < 1e-6:
                nm = (o.get("name") or "").lower()
                if nm == "over":
                    res[f"{prefix}o{suf}"] = o.get("price")
                elif nm == "under":
                    res[f"{prefix}u{suf}"] = o.get("price")
    return res


def _extract_btts(outs: list, prefix: str = "") -> dict:
    res = {}
    for o in (outs or []):
        nm = (o.get("name") or "").lower()
        if nm == "yes":
            res[f"{prefix}bttsY"] = o.get("price")
        elif nm == "no":
            res[f"{prefix}bttsN"] = o.get("price")
    return res


# AH-Viertel-Leiter (identisch zu fetch_wm_odds / steam_engine)
_AH_STEPS = ((0.25, "025"), (0.5, "050"), (0.75, "075"), (1.0, "100"),
             (1.25, "125"), (1.5, "150"), (1.75, "175"), (2.0, "200"), (2.25, "225"))


def _extract_ah(outs: list, home_name: str, away_name: str) -> dict:
    """spreads-Outcomes → AH-Leiter + diskrete Keys (ahH_n*/ahA_p*/ahA_n*), alles in
    Heim-Linien-Perspektive normalisiert. TheOddsAPI liefert point je Team-Sicht:
    Heim point=-1.0 = „Heim −1", Auswärts point=+1.0 = dieselbe Linie von der Gegenseite."""
    home_odds: dict[float, float] = {}   # heim-linie → heim-quote
    away_odds: dict[float, float] = {}    # heim-linie → auswärts-quote
    for o in (outs or []):
        nm, pt, price = o.get("name", ""), o.get("point"), o.get("price")
        if pt is None or not price:
            continue
        if _names_match(nm, home_name):
            home_odds[round(float(pt), 2)] = price
        elif _names_match(nm, away_name):
            away_odds[round(-float(pt), 2)] = price   # in Heim-Linien-Perspektive spiegeln
    res: dict = {}
    ladder = {}
    for hl in sorted(set(home_odds) | set(away_odds)):
        ho, ao = home_odds.get(hl), away_odds.get(hl)
        if ho and ao:
            ladder[str(hl)] = [round(ho, 3), round(ao, 3)]
    if ladder:
        res["ahLadder"] = ladder
    for val, suf in _AH_STEPS:
        if -val in home_odds:          # Heim −val
            res[f"ahH_n{suf}"] = round(home_odds[-val], 3)
        if -val in away_odds:          # Auswärts +val (Underdog-Deckung)
            res[f"ahA_p{suf}"] = round(away_odds[-val], 3)
        if val in away_odds:           # Auswärts −val (Auswärts-Favorit)
            res[f"ahA_n{suf}"] = round(away_odds[val], 3)
    return res


# ── Multi-Book-Soft-Konsens (27.07.2026, Lucas: Status „Public single-book“) ──────
# Der alte public_* nahm nur den ERSTEN verfügbaren Soft-Book (SOFT_PRIORITY[0], z.B. bet365) —
# 1-Book-Rauschen, deshalb feuerte public_static_bias für MLS/Liga kaum. Die WM bekam via
# fetch_wm_multibook_odds (API-Football /odds) einen Median-Konsens; für Klub-Ligen ist das
# unnötig: TheOddsAPI liefert je Event ohnehin viele Bücher (regions=eu,uk,us — 07.08.2026 Lucas:
# us-Bücher dazu für mehr Soft-Konsens-Tiefe auf den Kernligen). Wir mitteln also
# über ALLE weichen Bücher der bereits geholten Antwort — kein Extra-Call, keine Zweitquelle,
# gleiche Semantik wie WM ("Konsens (N Books)"). Sharp-Anker (Pinnacle, Betfair-Exchange) raus.
_SHARP_BOOKS = {"pinnacle", "betfair_ex_eu", "betfair_ex_uk", "betfair"}


def _soft_bookmakers(bks: list) -> list:
    return [b for b in (bks or []) if (b.get("key") or "").lower() not in _SHARP_BOOKS]


def _median_odd(vals: list):
    vals = [float(v) for v in vals if v and float(v) > 1.0]
    return round(statistics.median(vals), 3) if vals else None


def _market_outcomes(bk: dict, market_key: str):
    for m in (bk.get("markets") or []):
        if m.get("key") == market_key and m.get("outcomes"):
            return m["outcomes"]
    return None


def soft_consensus(bks: list, home_name: str, away_name: str):
    """Median-Konsens der Soft-Books für public_* (1X2 + O/U 1.5/2.5/3.5 + BTTS).
    Gibt (pub_dict, books_1x2, n_ou_books, n_btts_books). pub_dict enthält nur
    gesetzte public_*-Felder. Orientierungs-agnostisch (per Name gemappt), rein/testbar."""
    acc = {k: [] for k in ("hw", "dr", "aw", "o15", "u15", "o25", "u25",
                           "o35", "u35", "bttsY", "bttsN")}
    books_1x2, n_ou, n_btts = [], 0, 0
    for b in _soft_bookmakers(bks):
        key = (b.get("key") or "").lower()
        h2h = _market_outcomes(b, "h2h")
        if h2h:
            hw, dr, aw = _map_1x2(h2h, home_name, away_name)
            if hw and dr and aw:
                acc["hw"].append(hw); acc["dr"].append(dr); acc["aw"].append(aw)
                books_1x2.append(key)
        tot = (_market_outcomes(b, "totals") or []) + (_market_outcomes(b, "alternate_totals") or [])
        if tot:
            ou = _extract_ou(tot)
            if ou:
                n_ou += 1
                for kk, vv in ou.items():
                    if vv:
                        acc[kk].append(vv)
        bt_outs = _market_outcomes(b, "btts")
        if bt_outs:
            bt = _extract_btts(bt_outs)
            if bt:
                n_btts += 1
                for kk, vv in bt.items():
                    if vv:
                        acc[kk].append(vv)
    pub = {}
    for k, vals in acc.items():
        m = _median_odd(vals)
        if m is not None:
            pub[f"public_{k}"] = m
    return pub, books_1x2, n_ou, n_btts


def extract_prices(event: dict, orientation: str, home_name: str, away_name: str) -> dict:
    """1X2 + O/U (1.5/2.5/3.5) + BTTS + AH-Leiter aus einem Event ziehen — Sharp + Public.
    Heim/Auswärts korrekt zugeordnet (orientierungs-agnostisch)."""
    out = {}
    bks = event.get("bookmakers") or []
    # ── 1X2 (h2h) — Sharp-Anker ──
    bk, outs = _best_book(bks, "h2h")
    hw, dr, aw = _map_1x2(outs, home_name, away_name)
    if hw and dr and aw:
        out.update({"hw": hw, "dr": dr, "aw": aw, "bookmaker": bk})
    # ── Public/Soft-Konsens: MEDIAN über ALLE Soft-Books (27.07.2026) statt Einzel-Book ──
    _pub, _b1x2, _nou, _nbtts = soft_consensus(bks, home_name, away_name)
    out.update(_pub)
    if _pub.get("public_hw"):
        out["public_bookmaker"] = (f"Konsens ({len(_b1x2)} Books)" if len(_b1x2) >= 2
                                   else (_b1x2[0] if _b1x2 else "Soft-Book"))
    if any(_pub.get(f"public_{k}") for k in ("o15", "o25", "o35", "bttsY", "bttsN")):
        _n = max(_nou, _nbtts)
        out["public_ou_bookmaker"] = f"Konsens ({_n} Books)" if _n >= 2 else "Soft-Book"
    # ── Betfair Exchange = 2. Sharp-Anker (Preis-Cross-Check, 28.06.2026, Lucas) ──
    # Eigenständig gezogen (NICHT nur als Fallback in BOOK_PRIORITY), um Pinnacle gegenzuchecken.
    _, bfouts = _best_book(bks, "h2h", priority=["betfair_ex_eu"])
    bhw, bdr, baw = _map_1x2(bfouts, home_name, away_name)
    if bhw and bdr and baw:
        out.update({"bf_hw": bhw, "bf_dr": bdr, "bf_aw": baw})
    # ── Über/Unter (1.5/2.5/3.5) — Sharp ──
    _, t_outs = _best_book(bks, "totals")
    _, at_outs = _best_book(bks, "alternate_totals")   # 1.5/3.5 (per-Event, flag-gated)
    out.update(_extract_ou((t_outs or []) + (at_outs or [])))
    # ── BTTS — Sharp ──
    _, b_outs = _best_book(bks, "btts")
    out.update(_extract_btts(b_outs))
    # ── Asian Handicap (spreads) — Sharp-Leiter + diskrete Keys ──
    _, sp_outs = _best_book(bks, "spreads")
    out.update(_extract_ah(sp_outs, home_name, away_name))
    return out


from odds_plausibility import plausible_1x2 as _plausible_1x2   # 13.07.2026: EINE Quelle
from odds_plausibility import derive_double_chance             # 25.07.2026: DC für Safer-Line
from odds_plausibility import clean_snaps as _clean_snaps      # 10.08.2026: Selbstheilung Alt-Platzhalter
# (08.07.2026, Lucas: Radar zeigte Fake-Drops bis -84pp.) Beim Markt-Opening liefert The Odds API
# Platzhalter (dr=1.01, aw=1.06 …), bevor der Markt settlet. Die Regel lebt jetzt zentral in
# odds_plausibility.py — vorher lag sie dreifach im Repo mit UNTERSCHIEDLICHEN Overround-Grenzen
# (1.25 hier vs 1.30 in steam_engine): genau so laufen Schwellen still auseinander.


def _hours_to_kickoff(kickoff, now_iso: str):
    """Stunden bis Anpfiff (negativ = angepfiffen). None wenn unbekannt.

    17.07.2026: nötig für compute_closing — siehe build_odds_entry.
    """
    if not kickoff:
        return None
    from datetime import datetime as _d
    try:
        ko = _d.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        now = _d.fromisoformat(str(now_iso).replace("Z", "+00:00"))
        return (ko - now).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def build_odds_entry(prices: dict, existing: dict, now_iso: str, hist: list | None = None,
                     kickoff=None) -> dict:
    """Preise → gespeicherte Odds-Form (wie fetch_wm_odds.new_entry). Opening-Carry + Closing."""
    import fetch_wm_odds as W   # carry_soft_open + compute_closing wiederverwenden
    existing = existing or {}
    odds_open = dict(existing.get("odds_open") or {})
    # 1X2-Opening als KOHÄRENTES plausibles Set einfrieren — NICHT per-Outcome (sonst friert ein
    # Platzhalter wie dr=1.01 dauerhaft ein → Frankenstein-Markt → Fake-Drops im Radar). Bestehendes
    # plausibles Opening behalten; Müll/unset → erste PLAUSIBLE Quote aus der History (echte Eröffnung),
    # sonst die aktuelle plausible Quote. Nichts Plausibles → 1X2-Opening NICHT setzen.
    if not _plausible_1x2(odds_open.get("hw"), odds_open.get("dr"), odds_open.get("aw")):
        src = next((e for e in (hist or []) if _plausible_1x2(e.get("hw"), e.get("dr"), e.get("aw"))), None)
        if src is None and _plausible_1x2(prices.get("hw"), prices.get("dr"), prices.get("aw")):
            src = prices
        if src:
            odds_open["hw"], odds_open["dr"], odds_open["aw"] = src["hw"], src["dr"], src["aw"]
        else:
            for k in ("hw", "dr", "aw"):
                odds_open.pop(k, None)
    # O/U (alle Linien) + BTTS: per-Outcome-Carry (unkritischer, kein 3-Wege-Markt).
    _OU_BTTS = ("o15", "u15", "o25", "u25", "o35", "u35", "bttsY", "bttsN")
    for k in _OU_BTTS:
        if prices.get(k) and not odds_open.get(k):
            odds_open[k] = prices[k]
    entry = {
        "odds_open": odds_open, "updatedAt": now_iso,
    }
    # ── 22.07.2026 (Lucas, ENDGÜLTIG): 1X2 NUR schreiben wenn PLAUSIBEL ──────────────────────────
    # Die Platzhalter-Quoten-Klasse (1.04/1.04/1.04, Overround ≫1.3) tauchte immer wieder auf, weil
    # sie hier — an der SCHREIBQUELLE — roh ins `odds`-Feld gingen und dann jeder Verbraucher
    # (Fair/Edge/Trade/Signal) einzeln dagegen gehärtet werden musste. Schluss damit: dasselbe
    # gate+carry-Muster wie O/U/AH. Plausibel → schreiben. Implausibel/fehlend → letzte PLAUSIBLE
    # Quote tragen. Nichts Plausibles → 1X2 GAR NICHT setzen (kein Fake-Anker, lieber „kein Anker").
    _new_ok = _plausible_1x2(prices.get("hw"), prices.get("dr"), prices.get("aw"))
    _old_ok = _plausible_1x2(existing.get("hw"), existing.get("dr"), existing.get("aw"))
    if _new_ok:
        entry["hw"], entry["dr"], entry["aw"] = prices["hw"], prices["dr"], prices["aw"]
        entry["bookmaker"] = prices.get("bookmaker")
    elif _old_ok:
        entry["hw"], entry["dr"], entry["aw"] = existing["hw"], existing["dr"], existing["aw"]
        entry["bookmaker"] = existing.get("bookmaker")
        entry["oddsCarriedAt"] = now_iso   # 1X2 ist getragen, nicht frisch (Guard/Frontend sehen es)
    # ── 25.07.2026 (Lucas: „bei Sieg-Quote >2 die sichere Linie") — Doppelte Chance ableiten ──
    # WM holt DC per Event-Endpoint; fetch_liga_odds holt nur h2h/totals/spreads → MLS/Liga hatten
    # NIE dc1X/dcX2, deshalb feuerte die sichere-Linien-Ableitung (Heimsieg → DC 1X) für sie nie.
    # DC ist deterministisch aus dem (jetzt geschriebenen, plausiblen) 1X2 → hier ableiten, damit
    # der bestehende WM-Mechanismus 1:1 auch für MLS/Liga greift. Gegatet in derive_double_chance.
    _dc = derive_double_chance(entry.get("hw"), entry.get("dr"), entry.get("aw"))
    if _dc:
        entry["dc1X"], entry["dc12"], entry["dcX2"] = _dc["dc1X"], _dc["dc12"], _dc["dcX2"]
    # ── 15.07.2026 (Lucas: „quotentechnisch was von MLS?") — O/U-QUOTEN NICHT LÖSCHEN ──
    # BEFUND: TheOddsAPI liefert `totals` für die MLS nur sporadisch (bei 14 von 16 Fetch-Zyklen
    # fehlten sie). Der Eintrag wurde bei JEDEM Lauf komplett neu gebaut und O/U nur übernommen,
    # wenn der aktuelle Fetch sie hatte → jeder Lauf ohne totals LÖSCHTE die letzte O/U-Quote.
    # Die Spiele nahe am Anpfiff werden am häufigsten gerefresht → traf genau sie am härtesten
    # (erster Spieltag stand ganz ohne O/U da). Gilt für Liga genauso.
    #
    # Fix wie bei odds_open: fehlt die frische Quote, die letzte bekannte behalten (leicht veraltet
    # ist für O/U-Signale/Picks weit besser als gar keine; der nächste Fetch mit totals überschreibt
    # sie). Nur der aktuelle Stand (entry) wird getragen — die History-Snaps bleiben roh, damit die
    # Bewegungsanalyse echt bleibt.
    carried = False
    for k in _OU_BTTS:
        if prices.get(k):
            entry[k] = prices[k]
        elif existing.get(k):
            entry[k] = existing[k]
            carried = True
    # AH-Leiter + diskrete Keys durchreichen (09.07.2026 — Liga/MLS AH-Parität mit WM).
    if prices.get("ahLadder"):
        entry["ahLadder"] = prices["ahLadder"]
    elif existing.get("ahLadder"):
        entry["ahLadder"] = existing["ahLadder"]
        carried = True
    _ah_keys = {k for k in list(prices) + list(existing)
                if k.startswith("ahH_n") or k.startswith("ahA_p") or k.startswith("ahA_n")}
    for k in _ah_keys:
        if prices.get(k):
            entry[k] = prices[k]
        elif existing.get(k):
            entry[k] = existing[k]
            carried = True
    # 15.07.2026: Polymarket-Patches durchreichen. fetch_wm_poly_prices schreibt poly_* NACH dem
    # Odds-Lauf in dieselbe Datei. Baut fetch_liga_odds den Eintrag beim nächsten 2h-Lauf neu, ohne
    # diese Felder zu tragen, löscht es die Poly-Preise → Steam-Lag-Signal, Poly-Edge im Radar und
    # der Whale-Tab standen für die anstehenden Spiele ohne Poly da (bei JEDEM Odds-Lauf aufs Neue).
    # Poly kommt aus einem anderen Prozess → immer aus existing tragen (TheOddsAPI liefert kein poly).
    for k in list(existing.keys()):
        if k.startswith("poly_") and k not in entry:
            entry[k] = existing[k]

    # Transparenz: wann war die letzte Quote frisch? Guard/Frontend können Stale erkennen.
    if carried:
        entry["marketsCarriedAt"] = now_iso
        entry["marketsFreshAt"] = existing.get("marketsFreshAt") or existing.get("updatedAt")
    else:
        entry["marketsFreshAt"] = now_iso
    # Public/Soft-Konsens 1X2 + O/U + BTTS durchreichen (public_static_bias/lead_lag).
    _PUB = ("public_hw", "public_dr", "public_aw", "public_bookmaker",
            "public_o15", "public_u15", "public_o25", "public_u25",
            "public_o35", "public_u35", "public_bttsY", "public_bttsN",
            "public_ou_bookmaker")
    for k in _PUB:
        if prices.get(k) is not None:
            entry[k] = prices[k]
    # Betfair-Exchange-Anker 1X2 durchreichen (Sharp-Konsens-Cross-Check im Radar).
    for k in ("bf_hw", "bf_dr", "bf_aw"):
        if prices.get(k) is not None:
            entry[k] = prices[k]
    W.carry_soft_open(existing, entry)   # trägt vorhandene public_*_open mit (Soft-Opening-Fix)
    # Soft-Opening seeden (1×), falls nicht aus existing getragen — sonst „Opening==Jetzt".
    for k in ("hw", "dr", "aw", "o15", "u15", "o25", "u25", "o35", "u35", "bttsY", "bttsN"):
        if entry.get(f"public_{k}_open") is None and prices.get(f"public_{k}"):
            entry[f"public_{k}_open"] = prices[f"public_{k}"]
    # Closing-Snapshot (pre-match laufend, nach Anpfiff eingefroren) — gleiche Mechanik wie WM.
    # AH-Leiter mit-einfrieren → CLV für AH-Trades (wie WM, 23.06.2026).
    cur = {k: prices[k] for k in ("hw", "dr", "aw", "o15", "u15", "o25", "u25",
                                  "o35", "u35", "bttsY", "bttsN") if prices.get(k)}
    if prices.get("ahLadder"):
        cur["ahLadder"] = prices["ahLadder"]
    try:
        # 17.07.2026 — 🔴 CLV WAR FÜR LIGA + MLS KOMPLETT TOT.
        # Hier stand `None` als hours_to_ko. compute_closing braucht den Abstand zum Anpfiff, um zu
        # entscheiden: pre-match im Fenster → provisional, nach Anpfiff → final. Mit None fällt es
        # durch ALLE Zweige und gibt None zurück → `odds_closing` wurde NIE gesetzt → keine
        # closing_lines → **kein CLV**. Belegt: WM 100/104 Odds mit Closing (84 final), Liga 0/48,
        # MLS 0/30. Die WM nutzt einen eigenen Fetcher und war nie betroffen — deshalb fiel es nicht auf.
        _closing = W.compute_closing(existing.get("odds_closing"), cur,
                                     _hours_to_kickoff(kickoff, now_iso), now_iso)
        if _closing is not None:
            entry["odds_closing"] = _closing
    except Exception:
        pass
    return entry


def _snap_changed(last: dict | None, hw, dr, aw, neben: dict | None = None) -> bool:
    """Hat sich seit dem letzten Snap etwas bewegt? 1X2 ODER eine Nebenlinie.

    06.09.2026 (Lucas: „mit all den Infos muss doch was drin sein"). Bis heute fragte dieses
    Gate NUR nach hw/dr/aw. Bewegte sich die O/U-Linie, waehrend das 1X2 stand, wurde GAR KEIN
    Snapshot geschrieben — die O/U-Zeitreihe war ein Nebenprodukt der 1X2-Zeitreihe und hatte
    genau dort Luecken, wo eine reine Tor-Bewegung stattfand. Genau die Bewegung, die ein
    O/U-Pick braucht.

    Gemessener Anlass: von 318 abgerechneten Picks trugen 162 KEIN einziges Preis-Signal, und
    die fehlende Gruppe war fast vollstaendig Ueber/Unter und BTTS. Preis-Signale sind die
    einzige Signalfamilie mit belegtem CLV-Zusammenhang (r=+0,35, p=0,0001) — die Haelfte
    unserer Picks entstand blind zu der einen Haelfte, die etwas kann.

    `neben` ist optional, damit bestehende Aufrufer (und ihre Tests) unveraendert gelten.
    """
    if not last:
        return True
    if last.get("hw") != hw or last.get("dr") != dr or last.get("aw") != aw:
        return True
    for k, v in (neben or {}).items():
        if v is not None and last.get(k) != v:
            return True
    return False


def _kickoff_passed(kickoff_iso) -> bool:
    """Anpfiff vorbei? (28.06.2026, Lucas: Anpfiff-Freeze für die History — keine In-Play-Snaps.)"""
    if not kickoff_iso:
        return False
    from datetime import datetime, timezone
    try:
        kt = datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
        if kt.tzinfo is None:
            kt = kt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= kt
    except Exception:
        return False


def append_snapshot(history: dict, key: str, prices: dict, now_iso: str, post_ko: bool = False) -> int:
    """Hängt Pinnacle- + Public-Snapshot an die Zeitreihe an, wenn sich 1X2 geändert hat.
    Gibt Anzahl neuer Snaps zurück. Rein/testbar (gleiches Format wie wm2026-odds-history).
    post_ko=True (Anpfiff vorbei) → KEIN Snapshot mehr (In-Play würde den Sharp Radar verfälschen)."""
    if post_ko:
        return 0
    added = 0
    snaps = history.setdefault(key, [])

    def _neben_felder(prefix: str) -> dict:
        """O/U-Linien UND BTTS in den Snap.

        09.07.2026: O/U rein (lead_lag-O/U braucht Pinnacle+Public-Zeitreihe).
        06.09.2026: BTTS rein. `_extract_btts` holt bttsY/bttsN, `soft_consensus` mittelt sie,
        `build_odds_entry` traegt sie im Eintrag — nur die ZEITREIHE hat sie nie gesehen:
        0 von 27.086 Snapshots in liga+mls trugen BTTS. Die Information war da und wurde nie
        gefragt. Ohne Zeitreihe kann kein bewegungsbasiertes Preis-Signal je auf einen
        BTTS-Pick feuern.
        """
        f = {}
        for suf in ("15", "25", "35"):
            v = prices.get(f"{prefix}o{suf}")
            if v:
                f[f"o{suf}"] = v
                f[f"u{suf}"] = prices.get(f"{prefix}u{suf}")
        y = prices.get(f"{prefix}bttsY")
        if y:
            f["bttsY"] = y
            f["bttsN"] = prices.get(f"{prefix}bttsN")
        return f

    # 20.07.2026 (MLS-Audit): Platzhalter-Quoten (hw/dr/aw ≈ 1.04/1.01/1.04, Overround ~2.9) NIE in die
    # History schreiben. Sie sind kein echter Markt, aber die Sharp-Money-Signale (steam_lag, RLM,
    # opener, multi_book, lead_lag) lesen die HISTORY → der Platzhalter→Echt-Sprung wird als Fake-Steam
    # gelesen ODER vom Plausibilitäts-Guard genullt → die ganze Familie verstummt. Der frühere
    # Ghost-Moves-Fix gatete nur odds_open; hier ist die Schreibgrenze der Zeitreihe selbst.
    hw, dr, aw = prices.get("hw"), prices.get("dr"), prices.get("aw")
    if hw and dr and aw and _plausible_1x2(hw, dr, aw):
        last_pinn = next((s for s in reversed(snaps) if s.get("bk") != "public"), None)
        _nb = _neben_felder("")
        if _snap_changed(last_pinn, hw, dr, aw, _nb):
            snaps.append({"ts": now_iso, "bk": "pinnacle", "hw": hw, "dr": dr, "aw": aw,
                          **_nb})
            added += 1
    phw, pdr, paw = prices.get("public_hw"), prices.get("public_dr"), prices.get("public_aw")
    if phw and pdr and paw and _plausible_1x2(phw, pdr, paw):
        last_pub = next((s for s in reversed(snaps) if s.get("bk") == "public"), None)
        _nbp = _neben_felder("public_")
        if _snap_changed(last_pub, phw, pdr, paw, _nbp):
            snaps.append({"ts": now_iso, "bk": "public", "hw": phw, "dr": pdr, "aw": paw,
                          **_nbp})
            added += 1
    return added


def scrub_history(history: dict) -> int:
    """10.08.2026 (Lucas): Altlast-Platzhalter-Snaps aus der bestehenden History werfen und Anzahl
    entfernter Snaps zurückgeben. Selbstheilung: das Write-Gate (append_snapshot) verhindert NEUE
    Platzhalter, aber vor dem Gate (20.07) geschriebene blieben liegen und triggern Geister-Moves +
    Fake-Steam. clean_snaps = dieselbe Plausibilitätsgrenze. _meta bleibt unangetastet. REIN/testbar."""
    removed = 0
    for hk, snaps in list((history or {}).items()):
        if hk == "_meta" or not isinstance(snaps, list):
            continue
        clean = _clean_snaps(snaps)
        if len(clean) != len(snaps):
            removed += len(snaps) - len(clean)
            history[hk] = clean
    return removed


# ───────────────────────── Live-Fetch ─────────────────────────

# BTTS + alternate_totals (1.5/3.5) brauchen den Per-Event-Endpoint (QUOTA-teuer: markets×regions
# je Event). Deshalb FLAG-GATED (25.07.2026): ohne FETCH_EXTRA_MARKETS=1 kein Extra-Call, keine
# neuen Felder → Verhalten exakt wie bisher. Fenster begrenzt die Calls auf anpfiffnahe Spiele.
_EXTRA_MARKETS_ENABLED = os.environ.get("FETCH_EXTRA_MARKETS") == "1"
try:
    _EXTRA_WINDOW_H = float(os.environ.get("EXTRA_MARKETS_WINDOW_H", "96"))
except (TypeError, ValueError):
    _EXTRA_WINDOW_H = 96.0


def _merge_bookmakers(base_bks: list, extra_bks: list) -> list:
    """Extra-Markets (btts, alternate_totals) je Bookmaker in die Basis mergen — reihenfolge-
    unabhängig, keine Markt-Duplikate. Reine Funktion (testbar)."""
    by_key = {b.get("key"): b for b in (base_bks or []) if b.get("key")}
    for eb in (extra_bks or []):
        k = eb.get("key")
        if not k:
            continue
        if k in by_key:
            existing = by_key[k].setdefault("markets", [])
            have = {m.get("key") for m in existing}
            for m in (eb.get("markets") or []):
                if m.get("key") not in have:
                    existing.append(m)
        else:
            by_key[k] = eb
    return list(by_key.values())


def _fetch_event_extra(sport_key: str, event_id: str) -> list:
    """Per-Event-Endpoint für BTTS + alternate_totals. Gibt die bookmakers-Liste oder []."""
    import fetch_wm_odds as W
    path = (f"/v4/sports/{sport_key}/events/{event_id}/odds?apiKey={W.ODDS_KEY}"
            f"&regions=eu,uk,us&markets=btts,alternate_totals&oddsFormat=decimal")
    data = W.odds_get(path)
    if isinstance(data, dict):
        return data.get("bookmakers") or []
    return []


def _enrich_event_markets(ev: dict, sport_key: str, fx: dict, now_iso: str) -> dict:
    """Reichert ein Event um BTTS + alternate_totals an. Gated: FETCH_EXTRA_MARKETS=1 UND Anpfiff
    in [0 … _EXTRA_WINDOW_H]. Ohne Flag unverändert (kein Call, keine neuen Felder)."""
    if not _EXTRA_MARKETS_ENABLED:
        return ev
    htk = _hours_to_kickoff(fx.get("kickoff"), now_iso)
    if htk is None or htk < 0 or htk > _EXTRA_WINDOW_H:
        return ev
    eid = ev.get("id")
    if not eid:
        return ev
    extra = _fetch_event_extra(sport_key, eid)
    if not extra:
        return ev
    return {**ev, "bookmakers": _merge_bookmakers(ev.get("bookmakers") or [], extra)}


def _fetch_events(sport_key: str) -> list:
    # WICHTIG: odds_get hängt den apiKey NICHT an — der Pfad muss ?apiKey=… enthalten (wie WM).
    # BTTS + alternate_totals laufen NICHT im Batch, sondern per-Event via _enrich_event_markets
    # (flag-gated FETCH_EXTRA_MARKETS). Der Bulk-Call bleibt bei den Featured-Markets.
    import fetch_wm_odds as W
    # 09.07.2026: spreads (Asian Handicap) ergänzt → Liga/MLS bekommen AH-Picks wie die WM.
    path = (f"/v4/sports/{sport_key}/odds?apiKey={W.ODDS_KEY}"
            f"&regions=eu,uk,us&markets=h2h,totals,spreads&oddsFormat=decimal")
    data = W.odds_get(path)
    return data if isinstance(data, list) else []


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print("=== fetch_liga_odds.py ===")
    if not os.environ.get("ODDS_API_KEY"):
        print("  ❌  ODDS_API_KEY nicht gesetzt — übersprungen (läuft nur im Workflow).")
        sys.exit(0)
    if not os.path.exists(LIGA_FILE):
        print(f"  ❌  {os.path.basename(LIGA_FILE)} fehlt — erst build_liga_data.py laufen lassen.")
        sys.exit(1)
    with open(LIGA_FILE, encoding="utf-8") as f:
        wm = json.load(f)
    # Closing-Capture-Modus (nah am Anpfiff, 15min-Cron): NUR TheOddsAPI anfeuern, wenn ein
    # Liga-Spiel im Fenster [-20…+90] min anpfeift und noch kein finales Closing hat — sonst
    # sofort No-Op (quota-schonend). Gleicher Guard wie WM (_has_imminent_kickoff).
    if os.environ.get("CLOSING_CAPTURE_ONLY") == "1":
        import fetch_wm_odds as W
        if not W._has_imminent_kickoff(wm):
            print("  ⏸️  Kein Liga-Spiel nah am Anpfiff — Closing-Capture No-Op (Quota gespart).")
            sys.exit(0)
    groups = wm.get("groups") or {}
    odds_out = wm.setdefault("odds", {})
    # Odds-History laden (Zeitreihe für Sharp Radar / detect_wm_sharp_moves).
    history = {}
    if os.path.exists(LIGA_HISTORY):
        try:
            with open(LIGA_HISTORY, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}
    snaps_added = 0
    total = 0
    matched_keys = set()
    leagues_ok: set = set()      # Ligen, für die TheOddsAPI diesen Lauf WIRKLICH Events lieferte
    key_league: dict = {}        # Odds-Key → Liga (fürs per-Liga-Pruning)
    for lk, gd in groups.items():
        for fx in (gd.get("fixtures") or []):
            key_league[f"{fx['home']}-{fx['away']}"] = lk
    for lk, sport_key in LEAGUE_SPORT_KEYS.items():
        gd = groups.get(lk) or {}
        fixtures = gd.get("fixtures") or []
        if not fixtures:
            continue
        events = _fetch_events(sport_key)
        print(f"  {lk}: {len(events)} Events von TheOddsAPI")
        if not events:
            # 12.07.2026 (Wipe-Audit): Ausfall/Quota/429 für DIESE Liga → sie darf NICHT gepruned
            # werden, sonst löschen wir ihre Odds (inkl. odds_open/Opening-Linien) obwohl sie
            # nur nicht abgefragt werden konnten.
            print(f"  ⚠️  {lk}: 0 Events — Liga wird beim Pruning ÜBERSPRUNGEN (kein Wipe).")
            continue
        leagues_ok.add(lk)
        for fx in fixtures:
            if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN"):
                continue   # gespielt
            hn, an = fx.get("homeName"), fx.get("awayName")
            # Datum-nächstes Event (verhindert Hin-/Rückrunden-Verwechslung, s. pick_event_for_fixture).
            matched = pick_event_for_fixture(events, hn, an, fx.get("date") or "")
            if not matched:
                continue
            ev, orient = matched
            ev = _enrich_event_markets(ev, sport_key, fx, now_iso)
            prices = extract_prices(ev, orient, hn, an)
            if not prices.get("hw"):
                continue
            key = f"{fx['home']}-{fx['away']}"
            odds_out[key] = build_odds_entry(prices, odds_out.get(key), now_iso,
                                             hist=history.get(key), kickoff=fx.get("kickoff"))
            snaps_added += append_snapshot(history, key, prices, now_iso, post_ko=_kickoff_passed(fx.get("kickoff")))
            matched_keys.add(key)
            total += 1
    # Altlasten-Pruning (Bug 26.06.2026): früher fehl-gematchte Odds (falsche Runde) aus odds_out
    # entfernen. Behalten: diesen Lauf gematchte + gespielte Spiele (für Resolve/CLV).
    # 12.07.2026 (Wipe-Audit, Lucas): NUR PRO LIGA prunen, und nur für Ligen, die diesen Lauf
    # wirklich Events lieferten. Vorher reichte `total > 0` (also EINE erfolgreiche Liga), um die
    # Odds ALLER anderen Ligen zu löschen, wenn deren Abfrage still fehlschlug (Quota/429/Timeout
    # → _fetch_events gibt []). Das hätte odds_open/Opening-Linien vernichtet → Fake-Drops + CLV weg.
    if leagues_ok:
        played_keys = {f"{fx['home']}-{fx['away']}"
                       for g in groups.values() for fx in (g.get("fixtures") or [])
                       if (fx.get("result") or {}).get("status") in ("FT", "AET", "PEN")}
        pruned = 0
        for k in list(odds_out.keys()):
            if key_league.get(k) not in leagues_ok:
                continue          # Liga nicht (erfolgreich) abgefragt → NICHT anfassen
            if k not in matched_keys and k not in played_keys:
                del odds_out[k]
                pruned += 1
        skipped = [lk for lk in LEAGUE_SPORT_KEYS if (groups.get(lk) or {}).get("fixtures")
                   and lk not in leagues_ok]
        if skipped:
            print(f"  🛡️  Pruning übersprungen für {skipped} (keine Events geliefert) — Odds bleiben.")
        print(f"  🧹 {pruned} Altlast-Odds entfernt (nur aus {sorted(leagues_ok)}).")
    wm.setdefault("_meta", {})["oddsUpdatedAt"] = now_iso
    with open(LIGA_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)
    # 10.08.2026 (Lucas): Selbstheilung — Altlast-Platzhalter-Snaps (vor dem Write-Gate 20.07 geschrieben)
    # aus der bestehenden History scrubben (append_snapshot verhindert NEUE, alte blieben liegen).
    scrubbed = scrub_history(history)
    if scrubbed:
        print(f"  🧼 {scrubbed} Altlast-Platzhalter-Snap(s) aus der History gescrubbt.")
    history.setdefault("_meta", {})["oddsFetchedAt"] = now_iso
    with open(LIGA_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    # Minutengenaue Closing-Linien spiegeln (wie WM merge_closing_lines) → liga_closing_lines.json.
    # Der 15min-Capture-Job committet NUR diese Datei (verwirft liga-data.json) → clobbert nie Picks.
    import fetch_wm_odds as W
    _existing_cl = {}
    if os.path.exists(LIGA_CLOSING):
        try:
            with open(LIGA_CLOSING, encoding="utf-8") as f:
                _existing_cl = json.load(f) or {}
        except Exception:
            _existing_cl = {}
    _merged_cl = W.merge_closing_lines(_existing_cl, odds_out)
    if _merged_cl != _existing_cl:
        with open(LIGA_CLOSING, "w", encoding="utf-8") as f:
            json.dump(_merged_cl, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {total} Liga-Spiele bepreist · {snaps_added} neue Odds-Snapshots")


if __name__ == "__main__":
    main()
