#!/usr/bin/env python3
"""Tests für pick_helpers.py — is_legitimate, hero_sort, conflict-finding."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pick_helpers


class TestIsLegitimatePick(unittest.TestCase):
    """is_legitimate_pick — Single Source of Truth für 'Pick gilt?'."""

    def test_normal_pick_is_legitimate(self):
        p = {"market": "Heimsieg", "verdict": "BET", "edgePP": 8}
        self.assertTrue(pick_helpers.is_legitimate_pick(p))

    def test_tracking_excluded_is_not_legitimate(self):
        p = {"market": "Heimsieg", "verdict": "BET", "trackingExcluded": True}
        self.assertFalse(pick_helpers.is_legitimate_pick(p))

    def test_none_is_not_legitimate(self):
        self.assertFalse(pick_helpers.is_legitimate_pick(None))

    def test_empty_dict_is_legitimate(self):
        # Leerer dict zählt als legitim — der Caller muss verdict prüfen
        self.assertTrue(pick_helpers.is_legitimate_pick({}))

    def test_non_dict_is_not_legitimate(self):
        self.assertFalse(pick_helpers.is_legitimate_pick("not a dict"))
        self.assertFalse(pick_helpers.is_legitimate_pick(42))

    def test_resolved_pick_is_still_legitimate(self):
        """Auch nach WIN/LOSS bleibt der Pick legitim."""
        p = {"market": "Heimsieg", "verdict": "BET", "result": "WIN", "pnl": 10}
        self.assertTrue(pick_helpers.is_legitimate_pick(p))


class TestHeroSort(unittest.TestCase):
    """Hero-Sort: saferAlt > BET > Edge desc."""

    def test_safer_alt_wins_over_bet(self):
        bet_no_safer = {"market": "DNB: Auswärtsteam", "verdict": "BET",
                        "edgePP": 13, "odds": 3.14}
        abw_safer    = {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN",
                        "edgePP": 14, "odds": 1.88, "saferAltFor": "DNB: Auswärtsteam"}
        picks = [bet_no_safer, abw_safer]
        hero = pick_helpers.select_hero(picks)
        self.assertEqual(hero["market"], "AH Auswärts +0.5",
            "saferAlt-Pick muss Hero werden, auch wenn ABWÄGEN")

    def test_bet_wins_over_abwaegen_when_no_safer(self):
        bet = {"market": "Heimsieg", "verdict": "BET", "edgePP": 8}
        abw = {"market": "Über 2.5 Tore", "verdict": "ABWÄGEN", "edgePP": 12}
        hero = pick_helpers.select_hero([bet, abw])
        self.assertEqual(hero["market"], "Heimsieg")

    def test_higher_edge_wins_within_same_class(self):
        bet_a = {"market": "Heimsieg",     "verdict": "BET", "edgePP": 8}
        bet_b = {"market": "Auswärtssieg", "verdict": "BET", "edgePP": 11}
        hero = pick_helpers.select_hero([bet_a, bet_b])
        self.assertEqual(hero["edgePP"], 11)

    def test_tracking_excluded_skipped_in_hero(self):
        excluded_bet = {"market": "Heimsieg", "verdict": "BET", "edgePP": 14,
                        "trackingExcluded": True}
        valid_abw    = {"market": "Auswärtssieg", "verdict": "ABWÄGEN", "edgePP": 8}
        hero = pick_helpers.select_hero([excluded_bet, valid_abw])
        self.assertEqual(hero["market"], "Auswärtssieg",
            "trackingExcluded Pick darf nicht Hero werden")

    def test_empty_list_returns_none(self):
        self.assertIsNone(pick_helpers.select_hero([]))

    def test_only_watch_returns_none(self):
        watch = {"market": "Über 9.5 Ecken", "verdict": "WATCH", "edgePP": 0}
        self.assertIsNone(pick_helpers.select_hero([watch]))


class TestFindConflicts(unittest.TestCase):
    """find_picks_conflicting_with_hero."""

    def test_finds_classic_conflict(self):
        hero = {"market": "Heimsieg",         "verdict": "BET"}
        sec  = {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN"}
        conflicts = pick_helpers.find_picks_conflicting_with_hero([hero, sec], hero)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["market"], "AH Auswärts +0.5")

    def test_no_conflict_for_orthogonal(self):
        hero = {"market": "Heimsieg",      "verdict": "BET"}
        sec  = {"market": "Über 2.5 Tore", "verdict": "BET"}
        conflicts = pick_helpers.find_picks_conflicting_with_hero([hero, sec], hero)
        self.assertEqual(len(conflicts), 0,
            "Heim + Über sind orthogonal, kein Konflikt")

    def test_tracking_excluded_not_flagged_again(self):
        """Bereits excludierte Picks werden nicht erneut als Konflikt erkannt."""
        hero       = {"market": "Heimsieg", "verdict": "BET"}
        already    = {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN",
                      "trackingExcluded": True}
        conflicts = pick_helpers.find_picks_conflicting_with_hero([hero, already], hero)
        self.assertEqual(len(conflicts), 0,
            "Bereits excludierte Picks sollen nicht doppelt geflaggt werden")

    def test_no_hero_returns_empty(self):
        picks = [{"market": "Heimsieg", "verdict": "BET"}]
        self.assertEqual(pick_helpers.find_picks_conflicting_with_hero(picks, None), [])


class TestRealWorldScenarios(unittest.TestCase):
    """Reale Bug-Szenarien die wir heute gefixt haben — als Regressionsschutz."""

    def test_can_bih_scenario(self):
        """CAN-BIH: DNB Aus + AH Heim −0.5 + Auswärtssieg.
        Hero muss DNB Aus sein, AH Heim −0.5 muss als Konflikt erkannt werden."""
        picks = [
            {"market": "Auswärtssieg",      "verdict": "ABWÄGEN", "edgePP": 11, "odds": 4.61},
            {"market": "DNB: Auswärtsteam", "verdict": "ABWÄGEN", "edgePP": 14, "odds": 3.44},
            {"market": "AH Heim −0.5",      "verdict": "ABWÄGEN", "edgePP": 8,  "odds": 1.78},
        ]
        hero = pick_helpers.select_hero(picks)
        self.assertEqual(hero["market"], "DNB: Auswärtsteam",
            "Höchste Edge unter ABWÄGEN ohne saferAlt = DNB Aus")
        conflicts = pick_helpers.find_picks_conflicting_with_hero(picks, hero)
        conflict_markets = {c["market"] for c in conflicts}
        self.assertIn("AH Heim −0.5", conflict_markets,
            "AH Heim −0.5 muss als Konflikt zu DNB Aus erkannt werden")
        self.assertNotIn("Auswärtssieg", conflict_markets,
            "Auswärtssieg ist kompatibel mit DNB Aus (beide awayStrong)")

    def test_swe_tun_scenario(self):
        """SWE-TUN: DNB Aus + AH Aus +0.5 (safer-alt).
        Hero muss AH Aus +0.5 sein (saferAlt), nicht das DNB BET."""
        picks = [
            {"market": "Auswärtssieg",      "verdict": "BET",     "edgePP": 11, "odds": 4.32},
            {"market": "DNB: Auswärtsteam", "verdict": "BET",     "edgePP": 13, "odds": 3.14},
            {"market": "AH Auswärts +0.5",  "verdict": "ABWÄGEN", "edgePP": 14, "odds": 1.88,
             "saferAltFor": "DNB: Auswärtsteam"},
            {"market": "Über 1.5 Tore",     "verdict": "ABWÄGEN", "edgePP": 15, "odds": 1.35},
        ]
        hero = pick_helpers.select_hero(picks)
        self.assertEqual(hero["market"], "AH Auswärts +0.5",
            "saferAlt-Pick muss Hero werden auch wenn BETs vorhanden")


if __name__ == "__main__":
    unittest.main()
