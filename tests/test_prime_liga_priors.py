#!/usr/bin/env python3
"""test_prime_liga_priors.py — Backtest-als-Prior (26.06.2026). build_priors: hitRate → gedeckelte
Pseudo-Obs; zu wenig Calls → kein Prior."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import prime_liga_priors as P  # noqa: E402


class TestBuildPriors(unittest.TestCase):
    def test_capped_pseudo_obs(self):
        rep = {"perSignal": {"form_trend": {"hitRate": 0.60, "calls": 4000}}}
        out = P.build_priors(rep, strength=25)
        self.assertEqual(out["form_trend"]["nPrior"], 25)
        self.assertEqual(out["form_trend"]["winsPrior"], 15.0)  # 0.60 * 25

    def test_calls_below_cap(self):
        rep = {"perSignal": {"x": {"hitRate": 0.5, "calls": 60}}}
        out = P.build_priors(rep, strength=25)
        self.assertEqual(out["x"]["nPrior"], 25)  # min(25, 60)

    def test_too_few_calls_skipped(self):
        rep = {"perSignal": {"x": {"hitRate": 0.7, "calls": 10}}}  # < MIN_CALLS
        self.assertEqual(P.build_priors(rep), {})

    def test_missing_hitrate_skipped(self):
        rep = {"perSignal": {"x": {"hitRate": None, "calls": 999}}}
        self.assertEqual(P.build_priors(rep), {})


if __name__ == "__main__":
    unittest.main()
