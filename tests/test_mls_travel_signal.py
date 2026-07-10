#!/usr/bin/env python3
"""test_mls_travel_signal.py — MLS Reise/Höhe/Rasen-Composite (09.07.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.mls_travel import MLSTravelSignal

sig = MLSTravelSignal()


class TestMLSTravel(unittest.TestCase):
    def test_coast_to_coast_plus_altitude(self):
        # Colorado (1610, 1580 m) zu Hause vs Vancouver (1603, Küste, Turf) auswärts:
        # weite Reise + Höhe + (kein Turf-Mismatch, beide... Vancouver turf, Colorado grass → mismatch)
        ctx = {"home_id": "1610", "away_id": "1603"}
        r = sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)              # Heim-Vorteil durch Bürde
        self.assertGreater(r.metadata["dist_km"], 1500)

    def test_away_side_penalised(self):
        r = sig.evaluate({"market": "Auswärtssieg"}, {"home_id": "1610", "away_id": "1603"})
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_short_local_trip_no_signal(self):
        # LAFC (1616) vs LA Galaxy (1605) — selbe Stadt, keine Zeitzone/Höhe → kein Signal
        self.assertIsNone(sig.evaluate({"market": "Heimsieg"}, {"home_id": "1616", "away_id": "1605"}))

    def test_non_mls_teams_none(self):
        # WM/Liga-IDs nicht in der Venue-Tabelle → None (Signal n/a)
        self.assertIsNone(sig.evaluate({"market": "Heimsieg"}, {"home_id": "MEX", "away_id": "ZAF"}))


if __name__ == "__main__":
    unittest.main()
