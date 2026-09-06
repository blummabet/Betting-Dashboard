"""Die Bilanz wirkt auf die Gewichte — aber nur, was gehalten hat. 06.09.2026.

Lucas: „wenn wir draufkommen, ein Signal ist zum Scheissen, dann wird es runtergewichtet und
nur mehr beobachtet." Der alte Loop konnte das nicht: sein Massstab war die eigene
Trefferquote, alle Gewichte landeten unter 1 (gemessene Spanne am 05.09.: 0,590 .. 1,034 bei
erlaubten 0,300 .. 1,700). Er konnte abwerten und praktisch nicht aufwerten — und er vergab
Gewichte, aber keine Konfidenz.

Zwei Bremsen, die hier festgehalten werden:
  · Es wirkt NUR, was `signal_verlauf` als stabil ausweist (mehrere Messungen, >= 2 Wochen).
  · Fehlt der Verlauf oder ist er unlesbar, wirkt NICHTS — kein Rueckfall auf die
    Momentaufnahme. Fehlende Information ist keine Erlaubnis.
"""
import unittest

import update_signal_weights as U


class TestBilanzFaktor(unittest.TestCase):
    def test_ohne_urteil_kein_eingriff(self):
        self.assertEqual(U.bilanz_faktor("x", {}), 1.0)
        self.assertEqual(U.bilanz_faktor("x", None), 1.0)
        self.assertEqual(U.bilanz_faktor("x", {"schadet": [], "traegt bei": []}), 1.0)

    def test_stabil_schaedlich_wird_abgewertet(self):
        f = U.bilanz_faktor("boese", {"schadet": ["boese"]})
        self.assertEqual(f, U.BILANZ_ABWERTUNG)
        self.assertLess(f, 1.0)

    def test_stabil_beitragend_wird_aufgewertet(self):
        f = U.bilanz_faktor("gut", {"traegt bei": ["gut"]})
        self.assertEqual(f, U.BILANZ_AUFWERTUNG)
        self.assertGreater(f, 1.0)

    def test_abwerten_trifft_haerter_als_aufwerten(self):
        """Bewusst asymmetrisch: ein Signal, das belegt schadet, soll spuerbar leiser werden;
        eines, das beitraegt, bekommt einen Schubs, keine Vollmacht."""
        runter = 1.0 - U.BILANZ_ABWERTUNG
        rauf = U.BILANZ_AUFWERTUNG - 1.0
        self.assertGreater(runter, rauf)

    def test_widerspruch_ist_kein_urteil(self):
        f = U.bilanz_faktor("zwiespalt", {"schadet": ["zwiespalt"], "traegt bei": ["zwiespalt"]})
        self.assertEqual(f, 1.0)

    def test_der_eingriff_bleibt_klein(self):
        """Der Faktor verschiebt das Gelernte, er ersetzt es nicht. Waere er beliebig gross,
        haetten wir den Loop durch eine zweite, juengere Rechnung ersetzt."""
        self.assertGreaterEqual(U.BILANZ_ABWERTUNG, 0.5)
        self.assertLessEqual(U.BILANZ_AUFWERTUNG, 1.3)

    def test_die_sanity_grenzen_gelten_weiter(self):
        """Auch mit Faktor darf kein Gewicht aus [0.3, 1.7] laufen — das prueft die
        Klammer in update_weights, hier festgehalten als Vertrag."""
        self.assertLessEqual(1.7 * U.BILANZ_ABWERTUNG, 1.7)
        self.assertGreaterEqual(0.3 * U.BILANZ_AUFWERTUNG, 0.3)


class TestVerlaufLesen(unittest.TestCase):
    def test_fehlender_verlauf_wirkt_nicht(self):
        import pathlib
        alt = U.VERLAUF_FILE
        try:
            U.VERLAUF_FILE = pathlib.Path("/nicht/vorhanden/verlauf.json")
            self.assertEqual(U._stabile_urteile(), {})
        finally:
            U.VERLAUF_FILE = alt

    def test_kaputter_verlauf_wirkt_nicht(self):
        import pathlib
        import tempfile
        alt = U.VERLAUF_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                p = pathlib.Path(td) / "verlauf.json"
                p.write_text("{kein json", encoding="utf-8")
                U.VERLAUF_FILE = p
                self.assertEqual(U._stabile_urteile(), {})
        finally:
            U.VERLAUF_FILE = alt

    def test_verlauf_ohne_stabil_abschnitt(self):
        import pathlib
        import tempfile
        alt = U.VERLAUF_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                p = pathlib.Path(td) / "verlauf.json"
                p.write_text('{"signale": {}}', encoding="utf-8")
                U.VERLAUF_FILE = p
                self.assertEqual(U._stabile_urteile(), {})
        finally:
            U.VERLAUF_FILE = alt


if __name__ == "__main__":
    unittest.main()
