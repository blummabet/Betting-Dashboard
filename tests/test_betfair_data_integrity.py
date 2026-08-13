# tests/test_betfair_data_integrity.py — Betfair-Guard-Batterie (10.08.2026, Lucas).
# Testet jeden Guard gruen UND rot, ohne Netz/Telegram (reines Modul).
import os
import sys
import json
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_data_integrity as BI

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(minutes=10)).isoformat()
STALE = (NOW - timedelta(hours=5)).isoformat()


def m(mid="1", home="Alpha", away="Beta", league="Test", country="DE",
      kickoff="2026-08-10T18:00:00Z", hw=2.0, dr=3.5, aw=4.0,
      volH=8000, volD=1000, volA=1000, live=None, captured=FRESH):
    li = live if live is not None else {"time": 0, "finished": False}
    return {"matchId": mid, "home": home, "away": away, "league": league, "country": country,
            "kickoff": kickoff, "capturedAt": captured, "liveInfo": li,
            "totalVol": volH + volD + volA,
            "markets": {"Match Odds": {"vol": volH + volD + volA, "runners": [
                {"name": home, "odd": hw, "vol": volH},
                {"name": "The Draw", "odd": dr, "vol": volD},
                {"name": away, "odd": aw, "vol": volA}]}}}


def prices(matches, gen=FRESH):
    return {"_meta": {"generatedAt": gen, "n": len(matches)}, "matches": matches}


def hist_pts(n=2, mkv=True, minute=None):
    """n History-Punkte; jeder mit/ohne mkv, optional Live-Minute."""
    pts = []
    for i in range(n):
        p = {"ts": (NOW - timedelta(minutes=15 * (n - i))).isoformat(), "totalVol": 10000}
        if mkv:
            p["mkv"] = {"Match Odds": 10000 + i * 5000}
        if minute is not None:
            p["min"] = minute
        pts.append(p)
    return pts


def ctx(**kw):
    kw.setdefault("now", NOW)
    return BI.BetfairCtx(**kw)


class TestPricesFresh(unittest.TestCase):
    def test_fresh_ok(self):
        self.assertTrue(BI.check_prices_fresh(ctx(prices=prices([m()])))["ok"])

    def test_stale_error(self):
        c = ctx(prices=prices([m(captured=STALE)], gen=STALE))
        r = BI.check_prices_fresh(c)
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_no_ts_error(self):
        self.assertFalse(BI.check_prices_fresh(ctx(prices={"matches": [{"matchId": "1"}]}))["ok"])


class TestFeedPopulated(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(BI.check_feed_populated(ctx(prices=prices([m()])))["ok"])

    def test_empty_error(self):
        r = BI.check_feed_populated(ctx(prices=prices([])))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_all_zero_vol_error(self):
        mm = m(volH=0, volD=0, volA=0)
        self.assertFalse(BI.check_feed_populated(ctx(prices=prices([mm])))["ok"])


class TestHistoryMkv(unittest.TestCase):
    def _many(self, mkv_ok):
        matches, hist = [], {}
        for i in range(6):
            mid = str(100 + i)
            matches.append(m(mid=mid))
            hist[mid] = hist_pts(2, mkv=mkv_ok)
        return ctx(prices=prices(matches), history=hist)

    def test_present_ok(self):
        self.assertTrue(BI.check_history_mkv_present(self._many(True))["ok"])

    def test_missing_error(self):
        r = BI.check_history_mkv_present(self._many(False))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_not_warmed_ignored(self):
        # nur 1 History-Punkt → kein Delta erwartet → kein Fehler
        c = ctx(prices=prices([m(mid="1")]), history={"1": hist_pts(1, mkv=False)})
        self.assertTrue(BI.check_history_mkv_present(c)["ok"])


class TestLiveMinute(unittest.TestCase):
    def test_ok(self):
        c = ctx(prices=prices([m()]), history={"1": hist_pts(2, minute=55)})
        self.assertTrue(BI.check_live_minute_sane(c)["ok"])

    def test_bad_value_error(self):
        c = ctx(history={"9": [{"min": 200}]})
        r = BI.check_live_minute_sane(c)
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_live_missing_minute_warn(self):
        live_m = m(mid="1", live={"time": 60, "finished": False})
        c = ctx(prices=prices([live_m]), history={"1": hist_pts(2, minute=None)})
        r = BI.check_live_minute_sane(c)
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "warn")


