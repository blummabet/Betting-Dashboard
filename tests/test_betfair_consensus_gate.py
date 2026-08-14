# tests/test_betfair_consensus_gate.py — Zweitmeinung nur bei 1X2-Geld + pre-match (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


G = {"matchId": "1", "verdict": "konsens", "pinnOdd": 1.31, "softOdd": 1.25, "softN": 35,
     "poly": {"odd": 2.35, "vol": 69000}, "moneyName": "Rosenborg", "live": False}


def cidx(live=False):
    g = dict(G); g["live"] = live
    return {"1": g}


def alert(market="Match Odds", live=None):
    a = {"matchId": "1", "market": market}
    if live is not None:
        a["live"] = live
    return a


class TestConsensusGate(unittest.TestCase):
    def test_prematch_1x2_shows(self):
        s = BA._consensus_block(alert("Match Odds"), cidx(live=False))
        self.assertIn("Zweitmeinung", s)
        self.assertIn("Pinnacle", s)

    def test_over_under_money_suppressed(self):
        self.assertEqual(BA._consensus_block(alert("Over/Under 2.5"), cidx(live=False)), "")

    def test_btts_money_suppressed(self):
        self.assertEqual(BA._consensus_block(alert("Both Teams To Score"), cidx(live=False)), "")

    def test_live_1x2_suppressed_via_g(self):
        self.assertEqual(BA._consensus_block(alert("Match Odds"), cidx(live=True)), "")

    def test_live_1x2_suppressed_via_alert(self):
        s = BA._consensus_block(alert("Match Odds", live={"time": 60}), cidx(live=False))
        self.assertEqual(s, "")

    def test_no_anchor_empty(self):
        c = {"1": {"matchId": "1", "verdict": "no_anchor"}}
        self.assertEqual(BA._consensus_block(alert("Match Odds"), c), "")


if __name__ == "__main__":
    unittest.main()
