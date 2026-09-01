#!/usr/bin/env python3
"""
betfair_public_eval.py — Tracking & Auswertung der ÖFFENTLICHEN Betfair-Moneyflow/Halftime-Pushs
(31.07.2026, Lucas: „schaffst du die public Pushs zu tracken und auszuwerten?").

betfair_alerts.py loggt jeden gesendeten Public-Push nach betfair_public_ledger.json (pending).
Hier: den HT-Stand einfangen, fertige Spiele gegen End-/Halbzeitstand abrechnen (dieselben Grading-
Funktionen wie der Liga-Track-Record) und zu einer Bilanz zusammenfassen (Trefferquote + ROI, je
Szenario/Markt) → betfair_public_record.json. Bewertet: „lag das Geld, dem der Push folgte, richtig?"

Läuft im betfair.yml direkt NACH betfair_alerts.py (Mac-Runner, alle 15 Min). REIN/testbar.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import betfair_track_store as _store   # 01.09.2026: Ledger liegt kompakt, load() nimmt beide Formate

# Grading aus dem bestehenden Track-Record wiederverwenden (kein Duplikat).
from betfair_track_record import fav_token, winning_token, grade, MARKETS, RESULTS_MIN_H, CORRECTION_WINDOW_H, _clv_pp

try:
    from fetch_betfair_betwatch import fetch_results as _fetch_results   # 10.08.2026 (Lucas): autoritative Endstaende
except Exception:   # Modul/Netz optional — ohne bleibt die finished/expire-Logik unveraendert
    _fetch_results = None

BASE = Path(__file__).resolve().parent
LEDGER_FILE = BASE / "betfair_public_ledger.json"
RECORD_FILE = BASE / "betfair_public_record.json"
TRACK_RESULTS_FILE = BASE / "betfair_track_results.json"   # der breite Track (~65% Fangquote + Verschwinde-Settle)
PENDING_TTL_H = 72          # nie „finished" gesehen nach 3 Tagen → als nicht abrechenbar verwerfen
LEDGER_KEEP = 800


def _now():
    return datetime.now(timezone.utc)


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _by_id(prices):
    return {str(m.get("matchId")): m for m in (prices.get("matches") or [])}


def capture_ht(ledger, prices, now=None):
    """Halbzeit-Stand für noch offene Pushs einfangen (für HT-Märkte nötig; für FT harmlos)."""
    idx = _by_id(prices)
    for e in ledger:
        if e.get("status") != "pending" or e.get("htScore") is not None:
            continue
        m = idx.get(str(e.get("matchId")))
        if not m:
            continue
        li = m.get("liveInfo") or {}
        tt = li.get("time")
        at_ht = li.get("is_ht") or (isinstance(tt, (int, float)) and 43 <= tt <= 60)
        if at_ht and li.get("goal_v1") is not None and not li.get("finished"):
            e["htScore"] = [li.get("goal_v1"), li.get("goal_v2")]
    return ledger


def _settle_entry(e, ft, ht, now, via):
    """Einen Push gegen ft/ht abrechnen (setzt status/profit/ftScore). True, wenn abgerechnet."""
    fav = fav_token(e.get("market"), e.get("leadName"), e.get("home"), e.get("away"))
    win, ok = grade(fav, e.get("market"), ft, ht)
    if not ok:
        return False
    odd = e.get("leadOdd")
    e["settledAt"] = now.isoformat()
    e["ftScore"] = ft
    e["status"] = "won" if win else "lost"
    e["profit"] = (float(odd) - 1.0) if (win and isinstance(odd, (int, float))) else (-1.0 if not win else 0.0)
    e["via"] = via
    return True


def _track_index(track_results):
    """(matchId, market) → Zeile des breiten Tracks mit realem Endstand (ft/ht). Neuere gewinnen."""
    idx = {}
    for r in (track_results or []):
        mid, mk = r.get("matchId"), r.get("market")
        if mid is None or mk is None or (r.get("ft") is None and r.get("ht") is None):
            continue
        idx[(str(mid), mk)] = r
    return idx


def settle_from_track(ledger, track_results, now=None):
    """07.08.2026 (Lucas: „wie kann die Trefferquote klappen aber die Push-Bilanz nicht"): die Push-
    Bilanz erbt die Abrechnungen des breiten Track-Records. Sobald der breite Track ein Spiel abgerechnet
    hat — per „finished" ODER per Verschwinde-Settle — rechnen wir den passenden Push mit dessen realem
    End-/HT-Stand ab, egal ob DIESER Feed je „finished" gezeigt hat. Laeuft im selben betfair.yml-Lauf
    NACH betfair_track_record.py, liest also die frisch geschriebenen Ergebnisse. REIN."""
    now = now or _now()
    idx = _track_index(track_results)
    for e in ledger:
        if e.get("status") != "pending":
            continue
        row = idx.get((str(e.get("matchId")), e.get("market")))
        if row:
            e["clvBf"] = _clv_pp(e.get("leadOdd"), row.get("odd"))       # 12.08.2026 (Lucas): Push-CLV vs Betfair-Close
            e["clvPinn"] = _clv_pp(e.get("leadOdd"), row.get("pinnClose"))  # + vs Pinnacle-Close (nur abgedeckte Ligen)
            _settle_entry(e, row.get("ft"), row.get("ht"), now, "track")
    return ledger


def _grade_ledger_entry(e, ft, ht, now):
    """Einen pending-Push gegen den Endstand abrechnen (status won/lost/void + profit setzen). REIN."""
    fav = fav_token(e.get("market"), e.get("leadName"), e.get("home"), e.get("away"))
    win, ok = grade(fav, e.get("market"), ft, ht)
    e["settledAt"] = now.isoformat()
    e["ftScore"] = ft
    if not ok:
        e["status"] = "void"          # nicht abrechenbar (z.B. HT-Markt ohne HT-Stand)
        return
    odd = e.get("leadOdd")
    e["status"] = "won" if win else "lost"
    e["profit"] = (float(odd) - 1.0) if (win and isinstance(odd, (int, float))) else (-1.0 if not win else 0.0)


def _sent_before(e, cutoff):
    try:
        st = datetime.fromisoformat(str(e.get("sentAt")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return st < cutoff


def _after(iso, cutoff):
    """True, wenn Zeitstempel iso NACH cutoff liegt (robust gegen fehlende/kaputte Werte)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) > cutoff
    except (ValueError, TypeError):
        return False