class TestDirectionCoversMoney(unittest.TestCase):
    def _setup(self, prev_val):
        matches, hist, direction = [], {}, {}
        for i in range(6):
            mid = str(200 + i)
            mm = m(mid=mid)
            matches.append(mm)
            hist[mid] = hist_pts(2)
            direction[mid] = {"Match Odds": {"Alpha": {"dir": "in", "prev": prev_val, "odd": 2.0}}}
        return ctx(prices=prices(matches), history=hist, direction=direction)

    def test_prev_present_ok(self):
        self.assertTrue(BI.check_direction_covers_money(self._setup(2.1))["ok"])

    def test_prev_missing_error(self):
        r = BI.check_direction_covers_money(self._setup(None))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")


class TestDirectionPresent(unittest.TestCase):
    def test_ok(self):
        d = {"1": {"Match Odds": {"Alpha": {"dir": "in", "prev": 2.1, "odd": 2.0}}}}
        self.assertTrue(BI.check_direction_present(ctx(prices=prices([m()]), direction=d))["ok"])

    def test_empty_with_feed_error(self):
        r = BI.check_direction_present(ctx(prices=prices([m()]), direction={}))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_all_prev_null_error(self):
        d = {str(i): {"Match Odds": {"R": {"dir": "flat", "prev": None, "odd": 2.0}}} for i in range(60)}
        self.assertFalse(BI.check_direction_present(ctx(prices=prices([m()]), direction=d))["ok"])


class TestConsensusFresh(unittest.TestCase):
    def test_fresh_ok(self):
        c = ctx(consensus={"generatedAt": FRESH, "count": 5, "covered": 3, "games": []})
        self.assertTrue(BI.check_consensus_fresh(c)["ok"])

    def test_stale_error(self):
        c = ctx(consensus={"generatedAt": (NOW - timedelta(hours=8)).isoformat()})
        r = BI.check_consensus_fresh(c)
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")


class TestConsensusAnchorCoverage(unittest.TestCase):
    def test_some_anchors_ok(self):
        games = [{"league": "X", "verdict": "konsens"}] + [{"league": "X", "verdict": "no_anchor"}] * 5
        c = ctx(consensus={"games": games, "covered": 1})
        self.assertTrue(BI.check_consensus_anchor_coverage(c)["ok"])

    def test_zero_anchors_warn(self):
        from betfair_consensus import LEAGUE_ODDS_KEY
        lg = next(iter(LEAGUE_ODDS_KEY))   # 13.08.2026 (Lucas-Audit): echte gemappte Liga - nur die
        games = [{"league": lg, "verdict": "no_anchor"} for _ in range(6)]   # zaehlt als anchorable
        c = ctx(consensus={"games": games, "covered": 0})
        r = BI.check_consensus_anchor_coverage(c)
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "warn")

    def test_no_games_no_verdict(self):
        self.assertTrue(BI.check_consensus_anchor_coverage(ctx(consensus={"games": []}))["ok"])


