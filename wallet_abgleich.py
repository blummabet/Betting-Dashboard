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
# Wie weit darf die Bewegung vom Zeitstempel der Wette entfernt liegen? Der Wallet-Stand wird
# alle ~15 Minuten geschrieben, ein Kauf zeigt sich also im naechsten Schnappschuss.
FENSTER_MIN = 25.0
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


def kauf_belegt(bet, verlauf, fenster_min: float = FENSTER_MIN,
                toleranz: float = TOLERANZ) -> dict:
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
    if not (r[0][0] <= ts <= r[-1][0] + timedelta(minutes=fenster_min)):
        return {"belegt": None,
                "grund": "Verlauf deckt den Zeitpunkt nicht ab (%s bis %s)"
                         % (r[0][0].isoformat()[:16], r[-1][0].isoformat()[:16]), "delta": None}

    fenster = timedelta(minutes=fenster_min)
    passend = None
    for b in bewegungen(verlauf):
        bt = _zeit(b["ts"])
        if bt is None or not (ts - fenster <= bt <= ts + fenster):
            continue
        if b["delta"] >= 0:
            continue                       # ein Kauf nimmt Collateral weg
        if abs(abs(b["delta"]) - float(einsatz)) <= toleranz:
            passend = b
            break
    if passend:
        return {"belegt": True, "grund": "Abgang %.2f $ um %s"
                % (passend["delta"], str(passend["ts"])[:16]), "delta": passend["delta"]}
    return {"belegt": False,
            "grund": "kein Abgang von ~%.2f $ im Fenster +/-%.0f Min" % (einsatz, fenster_min),
            "delta": None}


def zuordnen(bets, verlauf, fenster_min: float = FENSTER_MIN,
             toleranz: float = TOLERANZ) -> dict:
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
    von 5 $ genau eine, und eine Wette ohne freies Budget in ihrem Fenster ist unbelegt.

    Fehlerklasse: eine Pruefung, die ihre eigene Modellannahme nicht prueft.
    """
    fenster = timedelta(minutes=fenster_min)
    r = reihe(verlauf)
    abgaenge = []
    for bew in bewegungen(verlauf):
        if bew["delta"] < 0:
            t = _zeit(bew["ts"])
            if t is not None:
                abgaenge.append({"ts": t, "budget": abs(bew["delta"]), "voll": abs(bew["delta"])})

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
        if not (r[0][0] <= ts <= r[-1][0] + fenster):
            urteil[i] = {"belegt": None,
                         "grund": "Verlauf deckt den Zeitpunkt nicht ab (%s bis %s)"
                                  % (r[0][0].isoformat()[:16], r[-1][0].isoformat()[:16])}
            continue
        treffer = None
        for a in abgaenge:
            if not (ts - fenster <= a["ts"] <= ts + fenster):
                continue
            if a["budget"] + toleranz >= float(einsatz):
                treffer = a
                break
        if treffer:
            treffer["budget"] -= float(einsatz)
            urteil[i] = {"belegt": True,
                         "grund": "Abgang %.2f $ um %s" % (-treffer["voll"],
                                                           treffer["ts"].isoformat()[:16])}
        else:
            urteil[i] = {"belegt": False,
                         "grund": "kein freier Abgang von ~%.2f $ im Fenster +/-%.0f Min"
                                  % (float(einsatz), fenster_min)}
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
