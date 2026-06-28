#!/usr/bin/env python3
"""test_pick_staking.py — Edge-Staking (fraktionales Kelly, 28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import pick_staking as PS  # noqa: E402

CFG = {"bankroll": 1000.0, "kelly_fraction": 0.25, "edge_per_conviction_pt": 0.006,
       "conviction_neutral": 5.0, "abwaegen_factor": 0.6, "min_stake": 2.0, "max_stake": 25.0}


def _p(conv, odds, verdict="BET"):
    return {"convictionScore": conv, "odds": odds, "verdict": verdict}


class TestStake(unittest.TestCase):
    def test_conviction_and_odds_scaling(self):
        self.assertEqual(PS.compute_stake(_p(8, 2.0), CFG), 4.5)    # edge .018 / b 1
        self.assertEqual(PS.compute_stake(_p(10, 1.5), CFG), 15.0)  # edge .03 / b .5
        self.assertEqual(PS.compute_stake(_p(10, 4.0), CFG), 2.5)   # Longshot → Kelly klein

    def test_neutral_or_below_floors_to_min(self):
        self.assertEqual(PS.compute_stake(_p(5, 2.0), CFG), 2.0)
        self.assertEqual(PS.compute_stake(_p(3, 2.0), CFG), 2.0)

    def test_abwaegen_more_cautious(self):
        self.assertEqual(PS.compute_stake(_p(8, 2.0, "ABWÄGEN"), CFG), 2.7)  # 4.5 × 0.6

    def test_capped_at_max(self):
        self.assertEqual(PS.compute_stake(_p(10, 1.2), CFG), 25.0)  # roh 37.5 → Cap

    def test_no_odds_returns_none(self):
        self.assertIsNone(PS.compute_stake({"convictionScore": 8, "verdict": "BET"}, CFG))
        self.assertIsNone(PS.compute_stake(_p(8, 1.0), CFG))

    def test_apply_sets_stake_skips_excluded_and_skip(self):
        wm = {"picks": {
            "A-1-a-b": [_p(8, 2.0), {"convictionScore": 9, "odds": 2.0, "verdict": "SKIP"}],
            "A-1-c-d": [{"convictionScore": 9, "odds": 2.0, "verdict": "BET", "trackingExcluded": True}],
        }}
        n = PS.apply(wm, CFG)
        self.assertEqual(n, 1)
        plist = wm["picks"]["A-1-a-b"]
        self.assertIn("stake", plist[0])
        self.assertNotIn("stake", plist[1])              # SKIP
        self.assertNotIn("stake", wm["picks"]["A-1-c-d"][0])  # excluded

    def test_apply_skips_resolved_picks(self):
        # Immutability: aufgelöste Picks werden NICHT (um)gestaked
        wm = {"picks": {"A-1-a-b": [{"convictionScore": 9, "odds": 2.0, "verdict": "BET", "result": "WIN"}]}}
        self.assertEqual(PS.apply(wm, CFG), 0)
        self.assertNotIn("stake", wm["picks"]["A-1-a-b"][0])


if __name__ == "__main__":
    unittest.main()
