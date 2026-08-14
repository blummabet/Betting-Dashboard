# tests/test_betfair_league_coverage.py — grosse Ligen haben einen Pinnacle-Anker-Key (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_consensus as BC


class TestLeagueCoverage(unittest.TestCase):
    def test_big_leagues_mapped(self):
        want = {
            "Turkish Super League":         "soccer_turkey_super_league",
            "Dutch Eredivisie":             "soccer_netherlands_eredivisie",
            "English Sky Bet Championship": "soccer_efl_champ",
            "German Bundesliga 2":          "soccer_germany_bundesliga2",
            "Swedish Allsvenskan":          "soccer_sweden_allsvenskan",
            "Saudi Professional League":    "soccer_saudi_arabia_pro_league",
        }
        for lg, key in want.items():
            self.assertEqual(BC.LEAGUE_ODDS_KEY.get(lg), key, "%s fehlt/falsch gemappt" % lg)

    def test_top5_and_mls_still_there(self):
        for lg in ("English Premier League", "Spanish La Liga", "German Bundesliga",
                   "Italian Serie A", "French Ligue 1", "Major League Soccer"):
            self.assertIn(lg, BC.LEAGUE_ODDS_KEY)

    def test_keys_are_soccer_prefixed(self):
        for key in BC.LEAGUE_ODDS_KEY.values():
            self.assertTrue(key.startswith("soccer_"), "%s ist kein soccer_-Key" % key)


if __name__ == "__main__":
    unittest.main()
