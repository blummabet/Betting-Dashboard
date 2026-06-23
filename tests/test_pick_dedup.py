#!/usr/bin/env python3
"""
test_pick_dedup.py — Eine Karte pro (Spiel, Markt) (23.06.2026, Lucas: PAN-CRO hatte 2× BTTS-Ja
in Cards + Tracking). Write-Boundary-Dedup in generate_wm_picks + Tripwire-Guard.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G   # noqa: E402
import wm_data_integrity as W   # noqa: E402


class TestDedupByMarket(unittest.TestCase):
    def test_keeps_one_strongest_per_market(self):
        picks = [
            {"market": "Beide Teams treffen — Ja", "verdict": "ABWÄGEN", "convictionScore": 4, "odds": 1.85},
            {"market": "Auswärtssieg", "verdict": "BET", "convictionScore": 7, "odds": 1.47},
            {"market": "Beide Teams treffen — Ja", "verdict": "ABWÄGEN", "convictionScore": 6, "odds": 1.82},
        ]
        out = G._dedup_picks_by_market(picks)
        markets = [p["market"] for p in out]
        self.assertEqual(markets.count("Beide Teams treffen — Ja"), 1)
        self.assertEqual(len(out), 2)
        # stärkerer BTTS bleibt (Conviction 6 > 4)
        btts = next(p for p in out if p["market"] == "Beide Teams treffen — Ja")
        self.assertEqual(btts["convictionScore"], 6)

    def test_bet_beats_abwaegen(self):
        picks = [
            {"market": "X", "verdict": "ABWÄGEN", "convictionScore": 9, "odds": 2.0},
            {"market": "X", "verdict": "BET", "convictionScore": 3, "odds": 1.5},
        ]
        out = G._dedup_picks_by_market(picks)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["verdict"], "BET")

    def test_no_dupes_passthrough(self):
        picks = [{"market": "A", "verdict": "BET"}, {"market": "B", "verdict": "ABWÄGEN"}]
        self.assertEqual(len(G._dedup_picks_by_market(picks)), 2)

    def test_order_preserved(self):
        picks = [{"market": "A", "verdict": "BET"}, {"market": "B", "verdict": "BET"},
                 {"market": "A", "verdict": "ABWÄGEN"}]
        out = G._dedup_picks_by_market(picks)
        self.assertEqual([p["market"] for p in out], ["A", "B"])


class TestDuplicatePickGuard(unittest.TestCase):
    def _run(self, picks):
        res = W.run_checks({"groups": {}, "picks": picks}, {}, {}, {},
                           now=datetime(2026, 6, 23, tzinfo=timezone.utc),
                           auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "no_duplicate_picks"), None)

    def test_dup_flagged(self):
        c = self._run({"L-2-PAN-CRO": [
            {"market": "Beide Teams treffen — Ja"}, {"market": "Beide Teams treffen — Ja"}]})
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])

    def test_clean_passes(self):
        c = self._run({"L-2-PAN-CRO": [
            {"market": "Beide Teams treffen — Ja"}, {"market": "Auswärtssieg"}]})
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
