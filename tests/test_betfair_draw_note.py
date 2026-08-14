# tests/test_betfair_draw_note.py — In-Play-Remis-Nachlauf-Warnung im Trades-Push (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def draw(**kw):
    a = {"leadName": "The Draw", "market": "Match Odds", "leadOdd": 4.40,
         "live": {"time": 55, "goal_v1": 0, "goal_v2": 0}}
    a.update(kw)
    return a


class TestDrawInplayNote(unittest.TestCase):
    def test_inplay_draw_goalless_warns(self):
        s = BA._draw_inplay_note(draw())
        self.assertIn("In-Play-Remis-Nachlauf", s)
        self.assertIn("von allein wahrscheinlicher", s)   # 0:0-Zusatz
        self.assertIn("ROI", s)

    def test_inplay_draw_with_lead_warns_without_goalless_tail(self):
        s = BA._draw_inplay_note(draw(live={"time": 55, "goal_v1": 1, "goal_v2": 0}))
        self.assertIn("In-Play-Remis-Nachlauf", s)
        self.assertNotIn("von allein wahrscheinlicher", s)

    def test_collapsed_draw_below_22_stronger(self):
        s = BA._draw_inplay_note(draw(leadOdd=2.0))
        self.assertIn("schon kollabiert", s)

    def test_prematch_draw_no_note(self):
        self.assertEqual(BA._draw_inplay_note(draw(live={})), "")   # nicht in-play

    def test_non_draw_no_note(self):
        self.assertEqual(BA._draw_inplay_note(draw(leadName="Alpha")), "")

    def test_non_matchodds_no_note(self):
        self.assertEqual(BA._draw_inplay_note(draw(market="Over/Under 2.5")), "")

    def test_finished_no_note(self):
        self.assertEqual(BA._draw_inplay_note(draw(live={"time": 90, "finished": True,
                         "goal_v1": 0, "goal_v2": 0})), "")


if __name__ == "__main__":
    unittest.main()
