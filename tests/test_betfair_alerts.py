# tests/test_betfair_alerts.py — Betfair-Telegram-Alerts (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def mk(name, runners):
    return {name: {"runners": runners}}


def match(mid=1, home="Alpha", away="Beta", league="Test", country="International", markets=None):
    return {"matchId": mid, "home": home, "away": away, "league": league,
            "country": country, "markets": markets or {}}


class TestTier(unittest.TestCase):
    def test_top5_and_mls_are_top(self):
        self.assertEqual(BA.tier_of({"league": "German Bundesliga"}), "top")
        self.assertEqual(BA.tier_of({"league": "Major League Soccer"}), "top")

    def test_uefa_and_others_are_rest(self):
        self.assertEqual(BA.tier_of({"league": "UEFA Champions League Qualifiers"}), "rest")
        self.assertEqual(BA.tier_of({"league": "Chinese League 2"}), "rest")

    def test_summer_series_not_top(self):
        self.assertEqual(BA.tier_of({"league": "English Premier League Summer Series"}), "rest")


class TestHtAlert(unittest.TestCase):
    def _ht_market(self, hv, dv, av):
        return mk("Half Time", [
            {"name": "Alpha", "odd": 2.1, "vol": hv},
            {"name": "The Draw", "odd": 2.2, "vol": dv},
            {"name": "Beta", "odd": 3.4, "vol": av}])

    def test_fires_at_threshold(self):
        m = match(markets=self._ht_market(4000, 2000, 2000))  # 8000 ≥ 7000
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["scenario"], "ht")
        self.assertAlmostEqual(a["total"], 8000)
        self.assertAlmostEqual(a["hs"], 0.5)

    def test_below_threshold_none(self):
        m = match(markets=self._ht_market(2000, 1000, 1000))  # 4000 < 7000
        self.assertIsNone(BA.ht_alert(m))

    def test_no_ht_market_none(self):
        self.assertIsNone(BA.ht_alert(match(markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 9000}]))))


class TestFreshAlert(unittest.TestCase):
    def test_top_needs_20k(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 30000}, {"name": "Beta", "odd": 2, "vol": 10000}]))
        hist = {"7": [{"totalVol": 20000}, {"totalVol": 45000}]}   # +25k
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["tier"], "top")
        self.assertAlmostEqual(a["inflow"], 25000)
        self.assertIn("1X2", a["lead"])

    def test_top_below_20k_none(self):
        m = match(mid=7, league="German Bundesliga", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"7": [{"totalVol": 20000}, {"totalVol": 35000}]}))  # +15k < 20k

    def test_rest_needs_10k(self):
        m = match(mid=8, league="Chinese League 2", markets={})
        self.assertIsNotNone(BA.fresh_alert(m, {"8": [{"totalVol": 5000}, {"totalVol": 16000}]}))   # +11k ≥ 10k
        self.assertIsNone(BA.fresh_alert(m, {"8": [{"totalVol": 5000}, {"totalVol": 13000}]}))       # +8k < 10k

    def test_needs_two_points(self):
        self.assertIsNone(BA.fresh_alert(match(mid=8, league="Chinese League 2"), {"8": [{"totalVol": 5000}]}))


class TestDedup(unittest.TestCase):
    def test_first_time_sends(self):
        self.assertTrue(BA.should_send({}, "ht:1", 8000))

    def test_small_increase_suppressed(self):
        self.assertFalse(BA.should_send({"ht:1": 8000}, "ht:1", 10000))   # +25% < +50%

    def test_big_increase_resends(self):
        self.assertTrue(BA.should_send({"ht:1": 8000}, "ht:1", 12500))    # +56% ≥ +50%


class TestMessage(unittest.TestCase):
    def test_ht_message(self):
        m = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 2, "vol": 5000},
                                           {"name": "The Draw", "odd": 3, "vol": 1500},
                                           {"name": "Beta", "odd": 4, "vol": 1500}]))
        msg = BA.build_message(BA.ht_alert(m))
        self.assertIn("Halbzeit-Geld", msg)
        self.assertIn("HZ-1X2", msg)
        self.assertIn("Alpha", msg)

    def test_fresh_message(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 30000}]))
        a = BA.fresh_alert(m, {"7": [{"totalVol": 10000}, {"totalVol": 45000}]})
        msg = BA.build_message(a)
        self.assertIn("Frisches Geld", msg)
        self.assertIn("Top-Liga", msg)
        self.assertIn("seit letztem Update", msg)


class TestCollect(unittest.TestCase):
    def test_collects_both(self):
        m = match(mid=9, league="Chinese League 2", markets=mk("Half Time",
                  [{"name": "Alpha", "odd": 2, "vol": 8000}]))
        alerts = BA.collect_alerts({"matches": [m]}, {"9": [{"totalVol": 1000}, {"totalVol": 20000}]})
        kinds = sorted(a["scenario"] for a in alerts)
        self.assertEqual(kinds, ["fresh", "ht"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
