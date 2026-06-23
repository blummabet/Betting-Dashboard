#!/usr/bin/env python3
"""
test_steam_lag_dedup.py — Steam-Lag: genau EINE Position pro (Match, Markt).

23.06.2026 (Lucas): die Dedup fand nach Konvergenz den Eintrag nicht mehr (Filter status=='OPEN')
und make_signal_id war tages-getaggt → dieselbe Wette wurde mehrfach getrackt (JOR-DZA hw 6×).
Fix: stabile ID + Match auf jeden Eintrag != RESOLVED. Anderer Markt im selben Spiel bleibt
eine eigene Position.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import steam_lag_monitor as M       # noqa: E402
import wm_data_integrity as W       # noqa: E402


class TestStableSignalId(unittest.TestCase):
    def test_id_independent_of_date(self):
        a = M.make_signal_id("AAA-BBB", "hw", "2026-06-08T09:00:00Z")
        b = M.make_signal_id("AAA-BBB", "hw", "2026-06-17T20:00:00Z")
        self.assertEqual(a, b, "ID muss stabil pro (Match,Markt) sein, datum-unabhängig")

    def test_different_market_different_id(self):
        self.assertNotEqual(M.make_signal_id("AAA-BBB", "hw"),
                            M.make_signal_id("AAA-BBB", "dr"))


class TestNoDuplicateAfterConvergence(unittest.TestCase):
    def _converged_entry(self):
        return {
            "id": "AAA-BBB_hw", "matchKey": "AAA-BBB", "homeId": "AAA", "awayId": "BBB",
            "home": "A", "away": "B", "homeFlag": "x", "awayFlag": "y",
            "matchDate": "2026-12-30", "market": "hw", "marketLabel": "Heimsieg",
            "signalTs": "2026-06-20T00:00:00Z",
            "entryEdgePp": 3.0, "entryPolyPrice": 0.30, "entryPinnFair": 0.33,
            "snapshots": [{"ts": "2026-06-20T00:00:00Z", "edgePp": 3.0,
                           "polyPrice": 0.30, "pinnFair": 0.33, "steamLag": False}],
            "currentEdgePp": 0.5, "currentPolyPrice": 0.33, "convergencePct": 100.0,
            "status": "CONVERGED", "convergenceTs": "2026-06-21T00:00:00Z",
            "convergenceHours": 24, "outcome": None,
        }

    def _signal(self, edge=3.5):
        return {"key": "AAA-BBB", "homeId": "AAA", "awayId": "BBB",
                "homeName": "A", "awayName": "B", "matchDate": "2026-12-30",
                "bestEdge": edge, "bestEdgeKey": "hw", "steamLag": False,
                "poly_hw": 0.29, "fair_hw": 0.325, "vol": 0}

    def test_redetection_appends_not_duplicates(self):
        log = {"signals": [self._converged_entry()], "updatedAt": "", "runCount": 0}
        M.update_log(log, [self._signal()], {}, "2026-06-25T12:00:00Z", kickoffs={})
        hw = [e for e in log["signals"] if e["matchKey"] == "AAA-BBB" and e["market"] == "hw"]
        self.assertEqual(len(hw), 1, "Re-Detektion darf KEINEN zweiten Eintrag erzeugen")
        self.assertGreaterEqual(len(hw[0]["snapshots"]), 2, "Snapshot muss angehängt werden")

    def test_different_market_creates_separate_position(self):
        log = {"signals": [self._converged_entry()], "updatedAt": "", "runCount": 0}
        dr = {"key": "AAA-BBB", "homeId": "AAA", "awayId": "BBB", "homeName": "A",
              "awayName": "B", "matchDate": "2026-12-30", "bestEdge": 2.6,
              "bestEdgeKey": "dr", "steamLag": False, "poly_dr": 0.25, "fair_dr": 0.276, "vol": 0}
        M.update_log(log, [dr], {}, "2026-06-25T12:00:00Z", kickoffs={})
        keys = {(e["matchKey"], e["market"]) for e in log["signals"]}
        self.assertIn(("AAA-BBB", "hw"), keys)
        self.assertIn(("AAA-BBB", "dr"), keys)


class TestSteamLagDupeGuard(unittest.TestCase):
    def _run(self, log):
        import unittest.mock as mock
        with mock.patch.object(W, "_lazy",
                               side_effect=lambda f: log if f == "steam_lag_log.json" else {}):
            res = W.run_checks({"groups": {}, "picks": {}}, {}, {}, {},
                               now=datetime(2026, 6, 23, tzinfo=timezone.utc),
                               auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "steam_lag_no_dupes"), None)

    def test_dupes_flagged(self):
        log = {"signals": [{"matchKey": "AAA-BBB", "market": "hw"},
                           {"matchKey": "AAA-BBB", "market": "hw"}]}
        c = self._run(log)
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])

    def test_clean_passes(self):
        log = {"signals": [{"matchKey": "AAA-BBB", "market": "hw"},
                           {"matchKey": "AAA-BBB", "market": "dr"}]}
        c = self._run(log)
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
