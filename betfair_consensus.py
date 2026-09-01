#!/usr/bin/env python3
"""
betfair_consensus.py — 09.08.2026 (Lucas): rein LESENDE Zweitmeinung zu jedem Betfair-Signal-Spiel.

Komplett getrennt vom bestehenden betfair_alerts.py / Push — fasst nichts an, sendet nichts. Nimmt die
Betfair-Spiele aus betfair_prices.json, holt zu den gecoverten Ligen die Pinnacle- + Soft-Quoten von
the-odds-api, matcht per Liga + Teamname + Anpfiff, de-viggt zu Wahrscheinlichkeiten, misst die Bewegung
seit dem letzten Lauf und schreibt einen Konsens (Betfair-Geld-Seite vs. Pinnacle vs. Soft) nach
betfair_consensus.json. Nur der neue Radar-Tab liest das.

Der Sinn: „ist das Betfair-Geld schlau?" — wenn Pinnacle die Quote in dieselbe Richtung zieht und die
Soft-Books nachhinken, ist es bestaetigt; ruehrt sich Pinnacle nicht, ist es eher Positionierung/Rauschen.
Obskure Ligen ohne Odds-Anker bleiben ehrlich als „kein Anker" markiert.

Laeuft im betfair.yml nach dem Fetch. Env: ODDS_API_KEY (wie fetch_liga_odds). Netzwerk nur hier — die
reine Match-/De-vig-/Konsens-Logik ist ohne Netz testbar (tests/test_betfair_consensus.py).
"""
from __future__ import annotations
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone

PRICES_FILE    = "betfair_prices.json"
DIRECTION_FILE = "betfair_direction.json"
HIST_FILE      = "betfair_consensus_history.json"   # Pinnacle-Prob-Snapshots je Spiel (fuer die Bewegung)
OUT_FILE       = "betfair_consensus.json"
MONEYMAP_FILE  = "money_map.json"          # 11.08.2026 (Lucas): Money-Map-Feed (Bubble-Cards)
MMLEDGER_FILE  = "money_map_ledger.json"   # Konsens-Signale mitschreiben -> Tracking (ab Tag 1)
MMRECORD_FILE  = "money_map_record.json"   # Trefferquote je Verdikt-Typ (Tracking-Tab)
MM_RESULTS_MIN_H = 3.0                      # Anpfiff so lange her -> Spiel sicher vorbei -> abrechenbar
MM_SINGLE_MIN    = float(os.environ.get("MM_SINGLE_MIN_USD") or 150000)   # 12.08.2026 (Lucas): nur EINE Geldquelle (Betfair ODER Poly) -> braucht so viel Geld, sonst raus. Betfair+Poly = immer rein. Pinnacle zaehlt NICHT (nur Odds-Anker).
MM_STRONG_PCT    = float(os.environ.get("MM_STRONG_PCT") or 55)   # 13.08.2026 (Lucas-Audit): "starke" Konsens/Divergenz erst, wenn BEIDE Geld-Seiten >= so viel % Mehrheit haben (54/46 = Muenzwurf).
try:
    from fetch_betfair_betwatch import fetch_results as _fetch_results  # autoritative Endstaende (Runner)
except Exception:
    _fetch_results = None
ODDS_KEY       = os.environ.get("ODDS_API_KEY") or "16154a94ee84482dcd5a4af88d521d73"   # leerer Secret-String -> App-Key
ODDS_BASE      = "https://api.the-odds-api.com/v4"
REGIONS        = "eu,uk,us"     # Pinnacle liegt in eu; Soft-Books ueber uk/us breiter erfasst
HIST_KEEP      = 24             # letzte n Snapshots je Spiel behalten
# 29.08.2026: 8 Snapshots × ~15 Min = ein Zwei-Stunden-Fenster, und bei Doppelläufen lagen
# zwei davon vier Minuten auseinander. Pinnacle schärft sich über Stunden, nicht über Minuten.
# Gleiche Lösung wie in poly_price_path.py: Mindestabstand statt jeden Lauf mitschreiben.
# 24 × ≥20 Min ≈ 8 Stunden Fenster bei kleinerer Datei als vorher pro Stunde.
SNAP_MIN_ABSTAND_MIN = 20      # näher beieinander liegende Snapshots nicht mitschreiben
MATCH_MIN      = 0.60          # Namens-Match-Schwelle (beide Teams muessen teilen)
# 09.08.2026 (Lucas): EXAKT dieselben Spiele wie die Betfair-Radar-Liste (betfair-radar.js qualifies()):
# tier-basiert — groesster FT-Markt >= 20K (Top/Int) / 15K (Rest) ODER groesster HT-Markt >= 10K / 5K.
# Betwatch liefert schon EUR (EURFX=1), distTotal = Summe der Runner-Vols.
_MK_FT = ("Match Odds", "Over/Under 2.5 Goals", "Over/Under 3.5 Goals", "Both teams to Score?")
_MK_HT = ("Half Time", "First Half Goals 0.5", "First Half Goals 1.5")
_TOP5_RX  = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|french ligue 1|\bmls\b|major league soccer)", re.I)
_TOP5_NEG = re.compile(r"(summer series|friendl|reserve|women|u1[0-9]\b|youth|amateur)", re.I)
_UEFA_RX  = re.compile(r"(champions league|europa league|europa conference|conference league|uefa)", re.I)

# ── Betfair-Liga-Name -> the-odds-api sport_key ──────────────────────────────
# Aus dem 09.08.2026-Abgleich (Betfair-Feed × the-odds-api /sports). Nur wo eine aktive Odds-Liga
# existiert; alles andere -> kein Anker. Weitere Ligen greifen automatisch, sobald ihr exakter
# Betfair-Ligastring hier steht (Rest ist nur Nachschlagen — falscher/fehlender Key = schadet nicht).
LEAGUE_ODDS_KEY = {
    # aus dem echten Feed bestaetigt:
    "Brazilian Serie A":            "soccer_brazil_campeonato",
    "Brazilian Serie B":            "soccer_brazil_serie_b",
    "Portuguese Primeira Liga":     "soccer_portugal_primeira_liga",
    "Argentinian Primera Division": "soccer_argentina_primera_division",
    "Austrian Bundesliga":          "soccer_austria_bundesliga",
    "Chilean Primera Division":     "soccer_chile_campeonato",
    "Belgian Pro League":           "soccer_belgium_first_div",
    "Finnish Veikkausliiga":        "soccer_finland_veikkausliiga",
    "Italian Coppa Italia":         "soccer_italy_coppa_italia",
    "Norwegian Eliteserien":        "soccer_norway_eliteserien",
    "Polish Ekstraklasa":           "soccer_poland_ekstraklasa",
    "German 3 Liga":                "soccer_germany_liga3",
    "Danish Superliga":             "soccer_denmark_superliga",
    "English Football League Cup":  "soccer_england_efl_cup",
    "Irish Premier Division":       "soccer_league_of_ireland",
    "Scottish Premiership":         "soccer_spl",
    # Top-5 + MLS (Betfair-Strings aus den Alerts bestaetigt):
    "English Premier League":       "soccer_epl",
    "Spanish La Liga":              "soccer_spain_la_liga",
    "German Bundesliga":            "soccer_germany_bundesliga",
    "Italian Serie A":              "soccer_italy_serie_a",
    "French Ligue 1":               "soccer_france_ligue_one",
    "Major League Soccer":          "soccer_usa_mls",
    # 13.08.2026 (Lucas): internationale Klub-Wettbewerbe (im Feed aktiv). Falscher/fehlender Key schadet
    # nicht (dann bleibt der Anker leer). UEFA-Gruppenphase kann hier genauso ergaenzt werden, sobald die
    # Betfair-Ligastrings feststehen (soccer_uefa_champs_league / _europa_league / _europa_conference_league).
    "CONMEBOL Copa Libertadores":   "soccer_conmebol_copa_libertadores",
    "CONMEBOL Copa Sudamericana":   "soccer_conmebol_copa_sudamericana",
    # 14.08.2026 (Lucas): grosse Ligen, die Betfair global zeigt, aber uns fehlten. TheOddsAPI-Keys
    # gegen die-odds-api-Doku verifiziert; Betfair-Strings aus dem echten Feed. In Saison ab ~August.
    "Turkish Super League":         "soccer_turkey_super_league",
    "Dutch Eredivisie":             "soccer_netherlands_eredivisie",
    "English Sky Bet Championship": "soccer_efl_champ",
    "German Bundesliga 2":          "soccer_germany_bundesliga2",
    "Swedish Allsvenskan":          "soccer_sweden_allsvenskan",
    "Saudi Professional League":    "soccer_saudi_arabia_pro_league",
}


