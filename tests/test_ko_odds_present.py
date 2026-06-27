#!/usr/bin/env python3
"""test_ko_odds_present.py — check_ko_odds_present (Bug 27.06.2026 „R32 ohne Pick"): KO-Paarung mit
Odds-History aber ohne top-level Odds (= als Phantom geprunt) wird geflaggt; mit Odds → grün."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(ko, odds, history):
    wm = {"_meta": {"profile": "wm2026"}, "groups": {}, "odds": odds, "koFixtures": ko}
    return W.IntegrityCtx(wm, {}, {}, {}, history=history)


KO = [{"round": "R32", "home": "BRA", "away": "JPN", "bothResolved": True, "result": None}]


class TestGuard(unittest.TestCase):
    def test_flags_pruned_ko_odds(self):
        # History da (2 Snaps), aber keine top-level Odds → geprunt
        res = W.check_ko_odds_present(_ctx(KO, {}, {"BRA-JPN": [{"hw": 1.7}, {"hw": 1.6}]}))
        self.assertFalse(res["ok"])
        self.assertIn("BRA-JPN", res["failures"][0])

    def test_ok_when_odds_present(self):
        res = W.check_ko_odds_present(_ctx(KO, {"BRA-JPN": {"hw": 1.6}},
                                          {"BRA-JPN": [{"hw": 1.7}, {"hw": 1.6}]}))
        self.assertTrue(res["ok"])

    def test_skip_unresolved(self):
        ko = [{"round": "R32", "home": None, "away": None, "bothResolved": False}]
        res = W.check_ko_odds_present(_ctx(ko, {}, {}))
        self.assertTrue(res["ok"])


if __name__ == "__main__":
    unittest.main()
