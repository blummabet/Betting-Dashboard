"""
test_steam_clv.py — CLV-Tracking für Steam-Picks (Lucas, 14.06.2026).
clvPP = (Pinnacle-Closing-Prob der Pick-Seite − 1/Einstiegsquote) · 100.
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import resolve_steam_clv as scl  # noqa: E402


class TestSteamCLVMath(unittest.TestCase):
    def test_positive_when_line_moved_our_way(self):
        # Einstieg @2.00 (50%), Closing-Prob 56% → Linie weiter in Pick-Richtung → +6pp
        self.assertAlmostEqual(scl.steam_clv_pp(0.56, 2.00), 6.0, places=1)

    def test_negative_when_line_moved_against(self):
        # Einstieg @1.80 (55.6%), Closing-Prob 50% → gegen uns → negativ
        self.assertLess(scl.steam_clv_pp(0.50, 1.80), 0)

    def test_none_on_missing_inputs(self):
        self.assertIsNone(scl.steam_clv_pp(None, 2.0))
        self.assertIsNone(scl.steam_clv_pp(0.5, None))
        self.assertIsNone(scl.steam_clv_pp(0.5, 1.0))


class TestSteamCLVResolve(unittest.TestCase):
    def _wm(self, with_result):
        # Fiktive Team-Codes (TS1/TS2) — kein echter Key, sonst überschreibt die reale
        # wm_closing_lines.json die Inline-Closing-Daten (MEX-KOR existiert dort jetzt).
        fx = {"matchday": 2, "home": "TS1", "away": "TS2", "date": "2026-06-20"}
        if with_result:
            fx["result"] = {"home_score": 2, "away_score": 0, "status": "FT"}
        return {
            "groups": {"A": {"fixtures": [fx]}},
            "odds": {"TS1-TS2": {"hw": 1.80, "dr": 3.6, "aw": 4.5,
                                 "odds_closing": {"hw": 1.65, "dr": 3.8, "aw": 5.2}}},
            "picks": {"A-2-TS1-TS2": [
                {"market": "Heimsieg", "verdict": "BET", "source": "steam",
                 "odds": 1.85, "entryOdd": 1.85, "steamMovePP": 6.0}]},
        }

    def test_clv_set_on_resolved_steam_pick(self):
        wm = self._wm(with_result=True)
        n = scl.resolve(wm)
        self.assertEqual(n, 1)
        p = wm["picks"]["A-2-TS1-TS2"][0]
        self.assertTrue(p.get("clvResolved"))
        self.assertIsInstance(p.get("clvPP"), float)
        # Closing hw 1.65 (~de-vigged Prob > 1/1.85) → Linie lief in Pick-Richtung → CLV > 0
        self.assertGreater(p["clvPP"], 0)

    def test_no_clv_before_result(self):
        wm = self._wm(with_result=False)
        self.assertEqual(scl.resolve(wm), 0)
        self.assertNotIn("clvPP", [k for k in wm["picks"]["A-2-TS1-TS2"][0] if k == "clvPP"
                                   and wm["picks"]["A-2-TS1-TS2"][0].get("clvResolved")])

    def test_non_steam_pick_ignored(self):
        wm = self._wm(with_result=True)
        wm["picks"]["A-2-TS1-TS2"][0]["source"] = "alt"
        self.assertEqual(scl.resolve(wm), 0)


if __name__ == "__main__":
    unittest.main()
