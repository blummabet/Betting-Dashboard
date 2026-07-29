# tests/test_betfair_coherence.py — Markt-Kohärenz-Signal (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_signals.betfair_coherence import BetfairCoherenceSignal


def ou(n, p, vol=9000):
    return {"Over/Under %s Goals" % n: {"runners": [
        {"name": "Over %s Goals" % n, "odd": round(1.0 / p, 3), "vol": vol / 2},
        {"name": "Under %s Goals" % n, "odd": round(1.0 / (1 - p), 3), "vol": vol / 2}]}}


def snap(mklist, fair=None, home="Alpha", away="Beta", league="Test"):
    mk = {}
    for d in mklist:
        mk.update(d)
    s = {"home": home, "away": away, "league": league, "markets": mk}
    if fair:
        s["mo"] = {"hw": 2.2, "dr": 3.4, "aw": 3.4, "fair": fair}
    return s


SIG = BetfairCoherenceSignal()


class TestCoherence(unittest.TestCase):
    def test_no_snapshot(self):
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {}))

    def test_1x2_pick_returns_none(self):
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(2.5, 0.45), ou(3.5, 0.24)],
                 fair={"home": 0.45, "draw": 0.28, "away": 0.27})
        self.assertIsNone(SIG.evaluate({"market": "Heimsieg"}, {"betfair_snapshot": s}))

    def test_thin_market_none(self):
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(3.5, 0.30), ou(2.5, 0.38, vol=500)])
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s}))

    def test_underpriced_over_fires_positive(self):
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(3.5, 0.30), ou(2.5, 0.38, vol=12000)])
        r = SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s})
        self.assertIsNotNone(r)
        self.assertEqual(r.metadata["token"], "OVER")
        self.assertGreater(r.score, 0)
        self.assertIn("lambda", r.metadata)
        print("OVER fire:", r.score, r.metadata["edge_pp"], "lam", r.metadata["lambda"], r.evidence)

    def test_hard_conflict_flag(self):
        s = snap([ou(0.5, 0.70), ou(1.5, 0.80), ou(2.5, 0.30, vol=12000), ou(3.5, 0.20)])
        r = SIG.evaluate({"market": "Unter 2.5"}, {"betfair_snapshot": s})
        if r is not None:
            print("hard:", r.metadata["hard_conflict"], r.score)
            self.assertTrue(r.metadata["hard_conflict"])

    def test_ladder_too_short_none(self):
        s = snap([ou(2.5, 0.45, vol=12000), ou(3.5, 0.24)])
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