def verify_settled(ledger, now=None, results_fetch=None):
    """11.08.2026 (Lucas, Plymouth-Fall): Der Live-Goal-Feed kann fuer ein Spiel komplett auf 0:0 haengen
    (Plymouth gewann 2:0 -> faelschlich 'lost'). POST /results ist der autoritative Endstand (bis 30 Tage).
    Kuerzlich (per finished/vanish/track) abgerechnete Pushs dagegen pruefen; weicht der Endstand ab, den
    Push nach dem echten Ergebnis neu abrechnen (status/profit/ftScore, via='results-fix'). Jede gepruefte
    Zeile wird als resChk markiert, damit nicht jeder Lauf neu fetcht. REIN (results_fetch injizierbar)."""
    now = now or _now()
    if results_fetch is None or not ledger:
        return ledger
    recent = now - timedelta(hours=CORRECTION_WINDOW_H)
    todo = [e for e in ledger
            if e.get("status") in ("won", "lost")
            and e.get("via") not in ("results", "results-fix")
            and not e.get("resChk")
            and _after(e.get("settledAt"), recent)]
    ids = sorted({str(e.get("matchId")) for e in todo if e.get("matchId")})
    if not ids:
        return ledger
    res = results_fetch(ids) or {}
    for e in todo:
        r = res.get(str(e.get("matchId"))) if isinstance(res, dict) else None
        if not isinstance(r, dict) or not r.get("finished") or r.get("goal_v1") is None:
            continue                       # /results kennt das Spiel (noch) nicht -> naechster Lauf erneut
        ft = [r.get("goal_v1"), r.get("goal_v2")]
        fav = fav_token(e.get("market"), e.get("leadName"), e.get("home"), e.get("away"))
        win, ok = grade(fav, e.get("market"), ft, e.get("htScore"))
        if not ok:
            e["resChk"] = True             # nicht abrechenbar -> nicht endlos neu holen
            continue
        new_status = "won" if win else "lost"
        if new_status != e.get("status") or ft != e.get("ftScore"):
            odd = e.get("leadOdd")
            e["status"] = new_status
            e["ftScore"] = ft
            e["profit"] = (float(odd) - 1.0) if (win and isinstance(odd, (int, float))) else (0.0 if win else -1.0)
            e["via"] = "results-fix"
            e["settledAt"] = now.isoformat()
        e["resChk"] = True
    return ledger


