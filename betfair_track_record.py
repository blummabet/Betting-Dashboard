#!/usr/bin/env python3
"""
betfair_track_record.py — Track-Record / Backtest für das Betfair-Geld-Signal (29.07.2026, Lucas).

## Frage
Welche LIGA × MARKT (× Team) trifft wirklich, wenn man dem Betfair-Geld folgt? Beispiel: „In Ecuador
kommt viel auf HT-Sieg rein" — geht das dort historisch oft auf? Zwei Signale werden GETRENNT bewertet:
  · Konzentration  — der Geld-Favorit je Markt hat ≥ CONC_THRESHOLD des Marktgeldes
  · Zufluss        — in den Markt kam seit dem letzten Snapshot frisches Geld (mkv-Delta ≥ INFLOW_MIN)
Kennzahlen je Bucket: Trefferquote UND ROI (Gewinn zu den Quoten, wenn man den Geld-Favorit „backt").

## Ablauf (läuft nach fetch_betfair_betwatch.py auf dem Mac-Runner)
  1. capture(): für jedes VOR-Anpfiff-Spiel je Markt den Geld-Favorit + Flags festhalten (jeder Lauf
     überschreibt → am Ende steht das CLOSING-Signal). Live nahe Halbzeit den HT-Stand einfangen.
  2. settle(): sobald ein Spiel „finished" ist, jeden gemerkten Markt gegen End-/HT-Stand abrechnen.
  3. aggregate(): über alle abgerechneten Signale nach Liga×Markt und Team×Markt bündeln.
Reiner Kern (fav_token, winning_token, grade, capture, settle, aggregate) ist netz-frei/testbar.

## Dateien
  liest  betfair_prices.json (+ betfair_history.json für den Zufluss)
  führt  betfair_track_state.json    — pending Signale + eingefangener HT-Stand
         betfair_track_results.json  — abgerechnete Einzel-Signale (Ledger, gekappt)
  schreibt betfair_track_record.json — Aggregat fürs Dashboard
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from safe_write import write_json_atomic   # 25.08.2026: temp+replace statt halber Datei
import betfair_track_store as _store       # 01.09.2026: kompaktes Ledger-Format (liest Altformat mit)
from freigabe import UG_MIN_N, Z as UG_Z   # 04.09.2026: dieselbe Schranke wie ueberall

BASE = Path(__file__).resolve().parent
PRICES_FILE = BASE / "betfair_prices.json"
HISTORY_FILE = BASE / "betfair_history.json"
STATE_FILE = BASE / "betfair_track_state.json"
RESULTS_FILE = BASE / "betfair_track_results.json"
CONSENSUS_FILE = BASE / "betfair_consensus.json"   # 12.08.2026 (Lucas): Pinnacle-Odd fuer CLV-vs-Pinnacle
RECORD_FILE = BASE / "betfair_track_record.json"
DIRECTION_FILE = BASE / "betfair_direction.json"   # 08.08.2026 (Lucas): Back/Lay-Richtung je Runner

try:
    from betfair_direction import look as _dir_look
except Exception:   # Modul optional — ohne bleibt dir einfach None
    def _dir_look(direction, matchId, market, runner):
        return None

try:
    from fetch_betfair_betwatch import fetch_results as _fetch_results   # 10.08.2026 (Lucas): autoritative Endstaende
except Exception:   # Modul/Netz optional — ohne bleibt die finished/vanish-Logik unveraendert
    _fetch_results = None

CONC_THRESHOLD = 0.65     # Geld-Favorit gilt als „konzentriert" ab so viel Marktanteil
INFLOW_MIN_EUR = 2000     # Markt gilt als „frischer Zufluss" ab so viel € Delta (prices sind €)
RESULTS_KEEP = int(os.environ.get("BF_RESULTS_KEEP") or 40000)   # Ledger-Kappung
# 01.09.2026 (Lucas: „kann es sein dass da schon ewig 8000 steht"). Ja — und zwar seit dem Tag,
# an dem der Ledger einmal voll war. Bei ~1.300 Abrechnungen taeglich hielten 8000 Zeilen genau
# SECHS Tage; jeder Liga×Markt-Bucket war damit auf n≈24 gedeckelt, waehrend das Lern-Board ab
# n=15 Card-Signale umdreht. 40.000 sind ~6 Wochen. Moeglich wird das nur durch das kompakte
# Format in betfair_track_store.py (105 statt 392 B/Zeile) — im alten Format waeren das 15,7 MB
# alle 10 Minuten ins Git.
PENDING_TTL_H = 60        # pending ohne Settlement nach so vielen h nach Anpfiff verwerfen
RESULTS_MIN_H = 3.0       # Anpfiff so lange her → Spiel sicher vorbei → autoritatives Ergebnis (POST /results) abfragbar
CORRECTION_WINDOW_H = 30  # so lange nach dem Settle darf /results eine per Live-Feed abgerechnete Zeile noch
                          # korrigieren (Live-Goal-Feed kann fuer ein Spiel auf 0:0 haengen, Plymouth-Fall)

# 07.08.2026 (Lucas: „Push-Bilanz komplett wertlos"): der Feed zeigt „finished" nur kurz/unzuverlaessig
# — ~35% der Spiele fallen aus dem Feed BEVOR ein 15-Min-Lauf sie als „finished" erwischt und bleiben
# ewig pending. Zweiter Settle-Pfad: faellt ein Spiel aus dem Feed, das wir zuletzt SPAET (>= 85') live
# gesehen haben, dann rechnen wir es mit diesem letzten Live-Stand ab (kein finished-Blitz noetig).
VANISH_MIN_MINUTE = 85    # nur abrechnen, wenn wir das Spiel zuletzt so spaet live gesehen haben
VANISH_GRACE_MIN = 25     # und es seither so lange weg ist (schuetzt vor kurzem Feed-Aussetzer)

# marketId → Typ. Genau die 7 Dashboard-Märkte.
MARKETS = {
    "Match Odds": "1x2",
    "Half Time": "ht1x2",
    "Over/Under 2.5 Goals": "ou25",
    "Over/Under 3.5 Goals": "ou35",
    "Both teams to Score?": "btts",
    "First Half Goals 0.5": "fho05",
    "First Half Goals 1.5": "fho15",
}


def _now():
    return datetime.now(timezone.utc)


# ── reine Grading-Logik ───────────────────────────────────────────────────────
def fav_token(market_id, runner_name, home, away):
    """Runner-Name → kanonisches Token (H/D/A · OVER/UNDER · YES/NO) je Markttyp. None wenn unklar."""
    t = MARKETS.get(market_id)
    if t in ("1x2", "ht1x2"):
        if runner_name == home:
            return "H"
        if runner_name == away:
            return "A"
        if runner_name == "The Draw":
            return "D"
        return None
    if t in ("ou25", "ou35", "fho05", "fho15"):
        n = str(runner_name or "").lower()
        if n.startswith("over"):
            return "OVER"
        if n.startswith("under"):
            return "UNDER"
        return None
    if t == "btts":
        n = str(runner_name or "").strip().lower()
        if n == "yes":
            return "YES"
        if n == "no":
            return "NO"
        return None
    return None


def winning_token(market_id, ft, ht):
    """Gewinner-Token aus End-(ft) bzw. Halbzeit-(ht) Stand [heim, ausw]. None wenn nicht abrechenbar."""
    t = MARKETS.get(market_id)
    if t == "1x2":
        if not ft:
            return None
        h, a = ft
        return "H" if h > a else "A" if a > h else "D"
    if t == "ht1x2":
        if not ht:
            return None
        h, a = ht
        return "H" if h > a else "A" if a > h else "D"
    if t == "ou25":
        return None if not ft else ("OVER" if (ft[0] + ft[1]) > 2.5 else "UNDER")
    if t == "ou35":
        return None if not ft else ("OVER" if (ft[0] + ft[1]) > 3.5 else "UNDER")
    if t == "btts":
        return None if not ft else ("YES" if (ft[0] > 0 and ft[1] > 0) else "NO")
    if t == "fho05":
        return None if not ht else ("OVER" if (ht[0] + ht[1]) > 0.5 else "UNDER")
    if t == "fho15":
        return None if not ht else ("OVER" if (ht[0] + ht[1]) > 1.5 else "UNDER")
    return None


def grade(fav, market_id, ft, ht):
    """→ (win, ok). ok=False, wenn nicht abrechenbar (z.B. HT-Markt ohne eingefangenen HT-Stand)."""
    wt = winning_token(market_id, ft, ht)
    if wt is None or fav is None:
        return (False, False)
    return (fav == wt, True)


# ── Snapshot-Helfer ───────────────────────────────────────────────────────────
def _lead(market):
    best = None
    for r in (market.get("runners") or []):
        v = r.get("vol") or 0
        if best is None or v > (best.get("vol") or 0):
            best = r
    return best


def _mkt_total(market):
    return sum((r.get("vol") or 0) for r in (market.get("runners") or []))


def _inflow_eur(history, mid, market_id):
    h = (history or {}).get(str(mid))
    if not isinstance(h, list) or len(h) < 2:
        return 0
    a, b = h[-2], h[-1]
    if not (isinstance(a, dict) and isinstance(b, dict) and a.get("mkv") and b.get("mkv")):
        return 0
    return (b["mkv"].get(market_id, 0) or 0) - (a["mkv"].get(market_id, 0) or 0)


def _is_prematch(m, now):
    li = m.get("liveInfo") or {}
    if li.get("time") is not None or li.get("finished"):
        return False
    try:
        kt = datetime.fromisoformat(str(m.get("kickoff")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return kt > now


# ── capture / settle / aggregate ──────────────────────────────────────────────
def capture(prices, history, state, now=None, direction=None, consensus=None):
    """Vor-Anpfiff-Signale je Markt festhalten (Closing = letzter Lauf) + HT-Stand live einfangen. REIN."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    for m in (prices.get("matches") or []):
        mid = str(m.get("matchId"))
        if mid in ("None", ""):
            continue
        li = m.get("liveInfo") or {}
        tt = li.get("time")
        # HT-Stand einfangen (nur solange live, nahe Halbzeit) — für die HT-Märkte
        if mid in pending and tt is not None and not li.get("finished"):
            if (li.get("is_ht") or (isinstance(tt, (int, float)) and 43 <= tt <= 60)) \
                    and pending[mid].get("htScore") is None and li.get("goal_v1") is not None:
                pending[mid]["htScore"] = [li.get("goal_v1"), li.get("goal_v2")]
            # 07.08.2026: zuletzt gesehenen Live-Stand mitschreiben (fuer den Verschwinde-Settle).
            if li.get("goal_v1") is not None:
                pending[mid]["last"] = {"score": [li.get("goal_v1"), li.get("goal_v2")],
                                        "min": tt, "seenAt": now.isoformat()}
        # Signale nur VOR Anpfiff aktualisieren
        if _is_prematch(m, now):
            home, away = m.get("home"), m.get("away")
            sigs = {}
            for mkid in MARKETS:
                mk = (m.get("markets") or {}).get(mkid)
                if not mk:
                    continue
                lead = _lead(mk)
                tot = _mkt_total(mk)
                if not lead or tot <= 0:
                    continue
                fav = fav_token(mkid, lead.get("name"), home, away)
                if fav is None:
                    continue
                share = (lead.get("vol") or 0) / tot
                d = _dir_look(direction, mid, mkid, lead.get("name")) if direction else None
                _prev = ((pending.get(mid) or {}).get("signals") or {}).get(mkid) or {}
                # 13.08.2026 (Lucas-Audit): bei Favoritenwechsel (z.B. O/U Over->Under, enges 1X2)
                # NICHT die alte entryOdd/pinnClose/pinnFair weitertragen -> sonst CLV auf falscher Seite.
                if _prev.get("fav") != fav:
                    _prev = {}
                _pinn = None
                _pinnFair = None
                if mkid == "Match Odds" and isinstance(consensus, dict):
                    _cg = consensus.get(mid) or {}
                    if isinstance(_cg.get("pinnOdd"), (int, float)):
                        _pinn = _cg["pinnOdd"]
                    # 13.08.2026 (Lucas-Audit): CLV-vs-Pinnacle gegen die DE-VIGGTE Fair-Wahrscheinlichkeit
                    # der Geld-Seite (nicht die rohe Quote inkl. Vig - die war ~2-3pp positiv verzerrt).
                    _pd = _cg.get("pinn") if isinstance(_cg.get("pinn"), dict) else None
                    if _pd:
                        _pside = {"H": "home", "D": "draw", "A": "away"}.get(fav)
                        _pf = _pd.get(_pside) if _pside else None
                        if isinstance(_pf, (int, float)) and 0.0 < _pf < 1.0:
                            _pinnFair = _pf
                sigs[mkid] = {"fav": fav, "share": round(share, 3), "odd": lead.get("odd"),
                              "entryOdd": _prev.get("entryOdd", lead.get("odd")),
                              "pinnClose": (_pinn if _pinn is not None else _prev.get("pinnClose")),
                              "pinnFair": (_pinnFair if _pinnFair is not None else _prev.get("pinnFair")),
                              "conc": share >= CONC_THRESHOLD,
                              "inflow": _inflow_eur(history, mid, mkid) >= INFLOW_MIN_EUR,
                              "dir": (d or {}).get("dir")}   # 'in'=gebackt (Quote kuerzer) · 'out'=gedriftet
            if sigs:
                pending[mid] = {"league": m.get("league"), "home": home, "away": away,
                                "country": m.get("country"), "kickoff": m.get("kickoff"),
                                "signals": sigs, "htScore": (pending.get(mid) or {}).get("htScore"),
                                "last": (pending.get(mid) or {}).get("last")}
    state["pending"] = pending
    return state