class TestTrackRecord(unittest.TestCase):
    def test_fresh_ok(self):
        self.assertTrue(BI.check_track_record_fresh(ctx(record={"generatedAt": FRESH, "n": 50}))["ok"])

    def test_stale_error(self):
        c = ctx(record={"generatedAt": (NOW - timedelta(hours=9)).isoformat()})
        self.assertFalse(BI.check_track_record_fresh(c)["ok"])

    def test_grading_sane_ok(self):
        results = [{"win": (i % 2 == 0), "odd": 2.0, "fav": "home"} for i in range(50)]
        c = ctx(record={"n": 50}, results=results)
        self.assertTrue(BI.check_track_record_grading_sane(c)["ok"])

    def test_corrupt_result_warn(self):
        results = [{"win": "yes", "odd": 0.5}]  # kein Bool, unmoegliche Quote, kein fav
        r = BI.check_track_record_grading_sane(ctx(record={"n": 1}, results=results))
        self.assertFalse(r["ok"])

    def test_rate_out_of_band_warn(self):
        results = [{"win": True, "odd": 2.0, "fav": "home"} for _ in range(50)]  # 100% → Bug
        r = BI.check_track_record_grading_sane(ctx(record={"n": 50}, results=results))
        self.assertFalse(r["ok"])


class TestStuckPending(unittest.TestCase):
    def test_normal_backlog_ok(self):
        # bis 60 h TTL ist pending normal (Spiele ohne 'finished') → kein Fehler
        st = {"pending": {"1": {"home": "A", "away": "B", "kickoff": (NOW - timedelta(hours=55)).isoformat()}}}
        self.assertTrue(BI.check_no_stuck_pending(ctx(state=st))["ok"])

    def test_past_ttl_warn(self):
        # > 72 h nach Anpfiff und noch pending → Prune hakt
        st = {"pending": {"1": {"home": "A", "away": "B", "kickoff": (NOW - timedelta(hours=80)).isoformat()}}}
        r = BI.check_no_stuck_pending(ctx(state=st))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "warn")


class TestOddsShape(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(BI.check_odds_and_shape_sane(ctx(prices=prices([m()])))["ok"])

    def test_phantom_error(self):
        mm = m()
        mm["kickoff"] = None
        r = BI.check_odds_and_shape_sane(ctx(prices=prices([mm])))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "error")

    def test_impossible_odd_warn(self):
        mm = m(hw=0.5)  # < 1.01
        r = BI.check_odds_and_shape_sane(ctx(prices=prices([mm])))
        self.assertFalse(r["ok"]); self.assertEqual(r["severity"], "warn")


class TestPublicEval(unittest.TestCase):
    def test_no_ts_skipped(self):
        self.assertTrue(BI.check_public_eval_alive(ctx(pubrec={"foo": 1}))["ok"])

    def test_stale_warn(self):
        c = ctx(pubrec={"generatedAt": (NOW - timedelta(hours=8)).isoformat()})
        self.assertFalse(BI.check_public_eval_alive(c)["ok"])

    def test_fresh_ok(self):
        self.assertTrue(BI.check_public_eval_alive(ctx(pubrec={"generatedAt": FRESH}))["ok"])


class TestRegistryAndMain(unittest.TestCase):
    def test_run_checks_crash_safe(self):
        @BI.betfair_check
        def _boom(c):
            raise RuntimeError("kaputt")
        try:
            res = BI.run_checks(ctx(prices=prices([m()])))
            self.assertTrue(any(x["id"] == "_boom" for x in res))
        finally:
            BI.BETFAIR_CHECKS[:] = [f for f in BI.BETFAIR_CHECKS if f.__name__ != "_boom"]

    def test_all_guards_return_schema(self):
        res = BI.run_checks(ctx(prices=prices([m()])))
        self.assertGreaterEqual(len(res), 12)
        for c in res:
            for k in ("id", "label", "severity", "ok", "nFail", "failures", "note"):
                self.assertIn(k, c)

    def test_main_writes_status(self, ):
        import tempfile, importlib
        # main() schreibt neben dem Modul — hier nur pruefen, dass build_ctx_from_disk + run_checks laufen
        res = BI.run_checks(BI.build_ctx_from_disk(now=NOW))
        self.assertIsInstance(res, list)


if __name__ == "__main__":
    unittest.main()