def settle(ledger, prices, now=None, results_fetch=None):
    """Fertige Spiele abrechnen. Setzt status won/lost/void + profit (1 Einheit Einsatz). REIN
    (results_fetch injizierbar; None = Endpoint-Pfad aus, weiter testbar)."""
    now = now or _now()
    idx = _by_id(prices)
    for e in ledger:
        if e.get("status") != "pending":
            continue
        m = idx.get(str(e.get("matchId")))
        if m:
            li = m.get("liveInfo") or {}
            if li.get("finished"):
                ft = [li.get("goal_v1"), li.get("goal_v2")] if li.get("goal_v1") is not None else None
                ht = e.get("htScore")
                if ht is None and li.get("goal_v1") is not None and (li.get("is_ht")):
                    ht = [li.get("goal_v1"), li.get("goal_v2")]
                _grade_ledger_entry(e, ft, ht, now)
                continue
        # nie „finished" gesehen & zu alt → verwerfen (Spiel aus dem Feed gefallen)
        if _sent_before(e, now - timedelta(hours=PENDING_TTL_H)):
            e["status"] = "expired"

    # 10.08.2026 (Lucas): AUTORITATIVER Endstand fuer Rest-Pending (analog track_record). Pushs, deren Spiel
    # weder im Feed „finished" war noch verfallen ist (aus dem Feed gefallen), ueber POST /football/results
    # abrechnen (bis 30 Tage). Additiv: nur laengst gesendete (> RESULTS_MIN_H), nur bei „finished" + Score.
    if results_fetch is not None:
        rescue = now - timedelta(hours=RESULTS_MIN_H)
        ids = [str(e.get("matchId")) for e in ledger
               if e.get("status") == "pending" and _sent_before(e, rescue)]
        if ids:
            res = results_fetch(ids) or {}
            for e in ledger:
                if e.get("status") != "pending":
                    continue
                r = res.get(str(e.get("matchId"))) if isinstance(res, dict) else None
                if not isinstance(r, dict) or not r.get("finished") or r.get("goal_v1") is None:
                    continue
                _grade_ledger_entry(e, [r.get("goal_v1"), r.get("goal_v2")], e.get("htScore"), now)
    return ledger


MANUAL_RESULTS_FILE = BASE / "manual_results.json"


def apply_manual_results(ledger, manual, now=None):
    """11.08.2026 (Lucas, Plymouth-Fall): Menschlich bestaetigte Endstaende fuer Spiele, die in KEINER
    Ergebnisquelle stehen (EFL-Cup u.ae. — weder Betwatch /results noch API-Football) und aus dem
    Live-Feed verschwanden (vanish@0:0 -> faelschlich 'lost'). manual_results.json: {matchId: {ft:[h,a],
    ht?:[h,a], note?}}. Ueberschreibt AUCH bereits abgerechnete Zeilen — der gepinnte Endstand schlaegt
    Feed/Vanish. Laeuft als LETZTER Schritt, also gewinnt er auch gegen ein erneutes settle_from_track.
    via='manual', resChk=True. REIN."""
    now = now or _now()
    if not isinstance(manual, dict) or not manual:
        return ledger
    for e in ledger:
        if not isinstance(e, dict):
            continue
        m = manual.get(str(e.get("matchId")))
        if not isinstance(m, dict):
            continue
        ft = m.get("ft")
        if not (isinstance(ft, list) and len(ft) == 2):
            continue
        ht = e.get("htScore") if e.get("htScore") is not None else m.get("ht")
        fav = fav_token(e.get("market"), e.get("leadName"), e.get("home"), e.get("away"))
        win, ok = grade(fav, e.get("market"), ft, ht)
        if not ok:
            continue
        odd = e.get("leadOdd")
        e["status"] = "won" if win else "lost"
        e["ftScore"] = ft
        e["profit"] = (float(odd) - 1.0) if (win and isinstance(odd, (int, float))) else (0.0 if win else -1.0)
        e["via"] = "manual"
        e["resChk"] = True
        if not e.get("settledAt"):
            e["settledAt"] = now.isoformat()
    return ledger


