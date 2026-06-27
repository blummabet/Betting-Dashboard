#!/usr/bin/env python3
"""test_liga_leagues_guard.py — check_liga_leagues_populated (26.06.2026): leere Liga-Gruppe
(z.B. ESP/GER ohne Spielplan) wird gemeldet; volle Gruppen grün; WM übersprungen."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(profile, groups):
    return W.IntegrityCtx({"_meta": {"profile": profile}, "groups": groups}, {}, {}, {})


class TestGuard(unittest.TestCase):
    def test_flags_empty_league(self):
        groups = {"ENG": {"teams": [{"id": "1"}], "fixtures": [{"home": "1", "away": "2"}]},
                  "ESP": {"teams": [], "fixtures": []}}
        res = W.check_liga_leagues_populated(_ctx("liga_default", groups))
        self.assertFalse(res["ok"])
        self.assertIn("ESP", res["failures"][0])

    def test_all_populated_passes(self):
        groups = {"ENG": {"teams": [{"id": "1"}], "fixtures": [{"home": "1", "away": "2"}]}}
        self.assertTrue(W.check_liga_leagues_populated(_ctx("liga_default", groups))["ok"])

    def test_wm_skipped(self):
        groups = {"A": {"teams": [], "fixtures": []}}
        self.assertIsNone(W.check_liga_leagues_populated(_ctx("wm2026", groups)))


if __name__ == "__main__":
    unittest.main()
