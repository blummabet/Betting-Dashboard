# tests/test_betfair_ou_fade.py — Under-Fade in der Betfair-Quotenrichtung (14.08.2026, Lucas).
# Ein LIVE-Under, das RAUS driftet (statt mit der Uhr kuerzer zu werden), obwohl der Ausgang noch lebt,
# wird gelayt -> im Trades-Push als Fade markiert; Public bleibt beim neutralen Zeit-Drift-Text.
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def alert(**kw):
    a = {"leadDir": "out", "leadPrev": 1.16, "leadOdd": 1.34,
         "leadLabel": "Under 1.5 Goals", "live": {"time": 33, "goal_v1": 0, "goal_v2": 0}}
    a.update(kw)
    return a


class TestOuUnderAlive(unittest.TestCase):
    def test_under_alive_below_line(self):
        self.assertIs(BA._ou_under_alive(alert()), True)          # 0 Tore < 1.5 -> lebt

    def test_under_dead_line_broken(self):
        self.assertIs(BA._ou_under_alive(alert(live={"time": 40, "goal_v1": 1, "goal_v2": 1})), False)  # 2 >= 1.5

    def test_over_is_not_under(self):
        self.assertIs(BA._ou_under_alive(alert(leadLabel="Over 3.5 Goals")), False)

    def test_team_market_not_under(self):
        self.assertIs(BA._ou_under_alive(alert(leadLabel="Alpha", leadName="Alpha")), False)

    def test_no_score_unknown(self):
        self.assertIsNone(BA._ou_under_alive(alert(live={"time": 33})))   # kein Score -> None

    def test_line_from_35(self):
        # Under 3.5 mit 3 Toren: 3 < 3.5 -> lebt noch
        self.assertIs(BA._ou_under_alive(alert(leadLabel="Under 3.5 Goals",
                      live={"time": 60, "goal_v1": 2, "goal_v2": 1})), True)
        # Under 3.5 mit 4 Toren: 4 >= 3.5 -> gerissen
        self.assertIs(BA._ou_under_alive(alert(leadLabel="Under 3.5 Goals",
                      live={"time": 60, "goal_v1": 2, "goal_v2": 2})), False)


class TestDirLineFade(unittest.TestCase):
    def test_trades_under_drift_alive_is_fade(self):
        s = BA._dir_line(alert(), ou_fade=True)
        self.assertIn("Under wird gelayt", s)
        self.assertIn("will das Tor", s)

    def test_public_under_drift_stays_neutral(self):
        s = BA._dir_line(alert(), ou_fade=False)   # Public unveraendert
        self.assertIn("im Spiel normal", s)
        self.assertNotIn("gelayt", s)

    def test_trades_over_drift_stays_neutral(self):
        s = BA._dir_line(alert(leadLabel="Over 3.5 Goals"), ou_fade=True)
        self.assertIn("im Spiel normal", s)
        self.assertNotIn("gelayt", s)

    def test_trades_under_drift_line_broken_neutral(self):
        s = BA._dir_line(alert(live={"time": 40, "goal_v1": 1, "goal_v2": 1}), ou_fade=True)
        self.assertIn("im Spiel normal", s)
        self.assertNotIn("gelayt", s)

    def test_under_shortening_is_confirmed(self):
        s = BA._dir_line(alert(leadDir="in", leadPrev=1.34, leadOdd=1.16), ou_fade=True)
        self.assertIn("Quote bestätigt", s)

    def test_prematch_under_drift_no_backing(self):
        s = BA._dir_line(alert(live={}), ou_fade=True)   # nicht live -> Vor-Anpfiff-Zweig
        self.assertIn("kein Back-Rückhalt", s)


if __name__ == "__main__":
    unittest.main()
