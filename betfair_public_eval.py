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
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import betfair_track_store as _store   # 01.09.2026: Ledger liegt kompakt, load() nimmt beide Formate

# Grading aus dem bestehenden Track-Record wiederverwenden (kein Duplikat).
from betfair_track_record import fav_token, winning_token, grade, MARKETS, RESULTS_MIN_H, CORRECTION_WINDOW_H, _clv_pp
# 08.09.2026: die beiden Untergrenzen kommen aus den Stellen, an denen sie schon wohnen —
# Wilson aus `sharp_gate` (dieselbe Definition wie im Whale-Gate und im Frontend), die
# Rendite-Grenze aus `freigabe` (n>=30, sonst None). Keine dritte Rechnung.
from sharp_gate import wilson_lb as _wilson_lb
from freigabe import untergrenze as _untergrenze

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
# 19.09.2026 (Lucas: „wir haben noch nicht die optimale Einstellung … das muessten wir
# rueckrechnen"). Das Schattenbuch der Beinahe-Treffer aus betfair_alerts wird hier mit
# DERSELBEN Mechanik abgerechnet wie ein echter Push — ein zweiter Abrechner waere ein zweites
# Urteil ueber denselben Endstand. Gesendet wurde davon nie etwas.
# 19.09.2026, nachgetragen am selben Abend: das Kursrutsch-Buch wurde geschrieben, aber von
# NIEMANDEM abgerechnet — `zaehler_bf_rutsch` haette bis in alle Ewigkeit 0 gemeldet und die
# vorregistrierte Messung `betfair-kursrutsch` waere nie faellig geworden. Ein Buch ohne
# Abrechnung ist eine Behauptung; genau dafuer steht `check_schattenbuch_fuellt_sich` in der
# Guard-Batterie, und genau daran habe ich beim Bau nicht gedacht.
RUTSCH_FILE = BASE / "betfair_rutsch_ledger.json"
RUTSCH_RECORD_FILE = BASE / "betfair_rutsch_bericht.json"
RUTSCH_KEEP = 800
SCHATTEN_FILE = BASE / "betfair_public_schatten.json"
SCHATTEN_RECORD_FILE = BASE / "betfair_public_schatten_bericht.json"
SCHATTEN_KEEP = 4000


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


def _track_spiel_index(track_results):
    """matchId → irgendeine Zeile des breiten Tracks mit Endstand. Neuere gewinnen.

    🔴 20.09.2026 (Lucas: „sind die dann in der Bilanz richtig drin, es sind immerhin zwei
    Winner"). Vasco da Gama v Coritiba liess sich nicht abrechnen, obwohl der breite Track das
    Spiel kannte: dort lagen FUENF Maerkte mit ft 5:0 — nur ausgerechnet Match Odds fehlte, weil
    `fav_token` an „Vasco Da Gama" gescheitert war und `capture()` das Signal deshalb nie
    angelegt hatte. Der Zeichenvergleich ist repariert, aber fuer die bereits gesendete Zeile
    kommt das zu spaet: ihr Markt steht im Track nicht, und `settle_from_track` sucht exakt
    (matchId, market).

    Der Endstand ist aber eine Eigenschaft des SPIELS, nicht des Marktes. Fehlt der eigene
    Markt, reicht irgendeine Zeile desselben Spiels — fuer ft/ht. NICHT fuer clvBf/clvPinn:
    die Schlusskurse gehoeren dem jeweiligen Markt und duerfen nicht von einem fremden geerbt
    werden. Deshalb traegt dieser Weg ein eigenes `via`."""
    idx = {}
    for r in (track_results or []):
        mid = r.get("matchId")
        if mid is None or r.get("ft") is None:
            continue
        idx[str(mid)] = r
    return idx


