# tests/test_betfair_pub_unconf_fav.py — kurzer Favorit nur mit Quoten-Bestaetigung (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


class TestUnconfirmedFav(unittest.TestCase):
    def test_galatasaray_137_flat_raus(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.37, "leadDir": None}))

    def test_kurzer_fav_driftet_raus(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.45, "leadDir": "out"}))

    def test_kurzer_fav_gebackt_bleibt(self):
        # Quote wird kuerzer (leadDir 'in') = echtes Steam -> bleibt
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.40, "leadDir": "in"}))

    def test_kein_kurzer_fav_bleibt(self):
        # 1.60 ist kein kurzer Favorit -> Filter greift nicht
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.60, "leadDir": None}))

    def test_underdog_geld_bleibt(self):
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 2.5, "leadDir": "out"}))

    def test_grenze_150(self):
        self.assertTrue(BA._pub_unconfirmed_fav({"leadOdd": 1.49, "leadDir": None}))
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": 1.50, "leadDir": None}))

    def test_ohne_odd_kein_flag(self):
        self.assertFalse(BA._pub_unconfirmed_fav({"leadOdd": None, "leadDir": None}))


if __name__ == "__main__":
    unittest.main()
