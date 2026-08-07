"""test_betfair_public_eval.py — Auswertung der öffentlichen Betfair-Pushs (31.07.2026, Lucas).
Grading gegen End-/HT-Stand (wiederverwendet betfair_track_record), Bilanz (Treffer/ROI)."""
import os, sys, unittest
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_public_eval as E

NOW = datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc)


def _p(mid, market, lead, odd, home="A", away="B", scn="fresh", ht=None):
    return {"k": mid, "matchId": mid, "scenario": scn, "market": market, "league": "L",
            "home": home, "away": away, "leadName": lead, "leadOdd": odd, "value": 30000,
            "sentAt": "2026-07-31T05:00:00+00:00", "status": "pending", "htScore": ht}


def _fin(mid, h, a, is_ht=False):
    return {"matchId": mid, "liveInfo": {"finished": True, "goal_v1": h, "goal_v2": a, "is_ht": is_ht}}


class TestSettle(unittest.TestCase):
    def test_over_under_win(self):
        led = [_p("100", "Over/Under 3.5 Goals", "Over 3.5 Goals", 2.0)]
        E.settle(led, {"matches": [_fin("100", 3, 2)]}, NOW)   # 5 Tore → OVER
        self.assertEqual(led[0]["status"], "won")
        self.assertAlmostEqual(led[0]["profit"], 1.0)

    def test_1x2_loss(self):
        led = [_p("102", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        E.settle(led, {"matches": [_fin("102", 1, 2)]}, NOW)   # Auswärtssieg → H verliert
        self.assertEqual(led[0]["status"], "lost")
        self.assertAlmostEqual(led[0]["profit"], -1.0)

    def test_ht_under_win_with_captured_score(self):
        led = [_p("101", "First Half Goals 1.5", "Under 1.5 Goals", 1.5, scn="ht", ht=[0, 0])]
        E.settle(led, {"matches": [_fin("101", 1, 1)]}, NOW)   # HT 0:0 → UNDER 1.5
        self.assertEqual(led[0]["status"], "won")

    def test_ht_market_without_score_is_void(self):
        led = [_p("103", "Half Time", "A", 2.0, scn="ht")]     # kein HT-Stand eingefangen
        E.settle(led, {"matches": [_fin("103", 2, 0)]}, NOW)
        self.assertEqual(led[0]["status"], "void")             # nicht abrechenbar → nicht gezählt

    def test_expire_stale_pending(self):
        led = [_p("999", "Match Odds", "A", 2.0)]              # sentAt 05:00, NOW +3d später
        late = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        E.settle(led, {"matches": []}, late)
        self.assertEqual(led[0]["status"], "expired")


class TestCaptureHt(unittest.TestCase):
    def test_captures_halftime_score(self):
        led = [_p("200", "First Half Goals 1.5", "Under 1.5 Goals", 1.5, scn="ht")]
        prices = {"matches": [{"matchId": "200", "liveInfo": {"is_ht": True, "goal_v1": 1, "goal_v2": 0, "finished": False}}]}
        E.capture_ht(led, prices, NOW)
        self.assertEqual(led[0]["htScore"], [1, 0])


class TestSettleFromTrack(unittest.TestCase):
    """07.08.2026: Push-Bilanz erbt die Abrechnungen des breiten Track-Records (auch Verschwinde-Settle)."""

    def test_erbt_finished_vom_track(self):
        led = [_p("500", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        tr = [{"matchId": "500", "market": "Match Odds", "ft": [2, 0], "ht": None}]
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "won")
        self.assertEqual(led[0]["via"], "track")
        self.assertAlmostEqual(led[0]["profit"], 0.8)

    def test_erbt_auch_ohne_eigenen_feed(self):
        # Feed hier LEER — der Push wird trotzdem ueber den Track abgerechnet, danach laesst
        # der eigene Feed-Pfad den bereits gesettelten in Ruhe.
        led = [_p("501", "Over/Under 2.5 Goals", "Under 2.5 Goals", 1.5)]
        tr = [{"matchId": "501", "market": "Over/Under 2.5 Goals", "ft": [1, 0], "ht": None, "via": "vanish"}]
        E.settle_from_track(led, tr, NOW)
        E.settle(led, {"matches": []}, NOW)
        self.assertEqual(led[0]["status"], "won")            # 1 Tor < 2.5 → UNDER trifft

    def test_ht_markt_ohne_ht_stand_bleibt_pending(self):
        led = [_p("502", "Half Time", "A", 2.0, scn="ht")]
        tr = [{"matchId": "502", "market": "Half Time", "ft": [2, 0], "ht": None}]
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "pending")        # nicht abrechenbar → spaeter Feed/TTL

    def test_kein_track_treffer_bleibt_pending(self):
        led = [_p("503", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        E.settle_from_track(led, [], NOW)
        self.assertEqual(led[0]["status"], "pending")

    def test_alte_track_zeile_ohne_ft_ht_ignoriert(self):
        led = [_p("504", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        tr = [{"matchId": "504", "market": "Match Odds"}]    # alte Zeile ohne ft/ht → ignorieren
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "pending")


class TestSummarize(unittest.TestCase):
    def test_hitrate_roi_and_splits(self):
        led = [
            {"status": "won", "scenario": "fresh", "market": "Over/Under 3.5 Goals", "leadOdd": 2.0, "profit": 1.0},
            {"status": "lost", "scenario": "fresh", "market": "Match Odds", "leadOdd": 1.8, "profit": -1.0},
            {"status": "won", "scenario": "ht", "market": "First Half Goals 1.5", "leadOdd": 1.5, "profit": 0.5},
            {"status": "pending", "scenario": "fresh", "market": "Match Odds", "leadOdd": 2.0},
        ]
        r = E.summarize(led, NOW)
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["wins"], 2)
        self.assertAlmostEqual(r["hitRate"], 2/3, places=3)
        self.assertAlmostEqual(r["roi"], 0.5/3, places=3)
        self.assertEqual(r["pending"], 1)
        self.assertIn("fresh", r["byScenario"])
        self.assertIn("ht", r["byScenario"])
        self.assertEqual(r["byScenario"]["ht"]["wins"], 1)


if __name__ == "__main__":
    unittest.main()
