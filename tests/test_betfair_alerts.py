# tests/test_betfair_alerts.py — Betfair-Telegram-Alerts (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


def mk(name, runners):
    return {name: {"runners": runners}}


def match(mid=1, home="Alpha", away="Beta", league="Test", country="DE", markets=None):
    # Default: Rest-Tier (league „Test", Land DE) → HZ-Schwelle 5000, frisches Geld 20000.
    return {"matchId": mid, "home": home, "away": away, "league": league,
            "country": country, "markets": markets or {}}


class TestTier(unittest.TestCase):
    def test_top5_and_mls_are_top(self):
        self.assertEqual(BA.tier_of({"league": "German Bundesliga"}), "top")
        self.assertEqual(BA.tier_of({"league": "Major League Soccer"}), "top")

    def test_international_is_top(self):
        # Lucas 30.07.2026: internationale Bewerbe (UEFA / Länderspiele) verhalten sich wie Top.
        self.assertEqual(BA.tier_of({"league": "UEFA Champions League Qualifiers"}), "top")
        self.assertEqual(BA.tier_of({"league": "Friendly", "country": "International"}), "top")

    def test_others_are_rest(self):
        self.assertEqual(BA.tier_of({"league": "Chinese League 2", "country": "CN"}), "rest")

    def test_summer_series_not_top(self):
        self.assertEqual(BA.tier_of({"league": "English Premier League Summer Series"}), "rest")


class TestHtAlert(unittest.TestCase):
    def _ht_market(self, hv, dv, av, name="Half Time"):
        return mk(name, [
            {"name": "Alpha", "odd": 2.1, "vol": hv},
            {"name": "The Draw", "odd": 2.2, "vol": dv},
            {"name": "Beta", "odd": 3.4, "vol": av}])

    def test_fires_when_onesided(self):
        # Rest-Tier: 6000 ≥ 5000 UND ~83–100% auf Alpha (≥85% mit 5500/6000)
        m = match(markets=self._ht_market(5500, 250, 250))
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["scenario"], "ht")
        self.assertAlmostEqual(a["total"], 6000)
        self.assertEqual(a["leadName"], "Alpha")
        self.assertGreaterEqual(a["leadShare"], 0.85)

    def test_balanced_market_none(self):
        # 6000 ≥ 5000, aber breit verteilt (max 50%) → kein Signal
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(3000, 1500, 1500))))

    def test_below_threshold_none(self):
        # einseitig (100%), aber nur 4000 < 5000 (Rest)
        self.assertIsNone(BA.ht_alert(match(markets=self._ht_market(4000, 0, 0))))

    def test_top_tier_needs_10k(self):
        # Top-Liga: 8000 < 10000 → nichts; 11000 ≥ 10000 → feuert
        self.assertIsNone(BA.ht_alert(match(league="German Bundesliga", markets=self._ht_market(8000, 0, 0))))
        self.assertIsNotNone(BA.ht_alert(match(league="German Bundesliga", markets=self._ht_market(11000, 0, 0))))

    def test_over15_first_half_counts(self):
        # „egal ob over 1,5 oder 12x HT": Über/Unter 1,5 erste HZ zählt genauso.
        m = match(markets=mk("First Half Goals 1.5", [
            {"name": "Over 1.5 Goals", "odd": 1.9, "vol": 5500},
            {"name": "Under 1.5 Goals", "odd": 2.0, "vol": 300}]))
        a = BA.ht_alert(m)
        self.assertIsNotNone(a)
        self.assertEqual(a["market"], "First Half Goals 1.5")
        self.assertFalse(a["isX2"])
        self.assertEqual(a["mktLabel"], "HZ Ü/U 1.5")

    def test_no_ht_market_none(self):
        self.assertIsNone(BA.ht_alert(match(markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 9000}]))))


