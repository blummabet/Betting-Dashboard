#!/usr/bin/env python3
"""Tests für resolve_wm_picks.py — Konflikt-Filter konsistent mit UI."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestKoResolution(unittest.TestCase):
    """KO-Picks (28.06.2026 Fix, Lucas): Key 'KO-R32-…' + Fixture in wm['koFixtures']."""

    def setUp(self):
        import resolve_wm_picks
        self.R = resolve_wm_picks

    def test_ko_pick_key_parses(self):
        self.assertEqual(self.R.parse_pick_key("KO-R32-ZAF-CAN"), ("KO", "R32", "ZAF", "CAN"))

    def test_group_pick_key_still_int(self):
        self.assertEqual(self.R.parse_pick_key("C-1-BRA-MAR"), ("C", 1, "BRA", "MAR"))

    def test_find_ko_fixture_in_kofixtures(self):
        wm = {"groups": {}, "koFixtures": [
            {"home": "ZAF", "away": "CAN", "round": "R32",
             "result": {"status": "FT", "home_score": 1, "away_score": 0}}]}
        fx = self.R.find_fixture(wm, "KO", "R32", "ZAF", "CAN")
        self.assertIsNotNone(fx)
        self.assertTrue(self.R.is_finished(fx))
        self.assertEqual(self.R.evaluate_pick("Unter 2.5 Tore",
                                              fx["result"]["home_score"], fx["result"]["away_score"]), "WIN")

    def test_find_ko_fixture_missing(self):
        self.assertIsNone(self.R.find_fixture({"koFixtures": []}, "KO", "R32", "ZAF", "CAN"))


class TestDNBEvaluation(unittest.TestCase):
    """DNB (Draw No Bet): Remis = VOID (Cashback), nicht LOSS. Bug 13.06.2026."""

    def setUp(self):
        import resolve_wm_picks
        self.ep = resolve_wm_picks.evaluate_pick

    def test_dnb_away_draw_is_void(self):
        # CAN-BIH 1:1 → DNB Auswärts muss VOID sein (war fälschlich LOSS)
        self.assertEqual(self.ep("DNB: Auswärtsteam", 1, 1), "VOID")

    def test_dnb_home_draw_is_void(self):
        self.assertEqual(self.ep("DNB: Heimteam", 2, 2), "VOID")

    def test_dnb_win_loss(self):
        self.assertEqual(self.ep("DNB: Auswärtsteam", 0, 2), "WIN")
        self.assertEqual(self.ep("DNB: Auswärtsteam", 2, 0), "LOSS")
        self.assertEqual(self.ep("DNB: Heimteam", 2, 0), "WIN")
        self.assertEqual(self.ep("DNB: Heimteam", 0, 2), "LOSS")

    def test_plain_1x2_unaffected(self):
        # Echte 1X2-Märkte dürfen NICHT vom DNB-Fix berührt werden
        self.assertEqual(self.ep("Auswärtssieg", 1, 1), "LOSS")
        self.assertEqual(self.ep("Auswärtssieg", 0, 1), "WIN")
        self.assertEqual(self.ep("Heimsieg", 2, 0), "WIN")

    def test_double_chance(self):
        self.assertEqual(self.ep("Doppelte Chance: X2", 1, 1), "WIN")
        self.assertEqual(self.ep("Doppelte Chance: 1X", 0, 3), "LOSS")


class TestAsianHandicap(unittest.TestCase):
    """AH-Auflösung inkl. Viertel-Linien (Push/Half) + Whole-Line-Push. Build 13.06.2026."""

    def setUp(self):
        import resolve_wm_picks
        self.ep = resolve_wm_picks.evaluate_pick

    def test_half_lines(self):
        self.assertEqual(self.ep("AH Heim −0.5", 1, 0), "WIN")
        self.assertEqual(self.ep("AH Heim −0.5", 1, 1), "LOSS")
        self.assertEqual(self.ep("AH Auswärts +0.5", 1, 1), "WIN")   # Remis → Away +0.5 gewinnt
        self.assertEqual(self.ep("AH Auswärts +0.5", 2, 1), "LOSS")

    def test_whole_lines_push(self):
        self.assertEqual(self.ep("AH Heim −1.0", 1, 0), "VOID")      # exakt 1 → Push
        self.assertEqual(self.ep("AH Heim −1.0", 2, 0), "WIN")
        self.assertEqual(self.ep("AH Auswärts +1.0", 2, 1), "VOID")  # Heim by 1 → Push
        self.assertEqual(self.ep("AH Heim −2.0", 2, 0), "VOID")

    def test_quarter_lines(self):
        self.assertEqual(self.ep("AH Heim −0.75", 1, 0), "WIN")      # by 1 → Half-Win → WIN
        self.assertEqual(self.ep("AH Heim −0.75", 1, 1), "LOSS")
        self.assertEqual(self.ep("AH Auswärts +0.75", 2, 1), "LOSS") # Heim by 1 → Half-Loss → LOSS

    def test_wide_lines(self):
        self.assertEqual(self.ep("AH Heim −1.5", 2, 0), "WIN")
        self.assertEqual(self.ep("AH Heim −1.5", 1, 0), "LOSS")
        self.assertEqual(self.ep("AH Auswärts +2.0", 2, 1), "WIN")   # Underdog-Absicherung

    def test_quarter_stake_factor(self):
        import resolve_wm_picks as r
        # Half-Win (Heim −0.75, Sieg mit genau 1) → WIN, halber Stake
        self.assertEqual(r._ah_result("ah heim −0.75", 1), ("WIN", 0.5))
        # Half-Loss (Auswärts +0.75, Heim by 1) → LOSS, halber Stake
        self.assertEqual(r._ah_result("ah auswärts +0.75", 1), ("LOSS", 0.5))
        # Volle Linie → Faktor 1.0
        self.assertEqual(r._ah_result("ah heim −0.5", 1), ("WIN", 1.0))
        # _apply_ah_stake_factor setzt das Feld am Pick
        p = {"market": "AH Heim −0.75", "result": "WIN"}
        r._apply_ah_stake_factor(p, 1, 0)
        self.assertEqual(p.get("resultStakeFactor"), 0.5)
        # Nicht-AH-Pick bekommt keinen Faktor
        p2 = {"market": "Über 2.5 Tore", "result": "WIN"}
        r._apply_ah_stake_factor(p2, 3, 1)
        self.assertNotIn("resultStakeFactor", p2)


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