def settle_from_track(ledger, track_results, now=None):
    """07.08.2026 (Lucas: „wie kann die Trefferquote klappen aber die Push-Bilanz nicht"): die Push-
    Bilanz erbt die Abrechnungen des breiten Track-Records. Sobald der breite Track ein Spiel abgerechnet
    hat — per „finished" ODER per Verschwinde-Settle — rechnen wir den passenden Push mit dessen realem
    End-/HT-Stand ab, egal ob DIESER Feed je „finished" gezeigt hat. Laeuft im selben betfair.yml-Lauf
    NACH betfair_track_record.py, liest also die frisch geschriebenen Ergebnisse. REIN."""
    now = now or _now()
    idx = _track_index(track_results)
    spiel_idx = _track_spiel_index(track_results)
    for e in ledger:
        if e.get("status") != "pending":
            continue
        row = idx.get((str(e.get("matchId")), e.get("market")))
        if row:
            e["clvBf"] = _clv_pp(e.get("leadOdd"), row.get("odd"))       # 12.08.2026 (Lucas): Push-CLV vs Betfair-Close
            e["clvPinn"] = _clv_pp(e.get("leadOdd"), row.get("pinnClose"))  # + vs Pinnacle-Close (nur abgedeckte Ligen)
            _settle_entry(e, row.get("ft"), row.get("ht"), now, "track")
            continue
        # Eigener Markt nicht im Track — aber der Endstand gehoert dem Spiel (s. _track_spiel_index).
        row = spiel_idx.get(str(e.get("matchId")))
        if row:
            _settle_entry(e, row.get("ft"), row.get("ht"), now, "track-spiel")
    return ledger


# 🔴 15.09.2026 (Lucas: „den public push mit den over 0.5 muessen wir aber entfernen aus allen
# stats oder"). Ja — aber als VOID mit Grund, nicht als Loeschung. Eine Zeile aus dem Buch zu
# nehmen ist genau das, was dieser Flaeche den Wert nimmt; die Zeile bleibt sichtbar und faellt
# aus Zaehler UND Nenner (`void` wird seit dem 08.09. ausgewiesen statt still geschluckt).
#
# Der Fall: „First Half Goals 0.5 · Over 0.5 @1.51", gesendet 15.09. um 14:16 UTC bei Stand 0:1
# in Minute 13. Der Ausgang stand da schon fest. Als „won" gezaehlt haette er die Trefferquote
# mit einer Sicherheit aufgeblasen — und ein geschoenter Track Record ist schlimmer als ein
# schlechter, weil man ihm nicht mehr glauben kann.
VOID_ENTSCHIEDEN = "Ausgang beim Senden bereits entschieden"


def entschieden_beim_senden(e) -> bool:
    """War der Ausgang schon entschieden, als der Push RAUSGING? REIN/testbar.

    Nur der Live-Stand ZUM SENDEZEITPUNKT (`live.score`) zaehlt. `htScore` waere der Halbzeit-
    stand aus der ABRECHNUNG — der sagt nichts darueber, was beim Senden bekannt war, und wer
    ihn hier benutzt, erklaert nachtraeglich Zeilen fuer ungueltig, die damals offen waren.
    Die Linien-Regel selbst steht in betfair_alerts.ausgang_schon_entschieden — EINE Stelle."""
    if not isinstance(e, dict):
        return False
    li = e.get("live") or {}
    sc = li.get("score")
    if not (isinstance(sc, list) and len(sc) >= 2):
        return False
    try:
        from betfair_alerts import ausgang_schon_entschieden
    except Exception:
        return False
    g1, g2 = sc[0], sc[1]
    alert = {"market": e.get("market"), "leadName": e.get("leadName"),
             "live": {"goal_v1": g1 if isinstance(g1, int) else None,
                      "goal_v2": g2 if isinstance(g2, int) else None,
                      "time": li.get("time"), "is_ht": False, "finished": False}}
    return ausgang_schon_entschieden(alert) is True