# ── I/O ──────────────────────────────────────────────────────────────────────
def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _dump(path, obj):
    try:
        json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception as e:
        print("Schreibfehler %s: %s" % (path, e))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Namens-Normalisierung + Match (die riskante, darum voll getestete Stelle) ──
# NUR klare Rechtsform-/Verbindungs-Token — KEINE unterscheidenden Woerter (sonst kollabieren
# „Manchester United" und „Manchester City" beide auf „manchester" -> Fehl-Match). Der Liga- +
# Anpfiff-Filter faengt den Rest ab.
_NOISE = {
    "fc", "cf", "sc", "afc", "cd", "ac", "if", "fk", "fs", "bk", "ff", "sk", "ud",
    "cfc", "sad", "bsc", "club", "de", "the", "calcio", "aj", "ogc", "rcd", "ssc",
}


# 13.08.2026 (Lucas-Audit): Abkuerzungs-Aliasse — Betfair kuerzt Klubs anders ab als Poly ("Man Utd"
# <-> "Manchester United", "Wolves" <-> "Wolverhampton"). Ohne diese Expansion teilen sie 0 Tokens und
# der ganze Poly-Eintrag fiel still raus. NUR eindeutige, KEINE unterscheidenden Tokens (united/city bleiben
# getrennt, weil sie separat gemappt/erhalten werden).
_ALIAS = {
    "utd": "united", "man": "manchester", "wolves": "wolverhampton",
    "spurs": "tottenham", "sheff": "sheffield", "nottm": "nottingham",
    "wba": "westbrom", "qpr": "queensparkrangers",
}


