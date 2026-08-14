# tests/test_betfair_pub_coherence.py — Public-Filter: Geld-% vs Quote (14.08.2026, Lucas).
# Galatasaray 85%@13.50 (inkohaerent) + Wolves Under 87% Quote driftet (Live-Drift) raus aus Public.
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_alerts as BA


class TestPubIncoherent(unittest.TestCase):
    def test_galatasaray_high_share_long_odd(self):
        self.assertTrue(BA._pub_incoherent({"leadShare": 0.85, "leadOdd": 13.50}))

    def test_normal_high_share_short_odd_ok(self):
        self.assertFalse(BA._pub_incoherent({"leadShare": 0.85, "leadOdd": 1.43}))

    def test_low_share_long_odd_ok(self):
        # nur 55% auf @4 -> kein Widerspruch (Underdog-Geld, kann echt sein)
        self.assertFalse(BA._pub_incoherent({"leadShare": 0.55, "leadOdd": 4.0}))

    def test_boundary_odd_3_share_70(self):
        self.assertTrue(BA._pub_incoherent({"leadShare": 0.70, "leadOdd": 3.0}))
        self.assertFalse(BA._pub_incoherent({"leadShare": 0.69, "leadOdd": 3.0}))
        self.assertFalse(BA._pub_incoherent({"leadShare": 0.80, "leadOdd": 2.9}))

    def test_no_odd_no_flag(self):
        self.assertFalse(BA._pub_incoherent({"leadShare": 0.9, "leadOdd": None}))


class TestPubLiveDrift(unittest.TestCase):
    def _live(self, **kw):
        a = {"live": {"time": 33}, "leadDir": "out"}
        a.update(kw)
        return a

    def test_live_drift_out_flagged(self):
        self.assertTrue(BA._pub_live_drift(self._live()))            # Wolves-Fall

    def test_live_backed_in_ok(self):
        self.assertFalse(BA._pub_live_drift(self._live(leadDir="in")))

    def test_prematch_drift_not_flagged(self):
        # nicht live -> greift nicht (Vor-Anpfiff-Drift ist eigener Fall)
        self.assertFalse(BA._pub_live_drift({"live": {}, "leadDir": "out"}))

    def test_live_flat_ok(self):
        self.assertFalse(BA._pub_live_drift(self._live(leadDir=None)))


if __name__ == "__main__":
    unittest.main()