def void_entschiedene(ledger, now=None) -> int:
    """Schon-entschiedene Zeilen auf void setzen — auch rueckwirkend. Idempotent. REIN/testbar."""
    n = 0
    for e in (ledger or []):
        if not isinstance(e, dict):
            continue
        if e.get("voidGrund") == VOID_ENTSCHIEDEN:
            continue                      # schon erledigt
        if not entschieden_beim_senden(e):
            continue
        e["status"] = "void"
        e["profit"] = 0.0
        e["voidGrund"] = VOID_ENTSCHIEDEN
        if now is not None:
            e["settledAt"] = now.isoformat()
        n += 1
    return n


def _grade_ledger_entry(e, ft, ht, now):
    """Einen pending-Push gegen den Endstand abrechnen (status won/lost/void + profit setzen). REIN."""
    if entschieden_beim_senden(e):
        e["settledAt"] = now.isoformat()
        e["ftScore"] = ft
        e["status"] = "void"
        e["profit"] = 0.0
        e["voidGrund"] = VOID_ENTSCHIEDEN
        return
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


_PUSH_KEY = re.compile(r"^(fresh|ht|fix):\d+$")


def gesendet_ohne_beleg(seen, ledger) -> list:
    """Push-Schluessel im Dedup-Stand, zu denen KEINE Ledger-Zeile existiert. REIN. -> sortiert.

    🔴 20.09.2026 (Lucas: „Beide Spiele stehen nicht in der Betfair-Public-Bilanz"). Lyon v
    Rennes war gesendet — betfair_public_seen.json trug `fresh:36039873`, und diesen Schluessel
    bekommt ein Spiel nur bei erfolgreichem Versand. Eine Ledger-Zeile gab es nie, in keinem der
    letzten 40 Commits. Ueber alle Eintraege: 4 von 277 (1,4 %).

    Nachtragen kann man sie nicht: von einem verlorenen Push existiert nur der Schluessel —
    Markt, Seite und vor allem die QUOTE beim Senden stehen nirgends. Eine Zeile mit
    geschaetzter Quote waere ein erfundener Beleg.
    Und eine EINZELNE nachzutragen waere noch schlechter: Lucas ist Lyon aufgefallen, weil es
    gewonnen hat. Genau die Zeilen zurueckzuholen, die jemandem auffallen, ist eine Auswahl
    nach Ausgang — die Bilanz sieht danach besser aus, ohne es zu sein.

    Also bleibt die Luecke, aber sie wird SICHTBAR: die Bilanz sagt ab jetzt selbst, wie viele
    Pushes sie nicht kennt. Eine Zahl, die ihre eigene Unvollstaendigkeit nennt, ist ehrlicher
    als eine, die sie verschweigt."""
    have = {"%s:%s" % (e.get("scenario"), e.get("matchId")) for e in (ledger or [])
            if isinstance(e, dict)}
    fehlt = [str(k) for k in (seen or {})
             if _PUSH_KEY.match(str(k)) and str(k) not in have]
    return sorted(fehlt)


# Jede Reparatur am Beleg-Pfad mit Datum und Grund. Die JUENGSTE ist die Grenze: ein datierter
# Verlust davor ist eine Narbe, einer danach ein Befund. Wer hier nichts eintraegt, bekommt einen
# Alarm, der von einem laengst behobenen Fall dauerhaft rot bleibt — und einen dauerhaft roten
# Alarm liest niemand mehr. Ein Eintrag ohne Grund ist keiner (Test).
REPARATUREN = [
    ("2026-09-20T00:00:00+00:00",
     "Beleg wird sofort nach dem Senden committet (scripts/ci_sichern.sh) statt zwoelf Schritte "
     "spaeter — die vier undatierten Verluste"),
    ("2026-09-22T05:14:00+00:00",
     "Die Ledger-Zeile entsteht in zwei Schritten: erst der Kern, dann die Anreicherung. Vorher "
     "riss ein werfendes `_consensus_for_push`/`_serie_fuer_push` den ganzen Beleg mit — der "
     "fuenfte Verlust, `fresh:36041720`, 21.09.2026 22:46"),
]


