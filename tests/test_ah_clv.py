#!/usr/bin/env python3
"""
test_ah_clv.py — CLV für Asian-Handicap-Trades aus der eingefrorenen Closing-AH-Leiter
(23.06.2026, Lucas). Vorher 0/8 Coverage: compute_closing speicherte die AH-Leiter nie, und der
Resolver mappte nur AH −0.5. Jetzt: ganze Leiter im Closing + generische de-vig je Linie/Seite.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import resolve_wm_results as R   # noqa: E402

LADDER = {"-2.5": [8.0, 1.03], "-1.5": [3.82, 1.23],
          "0.0": [1.48, 2.77], "1.0": [1.04, 7.5], "1.5": [1.01, 8.5]}


class TestAhCloseFair(unittest.TestCase):
    def test_home_line_devig(self):
        # AH Heim -1.5 → Leiter[-1.5]=[3.82,1.23], fair_home = devig(3.82,1.23)
        fair = R._ah_close_fair(LADDER, "AH Heim -1.5")
        self.assertIsNotNone(fair)
        self.assertAlmostEqual(fair, R._devig_2way(3.82, 1.23), places=4)
        self.assertTrue(0 < fair < 1)

    def test_away_line_uses_mirror_key(self):
        # AH Auswärts -1.5 → Heim +1.5 → Leiter[1.5]=[1.01,8.5], fair_away = devig(8.5,1.01)
        fair = R._ah_close_fair(LADDER, "AH Auswärts -1.5")
        self.assertAlmostEqual(fair, R._devig_2way(8.5, 1.01), places=4)

    def test_line_not_in_ladder_returns_none(self):
        self.assertIsNone(R._ah_close_fair(LADDER, "AH Heim -4.5"))

    def test_no_ladder_returns_none(self):
        self.assertIsNone(R._ah_close_fair(None, "AH Heim -1.5"))

    def test_home_and_away_sum_below_one(self):
        # Heim(-1.5) und die Gegenseite an derselben Leiter-Linie sind komplementär (~1.0)
        fair_h = R._devig_2way(3.82, 1.23)
        fair_a = R._devig_2way(1.23, 3.82)
        self.assertAlmostEqual(fair_h + fair_a, 1.0, places=4)


class TestGetPinnCloseForAh(unittest.TestCase):
    def test_routes_ah_to_ladder(self):
        res = {"_pinn_close_ah_ladder": LADDER}
        val = R.get_pinn_close_for_market(res, "AH Heim -1.5")
        self.assertAlmostEqual(val, R._devig_2way(3.82, 1.23), places=4)

    def test_ah_without_ladder_none(self):
        self.assertIsNone(R.get_pinn_close_for_market({}, "AH Heim -1.5"))


if __name__ == "__main__":
    unittest.main()
