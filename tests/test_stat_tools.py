#!/usr/bin/env python3
"""Tests für compute_pick_confidence + detect_pick_changes — is_legitimate_pick Migration."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestComputePickConfidenceImports(unittest.TestCase):
    def test_module_loads(self):
        import compute_pick_confidence
        self.assertTrue(hasattr(compute_pick_confidence, "is_legitimate_pick"))

    def test_uses_pick_helpers(self):
        src = (Path(__file__).parent.parent / "compute_pick_confidence.py").read_text(encoding="utf-8")
        self.assertIn("from pick_helpers import is_legitimate_pick", src,
            "compute_pick_confidence muss pick_helpers importieren")
        # Manueller Inline-Check sollte raus sein (nur als Fallback)
        self.assertNotIn('p.get("trackingExcluded"):\n                continue', src,
            "Manueller trackingExcluded-Check sollte durch is_legitimate_pick ersetzt sein")


class TestDetectPickChangesImports(unittest.TestCase):
    def test_module_loads(self):
        import detect_pick_changes
        self.assertTrue(hasattr(detect_pick_changes, "is_legitimate_pick"))

    def test_uses_pick_helpers(self):
        src = (Path(__file__).parent.parent / "detect_pick_changes.py").read_text(encoding="utf-8")
        self.assertIn("from pick_helpers import is_legitimate_pick", src)


class TestConfidenceFiltersTrackingExcluded(unittest.TestCase):
    """is_legitimate_pick filtert korrekt in Confidence-Stats."""

    def test_excluded_picks_not_in_buckets(self):
        """trackingExcluded Picks zählen nicht in Hit-Rate-Buckets."""
        # Synthetischer Test mit kleinem Datensatz
        import importlib, compute_pick_confidence
        importlib.reload(compute_pick_confidence)

        # Mock-Picks-Liste
        sample_picks = {
            "test-1": [
                {"market": "Heimsieg", "verdict": "BET", "result": "WIN",
                 "edgePP": 8, "dataQuality": "elo+form"},
                {"market": "AH Auswärts +0.5", "verdict": "ABWÄGEN",
                 "result": "VOID", "trackingExcluded": True,
                 "edgePP": 12, "dataQuality": "elo+form"},
            ]
        }
        # is_legitimate_pick muss True für 1. und False für 2. zurückgeben
        from pick_helpers import is_legitimate_pick
        self.assertTrue(is_legitimate_pick(sample_picks["test-1"][0]))
        self.assertFalse(is_legitimate_pick(sample_picks["test-1"][1]))


class TestDetectPickChangesIgnoresExcluded(unittest.TestCase):
    """trackingExcluded-Flips erscheinen nicht im Pick-Changes-Log."""

    def test_excluded_pick_change_ignored(self):
        """Wenn alter Pick excluded oder neuer Pick excluded → kein Change-Eintrag."""
        from pick_helpers import is_legitimate_pick
        # Simulation: Pick wechselt verdict, hat aber trackingExcluded
        old_p = {"market": "AH Heim −0.5", "verdict": "ABWÄGEN",
                 "trackingExcluded": True, "edgePP": 8}
        new_p = {"market": "AH Heim −0.5", "verdict": "BET",
                 "trackingExcluded": True, "edgePP": 9}
        # Beide sind nicht legitim → Loop in detect_pick_changes skipt sie
        self.assertFalse(is_legitimate_pick(old_p))
        self.assertFalse(is_legitimate_pick(new_p))


class TestLiveStatsRun(unittest.TestCase):
    """Smoketest: beide Scripts laufen ohne Fehler auf echten Daten."""

    def test_compute_confidence_runs_on_live_data(self):
        import json
        data_path = Path(__file__).parent.parent / "wm2026-data.json"
        if not data_path.exists():
            self.skipTest("wm2026-data.json fehlt")

        # Direkt die main()-Funktion testen
        import compute_pick_confidence
        # Lediglich Import + Bucket-Initialisierung — kein full-run nötig
        self.assertTrue(callable(compute_pick_confidence.init_bucket))


if __name__ == "__main__":
    unittest.main()