def letzte_reparatur() -> str:
    """Der Zeitpunkt, ab dem ein Verlust ein Befund ist. REIN."""
    return max(t for t, _ in REPARATUREN)


def gesendet_ohne_beleg_datiert(seen, ledger, ab=None) -> list:
    """Die Verluste, die NACH der Reparatur passiert sind. REIN. -> [{"key","t"}], neueste zuerst.

    🔴 20.09.2026, zweiter Teil. Die Ursache der vier verlorenen Zeilen ist gefunden und
    behoben: `betfair_alerts.py` sendet und schreibt den Beleg sofort, der Commit dafuer stand
    aber zwoelf Schritte und einen 12-Minuten-Schlaf spaeter, bei einem 15-Minuten-Takt. Seit
    heute sichert `scripts/ci_sichern.sh` ihn direkt nach dem Senden.
    Gegenprobe zum Roll-over-Verdacht: das Ledger haelt 282 von erlaubten 800 Zeilen, und alle
    vier fehlenden matchIds liegen INNERHALB seines Bereichs (35.667.446 … 36.077.729). Sie
    sind nicht herausgerollt, sie wurden nie geschrieben.

    Ob die Reparatur haelt, war damit aber noch nicht messbar: die Zahl stand bei 4 und ginge
    bei einem fuenften Verlust auf 5 — in einer Warn-Zeile sieht das niemand.
    Fehlerklasse: eine Narbe und eine frische Wunde in derselben Zahl.

    Der Dedup-Stand stempelt ab heute die Sendezeit. Vorher wurde nicht gestempelt, also ist
    jeder DATIERTE Eintrag ohne Beleg einer von NACH der Reparatur — kein gepflegter
    Ausnahmen-Katalog, der in drei Wochen niemand mehr anfasst.
    """
    ab = ab or letzte_reparatur()
    raus = []
    for k in gesendet_ohne_beleg(seen, ledger):
        rec = (seen or {}).get(k)
        t = rec.get("t") if isinstance(rec, dict) else None
        # 🔴 23.09.2026: „datiert" hiess bisher „nach der Reparatur". Das stimmte genau einen Tag.
        # Der fuenfte Verlust (`fresh:36041720`, 21.09. 22:46) hatte eine ANDERE Ursache — die
        # Anreicherung riss die Zeile mit — und die wurde am 22.09. 05:14 behoben. Er blieb
        # trotzdem als „frische Wunde" stehen, und die Meldung sagte weiter „der Sicherungsschritt
        # greift nicht" ueber einen Fall, den der heutige Code nicht mehr erzeugen kann.
        # Fehlerklasse: ein Alarm, der nie wieder ausgeht, ist keiner — ab dann liest ihn niemand.
        # Die Grenze ist deshalb die LETZTE Reparatur, nicht die erste, und sie wandert mit.
        if t and str(t) >= ab:
            raus.append({"key": k, "t": str(t)})
    return sorted(raus, key=lambda z: z["t"], reverse=True)


def gesendet_ohne_beleg_narbe(seen, ledger, ab=None) -> list:
    """Die alten Verluste — undatiert oder VOR der letzten Reparatur. REIN. -> [key]

    Sie gehoeren in die Bilanz (eine Luecke, die man nennt, ist ehrlicher als eine, die man
    verschweigt), aber nicht in den Alarm. Getrennt ausgewiesen, damit die Meldung nicht vier
    zaehlt und fuenf Schluessel darunter druckt.
    """
    frisch = {z["key"] for z in gesendet_ohne_beleg_datiert(seen, ledger, ab)}
    return [k for k in gesendet_ohne_beleg(seen, ledger) if k not in frisch]


