#!/usr/bin/env python3
"""Tests für pick_constants.py — Direction-Map + Incompatible-Set."""
import json
import os
import sys
import unittest
from pathlib import Path

# Repo-Root in den path damit `import pick_constants` funktioniert
sys.path.insert(0, str(Path(__file__).parent.parent))

import pick_constants


class TestDirectionMap(unittest.TestCase):
    """Validiert dass DIRECTION_MAP konsistent + vollständig ist."""

    def test_all_markets_have_valid_direction(self):
        """Jeder Markt-Wert muss eine bekannte Direction sein."""
        valid_directions = {
            "homeStrong", "homeBias", "awayStrong", "awayBias",
            "drawOnly", "decisive", "over", "under",
        }
        for market, direction in pick_constants.DIRECTION_MAP.items():
            self.assertIn(direction, valid_directions,
                f"Market '{market}' hat ungültige Direction '{direction}'")

    def test_minimum_market_coverage(self):
        """Stelle sicher dass alle Standard-Markttypen drin sind."""
        required = [
            "Heimsieg", "Auswärtssieg", "Unentschieden",
            "Über 2.5 Tore", "Unter 2.5 Tore",
            "Beide Teams treffen",
            "Doppelte Chance — 1X", "Doppelte Chance — X2",
            "AH Heim −0.5", "AH Auswärts +0.5",
            "DNB: Heimteam", "DNB: Auswärtsteam",
        ]
        for m in required:
            self.assertIn(m, pick_constants.DIRECTION_MAP,
                f"Pflicht-Markt '{m}' fehlt in DIRECTION_MAP")

    def test_get_pick_direction_returns_correct_value(self):
        self.assertEqual(pick_constants.get_pick_direction("Heimsieg"), "homeStrong")
        self.assertEqual(pick_constants.get_pick_direction("Unter 2.5 Tore"), "under")
        self.assertIsNone(pick_constants.get_pick_direction("Foo Bar"))
        self.assertIsNone(pick_constants.get_pick_direction(None))
        self.assertIsNone(pick_constants.get_pick_direction(""))


class TestIncompatibleSet(unittest.TestCase):
    """Validiert INCOMPATIBLE-Direction-Paare."""

    def test_symmetric_pairs(self):
        """Wenn (A,B) inkompatibel ist, muss auch (B,A) inkompatibel sein."""
        for (a, b) in list(pick_constants.INCOMPATIBLE):
            self.assertIn((b, a), pick_constants.INCOMPATIBLE,
                f"INCOMPATIBLE ist nicht symmetrisch: ({a},{b}) drin, ({b},{a}) fehlt")

    def test_classic_conflicts(self):
        """Bekannte Konflikte müssen erkannt werden."""
        f = pick_constants.are_directions_incompatible
        self.assertTrue(f("homeStrong", "awayStrong"))   # Heim vs Aus
        self.assertTrue(f("over", "under"))               # Über vs Unter
        self.assertTrue(f("homeStrong", "drawOnly"))      # Heim vs Draw

    def test_compatible_pairs(self):
        """Gleiche/orthogonale Directions sind kompatibel."""
        f = pick_constants.are_directions_incompatible
        self.assertFalse(f("homeStrong", "homeStrong"))   # gleich
        self.assertFalse(f("homeStrong", "over"))         # orthogonal (Heim + Tore)
        self.assertFalse(f("awayStrong", "under"))        # orthogonal
        self.assertFalse(f("homeStrong", "homeBias"))     # gleiche Richtung

    def test_none_handling(self):
        f = pick_constants.are_directions_incompatible
        self.assertFalse(f(None, "homeStrong"))
        self.assertFalse(f("homeStrong", None))
        self.assertFalse(f(None, None))


class TestJsonMirror(unittest.TestCase):
    """Validiert dass pick_constants.json mit pick_constants.py übereinstimmt."""

    def setUp(self):
        path = Path(__file__).parent.parent / "pick_constants.json"
        if not path.exists():
            self.skipTest("pick_constants.json nicht generiert — `python pick_constants.py --dump-json`")
        with open(path) as f:
            self.mirror = json.load(f)

    def test_direction_map_matches(self):
        self.assertEqual(self.mirror["DIRECTION_MAP"], pick_constants.DIRECTION_MAP,
            "JSON-Mirror DIRECTION_MAP ≠ Python DIRECTION_MAP — `python pick_constants.py --dump-json > pick_constants.json` ausführen")

    def test_incompatible_pairs_match(self):
        json_pairs = {tuple(p) for p in self.mirror["INCOMPATIBLE"]}
        self.assertEqual(json_pairs, pick_constants.INCOMPATIBLE,
            "JSON-Mirror INCOMPATIBLE ≠ Python INCOMPATIBLE — Mirror regenerieren")


if __name__ == "__main__":
    unittest.main()
