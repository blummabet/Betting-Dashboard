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
try:
    from fetch_betfair_betwatch import fetch_results as _fetch_results  # autoritative Endstaende (Runner)
except Exception:
    _fetch_results = None
ODDS_KEY       = os.environ.get("ODDS_API_KEY") or "16154a94ee84482dcd5a4af88d521d73"   # leerer Secret-String -> App-Key
ODDS_BASE      = "https://api.the-odds-api.com/v4"
REGIONS        = "eu,uk,us"     # Pinnacle liegt in eu; Soft-Books ueber uk/us breiter erfasst
HIST_KEEP      = 8              # letzte n Snapshots je Spiel behalten
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


def _norm(s) -> list:
    """Team-Name -> Liste signifikanter Tokens (klein, akzentfrei, ohne Rausch-Tokens/Zahlen)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return [t for t in s.split() if t and t not in _NOISE and not t.isdigit()]


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


def _flip(ev) -> dict:
    """Event mit vertauschten Teams (falls Heim/Auswaerts zwischen den Quellen gedreht sind)."""
    def rev(p):
        return [p[2], p[1], p[0]] if p else None
    return {"home": ev["away"], "away": ev["home"], "commence": ev.get("commence"),
            "pinn": rev(ev.get("pinn")), "soft": rev(ev.get("soft")),
            "pinnOdds": rev(ev.get("pinnOdds")), "softOdds": rev(ev.get("softOdds")), "nSoft": ev.get("nSoft")}


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
    if name == "The Draw":
        side = "draw"
    elif name == m.get("away"):
        side = "away"
    else:
        side = "home"
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


def money_map_row(g, pf):
    """11.08.2026 (Lucas Money-Map): build_game-Output g + poly_fav pf -> bubble-fertige Zeile.
    Betfair-Geld (EUR) + Poly-Geld (USD, eigene Seite) + Pinnacle-Probs + Verdikt + nSources. REIN/testbar."""
    bf_side = g.get("moneySide")
    pinn = g.get("pinn")
    row = {"matchId": g.get("matchId"), "home": g.get("home"), "away": g.get("away"),
           "league": g.get("league"), "live": g.get("live"), "kickoff": g.get("kickoff"),
           "verdict": g.get("verdict"),
           "betfair": ({"side": bf_side, "name": g.get("moneyName"),
                        "sharePct": g.get("moneySharePct"), "eur": g.get("totVol")} if bf_side else None),
           "poly": ({"side": pf["side"], "name": pf["name"], "sharePct": pf["sharePct"], "usd": pf["usd"],
                     "src": pf.get("src")}
                    if pf else None),
           "pinn": ({"fav": pinn.get("fav"), "home": pinn.get("home"), "draw": pinn.get("draw"),
                     "away": pinn.get("away")} if pinn else None)}
    # Money-Map-Verdikt auch OHNE Pinnacle/Soft-Anker (11.08.2026, Lucas): die Map lebt vom Geld,
    # Pinnacle ist nur Anker. Fehlt der Anker (z.B. UEFA Super Cup / Pokal - nicht in den 22 Odds-Ligen),
    # aber Betfair UND Poly liegen vor, dann Konsens/Divergenz aus Betfair-Seite vs Poly-Seite ableiten
    # (2/3, "ehrlich"). Nur Betfair allein bleibt no_anchor (nichts zum Vergleichen).
    if row["verdict"] == "no_anchor" and row["betfair"] and row["poly"]:
        row["verdict"] = "konsens" if row["betfair"]["side"] == row["poly"]["side"] else "uneinig"
    row["nSources"] = sum(1 for x in (row["betfair"], row["poly"], row["pinn"]) if x)
    return row


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
        led[mid] = {"matchId": mid, "home": r.get("home"), "away": r.get("away"), "league": r.get("league"),
                    "kickoff": r.get("kickoff"), "verdict": r.get("verdict"), "nSources": r.get("nSources"),
                    "moneySide": bf.get("side"), "moneyName": bf.get("name"),
                    "pinnFav": pinn.get("fav"), "polySide": poly.get("side"),
                    "firstSeen": (e or {}).get("firstSeen") or now, "updatedAt": now, "status": "pending"}
    return list(led.values())[-keep:]


def _winner_1x2(g1, g2):
    """1X2-Gewinner aus dem Endstand [heim, ausw] -> home/draw/away oder None."""
    if not isinstance(g1, int) or not isinstance(g2, int):
        return None
    return "home" if g1 > g2 else "away" if g2 > g1 else "draw"


def settle_mm_ledger(ledger, results_fetch=None, now=None, min_h=None):
    """11.08.2026 (Lucas Money-Map Tracking): pending-Konsens-Eintraege gegen den echten Endstand
    abrechnen (Betfair-Results-Endpoint). Gewann die Betfair-Geld-Seite (moneySide) -> status won/lost;
    zusaetzlich pinnWin (gewann Pinnacles Favorit). REIN/testbar (results_fetch injizierbar)."""
    from datetime import timedelta
    now = now or datetime.now(timezone.utc)
    min_h = MM_RESULTS_MIN_H if min_h is None else min_h
    ledger = [dict(e) for e in (ledger or []) if isinstance(e, dict)]
    if results_fetch is None:
        return ledger
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
    if not stale:
        return ledger
    res = results_fetch(stale) or {}
    for e in ledger:
        if e.get("status") != "pending":
            continue
        r = res.get(str(e.get("matchId"))) if isinstance(res, dict) else None
        if not isinstance(r, dict) or not r.get("finished") or r.get("goal_v1") is None:
            continue
        w = _winner_1x2(r.get("goal_v1"), r.get("goal_v2"))
        if w is None:
            continue
        e["ftScore"] = [r.get("goal_v1"), r.get("goal_v2")]
        e["winner"] = w
        e["moneyWin"] = (e.get("moneySide") == w)
        if e.get("pinnFav"):
            e["pinnWin"] = (e.get("pinnFav") == w)
        e["status"] = "won" if e["moneyWin"] else "lost"
        e["settledAt"] = now.isoformat()
    return ledger


def mm_summary(ledger, now=None):
    """Trefferquote je Verdikt-Typ (folgt man der Betfair-Geld-Seite): schlaegt Konsens die uneinigen
    Faelle? Plus Pinnacle-Favoriten-Quote zum Vergleich. REIN/testbar."""
    buckets = {}
    gn = gw = 0
    for e in (ledger or []):
        if not isinstance(e, dict) or e.get("status") not in ("won", "lost"):
            continue
        v = e.get("verdict") or "?"
        b = buckets.setdefault(v, {"n": 0, "wins": 0, "pinnN": 0, "pinnWins": 0})
        b["n"] += 1
        b["wins"] += 1 if e.get("moneyWin") else 0
        if e.get("pinnWin") is not None:
            b["pinnN"] += 1
            b["pinnWins"] += 1 if e.get("pinnWin") else 0
        gn += 1
        gw += 1 if e.get("moneyWin") else 0

    def _fin(b):
        return {"n": b["n"], "wins": b["wins"],
                "hitRate": round(b["wins"] / b["n"], 4) if b["n"] else None,
                "pinnN": b["pinnN"],
                "pinnHitRate": round(b["pinnWins"] / b["pinnN"], 4) if b["pinnN"] else None}

    return {"generatedAt": now or _now_iso(),
            "byVerdict": {k: _fin(v) for k, v in buckets.items()},
            "global": {"n": gn, "wins": gw, "hitRate": round(gw / gn, 4) if gn else None},
            "pending": sum(1 for e in (ledger or []) if isinstance(e, dict) and e.get("status") == "pending")}


def build_game(m, ev, prev, direction, poly=None) -> dict:
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
        "pinn": None, "soft": None, "pinnMovePP": None, "verdict": "no_anchor", "agree": None,
    }
    pinn = ev.get("pinn") if ev else None
    soft = ev.get("soft") if ev else None
    if pinn:
        out["pinn"] = {"home": _r(pinn[0]), "draw": _r(pinn[1]), "away": _r(pinn[2]), "fav": _fav(pinn)}
    if soft:
        out["soft"] = {"home": _r(soft[0]), "draw": _r(soft[1]), "away": _r(soft[2]),
                       "fav": _fav(soft), "n": ev.get("nSoft")}
    # Bewegung: Pinnacle-Prob der Geld-Seite gegen den letzten Snapshot
    if pinn and ms and prev and prev.get("pinn"):
        i = idx[ms["side"]]
        try:
            out["pinnMovePP"] = round((pinn[i] - prev["pinn"][i]) * 100, 1)
        except (TypeError, IndexError):
            pass
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

    now = _now_iso()
    games, new_hist, mm_rows = [], {}, []
    for m in live_pool:
        mid = str(m.get("matchId"))
        k = LEAGUE_ODDS_KEY.get(m.get("league"))
        ev = match_event(m, events_by_key.get(k, [])) if k else None
        poly = match_poly(m, money_side(m), poly_entries)
        prevlist = hist.get(mid) or []
        prev = prevlist[-1] if prevlist else None
        g = build_game(m, ev, prev, direction, poly)
        games.append(g)
        # Money-Map Poly-Pool (12.08.2026, Lucas): live (laufend) > close (<=3h, mit Shares) >
        # upcoming (weit draussen, nur Preis+Vol). So erscheint die Poly-Blase auch lange vor Anpfiff.
        li = m.get("liveInfo") or {}
        is_live = bool(li.get("time")) and not li.get("finished")
        if is_live and _best_poly_entry(m, poly_live_entries) is not None:
            mm_pool, mm_g = poly_live_entries, build_game(m, ev, prev, direction, match_poly(m, money_side(m), poly_live_entries))
        elif _best_poly_entry(m, poly_entries) is not None:
            mm_pool, mm_g = poly_entries, g
        else:
            mm_pool, mm_g = poly_upcoming_entries, g   # Verdikt bleibt no_anchor; money_map_row leitet Konsens aus Betfair vs Poly ab
        mm_rows.append(money_map_row(mm_g, poly_fav(m, mm_pool)))
        snap = {"ts": now}
        if ev and ev.get("pinn"):
            snap["pinn"] = [round(x, 4) for x in ev["pinn"]]
        if snap.get("pinn") or prevlist:
            new_hist[mid] = (prevlist + [snap])[-HIST_KEEP:]

    games.sort(key=lambda g: (g.get("verdict") != "no_anchor", g.get("totVol") or 0), reverse=True)
    covered = sum(1 for g in games if g.get("verdict") != "no_anchor")
    out = {"generatedAt": now, "count": len(games), "covered": covered,
           "leaguesCovered": sorted(set(LEAGUE_ODDS_KEY.values())), "games": games}
    _dump(OUT_FILE, out)
    _dump(HIST_FILE, new_hist)
    # Money-Map (11.08.2026, Lucas): bubble-fertiger Feed + Konsens-Ledger fuers Tracking. Additiv.
    mm_rows.sort(key=lambda r: (r.get("verdict") != "no_anchor", (r.get("betfair") or {}).get("eur") or 0), reverse=True)
    _dump(MONEYMAP_FILE, {"generatedAt": now, "count": len(mm_rows), "rows": mm_rows})
    mm_led = update_mm_ledger(_load(MMLEDGER_FILE, []), mm_rows, now=now)
    mm_led = settle_mm_ledger(mm_led, results_fetch=_fetch_results)   # abrechnen gegen Endstand
    _dump(MMLEDGER_FILE, mm_led)
    _dump(MMRECORD_FILE, mm_summary(mm_led))
    print("Money-Map: %d Zeilen -> %d im Ledger" % (len(mm_rows), len(mm_led)))
    print("Betfair-Konsens: %d Spiele (Radar-Schwelle), %d mit Odds-Anker" % (len(games), covered))


if __name__ == "__main__":
    main()