def summarize(ledger, now=None):
    now = now or _now()
    res = [e for e in ledger if e.get("status") in ("won", "lost")]
    pend = sum(1 for e in ledger if e.get("status") == "pending")
    # 08.09.2026: `expired` und `void` fielen bisher still aus dem Nenner — 17 bzw. 1 von 210
    # Ledger-Zeilen. Das Board zeigte „offen: 2" und verschwieg die 17, die NIE ein Ergebnis
    # bekommen haben. Das Poly-Board weist seine `unaufloesbar` aus; dieses tat es nicht.
    verfallen = sum(1 for e in ledger if e.get("status") == "expired")
    ungueltig = sum(1 for e in ledger if e.get("status") == "void")

    def agg(rows):
        n = len(rows)
        wins = sum(1 for e in rows if e.get("status") == "won")
        profit = sum(float(e.get("profit") or 0) for e in rows)
        odds = [float(e["leadOdd"]) for e in rows if isinstance(e.get("leadOdd"), (int, float))]
        clvb = [e["clvBf"] for e in rows if isinstance(e.get("clvBf"), (int, float))]
        clvp = [e["clvPinn"] for e in rows if isinstance(e.get("clvPinn"), (int, float))]
        # 🔴 08.09.2026 (Lucas: „ob das alles reibungslos funktioniert"). Das GROESSTE Push-Buch
        # im Repo (n=190) trug als einziges KEINE Untergrenze — weder hier noch auf dem Board.
        # Angezeigt wurden „58 % Treffer" und „ROI −2,6 %" als nackte Punktschaetzer, in genau
        # dem Repo, dessen eigene Regel lautet: ein Punktschaetzer ohne Untergrenze belegt
        # nichts. Das kleinste Buch (Poly Public, n=9) macht es seit dem 03.09. richtig.
        # Beides kommt aus vorhandenen Bausteinen: Wilson fuer die Quote, `untergrenze` fuer
        # die Rendite (n>=30, sonst None — eine „UG" aus drei Plays ist schlimmer als keine).
        _profite = [float(e.get("profit") or 0) for e in rows]
        _roi_ug = _untergrenze(_profite)
        return {"n": n, "wins": wins,
                "hitRate": round(wins / n, 4) if n else None,
                "hitUg": round(_wilson_lb(wins, n), 4) if n else None,
                "roi": round(profit / n, 4) if n else None,
                "roiUg": round(_roi_ug, 4) if _roi_ug is not None else None,
                # `belegt` ist die eine Zahl, auf die man schaut: die Rendite-Untergrenze ueber
                # null. Ohne sie ist ein positiver ROI eine Beobachtung, kein Beleg.
                "belegt": bool(_roi_ug is not None and _roi_ug > 0),
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
                "verfallen": verfallen, "ungueltig": ungueltig,
                "byScenario": by_scn, "byMarket": by_mkt,
                "byConsensus": by_cons, "consensusSplit": cons_split, "recent": recent})
    return out


RUTSCH_VOID_LIVE = ("live gesendet, bevor der Alarm auf Vor-Anpfiff beschraenkt wurde "
                    "(19.09.2026) — die Messung beschreibt ausschliesslich Vor-Anpfiff-Daten")


def void_live_rutsch(buch, grund=RUTSCH_VOID_LIVE) -> int:
    """Kursrutsch-Zeilen aus LAUFENDEN Spielen auf void setzen. REIN, idempotent. -> Anzahl.

    🔴 19.09.2026. Die ersten sechs Alarme kamen alle aus laufenden Spielen (22., 63., 44., 40.,
    38., 45. Minute), gemessen wurden aber ausschliesslich Vor-Anpfiff-Daten. Der Alarm ist
    seither gesperrt — die Zeilen stehen trotzdem im Buch und wuerden die vorregistrierte
    Messung von Anfang an verderben.

    Warum als REGEL und nicht als einmalige Korrektur an der Datei: die Datei gehoert der
    Pipeline und wird bei jedem Lauf neu geschrieben. Eine von Hand gesetzte Markierung
    ueberlebt den naechsten Lauf nicht zwingend — genau das ist heute Abend einmal passiert.
    Dieselbe Bauweise wie `void_entschiedene`: wirkt bei jedem Lauf neu, auch rueckwirkend."""
    n = 0
    for e in (buch or []):
        if not isinstance(e, dict) or e.get("status") == "void":
            continue
        if ((e.get("live") or {}).get("time")) is not None:
            e["status"] = "void"
            e["voidGrund"] = grund
            n += 1
    return n


