#!/usr/bin/env python3
"""
preis_signal.py — der einzige Teil der Engine, der CLV vorhersagt
=================================================================
06.09.2026 (Lucas: „ich kann mir nicht vorstellen, dass wir mit all den Infos nichts
Vernuenftiges machen koennen").

Doch, koennen wir — nur nicht mit dem Score, den wir bisher angezeigt haben.

## Der Befund

`sc` aus der Pick-Engine korreliert mit der Rendite mit **r = -0,007** (n=1114). Nicht
invertiert, wie ich zuerst behauptet habe — **leer**. Der Grund steht im Code: `sc` ist die
Summe aus Form, xG, Serien und Motivations-Abzuegen. Der **Preis kommt darin nicht vor**.

Trennt man die Signale danach, WOHER sie kommen, faellt die Summe auseinander:

    Gruppe                     n     r(Score, CLV)    p
    Preis/Geld-Signale       156        +0,353     0,0001
    Staerke-Signale          315        +0,003     0,956

Preis/Geld-Terzile, gegen den Schlusskurs gemessen:

    T1  n=52   Ø Score -1,06   Ø CLV  -3,40 pp   95%-KI [-4,68; -2,11]
    T2  n=52   Ø Score +2,43   Ø CLV  -1,67 pp   95%-KI [-2,68; -0,65]
    T3  n=52   Ø Score +6,38   Ø CLV  -0,69 pp   95%-KI [-1,43; +0,05]

Monoton, und das Bootstrap-KI der Korrelation ist [+0,21; +0,48] — es schliesst die Null aus.
Es haelt in zwei von drei Datensaetzen einzeln (liga +0,40, mls +0,47), im dritten schwach
(wm +0,11).

Die Staerke-Terzile dagegen sind flach: -1,80 / -2,29 / -1,75. Wer Form und xG addiert,
addiert Rauschen zu Rauschen. Und weil die Staerke-Signale 315 der 439 Feuerungen stellen,
**ersaeuft die Summe die Haelfte, die etwas kann**. Das ist die ganze Erklaerung fuer die
-0,007.

## Was das NICHT heisst

T3 liegt bei -0,69 pp, nicht im Plus. Die 95%-Obergrenze streift die Null (+0,05). Ehrlich
gelesen: die beste Gruppe ist vom Schlusskurs **nicht unterscheidbar**, die schlechteste
liegt klar darunter. Das ist kein Vorsprung — das ist der Unterschied zwischen „fairer Preis"
und „wir sind zu spaet". Ein Vorsprung waere ein KI, das ganz ueber der Null liegt; den
haben wir nicht, und dieses Modul behauptet ihn auch nicht.

Ein Teil davon ist ausserdem mechanisch: `lead_lag_bias` feuert per Definition, wenn Pinnacle
sich schon bewegt hat und das Buch noch nicht. Dass danach CLV kommt, ist kein Orakel,
sondern korrekt eingefangene Bewegung. Genau deshalb ist es aber brauchbar.

## Die zweite Haelfte des Befunds
**Nur 49 % der Picks (156 von 318) tragen ueberhaupt EIN Preis-Signal.** Die andere Haelfte
entsteht blind zum Markt. Fuer die gibt dieses Modul `None` zurueck — kein Urteil, keine
harmlose Null. *Fehlende Information ist keine Erlaubnis.*

REIN/testbar, kein I/O.
"""
from __future__ import annotations

# Signale, die aus Preis, Geld oder Bewegung kommen — nicht aus Mannschaftsstaerke.
PREIS_SIGNALE = frozenset({
    "lead_lag_bias",       # Pinnacle bewegt, Buch noch nicht
    "betfair_money",       # Betfair-Geldfluss
    "move_following",      # Bewegung, der andere folgen
    "steam_lag",           # Steam-Move mit Verzoegerung
    "public_static_bias",  # Publikumsgeld gegen den Pick
    "opener_move",         # Bewegung seit Eroeffnung
    "smart_money",         # als scharf markiertes Geld
    "reverse_line_move",   # Linie gegen das Volumen
    "multi_book_steam",    # gleichzeitige Bewegung ueber Buecher
})

# Terzil-Schnitte aus den 156 abgerechneten Picks mit Preis-Signal (06.09.2026).
SCHNITT_UNTEN = 1.2
SCHNITT_OBEN = 4.0

# Gemessenes Ø CLV je Band, mit 95%-KI. Beschreibung des Gemessenen, keine Prognose.
BAENDER = {
    "spaet":  {"clvPP": -3.40, "ki": (-4.68, -2.11), "n": 52},
    "mittel": {"clvPP": -1.67, "ki": (-2.68, -0.65), "n": 52},
    "fair":   {"clvPP": -0.69, "ki": (-1.43, +0.05), "n": 52},
}


def preis_score(pick) -> float | None:
    """Summe NUR der Preis/Geld-Signale eines Picks.

    -> float, wenn mindestens ein Preis-Signal gefeuert hat.
    -> None,   wenn keines gefeuert hat. Das ist NICHT 0.0: ein Pick ohne Marktbezug ist
       nicht „neutral bepreist", er ist ungemessen. Die Haelfte unserer Picks faellt hierher.
    """
    if not isinstance(pick, dict):
        return None
    treffer = []
    for s in (pick.get("signals") or []):
        if not isinstance(s, dict):
            continue
        if s.get("name") not in PREIS_SIGNALE:
            continue
        w = s.get("score")
        # bool ist in Python eine Zahl — hier waere True still zu 1.0 geworden.
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            continue
        treffer.append(float(w))
    if not treffer:
        return None
    return round(sum(treffer), 4)


def band(score) -> str | None:
    """Welches der drei gemessenen Baender? None, wenn es keinen Score gibt."""
    if score is None or isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if score < SCHNITT_UNTEN:
        return "spaet"
    if score < SCHNITT_OBEN:
        return "mittel"
    return "fair"


def urteil(pick) -> dict | None:
    """Das vollstaendige, belegte Urteil zu einem Pick — oder None.

    -> {"score": float, "band": str, "clvPP": float, "ki": (lo, hi), "n": int,
        "signale": [Namen]}   oder None, wenn kein Preis-Signal vorliegt.
    """
    sc = preis_score(pick)
    if sc is None:
        return None
    b = band(sc)
    if b is None:
        return None
    namen = sorted({s.get("name") for s in (pick.get("signals") or [])
                    if isinstance(s, dict) and s.get("name") in PREIS_SIGNALE})
    d = dict(BAENDER[b])
    d.update({"score": sc, "band": b, "signale": namen})
    return d