def settle(prices, state, results, now=None, results_fetch=None):
    """Fertige Spiele abrechnen → results-Ledger. Entfernt settled + zu alte pending. REIN (results_fetch
    injizierbar; None = Endpoint-Pfad aus, weiter testbar)."""
    now = now or _now()
    state = dict(state or {})
    pending = dict(state.get("pending") or {})
    results = list(results or [])

    def _grade_pending(mid, pend, ft, ht, via):
        """Ein pending-Spiel gegen ft/ht abrechnen und ins Ledger schreiben. Entfernt pending."""
        for mkid, sig in (pend.get("signals") or {}).items():
            win, ok = grade(sig["fav"], mkid, ft, ht)
            if not ok:
                continue
            _e = sig.get("entryOdd", sig.get("odd"))
            results.append({"league": pend.get("league"), "market": mkid,
                            "home": pend.get("home"), "away": pend.get("away"), "country": pend.get("country"),
                            "fav": sig["fav"], "odd": sig["odd"], "entryOdd": _e,
                            "pinnClose": sig.get("pinnClose"), "pinnFair": sig.get("pinnFair"),
                            "clvBf": _clv_pp(_e, sig.get("odd")), "clvPinn": _clv_pp_fair(_e, sig.get("pinnFair")),
                            "conc": bool(sig.get("conc")), "inflow": bool(sig.get("inflow")),
                            "win": bool(win), "settledAt": now.isoformat(),
                            "matchId": mid, "ft": ft, "ht": ht, "via": via, "dir": sig.get("dir")})
        pending.pop(mid, None)

    # 1) Feed zeigt „finished" → sauber abrechnen (der exakte Endstand).
    for m in (prices.get("matches") or []):
        li = m.get("liveInfo") or {}
        if not li.get("finished"):
            continue
        mid = str(m.get("matchId"))
        pend = pending.get(mid)
        if not pend:
            continue
        ft = [li.get("goal_v1"), li.get("goal_v2")] if li.get("goal_v1") is not None else None
        ht = pend.get("htScore")
        _grade_pending(mid, pend, ft, ht, "finished")

    # 2) Verschwinde-Settle (07.08.2026): Spiel ist aus dem Feed, „finished" wurde NIE erwischt —
    #    aber wir haben es zuletzt spaet (>= VANISH_MIN_MINUTE) live gesehen und es ist seit
    #    >= VANISH_GRACE_MIN weg. Dann mit dem letzten Live-Stand abrechnen (naeherungsweise Endstand).
    feed_ids = {str(m.get("matchId")) for m in (prices.get("matches") or [])}
    for mid in list(pending.keys()):
        if mid in feed_ids:
            continue                      # noch im Feed → Pfad 1 kuemmert sich
        pend = pending[mid]
        last = pend.get("last") or {}
        score, mn = last.get("score"), last.get("min")
        if score is None or not isinstance(mn, (int, float)) or mn < VANISH_MIN_MINUTE:
            continue                      # nie spaet genug live gesehen → nicht schaetzen (→ TTL)
        try:
            seen = datetime.fromisoformat(str(last.get("seenAt")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            seen = None
        if seen is None or seen > now - timedelta(minutes=VANISH_GRACE_MIN):
            continue                      # zu frisch → koennte kurzer Feed-Aussetzer sein, warten
        _grade_pending(mid, pend, list(score), pend.get("htScore"), "vanish")

    # 3) 10.08.2026 (Lucas): AUTORITATIVER Endstand fuer den Rest. Spiele, die weder „finished" noch
    #    Verschwinde-Settle erwischt hat (aus dem Feed gefallen bevor >= VANISH_MIN_MINUTE, ~35%), holen
    #    wir ueber POST /football/results (bis 30 Tage). Additiv: nur laengst gespielte (Anpfiff > RESULTS_MIN_H)
    #    noch-pending, nur wenn der Endpoint „finished" + Score liefert. Fehler/kein Fetcher → alte TTL-Logik.
    if results_fetch is not None and pending:
        stale = []
        for mid in list(pending.keys()):
            try:
                kt = datetime.fromisoformat(str(pending[mid].get("kickoff")).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                kt = None
            if kt is not None and kt < now - timedelta(hours=RESULTS_MIN_H):
                stale.append(mid)
        if stale:
            res = results_fetch(stale) or {}
            for mid in stale:
                r = res.get(str(mid)) if isinstance(res, dict) else None
                if not isinstance(r, dict) or not r.get("finished") or r.get("goal_v1") is None:
                    continue
                _grade_pending(mid, pending[mid], [r.get("goal_v1"), r.get("goal_v2")],
                               pending[mid].get("htScore"), "results")

    # zu alte pending (nie „finished" gesehen) verwerfen
    cutoff = now - timedelta(hours=PENDING_TTL_H)
    for mid in list(pending.keys()):
        try:
            kt = datetime.fromisoformat(str(pending[mid].get("kickoff")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            kt = None
        if kt is not None and kt < cutoff:
            pending.pop(mid, None)
    state["pending"] = pending
    return state, results[-RESULTS_KEEP:]


def _after(iso, cutoff):
    """True, wenn Zeitstempel iso NACH cutoff liegt (robust gegen fehlende/kaputte Werte)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) > cutoff
    except (ValueError, TypeError):
        return False


def verify_settled(results, now=None, results_fetch=None):
    """11.08.2026 (Lucas, Plymouth-Fall): Der Live-Goal-Feed kann fuer ein einzelnes Spiel komplett auf
    0:0 haengen (Plymouth gewann 2:0 -> faelschlich 'lost'). POST /results ist der autoritative Endstand
    (bis 30 Tage). Kuerzlich per Live-Feed (finished/vanish) abgerechnete Zeilen dagegen pruefen; weicht
    der Endstand ab, win/ft korrigieren (via='results-fix'). Jede gepruefte Zeile wird als resChk markiert,
    damit nicht jeder Lauf neu fetcht. Da byTeamMarket/byLeagueMarket jedes Mal frisch aus dem Ledger
    aggregiert werden, heilt eine korrigierte Zeile automatisch auch die Lern-Stats. REIN (results_fetch
    injizierbar; None = aus)."""
    now = now or _now()
    if results_fetch is None or not results:
        return results
    recent = now - timedelta(hours=CORRECTION_WINDOW_H)
    todo = [r for r in results
            if isinstance(r, dict) and not r.get("resChk")
            and r.get("via") in ("finished", "vanish")
            and _after(r.get("settledAt"), recent)]
    ids = sorted({str(r.get("matchId")) for r in todo if r.get("matchId")})
    if not ids:
        return results
    res = results_fetch(ids) or {}
    for r in todo:
        rr = res.get(str(r.get("matchId"))) if isinstance(res, dict) else None
        if not isinstance(rr, dict) or not rr.get("finished") or rr.get("goal_v1") is None:
            continue                       # /results kennt das Spiel (noch) nicht -> naechster Lauf erneut
        ft = [rr.get("goal_v1"), rr.get("goal_v2")]
        win, ok = grade(r.get("fav"), r.get("market"), ft, r.get("ht"))
        if not ok:
            r["resChk"] = True             # nicht abrechenbar (z.B. HT ohne HT-Stand) -> nicht endlos neu holen
            continue
        if bool(win) != bool(r.get("win")) or ft != r.get("ft"):
            r["ft"] = ft
            r["win"] = bool(win)
            r["via"] = "results-fix"
        r["resChk"] = True
    return results


def _clv_pp(entry, close):
    """CLV in Prozentpunkten: implizite Wahrscheinlichkeit(Close) minus (Einstieg). >0 = die Linie zog
    NACH unserem Einstieg auf unsere Seite (wir haben die spaetere/schaerfere Quote geschlagen = Value).
    None, wenn eine Quote fehlt/ungueltig. REIN/testbar. 12.08.2026 (Lucas: CLV auch fuer Betfair)."""
    try:
        e, c = float(entry), float(close)
        if e > 1 and c > 1:
            return round((1.0 / c - 1.0 / e) * 100.0, 2)
    except (TypeError, ValueError):
        pass
    return None


def _clv_pp_fair(entry, fair_prob):
    """CLV vs de-viggter Pinnacle-Fairwahrscheinlichkeit: fairProb - 1/entry (in pp). >0 = Pinnacle sieht
    unsere Seite wahrscheinlicher als unsere Einstiegsquote impliziert = Value. Vig-frei (13.08.2026,
    Lucas-Audit: vorher lief CLV-vs-Pinnacle gegen die ROHE Quote inkl. Marge -> systematisch gruen). REIN."""
    try:
        e, p = float(entry), float(fair_prob)
        if e > 1 and 0.0 < p < 1.0:
            return round((p - 1.0 / e) * 100.0, 2)
    except (TypeError, ValueError):
        pass
    return None


def _bucket():
    return {"n": 0, "wins": 0, "roiSum": 0.0, "roiSqSum": 0.0,
            "nConc": 0, "winsConc": 0, "roiConc": 0.0,
            "nInflow": 0, "winsInflow": 0, "roiInflow": 0.0,
            # 08.08.2026 (Lucas): Richtung — kam das Geld als Back (Quote kuerzer) oder driftete es?
            "nBack": 0, "winsBack": 0, "roiBack": 0.0,
            "nDrift": 0, "winsDrift": 0, "roiDrift": 0.0,
            "nClvBf": 0, "clvBfSum": 0.0, "beatBf": 0,
            "nClvPinn": 0, "clvPinnSum": 0.0, "beatPinn": 0}


def _add(b, r):
    try:
        odd = float(r.get("odd"))
    except (TypeError, ValueError):
        odd = None
    profit = ((odd - 1.0) if r.get("win") else -1.0) if odd and odd > 1 else 0.0
    b["n"] += 1
    b["wins"] += 1 if r.get("win") else 0
    b["roiSum"] += profit
    # 04.09.2026: ohne Quadratsumme gibt es nur den Punktschaetzer — und auf genau den hat das
    # Terminal seit dem 17.08. hart gemutet. Ein Feld, kein Call. (Siehe _fin/roiUg.)
    b["roiSqSum"] += profit * profit
    if r.get("conc"):
        b["nConc"] += 1; b["winsConc"] += 1 if r.get("win") else 0; b["roiConc"] += profit
    if r.get("inflow"):
        b["nInflow"] += 1; b["winsInflow"] += 1 if r.get("win") else 0; b["roiInflow"] += profit
    d = r.get("dir")
    if d == "in":
        b["nBack"] += 1; b["winsBack"] += 1 if r.get("win") else 0; b["roiBack"] += profit
    elif d == "out":
        b["nDrift"] += 1; b["winsDrift"] += 1 if r.get("win") else 0; b["roiDrift"] += profit
    cb = r.get("clvBf")
    if isinstance(cb, (int, float)):
        b["nClvBf"] += 1; b["clvBfSum"] += cb; b["beatBf"] += 1 if cb > 0 else 0
    cp = r.get("clvPinn")
    # 13.08.2026 (Lucas-Audit): nur NEU (de-viggt) gerechnete Zeilen zaehlen - Alt-Zeilen ohne
    # pinnFair trugen den rohen Vig-Bias und faerbten den Schnitt kuenstlich gruen.
    if isinstance(cp, (int, float)) and r.get("pinnFair") is not None:
        b["nClvPinn"] += 1; b["clvPinnSum"] += cp; b["beatPinn"] += 1 if cp > 0 else 0


# 04.09.2026 (Lucas-Checkup des Betfair-Terminals) ──────────────────────────────
# Am 05.08. steht ueber `aggregate` schon: „451 winzige Buckets -> pro Bucket sagt es fast
# nichts." Am 17.08. hat `_tMute` im Terminal trotzdem hart darauf gegatet:
#
#     if (b && b.n >= 10 && b.roi <= -0.05) -> Zeile gemutet
#
# Gemessen am 04.09. sind die fuenf Ligen auf dem Board damit bei n = 9 bis 14:
#
#     English Premier League   n10  ROI -11,1%   -> 9 Zeilen gemutet
#     French Ligue 1           n10  ROI -21,1%   -> gemutet
#     German Bundesliga        n 9  ROI  -5,6%   -> NICHT gemutet, nur weil n=9 statt 10
#     Spanish La Liga          n14  ROI +13,1%   -> "🟢 64%"
#     Italian Serie A          n10  ROI +52,1%   -> "🟢 80%"
#
# Die Rauschprobe: zieht man dieselben Stichprobengroessen ZUFAELLIG aus dem gemeinsamen Topf
# aller 1.652 Match-Odds-Plays (Gesamt-ROI +0,9%), ist die Spanne zwischen bester und
# schlechtester Liga in 91% der Laeufe MINDESTENS so gross wie die beobachtete. Die Unterschiede
# zwischen den Ligen sind also nicht nur unbelegt, sie sind kleiner als reiner Zufall ueblicherweise
# erzeugt. Trotzdem hat das Board die drei ueberzeugtesten Zeilen des Tages weggeblendet
# (Man City Konviktion 93, PSG 100, Arsenal 85).
#
# Deshalb faehrt jeder Bucket jetzt seine RENDITE-UNTERGRENZE mit — dieselbe Rechnung und
# dieselbe n>=30-Grenze wie im Rest des Repos (freigabe.untergrenze). Unter 30 Plays gibt es
# keine Zahl, und damit auch kein Urteil.
def _ug(n, summe, quadratsumme):
    """Einseitige 95%-Untergrenze der Rendite aus n/Summe/Quadratsumme. REIN.

    Aus Summe und Quadratsumme laesst sich die Streuung rekonstruieren, ohne alle Einzelwerte
    zu halten — dieselbe Formel, die freigabe.untergrenze auf der Werteliste rechnet."""
    if n < max(3, UG_MIN_N):
        return None
    m = summe / n
    var = (quadratsumme - n * m * m) / (n - 1)
    if var <= 0:
        return None          # keine Streuung heisst nicht Gewissheit, sondern zu wenig Daten
    return m - UG_Z * (var ** 0.5) / (n ** 0.5)


def _fin(b):
    def rate(w, n):
        return round(w / n, 4) if n else None
    _u = _ug(b["n"], b["roiSum"], b["roiSqSum"])
    return {"n": b["n"], "wins": b["wins"], "hitRate": rate(b["wins"], b["n"]),
            "roi": round(b["roiSum"] / b["n"], 4) if b["n"] else None,
            # Der Punktschaetzer bleibt sichtbar — er entscheidet nur nichts mehr.
            "roiUg": round(_u, 4) if _u is not None else None,
            "ugAb": UG_MIN_N,
            "nConc": b["nConc"], "hitRateConc": rate(b["winsConc"], b["nConc"]),
            "roiConc": round(b["roiConc"] / b["nConc"], 4) if b["nConc"] else None,
            "nInflow": b["nInflow"], "hitRateInflow": rate(b["winsInflow"], b["nInflow"]),
            "roiInflow": round(b["roiInflow"] / b["nInflow"], 4) if b["nInflow"] else None,
            "nBack": b["nBack"], "hitRateBack": rate(b["winsBack"], b["nBack"]),
            "roiBack": round(b["roiBack"] / b["nBack"], 4) if b["nBack"] else None,
            "nDrift": b["nDrift"], "hitRateDrift": rate(b["winsDrift"], b["nDrift"]),
            "roiDrift": round(b["roiDrift"] / b["nDrift"], 4) if b["nDrift"] else None,
            "nClvBf": b["nClvBf"], "avgClvBf": round(b["clvBfSum"] / b["nClvBf"], 2) if b["nClvBf"] else None,
            "pctBeatBf": rate(b["beatBf"], b["nClvBf"]),
            "nClvPinn": b["nClvPinn"], "avgClvPinn": round(b["clvPinnSum"] / b["nClvPinn"], 2) if b["nClvPinn"] else None,
            "pctBeatPinn": rate(b["beatPinn"], b["nClvPinn"])}


def aggregate(results, now=None):
    """Ledger → {byLeagueMarket, byTeamMarket} mit Trefferquote + ROI, je gesamt/konz/zufluss. REIN."""
    now = now or _now()
    lm, tm, bm = {}, {}, {}
    # 05.08.2026 (Lucas: "wissen wir ueberhaupt, ob die Kohle erfolgreich war?"): bisher gab es nur
    # Liga x Markt (451 winzige Buckets) -> pro Bucket sagt es fast nichts. Jetzt ZUSAETZLICH ein
    # globales Roll-up (die Kernzahl: zahlt sich Geld-folgen ueberhaupt aus?) UND je Markt ueber ALLE
    # Ligen (da steckt die eigentliche Kante: z.B. Match Odds profitabel, Tormaerkte nicht).
    g = _bucket()
    for r in (results or []):
        _add(g, r)
        mkk = r.get("market")
        if mkk:
            bm.setdefault(mkk, _bucket()); _add(bm[mkk], r)
        lk = "%s|%s" % (r.get("league"), r.get("market"))
        lm.setdefault(lk, _bucket()); _add(lm[lk], r)
        for team in (r.get("home"), r.get("away")):
            if not team:
                continue
            tk = "%s|%s" % (team, r.get("market"))
            tm.setdefault(tk, _bucket()); _add(tm[tk], r)
    return {"generatedAt": now.isoformat(), "n": len(results or []),
            "concThreshold": CONC_THRESHOLD, "inflowMinEur": INFLOW_MIN_EUR,
            "global": _fin(g), "byMarket": {k: _fin(v) for k, v in bm.items()},
            "byLeagueMarket": {k: _fin(v) for k, v in lm.items()},
            "byTeamMarket": {k: _fin(v) for k, v in tm.items()}}


# ── I/O (main) ────────────────────────────────────────────────────────────────
def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p, data):
    """Atomar (25.08.2026, Audit)."""
    write_json_atomic(p, data, indent=None)


def main():
    print("=== betfair_track_record.py ===")
    prices = _load(PRICES_FILE, {})
    if not prices.get("matches"):
        print("  ℹ️  keine betfair_prices.json — übersprungen (kein Wipe).")
        return 0
    history = _load(HISTORY_FILE, {})
    state = _load(STATE_FILE, {})
    results = _store.load(RESULTS_FILE)          # nimmt Alt- wie Neuformat
    direction = _load(DIRECTION_FILE, {})
    if not isinstance(results, list):
        results = []
    now = _now()
    _cons_raw = _load(CONSENSUS_FILE, {})
    _cons = {str(g.get("matchId")): g for g in (_cons_raw.get("games") or []) if isinstance(g, dict)} if isinstance(_cons_raw, dict) else {}
    state = capture(prices, history, state, now=now, direction=direction if isinstance(direction, dict) else {}, consensus=_cons)
    state, results = settle(prices, state, results, now=now, results_fetch=_fetch_results)
    results = verify_settled(results, now=now, results_fetch=_fetch_results)
    record = aggregate(results, now=now)
    _write(STATE_FILE, state)
    _store.dump(RESULTS_FILE, results)
    record["fenster"] = _store.fenster(results)   # damit die UI die 40.000 nicht wieder fuer „alles" haelt
    _write(RECORD_FILE, record)
    _f = record["fenster"]
    print("  ✅  %d pending · %d abgerechnet (%s Tage Fenster, Deckel %d) · %d Liga×Markt · %d Team×Markt"
          % (len(state.get("pending", {})), len(results), _f.get("tage"), RESULTS_KEEP,
             len(record["byLeagueMarket"]), len(record["byTeamMarket"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
