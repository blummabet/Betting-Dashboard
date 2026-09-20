#!/usr/bin/env python3
"""test_sichtbar_ab.py — der Maßstab neben der grünen Zahl (20.09.2026).

Lucas: „ob jetzt dann zum Beispiel bestimmte Ligen höhere Trefferquote haben … entweder
verstehst du mich falsch oder es ist nicht höher, obwohl dort eine höhere grüne Zahl steht.
Ach, ich verstehe es nicht."

Er hat die Tafel richtig gelesen — die +87 % sind echt passiert. Was fehlte, war der Maßstab.
Vorgeführt an seinen eigenen 32.055 Zeilen: Liga-Etiketten zufällig vertauscht, also ein
garantiert NICHT vorhandener Liga-Effekt — die Spitze sah aus wie vorher (+65 %, +63 %, +60 %
bei n=20..34). Bei 2254 Eimern mit im Median 11 Spielen muss einer oben stehen.
"""
import math
import random
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from betfair_track_record import _sichtbar_ab, _ug  # noqa: E402


def _reihe(n, quote=2.0, treffer=None):
    """n Wetten zur selben Quote; `treffer` davon gewonnen."""
    treffer = n // 2 if treffer is None else treffer
    xs = [(quote - 1.0)] * treffer + [-1.0] * (n - treffer)
    return n, sum(xs), sum(x * x for x in xs)


class TestSichtbarAb(unittest.TestCase):
    def test_weniger_spiele_verlangen_mehr_vorsprung(self):
        klein = _sichtbar_ab(*_reihe(20))
        gross = _sichtbar_ab(*_reihe(200))
        self.assertGreater(klein, gross)
        # zehnmal so viele Spiele → rund sqrt(10)-mal kleinere Schranke (3,24 gemessen,
        # 3,16 theoretisch; die Differenz ist der (n-1)-Nenner bei kleinem n)
        self.assertAlmostEqual(klein / gross, math.sqrt(10), delta=0.15)

    def test_die_groessenordnung_stimmt_mit_der_tafel(self):
        """Am echten Bestand: 22 Spiele verlangen rund +64 %, 30 rund +68 %."""
        s = _sichtbar_ab(*_reihe(22, quote=3.0))
        self.assertTrue(0.3 < s < 1.2, s)

    def test_unter_zehn_spielen_wird_nichts_behauptet(self):
        """Die Näherung taugt dort nicht — und eine Zahl, die man nicht glauben kann, ist
        schlimmer als keine."""
        for n in (0, 1, 5, 9):
            self.assertIsNone(_sichtbar_ab(*_reihe(max(n, 1))) if n else _sichtbar_ab(0, 0.0, 0.0),
                              "n=%d" % n)
        self.assertIsNotNone(_sichtbar_ab(*_reihe(10)))

    def test_ohne_streuung_kein_urteil(self):
        """Zehnmal dasselbe Ergebnis heißt nicht Gewissheit, sondern zu wenig Daten."""
        self.assertIsNone(_sichtbar_ab(10, -10.0, 10.0))

    def test_sie_ist_nie_null(self):
        """Eine Schranke von 0 würde JEDE positive Zeile durchwinken — genau die Falle,
        gegen die die Spalte gebaut ist."""
        for n in (10, 30, 100, 1000):
            self.assertGreater(_sichtbar_ab(*_reihe(n)), 0.0, "n=%d" % n)

    def test_es_ist_KEINE_zweite_schwelle_neben_roiUg(self):
        """Zwei Schwellen für dieselbe Sache wären der Fehler. `roi > sichtbarAb` muss genau
        dann gelten, wenn `roiUg > 0` — dieselbe Wahrheit, andere Sprache."""
        random.seed(5)
        geprueft = 0
        for _ in range(3000):
            n = random.randint(30, 300)
            xs = [random.choice([-1.0, random.uniform(0.2, 4.0)]) for _ in range(n)]
            S, Q = sum(xs), sum(x * x for x in xs)
            sa, ug = _sichtbar_ab(n, S, Q), _ug(n, S, Q)
            if sa is None or ug is None:
                continue
            geprueft += 1
            self.assertEqual((S / n) > sa, ug > 0,
                             "n=%d roi=%.3f sichtbarAb=%.3f roiUg=%.3f" % (n, S / n, sa, ug))
        self.assertGreater(geprueft, 2900)


if __name__ == "__main__":
    unittest.main()
