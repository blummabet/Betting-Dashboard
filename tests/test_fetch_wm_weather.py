#!/usr/bin/env python3
"""test_fetch_wm_weather.py — KO-Wetter (30.06.2026, Lucas: „Wetter fehlt"): der Fetcher iterierte nur
groups → KO-Spiele bekamen nie Wetter. Helfer müssen Gruppen + bothResolved KO liefern; KO-Stadtnamen
müssen auf Koordinaten auflösen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fetch_wm_weather as W


class TestFixtureGather(unittest.TestCase):
    WM = {"groups": {"A": {"fixtures": [{"home": "GER", "away": "FRA", "venue": "X", "date": "2026-06-11"}]}},
          "koFixtures": [{"home": "ZAF", "away": "CAN", "venue": "Los Angeles (Inglewood)", "date": "2026-06-28"},
                         {"home": "GER", "away": None, "venue": "Boston", "date": "2026-07-04"}]}

    def test_group_fixtures(self):
        self.assertEqual(len(list(W._group_fixtures(self.WM))), 1)

    def test_ko_only_both_resolved(self):
        ko = list(W._ko_fixtures(self.WM))
        self.assertEqual(len(ko), 1)               # offene Paarung (away=None) übersprungen
        self.assertEqual(ko[0]["home"], "ZAF")


class TestKoVenueCoords(unittest.TestCase):
    def test_ko_city_names_resolve(self):
        # KO-Venue ist nur die Stadt → City-Fallback in _resolve_coords muss greifen
        for city in ["Monterrey", "Houston", "Los Angeles (Inglewood)", "Boston (Foxborough)",
                     "New York/New Jersey", "Dallas (Arlington)"]:
            self.assertIsNotNone(W._resolve_coords(city), f"{city} sollte Coords haben")


if __name__ == "__main__":
    unittest.main()
