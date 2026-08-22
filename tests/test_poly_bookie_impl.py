#!/usr/bin/env python3
"""test_poly_bookie_impl.py — 22.08.2026 (Lucas): Pinnacle-Fair pro Markt fuer den Poly-Trader.
1X2/O2.5 aus *_fair-Keys (pinn_ bevorzugt, sonst plain), O1.5/O3.5/BTTS on-the-fly de-viggt."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_poly_prices as F


class TestBookieImpl(unittest.TestCase):
    ODDS = {
        "pinn_hw_fair": 1.69, "hw_fair": 1.69, "dr_fair": 4.20, "aw_fair": 5.86,
        "o25_fair": 1.99, "o15": 1.30, "u15": 3.65, "o35": 3.36, "u35": 1.35,
        "bttsY": 1.98, "bttsN": 1.87,
    }

    def test_fair_1x2(self):
        self.assertAlmostEqual(F._bookie_impl(self.ODDS, "Heimsieg"), 59.17, places=1)
        self.assertAlmostEqual(F._bookie_impl(self.ODDS, "Unentschieden"), 23.81, places=1)

    def test_fair_fallback_when_pinn_missing(self):
        od = {k: v for k, v in self.ODDS.items() if k != "pinn_hw_fair"}
        self.assertAlmostEqual(F._bookie_impl(od, "Heimsieg"), 59.17, places=1)

    def test_devig_over15_over35(self):
        self.assertAlmostEqual(F._bookie_impl(self.ODDS, "Over 1.5 Tore"), 73.74, places=1)
        self.assertAlmostEqual(F._bookie_impl(self.ODDS, "Over 3.5 Tore"), 28.66, places=1)

    def test_devig_btts_yes_no_sum_100(self):
        y = F._bookie_impl(self.ODDS, "Beide Teams treffen")
        n = F._bookie_impl(self.ODDS, "Beide Teams treffen: Nein")
        self.assertAlmostEqual(y, 48.57, places=1)
        self.assertAlmostEqual(y + n, 100.0, places=1)

    def test_missing_data_none(self):
        self.assertIsNone(F._bookie_impl({}, "Over 1.5 Tore"))
        self.assertIsNone(F._bookie_impl({"o15": 1.3}, "Over 1.5 Tore"))
        self.assertIsNone(F._bookie_impl(self.ODDS, "Unbekannter Markt"))


if __name__ == "__main__":
    unittest.main()
