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

    def test_fires_when_onesided(self):
        # 8000 ≥ 7000 UND 88% auf Alpha (≥85%)
        m = match(markets=self._ht_market(7000, 500, 500))
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["scenario"], "ht")
        self.assertAlmostEqual(a["total"], 8000)
        self.assertEqual(a["leadName"], "Alpha")
        self.assertGreaterEqual(a["leadShare"], 0.85)

    def test_balanced_market_none(self):
        # 8000 ≥ 7000, aber breit verteilt (max 50%) → kein Signal
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(4000, 2000, 2000))))

    def test_below_threshold_none(self):
        # einseitig (100%), aber nur 4000 < 7000
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(4000, 0, 0))))

    def test_no_ht_market_none(self):
        self.assertIsNone(BA.ht_alert(match(markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 9000}]))))


class TestFreshAlert(unittest.TestCase):
    def test_top_needs_20k_per_market(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 30000}, {"name": "Beta", "odd": 2, "vol": 10000}]))
        hist = {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 45000}}]}   # +25k auf 1X2
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["tier"], "top")
        self.assertEqual(a["market"], "Match Odds")
        self.assertAlmostEqual(a["inflow"], 25000)
        self.assertAlmostEqual(a["total"], 45000)     # Markt-Volumen, NICHT Spiel-Gesamt
        self.assertEqual(a["leadName"], "Alpha")

    def test_top_below_20k_none(self):
        m = match(mid=7, league="German Bundesliga", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 35000}}]}))  # +15k

    def test_biggest_inflow_market_wins(self):
        # 1X2 +5k, aber Ü/U 2.5 +12k → der groessere Zufluss-Markt gewinnt (Rest-Liga, Schwelle 10k)
        m = match(mid=8, league="Chinese League 2",
                  markets=mk("Over/Under 2.5 Goals", [{"name": "Over 2.5 Goals", "odd": 2, "vol": 22000}, {"name": "Under 2.5 Goals", "odd": 2, "vol": 3000}]))
        hist = {"8": [{"mkv": {"Match Odds": 40000, "Over/Under 2.5 Goals": 10000}},
                      {"mkv": {"Match Odds": 45000, "Over/Under 2.5 Goals": 22000}}]}
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["market"], "Over/Under 2.5 Goals")
        self.assertAlmostEqual(a["inflow"], 12000)

    def test_rest_below_10k_none(self):
        m = match(mid=8, league="Chinese League 2", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"8": [{"mkv": {"Match Odds": 5000}}, {"mkv": {"Match Odds": 13000}}]}))  # +8k

    def test_no_mkv_none(self):
        # ohne per-Markt-History (nur totalVol) kein Signal — irrefuehrende Gesamt-Zahl vermeiden
        self.assertIsNone(BA.fresh_alert(match(mid=9, league="Chinese League 2"),
                                         {"9": [{"totalVol": 5000}, {"totalVol": 30000}]}))

    def test_needs_two_points(self):
        self.assertIsNone(BA.fresh_alert(match(mid=8, league="Chinese League 2"), {"8": [{"mkv": {"Match Odds": 5000}}]}))


class TestDedup(unittest.TestCase):
    def test_first_time_sends(self):
        self.assertTrue(BA.should_send({}, "ht:1", 8000))

    def test_small_increase_suppressed(self):
        self.assertFalse(BA.should_send({"ht:1": 8000}, "ht:1", 10000))   # +25% < +50%

    def test_big_increase_resends(self):
        self.assertTrue(BA.should_send({"ht:1": 8000}, "ht:1", 12500))    # +56% ≥ +50%


class TestMessage(unittest.TestCase):
    def test_ht_message(self):
        m = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 2, "vol": 8000},
                                           {"name": "The Draw", "odd": 3, "vol": 500},
                                           {"name": "Beta", "odd": 4, "vol": 500}]))
        msg = BA.build_message(BA.ht_alert(m))
        self.assertIn("Halbzeit-Geld", msg)
        self.assertIn("HZ-1X2", msg)
        self.assertIn("auf Alpha", msg)   # dominanter Ausgang genannt
        self.assertIn("%", msg)

    def test_fresh_message(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 45000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 45000}}]})
        msg = BA.build_message(a)
        self.assertIn("Frisches Geld", msg)
        self.assertIn("Top-Liga", msg)
        self.assertIn("1X2", msg)          # Markt genannt
        self.assertIn("frisch", msg)
        self.assertIn("Alpha", msg)        # fuehrender Ausgang


class TestCollect(unittest.TestCase):
    def test_collects_both(self):
        m = match(mid=9, league="Chinese League 2", markets=mk("Half Time",
                  [{"name": "Alpha", "odd": 2, "vol": 8000}]))
        alerts = BA.collect_alerts({"matches": [m]}, {"9": [{"mkv": {"Half Time": 1000}}, {"mkv": {"Half Time": 20000}}]})
        kinds = sorted(a["scenario"] for a in alerts)
        self.assertEqual(kinds, ["fresh", "ht"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
