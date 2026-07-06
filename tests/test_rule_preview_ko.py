#!/usr/bin/env python3
"""test_rule_preview_ko.py — Regel-Preview muss KO-Spiele überstehen (06.07.2026, Lucas).
Bug: `matchday >= 3` crashte bei KO (matchday = Runden-String "R16") → KEINE KO-Previews;
zudem iterierte main() nur groups. Beides gefixt."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import generate_wm_rule_preview as R


class TestRulePreviewKO(unittest.TestCase):
    def _info(self, matchday, group="KO"):
        return {"home": "Portugal", "away": "Spanien", "date": "2026-07-06", "group": group,
                "matchday": matchday, "homeElo": 1900, "awayElo": 1950, "upsetScore": 3,
                "picks": [], "homeForm": None, "awayForm": None, "h2h": None, "coHostBonus": False}

    def test_ko_string_matchday_kein_crash(self):
        # Vorher: TypeError '>=' str vs int
        full, tg = R.build_preview(self._info("R16"))
        self.assertTrue(full and tg)
        self.assertIn("Achtelfinale", full)

    def test_ko_verschiedene_runden(self):
        for code, label in [("R32", "Sechzehntelfinale"), ("QF", "Viertelfinale"),
                            ("SF", "Halbfinale"), ("F", "Finale")]:
            full, _ = R.build_preview(self._info(code))
            self.assertIn(label, full)

    def test_gruppe_int_matchday_weiter_ok(self):
        full, tg = R.build_preview(self._info(3, group="A"))
        self.assertTrue(full and tg)
        self.assertIn("Spieltag 3", full)


if __name__ == "__main__":
    unittest.main()
