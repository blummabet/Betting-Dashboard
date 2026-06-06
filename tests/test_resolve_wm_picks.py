#!/usr/bin/env python3
"""Tests für resolve_wm_picks.py — Konflikt-Filter konsistent mit UI."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestModuleImports(unittest.TestCase):
    """Sicherstellen dass refaktorierte Imports drin sind."""

    def test_module_loads(self):
        import resolve_wm_picks
        self.assertTrue(hasattr(resolve_wm_picks, "_select_hero_and_mark_conflicts"))

    def test_uses_pick_constants(self):
        src = (Path(__file__).parent.parent / "resolve_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("from pick_constants import", src,
            "resolve_wm_picks muss pick_constants importieren")
        self.assertNotIn("DIRECTION_MAP = {", src,
            "Inline DIRECTION_MAP darf nicht mehr existieren")
        self.assertNotIn("INCOMPATIBLE = {", src,
            "Inline INCOMPATIBLE darf nicht mehr existieren")

    def test_uses_pick_helpers(self):
        src = (Path(__file__).parent.parent / "resolve_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("from pick_helpers import hero_sort_key", src,
            "resolve_wm_picks muss hero_sort_key importieren (UI-Konsistenz)")


class TestSelectHeroAndMarkConflicts(unittest.TestCase):
    """Konflikt-Filter — Hero-Sort konsistent mit UI."""

    def setUp(self):
        from resolve_wm_picks import _select_hero_and_mark_conflicts
        self.fn = _select_hero_and_mark_conflicts

    def test_can_bih_scenario(self):
        """CAN-BIH ohne saferAlt: Hero = DNB Aus (höchste Edge). AH Heim = Konflikt."""
        picks = [
            {"market": "Auswärtssieg",      "verdict": "ABWÄGEN", "edgePP": 11},
            {"market": "DNB: Auswärtsteam", "verdict": "ABWÄGEN", "edgePP": 14},
            {"market": "AH Heim −0.5",      "verdict": "ABWÄGEN", "edgePP": 8},
        ]
        n_voids = self.fn(picks)
        self.assertEqual(n_voids, 1)
        # Genau AH Heim −0.5 wurde als VOID markiert
        ah_heim = next(p for p in picks if p["market"] == "AH Heim −0.5")
        self.assertEqual(ah_heim.get("result"), "VOID")
        self.assertTrue(ah_heim.get("trackingExcluded"))

    def test_usa_pry_with_safer_alt(self):
        """USA-PRY mit saferAlt: Hero = Über 1.5 (saferAlt). AH Aus +0.5 orthogonal.

        Vorher wurde mit alter Sort-Logic Heimsieg als Hero gewählt → AH Aus als Konflikt.
        Mit saferAlt-priorisierter Sort: Über 1.5 ist Hero → AH Aus ist orthogonal (over vs awayStrong).
        Konsistent mit UI: User wettet Hero, also Über 1.5, nicht AH Aus → kein realer Konflikt.
        """
        picks = [
            {"market": "Heimsieg",         "verdict": "BET", "edgePP": 12},
            {"market": "DNB: Heimteam",    "verdict": "ABWÄGEN", "edgePP": 6},
            {"market": "Über 1.5 Tore",    "verdict": "BET", "edgePP": 9, "saferAltFor": "Über 3.5 Tore"},
            {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN", "edgePP": 12},
        ]
        n_voids = self.fn(picks)
        # Hero = Über 1.5 (saferAlt). Konflikte: keine — over ist orthogonal zu allen homeStrong+awayStrong.
        self.assertEqual(n_voids, 0,
            "Hero = Über 1.5 (saferAlt) sollte keine homeStrong/awayStrong-Konflikte erzeugen")

    def test_empty_picks_returns_zero(self):
        self.assertEqual(self.fn([]), 0)

    def test_only_watch_picks_returns_zero(self):
        picks = [{"market": "Über 9.5 Ecken", "verdict": "WATCH", "edgePP": 0}]
        self.assertEqual(self.fn(picks), 0)

    def test_already_resolved_picks_not_re_marked(self):
        picks = [
            {"market": "Heimsieg",         "verdict": "BET",     "edgePP": 12},
            {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN", "edgePP": 12, "result": "WIN"},
        ]
        n_voids = self.fn(picks)
        # AH Aus war schon resolved (WIN) → nicht überschreiben
        self.assertEqual(n_voids, 0)
        ah_aus = next(p for p in picks if p["market"] == "AH Auswärts +0.5")
        self.assertEqual(ah_aus.get("result"), "WIN")


class TestRealWorldConsistency(unittest.TestCase):
    """Tracker und Renderer wählen denselben Hero — sonst Drift."""

    def test_tracker_uses_same_sort_as_renderer(self):
        """Hero-Sort in resolve_wm_picks identisch mit pick_helpers.select_hero."""
        from resolve_wm_picks import _select_hero_and_mark_conflicts
        from pick_helpers import select_hero
        picks = [
            {"market": "Heimsieg",         "verdict": "BET", "edgePP": 12, "odds": 2.01},
            {"market": "Über 1.5 Tore",    "verdict": "BET", "edgePP": 9, "odds": 1.40,
             "saferAltFor": "Über 3.5 Tore"},
            {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN", "edgePP": 12, "odds": 1.87},
        ]
        ui_hero = select_hero([dict(p) for p in picks])
        # Tracker run + check welcher Pick als Hero gewählt wurde
        picks_copy = [dict(p) for p in picks]
        _select_hero_and_mark_conflicts(picks_copy)
        # Wenn Hero = Über 1.5, dann ist Heimsieg/AH Aus NICHT excludiert (over orthogonal)
        # Wenn Hero = Heimsieg (alter Bug), wären andere als Konflikt markiert
        excluded = [p for p in picks_copy if p.get("trackingExcluded")]
        self.assertEqual(ui_hero["market"], "Über 1.5 Tore")
        self.assertEqual(len(excluded), 0,
            "Mit saferAlt-Hero (= UI-Hero) gibt's keinen Konflikt mit over-Direction")


if __name__ == "__main__":
    unittest.main()
