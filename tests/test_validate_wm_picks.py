#!/usr/bin/env python3
"""Tests für validate_wm_picks.py — Cross-Market-Check + Sanity-Checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestModuleImports(unittest.TestCase):
    """Sicherstellen dass refaktorierte Imports drin sind."""

    def test_module_loads(self):
        import validate_wm_picks
        self.assertTrue(hasattr(validate_wm_picks, "validate_cross_market"))

    def test_uses_pick_constants(self):
        src = (Path(__file__).parent.parent / "validate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("from pick_constants import", src,
            "validate_wm_picks muss pick_constants importieren")
        self.assertNotIn("DIRECTION_MAP = {", src,
            "Inline DIRECTION_MAP darf nicht mehr existieren")
        self.assertNotIn("INCOMPATIBLE = {", src,
            "Inline INCOMPATIBLE darf nicht mehr existieren")

    def test_uses_is_legitimate_pick(self):
        src = (Path(__file__).parent.parent / "validate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("is_legitimate_pick", src,
            "validate_wm_picks muss is_legitimate_pick verwenden")


class TestCrossMarketValidator(unittest.TestCase):
    """E_CROSS_MARKET feuert bei BET-BET-Konflikten."""

    def setUp(self):
        from validate_wm_picks import validate_cross_market
        self.fn = validate_cross_market

    def test_no_conflict_for_orthogonal_bets(self):
        picks = [
            {"market": "Heimsieg",      "verdict": "BET"},
            {"market": "Über 2.5 Tore", "verdict": "BET"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["level"] == "error"]
        self.assertEqual(len(errors), 0,
            "Heimsieg + Über sind orthogonal — kein Error")

    def test_conflict_for_incompatible_bets(self):
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "BET"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 1,
            "Heimsieg + AH Aus = unvereinbar → Error muss feuern")

    def test_no_conflict_for_abwaegen(self):
        """ABWÄGEN-Picks lösen keine Errors aus (nur BET wird geprüft)."""
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "ABWÄGEN"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 0)

    def test_tracking_excluded_ignored(self):
        """trackingExcluded BET-Picks werden nicht als Konflikt-Quelle gewertet."""
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "BET", "trackingExcluded": True},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 0,
            "trackingExcluded Pick wird ignoriert — kein Konflikt-Error")


class TestLiveDataValidation(unittest.TestCase):
    """Smoketest auf echten WM-Daten — sollte sauber laufen."""

    def test_live_picks_validate_clean(self):
        import json
        from validate_wm_picks import validate_pick, validate_cross_market

        data_path = Path(__file__).parent.parent / "wm2026-data.json"
        if not data_path.exists():
            self.skipTest("wm2026-data.json fehlt")

        with open(data_path, encoding="utf-8") as f:
            wm = json.load(f)

        issues = []
        for mk, plist in wm.get("picks", {}).items():
            if not isinstance(plist, list): continue
            for p in plist:
                validate_pick(mk, p, wm, issues)
            validate_cross_market(mk, plist, issues)

        errors = [i for i in issues if i["level"] == "error"]
        # Generator sollte alle Konflikte schon abgefangen haben → 0 Errors
        self.assertEqual(len(errors), 0,
            f"Validator hat {len(errors)} Errors gefunden — Generator-Bug?")


if __name__ == "__main__":
    unittest.main()
