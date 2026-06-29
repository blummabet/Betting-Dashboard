#!/usr/bin/env python3
"""test_cocobet_dataset.py — Single-Source-Dataset-Auflösung (26.06.2026 Konsolidierung)."""
import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


def _reload(dataset=None, profile=None, season=None):
    for k, v in (("COCOBET_DATASET", dataset), ("COCOBET_PROFILE", profile), ("LIGA_SEASON", season)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import cocobet_dataset as D
    return importlib.reload(D)


class TestDataset(unittest.TestCase):
    def tearDown(self):
        _reload(None, None, None)   # Env sauber zurücksetzen

    def test_wm_default(self):
        D = _reload(None)
        self.assertFalse(D.is_liga())
        self.assertEqual(D.active_dataset(), "wm")
        self.assertEqual(D.data_file().name, "wm2026-data.json")
        self.assertEqual(D.prefix(), "")
        self.assertEqual(D.active_profile(), "wm2026")

    def test_liga(self):
        D = _reload("liga")
        self.assertTrue(D.is_liga())
        self.assertEqual(D.data_file().name, "liga-data.json")
        self.assertEqual(D.prefix(), "liga_")
        self.assertEqual(D.active_profile(), "liga_default")
        self.assertEqual(D.file("signal_weights.json", "liga_signal_weights.json").name,
                         "liga_signal_weights.json")

    def test_leagues_single_source(self):
        D = _reload("liga")
        self.assertEqual(D.leagues(), {"ENG": 39, "ESP": 140, "GER": 78, "ITA": 135, "FRA": 61})

    def test_mls_dataset(self):
        # 29.06.2026 (Lucas): MLS als 3. Datensatz. Name aus liga-Schema abgeleitet (liga→mls).
        D = _reload("mls")
        self.assertTrue(D.is_liga())                       # non-WM → Klub-Pfade greifen
        self.assertEqual(D.active_dataset(), "mls")
        self.assertEqual(D.data_file().name, "mls-data.json")
        self.assertEqual(D.prefix(), "mls_")
        self.assertEqual(D.active_profile(), "mls_default")
        self.assertEqual(D.leagues(), {"MLS": 253})
        self.assertEqual(D.file("wm_streaks.json", "liga_streaks.json").name, "mls_streaks.json")

    def test_mls_profile_env_override(self):
        D = _reload("mls", "custom_profile")
        self.assertEqual(D.active_profile(), "custom_profile")

    def test_current_season(self):
        D = _reload(None)
        self.assertEqual(D.current_season(datetime(2026, 7, 1, tzinfo=timezone.utc)), 2026)
        self.assertEqual(D.current_season(datetime(2026, 3, 1, tzinfo=timezone.utc)), 2025)

    def test_season_env_override(self):
        D = _reload("liga", None, "2024")
        self.assertEqual(D.season(), 2024)


if __name__ == "__main__":
    unittest.main()
