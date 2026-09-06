"""Der Lern-Loop muss gegen den PREIS lernen, nicht gegen die Trefferquote — 06.09.2026.

Anlass: `update_signal_weights` mass jedes Signal an der Trefferquote (erst gegen den
Muenzwurf, ab 30.08. gegen die eigene Basisquote). Beides sind Trefferquoten, und eine
Trefferquote ohne die Quoten ist keine Zahl (Bug-Klasse 6).

Gemessene Folge: `lead_lag_bias` — das Signal mit dem staerksten CLV-Zusammenhang
(r = +0,495) — stand in liga auf Gewicht 0,901, also gedaempft. Nach der Umstellung: 1,068.

Die Tests halten die REGEL fest: 0,5 heisst „genau wie bepreist", ein Favoritensieg ist
weniger wert als ein Aussenseitersieg, und ohne Quote gibt es keine Beobachtung.
"""
import unittest

# KEIN os.environ["COCOBET_DATASET"] hier — `test_mls_dataset_audit` verbietet genau das, und
# zu Recht: der Datensatz wird beim Import gelesen, ein Testmodul wuerde ihn fuer alle
# nachfolgenden Module umstellen. Dieser Test hat das beim ersten Lauf ausgeloest und 20
# fremde Tests mitgerissen. Die geprueften Funktionen sind rein und brauchen keinen Datensatz.
import update_signal_weights as U


def _pick(result, quote, verdict=None):
    p = {"result": result, "odds": quote}
    if verdict:
        p["processVerdict"] = verdict
    return p


class TestPreisJustierterOutcome(unittest.TestCase):
    def test_genau_wie_bepreist_ist_neutral(self):
        """Ein 50/50-Pick, gewonnen: 0,5 + (1,0 - 0,5)/2 = 0,75. Ein 50/50-Pick, verloren: 0,25.
        Im Mittel 0,5 — der neutrale Punkt faellt aus der Rechnung, nicht aus einer Schaetzung."""
        w = U._preis_justierter_outcome(_pick("WIN", 2.0))
        l = U._preis_justierter_outcome(_pick("LOSS", 2.0))
        self.assertAlmostEqual((w + l) / 2, 0.5, places=6)

    def test_favoritensieg_ist_weniger_wert_als_aussenseitersieg(self):
        """Der ganze Fehler in einem Satz: 70 % Treffer auf 1,30 war bisher ein Bonus."""
        fav = U._preis_justierter_outcome(_pick("WIN", 1.30))
        aus = U._preis_justierter_outcome(_pick("WIN", 3.00))
        self.assertLess(fav, aus)

    def test_favoritenniederlage_bestraft_haerter(self):
        fav = U._preis_justierter_outcome(_pick("LOSS", 1.30))
        aus = U._preis_justierter_outcome(_pick("LOSS", 3.00))
        self.assertLess(fav, aus)

    def test_bleibt_im_intervall(self):
        for q in (1.01, 1.2, 2.0, 5.0, 50.0):
            for r in ("WIN", "LOSS"):
                v = U._preis_justierter_outcome(_pick(r, q))
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)

    def test_ohne_quote_keine_beobachtung(self):
        """Fehlende Information ist keine Erlaubnis — kein Rueckfall auf die alte Trefferquote."""
        self.assertIsNone(U._preis_justierter_outcome({"result": "WIN"}))
        self.assertIsNone(U._preis_justierter_outcome({"result": "WIN", "odds": None}))
        self.assertIsNone(U._preis_justierter_outcome({"result": "WIN", "odds": 1.0}))
        self.assertIsNone(U._preis_justierter_outcome({"result": "WIN", "odds": "2.0"}))

    def test_bool_ist_keine_quote(self):
        self.assertIsNone(U._preis_justierter_outcome({"result": "WIN", "odds": True}))

    def test_ohne_ergebnis_keine_beobachtung(self):
        self.assertIsNone(U._preis_justierter_outcome({"odds": 2.0}))
        self.assertIsNone(U._preis_justierter_outcome({"result": "VOID", "odds": 2.0}))

    def test_entryodd_schlaegt_anzeigequote(self):
        """Gelernt wird an dem Preis, den wir wirklich genommen haben."""
        p = {"result": "WIN", "odds": 2.00, "entryOdd": 1.50}
        nur_anzeige = U._preis_justierter_outcome({"result": "WIN", "odds": 2.00})
        self.assertLess(U._preis_justierter_outcome(p), nur_anzeige)

    def test_unbrauchbare_entryodd_faellt_auf_odds_zurueck(self):
        p = {"result": "WIN", "odds": 2.00, "entryOdd": None}
        self.assertEqual(U._preis_justierter_outcome(p),
                         U._preis_justierter_outcome({"result": "WIN", "odds": 2.00}))

    def test_prozessurteil_wirkt_weiter(self):
        """LUCKY/UNLUCKY trennt Koennen von Varianz — das bleibt, nur der Massstab aendert sich."""
        gluecklich = U._preis_justierter_outcome(_pick("WIN", 2.0, "LUCKY"))
        verdient = U._preis_justierter_outcome(_pick("WIN", 2.0, "JUSTIFIED"))
        self.assertLess(gluecklich, verdient)


class TestNeutralerPunkt(unittest.TestCase):
    def test_ergebnisstrom_ist_gegen_0_5_geeicht(self):
        """Ueber viele Picks, die genau wie bepreist ausgehen, muss der Strom auf 0,5 landen —
        sonst ist der Nullpunkt wieder eine Schaetzung."""
        werte = []
        for quote, treffer in ((1.25, 4), (2.0, 1), (5.0, 1)):
            gesamt = {1.25: 5, 2.0: 2, 5.0: 5}[quote]
            werte += [U._preis_justierter_outcome(_pick("WIN", quote)) for _ in range(treffer)]
            werte += [U._preis_justierter_outcome(_pick("LOSS", quote))
                      for _ in range(gesamt - treffer)]
        self.assertAlmostEqual(sum(werte) / len(werte), 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
