#!/usr/bin/env python3
"""test_liga_betfair_anchor.py — Betfair Exchange als 2. Sharp-Anker (28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_odds as F  # noqa: E402


def _ev(books):
    return {"bookmakers": [{"key": k, "markets": [{"key": "h2h", "outcomes": o}]} for k, o in books]}


def _h2h(h, d, a):
    return [{"name": "Bayern", "price": h}, {"name": "Draw", "price": d}, {"name": "Koeln", "price": a}]


class TestBetfairAnchor(unittest.TestCase):
    def test_betfair_captured_separately(self):
        ev = _ev([("pinnacle", _h2h(1.5, 4.2, 6.5)), ("betfair_ex_eu", _h2h(1.55, 4.3, 6.2))])
        p = F.extract_prices(ev, "direct", "Bayern", "Koeln")
        self.assertEqual((p["hw"], p["dr"], p["aw"]), (1.5, 4.2, 6.5))  # Pinnacle bleibt Sharp-Anker
        self.assertEqual(p["bookmaker"], "pinnacle")
        self.assertEqual((p["bf_hw"], p["bf_dr"], p["bf_aw"]), (1.55, 4.3, 6.2))

    def test_no_betfair_no_bf_fields(self):
        ev = _ev([("pinnacle", _h2h(1.5, 4.2, 6.5))])
        p = F.extract_prices(ev, "direct", "Bayern", "Koeln")
        self.assertNotIn("bf_hw", p)

    def test_map_1x2_orientation_agnostic(self):
        # Namen werden direkt zugeordnet, egal in welcher Reihenfolge die Outcomes kommen
        outs = [{"name": "Koeln", "price": 6.5}, {"name": "Bayern", "price": 1.5}, {"name": "Draw", "price": 4.2}]
        self.assertEqual(F._map_1x2(outs, "Bayern", "Koeln"), (1.5, 4.2, 6.5))

    def test_build_entry_carries_bf(self):
        entry = F.build_odds_entry({"hw": 1.5, "dr": 4.2, "aw": 6.5, "bf_hw": 1.55, "bf_dr": 4.3, "bf_aw": 6.2},
                                   {}, "2026-08-20T10:00:00Z")
        self.assertEqual((entry["bf_hw"], entry["bf_dr"], entry["bf_aw"]), (1.55, 4.3, 6.2))


class TestKickoffFreeze(unittest.TestCase):
    def test_append_snapshot_normal(self):
        hist = {}
        n = F.append_snapshot(hist, "a-b", {"hw": 1.5, "dr": 4.0, "aw": 6.0}, "2026-08-20T10:00:00Z")
        self.assertEqual(n, 1)
        self.assertEqual(len(hist["a-b"]), 1)

    def test_append_snapshot_post_kickoff_skipped(self):
        # Anpfiff vorbei → KEIN Snapshot (In-Play würde Sharp Radar verfälschen)
        hist = {}
        n = F.append_snapshot(hist, "a-b", {"hw": 30.0, "dr": 12.0, "aw": 1.02},
                              "2026-08-20T22:00:00Z", post_ko=True)
        self.assertEqual(n, 0)
        self.assertNotIn("a-b", hist)

    def test_kickoff_passed(self):
        self.assertTrue(F._kickoff_passed("2000-01-01T00:00:00Z"))   # lange vorbei
        self.assertFalse(F._kickoff_passed("2099-01-01T00:00:00Z"))  # Zukunft
        self.assertFalse(F._kickoff_passed(None))


if __name__ == "__main__":
    unittest.main()
