"""Tests fuer preis_signal.py — 06.09.2026.

Die Tests halten die REGEL fest, nicht den heutigen Datenstand:
  • ohne Preis-Signal gibt es kein Urteil (None, nicht 0.0)
  • Staerke-Signale duerfen den Score nicht beruehren
  • bool ist keine Zahl
  • die Baender sind monoton in der gemessenen CLV
"""
import unittest

import preis_signal as P


def _pick(*paare):
    return {"signals": [{"name": n, "score": s} for n, s in paare]}


class TestPreisScore(unittest.TestCase):
    def test_ohne_preis_signal_kein_urteil(self):
        """Die Haelfte unserer Picks hat keinen Marktbezug. Das ist kein neutraler Score."""
        p = _pick(("form_trend", 1.6), ("xg_strength", 2.4), ("injury", -1.1))
        self.assertIsNone(P.preis_score(p))
        self.assertIsNone(P.urteil(p))

    def test_staerke_signale_zaehlen_nicht_mit(self):
        nur_preis = _pick(("betfair_money", 3.0))
        gemischt = _pick(("betfair_money", 3.0), ("form_trend", 9.9), ("xg_strength", -8.0))
        self.assertEqual(P.preis_score(nur_preis), P.preis_score(gemischt))

    def test_mehrere_preis_signale_summieren(self):
        p = _pick(("betfair_money", 1.5), ("lead_lag_bias", 2.0), ("opener_move", -0.5))
        self.assertAlmostEqual(P.preis_score(p), 3.0)

    def test_bool_ist_keine_zahl(self):
        """True ist in Python 1 — ohne Guard waere das ein stiller Score von 1.0."""
        self.assertIsNone(P.preis_score(_pick(("betfair_money", True))))

    def test_kaputte_eingaben(self):
        self.assertIsNone(P.preis_score(None))
        self.assertIsNone(P.preis_score({}))
        self.assertIsNone(P.preis_score({"signals": None}))
        self.assertIsNone(P.preis_score({"signals": ["kein dict"]}))
        self.assertIsNone(P.preis_score(_pick(("betfair_money", "viel"))))


class TestBand(unittest.TestCase):
    def test_schnitte(self):
        self.assertEqual(P.band(P.SCHNITT_UNTEN - 0.01), "spaet")
        self.assertEqual(P.band(P.SCHNITT_UNTEN), "mittel")
        self.assertEqual(P.band(P.SCHNITT_OBEN - 0.01), "mittel")
        self.assertEqual(P.band(P.SCHNITT_OBEN), "fair")

    def test_kein_score_kein_band(self):
        self.assertIsNone(P.band(None))
        self.assertIsNone(P.band(True))
        self.assertIsNone(P.band("4.0"))

    def test_baender_sind_monoton_in_der_gemessenen_clv(self):
        """Die Reihenfolge ist der ganze Befund. Kippt sie, ist das Modul falsch parametriert."""
        b = P.BAENDER
        self.assertLess(b["spaet"]["clvPP"], b["mittel"]["clvPP"])
        self.assertLess(b["mittel"]["clvPP"], b["fair"]["clvPP"])

    def test_kein_band_behauptet_einen_vorsprung(self):
        """Auch das beste Band liegt nicht ueber der Null — das darf kein Update still aendern."""
        for name, d in P.BAENDER.items():
            self.assertLessEqual(d["clvPP"], 0.0, f"{name} behauptet CLV ueber null")


class TestUrteil(unittest.TestCase):
    def test_traegt_das_gemessene_intervall_mit(self):
        u = P.urteil(_pick(("lead_lag_bias", 4.0), ("betfair_money", 2.5)))
        self.assertEqual(u["band"], "fair")
        self.assertEqual(u["signale"], ["betfair_money", "lead_lag_bias"])
        self.assertEqual(len(u["ki"]), 2)
        self.assertLess(u["ki"][0], u["clvPP"])
        self.assertGreater(u["ki"][1], u["clvPP"])
        self.assertGreaterEqual(u["n"], 30)

    def test_spaetes_band_ist_klar_unter_null(self):
        u = P.urteil(_pick(("public_static_bias", -2.0)))
        self.assertEqual(u["band"], "spaet")
        self.assertLess(u["ki"][1], 0.0)   # ganzes Intervall unter null


if __name__ == "__main__":
    unittest.main()
