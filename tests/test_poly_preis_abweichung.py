#!/usr/bin/env python3
"""03.09.2026 — Lucas: „Was fehlt dann noch von Poly bei dem Betis - Real Madrid Beispiel?"

Das Geld. Komplett. Die Zeile kam aus dem pinnacle_poly_scan (`src="scan"`), der nur ein
Preis-Tripel und ein `vol` liefert — `shares` ist dort per Konstruktion leer:

    poly: [0.45, 0.195, 0.475]      drei Preise
    vol:  74.0                      vierundsiebzig Dollar

Der Geld-Scan hatte den Markt nicht, weil er zwei Bedingungen verfehlt: Anpfiff in ~36h
(Fenster 3h) und $74 Volumen (Schwelle $7.500). Beides normal so frueh.

Der eigentliche Befund kam beim Nachsehen: der Poly-Preis sagte 47,5¢ fuer Real Madrid,
Pinnacle 69%, Betfair 92% Geldanteil bei Quote 1,41 (~71%). Gut zwanzig Punkte daneben — kein
Widerspruch aus Ueberzeugung, sondern ein Eroeffnungskurs, den niemand angefasst hat. Und die
„Zustimmung" bestand darin, dass 47,5¢ knapp ueber 45¢ lag: zweieinhalb Cent bei $74 Umsatz.

Diese Tests nageln fest, dass so ein Preis seine Abweichung mittraegt, statt als Anlehnung
gelesen zu werden.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_consensus as BC

# Die echten Zahlen aus money_map.json vom 03.09.2026.
PINN_BETIS = {"fav": "away", "home": 0.1264, "draw": 0.1796, "away": 0.694}
POLY_BETIS = {"side": "away", "name": "Real Madrid CF", "sharePct": 48, "usd": 74, "src": "scan"}


class AbweichungTest(unittest.TestCase):
    def test_der_betis_fall_wird_beziffert(self):
        self.assertAlmostEqual(BC.poly_preis_abweichung(POLY_BETIS, PINN_BETIS), 21.4, places=1)

    def test_ein_naher_preis_faellt_nicht_auf(self):
        nah = dict(POLY_BETIS, sharePct=70)
        self.assertLess(BC.poly_preis_abweichung(nah, PINN_BETIS), BC.POLY_PREIS_MAX_ABW_PP)

    def test_echtes_geld_wird_gar_nicht_erst_verglichen(self):
        """`sharePct` misst dort GELD, nicht einen Preis — die beiden sind nicht vergleichbar.
        Ein Geld-Anteil, der vom Anker abweicht, ist ja gerade das Signal."""
        for quelle in ("close", "upcoming", None):
            self.assertIsNone(BC.poly_preis_abweichung(dict(POLY_BETIS, src=quelle), PINN_BETIS))

    def test_ohne_anker_oder_ohne_preis_gibt_es_nichts_zu_messen(self):
        self.assertIsNone(BC.poly_preis_abweichung(POLY_BETIS, None))
        self.assertIsNone(BC.poly_preis_abweichung(None, PINN_BETIS))
        self.assertIsNone(BC.poly_preis_abweichung(dict(POLY_BETIS, sharePct=None), PINN_BETIS))
        self.assertIsNone(BC.poly_preis_abweichung(POLY_BETIS, {"fav": "away", "home": 0.5}))


class ZeileTest(unittest.TestCase):
    def _spiel(self):
        return {"matchId": "35996596", "home": "Betis", "away": "Real Madrid",
                "league": "Spanish La Liga", "live": False, "kickoff": "2026-09-04T19:00:00Z",
                "verdict": "konsens", "moneySide": "away", "moneyName": "Real Madrid",
                "moneySharePct": 92, "totVol": 248367, "moneyOdd": 1.41, "pinn": PINN_BETIS}

    def test_die_zeile_traegt_die_abweichung_mit(self):
        r = BC.money_map_row(self._spiel(), POLY_BETIS)
        self.assertAlmostEqual(r["polyPreisAbwPP"], 21.4, places=1)
        self.assertTrue(r["polyPreisWeit"])

    def test_der_scan_preis_zaehlt_weiterhin_nicht_als_quelle(self):
        """Das galt schon seit dem 30.08. — hier nur festgehalten, damit es beim Umbau bleibt."""
        r = BC.money_map_row(self._spiel(), POLY_BETIS)
        self.assertFalse(r["polyGeld"])
        self.assertEqual(r["nSources"], 2)

    def test_die_poly_seite_bleibt_sichtbar(self):
        """Weggelassen wird sie NICHT — sie ist eine Information, nur eben keine Zustimmung."""
        r = BC.money_map_row(self._spiel(), POLY_BETIS)
        self.assertEqual(r["poly"]["side"], "away")
        self.assertEqual(r["poly"]["usd"], 74)

    def test_ein_naher_scan_preis_wird_nicht_angeprangert(self):
        r = BC.money_map_row(self._spiel(), dict(POLY_BETIS, sharePct=70))
        self.assertFalse(r["polyPreisWeit"])

    def test_ohne_scan_preis_stehen_die_felder_gar_nicht_erst_da(self):
        """Kein Feld ist ehrlicher als ein Feld mit einer Null, die nichts bedeutet."""
        r = BC.money_map_row(self._spiel(), dict(POLY_BETIS, src="close"))
        self.assertNotIn("polyPreisAbwPP", r)
        self.assertNotIn("polyPreisWeit", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
