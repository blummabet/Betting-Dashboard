#!/usr/bin/env python3
"""02.09.2026 — Lucas: „kannst du mal die inhalte hier checken bei 'Großes Geld' und 'Bewegung'
ob das vernünftig implementiert oder man da mehr rausholen kann".

Der Audit ergab, dass der Geld-Split zwei verschiedene Dinge war, und keines davon das, was
oben drueber stand. Gemessen ueber 1.912 Maerkte aus poly_money_broad_close.json:

  · ZWEI Ausgaenge (n=1.262): |Geld% − Preis| Median 0,0pp, 1262 von 1262 unter 1pp. Struktur:
    komplementaere Tokens -> Wert-Anteil = p/(1−p). Der Split IST der Preis.
  · DREI Ausgaenge (n=650): Abdeckung sum(shares)/totalUsd Median 36%, bei 79% unter 50%. Der
    Split ist ein Artefakt der Erfassungsluecke — ein leerer Holders-Abruf landete als 0.

Diese Tests nageln fest, dass die Anzeige das sagt, statt eine Seite zu behaupten. Sie sind
bewusst hart bei der einen Frage, um die es hier geht: darf aus fehlender Erfassung eine
Aussage werden? Nein.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_money_accuracy as PMA
import poly_money_broad as PMB


class SplitGueteTest(unittest.TestCase):
    def test_zwei_ausgaenge_sind_preis_echo(self):
        g = PMA.split_guete({"A": 60.0, "B": 40.0}, 100)
        self.assertEqual(g["art"], "preis_echo")

    def test_zwei_ausgaenge_bleiben_preis_echo_egal_wie_gut_erfasst(self):
        """Auch bei 100% Abdeckung sagt ein Zwei-Wege-Split nichts Eigenes — er ist der Preis."""
        self.assertEqual(PMA.split_guete({"A": 60.0, "B": 40.0}, 100)["art"], "preis_echo")

    def test_drei_ausgaenge_gut_erfasst_sind_belastbar(self):
        g = PMA.split_guete({"A": 60.0, "B": 20.0, "C": 5.0}, 100)
        self.assertEqual(g["art"], "belastbar")
        self.assertAlmostEqual(g["abdeckung"], 0.85)

    def test_drei_ausgaenge_duenn_erfasst_sind_nicht_belastbar(self):
        """Der Osasuna-Fall: 43% erfasst, 96,6% angeblich auf einer Seite bei 44,5¢."""
        g = PMA.split_guete({"Osasuna": 745597.0, "Draw": 13100.0, "Getafe": 13006.0}, 1796655)
        self.assertEqual(g["art"], "duenn")
        self.assertLess(g["abdeckung"], 0.5)

    def test_unbekanntes_volumen_ist_nicht_belastbar(self):
        """Ohne Nenner ist die Abdeckung unbekannt — und unbekannt ist kein Freibrief."""
        for tot in (0, None, "", -5):
            self.assertEqual(PMA.split_guete({"A": 1.0, "B": 1.0, "C": 1.0}, tot)["art"], "duenn")

    def test_leerer_oder_einseitiger_split(self):
        self.assertEqual(PMA.split_guete({}, 100)["art"], "leer")
        self.assertEqual(PMA.split_guete({"A": 5.0}, 100)["art"], "leer")
        self.assertEqual(PMA.split_guete({"A": 0.0, "B": 0.0}, 100)["art"], "leer")

    def test_nicht_numerische_werte_fliegen_raus(self):
        self.assertEqual(PMA.split_guete({"A": "viel", "B": 5.0}, 100)["art"], "leer")

    def test_schwelle_ist_die_dokumentierte(self):
        self.assertEqual(PMA.SPLIT_ABDECKUNG_MIN, 0.70)
        knapp_drunter = PMA.split_guete({"A": 60.0, "B": 5.0, "C": 4.0}, 100)
        self.assertEqual(knapp_drunter["art"], "duenn")

    def test_broad_reicht_dieselbe_funktion_durch(self):
        """Eine Quelle für die Güte — sonst driften Producer und Auswertung auseinander."""
        self.assertIs(PMB.split_guete, PMA.split_guete)


class EvaluateGattertTest(unittest.TestCase):
    """Der Rückblick darf nur über Märkte urteilen, deren Split etwas anderes sagen KANN
    als der Preis. Vorher stand ein „🔴 faden" über 848 Spielen, von denen fast keines
    auswertbar war."""

    def _frozen(self, n_belastbar=0, n_echo=0, n_duenn=0):
        f, res = {}, {}
        for i in range(n_belastbar):
            k = "bel%d" % i
            f[k] = {"shares": {"H": 80.0, "D": 10.0, "A": 5.0}, "totalUsd": 100,
                    "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "TESTLIGA"}
            res[k] = "H"
        for i in range(n_echo):
            k = "echo%d" % i
            f[k] = {"shares": {"H": 60.0, "A": 40.0}, "totalUsd": 100,
                    "prices": {"H": 0.6, "A": 0.4}, "league": "TESTLIGA"}
            res[k] = "H"
        for i in range(n_duenn):
            k = "dnn%d" % i
            f[k] = {"shares": {"H": 20.0, "D": 1.0, "A": 1.0}, "totalUsd": 100,
                    "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "TESTLIGA"}
            res[k] = "H"
        return f, res

    def test_preis_echo_und_duenne_zaehlen_nicht_mit(self):
        f, res = self._frozen(n_belastbar=2, n_echo=5, n_duenn=7)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["n"], 2)
        self.assertEqual(rep["guete"]["preis_echo"], 5)
        self.assertEqual(rep["guete"]["duenn"], 7)
        self.assertEqual(rep["guete"]["belastbar"], 2)

    def test_unter_der_mindeststichprobe_gibt_es_kein_urteil(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N - 1)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["verdict"], "zu wenig Daten")

    def test_ab_der_mindeststichprobe_gibt_es_eines(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertNotEqual(rep["verdict"], "zu wenig Daten")

    def test_liga_urteil_erst_ab_eigener_mindeststichprobe(self):
        f, res = self._frozen(n_belastbar=PMA.URTEIL_MIN_N_LIGA - 1)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["byLeague"], [])

    def test_guete_steht_auch_bei_null_gewerteten_maerkten_da(self):
        f, res = self._frozen(n_echo=4)
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual(rep["n"], 0)
        self.assertEqual(rep["guete"]["preis_echo"], 4)


class LigaAusSlugTest(unittest.TestCase):
    """`SOCCER` war mit 39% der groesste Eimer der Liga-Tabelle und trug keinen Liganamen.
    Die Zuordnung wird aus den eigenen Daten gelernt, nicht geraten."""

    def test_spezifisches_label_bleibt_unangetastet(self):
        self.assertEqual(PMA.liga_label("lal-a-b-2026-01-01", "EPL", {"lal": "LA-LIGA"}), "EPL")

    def test_generisches_label_wird_ueber_den_praefix_aufgeloest(self):
        self.assertEqual(PMA.liga_label("lal-osa-get-2026-08-31", "SOCCER", {"lal": "LA-LIGA"}), "LA-LIGA")

    def test_unbekannter_praefix_bleibt_getrennt_aber_unbenannt(self):
        self.assertEqual(PMA.liga_label("mex-a-b-2026-01-01", "SOCCER", {}), "SOCCER:MEX")

    def test_gelernt_wird_erst_ab_genug_belegen(self):
        self.assertEqual(PMA.liga_lernen([("col-a", "UECL")] * (PMA.LIGA_MIN_BELEGE - 1)), {})
        self.assertEqual(PMA.liga_lernen([("col-a", "UECL")] * PMA.LIGA_MIN_BELEGE), {"col": "UECL"})

    def test_uneindeutiger_praefix_wird_nicht_gelernt(self):
        eintraege = [("col-a", "UECL")] * 3 + [("col-b", "COLOMBIA")] * 3
        self.assertEqual(PMA.liga_lernen(eintraege), {})

    def test_generische_labels_lehren_nichts(self):
        self.assertEqual(PMA.liga_lernen([("lal-a", "SOCCER")] * 9), {})

    def test_evaluate_loest_soccer_auf(self):
        f = {"lal-x-2026-01-01": {"shares": {"H": 80.0, "D": 10.0, "A": 5.0}, "totalUsd": 100,
                                  "prices": {"H": 0.5, "D": 0.3, "A": 0.2}, "league": "SOCCER"}}
        for i in range(PMA.LIGA_MIN_BELEGE):
            f["lal-lehr%d-2026-01-01" % i] = {"shares": {"H": 1.0, "A": 1.0}, "totalUsd": 100,
                                              "prices": {"H": 0.5, "A": 0.5}, "league": "LA-LIGA"}
        res = {k: "H" for k in f}
        rep = PMA.evaluate(f, res, min_odds=1.35)
        self.assertEqual([r["league"] for r in rep["rows"]], ["LA-LIGA"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
