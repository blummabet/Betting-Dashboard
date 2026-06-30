#!/usr/bin/env python3
"""test_pre_match_readiness.py — Readiness-Exit-Logik (30.06.2026, Lucas: „WM-Action fehlgeschlagen").
Wetter-Lücke darf den Workflow nur failen, wenn Spiele anstehen (zwischen KO-Runden = 0 Spiele → kein
Blocker)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pre_match_readiness as P


class TestWeatherBlocker(unittest.TestCase):
    def test_no_upcoming_not_blocker(self):
        # 0 anstehende Spiele → Wetter-Lücke ist nur Hinweis, failt den Lauf NICHT
        self.assertFalse(P.weather_is_blocker(False))

    def test_upcoming_is_blocker(self):
        # Spiele im Fenster → fehlendes Wetter ist echte Lücke (weather_signal kann nicht feuern)
        self.assertTrue(P.weather_is_blocker(True))


if __name__ == "__main__":
    unittest.main()