def nachgrade_ungeklaerte(buch) -> int:
    """void OHNE Grund heisst „konnte nicht abgerechnet werden" — das wird bei jedem Lauf neu
    versucht. REIN, idempotent. -> Anzahl der zurueckgesetzten Zeilen.

    🔴 20.09.2026 (Lucas: „Beide Spiele stehen nicht in der Betfair-Public-Bilanz. Beide haben
    gewonnen."). Vasco da Gama gewann 5:0, gewettet zu 1.37 — die Zeile stand auf void, weil
    `fav_token` den Runner „Vasco Da Gama" nicht auf das Heimteam „Vasco da Gama" abbilden
    konnte (grosses D). Der Zeichenvergleich ist seit heute normalisiert, aber die Zeile waere
    trotzdem fuer immer void geblieben: `_grade_ledger_entry` setzt void und schreibt KEINEN
    Grund, und void ist sonst endgueltig.

    Ein „nicht abrechenbar" ist aber kein Urteil ueber die Wette, sondern eins ueber uns. Es
    gehoert wiederholt, sobald wir es besser koennen. Ein void MIT Grund (VOID_ENTSCHIEDEN,
    Kursrutsch-Live) ist dagegen eine Entscheidung und bleibt stehen."""
    n = 0
    for e in (buch or []):
        if not isinstance(e, dict):
            continue
        if e.get("status") == "void" and not e.get("voidGrund"):
            e["status"] = "pending"
            e.pop("settledAt", None)
            n += 1
    return n


def abrechnen(buch, prices, track_results, manual=None, keep=LEDGER_KEEP):
    """Ein Push-Buch durch die ganze Abrechnungskette schicken. Genau die Reihenfolge, die
    main() seit dem 15.09. faehrt — als Funktion, damit das Schattenbuch nicht seine eigene
    bekommt und dann irgendwann anders rechnet als das echte."""
    nachgrade_ungeklaerte(buch)     # „nicht abrechenbar" ist kein Urteil, sondern ein Versuch
    buch = capture_ht(buch, prices)
    buch = settle_from_track(buch, track_results)
    buch = settle(buch, prices, results_fetch=_fetch_results)
    buch = verify_settled(buch, results_fetch=_fetch_results)
    buch = apply_manual_results(buch, manual if manual is not None else _load(MANUAL_RESULTS_FILE, {}))
    nvoid = void_entschiedene(buch)
    return buch[-keep:], nvoid


