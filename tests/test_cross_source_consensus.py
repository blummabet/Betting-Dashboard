# tests/test_cross_source_consensus.py — Triple/Konsens (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cross_source_consensus import build_consensus


def ctx(poly=None, odds=None, bf_home=None, bf_away=None):
    c = {}
    if poly is not None: c["poly_snapshot"] = poly
    if odds is not None: c["odds_snapshot"] = odds
    if bf_home is not None or bf_away is not None:
        c["betfair_snapshot"] = {"mo": {"fair": {"home": bf_home, "away": bf_away}}}
    return c


class TestConsensus(unittest.TestCase):
    def test_konsens_three_sources_tight(self):
        pick = {"market": "Heimsieg", "softNow": 1.72}   # 1/1.72 ≈ 0.581
        c = build_consensus(pick, ctx(poly={"fair_hw": 0.58, "poly_hw": 0.60}, bf_home=0.585))
        self.assertIsNotNone(c)
        self.assertEqual(c["kind"], "konsens")
        self.assertGreaterEqual(c["n"], 3)
        self.assertLessEqual(c["spreadPP"], 6.0)

    def test_divergenz_outlier(self):
        # Pinnacle/Betfair/Soft ~0.58, Poly weit drunter (0.45) → Divergenz, Ausreißer poly
        pick = {"market": "Heimsieg", "softNow": 1.72}
        c = build_consensus(pick, ctx(poly={"fair_hw": 0.58, "poly_hw": 0.45}, bf_home=0.585))
        self.assertEqual(c["kind"], "divergenz")
        self.assertEqual(c["outlier"], "poly")
        self.assertGreaterEqual(c["outlierGapPP"], 8.0)

    def test_pinnacle_fallback_from_odds(self):
        # kein poly_snapshot → Pinnacle aus odds de-viggt (hw/dr/aw)
        pick = {"market": "Auswärtssieg", "softNow": 2.05}
        c = build_consensus(pick, ctx(odds={"hw": 3.5, "dr": 3.6, "aw": 2.0}, bf_away=0.49))
        self.assertIsNotNone(c)
        self.assertIn("pinnacle", c["sources"])
        self.assertIn("betfair", c["sources"])

    def test_needs_two_sources(self):
        self.assertIsNone(build_consensus({"market": "Heimsieg", "softNow": 1.7}, ctx()))

    def test_non_1x2_returns_none(self):
        self.assertIsNone(build_consensus({"market": "Über 2.5", "softNow": 1.9},
                                          ctx(poly={"fair_hw": 0.5}, bf_home=0.5)))
        self.assertIsNone(build_consensus({"market": "BTTS Ja"}, ctx(bf_home=0.5)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
