#!/usr/bin/env python3
"""test_corner_probe.py — Coverage-Probe-Parsing für Corner/HT-Märkte (28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import probe_corner_markets as P  # noqa: E402


class TestSummary(unittest.TestCase):
    def test_maps_books_per_market_and_flags_sharp(self):
        ev = {"bookmakers": [
            {"key": "pinnacle", "markets": [
                {"key": "alternate_totals_corners", "outcomes": [{"name": "Over", "price": 1.9}]},
                {"key": "totals_h1", "outcomes": [{"name": "Over", "price": 2.0}]},
            ]},
            {"key": "unibet", "markets": [
                {"key": "corners_1x2", "outcomes": [{"name": "X", "price": 3.0}]},
                {"key": "alternate_totals_corners", "outcomes": []},   # leer → ignorieren
            ]},
        ]}
        s = P.summarize_event_odds(ev)
        self.assertEqual(s["byMarket"]["alternate_totals_corners"], ["pinnacle"])  # unibet leer
        self.assertEqual(s["byMarket"]["corners_1x2"], ["unibet"])
        self.assertEqual(s["cornerBooks"], ["pinnacle", "unibet"])
        self.assertEqual(s["sharpCorner"], ["pinnacle"])
        self.assertEqual(s["htBooks"], ["pinnacle"])
        self.assertEqual(s["sharpHt"], ["pinnacle"])

    def test_empty(self):
        s = P.summarize_event_odds({})
        self.assertEqual(s["cornerBooks"], [])
        self.assertEqual(s["sharpCorner"], [])


if __name__ == "__main__":
    unittest.main()
