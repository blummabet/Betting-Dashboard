#!/usr/bin/env python3
"""test_ko_learning_coverage.py — K.-o.-Runden im Lern-Loop (04.07.2026, Lucas: „seit KO-Modus
feuert der Aufstellungs-Check nie + werden die 1/16-Picks als lucky/unlucky bewertet?").

Zwei KO-Lücken, beide „nur groups statt koFixtures":
  1) fetch_wm_lineups._load_wm_fixtures sammelte KO-Spiele nie → keine KO-Aufstellungen → lineup_signal
     konnte in der K.-o.-Phase nie feuern.
  2) build_signal_ledger._build_stats_lookup kannte nur groups → KO-Picks bekamen nie ein
     Prozess-Verdict (verdient/Pech) → verlorene-aber-verdiente KO-Picks voll bestraft."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLineupFetcherKO(unittest.TestCase):
    def test_ko_fixtures_werden_gesammelt(self):
        import fetch_wm_lineups as F
        wm = {
            "groups": {"A": {"fixtures": [
                {"home": "MEX", "away": "ZAF", "date": "2026-06-11", "matchday": 1}]}},
            "koFixtures": [
                {"home": "BRA", "away": "JPN", "round": "R32", "date": "2026-06-29",
                 "kickoff": "2026-06-29T17:00:00Z"},
                {"home": "FRA", "away": "SWE", "round": "R32",     # date fehlt → aus kickoff
                 "kickoff": "2026-06-30T21:00:00Z"},
                {"home": None, "away": None, "round": "R16"},       # unaufgelöst → raus
            ],
        }
        import json, tempfile, os
        tf = Path(tempfile.mktemp(suffix=".json"))
        tf.write_text(json.dumps(wm), encoding="utf-8")
        _orig = F.WM_FILE
        F.WM_FILE = tf
        try:
            fx = F._load_wm_fixtures()
        finally:
            F.WM_FILE = _orig
            tf.unlink()
        keys = {f["match_key"] for f in fx}
        self.assertIn("BRA-JPN", keys)
        self.assertIn("FRA-SWE", keys)   # date aus kickoff abgeleitet
        ko = [f for f in fx if f["group"] == "KO"]
        self.assertEqual(len(ko), 2)     # unaufgelöstes Spiel nicht dabei


class TestLedgerKOStats(unittest.TestCase):
    def _wm(self):
        stats = {"homeXg": 2.1, "awayXg": 0.5, "xgTotal": 2.6, "xgSource": "sim"}
        return {
            "groups": {},
            "koFixtures": [
                {"home": "BRA", "away": "JPN", "round": "R32",
                 "result": {"status": "FT", "home_score": 2, "away_score": 1, "stats": stats}},
            ],
            "picks": {
                "KO-R32-BRA-JPN": [
                    {"verdict": "BET", "market": "Heimsieg", "result": "WIN",
                     "signals": [{"name": "steam_move", "score": 3.0}]},
                ]
            },
        }

    def test_ko_stats_im_lookup(self):
        import build_signal_ledger as B
        lookup = B._build_stats_lookup(self._wm())
        self.assertIn("KO-R32-BRA-JPN", lookup)

    def test_ko_pick_bekommt_prozess_verdict(self):
        import build_signal_ledger as B
        obs = B.collect_observations(self._wm())
        self.assertEqual(len(obs), 1)
        # xG klar Heim (2.1 vs 0.5) + Heimsieg-WIN → verdient/JUSTIFIED, kein leeres Verdict
        self.assertIn("processVerdict", obs[0])
        self.assertTrue(obs[0]["processVerdict"])


if __name__ == "__main__":
    unittest.main()
