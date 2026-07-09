#!/usr/bin/env python3
"""
test_ah_btts_resolution.py — AH/BTTS robust über ALLE Eventualitäten (16.06.2026).

Zwei Bugs der gleichen Klasse ('AH Heim' enthält Substring 'heim' → fälschlich als
1X2-Heimsieg behandelt):
  1. monitor_open_positions: AH-Position gegen 1X2-fair (0.66) statt AH-fair (0.18)
     bewertet → Phantom-CLV +50pp / Drift +46pp im Health-Alert.
  2. resolve_wm_results: AH-Linien + em-dash-BTTS nicht im exakten Dict → VOID statt
     WIN/LOSS (kein P&L, kein Lernen).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import resolve_wm_results as R
import monitor_open_positions as M


def _res(hs, as_):
    return {"status": "FT", "home_score": hs, "away_score": as_,
            "winner": "H" if hs > as_ else ("A" if as_ > hs else "draw"),
            "_home_id": "H", "_away_id": "A"}


class TestAhBttsSettlement(unittest.TestCase):
    def dr(self, market, hs, as_):
        return R.determine_result({"market": market}, _res(hs, as_))

    def test_ah_home_minus_2_5(self):
        self.assertEqual(self.dr("AH Heim -2.5", 3, 0), "WIN")    # 3+ Tore Sieg
        self.assertEqual(self.dr("AH Heim -2.5", 2, 0), "LOSS")   # nur 2 Tore
        self.assertEqual(self.dr("AH Heim -2.5", 2, 1), "LOSS")

    def test_ah_home_minus_1_5(self):
        self.assertEqual(self.dr("AH Heim -1.5", 2, 0), "WIN")
        self.assertEqual(self.dr("AH Heim -1.5", 1, 0), "LOSS")

    def test_ah_away_plus_0_5(self):
        self.assertEqual(self.dr("AH Auswärts +0.5", 1, 1), "WIN")   # Remis reicht
        self.assertEqual(self.dr("AH Auswärts +0.5", 0, 1), "WIN")   # Auswärts gewinnt
        self.assertEqual(self.dr("AH Auswärts +0.5", 1, 0), "LOSS")  # Auswärts verliert

    def test_ah_integer_push(self):
        self.assertEqual(self.dr("AH Heim -1", 1, 0), "VOID")   # exakt 1 Tor = Push
        self.assertEqual(self.dr("AH Heim -1", 2, 0), "WIN")

    def test_ah_unicode_minus(self):
        self.assertEqual(self.dr("AH Heim −2.5", 3, 0), "WIN")  # − statt -

    def test_btts_emdash_variants(self):
        self.assertEqual(self.dr("Beide Teams treffen — Ja", 1, 1), "WIN")
        self.assertEqual(self.dr("Beide Teams treffen — Ja", 1, 0), "LOSS")
        self.assertEqual(self.dr("Beide Teams treffen — Nein", 1, 0), "WIN")
        self.assertEqual(self.dr("Beide Teams treffen — Nein", 2, 2), "LOSS")

    def test_moneyline_unchanged(self):
        self.assertEqual(self.dr("Heimsieg", 1, 0), "WIN")
        self.assertEqual(self.dr("Over 2.5 Tore", 2, 1), "WIN")
        self.assertEqual(self.dr("Under 2.5 Tore", 1, 1), "WIN")

    def test_quarter_line_half_stake_pnl(self):
        """AH-Viertel-Linien (09.07.2026) sind Split-Wetten → die P&L muss den halben
        Einsatz buchen (resultStakeFactor 0.5), nicht den vollen. Der Card-Resolver
        (_ah_result) und der Placed-Bet-Grader (determine_result/compute_pnl) müssen
        übereinstimmen — sonst still über-/unterbuchte Beträge auf .25/.75/1.25-Linien."""
        # AH Heim −1.25, Heimsieg mit genau 1 Tor → Half-Loss (−1.0 Push, −1.5 Loss)
        bet = {"market": "AH Heim −1.25", "stake": 5.0, "polyPrice": 0.5}
        r = R.determine_result(bet, _res(1, 0))
        self.assertEqual(r, "LOSS")
        self.assertEqual(bet.get("resultStakeFactor"), 0.5)
        self.assertAlmostEqual(R.compute_pnl(bet, r), -2.5)   # halber Stake, nicht −5
        # AH Auswärts +0.25, Remis → Half-Win (0 Push, +0.5 Win)
        bet2 = {"market": "AH Auswärts +0.25", "stake": 5.0, "polyPrice": 0.5}
        r2 = R.determine_result(bet2, _res(0, 0))
        self.assertEqual(r2, "WIN")
        self.assertEqual(bet2.get("resultStakeFactor"), 0.5)
        self.assertAlmostEqual(R.compute_pnl(bet2, r2), 2.5)  # (2.0−1)·(5·0.5)
        # Ganze/halbe Linien unberührt: voller Stake
        bet3 = {"market": "AH Heim −1.5", "stake": 5.0, "polyPrice": 0.5}
        r3 = R.determine_result(bet3, _res(2, 0))
        self.assertIsNone(bet3.get("resultStakeFactor"))
        self.assertAlmostEqual(R.compute_pnl(bet3, r3), 5.0)


class TestMonitorMarketResolve(unittest.TestCase):
    """AH/BTTS-Positionen über den Token bewerten, NICHT über 1X2-fair."""

    def _fx(self):
        return {
            "key": "URU-CPV", "fair_hw": 0.655, "edge_hw": -1.0, "poly_hw": 0.665,
            "ah_edges": [
                {"side": "home", "line": -2.5, "poly": 0.155, "fair": 0.1955,
                 "edge": 4.1, "tokens": ["AHTOK_25", "AHNO_25"]},
                {"side": "home", "line": -1.5, "poly": 0.355, "fair": 0.3824,
                 "edge": 2.7, "tokens": ["AHTOK_15", "AHNO_15"]},
            ],
            "poly_btts": 0.46, "fair_btts": 0.50, "edge_btts": 4.0,
            "poly_btts_no": 0.54, "fair_btts_no": 0.50, "edge_btts_no": -4.0,
            "poly_btts_tokens": ["BTTSYES", "BTTSNO"],
        }

    def test_ah_uses_ah_fair_not_moneyline(self):
        bet = {"market": "AH Heim -2.5", "tokenId": "AHTOK_25"}
        edge, poly, fair = M.resolve_current_market(bet, self._fx())
        self.assertEqual(fair, 0.1955)   # AH-fair, NICHT 0.655 (Moneyline)
        self.assertEqual(edge, 4.1)

    def test_ah_fallback_by_side_line(self):
        # ohne passenden Token → Seite+Linie aus Label
        bet = {"market": "AH Heim -1.5", "tokenId": "GIBTSNICHT"}
        edge, poly, fair = M.resolve_current_market(bet, self._fx())
        self.assertEqual(fair, 0.3824)

    def test_btts_no_uses_no_fair(self):
        bet = {"market": "Beide Teams treffen — Nein", "tokenId": "BTTSNO"}
        edge, poly, fair = M.resolve_current_market(bet, self._fx())
        self.assertEqual(fair, 0.50)
        self.assertEqual(edge, -4.0)

    def test_moneyline_still_works(self):
        bet = {"market": "Heimsieg", "marketKey": "hw"}
        edge, poly, fair = M.resolve_current_market(bet, self._fx())
        self.assertEqual(fair, 0.655)

    def test_no_phantom_clv_for_ah(self):
        # Der reportete Bug: AH-Position darf NICHT die 1X2-fair (0.655) ziehen
        bet = {"market": "AH Heim -2.5", "tokenId": "AHTOK_25",
               "pinnFair": 0.1955, "edgePP": 4.1, "polyPrice": 0.155}
        h = M.compute_health(bet, self._fx())
        # CLV = current_fair(0.1955) - entry_poly(0.155) = ~+4pp, NICHT +50pp
        self.assertLess(h["score"], 101)
        # kein „Edge NEGATIV" mehr (das war die 1X2-Verwechslung)
        comp = " ".join(str(c) for c in h.get("components", []))
        self.assertNotIn("+46", comp)


if __name__ == "__main__":
    unittest.main()
