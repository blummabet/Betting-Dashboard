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



class TestLiveUnderReactive(unittest.TestCase):
    """15.08.2026 (Lucas): live in-play Tore-Über/Unter, Geld auf UNTER = reaktiv (Zeit-Zerfall) -> raus
    (HZ + Voll-Match, Trades + Public). Über bleibt, HZ-1X2/1X2/Corners/Vor-Anpfiff bleiben."""
    def _a(self, **kw):
        base = {"scenario": "ht", "market": "First Half Goals 1.5", "leadLabel": "Under 1.5 Goals",
                "leadOdd": 1.85, "leadDir": "in", "live": {"time": 38}}
        base.update(kw)
        return base

    def test_live_hz_under_raus(self):
        self.assertTrue(BA._live_under_reactive(self._a()))

    def test_live_ft_under_raus(self):
        # der neue Fall: Voll-Match Over/Under 2.5, fresh, live, Unter (Bolton v Preston)
        self.assertTrue(BA._live_under_reactive({"scenario": "fresh", "market": "Over/Under 2.5 Goals",
            "leadName": "Under 2.5 Goals", "leadOdd": 1.35, "live": {"time": 84}}))

    def test_live_over_bleibt(self):
        self.assertFalse(BA._live_under_reactive(self._a(market="First Half Goals 0.5", leadLabel="Over 0.5 Goals")))
        self.assertFalse(BA._live_under_reactive({"scenario": "fresh", "market": "Over/Under 2.5 Goals",
            "leadName": "Over 2.5 Goals", "live": {"time": 84}}))

    def test_vor_anpfiff_bleibt(self):
        self.assertFalse(BA._live_under_reactive(self._a(live={}, kickoff="2999-01-01T00:00:00Z")))
        self.assertFalse(BA._live_under_reactive({"scenario": "fresh", "market": "Over/Under 2.5 Goals",
            "leadName": "Under 2.5 Goals", "live": {}, "kickoff": "2999-01-01T00:00:00Z"}))

    def test_hz_1x2_und_1x2_bleiben(self):
        self.assertFalse(BA._live_under_reactive(self._a(market="Half Time", leadLabel="Bolton (Heim)")))
        self.assertFalse(BA._live_under_reactive({"scenario": "fresh", "market": "Match Odds",
            "leadName": "Bolton", "live": {"time": 84}}))

    def test_corners_cards_nicht_betroffen(self):
        # "Corners/Cards Over/Under" enthält kein "Goals" -> bleibt
        self.assertFalse(BA._live_under_reactive({"scenario": "fresh", "market": "Corners Over/Under 8.5",
            "leadName": "Under 8.5", "live": {"time": 84}}))


if __name__ == "__main__":
    unittest.main()