class TestFreshAlert(unittest.TestCase):
    def test_top_needs_30k_per_market(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 2, "vol": 40000}, {"name": "Beta", "odd": 2, "vol": 12000}]))
        hist = {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 52000}}]}   # +32k auf 1X2 (≥30k)
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["tier"], "top")
        self.assertEqual(a["market"], "Match Odds")
        self.assertAlmostEqual(a["inflow"], 32000)
        self.assertAlmostEqual(a["total"], 52000)     # Markt-Volumen, NICHT Spiel-Gesamt
        self.assertEqual(a["leadName"], "Alpha")

    def test_top_below_30k_none(self):
        m = match(mid=7, league="German Bundesliga", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 45000}}]}))  # +25k < 30k

    def test_biggest_inflow_market_wins(self):
        # 1X2 +7k, aber Ü/U 2.5 +25k → der groessere Zufluss-Markt gewinnt (Rest-Liga, Schwelle 20k)
        m = match(mid=8, league="Chinese League 2", country="CN",
                  markets=mk("Over/Under 2.5 Goals", [{"name": "Over 2.5 Goals", "odd": 2, "vol": 32000}, {"name": "Under 2.5 Goals", "odd": 2, "vol": 3000}]))
        hist = {"8": [{"mkv": {"Match Odds": 40000, "Over/Under 2.5 Goals": 10000}},
                      {"mkv": {"Match Odds": 47000, "Over/Under 2.5 Goals": 35000}}]}
        a = BA.fresh_alert(m, hist)
        self.assertIsNotNone(a)
        self.assertEqual(a["market"], "Over/Under 2.5 Goals")
        self.assertAlmostEqual(a["inflow"], 25000)

    def test_rest_below_20k_none(self):
        m = match(mid=8, league="Chinese League 2", country="CN", markets={})
        self.assertIsNone(BA.fresh_alert(m, {"8": [{"mkv": {"Match Odds": 5000}}, {"mkv": {"Match Odds": 20000}}]}))  # +15k < 20k

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
        m = match(mid=9, league="Chinese League 2", country="CN", markets=mk("Half Time",
                  [{"name": "Alpha", "odd": 2, "vol": 8000}]))
        alerts = BA.collect_alerts({"matches": [m]}, {"9": [{"mkv": {"Half Time": 1000}}, {"mkv": {"Half Time": 22000}}]})
        kinds = sorted(a["scenario"] for a in alerts)
        self.assertEqual(kinds, ["fresh", "ht"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestFavoriteFilter(unittest.TestCase):
    def test_ht_skips_near_lock_favorite(self):
        # 100% auf einem Ausgang, aber Quote 1.05 (fuehrt schon) -> sinnlos, kein Push
        m = match(markets=mk("Half Time", [
            {"name": "Alpha", "odd": 1.05, "vol": 9000},
            {"name": "The Draw", "odd": 15, "vol": 0}, {"name": "Beta", "odd": 30, "vol": 0}]))
        self.assertIsNone(BA.ht_alert(m))

    def test_ht_fires_when_lead_odd_ok(self):
        m = match(markets=mk("Half Time", [
            {"name": "Alpha", "odd": 1.8, "vol": 9000},
            {"name": "The Draw", "odd": 3, "vol": 500}, {"name": "Beta", "odd": 6, "vol": 500}]))
        self.assertIsNotNone(BA.ht_alert(m))

    def test_fresh_skips_near_lock_favorite(self):
        # Zufluss auf 1X2, aber Fuehrender @1.03 -> sinnlos
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.03, "vol": 90000}, {"name": "Beta", "odd": 40, "vol": 2000}]))
        hist = {"7": [{"mkv": {"Match Odds": 20000}}, {"mkv": {"Match Odds": 92000}}]}   # +72k
        self.assertIsNone(BA.fresh_alert(m, hist))

    def test_fresh_fires_when_lead_odd_ok(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.6, "vol": 60000}, {"name": "Beta", "odd": 3.2, "vol": 30000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 60000}}, {"mkv": {"Match Odds": 90000}}]})
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a["leadOdd"], 1.6)


class TestBoldMoney(unittest.TestCase):
    def test_fresh_money_is_bold(self):
        m = match(mid=7, league="German Bundesliga",
                  markets=mk("Match Odds", [{"name": "Alpha", "odd": 1.8, "vol": 45000}]))
        a = BA.fresh_alert(m, {"7": [{"mkv": {"Match Odds": 10000}}, {"mkv": {"Match Odds": 45000}}]})
        msg = BA.build_message(a)
        self.assertIn("+<b>", msg)          # Zufluss fett
        self.assertIn("jetzt <b>", msg)     # Markt-Volumen fett
        self.assertIn("@1.80", msg)         # Quote sichtbar

    def test_ht_money_is_bold(self):
        m = match(markets=mk("Half Time", [{"name": "Alpha", "odd": 1.9, "vol": 8000},
                                           {"name": "The Draw", "odd": 3, "vol": 500},
                                           {"name": "Beta", "odd": 5, "vol": 500}]))
        msg = BA.build_message(BA.ht_alert(m))
        self.assertRegex(msg, r"HZ-1X2: <b>€")   # gematchtes Geld fett
