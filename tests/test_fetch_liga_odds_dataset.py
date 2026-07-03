#!/usr/bin/env python3
"""test_fetch_liga_odds_dataset.py — fetch_liga_odds MUSS dataset-aware sein (01.07.2026, Lucas:
„holen wir MLS-Odds für Sharp Radar/Steam/CLV?"). Bei der Dataset-Migration wurde der Odds-Fetcher
übersehen (LIGA_FILE/LIGA_HISTORY hart auf liga-*) → der MLS-Lauf schrieb ins Liga-File, die MLS-
Konsumenten (mls-odds-history.json) blieben leer. Dieser Test friert die dataset-aware Auflösung ein."""
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _paths_for(dataset: str):
    prev = os.environ.get("COCOBET_DATASET")
    os.environ["COCOBET_DATASET"] = dataset
    try:
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import fetch_liga_odds
        importlib.reload(fetch_liga_odds)
        return (os.path.basename(fetch_liga_odds.LIGA_FILE),
                os.path.basename(fetch_liga_odds.LIGA_HISTORY))
    finally:
        if prev is None:
            os.environ.pop("COCOBET_DATASET", None)
        else:
            os.environ["COCOBET_DATASET"] = prev


class TestFetchLigaOddsDatasetAware(unittest.TestCase):
    def test_liga(self):
        self.assertEqual(_paths_for("liga"), ("liga-data.json", "liga-odds-history.json"))

    def test_mls(self):
        self.assertEqual(_paths_for("mls"), ("mls-data.json", "mls-odds-history.json"))

    def test_not_hardcoded(self):
        src = (Path(__file__).parent.parent / "fetch_liga_odds.py").read_text(encoding="utf-8")
        # Kein hartcodiertes liga-*.json mehr für die zwei zentralen Pfade
        self.assertIn("D.data_file()", src)
        self.assertIn('D.file("wm2026-odds-history.json", "liga-odds-history.json")', src)

    @classmethod
    def tearDownClass(cls):
        # Module wieder auf Default-Dataset zurücksetzen, damit andere Tests nicht kontaminiert werden.
        _paths_for("liga")


if __name__ == "__main__":
    unittest.main()
