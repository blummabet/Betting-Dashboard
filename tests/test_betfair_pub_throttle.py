# tests/test_betfair_pub_throttle.py — HZ-Gate + eskalierende Public-Wiederhol-Bremse (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


class TestHtUseless(unittest.TestCase):
    def test_halbzeitpause_raus(self):
        self.assertTrue(BA._pub_ht_useless({"scenario": "ht", "live": {"is_ht": True}, "leadOdd": 2.0}))

    def test_ht_longshot_raus(self):
        self.assertTrue(BA._pub_ht_useless({"scenario": "ht", "live": {"time": 40}, "leadOdd": 13.5}))

    def test_ht_plausibel_bleibt(self):
        self.assertFalse(BA._pub_ht_useless({"scenario": "ht", "live": {"time": 40}, "leadOdd": 1.82}))

    def test_ht_odd_grenze_4(self):
        self.assertFalse(BA._pub_ht_useless({"scenario": "ht", "live": {"time": 40}, "leadOdd": 4.0}))
        self.assertTrue(BA._pub_ht_useless({"scenario": "ht", "live": {"time": 40}, "leadOdd": 4.01}))

    def test_fresh_nicht_betroffen(self):
        self.assertFalse(BA._pub_ht_useless({"scenario": "fresh", "live": {"is_ht": True}, "leadOdd": 13.5}))


class TestEscalatingResend(unittest.TestCase):
    def test_ladder_hoehere_huerde_ab_3(self):
        # Leiter [2.0, 3.0, 4.5, 6.0] (22.08.2026, Lucas: 1->2 von 1.5 auf 2.0 gehaertet).
        seen = {}; k = "ht:1"
        self.assertTrue(BA.should_send_public(seen, k, 10000))          # 1. immer
        BA._pub_seen_put(seen, k, 10000)                               # n=1
        # 2. Push braucht 2.0x = 20000
        self.assertFalse(BA.should_send_public(seen, k, 19000))
        self.assertTrue(BA.should_send_public(seen, k, 20000))
        BA._pub_seen_put(seen, k, 20000)                              # n=2
        # 3. Push braucht 3.0x = 60000
        self.assertFalse(BA.should_send_public(seen, k, 59000))
        self.assertTrue(BA.should_send_public(seen, k, 60000))
        BA._pub_seen_put(seen, k, 60000)                             # n=3
        # 4. Push braucht 4.5x = 270000
        self.assertFalse(BA.should_send_public(seen, k, 269000))
        self.assertTrue(BA.should_send_public(seen, k, 270000))
        BA._pub_seen_put(seen, k, 270000)                           # n=4
        # 5.+ braucht 6.0x = 1620000
        self.assertFalse(BA.should_send_public(seen, k, 1000000))
        self.assertTrue(BA.should_send_public(seen, k, 1620000))

    def test_backward_compat_alter_float(self):
        seen = {"ht:1": 10000.0}   # Alt-Eintrag = float -> als n=1 gewertet -> 2.0x Huerde
        self.assertFalse(BA.should_send_public(seen, "ht:1", 19000))   # <2.0x
        self.assertTrue(BA.should_send_public(seen, "ht:1", 20000))    # >=2.0x

    def test_put_zaehlt_hoch(self):
        seen = {}
        BA._pub_seen_put(seen, "k", 100); self.assertEqual(seen["k"]["n"], 1)
        BA._pub_seen_put(seen, "k", 200); self.assertEqual(seen["k"]["n"], 2)



class TestPubLiveOnce(unittest.TestCase):
    """15.08.2026 (Lucas): live nur EIN Public-Push pro Spiel (Norwich kam 2. mal). Vor-Anpfiff: Leiter."""
    def _live(self, **kw):
        base = {"scenario": "fresh", "matchId": "35759270", "live": {"time": 60}}
        base.update(kw); return base

    def test_live_zweiter_push_raus(self):
        seen = {}
        a = self._live()
        # 1. Push geht (noch nichts gesehen)
        self.assertFalse(BA._pub_skip_resend(a, seen))
        BA._pub_seen_put(seen, "fresh:35759270", 70000)
        # 2. Push desselben Live-Spiels -> unterdrückt, egal wie stark das Volumen wuchs
        self.assertTrue(BA._pub_skip_resend(a, seen))

    def test_vor_anpfiff_behaelt_leiter(self):
        seen = {"fresh:1": {"v": 70000, "n": 1}}
        pre = {"scenario": "fresh", "matchId": "1", "live": {}, "kickoff": "2999-01-01T00:00:00Z"}
        self.assertFalse(BA._pub_skip_resend(pre, seen))   # nicht live -> Leiter entscheidet

    def test_erstes_live_ohne_seen_geht(self):
        self.assertFalse(BA._pub_skip_resend(self._live(), {}))

    def test_ht_zweiter_push_raus(self):
        # 15.08.2026 (Lucas): HZ-Geld auch nur EIN Push — Guabira HZ 15K->23.3K (1.55x) kam 2. mal (PRE)
        ht = {"scenario": "ht", "matchId": "42", "live": {}, "kickoff": "2999-01-01T00:00:00Z"}
        seen = {}
        self.assertFalse(BA._pub_skip_resend(ht, seen))          # 1. Push geht
        BA._pub_seen_put(seen, "ht:42", 15000)
        self.assertTrue(BA._pub_skip_resend(ht, seen))           # 2. Push -> unterdrückt (auch Vor-Anpfiff)

    def test_fresh_vor_anpfiff_behaelt_leiter(self):
        # Vor-Anpfiff FRISCH (1X2) behaelt die Staffel-Leiter (Galatasaray) -> NICHT unterdrueckt
        seen = {"fresh:9": {"v": 70000, "n": 1}}
        pre = {"scenario": "fresh", "matchId": "9", "live": {}, "kickoff": "2999-01-01T00:00:00Z"}
        self.assertFalse(BA._pub_skip_resend(pre, seen))


if __name__ == "__main__":
    unittest.main()
