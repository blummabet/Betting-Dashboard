#!/usr/bin/env python3
"""test_liga_odds_round_guard.py — check_liga_odds_round_sane (Bug 26.06.2026 „Spieltag 1 dann 20").
Odds auf ferner Runde (Hin/Rück-Fehlmatch) → Guard schlägt an; nur nahe Runden → grün; WM → skip."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(profile, fixtures, odds):
    wm = {"_meta": {"profile": profile},
          "groups": {"ENG": {"fixtures": fixtures}}, "odds": odds}
    return W.IntegrityCtx(wm, {}, {}, {})


FX = [
    {"home": "1", "away": "2", "matchday": 1, "result": None},
    {"home": "3", "away": "4", "matchday": 1, "result": None},
    {"home": "2", "away": "1", "matchday": 31, "result": None},   # Rückspiel
]


class TestGuard(unittest.TestCase):
    def test_flags_far_round_odds(self):
        odds = {"1-2": {"hw": 1.8}, "2-1": {"hw": 1.9}}  # Runde 1 + fälschlich Runde 31
        res = W.check_liga_odds_round_sane(_ctx("liga_default", FX, odds))
        self.assertFalse(res["ok"])
        self.assertIn("2-1", res["failures"][0])

    def test_clean_near_round_passes(self):
        odds = {"1-2": {"hw": 1.8}, "3-4": {"hw": 2.0}}  # nur Runde 1
        res = W.check_liga_odds_round_sane(_ctx("liga_default", FX, odds))
        self.assertTrue(res["ok"])

    def test_wm_skipped(self):
        odds = {"1-2": {"hw": 1.8}, "2-1": {"hw": 1.9}}
        self.assertIsNone(W.check_liga_odds_round_sane(_ctx("wm2026", FX, odds)))


if __name__ == "__main__":
    unittest.main()
