#!/usr/bin/env python3
"""
sharp_gate.py — 29.08.2026 (Lucas: „prinzipiell checken, welche Wallets wir tracken").

DIE Definition von „scharf". Vorher gab es vier:

  _pwIsSharpScore  (poly-wallets.js)   n>=4 · rohe Quote >=55% · CLV>=0 · P&L>0 ZWINGEND
  _is_smart        (poly_whale_watch)  n>=8 · Wilson >50%      · CLV>=0 · P&L unbekannt OK
  is_sharp         (poly_live_watch)   handkopierte Klammer der JS-Konstanten
  SHARP_MIN_CLV    (poly_money_broad)  n>=4 · Quote >=50%      · CLV>=1.5pp   (seit 05.08. tot)

Gemessen am Stand vom 29.08. lieferten die zwei lebenden Gates 42 bzw. 16 Wallets bei einer
Schnittmenge von 15 — 27 Wallets trugen also auf der Seite Konviktion, die im Push nie als
bewiesen gegolten haetten. Schlimmer: die beiden behandelten fehlende Daten GENAU UMGEKEHRT.
Das Gate, das wirklich sendet, liess unbekannten P&L durch; das Gate, das nur anzeigt, warf ihn
raus — obwohl nur 13% aller Wallets ueberhaupt einen P&L-Wert haben. Damit entschied nicht die
Qualitaet einer Wallet, sondern ob das 60er-Fetch-Budget sie erwischt hatte.

Was hier gilt, und warum:

  n >= SHARP_MIN_N (8)
      Der alte JS-Boden von 4 war ohnehin Dekoration: `enrich_wallet_pnl` holt P&L erst ab n>=5,
      und das JS-Gate verlangte P&L>0 — von 131 Wallets mit exakt n=4 hatte KEINE einen Wert.
      n>=4 und n>=8 lieferten deshalb dasselbe Ergebnis. Jetzt steht die 8 ehrlich da.

  Wilson-Untergrenze der Trefferquote > 50% (einseitig, z=1.645)
      Eine rohe Quote von 55% bei n=9 ist kein Beweis: 5/9 hat eine Wilson-Untergrenze von 30%.
      Von den 42 Wallets, die das alte JS-Gate „scharf" nannte, bestanden 27 diesen Test nicht —
      darunter eine mit 5/9, CLV +0,03pp und $729 Lebensbilanz. Die Stichprobe entscheidet mit,
      nicht nur der Anteil.

  Ø CLV >= 0
      Eine hohe Quote ohne CLV ist Glueck. Bleibt wie gehabt.

  KEIN bestaetigter Verlierer (P&L bekannt UND < 0)
      P&L ist ein AUSSCHLUSS, kein Beweis. Zwei Gruende: er ist bei 87% der Wallets unbekannt,
      und er misst etwas anderes als die Trefferquote — `hit` kommt aus den Positionen, die wir
      sehen (je Markt die 4 groessten Holder), `pnl` aus `/user-pnl?interval=all`, also der
      gesamten Polymarket-Lebensbilanz inklusive Wahlen und Krypto. Wer +$3,7 Mio aus Wahlmaerkten
      hat, kann im Fussball trotzdem nichts koennen. Beides zu einem „bewiesen" zu verrechnen war
      eine Vermischung zweier Welten.

Die JS-Seite (poly-wallets.js `_pwIsSharpScore`) spiegelt das. Geteilter Code geht ueber die
Sprachgrenze nicht, ein geteilter VERTRAG schon: tests/fixtures/sharp_gate_cases.json haelt die
Faelle, und sowohl pytest als auch node pruefen beide Implementierungen dagegen. Weicht eine ab,
faellt es sofort auf — nicht erst, wenn die Seite etwas anderes behauptet als der Push.

Rein/netzfrei/testbar.
"""
from __future__ import annotations

import math
import os

SHARP_MIN_N = int(os.environ.get("SHARP_MIN_N") or 8)
# 1.645 = 95% einseitig („signifikant ueber 50%"); 1.2816 = 90% (mehr Treffer), 1.96 = strenger.
SHARP_Z = float(os.environ.get("SHARP_Z") or 1.645)


def wilson_lb(wins, n, z: float = SHARP_Z) -> float:
    """Untere Wilson-Grenze der Trefferquote. Robuster als die rohe Quote bei kleinem n:
    sie zieht sich mit der Stichprobe zusammen, statt 5/9 wie 500/900 zu behandeln."""
    n = int(n or 0)
    if n <= 0:
        return 0.0
    p = (wins or 0) / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - margin


def beats_coinflip(wins, n, z: float = SHARP_Z) -> bool:
    """Ist die Trefferquote SIGNIFIKANT ueber 50% — oder koennte es Zufall sein?"""
    return bool(n) and wilson_lb(wins, n, z) > 0.5


