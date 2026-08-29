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


def is_confirmed_loser(score) -> bool:
    """P&L bekannt UND negativ. Unbekannt ist KEIN Verlierer-Nachweis."""
    if not isinstance(score, dict):
        return False
    pnl = score.get("pnl")
    return isinstance(pnl, (int, float)) and pnl < 0