def summarize(ledger, now=None):
    now = now or _now()
    res = [e for e in ledger if e.get("status") in ("won", "lost")]
    pend = sum(1 for e in ledger if e.get("status") == "pending")

    def agg(rows):
        n = len(rows)
        wins = sum(1 for e in rows if e.get("status") == "won")
        profit = sum(float(e.get("profit") or 0) for e in rows)
        odds = [float(e["leadOdd"]) for e in rows if isinstance(e.get("leadOdd"), (int, float))]
        clvb = [e["clvBf"] for e in rows if isinstance(e.get("clvBf"), (int, float))]
        clvp = [e["clvPinn"] for e in rows if isinstance(e.get("clvPinn"), (int, float))]
        return {"n": n, "wins": wins,
                "hitRate": round(wins / n, 4) if n else None,
                "roi": round(profit / n, 4) if n else None,
                "avgOdd": round(sum(odds) / len(odds), 2) if odds else None,
                "nClvBf": len(clvb), "avgClvBf": round(sum(clvb) / len(clvb), 2) if clvb else None,
                "pctBeatBf": round(sum(1 for x in clvb if x > 0) / len(clvb), 3) if clvb else None,
                "nClvPinn": len(clvp), "avgClvPinn": round(sum(clvp) / len(clvp), 2) if clvp else None,
                "pctBeatPinn": round(sum(1 for x in clvp if x > 0) / len(clvp), 3) if clvp else None}

    by_scn, by_mkt = {}, {}
    for scn in ("fresh", "ht"):
        rows = [e for e in res if e.get("scenario") == scn]
        if rows:
            by_scn[scn] = agg(rows)
    for mk in sorted({e.get("market") for e in res if e.get("market")}):
        by_mkt[mk] = agg([e for e in res if e.get("market") == mk])

    # 10.08.2026 (Lucas): Split nach Konsens-Zweitmeinung — laufen konsens-BESTAETIGTE Pushs besser als
    # uneinige? Der eigentliche ROI-Hebel: wenn ja, filtert der Konsens die edge-losen Pushs raus.
    def _cv(e):
        c = e.get("consensus")
        return c.get("verdict") if isinstance(c, dict) else None
    by_cons = {}
    for v in ("konsens", "teil", "uneinig", "no_anchor"):
        rows = [e for e in res if _cv(e) == v]
        if rows:
            by_cons[v] = agg(rows)
    cons_split = {}
    agree_rows = [e for e in res if _cv(e) in ("konsens", "teil")]     # Buchmacher bestaetigen die Geld-Seite
    disagree_rows = [e for e in res if _cv(e) == "uneinig"]            # Buchmacher sehen die andere Seite vorn
    if agree_rows:
        cons_split["agree"] = agg(agree_rows)
    if disagree_rows:
        cons_split["disagree"] = agg(disagree_rows)

    recent = [{"home": e.get("home"), "away": e.get("away"), "league": e.get("league"),
               "market": e.get("market"), "leadName": e.get("leadName"), "leadOdd": e.get("leadOdd"),
               "won": e.get("status") == "won", "settledAt": e.get("settledAt")}
              for e in sorted(res, key=lambda x: str(x.get("settledAt") or ""), reverse=True)[:15]]

    out = agg(res)
    out.update({"generatedAt": now.isoformat(), "pending": pend,
                "byScenario": by_scn, "byMarket": by_mkt,
                "byConsensus": by_cons, "consensusSplit": cons_split, "recent": recent})
    return out


def main():
    ledger = _load(LEDGER_FILE, [])
    if not isinstance(ledger, list):
        ledger = []
    prices = _load(BASE / "betfair_prices.json", {})
    ledger = capture_ht(ledger, prices)
    # 07.08.2026: zuerst die Abrechnungen des breiten Tracks erben (realer Endstand, auch fuer Spiele,
    # die DIESER Feed nie als „finished" gesehen hat), dann der eigene Feed-Pfad + TTL-Verfall.
    track_results = _store.load(TRACK_RESULTS_FILE)   # 01.09.2026: kompaktes Format, load() nimmt beide
    ledger = settle_from_track(ledger, track_results)
    ledger = settle(ledger, prices, results_fetch=_fetch_results)
    ledger = verify_settled(ledger, results_fetch=_fetch_results)   # 11.08.2026: autoritative Nachkontrolle (Plymouth-Fall)
    # 11.08.2026 (Lucas): LETZTER Schritt — manuell gepinnte Endstaende (Spiele in keiner Ergebnisquelle,
    # z.B. EFL-Cup, aus dem Feed verschwunden). Schlaegt Feed/Vanish auch bei bereits abgerechneten Zeilen.
    ledger = apply_manual_results(ledger, _load(MANUAL_RESULTS_FILE, {}))
    # abgeschlossene/verworfene lange behalten fürs Ledger, aber deckeln
    ledger = ledger[-LEDGER_KEEP:]
    record = summarize(ledger)
    try:
        json.dump(ledger, open(LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        json.dump(record, open(RECORD_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("Schreibfehler:", e)
    print("Public-Eval: %d abgerechnet (%s%% Treffer, ROI %s) · %d offen"
          % (record["n"], round((record["hitRate"] or 0) * 100), record["roi"], record["pending"]))
    cs = record.get("consensusSplit") or {}
    if cs:
        print("  🧭 Konsens-Split: " + " · ".join(
            "%s n=%d Treffer %s%% ROI %s" % (k, cs[k]["n"], round((cs[k]["hitRate"] or 0) * 100), cs[k]["roi"])
            for k in ("agree", "disagree") if k in cs))


if __name__ == "__main__":
    main()
