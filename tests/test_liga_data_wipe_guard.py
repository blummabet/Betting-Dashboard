#!/usr/bin/env python3
"""
test_liga_data_wipe_guard.py — Wipe-Schutz in build_liga_data (12.07.2026).

Bug: Lucas' API-Zugang lief über Nacht ab → /fixtures gab 0 Ergebnisse → build_liga_data
überschrieb mls-data.json mit LEEREN groups (0 Teams/0 Fixtures). Die Liga-Cards-Ansicht
merged mls-data.json mit → verwaiste Picks (292 Keys) auf nicht-existente Fixtures/Teams →
die ganze National-Cards-Ansicht kippte. Ein API-Ausfall darf NIE Daten vernichten.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

# 13.07.2026 — hier stand `os.environ.setdefault("COCOBET_DATASET", "liga")` auf MODUL-Ebene.
# Das wirkt schon beim EINSAMMELN der Tests, also bevor irgendein Test läuft: die halbe Suite lief
# danach im Liga-Datensatz. Solange alle Guards ihre Dateien hart als "wm_*.json" verdrahtet hatten,
# fiel das nicht auf. Als die Guards dataset-aware wurden, kippten schlagartig 13 völlig
# unbeteiligte Tests (book_health, smart_money, ko_apif …) — isoliert waren sie grün.
#
# merge_groups_preserve ist eine reine Funktion und braucht den Datensatz gar nicht.
# Env-Isolation je Test kommt jetzt zentral aus tests/conftest.py.

from build_liga_data import merge_groups_preserve


def _g(teams=0, fixtures=0):
    return {"teams": [{"id": str(i)} for i in range(teams)],
            "fixtures": [{"home": "1", "away": "2"} for _ in range(fixtures)]}


class TestWipeGuard(unittest.TestCase):
    def test_empty_api_does_not_wipe_existing(self):
        old = {"MLS": _g(30, 400)}
        new = {"MLS": _g(0, 0)}            # API-Ausfall
        merged, kept = merge_groups_preserve(old, new)
        self.assertEqual(kept, ["MLS"])
        self.assertEqual(len(merged["MLS"]["fixtures"]), 400)   # alter Stand erhalten
        self.assertEqual(len(merged["MLS"]["teams"]), 30)

    def test_partial_outage_keeps_only_failed_league(self):
        old = {"ENG": _g(20, 380), "ESP": _g(20, 380)}
        new = {"ENG": _g(20, 380), "ESP": _g(0, 0)}   # nur ESP fiel aus
        merged, kept = merge_groups_preserve(old, new)
        self.assertEqual(kept, ["ESP"])
        self.assertEqual(len(merged["ESP"]["fixtures"]), 380)   # ESP gerettet
        self.assertEqual(len(merged["ENG"]["fixtures"]), 380)   # ENG normal übernommen

    def test_missing_league_in_build_is_kept(self):
        old = {"ENG": _g(20, 380), "MLS": _g(30, 400)}
        new = {"ENG": _g(20, 380)}          # MLS fehlt im Build komplett
        merged, kept = merge_groups_preserve(old, new)
        self.assertIn("MLS", merged)
        self.assertEqual(len(merged["MLS"]["fixtures"]), 400)

    def test_good_build_replaces_normally(self):
        old = {"ENG": _g(20, 380)}
        new = {"ENG": _g(20, 400)}          # frischer Build mit mehr Fixtures
        merged, kept = merge_groups_preserve(old, new)
        self.assertEqual(kept, [])
        self.assertEqual(len(merged["ENG"]["fixtures"]), 400)

    def test_first_run_empty_old(self):
        merged, kept = merge_groups_preserve({}, {"ENG": _g(20, 380)})
        self.assertEqual(kept, [])
        self.assertEqual(len(merged["ENG"]["fixtures"]), 380)


if __name__ == "__main__":
    unittest.main()
