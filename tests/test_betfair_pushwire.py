# tests/test_betfair_pushwire.py — Under-Fade + Remis-Note haengen am RICHTIGEN Builder (14.08.2026,
# Lucas): Frisch-Pushes rendern ueber build_public_message; nur trades=True zeigt die Warnungen.
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def fresh(**kw):
    a = {"scenario": "fresh", "flag": "🇵🇹", "home": "A", "away": "B", "league": "Test",
         "market": "Match Odds", "leadName": "The Draw", "leadShare": 0.9,
         "total": 50000.0, "inflow": 42900.0, "leadDir": "in", "leadPrev": 5.10, "leadOdd": 4.40,
         "live": {"time": 60, "goal_v1": 0, "goal_v2": 0}}
    a.update(kw)
    return a


class TestPushWiring(unittest.TestCase):
    def test_trades_fresh_draw_shows_note(self):
        s = BA.build_public_message(fresh(), trades=True)
        self.assertIn("In-Play-Remis-Nachlauf", s)

    def test_public_fresh_draw_no_note(self):
        s = BA.build_public_message(fresh(), trades=False)   # Public unveraendert
        self.assertNotIn("In-Play-Remis-Nachlauf", s)

    def test_trades_fresh_under_drift_is_fade(self):
        a = fresh(market="Over/Under 3.5", leadName="Under 3.5 Goals",
                  leadDir="out", leadPrev=1.16, leadOdd=1.34,
                  live={"time": 40, "goal_v1": 0, "goal_v2": 0})
        s = BA.build_public_message(a, trades=True)
        self.assertIn("Under wird gelayt", s)

    def test_public_fresh_under_drift_neutral(self):
        a = fresh(market="Over/Under 3.5", leadName="Under 3.5 Goals",
                  leadDir="out", leadPrev=1.16, leadOdd=1.34,
                  live={"time": 40, "goal_v1": 0, "goal_v2": 0})
        s = BA.build_public_message(a, trades=False)
        self.assertNotIn("gelayt", s)
        self.assertIn("im Spiel normal", s)

    def test_default_is_public(self):
        # ohne trades-Arg = Public-Verhalten (kein Note)
        self.assertNotIn("In-Play-Remis-Nachlauf", BA.build_public_message(fresh()))


if __name__ == "__main__":
    unittest.main()
