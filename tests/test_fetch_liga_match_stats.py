#!/usr/bin/env python3
"""
test_fetch_liga_match_stats.py — Post-Match-xG-Transformer (26.06.2026, Lucas: Lernen aus Match-xG).
build_match_stats: echtes xG bevorzugt, xGsim-Fallback, Heim/Auswärts per Team-ID gemappt.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_match_stats as M  # noqa: E402


class TestBuildMatchStats(unittest.TestCase):
    def test_real_xg(self):
        extract = {40: {"xg": 1.8, "xgsim": 1.2}, 50: {"xg": 0.7, "xgsim": 0.9}}
        s = M.build_match_stats(extract, "40", "50")
        self.assertEqual((s["xgHome"], s["xgAway"], s["xgTotal"]), (1.8, 0.7, 2.5))
        self.assertEqual(s["xgSource"], "api")

    def test_sim_fallback(self):
        extract = {40: {"xg": None, "xgsim": 1.1}, 50: {"xg": None, "xgsim": 0.6}}
        s = M.build_match_stats(extract, "40", "50")
        self.assertEqual(s["xgSource"], "sim")
        self.assertEqual(s["xgTotal"], 1.7)

    def test_missing_team(self):
        self.assertIsNone(M.build_match_stats({40: {"xg": 1.0, "xgsim": 1.0}}, "40", "99"))

    def test_none_extract(self):
        self.assertIsNone(M.build_match_stats(None, "40", "50"))


if __name__ == "__main__":
    unittest.main()