def _felder(score):
    """Nimmt beide Formen: die rohe aus poly_wallet_track.json ({n, wins, clvSumPP, pnl}) und die
    abgeleitete des Frontends ({n, hit, avgClv, pnl}). Gibt (n, wins, avg_clv, pnl) zurueck;
    pnl ist None, wenn UNBEKANNT — der Unterschied zu 0.0 ist der ganze Punkt."""
    if not isinstance(score, dict):
        return 0, 0, 0.0, None
    n = int(score.get("n") or 0)
    if n <= 0:
        return 0, 0, 0.0, None
    wins = score.get("wins")
    if wins is None:
        wins = round(float(score.get("hit") or 0) * n)
    if "avgClv" in score and score.get("avgClv") is not None:
        avg_clv = float(score.get("avgClv") or 0)
    else:
        avg_clv = float(score.get("clvSumPP") or 0) / n
    pnl = score.get("pnl")
    pnl = float(pnl) if isinstance(pnl, (int, float)) else None
    return n, int(wins), avg_clv, pnl


def is_sharp(score, min_n: int = SHARP_MIN_N, z: float = SHARP_Z) -> bool:
    """Die eine Definition. Siehe Modul-Doku fuer das Warum je Bedingung."""
    n, wins, avg_clv, pnl = _felder(score)
    if n < min_n:
        return False
    if not beats_coinflip(wins, n, z):
        return False
    if avg_clv < 0:
        return False
    if pnl is not None and pnl < 0:      # bestaetigter Verlierer raus; unbekannt bleibt drin
        return False
    return True


# ── Der Regler (01.09.2026) ──────────────────────────────────────────────────
# Gemessen, warum das binaere Gate allein zu teuer ist: Wallets auf dem Stand 25.08.
# klassifiziert und danach ausgewertet, was sie WIRKLICH getan haben (Delta der Aggregate
# in poly_wallet_track.json — reine Vorwaerts-Leistung, kein Rueckblick):
#
#   z=1.645 (dieses Gate)  16 Wallets  ->  n=180  54,4% Treffer (UG 48,3%)  Ø CLV +0,26pp
#   z=1.282                24 Wallets  ->  n=251  55,8%         (UG 50,6%)  Ø CLV +0,55pp
#   z=1.036                33 Wallets  ->  n=290  55,2%         (UG 50,3%)  Ø CLV +0,61pp
#
#   die ausgeschlossene Bande (rohe Quote >=55%, Wilson-UG <=50%, CLV>=0):
#                          35 Wallets  ->  n=136  52,2%                     Ø CLV +0,94pp
#
# Die strengste Einstellung liefert die SCHLECHTESTE Vorwaerts-Leistung auf jeder Achse.
# Die Strenge kauft keine Treffsicherheit, sie kauft eine kleinere, verrauschtere Auswahl.
#
# ⚠️ Der Fehler lag nicht in der Schwelle, sondern in der FORM: `is_sharp` ist ein Schalter.
# Eine Wallet mit 60% aus 65 Plays (Wilson-UG 49,8% — zwei Zehntel zu wenig) trug dieselbe
# Null bei wie eine mit 30% aus 8. Genau drei solcher Wallets lieferten danach +1,28 / +1,89 /
# +1,91pp CLV.
#
# Deshalb: fuer Zwecke, die ABWAEGEN (die Conviction), ein Regler statt eines Schalters.
# Fuer Zwecke, die VEROEFFENTLICHEN (der Public-Push), bleibt der Schalter — dort kostet ein
# Fehlalarm Glaubwuerdigkeit, und Strenge ist der richtige Preis dafuer.
#
# ⚠️ NICHT auf den Sieger getunt: vier z-Werte auf EINEM Wochenfenster, da ist der Beste
# teilweise Zufall. Belegt ist nur, dass 1,645 nicht besser ist als lockerer. Die Rampe
# umgeht die Frage, statt sie zu beantworten — sie braucht keinen zweiten Schwellenwert.
GRADE_FLOOR_LB = float(os.environ.get("SHARP_GRADE_FLOOR") or 0.40)


def sharp_grade(score, min_n: int = SHARP_MIN_N, z: float = SHARP_Z,
                floor: float = GRADE_FLOOR_LB) -> float:
    """Wie gut ist diese Wallet BELEGT? 0.0 (gar nicht) bis 1.0 (bewiesen). REIN.

    Die harten Ausschluesse sind dieselben wie in `is_sharp` — zu wenig Plays, negativer CLV,
    bestaetigter Verlierer geben 0.0. Dazwischen laeuft die Wilson-Untergrenze linear:
    bei >50% voll, bei <=`floor` null. Kein Sprung an der 50%-Klippe.

    Damit gilt per Konstruktion `is_sharp(s) == (sharp_grade(s) >= 1.0)` — eine Definition,
    zwei Lesarten. Der Test haelt das fest.
    """
    n, wins, avg_clv, pnl = _felder(score)
    if n < min_n:
        return 0.0
    if avg_clv < 0:
        return 0.0
    if pnl is not None and pnl < 0:
        return 0.0
    lb = wilson_lb(wins, n, z)
    if lb > 0.5:
        return 1.0
    if lb <= floor or floor >= 0.5:
        return 0.0
    return (lb - floor) / (0.5 - floor)


def is_confirmed_loser(score) -> bool:
    """P&L bekannt UND negativ. Unbekannt ist KEIN Verlierer-Nachweis."""
    if not isinstance(score, dict):
        return False
    pnl = score.get("pnl")
    return isinstance(pnl, (int, float)) and pnl < 0
