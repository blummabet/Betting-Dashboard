#!/usr/bin/env python3
"""test_clv_card_coverage.py — check_clv_card_coverage (28.06.2026, CLV-Nordstern)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(picks):
    return W.IntegrityCtx({"_meta": {"profile": "wm2026"}, "groups": {}, "picks": picks}, {}, {}, {})


def _steam(result="WIN", clv=None):
    p = {"source": "steam", "result": result, "market": "Heimsieg"}
    if clv is not None:
        p["clvPP"] = clv
        p["clvResolved"] = True
    return p


class TestGuard(unittest.TestCase):
    def test_below_min_n_is_ok(self):
        # 5 aufgelöste, 0 mit Closing → trotzdem grün (zu wenig Daten zum Urteilen)
        picks = {f"A-1-x{i}-y{i}": [_steam(clv=None)] for i in range(5)}
        self.assertTrue(W.check_clv_card_coverage(_ctx(picks))["ok"])

    def test_low_coverage_flags(self):
        # 12 aufgelöst, nur 3 mit Closing (25%) → Flag
        picks = {}
        for i in range(3):
            picks[f"A-1-a{i}-b{i}"] = [_steam(clv=2.0)]
        for i in range(9):
            picks[f"A-1-c{i}-d{i}"] = [_steam(clv=None)]
        res = W.check_clv_card_coverage(_ctx(picks))
        self.assertFalse(res["ok"])
        self.assertIn("3/12", res["failures"][0])

    def test_good_coverage_ok(self):
        # 10 aufgelöst, 9 mit Closing (90%) → grün
        picks = {f"A-1-a{i}-b{i}": [_steam(clv=1.0)] for i in range(9)}
        picks["A-1-z-z"] = [_steam(clv=None)]
        self.assertTrue(W.check_clv_card_coverage(_ctx(picks))["ok"])


if __name__ == "__main__":
    unittest.main()
