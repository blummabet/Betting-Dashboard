#!/usr/bin/env python3
"""test_early_season_penalty.py — Season-Opener-Dämpfung (01.07.2026, Lucas: „ersten 3 Spieltage ganz
wenig dämpfen, aber Vorsaison-Form/H2H bleiben wichtig"). Kleine Conviction-Vorsicht NUR für Liga/MLS
in den ersten N Spieltagen; WM unberührt; Signale selbst bleiben voll gewichtet."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate_wm_picks as G


class TestEarlySeasonPenalty(unittest.TestCase):
    def setUp(self):
        self._orig = G.D.is_liga

    def tearDown(self):
        G.D.is_liga = self._orig

    def test_wm_never_penalized(self):
        G.D.is_liga = lambda: False
        for md in (1, 2, 3):
            self.assertEqual(G._early_season_penalty({"matchday": md}), 0.0)

    def test_liga_early_matchdays_penalized(self):
        G.D.is_liga = lambda: True
        for md in range(1, G.EARLY_SEASON_MATCHDAYS + 1):
            self.assertEqual(G._early_season_penalty({"matchday": md}),
                             G.EARLY_SEASON_CONVICTION_PENALTY)

    def test_liga_later_matchdays_not_penalized(self):
        G.D.is_liga = lambda: True
        self.assertEqual(G._early_season_penalty({"matchday": G.EARLY_SEASON_MATCHDAYS + 1}), 0.0)
        self.assertEqual(G._early_season_penalty({"matchday": 20}), 0.0)

    def test_missing_or_bad_matchday(self):
        G.D.is_liga = lambda: True
        self.assertEqual(G._early_season_penalty({}), 0.0)
        self.assertEqual(G._early_season_penalty({"matchday": None}), 0.0)
        self.assertEqual(G._early_season_penalty({"matchday": "x"}), 0.0)

    def test_penalty_is_small(self):
        # „ganz wenig dämpfen" — max 1 Conviction-Punkt, damit Signale/Move dominieren
        self.assertLessEqual(G.EARLY_SEASON_CONVICTION_PENALTY, 1.0)


if __name__ == "__main__":
    unittest.main()