def _norm(s) -> list:
    """Team-Name -> Liste signifikanter Tokens (klein, akzentfrei, ohne Rausch-Tokens/Zahlen)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return [_ALIAS.get(t, t) for t in s.split() if t and t not in _NOISE and not t.isdigit()]


def _name_score(a, b) -> float:
    """0..1: geteilte signifikante Tokens / groessere Tokenmenge. 0 = kein gemeinsames Kern-Token."""
    A, B = set(_norm(a)), set(_norm(b))
    if not A or not B:
        return 0.0
    inter = A & B
    if not inter:
        return 0.0
    return len(inter) / max(len(A), len(B))


def _median(xs):
    """Ausreisser-fester Konsens: Median einer Zahlenliste (leere/ungueltige Liste -> None)."""
    ys = sorted(v for v in xs if isinstance(v, (int, float)))
    n = len(ys)
    if n == 0:
        return None
    mid = n // 2
    return ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2.0


def _devig3(h, d, a):
    """Drei-Weg-Quoten (dezimal) -> de-viggte Wahrscheinlichkeiten [heim, remis, auswaerts]."""
    try:
        inv = [1.0 / float(h), 1.0 / float(d), 1.0 / float(a)]
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = sum(inv)
    if s <= 0:
        return None
    return [x / s for x in inv]


def _devig2(over, under):
    """Zwei-Weg-Quoten (Over/Under, dezimal) -> de-viggte [pOver, pUnder]."""
    try:
        io, iu = 1.0 / float(over), 1.0 / float(under)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    tot = io + iu
    if tot <= 0:
        return None
    return [io / tot, iu / tot]


def _fmt_line(pt):
    """Totals-Punkt (2.5) -> Label-Schluessel passend zu Betfair ('2.5'). 3.0 -> '3'."""
    try:
        return ("%g" % float(pt))
    except (TypeError, ValueError):
        return None


def parse_event(ev) -> dict:
    """the-odds-api-Event -> Probs (de-viggt) UND rohe Dezimal-Quoten je Quelle, [heim, remis, auswaerts]."""
    home, away = ev.get("home_team"), ev.get("away_team")
    pinn, pinn_odds, soft_p, soft_o = None, None, [], []
    for bk in ev.get("bookmakers") or []:
        h = d = a = None
        for mkt in bk.get("markets") or []:
            if mkt.get("key") != "h2h":
                continue
            for oc in mkt.get("outcomes") or []:
                nm, pr = oc.get("name"), oc.get("price")
                if nm == home:
                    h = pr
                elif nm == away:
                    a = pr
                elif nm and str(nm).lower() == "draw":
                    d = pr
        probs = _devig3(h, d, a) if (h and d and a) else None
        if not probs:
            continue
        odds = [float(h), float(d), float(a)]
        if bk.get("key") == "pinnacle":
            pinn, pinn_odds = probs, odds
        else:
            soft_p.append(probs)
            soft_o.append(odds)
    soft = [sum(x[i] for x in soft_p) / len(soft_p) for i in range(3)] if soft_p else None
    # 11.08.2026 (Lucas): Median statt Mittelwert der rohen Dezimalquoten -- bei Aussenseitern zieht ein
    # einzelnes Buch mit irrer (oft live-traeger) Quote den arithmetischen Schnitt hoch und laesst die
    # Anzeige von Scan zu Scan springen (11 -> 34). Der Median ist ausreisser-fest.
    soft_odds = [_median([x[i] for x in soft_o]) for i in range(3)] if soft_o else None
    return {"home": home, "away": away, "commence": ev.get("commence_time"),
            "pinn": pinn, "soft": soft, "pinnOdds": pinn_odds, "softOdds": soft_odds, "nSoft": len(soft_p)}


def parse_totals(ev) -> dict:
    """the-odds-api-Event (regions=eu, markets=totals+alternate_totals) -> Pinnacle-Over/Under je Linie,
    de-viggt zu fairen Wahrscheinlichkeiten. Nur Pinnacle (der Anker). Rueckgabe wie parse_event
    (home/away/commence) plus 'totals': {lineStr: {overFair,underFair,overOdd,underOdd}}."""
    home, away = ev.get("home_team"), ev.get("away_team")
    raw = {}
    for bk in ev.get("bookmakers") or []:
        if bk.get("key") != "pinnacle":
            continue
        for mkt in bk.get("markets") or []:
            if mkt.get("key") not in ("totals", "alternate_totals"):
                continue
            for oc in mkt.get("outcomes") or []:
                pt, nm, pr = oc.get("point"), oc.get("name"), oc.get("price")
                key = _fmt_line(pt)
                if key is None or nm is None or not pr:
                    continue
                slot = raw.setdefault(key, {})
                side = str(nm).lower()
                if side.startswith("over"):
                    slot["overOdd"] = float(pr)
                elif side.startswith("under"):
                    slot["underOdd"] = float(pr)
        break
    totals = {}
    for key, v in raw.items():
        o, u = v.get("overOdd"), v.get("underOdd")
        fair = _devig2(o, u)
        if not fair:
            continue
        totals[key] = {"overFair": _r(fair[0]), "underFair": _r(fair[1]),
                       "overOdd": round(o, 2), "underOdd": round(u, 2)}
    return {"home": home, "away": away, "commence": ev.get("commence_time"), "totals": totals}


def _flip(ev) -> dict:
    """Event mit vertauschten Teams (falls Heim/Auswaerts zwischen den Quellen gedreht sind)."""
    def rev(p):
        return [p[2], p[1], p[0]] if p else None
    return {"home": ev["away"], "away": ev["home"], "commence": ev.get("commence"),
            "pinn": rev(ev.get("pinn")), "soft": rev(ev.get("soft")),
            "pinnOdds": rev(ev.get("pinnOdds")), "softOdds": rev(ev.get("softOdds")), "nSoft": ev.get("nSoft"),
            "totals": ev.get("totals")}


# ── Polymarket (globaler Broad-Scan: poly_money_broad_close.json) ─────────────
_POLY_NON_TEAM = {"yes", "no", "draw", "the draw", "tie", "over", "under"}


def _poly_key_for(name, keys):
    """Bester Preis-Schluessel (Team-Name) fuer ein Team; None wenn nichts ordentlich matcht."""
    best, bsc = None, 0.49
    for k in keys:
        if str(k).lower() in _POLY_NON_TEAM:
            continue
        sc = _name_score(name, k)
        if sc > bsc:
            best, bsc = k, sc
    return best


def _best_poly_entry(m, poly_entries):
    """Bester Poly-Eintrag zum Betfair-Spiel -> (pe, hk, ak) oder None. Beide Teams muessen matchen."""
    home, away = m.get("home"), m.get("away")
    best, bsc = None, 0.99
    for pe in poly_entries:
        keys = list((pe.get("prices") or {}).keys())
        hk, ak = _poly_key_for(home, keys), _poly_key_for(away, keys)
        # 12.08.2026 (Lucas): eine Seite matcht stark, die andere ist bei Poly anders abgekuerzt
        # (Betfair "Paris St-G" vs Poly "Paris Saint-Germain" -> nur 0.33, unter der 0.49-Schwelle).
        # Bei genau 2 Team-Ausgaengen die fehlende Seite als den Gegner ableiten -- aber nur, wenn sie
        # mindestens EIN Token teilt (schuetzt vor Falsch-Paarung, wenn nur ein Team zufaellig gleich heisst).
        team_keys = [k for k in keys if str(k).lower() not in _POLY_NON_TEAM]
        if len(team_keys) == 2:
            if hk and not ak:
                cand = next((k for k in team_keys if k != hk), None)
                if cand and _name_score(away, cand) > 0:
                    ak = cand
            elif ak and not hk:
                cand = next((k for k in team_keys if k != ak), None)
                if cand and _name_score(home, cand) > 0:
                    hk = cand
        if hk and ak and hk != ak:
            sc = _name_score(home, hk) + _name_score(away, ak)
            if sc > bsc:
                best, bsc = (pe, hk, ak), sc
    return best


def match_poly(m, ms, poly_entries):
    """Poly-Markt zum Betfair-Spiel: {vol, odd (fuer die Geld-Seite, None wenn Poly die Seite nicht hat),
    sharePct}. None wenn Poly den Markt nicht hat. Beide Teams muessen matchen."""
    best = _best_poly_entry(m, poly_entries)
    if not best:
        return None
    pe, hk, ak = best
    prices, shares = pe.get("prices") or {}, pe.get("shares") or {}
    side = ms.get("side") if ms else None
    if side == "home":
        key = hk
    elif side == "away":
        key = ak
    else:
        key = next((k for k in prices if str(k).lower() in ("draw", "the draw", "tie")), None)
    price = prices.get(key) if key else None
    tot = sum(v for v in shares.values() if isinstance(v, (int, float))) if shares else 0
    share_pct = round(shares.get(key) / tot * 100) if (key and tot and isinstance(shares.get(key), (int, float))) else None
    return {"vol": round(pe.get("totalUsd") or 0),
            "odd": round(1.0 / price, 2) if (isinstance(price, (int, float)) and price > 0) else None,
            "sharePct": share_pct}



def pick_poly(m, ms, is_live, poly_close, poly_live, poly_upcoming):
    """Poly-Quelle je Phase (18.08.2026, Lucas): LAUFENDES Spiel -> frische Live-Poly ZUERST (sonst
    zeigt der Terminal auf einem Live-Spiel die eingefrorene Pre-Match-Quote aus dem Close-Pool).
    Nicht-live: Close (<=3h Freeze, mit Holder-Shares) zuerst, dann Upcoming (weit vor Anpfiff, Preis+Vol).
    Rein additiv/reine Auswahl-Logik, ohne Netz testbar."""
    poly = match_poly(m, ms, poly_live) if is_live else None
    if poly is None:
        poly = match_poly(m, ms, poly_close)
    if poly is None:
        poly = match_poly(m, ms, poly_upcoming)
    return poly

def match_event(m, evs):
    """Bestes Odds-Event zum Betfair-Spiel, orientiert auf dessen Heim/Auswaerts. None wenn kein Match."""
    home, away = m.get("home"), m.get("away")
    best, best_sc = None, MATCH_MIN
    for ev in evs:
        d = _name_score(home, ev["home"]) + _name_score(away, ev["away"])
        s = _name_score(home, ev["away"]) + _name_score(away, ev["home"])
        if d >= s and _name_score(home, ev["home"]) > 0 and _name_score(away, ev["away"]) > 0:
            sc, cand = d, ev
        elif s > d and _name_score(home, ev["away"]) > 0 and _name_score(away, ev["home"]) > 0:
            sc, cand = s, _flip(ev)
        else:
            continue
        if sc > best_sc:
            best, best_sc = cand, sc
    return best


# ── Betfair-Geld-Seite + Richtung ────────────────────────────────────────────
def _is_top_tier(m) -> bool:
    lg = str(m.get("league") or "")
    if _TOP5_RX.search(lg) and not _TOP5_NEG.search(lg):
        return True
    cc = str(m.get("country") or "")
    return bool(_UEFA_RX.search(lg)) or bool(re.match(r"^(int|international|eu|europe)$", cc, re.I))


def qualifies_radar(m) -> bool:
    """EXAKT die Radar-Listen-Schwelle (betfair-radar.js qualifies): groesster FT-Markt >= tier-Schwelle
    ODER groesster HT-Markt >= tier-Schwelle. So zeigt der Konsens genau dieselben Spiele wie die Liste."""
    mk = m.get("markets") or {}

    def vol(name):
        return sum((r.get("vol") or 0.0) for r in ((mk.get(name) or {}).get("runners") or []))

    top = _is_top_tier(m)
    ft_thr, ht_thr = (20000.0, 10000.0) if top else (15000.0, 5000.0)
    ft_max = max([vol(n) for n in _MK_FT] or [0.0])
    ht_max = max([vol(n) for n in _MK_HT] or [0.0])
    return ft_max >= ft_thr or ht_max >= ht_thr


def money_side(m):
    """Seite mit dem meisten gematchten 1X2-Geld: {side home/draw/away, name, share, odd, totVol}."""
    mk = (m.get("markets") or {}).get("Match Odds")
    rs = (mk or {}).get("runners") or []
    if not rs:
        return None
    tot = sum((r.get("vol") or 0.0) for r in rs) or 1.0
    lead = max(rs, key=lambda r: (r.get("vol") or 0.0))
    name = lead.get("name")
    # 22.08.2026 (Lucas: „Kohle sieht aus wie Home, liegt aber 90% auf Alkmaar"): Betfair liefert den
    # Ausgangsnamen oft anders formatiert als den Teamnamen ("Az Alkmaar" vs "AZ Alkmaar") -> exaktes
    # == schlug fehl und fiel in den else-Zweig -> falsche Seite "home". Jetzt Fuzzy-Match (_name_score)
    # gegen BEIDE Teams, stärkere Seite gewinnt (Draw separat).
    nm = str(name or "")
    if nm.strip().lower() in ("the draw", "draw", "tie"):
        side = "draw"
    else:
        sh = _name_score(nm, m.get("home") or "")
        sa = _name_score(nm, m.get("away") or "")
        side = "away" if sa > sh else "home"
    return {"side": side, "name": name, "share": (lead.get("vol") or 0.0) / tot,
            "odd": lead.get("odd"), "totVol": tot}


def _money_dir(direction, m, ms):
    """Back/Lay-Richtung der Geld-Seite aus betfair_direction.json (in=Back, out=driftet)."""
    if not (direction and ms):
        return None
    try:
        e = ((direction.get(str(m.get("matchId"))) or {}).get("Match Odds") or {}).get(ms.get("name"))
        return (e or {}).get("dir")
    except Exception:
        return None


def _fav(probs):
    i = max(range(3), key=lambda k: probs[k])
    return ("home", "draw", "away")[i]


def _r(x):
    return round(float(x), 4) if isinstance(x, (int, float)) else None


def poly_fav(m, poly_entries):
    """11.08.2026 (Lucas Money-Map): Polys EIGENE Geld-Favoriten-Seite (nicht die Betfair-Seite -> fuer
    Divergenz-Erkennung): {side, name, sharePct, usd} oder None. REIN/testbar."""
    best = _best_poly_entry(m, poly_entries)
    if not best:
        return None
    pe, hk, ak = best
    prices, shares = pe.get("prices") or {}, pe.get("shares") or {}
    dk = next((k for k in prices if str(k).lower() in ("draw", "the draw", "tie")), None)
    cand = [("home", hk), ("away", ak)] + ([("draw", dk)] if dk else [])
    tot = sum(v for v in shares.values() if isinstance(v, (int, float))) or 0
    if tot > 0:
        bside, bsh, bname = None, -1, None
        for side, key in cand:
            sh = shares.get(key) if key else None
            if isinstance(sh, (int, float)) and sh > bsh:
                bside, bsh, bname = side, sh, key
        if bside is None:
            return None
        return {"side": bside, "name": bname, "sharePct": round(bsh / tot * 100),
                "usd": round(pe.get("totalUsd") or 0), "src": pe.get("src") or "close"}
    # 12.08.2026 (Lucas Money-Map): keine Shares (upcoming-Erfassung, weit vor Anpfiff) -> Favorit aus dem
    # PREIS (auf Poly = geldgewichtete Wahrscheinlichkeit). sharePct = Preis*100, usd = Markt-Volumen.
    bside, bp, bname = None, -1.0, None
    for side, key in cand:
        p = prices.get(key) if key else None
        if isinstance(p, (int, float)) and p > bp:
            bside, bp, bname = side, p, key
    if bside is None or bp <= 0:
        return None
    return {"side": bside, "name": bname, "sharePct": round(bp * 100),
            "usd": round(pe.get("totalUsd") or 0), "src": pe.get("src") or "upcoming"}


def _poly_has_any_overlap(m, pools) -> bool:
    """13.08.2026 (Lucas-Audit): Liegt im Poly-Pool ueberhaupt ein Kandidat, der mit Heim ODER Auswaerts
    mind. ein Token teilt? Fuer den Namens-Match-Miss-Zaehler: Betfair-Geld da, poly=None, aber ein
    plausibler Poly-Markt existiert -> wahrscheinlich eine (Rest-)Abkuerzungs-Luecke. REIN."""
    home, away = m.get("home"), m.get("away")
    for pe in (pools or []):
        for k in ((pe.get("prices") or {}).keys()):
            if str(k).lower() in _POLY_NON_TEAM:
                continue
            if _name_score(home, k) > 0 or _name_score(away, k) > 0:
                return True
    return False


def _poly_ist_geld(pl) -> bool:
    """Zaehlt diese Poly-Seite als GELDQUELLE — oder ist sie nur ein Preis?

    30.08.2026 (Lucas-Checkup der Uebersicht): _mm_money_ok schliesst src=="scan" seit dem
    23.08. bewusst aus (ein Scan-Poly liefert nur den fairen Preis, kein echtes Geld) und das
    Frontend beschriftet ihn als „Poly · Preis (duenn)". nSources, mmStrong und der
    no_anchor-Rueckfall haben diese Entscheidung nie mitbekommen und zaehlten ihn voll mit.
    Folge auf der Uebersicht: Chelsea–Brighton stand als „✅ knapp einig · 3 / 3" da — die
    dritte Quelle waren $1.410 neben €328.000 Betfair-Geld. Napoli–Como genauso mit $1.787.
    Eine Bestaetigung, die aus einem einzelnen Ticket besteht, ist keine.

    EINE Definition, hier. _mm_money_ok ruft sie ebenfalls auf."""
    if not pl:
        return False
    if pl.get("src") == "scan":
        return False
    try:
        return float(pl.get("usd") or 0) > 0
    except (TypeError, ValueError):
        return False


def money_map_row(g, pf):
    """11.08.2026 (Lucas Money-Map): build_game-Output g + poly_fav pf -> bubble-fertige Zeile.
    Betfair-Geld (EUR) + Poly-Geld (USD, eigene Seite) + Pinnacle-Probs + Verdikt + nSources. REIN/testbar."""
    bf_side = g.get("moneySide")
    pinn = g.get("pinn")
    row = {"matchId": g.get("matchId"), "home": g.get("home"), "away": g.get("away"),
           "league": g.get("league"), "live": g.get("live"), "kickoff": g.get("kickoff"),
           "verdict": g.get("verdict"),
           # 01.09.2026 (Lucas: „was macht das besser als die Money Map?"). Beim Vergleich fiel auf:
           # die Map schrieb `moneyWin` mit, aber NIE eine Quote. Ihre 81% Trefferquote bei „stark"
           # sagen deshalb nichts ueber Geld — das Geld liegt auf Favoriten, eine hohe Trefferquote
           # ist dort der Normalfall. Ohne Preis ist die Map nicht widerlegbar, und was nicht
           # widerlegbar ist, belegt auch nichts. `moneyOdd` gab es in build_game() bereits, sie kam
           # nur nie hier an.
           "betfair": ({"side": bf_side, "name": g.get("moneyName"),
                        "sharePct": g.get("moneySharePct"), "eur": g.get("totVol"),
                        "odd": g.get("moneyOdd")} if bf_side else None),
           "poly": ({"side": pf["side"], "name": pf["name"], "sharePct": pf["sharePct"], "usd": pf["usd"],
                     "src": pf.get("src")}
                    if pf else None),
           "pinn": ({"fav": pinn.get("fav"), "home": pinn.get("home"), "draw": pinn.get("draw"),
                     "away": pinn.get("away")} if pinn else None)}
    # Money-Map-Verdikt auch OHNE Pinnacle/Soft-Anker (11.08.2026, Lucas): die Map lebt vom Geld,
    # Pinnacle ist nur Anker. Fehlt der Anker (z.B. UEFA Super Cup / Pokal - nicht in den 22 Odds-Ligen),
    # aber Betfair UND Poly liegen vor, dann Konsens/Divergenz aus Betfair-Seite vs Poly-Seite ableiten
    # (2/3, "ehrlich"). Nur Betfair allein bleibt no_anchor (nichts zum Vergleichen).
    _pl_geld = _poly_ist_geld(row["poly"])
    if row["verdict"] == "no_anchor" and row["betfair"] and _pl_geld:
        row["verdict"] = "konsens" if row["betfair"]["side"] == row["poly"]["side"] else "uneinig"
    # 13.08.2026 (Lucas-Audit): Magnitude. "stark" nur, wenn BEIDE Geld-Seiten eine klare Mehrheit
    # (>= MM_STRONG_PCT) zeigen -> das Frontend daempft schwache 54/46-Faelle (kein Signal).
    _bfm = (row.get("betfair") or {}).get("sharePct") or 0
    _plm = (row.get("poly") or {}).get("sharePct") or 0
    row["mmStrong"] = bool(row.get("betfair") and _pl_geld and _bfm >= MM_STRONG_PCT and _plm >= MM_STRONG_PCT)
    # 30.08.2026: ein reiner Scan-Preis fuellt die Poly-SEITE (er bleibt sichtbar), zaehlt aber
    # nicht als Quelle. `polyGeld` sagt dem Frontend, warum aus 3 eine 2 wurde.
    row["polyGeld"] = _pl_geld
    row["nSources"] = sum(1 for x in (row["betfair"], (row["poly"] if _pl_geld else None), row["pinn"]) if x)
    return row


def _mm_money_ok(row, single_min=MM_SINGLE_MIN):
    """12.08.2026 (Lucas): die Money-Map ist ein VERGLEICH -> sie braucht echtes Geld auf zwei
    Seiten. Geldquellen sind nur Betfair (EUR) + Poly (USD); Pinnacle ist bloss der Odds-Anker,
    zaehlt hier NICHT. Regel: Betfair UND Poly -> immer rein. Nur eine Quelle -> nur wenn >= single_min
    (Marquee-Spiel wie ein UEFA-Super-Cup). Gar kein Geld -> raus. Killt duenne Einzelquellen-Spiele
    (U19/Minnows), ohne gute Divergenz-Faelle mit kleinem Betfair aber echtem Poly zu opfern. REIN."""
    bf = float((row.get("betfair") or {}).get("eur") or 0)
    _pl = row.get("poly") or {}
    pl = float(_pl.get("usd") or 0)
    # 23.08.2026 (Lucas): ein Scan-Poly (nur fairer Preis, ~kein echtes Geld) füllt die Poly-SEITE,
    # zählt aber NICHT als Geldquelle — sonst würde ein dünner Preis einen schwachen Betfair-Row retten.
    pl_money = pl if _poly_ist_geld(_pl) else 0.0
    n_money = (1 if bf > 0 else 0) + (1 if pl_money > 0 else 0)
    if n_money >= 2:
        return True
    if n_money == 1:
        return max(bf, pl) >= single_min
    return False


def update_mm_ledger(prev, rows, now=None, keep=2000):
    """11.08.2026 (Lucas Money-Map Tracking): Konsens-Signale mitschreiben (upsert je matchId, solange
    pending) -> Basis fuers spaetere Settlement (gewann die Konsens-Seite?). REIN/testbar."""
    now = now or _now_iso()
    led = {}
    for e in (prev or []):
        if isinstance(e, dict) and e.get("matchId"):
            led[e["matchId"]] = dict(e)
    for r in rows or []:
        mid = r.get("matchId")
        if not mid or r.get("verdict") in (None, "no_anchor"):
            continue
        e = led.get(mid)
        if e and e.get("status") not in (None, "pending"):
            continue                              # schon abgerechnet -> nicht ueberschreiben
        bf, pinn, poly = r.get("betfair") or {}, r.get("pinn") or {}, r.get("poly") or {}
        # ZWEI Preise, und zwar bewusst:
        #   moneyOddFirst — die Quote, als die Zeile ZUERST auftauchte. Nur die haette man nehmen
        #                   koennen; sie ist die ehrliche Basis fuers ROI (wie killer.haltePreis).
        #   moneyOddLast  — die zuletzt gesehene Quote vor Anpfiff. Erst sie macht CLV moeglich,
        #                   und CLV ist bei kleinem n belastbarer als ROI.
        # Die erste wird NIE ueberschrieben, die zweite bei jedem Lauf.
        _odd = bf.get("odd")
        _first = (e or {}).get("moneyOddFirst")
        _alte_seite = (e or {}).get("moneySide")
        if _alte_seite is not None and _alte_seite != bf.get("side"):
            _first = None                          # Seite gewechselt -> das ist eine ANDERE Wette,
                                                   # der alte Einstiegspreis gilt dafuer nicht
        led[mid] = {"matchId": mid, "home": r.get("home"), "away": r.get("away"), "league": r.get("league"),
                    "kickoff": r.get("kickoff"), "verdict": r.get("verdict"), "nSources": r.get("nSources"),
                    "moneySide": bf.get("side"), "moneyName": bf.get("name"),
                    "moneyOddFirst": _first if _first is not None else _odd,
                    "moneyOddLast": _odd if _odd is not None else (e or {}).get("moneyOddLast"),
                    "pinnFav": pinn.get("fav"), "polySide": poly.get("side"), "mmStrong": r.get("mmStrong"),
                    "firstSeen": (e or {}).get("firstSeen") or now, "updatedAt": now, "status": "pending"}
    return list(led.values())[-keep:]


def _winner_1x2(g1, g2):
    """1X2-Gewinner aus dem Endstand [heim, ausw] -> home/draw/away oder None."""
    if not isinstance(g1, int) or not isinstance(g2, int):
        return None
    return "home" if g1 > g2 else "away" if g2 > g1 else "draw"


def _feed_finished_map(prices):
    """13.08.2026 (Lucas): matchId -> [goal_v1, goal_v2] fuer im Live-Feed als 'finished' markierte Spiele.
    Autoritativer Endstand aus betfair_prices.json — DIESELBE Quelle, aus der der Track-Record abrechnet.
    Kein Netz. Greift, solange das Spiel noch im Betwatch-Fenster (~26h) steht."""
    out = {}
    for m in ((prices or {}).get("matches") or []):
        if not isinstance(m, dict):
            continue
        li = m.get("liveInfo") or {}
        if li.get("finished") and li.get("goal_v1") is not None and li.get("goal_v2") is not None:
            out[str(m.get("matchId"))] = [li.get("goal_v1"), li.get("goal_v2")]
    return out


def settle_mm_ledger(ledger, results_fetch=None, now=None, min_h=None, prices=None):
    """11.08.2026 (Lucas Money-Map Tracking): pending-Konsens-Eintraege gegen den echten Endstand
    abrechnen. Gewann die Betfair-Geld-Seite (moneySide) -> status won/lost; zusaetzlich pinnWin.
    13.08.2026 (Lucas "tracking funktioniert nicht"): ZWEI Quellen wie der Track-Record —
      1) Live-Feed 'finished' (betfair_prices.json, KEIN Netz) — greift, solange das Spiel im Fenster ist.
      2) fetch_results (autoritativer Endpoint) fuer aus dem Feed gefallene Spiele (braucht BETWATCH_KEY).
    Vorher lief NUR (2); ohne Key im Konsens-Step blieb jeder Eintrag fuer immer pending. REIN/testbar."""
    from datetime import timedelta
    now = now or datetime.now(timezone.utc)
    min_h = MM_RESULTS_MIN_H if min_h is None else min_h
    ledger = [dict(e) for e in (ledger or []) if isinstance(e, dict)]

    def _apply(e, g1, g2):
        w = _winner_1x2(g1, g2)
        if w is None:
            return
        e["ftScore"] = [g1, g2]
        e["winner"] = w
        e["moneyWin"] = (e.get("moneySide") == w)
        if e.get("polySide"):
            e["polyWin"] = (e.get("polySide") == w)
        if e.get("pinnFav"):
            e["pinnWin"] = (e.get("pinnFav") == w)
        e["status"] = "won" if e["moneyWin"] else "lost"
        e["settledAt"] = now.isoformat()

    # 1) Endstand aus dem Live-Feed (kein Netz) — bewaehrter Track-Record-Pfad.
    feed = _feed_finished_map(prices)
    for e in ledger:
        if e.get("status") != "pending":
            continue
        sc = feed.get(str(e.get("matchId")))
        if sc and sc[0] is not None and sc[1] is not None:
            _apply(e, sc[0], sc[1])

    # 2) Autoritativer Endpoint fuer den Rest (aus dem Feed gefallen). Braucht BETWATCH_KEY im Job.
    if results_fetch is not None:
        cutoff = now - timedelta(hours=min_h)
        stale = []
        for e in ledger:
            if e.get("status") != "pending":
                continue
            try:
                kt = datetime.fromisoformat(str(e.get("kickoff")).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                kt = None
            if kt is not None and kt < cutoff:
                stale.append(str(e.get("matchId")))
        if stale:
            res = results_fetch(stale) or {}
            for e in ledger:
                if e.get("status") != "pending":
                    continue
                r = res.get(str(e.get("matchId"))) if isinstance(res, dict) else None
                if not isinstance(r, dict) or not r.get("finished") or r.get("goal_v1") is None:
                    continue
                _apply(e, r.get("goal_v1"), r.get("goal_v2"))
    return ledger


def mm_summary(ledger, now=None, recent_keep=40):
    """13.08.2026 (Lucas: mehr Tracking): Trefferquote je Verdikt (folgt man der Betfair-Geld-Seite) PLUS
    Poly-Quote (folgt man der Poly-Seite) und Pinnacle-Favorit; je Liga; Divergenz-Duell (Betfair vs Poly
    wenn uneinig, wer trifft oefter?); und die letzten abgerechneten Spiele. Poly/Duell werden direkt aus
    polySide vs Endstand berechnet -> funktioniert auch fuer schon abgerechnete Alt-Zeilen. REIN/testbar."""
    buckets, leagues, strength = {}, {}, {}
    gn = gw = 0
    # 01.09.2026: Trefferquote UND Rendite — und beide streng getrennt gezaehlt. Zeilen aus der Zeit
    # vor dem 01.09. tragen keine Quote; sie zaehlen in die Trefferquote, aber NICHT in den ROI.
    # Deshalb ein eigenes `nRoi` je Eimer: eine Rendite aus 12 von 900 Zeilen darf nicht aussehen
    # wie eine aus 900.
    grend, gclv = [], []

    def _leer():
        return {"n": 0, "wins": 0, "polyN": 0, "polyWins": 0, "pinnN": 0, "pinnWins": 0,
                "rend": [], "clv": []}

    def _geld(b, e):
        """Rendite zum EINSTIEGSPREIS (nur der war nehmbar) und CLV Einstieg→letzte Quote."""
        o1, o2 = e.get("moneyOddFirst"), e.get("moneyOddLast")
        if isinstance(o1, (int, float)) and o1 > 1:
            b["rend"].append((o1 - 1.0) if e.get("moneyWin") else -1.0)
            if isinstance(o2, (int, float)) and o2 > 1:
                b["clv"].append(round((1.0 / o2 - 1.0 / o1) * 100.0, 2))

    settled = [e for e in (ledger or []) if isinstance(e, dict) and e.get("status") in ("won", "lost")]
    for e in settled:
        w = e.get("winner")
        v = e.get("verdict") or "?"
        b = buckets.setdefault(v, _leer())
        b["n"] += 1
        b["wins"] += 1 if e.get("moneyWin") else 0
        _geld(b, e)
        ps = e.get("polySide")
        if ps and w:
            b["polyN"] += 1
            b["polyWins"] += 1 if ps == w else 0
        if e.get("pinnWin") is not None:
            b["pinnN"] += 1
            b["pinnWins"] += 1 if e.get("pinnWin") else 0
        L = leagues.setdefault(e.get("league") or "?", {"n": 0, "wins": 0})
        L["n"] += 1
        L["wins"] += 1 if e.get("moneyWin") else 0
        st = e.get("mmStrong")
        if st is not None:
            SB = strength.setdefault(bool(st), {"n": 0, "wins": 0, "rend": [], "clv": []})
            SB["n"] += 1
            SB["wins"] += 1 if e.get("moneyWin") else 0
            _geld(SB, e)
        gn += 1
        gw += 1 if e.get("moneyWin") else 0
        o1, o2 = e.get("moneyOddFirst"), e.get("moneyOddLast")
        if isinstance(o1, (int, float)) and o1 > 1:
            grend.append((o1 - 1.0) if e.get("moneyWin") else -1.0)
            if isinstance(o2, (int, float)) and o2 > 1:
                gclv.append(round((1.0 / o2 - 1.0 / o1) * 100.0, 2))

    def _rate(x, n):
        return round(x / n, 4) if n else None

    def _ug(v, z=1.645):
        """Einseitige 95%-Untergrenze. Derselbe Richter wie im Freigabe-Register und im Killer —
        ein Punktschaetzer ist kein Beleg ([[feedback_punktschaetzer_kein_beleg]])."""
        n = len(v)
        if n < 2:
            return None
        m = sum(v) / n
        var = sum((x - m) ** 2 for x in v) / (n - 1)
        return round(m - z * (var ** 0.5) / (n ** 0.5), 4)

    def _geldfin(b):
        r, c = b.get("rend") or [], b.get("clv") or []
        return {"nRoi": len(r),
                "roi": round(sum(r) / len(r), 4) if r else None,
                "roiLb": _ug(r),
                "nClv": len(c),
                "clv": round(sum(c) / len(c), 2) if c else None,
                "clvLb": _ug(c)}

    def _fin(b):
        d = {"n": b["n"], "wins": b["wins"], "hitRate": _rate(b["wins"], b["n"]),
             "polyN": b["polyN"], "polyWins": b["polyWins"], "polyHitRate": _rate(b["polyWins"], b["polyN"]),
             "pinnN": b["pinnN"], "pinnHitRate": _rate(b["pinnWins"], b["pinnN"])}
        d.update(_geldfin(b))
        return d

    def _sfin(s):
        if not s:
            return None
        d = {"n": s["n"], "wins": s["wins"], "hitRate": _rate(s["wins"], s["n"])}
        d.update(_geldfin(s))
        return d

    dv = buckets.get("uneinig") or {"n": 0, "wins": 0, "polyN": 0, "polyWins": 0}
    divergence = {"n": dv["n"], "betfairWins": dv["wins"], "betfairRate": _rate(dv["wins"], dv["n"]),
                  "polyN": dv["polyN"], "polyWins": dv["polyWins"], "polyRate": _rate(dv["polyWins"], dv["polyN"])}

    by_league = dict(sorted(
        ((lg, {"n": L["n"], "wins": L["wins"], "hitRate": _rate(L["wins"], L["n"])}) for lg, L in leagues.items()),
        key=lambda kv: (-kv[1]["n"], kv[0])))

    def _slim(e):
        ps, w = e.get("polySide"), e.get("winner")
        return {"matchId": e.get("matchId"), "home": e.get("home"), "away": e.get("away"),
                "league": e.get("league"), "verdict": e.get("verdict"),
                "moneySide": e.get("moneySide"), "moneyName": e.get("moneyName"),
                "polySide": ps, "winner": w, "moneyWin": e.get("moneyWin"),
                "polyWin": ((ps == w) if (ps and w) else None),
                "ftScore": e.get("ftScore"), "kickoff": e.get("kickoff"), "settledAt": e.get("settledAt")}
    recent = [_slim(e) for e in sorted(settled, key=lambda e: (e.get("settledAt") or e.get("kickoff") or ""), reverse=True)[:recent_keep]]

    return {"generatedAt": now or _now_iso(),
            "byVerdict": {k: _fin(v) for k, v in buckets.items()},
            "byLeague": by_league,
            "byStrength": {"strong": _sfin(strength.get(True)), "weak": _sfin(strength.get(False))},
            "divergence": divergence,
            "recent": recent,
            "global": dict({"n": gn, "wins": gw, "hitRate": _rate(gw, gn)},
                           **_geldfin({"rend": grend, "clv": gclv})),
            "pending": sum(1 for e in (ledger or []) if isinstance(e, dict) and e.get("status") == "pending")}


# ── Pinnacle-Bewegung ────────────────────────────────────────────────────────
# 29.08.2026 (Lucas: „Pini move da" als Bedingung fürs Killer-Element):
# Die Bewegung wurde gegen den UNMITTELBAR vorigen Snapshot gerechnet. Der Scan läuft alle
# ~15 Minuten, gelegentlich zweimal in vier Minuten — zwischen zwei Läufen bewegt Pinnacle
# sich praktisch nie. Ergebnis: über 40 Spiele gab es genau ZWEI verschiedene Werte (−0.0
# und 1.2). Die Bewegung war faktisch tot und als Bedingung wertlos.
# Gemessen wird jetzt über das FENSTER (ältester bis aktueller Snapshot) — genau so, wie es
# _pwMoveFor in poly-wallets.js für die Poly-Preise längst macht. Aus der echten Historie:
# 0.658 → 0.544 = −11.4pp über zwei Stunden, vorher unsichtbar.
#
# Drei Regeln müssen mit:
#  · Nur VOR Anpfiff. Ein Live-Repricing nach einem Tor (in der Historie: 0.50 → 0.69
#    innerhalb eines Laufs) ist ein Spielstand, keine Sharp-Bewegung.
#  · Snapshots ohne `pinn` werden ÜBERSPRUNGEN, nicht als 0 gelesen — fehlende Information
#    ist keine Bewegung.
#  · `stepPP` ist der letzte ECHTE Schritt (identische Nachbar-Snapshots aus einem Doppel-
#    lauf werden übersprungen). Zieht er in dieselbe Richtung wie das Fenster, läuft die
#    Bewegung noch — dieselbe Definition wie beim Poly-Steam.
PINN_MOVE_MIN_PP = 1.0     # darunter Rauschen, kein Move


def _ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def pinn_move(prevlist, pinn, side, kickoff=None, live=False):
    """Bewegung der Pinnacle-Wahrscheinlichkeit der Geld-Seite über das Snapshot-Fenster. REIN."""
    i = {"home": 0, "draw": 1, "away": 2}.get(side)
    if i is None or not pinn or len(pinn) <= i or live:
        return None
    if isinstance(prevlist, dict):      # Rückwärts-kompatibel: ein einzelner Snapshot
        prevlist = [prevlist]
    ko = _ts(kickoff)
    hist = []
    for snap in (prevlist or []):
        if not isinstance(snap, dict):
            continue
        p = snap.get("pinn")
        if not isinstance(p, (list, tuple)) or len(p) <= i or not isinstance(p[i], (int, float)):
            continue
        ts = _ts(snap.get("ts"))
        if ko and ts and ts >= ko:
            continue                    # nach Anpfiff: Spielstand, nicht Sharp-Geld
        hist.append(float(p[i]))
    if not hist:
        return None
    jetzt = float(pinn[i])
    move = (jetzt - hist[0]) * 100.0
    step = (jetzt - hist[-1]) * 100.0
    for v in reversed(hist):            # letzter Schritt, der überhaupt einer war
        if abs(jetzt - v) > 1e-9:
            step = (jetzt - v) * 100.0
            break
    return {"movePP": round(move, 1), "stepPP": round(step, 1), "n": len(hist) + 1,
            "move": abs(move) >= PINN_MOVE_MIN_PP,
            "laeuft": (step > 0) == (move > 0) and abs(step) >= 0.2}


def build_game(m, ev, prev, direction, poly=None, totals_ev=None) -> dict:
    """Ein Spiel: Betfair-Geld-Seite + (falls Anker) Pinnacle/Soft-Probs+Quoten, Poly-Odd+Volumen,
    Bewegung, Verdikt. REIN (Netz passiert vorher)."""
    ms = money_side(m)
    li = m.get("liveInfo") or {}
    idx = {"home": 0, "draw": 1, "away": 2}
    i = idx.get(ms.get("side")) if ms else None
    out = {
        "matchId": str(m.get("matchId")), "home": m.get("home"), "away": m.get("away"),
        "league": m.get("league"), "country": m.get("country"), "kickoff": m.get("kickoff"),
        "live": bool(li.get("time")) and not li.get("finished"),
        "moneySide": ms.get("side") if ms else None,
        "moneyName": ms.get("name") if ms else None,
        "moneySharePct": round((ms.get("share") or 0.0) * 100) if ms else None,
        "moneyOdd": ms.get("odd") if ms else None,
        "moneyDir": _money_dir(direction, m, ms),
        "totVol": round(ms.get("totVol")) if ms else 0,
        # rohe Quoten je Quelle FUER DIE GELD-SEITE (das, was Lucas direkt vergleichen will):
        "pinnOdd": (round(ev["pinnOdds"][i], 2) if (ev and ev.get("pinnOdds") and i is not None) else None),
        "softOdd": (round(ev["softOdds"][i], 2) if (ev and ev.get("softOdds") and i is not None) else None),
        "softN": ev.get("nSoft") if ev else None,
        "poly": poly,
        "pinn": None, "soft": None, "pinnMovePP": None, "pinnMove": None,
        "verdict": "no_anchor", "agree": None,
       "pinnTotals": None,
    }
    pinn = ev.get("pinn") if ev else None
    soft = ev.get("soft") if ev else None
    if pinn:
        out["pinn"] = {"home": _r(pinn[0]), "draw": _r(pinn[1]), "away": _r(pinn[2]), "fav": _fav(pinn)}
    if soft:
        out["soft"] = {"home": _r(soft[0]), "draw": _r(soft[1]), "away": _r(soft[2]),
                       "fav": _fav(soft), "n": ev.get("nSoft")}
    # Bewegung: Pinnacle-Prob der Geld-Seite über das Snapshot-Fenster (s. pinn_move oben)
    if pinn and ms:
        pm = pinn_move(prev, pinn, ms.get("side"), m.get("kickoff"), live=out["live"])
        if pm:
            out["pinnMovePP"] = pm["movePP"]
            out["pinnMove"] = pm
    # Verdikt
    ref = pinn or soft
    if ms and ref:
        pinn_ok = (pinn is None) or (_fav(pinn) == ms["side"])
        soft_ok = (soft is None) or (_fav(soft) == ms["side"])
        anchor_fav = _fav(ref) == ms["side"]
        if anchor_fav and pinn_ok and soft_ok:
            out["verdict"] = "konsens"       # alle Quellen sehen dieselbe Seite vorn
        elif anchor_fav:
            out["verdict"] = "teil"          # Anker stimmt, eine Quelle schert aus
        else:
            out["verdict"] = "uneinig"       # Buchmacher sehen die andere Seite vorn
        out["agree"] = out["verdict"] in ("konsens", "teil")
    # 18.08.2026 (Lucas): Pinnacle-Totals (volle Over/Under-Leiter) andocken -> O/U-Edge im Terminal.
    if totals_ev and totals_ev.get("totals"):
        out["pinnTotals"] = totals_ev["totals"]
    return out


# ── Netzwerk (nur hier; laeuft am Mac-Runner) ────────────────────────────────
def fetch_odds(sport_key):
    if not ODDS_KEY:
        return []
    url = ("%s/sports/%s/odds?apiKey=%s&regions=%s&markets=h2h&oddsFormat=decimal&dateFormat=iso"
           % (ODDS_BASE, sport_key, ODDS_KEY, REGIONS))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cocobet-consensus"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        return data if isinstance(data, list) else []
    except Exception as e:
        print("odds-fetch %s: %s" % (sport_key, e))
        return []


def fetch_totals(sport_key):
    """Pinnacle Over/Under, VOLLE Leiter (18.08.2026, Lucas): separater Call, nur eu-Region (dort liegt
    Pinnacle) + markets=totals,alternate_totals. So kostet es nur die Totals-Maerkte in EINER Region
    statt aller Maerkte ueber alle Regionen. h2h-Call bleibt unveraendert."""
    if not ODDS_KEY:
        return []
    url = ("%s/sports/%s/odds?apiKey=%s&regions=eu&markets=totals,alternate_totals&oddsFormat=decimal&dateFormat=iso"
           % (ODDS_BASE, sport_key, ODDS_KEY))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cocobet-consensus"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        return data if isinstance(data, list) else []
    except Exception as e:
        print("totals-fetch %s: %s" % (sport_key, e))
        return []


def main():
    prices = _load(PRICES_FILE, {})
    matches = prices.get("matches") or []
    direction = _load(DIRECTION_FILE, {})
    if not isinstance(direction, dict):
        direction = {}
    hist = _load(HIST_FILE, {})
    if not isinstance(hist, dict):
        hist = {}

    # EXAKT die Spiele der Betfair-Radar-Liste (qualifies_radar), fertige raus.
    live_pool = [m for m in matches
                 if not (m.get("liveInfo") or {}).get("finished") and qualifies_radar(m)]

    # welche Odds-Ligen brauchen wir (nur die, die auch im Feed liegen)?
    need = {}
    for m in live_pool:
        k = LEAGUE_ODDS_KEY.get(m.get("league"))
        if k:
            need.setdefault(k, []).append(m)

    events_by_key = {k: [parse_event(e) for e in (fetch_odds(k) or [])] for k in need}
    totals_by_key = {k: [parse_totals(e) for e in (fetch_totals(k) or [])] for k in need}

    # Poly (globaler Broad-Scan, committet vom Poly-Workflow): nur Basis-Moneylines (kein
    # more-markets/exact-score/total), damit wir die Team-Preise + Volumen matchen koennen.
    poly_raw = _load("poly_money_broad_close.json", {})
    poly_entries = [dict(v, src="close") for k, v in poly_raw.items()
                    if isinstance(v, dict) and v.get("prices")
                    and not any(x in str(k) for x in ("-more-markets", "-exact-score", "-total", "-spread"))
                    and len(v.get("prices")) <= 4] if isinstance(poly_raw, dict) else []
    # Stufe 4 (Live): fuer laufende Spiele die LIVE-Poly-Blase (poly_money_broad_live.json).
    # Additiv — nur die Money-Map nutzt sie; der Betfair-Radar (games) bleibt auf dem Close-Freeze.
    poly_live_raw = _load("poly_money_broad_live.json", {})
    poly_live_entries = [dict(v, src="live") for k, v in poly_live_raw.items()
                    if isinstance(v, dict) and v.get("prices")
                    and not any(x in str(k) for x in ("-more-markets", "-exact-score", "-total", "-spread"))
                    and len(v.get("prices")) <= 4] if isinstance(poly_live_raw, dict) else []
    # Money-Map (12.08.2026, Lucas): breitere "upcoming"-Erfassung (nur Preis+Vol, kein Holder-Call) ->
    # Poly-Blase auch fuer Spiele weit vor Anpfiff (Super Cup/Pokal), wenn close/live den Markt noch nicht hat.
    poly_upcoming_raw = _load("poly_money_upcoming.json", {})
    poly_upcoming_entries = [dict(v, src="upcoming") for k, v in poly_upcoming_raw.items()
                    if isinstance(v, dict) and v.get("prices")
                    and not any(x in str(k) for x in ("-more-markets", "-exact-score", "-total", "-spread"))
                    and len(v.get("prices")) <= 4] if isinstance(poly_upcoming_raw, dict) else []
    # 23.08.2026 (Lucas: „Serie A ist alles da, aber Money-Map zeigt kein Poly"): letzter Fallback ist
    # der FAIRE Poly-Preis aus dem Pinnacle×Poly-Scan (pinnacle_poly_scan.json). Er deckt auch dünne
    # Märkte ($597-Bücher), die durch die Volumen-Schwelle des Broad-Money-Scans fallen. Er füllt NUR
    # die Poly-SEITE (für den Konsens) — als „scan" markiert, damit er im Render als dünn/Preis erscheint
    # und im Money-Gate NICHT als echte Geldquelle zählt (siehe _mm_money_ok).
    scan_raw = _load("pinnacle_poly_scan.json", {})
    poly_scan_entries = []
    for _k, _v in ((scan_raw.get("games") or {}).items() if isinstance(scan_raw, dict) else []):
        if not isinstance(_v, dict):
            continue
        _snaps = _v.get("snaps") or []
        _last = _snaps[-1] if _snaps else None
        _poly = (_last or {}).get("poly") if isinstance(_last, dict) else None
        _home, _away = _v.get("home"), _v.get("away")
        if not (isinstance(_poly, list) and len(_poly) >= 3 and _home and _away):
            continue
        poly_scan_entries.append({
            "prices": {_home: _poly[0], "Draw": _poly[1], _away: _poly[2]},
            "shares": {}, "totalUsd": (_last or {}).get("vol") or 0, "src": "scan"})

    now = _now_iso()
    games, new_hist, mm_rows, mm_name_misses = [], {}, [], []
    for m in live_pool:
        mid = str(m.get("matchId"))
        k = LEAGUE_ODDS_KEY.get(m.get("league"))
        ev = match_event(m, events_by_key.get(k, [])) if k else None
        tev = match_event(m, totals_by_key.get(k, [])) if k else None
        # Poly-Quelle je nach Phase (18.08.2026, Lucas): LAUFENDES Spiel -> FRISCHE Live-Poly hat Vorrang,
        # sonst zeigte der Terminal auf einem Live-Spiel die eingefrorene Pre-Match-Quote aus dem Close-Pool.
        # Nicht-live: Close (<=3h Freeze, mit Holder-Shares) zuerst, dann die breitere Upcoming-Erfassung
        # (Preis+Vol, kein Freeze) fuer Spiele weit vor Anpfiff. sharePct kann bei live/upcoming None sein.
        _li = m.get("liveInfo") or {}
        _isl = bool(_li.get("time")) and not _li.get("finished")
        poly = pick_poly(m, money_side(m), _isl, poly_entries, poly_live_entries, poly_upcoming_entries)
        prevlist = hist.get(mid) or []
        # 29.08.2026: build_game bekommt die GANZE Fenster-Historie, nicht mehr nur den
        # letzten Snapshot — sonst misst pinn_move zwei Läufe im Abstand von Minuten.
        prev = prevlist
        g = build_game(m, ev, prev, direction, poly, totals_ev=tev)
        games.append(g)
        # Money-Map Poly-Pool (12.08.2026, Lucas): live (laufend) > close (<=3h, mit Shares) >
        # upcoming (weit draussen, nur Preis+Vol). So erscheint die Poly-Blase auch lange vor Anpfiff.
        li = m.get("liveInfo") or {}
        is_live = bool(li.get("time")) and not li.get("finished")
        if is_live and _best_poly_entry(m, poly_live_entries) is not None:
            mm_pool, mm_g = poly_live_entries, build_game(m, ev, prev, direction, match_poly(m, money_side(m), poly_live_entries))
        elif _best_poly_entry(m, poly_entries) is not None:
            mm_pool, mm_g = poly_entries, g
        elif _best_poly_entry(m, poly_upcoming_entries) is not None:
            mm_pool, mm_g = poly_upcoming_entries, g   # Verdikt bleibt no_anchor; money_map_row leitet Konsens aus Betfair vs Poly ab
        else:
            mm_pool, mm_g = poly_scan_entries, g   # 23.08.2026 (Lucas): dünner Markt -> fairer Poly-Preis aus dem Scan
        _mmr = money_map_row(mm_g, poly_fav(m, mm_pool))
        mm_rows.append(_mmr)
        # 13.08.2026 (Lucas-Audit): Namens-Match-Miss zaehlen - Betfair-Geld da, Poly=None, aber im
        # Pool liegt ein Kandidat mit Token-Overlap (wahrscheinlich Abkuerzungs-Luecke).
        if _mmr.get("betfair") and not _mmr.get("poly") and _poly_has_any_overlap(m, mm_pool):
            mm_name_misses.append({"matchId": mid, "home": m.get("home"), "away": m.get("away"), "league": m.get("league")})
        snap = {"ts": now}
        if ev and ev.get("pinn"):
            snap["pinn"] = [round(x, 4) for x in ev["pinn"]]
        if snap.get("pinn") or prevlist:
            _letzte = _ts((prevlist[-1] or {}).get("ts")) if prevlist else None
            _jetzt = _ts(now)
            _zu_dicht = bool(_letzte and _jetzt
                             and (_jetzt - _letzte).total_seconds() < SNAP_MIN_ABSTAND_MIN * 60)
            # Zu dicht am letzten Eintrag: NICHT anhängen (sonst schiebt ein Doppellauf das
            # Fenster weg und der letzte Schritt misst vier Minuten statt zwanzig).
            new_hist[mid] = (prevlist if _zu_dicht else (prevlist + [snap]))[-HIST_KEEP:]

    games.sort(key=lambda g: (g.get("verdict") != "no_anchor", g.get("totVol") or 0), reverse=True)
    covered = sum(1 for g in games if g.get("verdict") != "no_anchor")
    out = {"generatedAt": now, "count": len(games), "covered": covered,
           "leaguesCovered": sorted(set(LEAGUE_ODDS_KEY.values())), "games": games}
    _dump(OUT_FILE, out)
    _dump(HIST_FILE, new_hist)
    # Money-Map (11.08.2026, Lucas): bubble-fertiger Feed + Konsens-Ledger fuers Tracking. Additiv.
    mm_rows = [r for r in mm_rows if _mm_money_ok(r)]   # 12.08.2026 (Lucas): min. 2 Geldquellen (Betfair+Poly) ODER eine Quelle >= MM_SINGLE_MIN
    mm_rows.sort(key=lambda r: (r.get("verdict") != "no_anchor", (r.get("betfair") or {}).get("eur") or 0), reverse=True)
    _dump(MONEYMAP_FILE, {"generatedAt": now, "count": len(mm_rows), "rows": mm_rows,
                          "nameMatchMisses": len(mm_name_misses), "nameMatchMissList": mm_name_misses[:20]})
    if mm_name_misses:
        print("WARN Money-Map Namens-Match-Miss: %d Spiele mit Betfair-Geld aber poly=None trotz Poly-Kandidat (%s ...)"
              % (len(mm_name_misses), ", ".join("%s-%s" % (x["home"], x["away"]) for x in mm_name_misses[:3])))
    mm_led = update_mm_ledger(_load(MMLEDGER_FILE, []), mm_rows, now=now)
    # 13.08.2026 (Lucas): Feed (betfair_prices.json) MIT reingeben -> abrechnen ohne Netz; _fetch_results als Backfill.
    mm_led = settle_mm_ledger(mm_led, results_fetch=_fetch_results, prices=prices)   # abrechnen gegen Endstand
    _dump(MMLEDGER_FILE, mm_led)
    _dump(MMRECORD_FILE, mm_summary(mm_led))
    _mm_done = sum(1 for e in mm_led if isinstance(e, dict) and e.get("status") in ("won", "lost"))
    _mm_open = sum(1 for e in mm_led if isinstance(e, dict) and e.get("status") == "pending")
    print("Money-Map: %d Zeilen -> %d im Ledger (%d abgerechnet, %d offen)" % (len(mm_rows), len(mm_led), _mm_done, _mm_open))
    print("Betfair-Konsens: %d Spiele (Radar-Schwelle), %d mit Odds-Anker" % (len(games), covered))


if __name__ == "__main__":
    main()
