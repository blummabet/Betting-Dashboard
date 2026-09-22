#!/usr/bin/env python3
"""
tests/test_endstand_ausweg.py — 22.09.2026: der Ausgang stand die ganze Zeit daneben.

🔴 Lucas' Störungsmeldung vom 22.09., 06:02 UTC, unter „Kostet Geld":

    spl-haz-taa-2026-09-08-more-markets: seit 13.6 Tagen offen
    ucl-aek1-lin2-2026-09-08-more-markets: seit 13.5 Tagen offen
    — Bündel: der Eintrag kennt seinen Markt, die Auflösung nicht (Altbestand)

Der Riegel dahinter ist richtig: die Auflösung sagt „Under", und in einem `-more-markets`-Bündel
liegen Under 1,5 und Under 3,5 nebeneinander. Ohne `cond` auf beiden Seiten ist „Under" kein
Ergebnis. Nach 14 Tagen wären beide als „unauflösbar" verfallen — einer davon ein Treffer.

Nur: die Auflösung `…-exact-score` desselben Spiels trägt den ENDSTAND, und der Eintrag trägt
seit dem 10.09. die LINIE im Klartext. AEK 1:0 LASK, Linie 3,5 → Under. Das ist keine Schätzung,
das ist Arithmetik.

Fehlerklasse: **eine Frage für unbeantwortbar erklärt, während ihre Antwort in der Datei daneben
steht.**

Der zweite Teil ist wichtiger als der erste: die Regel darf NUR rechnen, wo sie eindeutig ist.
Vereinsnamen tragen Ziffern, Linien können ganzzahlig sein, und ein Push hat keinen Sieger.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_slug_urteil as U


class TestDieBeidenEchtenFaelle(unittest.TestCase):
    def test_aek_lask(self):
        """AEK 1:0 LASK, O/U 3.5 → Under. Der Eintrag stand auf Under: ein Treffer, der
        verfallen wäre."""
        self.assertEqual(
            U.ausgang_aus_endstand("AEK vs. LASK Linz: O/U 3.5", "AEK 1 - 0 LASK Linz"), "Under")

    def test_al_hazem(self):
        """1:0, O/U 2.5 → Under. Der Eintrag stand auf Over: ein Verlust, der ebenso in die
        Bilanz gehört — sonst rechnet man nur die guten Fälle nach."""
        self.assertEqual(
            U.ausgang_aus_endstand("Al Hazem SC vs. Al Taawoun Saudi Club: O/U 2.5",
                                   "Al Hazem SC 1 - 0 Al Taawoun Saudi Club"), "Under")


class TestDieLinie(unittest.TestCase):
    def test_die_ueblichen_schreibweisen(self):
        for t, erwartet in (("A vs. B: O/U 3.5", 3.5), ("A vs B: OU 2.5", 2.5),
                            ("A vs B: Over/Under 1.5", 1.5), ("A vs B: Totals 4.5", 4.5),
                            ("A vs B: O/U 2,5", 2.5)):
            self.assertEqual(U.linie(t), erwartet, t)

    def test_zwei_linien_sind_keine_antwort(self):
        """Zwei Linien im Text heissen zwei Märkte."""
        self.assertIsNone(U.linie("A vs B: O/U 2.5 und O/U 3.5"))

    def test_keine_linie(self):
        for t in ("AEK vs. LASK Linz", "", None, "A vs B: Beide treffen"):
            self.assertIsNone(U.linie(t))


class TestDerEndstand(unittest.TestCase):
    def test_der_normalfall(self):
        self.assertEqual(U.endstand("AEK 1 - 0 LASK Linz"), (1, 0))
        self.assertEqual(U.endstand("A 12 - 3 B"), (12, 3))
        self.assertEqual(U.endstand("A 2:1 B"), (2, 1))

    def test_eine_ziffer_im_vereinsnamen_kippt_ihn_nicht(self):
        """⭐ „FC Schalke 04" — die Falle, an der eine naive Regel stirbt."""
        self.assertEqual(U.endstand("FC Schalke 04 2 - 1 Hertha"), (2, 1))
        self.assertEqual(U.endstand("Bayern 1 - 0 FC Schalke 04"), (1, 0))

    def test_eine_jahreszahl_zaehlt_nicht_als_endstand(self):
        """„FC 1899 - 2000" faellt am Stellen-Limit raus, nicht am Zaehlen der Treffer."""
        self.assertEqual(U.endstand("FC 1899 - 2000 vs X 2 - 1 Y"), (2, 1))

    def test_zwei_echte_muster_sind_keine_antwort(self):
        """Lieber keine Abrechnung als eine geratene."""
        self.assertIsNone(U.endstand("A 1 - 0 B 2 - 1 C"))

    def test_gar_kein_endstand(self):
        for t in ("AEK", "", None, "Goalscorer: Razvan Marin"):
            self.assertIsNone(U.endstand(t))


class TestWoSieSchweigenMuss(unittest.TestCase):
    def test_ganzzahlige_linie_genau_getroffen_ist_ein_push(self):
        """⭐ Der wichtigste Nicht-Fall. Bei O/U 3 und 3 Toren gibt es keinen Sieger — „Under"
        hinzuschreiben wäre ein erfundener Ausgang."""
        self.assertIsNone(U.ausgang_aus_endstand("A vs B: O/U 3", "A 2 - 1 B"))

    def test_ganzzahlige_linie_sonst_entscheidet_normal(self):
        self.assertEqual(U.ausgang_aus_endstand("A vs B: O/U 3", "A 3 - 1 B"), "Over")
        self.assertEqual(U.ausgang_aus_endstand("A vs B: O/U 3", "A 1 - 1 B"), "Under")

    def test_ohne_linie_kein_ausgang(self):
        self.assertIsNone(U.ausgang_aus_endstand("AEK vs. LASK Linz", "AEK 1 - 0 LASK Linz"))

    def test_ohne_endstand_kein_ausgang(self):
        self.assertIsNone(U.ausgang_aus_endstand("A vs B: O/U 3.5", "AEK"))
        self.assertIsNone(U.ausgang_aus_endstand("A vs B: O/U 3.5", None))

    def test_beide_richtungen_werden_wirklich_gerechnet(self):
        """Gegenprobe: eine Regel, die immer „Under" sagt, wäre bei den beiden echten Fällen
        oben genauso grün."""
        self.assertEqual(U.ausgang_aus_endstand("A vs B: O/U 2.5", "A 3 - 1 B"), "Over")
        self.assertEqual(U.ausgang_aus_endstand("A vs B: O/U 2.5", "A 1 - 0 B"), "Under")


if __name__ == "__main__":
    unittest.main()
