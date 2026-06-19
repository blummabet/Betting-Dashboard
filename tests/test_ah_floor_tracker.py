#!/usr/bin/env python3
"""
test_ah_floor_tracker.py — AH-Preis-Floor + AH-Linien-Tracker (19.06.2026, Lucas)

Tiefe Handicaps (<20¢) sind rauschige Longshots → gekappt bis der Tracker +EV beweist.
Der Tracker bucketet AH-Bets nach |Linie|.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import auto_wm_poly_trigger as T          # noqa: E402
import analyze_ah_outcomes as A           # noqa: E402


class TestAhFloorConfig(unittest.TestCase):
    def test_floor_loaded(self):
        self.assertAlmostEqual(T.AH_MIN_ENTRY_PRICE, 0.20, places=2)
        # strenger als der allgemeine Entry-Floor
        self.assertGreater(T.AH_MIN_ENTRY_PRICE, T.MIN_ENTRY_PRICE)


class TestAhLineBucket(unittest.TestCase):
    def test_parses_depth_signless(self):
        self.assertEqual(A._line_bucket("AH Heim -3.5"), 3.5)
        self.assertEqual(A._line_bucket("AH Auswärts +2.5"), 2.5)
        self.assertEqual(A._line_bucket("AH Heim -1.5"), 1.5)

    def test_non_ah_returns_none(self):
        self.assertIsNone(A._line_bucket("Über 2.5 Tore"))
        self.assertIsNone(A._line_bucket("Heimsieg"))
        self.assertIsNone(A._line_bucket(""))

    def test_analyze_buckets_by_line(self, ):
        import json, tempfile, os
        results = {"bets": [
            {"market": "AH Heim -3.5", "result": "LOSS", "stake": 5.5, "pnl": -5.5},
            {"market": "AH Heim -3.5", "result": "WIN",  "stake": 5.5, "pnl": 14.0},
            {"market": "AH Heim -2.5", "result": "SOLD", "stake": 5.5, "pnl": 0.5},
            {"market": "Über 2.5 Tore", "result": "WIN", "stake": 5.5, "pnl": 4.0},
        ]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(results, f); rp = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"bets": []}, f); pp = f.name
        try:
            b = A.analyze(rp, pp)
            self.assertEqual(b[3.5]["decided"], 2)
            self.assertEqual(b[3.5]["win"], 1)
            self.assertEqual(b[3.5]["loss"], 1)
            self.assertEqual(b[2.5]["decided"], 1)
            self.assertNotIn(None, b)   # Tor-Markt nicht gebucket
        finally:
            os.unlink(rp); os.unlink(pp)


if __name__ == "__main__":
    unittest.main()