def main():
    ledger = _load(LEDGER_FILE, [])
    if not isinstance(ledger, list):
        ledger = []
    prices = _load(BASE / "betfair_prices.json", {})
    # 07.08.2026: zuerst die Abrechnungen des breiten Tracks erben (realer Endstand, auch fuer Spiele,
    # die DIESER Feed nie als „finished" gesehen hat), dann der eigene Feed-Pfad + TTL-Verfall.
    # Die ganze Kette steht seit dem 19.09. in `abrechnen()` — EINMAL, damit das Schattenbuch
    # nicht seine eigene Reihenfolge bekommt und irgendwann anders rechnet als das echte Buch.
    track_results = _store.load(TRACK_RESULTS_FILE)   # 01.09.2026: kompaktes Format, load() nimmt beide
    ledger, _nv = abrechnen(ledger, prices, track_results)
    if _nv:
        print("  🔇 %d Zeile(n) auf void gesetzt: %s" % (_nv, VOID_ENTSCHIEDEN))
    record = summarize(ledger)
    try:
        json.dump(ledger, open(LEDGER_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        json.dump(record, open(RECORD_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("Schreibfehler:", e)
    print("Public-Eval: %d abgerechnet (%s%% Treffer, ROI %s) · %d offen"
          % (record["n"], round((record["hitRate"] or 0) * 100), record["roi"], record["pending"]))
    # ── das Schattenbuch: dieselbe Kette, nie gesendet ────────────────────────────────
    try:
        schatten = _load(SCHATTEN_FILE, [])
        if isinstance(schatten, list) and schatten:
            schatten, _ = abrechnen(schatten, prices, track_results, keep=SCHATTEN_KEEP)
            sbericht = summarize(schatten)
            json.dump(schatten, open(SCHATTEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            json.dump(sbericht, open(SCHATTEN_RECORD_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print("  🕯️  Schatten-Eval: %d abgerechnet (%s%% Treffer, ROI %s) · %d offen"
                  % (sbericht["n"], round((sbericht["hitRate"] or 0) * 100),
                     sbericht["roi"], sbericht["pending"]))
    except Exception as _e:
        print("  ⚠️  Schattenbuch nicht abgerechnet:", _e)

    # ── das Kursrutsch-Buch: dieselbe Kette, nur Trades ───────────────────────────────
    try:
        rutsch = _load(RUTSCH_FILE, [])
        if isinstance(rutsch, list) and rutsch:
            rutsch, _ = abrechnen(rutsch, prices, track_results, keep=RUTSCH_KEEP)
            _nl = void_live_rutsch(rutsch)
            if _nl:
                print("  \U0001f507 %d Kursrutsch-Zeile(n) auf void: live gesendet, vor der "
                      "Vor-Anpfiff-Sperre" % _nl)
            rbericht = summarize(rutsch)
            json.dump(rutsch, open(RUTSCH_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            json.dump(rbericht, open(RUTSCH_RECORD_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print("  \U0001f4c9 Kursrutsch-Eval: %d abgerechnet (%s%% Treffer, ROI %s) · %d offen"
                  % (rbericht["n"], round((rbericht["hitRate"] or 0) * 100),
                     rbericht["roi"], rbericht["pending"]))
    except Exception as _e:
        print("  ⚠️  Kursrutsch-Buch nicht abgerechnet:", _e)

    # 20.09.2026: die Bilanz nennt ihre eigene Luecke (s. gesendet_ohne_beleg).
    try:
        _seen = _load(BASE / "betfair_public_seen.json", {})
        _ohne = gesendet_ohne_beleg(_seen if isinstance(_seen, dict) else {}, ledger)
        record["gesendetOhneBeleg"] = len(_ohne)
        record["gesendetOhneBelegKeys"] = _ohne[:20]
        # Getrennt ausgewiesen: die alte Narbe (undatiert) und alles, was NACH der Reparatur
        # verloren ging. Nur das zweite ist ein Befund.
        _neu = gesendet_ohne_beleg_datiert(_seen if isinstance(_seen, dict) else {}, ledger)
        record["gesendetOhneBelegNeu"] = len(_neu)
        record["gesendetOhneBelegNeuKeys"] = _neu[:10]
        # Die Narbe getrennt: sonst zaehlt die Meldung die alten und druckt ALLE Schluessel.
        _narbe = gesendet_ohne_beleg_narbe(_seen if isinstance(_seen, dict) else {}, ledger)
        record["gesendetOhneBelegAltKeys"] = _narbe[:20]
        record["belegReparaturAb"] = letzte_reparatur()
        if _ohne:
            print("  ⚠️  %d gesendete(r) Push(es) ohne Ledger-Zeile: %s"
                  % (len(_ohne), ", ".join(_ohne[:6])))
            json.dump(record, open(RECORD_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    except Exception as _e:
        print("  ⚠️  Beleg-Pruefung uebersprungen:", _e)

    cs = record.get("consensusSplit") or {}
    if cs:
        print("  🧭 Konsens-Split: " + " · ".join(
            "%s n=%d Treffer %s%% ROI %s" % (k, cs[k]["n"], round((cs[k]["hitRate"] or 0) * 100), cs[k]["roi"])
            for k in ("agree", "disagree") if k in cs))


if __name__ == "__main__":
    main()
