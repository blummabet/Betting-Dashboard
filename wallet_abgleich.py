#!/usr/bin/env python3
"""
wallet_abgleich.py — hat diese Wette das Wallet je berührt?
===========================================================
🔴 21.09.2026, 01:04 UTC (Lucas: „Das kam. Aber auf poly wurde nicht gesetzt").

Deportivo Toluca vs Santos Laguna, $5, Order-ID, Zeile im Buch. Gemessen am Wallet-Verlauf:

    20.09. 21:53   usdc 178,2312   positions 0,00
       …           (Order um 01:04)
    21.09. 04:39   usdc 178,2312   positions 0,00

Sieben Stunden, keine Bewegung. Kein Abgang, keine Position, keine Rueckzahlung. Und trotzdem
hat das Buch die Zeile abgerechnet: `result: LOSS, pnl: -5.00`. Ein Verlust, den es nie gab,
steht in der Bilanz, an der gemessen wird, ob sich das Ganze lohnt.

Dass die Mechanik grundsaetzlich traegt, sieht man daneben — echte Kaeufe bewegen das Wallet:

    20.09. 21:08   usdc 176,73 -> 171,65   (-5,07, Kauf um 21:04)
    20.09. 21:53   usdc 171,65 -> 178,23   (+6,58, Auszahlung)

Fehlerklasse: **ein Buch, das seine eigene Behauptung nie gegen die Kasse prueft.** Es rechnet
aus `status: "placed"` plus Spielausgang ab. Ob je Geld geflossen ist, fragt es nicht.

## Warum das ohne eine einzige API-Abfrage geht

Der Wallet-Stand wird alle ~15 Minuten geschrieben und committet. Die zweite, unabhaengige
Quelle liegt also seit Monaten im Repo — sie wurde nur nie gelesen. `poly_wallet_verlauf.json`
haelt sie ab jetzt als Reihe, damit der Abgleich nicht in der Git-Historie graben muss.

REIN/testbar: kein I/O in diesem Modul.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Ein Kauf muss sich im freien Collateral zeigen. Kleiner als das ist Rauschen (Rundung,
# Gebuehren, ein paralleler Vorgang).
MIN_DELTA = 0.50
# Wie genau muss der Abgang zum Einsatz passen? 5 $ Einsatz zeigten sich als -5,07 (Gebuehr).
TOLERANZ = 0.75


def _zeit(w):
    if not w:
        return None
    try:
        t = datetime.fromisoformat(str(w).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def reihe(verlauf) -> list:
    """Der Wallet-Verlauf als sortierte [(zeit, usdc)]. REIN."""
    raus = []
    for e in (verlauf or []):
        if not isinstance(e, dict):
            continue
        t, u = _zeit(e.get("ts") or e.get("updatedAt")), e.get("usdc")
        if t is None or not isinstance(u, (int, float)):
            continue
        raus.append((t, float(u)))
    raus.sort(key=lambda x: x[0])
    return raus


# 🔴 21.09.2026, beim Nachmessen gegen die echte Historie aufgefallen — und es war meine eigene
# Modellannahme, die nicht trug.
#
# Der Abgleich suchte einen Abgang im Fenster +/-25 Minuten um die Wette. Das setzt voraus, dass
# alle ~15 Minuten ein Stand geschrieben wird. Am 15.09. klaffte eine Luecke von 03:35 bis
# 09:12; zwei Wetten darin galten als „nie bezahlt", obwohl das freie Collateral ueber die
# Luecke hinweg um genau 10,09 $ fiel — also zwei Kaeufe zu 5 $. Der Abgang stand bei 09:12 und
# damit 2h48 neben der Wette.
#
# Fehlerklasse: **ein fester Abstand als Mass fuer etwas, das in Beobachtungs-ABSCHNITTEN
# vorliegt.** Ein Schnappschuss sagt nicht „um 09:12 floss Geld", er sagt „zwischen 03:35 und
# 09:12 floss Geld". Genau das ist ab hier das Mass:
#
#   ruhender Abschnitt   [ts … bisTs]  derselbe Stand, durchgehend  -> hier kann kein Kauf sein
#   Uebergang            [bisTs … ts']  dazwischen aenderte er sich  -> hier ist der Kauf, wenn einer
#
# Eine Wette in einem RUHENDEN Abschnitt ist bewiesen unbelegt — das ist der Toluca-Fall. Eine
# Wette in einem Uebergang zieht aus dessen Abgang ihr Budget. Eine Wette vor dem ersten oder
# nach dem letzten Stand ist unbeobachtet und bleibt es.
#
# Die kleine Toleranz bleibt fuer den Uhren-Versatz zwischen `placedAt` (Order) und `updatedAt`
# (Balance-Lauf); sie verschiebt keine Wette in einen anderen Abschnitt, sie dehnt nur dessen
# Raender.
SLACK_MIN = 3.0


def _punkte(verlauf) -> list:
    """[(von, bis, usdc)] je Stand — `bis` = bis wann er galt. REIN."""
    raus = []
    for e in (verlauf or []):
        if not isinstance(e, dict):
            continue
        a, u = _zeit(e.get("ts") or e.get("updatedAt")), e.get("usdc")
        if a is None or not isinstance(u, (int, float)):
            continue
        b = _zeit(e.get("bisTs")) or a
        raus.append((a, b if b > a else a, float(u)))
    raus.sort(key=lambda x: x[0])
    return raus


def abschnitte(verlauf, min_delta: float = MIN_DELTA, slack_min: float = SLACK_MIN) -> list:
    """Die beobachteten Abschnitte. REIN. -> [{"von","bis","delta","ruht"}]

    `delta` ist die Aenderung des freien Collaterals in diesem Abschnitt; `ruht` heisst, dass
    er innerhalb EINES Standes liegt und sich also nichts geaendert hat.
    """
    p = _punkte(verlauf)
    sl = timedelta(minutes=slack_min)
    raus = []
    for i, (von, bis, _u) in enumerate(p):
        if bis > von:
            raus.append({"von": von - sl, "bis": bis + sl, "delta": 0.0, "ruht": True})
        if i + 1 < len(p):
            d = round(p[i + 1][2] - p[i][2], 4)
            raus.append({"von": bis - sl, "bis": p[i + 1][0] + sl,
                         "delta": d if abs(d) >= min_delta else 0.0,
                         "ruht": abs(d) < min_delta})
    return raus


def beobachtet(verlauf, ts, **kw):
    """Liegt `ts` in einem beobachteten Abschnitt? REIN. -> (bool, grund)"""
    if ts is None:
        return False, "Wette ohne Zeitstempel"
    for a in abschnitte(verlauf, **kw):
        if a["von"] <= ts <= a["bis"]:
            return True, ""
    p = _punkte(verlauf)
    if not p:
        return False, "kein Wallet-Verlauf"
    return False, ("ausserhalb des Verlaufs (%s bis %s)"
                   % (p[0][0].isoformat()[:16], p[-1][1].isoformat()[:16]))


def ende(verlauf):
    """Bis wann reicht dieser Verlauf? REIN. None = leer.

    🔴 21.09.2026: nicht dasselbe wie der letzte `ts`. Ein Stand, der stundenlang unveraendert
    bleibt, steht mit dem Zeitpunkt seiner ERSTEN Sichtung in der Reihe; `bisTs` sagt, bis wann
    er galt. Wer nur `ts` liest, erklaert den halben Tag fuer nicht abgedeckt, obwohl
    durchgehend hingesehen wurde.
    """
    letzt = None
    for e in (verlauf or []):
        if not isinstance(e, dict):
            continue
        for w in (e.get("bisTs"), e.get("ts"), e.get("updatedAt")):
            t = _zeit(w)
            if t is not None and (letzt is None or t > letzt):
                letzt = t
    return letzt


def bewegungen(verlauf, min_delta: float = MIN_DELTA) -> list:
    """Jede Aenderung des freien Collaterals. REIN. -> [{"ts","delta","von","bis"}]

    `ts` ist der Zeitpunkt des SPAETEREN Schnappschusses: frueher kann die Bewegung nicht
    gesehen worden sein, und genau das ist die Aussage — nicht wann sie geschah.
    """
    r = reihe(verlauf)
    raus = []
    for (t0, u0), (t1, u1) in zip(r, r[1:]):
        d = round(u1 - u0, 4)
        if abs(d) >= min_delta:
            raus.append({"ts": t1.isoformat(), "delta": d, "von": u0, "bis": u1})
    return raus


def kauf_belegt(bet, verlauf, toleranz: float = TOLERANZ) -> dict:
    """Gibt es zu dieser Wette einen passenden Abgang im Wallet? REIN.

    -> {"belegt": True|False|None, "grund": str, "delta": float|None}

    **None heisst „nicht pruefbar"** und niemals „in Ordnung": ohne Zeitstempel an der Wette
    oder ohne Verlauf, der ihren Zeitraum abdeckt, ist die Frage nicht beantwortet. Genau diese
    Unterscheidung hat gefehlt — ein Buch ohne Gegenprobe sah aus wie ein geprueftes.
    """
    ts = _zeit((bet or {}).get("placedAt"))
    einsatz = (bet or {}).get("stake")
    if ts is None or not isinstance(einsatz, (int, float)) or einsatz <= 0:
        return {"belegt": None, "grund": "Wette ohne Zeitstempel oder Einsatz", "delta": None}
    r = reihe(verlauf)
    if not r:
        return {"belegt": None, "grund": "kein Wallet-Verlauf", "delta": None}
    ok, warum = beobachtet(verlauf, ts)
    if not ok:
        return {"belegt": None, "grund": warum, "delta": None}

    for a in abschnitte(verlauf):
        if not (a["von"] <= ts <= a["bis"]):
            continue
        if a["delta"] < 0 and abs(a["delta"]) + toleranz >= float(einsatz):
            return {"belegt": True,
                    "grund": "Abgang %.2f $ zwischen %s und %s"
                             % (a["delta"], a["von"].isoformat()[:16], a["bis"].isoformat()[:16]),
                    "delta": a["delta"]}
    return {"belegt": False,
            "grund": "kein Abgang von ~%.2f $ im beobachteten Abschnitt" % float(einsatz),
            "delta": None}


def zuordnen(bets, verlauf, toleranz: float = TOLERANZ) -> dict:
    """Ordnet jede Wette einem Wallet-Abgang zu. REIN. -> {betKey_index: urteil}

    🔴 21.09.2026, zwei Fehlversuche von mir, beide beim Nachmessen aufgefallen:

    1. **Einzelsuche.** Ich suchte je Wette einen Abgang von genau ihrem Einsatz. Zwei Kaeufe
       im selben 15-Minuten-Fenster zeigen sich aber als EIN Abgang von 10 $ — die Suche nach
       5 $ findet ihn nicht. Ergebnis: drei gewonnene Wetten waeren als erfunden gemeldet
       worden.
    2. **Gruppierung nach Zeitfenster.** Dann fasste ich Wetten zusammen, die naeher als das
       Fenster beieinander lagen — und kettete damit 13:07 und 13:31 zu einer Gruppe, die es
       nie gab. Aus vier ungeklaerten Zeilen wurden sechs.

    Beides war derselbe Denkfehler: ich habe die Wetten sortiert, statt das Geld zu verteilen.
    Richtig ist eine Zuordnung — jeder Abgang hat ein Budget in Hoehe seines Betrags, und jede
    Wette verbraucht daraus ihren Einsatz. Ein Abgang von 10 $ traegt zwei 5-$-Wetten, einer
    von 5 $ genau eine, und eine Wette ohne freies Budget in ihrem Abschnitt ist unbelegt.

    3. **Ein festes Zeitfenster.** Der dritte Fehlversuch, gefunden gegen die echte Historie:
       der passende Abgang musste +/-25 Minuten neben der Wette liegen. Das gilt nur, solange
       alle 15 Minuten ein Stand geschrieben wird. Am 15.09. lag eine Luecke von 03:35 bis
       09:12; ueber sie hinweg fiel das Collateral um 10,09 $ — zwei Kaeufe zu 5 $ — und beide
       Wetten galten als unbelegt, weil der Abgang 2h48 danebenstand. Ein Schnappschuss sagt
       nicht „um 09:12 floss Geld", sondern „zwischen 03:35 und 09:12 floss Geld". Zugeordnet
       wird deshalb nach ABSCHNITT, nicht nach Abstand (s. `abschnitte`).

    Fehlerklasse: eine Pruefung, die ihre eigene Modellannahme nicht prueft.
    """
    r = reihe(verlauf)
    abgaenge = []
    for a in abschnitte(verlauf):
        if a["delta"] < 0:
            abgaenge.append({"von": a["von"], "bis": a["bis"],
                             "budget": abs(a["delta"]), "voll": abs(a["delta"])})

    paare = []
    for i, b in enumerate(bets or []):
        if not isinstance(b, dict):
            continue
        paare.append((i, _zeit(b.get("placedAt")), b))
    paare.sort(key=lambda x: (x[1] is None, x[1]))

    urteil = {}
    for i, ts, b in paare:
        einsatz = b.get("stake")
        if ts is None or not isinstance(einsatz, (int, float)) or einsatz <= 0:
            urteil[i] = {"belegt": None, "grund": "Wette ohne Zeitstempel oder Einsatz"}
            continue
        if not r:
            urteil[i] = {"belegt": None, "grund": "kein Wallet-Verlauf"}
            continue
        ok, warum = beobachtet(verlauf, ts)
        if not ok:
            urteil[i] = {"belegt": None, "grund": warum}
            continue
        treffer = None
        for a in abgaenge:
            if not (a["von"] <= ts <= a["bis"]):
                continue
            if a["budget"] + toleranz >= float(einsatz):
                treffer = a
                break
        if treffer:
            treffer["budget"] -= float(einsatz)
            urteil[i] = {"belegt": True,
                         "grund": "Abgang %.2f $ zwischen %s und %s"
                                  % (-treffer["voll"], treffer["von"].isoformat()[:16],
                                     treffer["bis"].isoformat()[:16])}
        else:
            urteil[i] = {"belegt": False,
                         "grund": "kein freier Abgang von ~%.2f $ im beobachteten Abschnitt"
                                  % float(einsatz)}
    return urteil


def pruefe_buch(bets, verlauf, **kw) -> dict:
    """Das ganze Buch gegen die Kasse. REIN.

    -> {"belegt": [...], "ohne": [...], "unpruefbar": [...], "summeOhne": float}

    `summeOhne` ist die Zahl, um die die Bilanz falsch sein kann: Einsatz plus gebuchtes
    Ergebnis jeder Zeile, die nie Geld bewegt hat.
    """
    belegt, ohne, unpruefbar = [], [], []
    urteile = zuordnen(bets, verlauf, **kw)
    for i, b in enumerate(bets or []):
        if not isinstance(b, dict):
            continue
        u = urteile.get(i) or {"belegt": None, "grund": "nicht bewertet"}
        zeile = {"betKey": b.get("betKey"), "placedAt": b.get("placedAt"),
                 "stake": b.get("stake"), "result": b.get("result"), "pnl": b.get("pnl"),
                 "method": b.get("method"), "grund": u["grund"]}
        (belegt if u["belegt"] is True
         else ohne if u["belegt"] is False else unpruefbar).append(zeile)
    summe = 0.0
    for z in ohne:
        try:
            summe += abs(float(z.get("pnl") or 0))
        except (TypeError, ValueError):
            pass
    return {"belegt": belegt, "ohne": ohne, "unpruefbar": unpruefbar,
            "summeOhne": round(summe, 2)}


# ── Die Abrechnung selbst (21.09.2026) ───────────────────────────────────────────────────
# `pruefe_buch` MELDET nur. Solange die Zeile danach unveraendert mit -5,00 $ im Buch steht,
# ist die Bilanz weiter falsch und jeder Leser rechnet sie mit.
# Fehlerklasse: ein Befund, der gemeldet, aber nicht gezogen wird.

# Der Zustand, den eine bewiesen unbelegte Zeile traegt. Kein neuer Ausgang — ein Vermerk, dass
# es keinen gibt.
OHNE_STATUS = "unbelegt"
OHNE_RESULT = "UNBELEGT"


def entbuchen(bets, verlauf, **kw) -> list:
    """Nimmt Zeilen aus der Bilanz, die BEWIESEN nie die Kasse beruehrt haben. -> geaenderte.

    Aendert `bets` in place. Jede getroffene Zeile bekommt:
        status/result  -> "unbelegt"/"UNBELEGT"   (kein Ausgang, den es nie gab)
        pnl            -> 0.0
        bilanz         -> False                    (Zaehler UND Nenner lassen sie aus)
        pnlGebucht     -> der alte Wert            (nichts wird vernichtet)
        kasseGrund     -> warum

    **Nur `belegt is False`.** `None` heisst „nicht pruefbar" und bleibt gebucht — eine Zeile
    aus der Zeit vor dem Verlauf ist nicht widerlegt, sie ist unbeobachtet. Sie stillschweigend
    aus der Bilanz zu nehmen waere derselbe Fehler noch einmal, nur in die andere Richtung:
    fehlende Information, die ein Urteil faellt.

    Idempotent: eine bereits entbuchte Zeile wird nicht noch einmal angefasst.
    """
    urteile = zuordnen(bets, verlauf, **kw)
    raus = []
    for i, b in enumerate(bets or []):
        if not isinstance(b, dict):
            continue
        if b.get("bilanz") is False:              # schon entbucht
            continue
        if not b.get("result"):                   # noch offen — der Kauf ist Sache des
            continue                              # Ruhende-Order-Waechters, nicht dieser Stelle
        if (urteile.get(i) or {}).get("belegt") is not False:
            continue
        alt_pnl, alt_status, alt_result = b.get("pnl"), b.get("status"), b.get("result")
        b["pnlGebucht"] = alt_pnl
        b["statusGebucht"], b["resultGebucht"] = alt_status, alt_result
        b["status"], b["result"] = OHNE_STATUS, OHNE_RESULT
        b["pnl"] = 0.0
        b["bilanz"] = False
        b["kasse"] = "ohne"
        b["kasseGrund"] = (urteile.get(i) or {}).get("grund") or "kein Abgang im Wallet"
        raus.append({"betKey": b.get("betKey"), "stake": b.get("stake"),
                     "pnlGebucht": alt_pnl, "resultGebucht": alt_result,
                     "grund": b["kasseGrund"]})
    return raus


def entbucht_text(geaendert) -> str:
    """Eine Zeile fuer die Konsole/Meldung. REIN. Leer = nichts zu sagen."""
    if not geaendert:
        return ""
    summe = 0.0
    for z in geaendert:
        try:
            summe += float(z.get("pnlGebucht") or 0)
        except (TypeError, ValueError):
            pass
    return ("%d Zeile(n) aus der Bilanz genommen — nie eine Wallet-Bewegung, gebucht waren "
            "%+.2f $ (%s)" % (len(geaendert), summe,
                              "; ".join(str(z.get("betKey"))[:34] for z in geaendert[:3])))
