"""devig.py — Buchmacherquoten → faire Wahrscheinlichkeiten. EINE Quelle für alle Verfahren.

07.09.2026. Anlass: der Wisdom-of-the-Crowd-Ansatz (Buchdahl, 111.909 Quotenpaare / 37.303
Spiele / 22 Ligen: +2,51 % Yield über alle Value-Wetten, +5,71 % ab Schwelle 2 %; peer-reviewed
Analogon Kaunitz et al. 2017, arXiv:1710.02824 — 56.435 Wetten Backtest ROI 3,5 %, 265 Wetten
Echtgeld ROI 8,5 %). Er steht und fällt mit der Frage, wie aus einer Quote eine faire
Wahrscheinlichkeit wird.

DIE ENTSCHEIDUNG, DIE WIRKLICH ZÄHLT — nachgerechnet, nicht übernommen:

  Zweiseitige Märkte (Ü/U, BTTS, Asian Handicap): alle Verfahren stimmen bis auf 0,01 pp
  überein. Shin ist bei n=2 identisch mit additiv. Die Methodenwahl ist dort GEGENSTANDSLOS —
  wer darüber diskutiert, diskutiert über nichts.

  1X2: beim Außenseiter liegen die Verfahren 5–11 % auseinander (Beispiel 1,25/6,50/13,00:
  faire Außenseiter-Quote multiplikativ 13,40 · Shin 14,54 · Power 14,71 · additiv 15,00).
  Das ist das Zwei- bis Vierfache einer typischen Value-Schwelle. Multiplikatives De-Vigging
  ERZEUGT dort Scheinvalue auf Longshots, weil es die Marge gleichmäßig verteilt — sie liegt
  aber nachweislich überproportional auf den langen Quoten (Whelan, 84.230 Fußballspiele:
  ~3 % Verlust bei den kürzesten, ~17 % bei den längsten Quoten).

Deshalb: `fair()` nimmt für Drei-Weg-Märkte Shin, für Zwei-Weg multiplikativ — und `streuung()`
sagt, wie weit die Verfahren bei diesem konkreten Markt auseinanderliegen. Ein Pick, der nur
unter einem der Verfahren Value ist, ist kein Pick. Das ist keine Feinheit, sondern der
Unterschied zwischen einer Kante und einem Artefakt der Rechenvorschrift.

⚠️ Was die Literatur NICHT hergibt: dass Shin insgesamt „besser" wäre. Über den ganzen Markt
gemessen (RPS) ist der Unterschied ~0,0003 und in der neuesten Replikation sogar umgekehrt.
Whelan zeigt zudem, dass Shins z-Parameter mit r=0,99 schlicht mit dem Overround korreliert —
er misst die Marge, nicht Insiderhandel. Shin steht hier also NICHT, weil das Modell stimmt,
sondern weil seine Margenverteilung die gemessene Longshot-Ladung besser trifft als eine
gleichmäßige. Ein Werkzeug, keine Wahrheit.
"""
from __future__ import annotations

import math

VERFAHREN = ("multiplikativ", "shin", "power", "oddsRatio", "additiv")


def _inv(quoten):
    return [1.0 / float(o) for o in quoten]


def _ok(quoten) -> bool:
    try:
        return len(quoten) >= 2 and all(float(o) > 1.0 for o in quoten)
    except (TypeError, ValueError):
        return False


def multiplikativ(quoten):
    r = _inv(quoten)
    s = sum(r)
    return [x / s for x in r]


def additiv(quoten):
    r = _inv(quoten)
    s, n = sum(r), len(r)
    p = [x - (s - 1.0) / n for x in r]
    # Additiv kann bei langen Quoten NEGATIV werden. Dann ist es keine Wahrscheinlichkeit
    # mehr — lieber gar nichts als eine Zahl, die es nicht gibt.
    return p if all(x > 0 for x in p) else None


def _suche(f, lo, hi, schritte=90):
    """Monotone Bisektion auf Σp(x) = 1. Feste Schrittzahl = deterministisch und testbar."""
    for _ in range(schritte):
        m = (lo + hi) / 2.0
        if sum(f(m)) > 1.0:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2.0


def power(quoten):
    r = _inv(quoten)
    k = _suche(lambda k: [x ** k for x in r], 0.5, 3.0)
    p = [x ** k for x in r]
    s = sum(p)
    return [x / s for x in p]


def shin(quoten):
    r = _inv(quoten)
    b = sum(r)
    def pz(z):
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * x * x / b) - z) / (2.0 * (1.0 - z)) for x in r]
    z = _suche(pz, 1e-9, 0.6)
    p = pz(z)
    s = sum(p)
    return [x / s for x in p]


def odds_ratio(quoten):
    r = _inv(quoten)
    def por(o):
        return [x / (o + x - o * x) for x in r]
    o = _suche(por, 1e-6, 50.0, 120)
    p = por(o)
    s = sum(p)
    return [x / s for x in p]


_FN = {"multiplikativ": multiplikativ, "shin": shin, "power": power,
       "oddsRatio": odds_ratio, "additiv": additiv}


def entvigen(quoten, verfahren: str = "shin"):
    """Faire Wahrscheinlichkeiten nach einem benannten Verfahren, oder None."""
    if not _ok(quoten):
        return None
    f = _FN.get(verfahren)
    if f is None:
        raise ValueError("unbekanntes Verfahren: %r" % verfahren)
    try:
        return f([float(o) for o in quoten])
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def fair(quoten):
    """Das Verfahren, das zu diesem Markt passt — s. Kopf. Zwei Wege: multiplikativ (alle
    Verfahren identisch). Drei oder mehr: Shin (Marge liegt auf den langen Quoten)."""
    if not _ok(quoten):
        return None
    return entvigen(quoten, "multiplikativ" if len(quoten) == 2 else "shin")


def streuung(quoten):
    """Wie weit liegen die Verfahren bei DIESEM Markt auseinander? {feld: maxAbweichungPct}.

    Der eigentliche Zweck: ein Value-Flag, das nur unter EINEM Verfahren steht, ist ein Artefakt
    der Rechenvorschrift. Diese Zahl gehört deshalb neben jedes Flag — nicht in eine Fußnote.
    """
    if not _ok(quoten):
        return None
    saetze = []
    for v in VERFAHREN:
        p = entvigen(quoten, v)
        if p:
            saetze.append(p)
    if len(saetze) < 2:
        return None
    raus = []
    for i in range(len(quoten)):
        werte = [s[i] for s in saetze]
        lo, hi = min(werte), max(werte)
        raus.append(round(100.0 * (hi - lo) / lo, 2) if lo > 0 else None)
    return raus
