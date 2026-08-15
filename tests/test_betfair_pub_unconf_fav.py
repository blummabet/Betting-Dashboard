# tests/test_betfair_pub_unconf_fav.py — kurzer Favorit nur mit Quoten-Bestaetigung (14.08.2026, Lucas).
# 14.08.2026: Schwelle 1.50 -> 1.35 -> nur noch sehr kurze Favoriten (1.30-1.35) brauchen Bestaetigung.
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


class TestUnconfirmedFav(unittest.TestCase):
    def test_sehr_kurzer_fav_flat_raus(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.32, "leadDir": None}))

    def test_sehr_kurzer_fav_driftet_raus(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.33, "leadDir": "out"}))

    def test_sehr_kurzer_fav_gebackt_bleibt(self):
        # Quote wird kuerzer (leadDir 'in') = echtes Steam -> bleibt
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.32, "leadDir": "in"}))

    def test_ab_135_kein_kurzer_fav_mehr(self):
        # 14.08.2026 (Lucas): Schwelle 1.35 -> 1.37/1.45 sind KEINE kurzen Favoriten mehr,
        # Filter greift nicht (sie haengen jetzt an Live-Drift/Inkohaerenz + Throttle).
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.37, "leadDir": None}))
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.45, "leadDir": "out"}))

    def test_underdog_geld_bleibt(self):
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 2.5, "leadDir": "out"}))

    def test_grenze_135(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.34, "leadDir": None}))
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.35, "leadDir": None}))

    def test_ohne_odd_kein_flag(self):
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": None, "leadDir": None}))


if __name__ == "__main__":
    unittest.main()
