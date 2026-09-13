#!/usr/bin/env python3
"""stats_perioden.py — alle Ströme auf Wochen-, Monats- und Gesamtbasis (09.09.2026).

Lucas: „schaffen wir eine eigene Stats-Seite? Im Mehr-Menü einfach Stats, und dort alles rein
was geht — Cards, Betfair, Poly, Push-Channels usw. Alles auf Monatsbasis und Wochenbasis auch.
Schön modern dargestellt, weil brauch das um es zu posten."

Diese Datei rechnet, das Frontend zeichnet. Kein Netz, keine Seiteneffekte ausser dem Artefakt.

⭐ DIE ZWEI SÄTZE, AN DENEN SO EINE SEITE SONST SCHEITERT

1. EINE PERIODE OHNE ABDECKUNG IST KEINE PERIODE.
   Der Betfair-Ledger haelt nur ein rollierendes Fenster: er reicht am 09.09. bis zum 26.08.
   zurueck. Ein Balken „August" waere damit nicht der August, sondern seine letzte Woche — und
   saehe im Vergleich zum September aus wie ein schwacher Monat statt wie ein halber. Jede Zeile
   traegt deshalb `vollstaendig` und, wenn sie es nicht ist, warum. Das ist dieselbe Klasse wie
   „fehlende Information rendert als harmloser Default", nur auf der Zeitachse.

2. EINE TREFFERQUOTE OHNE DIE QUOTEN IST KEINE ZAHL.
   Steht in diesem Repo an genug Stellen. Jeder Block liefert deshalb ROI je Periode, wo es
   Quoten gibt — und sagt es ausdruecklich, wo nicht. Zusaetzlich die Wilson-Untergrenze: bei
   n=12 in einer Woche ist der Punktschaetzer Dekoration.

Post-Modus: die Seite kann Quoten und Betraege ausblenden (Lucas postet Screenshots). Das ist
reine Anzeige — hier wird nichts weggelassen, damit nicht zwei Wahrheiten entstehen.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_FILE = "stats_perioden.json"

WOCHEN_ZURUECK = int(os.environ.get("STATS_WOCHEN") or 8)
Z = 1.645          # einseitige 95-%-Grenze, wie ueberall hier
UG_MIN_N = 30      # darunter gibt es keine Untergrenze, nur den Schnitt


def _now():
    return datetime.now(timezone.utc)


def _load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _tag(x):
    """ISO-String -> 'YYYY-MM-DD' oder None. Unlesbar heisst None, nicht heute."""
    if not x:
        return None
    s = str(x)[:10]
    try:
        date.fromisoformat(s)
    except ValueError:
        return None
    return s


def woche_von(tag: str) -> str:
    """ISO-Kalenderwoche eines Tages: '2026-W37'. REIN."""
    j, w, _ = date.fromisoformat(tag).isocalendar()
    return "%04d-W%02d" % (j, w)


def monat_von(tag: str) -> str:
    return tag[:7]


def wochen_spanne(schluessel: str):
    """('YYYY-MM-DD','YYYY-MM-DD') — Montag und Sonntag dieser ISO-Woche. REIN."""
    j, w = int(schluessel[:4]), int(schluessel[6:])
    mo = date.fromisocalendar(j, w, 1)
    return mo.isoformat(), (mo + timedelta(days=6)).isoformat()


def monats_spanne(schluessel: str):
    j, m = int(schluessel[:4]), int(schluessel[5:7])
    erst = date(j, m, 1)
    letzt = date(j + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    return erst.isoformat(), letzt.isoformat()


def wilson_ug(treffer, n, z: float = Z):
    """Einseitige Wilson-Untergrenze eines Anteils. Dieselbe Definition wie in sharp_gate."""
    n = int(n or 0)
    if n <= 0:
        return None
    ph = (treffer or 0) / n
    d = 1 + z * z / n
    mitte = (ph + z * z / (2 * n)) / d
    rand = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return mitte - rand


def mittel_ug(werte, z: float = Z, min_n: int = UG_MIN_N):
    """Einseitige Untergrenze eines Mittelwerts. None unter `min_n` — ohne Streuung waere die
    Schranke der Punktschaetzer mit einem Etikett davor."""
    n = len(werte)
    if n < max(3, min_n):
        return None
    m = sum(werte) / n
    var = sum((x - m) ** 2 for x in werte) / (n - 1)
    return m - z * math.sqrt(var) / math.sqrt(n)


# ── Eine Zeile aus einer Menge Plays ────────────────────────────────────────────────────
def kennzahlen(plays) -> dict:
    """{n, treffer, hitPct, hitUg, roi, roiUg, pl, clv, mitQuote} aus Play-Dicts. REIN.

    Ein Play: {"tag": 'YYYY-MM-DD', "gewonnen": bool|None, "rendite": float|None,
               "clv": float|None}. `rendite` ist die Rendite JE EINHEIT Einsatz (pnl/stake),
    nicht die Summe — nur so misst die Streuung das, was sie messen soll.
    """
    n = len(plays)
    gew = [p for p in plays if isinstance(p.get("gewonnen"), bool)]
    treffer = sum(1 for p in gew if p["gewonnen"])
    ren = [float(p["rendite"]) for p in plays if isinstance(p.get("rendite"), (int, float))]
    clv = [float(p["clv"]) for p in plays if isinstance(p.get("clv"), (int, float))]
    aus = {"n": n, "treffer": treffer if gew else None,
           "hitPct": round(100.0 * treffer / len(gew), 1) if gew else None,
           "hitUg": None, "roi": None, "roiUg": None, "pl": None, "clv": None,
           # ⚠️ Ohne Quoten gibt es keinen ROI — und das muss die Zeile SAGEN, sonst liest man
           # eine fehlende Zahl als „null Rendite".
           "mitQuote": len(ren), "mitClv": len(clv)}
    if gew:
        _u = wilson_ug(treffer, len(gew))
        aus["hitUg"] = round(100 * _u, 1) if _u is not None else None
    if ren:
        aus["roi"] = round(100.0 * sum(ren) / len(ren), 1)
        aus["pl"] = round(sum(ren), 2)
        _r = mittel_ug(ren)
        aus["roiUg"] = round(100 * _r, 1) if _r is not None else None
    if clv:
        aus["clv"] = round(sum(clv) / len(clv), 2)
    return aus


def _abdeckung(plays):
    tage = sorted(p["tag"] for p in plays if p.get("tag"))
    return (tage[0], tage[-1]) if tage else (None, None)


def perioden_reihen(plays, heute: str) -> list:
    """Je Woche (letzte WOCHEN_ZURUECK), je Monat und Gesamt eine Zeile. REIN.

    ⭐ `vollstaendig` ist der Kern. Eine Periode gilt nur dann als vollstaendig, wenn die
    QUELLE sie ganz abdeckt — also ihr erster Tag nicht vor dem ersten Tag der Quelle liegt und
    ihr letzter Tag nicht in der Zukunft. Sonst steht ein halber August neben einem ganzen
    September und sieht aus wie ein schwacher Monat.
    """
    plays = [p for p in (plays or []) if p.get("tag")]
    von, bis = _abdeckung(plays)
    reihen = []
    if not plays:
        return reihen

    def _zeile(schluessel, art, p_von, p_bis, teil):
        k = kennzahlen(teil)
        voll = bool(von and p_von >= von and p_bis <= heute)
        k.update({"periode": schluessel, "art": art, "von": p_von, "bis": p_bis,
                  "vollstaendig": voll})
        if not voll:
            k["grund"] = ("läuft noch" if p_bis > heute else
                          "die Datenquelle reicht nur bis %s zurück" % von)
        return k

    heute_d = date.fromisoformat(heute)
    for i in range(WOCHEN_ZURUECK - 1, -1, -1):
        tag = (heute_d - timedelta(weeks=i)).isoformat()
        w = woche_von(tag)
        wv, wb = wochen_spanne(w)
        if wb < von:
            continue                       # ganz vor der Abdeckung: gar keine Zeile, keine Null
        teil = [p for p in plays if wv <= p["tag"] <= wb]
        reihen.append(_zeile(w, "woche", wv, wb, teil))
    for m in sorted({p["tag"][:7] for p in plays}):
        mv, mb = monats_spanne(m)
        teil = [p for p in plays if mv <= p["tag"] <= mb]
        reihen.append(_zeile(m, "monat", mv, mb, teil))
    ges = kennzahlen(plays)
    ges.update({"periode": "gesamt", "art": "gesamt", "von": von, "bis": bis,
                "vollstaendig": True})
    reihen.append(ges)
    return reihen


# ── Die Quellen ─────────────────────────────────────────────────────────────────────────
def cards_plays(datensatz=None) -> list:
    """Abgerechnete Engine-Picks. Nutzt `freigabe._card_plays` — eine Quelle, nicht zwei."""
    try:
        import freigabe as F
        rows = F._card_plays()
    except Exception:
        return []
    aus = []
    for r in rows:
        if datensatz and r.get("ds") != datensatz:
            continue
        t = _tag(r.get("ts"))
        if not t:
            continue
        aus.append({"tag": t, "rendite": r.get("r"), "clv": r.get("clv"),
                    "gewonnen": (r.get("r") > 0) if isinstance(r.get("r"), (int, float)) else None})
    return aus


def betfair_plays(zeilen=None) -> list:
    """Abgerechnete Betfair-Signale aus dem Ledger."""
    if zeilen is None:
        try:
            import betfair_track_store as S
            zeilen = S.load(str(BASE / "betfair_track_results.json"))
        except Exception:
            return []
    aus = []
    for r in (zeilen or []):
        t = _tag(r.get("settledAt"))
        o = r.get("odd") or r.get("entryOdd")
        if not t or not isinstance(o, (int, float)) or o <= 1.0:
            continue
        aus.append({"tag": t, "gewonnen": bool(r.get("win")),
                    "rendite": (float(o) - 1.0) if r.get("win") else -1.0,
                    "clv": r.get("clvBf")})
    return aus


def _row_cat(r):
    """Kategorie einer Zeile ueber den kanonischen Helfer, nicht ueber das rohe Feld.

    Nicht jede Zeile traegt einen `cat`-Stempel; `poly_shortlist_track._row_cat` leitet ihn dann
    aus der Liga ab. Ohne ihn landete eine ungestempelte UFC-Zeile in der bespielbaren Bilanz —
    genau der Fehler, gegen den `tests/test_shortlist_kategorie.py` einen Waechter haelt. Der hat
    hier beim ersten Lauf zugeschlagen.
    """
    try:
        from poly_shortlist_track import _row_cat as _rc
    except Exception:
        return r.get("cat")
    return _rc(r)


def poly_plays(track=None) -> list:
    d = track if track is not None else _load("poly_shortlist_track.json")
    st = (d or {}).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else st
    gesperrt = set((d or {}).get("blockedCats") or [])
    aus = []
    for r in st:
        t = _tag(r.get("settledTs"))
        # Gesperrte Sportarten laufen als reine Beobachtung — sie gehoeren nicht in eine Bilanz
        # dessen, was gespielt werden darf. Dieselbe Trennung wie im Track-Record.
        if not t or (_row_cat(r) in gesperrt):
            continue
        stake = r.get("stake")
        ren = (float(r["pnl"]) / float(stake)) if (isinstance(r.get("pnl"), (int, float))
                                                   and isinstance(stake, (int, float)) and stake) else None
        aus.append({"tag": t, "gewonnen": (r.get("result") == "win") if r.get("result") else None,
                    "rendite": ren, "clv": r.get("clvPP"),
                    "public": bool(r.get("public"))})
    return aus


def _push_plays(rows, ts_feld, quote_feld, win_fn, clv_feld=None) -> list:
    """Ein Push-Ledger -> Plays. Ein Push ohne Ergebnis zaehlt als Zeile OHNE Treffer:
    er ist gesendet worden, das ist die eine Zahl, die immer stimmt."""
    aus = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        t = _tag(r.get(ts_feld))
        if not t:
            continue
        w = win_fn(r)
        o = r.get(quote_feld) if quote_feld else None
        ren = None
        if isinstance(w, bool) and isinstance(o, (int, float)) and o > 1.0:
            ren = (float(o) - 1.0) if w else -1.0
        aus.append({"tag": t, "gewonnen": w, "rendite": ren,
                    "clv": r.get(clv_feld) if clv_feld else None})
    return aus


def shortlist_push_plays(ledger=None, track=None) -> list:
    """Die Shortlist-Pushes mit ihrem Ausgang. REIN (beide Quellen injizierbar).

    Zwei Quellen, klar getrennte Rollen — und genau so muss es sein:
      · `shortlist_push_ledger.json` sagt, WANN und ZU WELCHEM PREIS gepusht wurde.
      · `poly_shortlist_track.json` sagt, wie es AUSGEGANGEN ist.

    Die Abrechnung wird NICHT nachgebaut. Das Track-Buch weiss seit dem 10.09., wann ein
    Buendel-Markt ueberhaupt entscheiden darf (poly_slug_urteil); eine zweite Abrechnung hier
    haette diese Regel nicht — und zwei Buecher mit zwei Regeln waren schon einmal der Fehler.

    Ein Push ohne Ausgang zaehlt als Zeile OHNE Treffer: er ist gesendet worden, das ist die eine
    Zahl, die immer stimmt. Ein Push ohne brauchbaren Preis bekommt keine Rendite, keine Null.
    """
    rows = ledger if ledger is not None else _load("shortlist_push_ledger.json", [])
    rows = rows if isinstance(rows, list) else []
    tr = track if track is not None else _load("poly_shortlist_track.json", {})
    st = (tr or {}).get("settled") or []
    st = list(st.values()) if isinstance(st, dict) else st
    erg = {}
    for r in st:
        if isinstance(r, dict) and r.get("key") and r.get("side") and r.get("result"):
            erg["%s|%s" % (r["key"], r["side"])] = (r["result"] == "win")
    aus = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = _tag(r.get("sentAt"))
        if not t:
            continue
        w = erg.get(r.get("k") or "%s|%s" % (r.get("key"), r.get("side")))
        preis = r.get("pushPreis")
        ren = None
        if isinstance(w, bool) and isinstance(preis, (int, float)) and 0 < preis < 1:
            # Aktien = Einsatz/Preis, der Gewinner zahlt 1.00 je Aktie — dieselbe Rechnung wie
            # im Track-Buch, nur mit dem Push-Preis statt dem Scan-Preis.
            ren = (1.0 / float(preis) - 1.0) if w else -1.0
        aus.append({"tag": t, "gewonnen": w, "rendite": ren, "clv": None})
    return aus


def push_bloecke() -> list:
    """Je Kanal ein Block. Die Ledger tragen alle einen Sende-Zeitstempel und einen Status —
    gebucht wird nach dem SENDEDATUM, denn das ist die Handlung, um die es geht."""
    aus = []
    bl = _load("betfair_public_ledger.json", [])
    aus.append(("bf-public", "Betfair · Public-Channel", "🟣", _push_plays(
        bl if isinstance(bl, list) else [], "sentAt", "leadOdd",
        lambda r: True if r.get("status") == "won" else (False if r.get("status") == "lost" else None)), None))
    # Der Whale-Kanal fuehrt keine Quote, aber ein P&L bei festem Einsatz ($10) — das IST die
    # Rendite je Einheit. Aus `pushPrice` waere sie nur rekonstruiert, und in 11 von 23 Zeilen
    # fehlt der Preis ganz.
    wl = _load("poly_whale_public_ledger.json", [])
    _wr = []
    for r in (wl if isinstance(wl, list) else []):
        t = _tag(r.get("sentAt"))
        if not t:
            continue
        _w = True if r.get("result") == "win" else (False if r.get("result") == "loss" else None)
        _pnl, _st = r.get("pnl"), r.get("stake") or 10.0
        _wr.append({"tag": t, "gewonnen": _w,
                    "rendite": (float(_pnl) / float(_st)) if isinstance(_pnl, (int, float)) else None,
                    "clv": None})
    aus.append(("whale-public", "Poly-Whales · Public-Channel", "🐋", _wr, None))
    kp = _load("killer_push_ledger.json", [])
    aus.append(("killer", "Konjunktion · Trades", "🔒", _push_plays(
        kp if isinstance(kp, list) else [], "gepushtAm", "pushPreis",
        lambda r: r.get("win") if isinstance(r.get("win"), bool) else None), None))
    # 🔴 10.09.2026 (Lucas: „was ist Liga-Picks Trades?") — HIER STAND DAS FALSCHE BUCH.
    #
    # `pick_push_ledger.json` ist ein SCHATTENBUCH und soll es sein: es schreibt jeden
    # announce-faehigen Pick mit, den gesendeten UND den vom Gegensignal-Filter aussortierten,
    # damit der Filter sich nicht selbst bestaetigen kann (s. pick_push_ledger.py). Genau das
    # macht es als Quelle fuer einen PUSH-KANAL untauglich:
    #
    #     Liga   131 Zeilen  ->   42 gepusht,   89 nie
    #     MLS     44 Zeilen  ->    6 gepusht,   38 nie
    #
    # 127 Picks standen damit in der Gruppe „Push-Kanäle", die nie in einem Push waren. Dieselbe
    # Fehlerklasse wie beim Public-Block heute frueh: der Name verspricht eine Menge, die Zahl
    # enthaelt eine andere. Ein Kanal-Block zaehlt, was den Kanal verlassen hat — sonst misst er
    # die Engine und nennt es Kanal.
    #
    # ⭐ Die Aussortierten verschwinden nicht: der Hinweis nennt ihre Zahl, und die Gegenprobe
    # („waren die Aussortierten in Wahrheit gut?") steht dort, wo sie hingehoert — als eigene
    # Schublade im Freigabe-Register, nach denselben Regeln beurteilt wie jede andere.
    for datei, name in (("liga_pick_push_ledger.json", "Liga-Picks · Trades"),
                        ("mls_pick_push_ledger.json", "MLS-Picks · Trades")):
        pl = _load(datei, [])
        rows = pl if isinstance(pl, list) else (pl.get("zeilen") or [])
        rows = [r for r in rows if isinstance(r, dict)]
        gepusht = [r for r in rows if r.get("push")]
        _hinweis = None
        if len(rows) > len(gepusht):
            _hinweis = ("Nur was wirklich rausging: %d von %d announce-fähigen Picks. Die %d "
                        "aussortierten führt das Schattenbuch weiter — sie stehen als Gegenprobe "
                        "im Freigabe-Register, nicht in der Kanal-Bilanz."
                        % (len(gepusht), len(rows), len(rows) - len(gepusht)))
        aus.append((datei.split("_")[0] + "-picks", name, "🎯", _push_plays(
            gepusht, "gesehenAm", "odds",
            lambda r: r.get("win") if isinstance(r.get("win"), bool) else None), _hinweis))
    # 🔴 10.09.2026 (Lucas: „wird das erst seit kurzem getrackt? weil nur 23 in KW 37 und sonst
    # nichts"). Hier stand `shortlist_push_seen.json` — ein DEDUP-Buch mit drei Tagen TTL, kein
    # Ledger. Es raeumt sich selbst auf, also konnte der Block nie mehr als drei Tage zeigen, und
    # ein Ergebnis trug es auch nicht. Die leeren Wochen waren keine Pushes-Luecke, sondern eine
    # Gedaechtnisluecke.
    #
    # Jetzt liest der Block `shortlist_push_ledger.json` (push_shortlist_trades schreibt es seit
    # dem 10.09.). Der Ausgang kommt aus `poly_shortlist_track.json` — dieselbe Abrechnung wie
    # ueberall, statt einer zweiten Meinung. Gerechnet wird mit dem PUSH-Preis, nicht dem
    # Scan-Preis: wer dem Push folgt, steigt zu dem ein, der in der Nachricht stand.
    aus.append(("shortlist", "Heute spielenswert · Trades", "⚡", shortlist_push_plays(),
                "Das Buch beginnt am 12.09.2026. Am 10.09. wurde es gebaut, aber nie "
                "committet — die Datei kam auf keinem Runner an, und dieser Block stand "
                "seither auf leer statt auf falsch. Davor gab es für den Kanal nur ein "
                "Dedup-Buch mit 3 Tagen Gedächtnis; die früheren Pushes sind nicht "
                "rekonstruierbar."))
    return [(i, n, e, [p for p in pl if p.get("tag")], h) for i, n, e, pl, h in aus]


# ── Der Gegensignal-Filter: die Gegenprobe als eigener Block ────────────────────────────
# 13.09.2026 (Lucas: „ich brauch es zumindest in den Stats, weil ich will im Public ja
# Auswertungen schicken — als eigener Block, das reicht dann auch um weiter zu beobachten").
#
# Der Filter (pick_announce_state.push_ok) entstand am 30.08. aus einer Messung an 220
# abgerechneten ABWÄGEN: ohne Gegensignal 78,7 % Treffer und +40,0 % ROI, mit Gegensignal
# −11,7 %. Diese Zahlen sind IN-SAMPLE — sie sind die Stichprobe, an der die Regel gebaut
# wurde, und sie lasen den Signalstand bei ABRECHNUNG, während der Filter vorher entscheidet.
#
# Das Schattenbuch (pick_push_ledger.py) friert seit dem 30.08. den Stand VOR ANPFIFF ein.
# Alles darin ist damit echtes Out-of-Sample. Am 13.09. sah das so aus:
#
#     gepusht      n=31   71,0 % Treffer   ROI +15,6 %   [−7,4 … +37,7]
#     aussortiert  n=85   63,5 %           ROI  +3,5 %   [−10,6 … +17,9]
#
# Also: die Richtung stimmt, die Stärke nicht — und die Aussortierten verlieren nicht, sie
# gewinnen weniger. Deshalb steht hier NICHT nur die gepushte Seite (die sähe gut aus und
# wäre die Selbstbestätigung, die das Schattenbuch gerade verhindern soll), sondern beide
# Arme UND der Unterschied mit seinem Band.
FILTER_MIN_N = 30          # je Arm; darunter gibt es kein Urteil, nur den Stand
FILTER_BOOT = 4000
FILTER_SEED = 20260913     # fest: dieselbe Datenlage muss dieselbe Zahl ergeben


def _filter_zeilen():
    """Alle Schattenbuch-Zeilen aller Datensätze, mit Ergebnis UND Quote."""
    aus = []
    for pfad in sorted(BASE.glob("*pick_push_ledger.json")):
        roh = _load(pfad.name, [])
        zeilen = roh if isinstance(roh, list) else (roh.get("zeilen") or [])
        for r in zeilen:
            if not isinstance(r, dict):
                continue
            if r.get("status") != "abgerechnet" or not isinstance(r.get("win"), bool):
                continue
            o = r.get("odds")
            if not isinstance(o, (int, float)) or o <= 1.0:
                continue
            aus.append(r)
    return aus


def _arm(rows):
    return [{"tag": _tag(r.get("gesehenAm")), "gewonnen": bool(r.get("win")),
             "rendite": (float(r["odds"]) - 1.0) if r["win"] else -1.0, "clv": None}
            for r in rows if _tag(r.get("gesehenAm"))]


def burst_plays(phase=None) -> list:
    """Stake-Einsatz-Bursts als Plays (13.09.2026, Lucas: „haette ich auch gerne in den Stats").

    ⭐ `rendite` kommt aus der Abrechnung des Bursts (Summe pnl / Summe Einsatz), NICHT aus
    seiner Quote. Ein Burst ist eine Position auf mehreren Tickets, teils zu leicht
    verschiedenen Einsaetzen — die Quote allein waere die falsche Rechnung.

    Zeilen mit Status `nicht_abrechenbar` fallen raus: ihre Wetten sind aus dem rollierenden
    Stake-Ledger gefallen, sie sind keine offene Frage mehr, sondern eine verlorene. Sie als
    „ohne Ergebnis" mitzuzaehlen wuerde die Zahl der Pushes richtig, die Trefferquote aber
    schleichend falsch machen.
    """
    roh = _load("stake_burst_ledger.json", [])
    zeilen = roh if isinstance(roh, list) else (roh.get("zeilen") or [])
    aus = []
    for r in zeilen:
        if not isinstance(r, dict) or r.get("status") == "nicht_abrechenbar":
            continue
        if phase and r.get("phase") != phase:
            continue
        t = _tag(r.get("sentAt"))
        if not t:
            continue
        ren = r.get("rendite")
        aus.append({"tag": t,
                    "gewonnen": r.get("win") if isinstance(r.get("win"), bool) else None,
                    "rendite": float(ren) if isinstance(ren, (int, float)) else None,
                    "clv": None})
    return aus


def filter_vergleich(zeilen=None, boot: int = FILTER_BOOT) -> dict | None:
    """Beide Arme und der UNTERSCHIED zwischen ihnen, mit Band. REIN (fester Seed).

    ⭐ Warum der Unterschied und nicht zwei Zahlen nebeneinander: zwei Bänder, die sich
    überlappen, heißen NICHT automatisch „kein Unterschied" — und zwei, die sich nicht
    überlappen, sind auch kein Test. Gefragt ist die Verteilung der Differenz, und die
    entsteht nur, wenn man sie direkt zieht.
    """
    import random
    zeilen = _filter_zeilen() if zeilen is None else zeilen
    ja = [r for r in zeilen if r.get("push")]
    nein = [r for r in zeilen if not r.get("push")]
    if not ja or not nein:
        return None
    e = lambda rows: [(float(r["odds"]) - 1.0) if r["win"] else -1.0 for r in rows]
    h = lambda rows: [1.0 if r["win"] else 0.0 for r in rows]
    ea, eb, ha, hb = e(ja), e(nein), h(ja), h(nein)
    rnd = random.Random(FILTER_SEED)

    def _diff(a, b):
        m = lambda v: sum(v) / len(v)
        zieh = sorted(m([a[rnd.randrange(len(a))] for _ in a])
                      - m([b[rnd.randrange(len(b))] for _ in b]) for _ in range(boot))
        return {"punkt": round(100 * (m(a) - m(b)), 1),
                "lo": round(100 * zieh[int(0.05 * boot)], 1),
                "hi": round(100 * zieh[int(0.95 * boot)], 1),
                "anteilUnterNull": round(100.0 * sum(1 for x in zieh if x < 0) / boot)}

    roi_d, hit_d = _diff(ea, eb), _diff(ha, hb)
    aus = {"gesendet": kennzahlen(_arm(ja)), "aussortiert": kennzahlen(_arm(nein)),
           "roiDiff": roi_d, "hitDiff": hit_d,
           "quelle": "Schattenbuch — Signalstand vor Anpfiff eingefroren",
           "bootstrap": boot}
    tage = sorted(t for t in (_tag(r.get("gesehenAm")) for r in zeilen) if t)
    aus["abdeckung"] = {"von": tage[0] if tage else None, "bis": tage[-1] if tage else None}
    if len(ja) < FILTER_MIN_N or len(nein) < FILTER_MIN_N:
        aus["urteil"] = "sammelt"
        aus["grund"] = ("%d gesendet / %d aussortiert abgerechnet — unter %d je Seite sagt der "
                        "Vergleich nichts" % (len(ja), len(nein), FILTER_MIN_N))
    elif roi_d["lo"] > 0:
        aus["urteil"] = "der Filter trägt"
        aus["grund"] = ("%+.1f pp Rendite gegenüber den Aussortierten, Untergrenze %+.1f pp"
                        % (roi_d["punkt"], roi_d["lo"]))
    else:
        aus["urteil"] = "noch nicht belegt"
        aus["grund"] = ("%+.1f pp Rendite gegenüber den Aussortierten, aber das Band reicht von "
                        "%+.1f bis %+.1f pp — in %d %% der Ziehungen wäre der Filter schlechter"
                        % (roi_d["punkt"], roi_d["lo"], roi_d["hi"], roi_d["anteilUnterNull"]))
    return aus


def baue(now=None) -> dict:
    heute = (now or _now()).date().isoformat()
    bloecke = []

    def _add(bid, label, emoji, gruppe, plays, hinweis=None):
        plays = [p for p in (plays or []) if p.get("tag")]
        if not plays:
            return
        von, bis = _abdeckung(plays)
        b = {"id": bid, "label": label, "emoji": emoji, "gruppe": gruppe,
             "abdeckung": {"von": von, "bis": bis},
             "reihen": perioden_reihen(plays, heute)}
        if hinweis:
            b["hinweis"] = hinweis
        bloecke.append(b)

    # ⚠️ „Gesamt" ist Liga + MLS, NICHT alles.
    #
    # 10.09.2026 (Lucas: „WM kann raus, wertlos in Wahrheit"). Am 09.09. bekam die WM einen
    # eigenen Block, damit sie die Gesamtzahl nicht mehr zur Haelfte fuellt. Das war die halbe
    # Loesung: getrennt stand sie zwar richtig da, aber sie beantwortet keine Frage, die heute
    # noch jemand stellt — das Turnier ist seit dem 19.07. vorbei, die Engine hat sich seither
    # zweimal geaendert, und die Seite existiert, damit Lucas den LAUFENDEN Betrieb postet.
    #
    # ⭐ Die Daten bleiben, wo sie sind: `freigabe._card_plays()` liefert die WM-Picks
    # unveraendert weiter, und `cards_plays("WM")` beantwortet die Frage weiterhin fuer jeden,
    # der sie stellt. Weggenommen wird nur der Platz auf der Seite, nicht die Auskunft aus dem
    # System — dieselbe Trennung wie bei der ✦-Prosa im Cards-Digest heute frueh.
    _add("cards", "Cards · laufender Betrieb", "🎯", "Eigene Engine",
         cards_plays("Liga") + cards_plays("MLS"),
         "Liga und MLS. Die WM 2026 ist seit dem 19.07. vorbei und zählt hier nicht mit.")
    _add("cards-liga", "Cards · Liga", "🎯", "Eigene Engine", cards_plays("Liga"))
    _add("cards-mls", "Cards · MLS", "🎯", "Eigene Engine", cards_plays("MLS"))
    _add("betfair", "Betfair · alle Signale", "💷", "Marktdaten", betfair_plays(),
         "Der Ledger hält ein rollierendes Fenster — ältere Perioden sind unvollständig, "
         "nicht schwach.")
    _pp = poly_plays()
    _add("poly", "Polymarket · Shortlist", "🎮", "Marktdaten", _pp,
         "Ohne die gesperrten Sportarten (US-Sport, Kampfsport) — die laufen als reine "
         "Beobachtung und werden nicht gespielt.")
    _add("poly-public", "Polymarket · Public-Kandidaten", "◆", "Marktdaten",
         [p for p in _pp if p.get("public")])
    for bid, name, emoji, plays, hinweis in push_bloecke():
        _add("push-" + bid, name, emoji, "Push-Kanäle", plays, hinweis)
    # 13.09.2026 (Lucas): die Stake-Bursts als eigener Block. Live und vor Anpfiff zusaetzlich
    # getrennt — die Vorab-Messung sah +29,0 % (live) gegen +8,8 % (vor), und zusammengerechnet
    # waere keine der beiden Fragen mehr zu beantworten.
    _add("stake-burst", "Stake-Bursts · Trades", "⚡", "Push-Kanäle", burst_plays(),
         "Ein Burst ist EINE Auswahl, die innerhalb von Sekunden auf mehrere Tickets zur "
         "gleichen Quote gespielt wurde. Gerechnet wird geldgewichtet über alle Tickets des "
         "Bursts, nicht je Ticket.")
    _add("stake-burst-live", "Stake-Bursts · live", "⚡", "Push-Kanäle", burst_plays("live"))
    _add("stake-burst-vor", "Stake-Bursts · vor Anpfiff", "⚡", "Push-Kanäle", burst_plays("vor"))
    # 13.09.2026 (Lucas): der Gegensignal-Filter als eigene Gruppe — BEIDE Arme, damit die
    # Gegenprobe auf derselben Seite steht wie das Ergebnis. Nur den gesendeten Arm zu zeigen
    # waere die Selbstbestaetigung, die das Schattenbuch gerade verhindern soll.
    _fz = _filter_zeilen()
    _add("filter-gesendet", "Gegensignal-Filter · gesendet", "🟢", "Push-Filter",
         _arm([r for r in _fz if r.get("push")]),
         "Picks, zu denen KEIN Signal widerspricht — die gehen in den Public-Channel.")
    _add("filter-aussortiert", "Gegensignal-Filter · aussortiert", "⚪", "Push-Filter",
         _arm([r for r in _fz if not r.get("push")]),
         "Die vom Filter zurückgehaltenen Picks, abgerechnet als wären sie gesendet worden. "
         "Sie sind die Gegenprobe: wären sie in Wahrheit gut, stünde es hier.")
    aus = {"generatedAt": (now or _now()).isoformat(), "heute": heute,
           "wochenZurueck": WOCHEN_ZURUECK, "ugMinN": UG_MIN_N,
           "bloecke": bloecke}
    _v = filter_vergleich(_fz)
    if _v:
        aus["filterVergleich"] = _v
    return aus


def main() -> int:
    from safe_write import write_json_atomic
    d = baue()
    write_json_atomic(BASE / OUT_FILE, d, indent=1)
    print("=== stats_perioden.py ===")
    for b in d["bloecke"]:
        ges = [r for r in b["reihen"] if r["art"] == "gesamt"]
        g = ges[0] if ges else {}
        print("  %-34s n=%-6s Treffer %-6s ROI %-7s (%s .. %s)"
              % (b["label"], g.get("n"),
                 ("%.1f%%" % g["hitPct"]) if g.get("hitPct") is not None else "—",
                 ("%+.1f%%" % g["roi"]) if g.get("roi") is not None else "—",
                 b["abdeckung"]["von"], b["abdeckung"]["bis"]))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
