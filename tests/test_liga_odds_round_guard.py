#!/usr/bin/env python3
"""test_liga_odds_round_guard.py — check_liga_odds_round_sane (Bug 26.06.2026 „Spieltag 1 dann 20").
27.07.2026 datums-basiert: Odds auf fernem Termin (Hin/Rück-Fehlmatch) → Guard schlägt an; nahe
Termine → grün; WM → skip; MLS mit unsynchronen Runden aber nahen Terminen → KEIN Fehlalarm."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(profile, fixtures, odds):
    wm = {"_meta": {"profile": profile},
          "groups": {"ENG": {"fixtures": fixtures}}, "odds": odds}
    return W.IntegrityCtx(wm, {}, {}, {})


FX = [
    {"home": "1", "away": "2", "matchday": 1, "date": "2026-08-15", "result": None},
    {"home": "3", "away": "4", "matchday": 1, "date": "2026-08-16", "result": None},
    {"home": "2", "away": "1", "matchday": 31, "date": "2027-02-20", "result": None},   # Rückspiel Monate später
]


class TestGuard(unittest.TestCase):
    def test_flags_far_date_odds(self):
        odds = {"1-2": {"hw": 1.8}, "2-1": {"hw": 1.9}}  # naher Termin + fälschlich fernes Rückspiel
        res = W.check_liga_odds_round_sane(_ctx("liga_default", FX, odds))
        self.assertFalse(res["ok"])
        self.assertIn("2-1", res["failures"][0])

    def test_clean_near_dates_pass(self):
        odds = {"1-2": {"hw": 1.8}, "3-4": {"hw": 2.0}}  # beide im selben Fenster
        res = W.check_liga_odds_round_sane(_ctx("liga_default", FX, odds))
        self.assertTrue(res["ok"])

    def test_mls_unsynchrone_runden_kein_fehlalarm(self):
        # MLS-Regression 27.07.2026: Runden NICHT kalender-synchron. Runde 18/19/3 liegen zeitlich
        # nah beieinander → runden-basiert wären 32 Odds fälschlich gelb, datums-basiert grün.
        fx = [
            {"home": "A", "away": "B", "matchday": 18, "date": "2026-08-01", "result": None},
            {"home": "C", "away": "D", "matchday": 19, "date": "2026-08-16", "result": None},
            {"home": "E", "away": "F", "matchday": 3,  "date": "2026-08-02", "result": None},
        ]
        odds = {"A-B": {"hw": 1.8}, "C-D": {"hw": 2.0}, "E-F": {"hw": 1.9}}
        res = W.check_liga_odds_round_sane(_ctx("mls_default", fx, odds))
        self.assertTrue(res["ok"], res)

    def test_leere_poly_shell_verschiebt_front_nicht(self):
        # Ferne poly-only-Shell OHNE hw darf weder flaggen noch den Front verschieben.
        fx = [
            {"home": "A", "away": "B", "matchday": 18, "date": "2026-08-01", "result": None},
            {"home": "G", "away": "H", "matchday": 30, "date": "2026-11-04", "result": None},
        ]
        odds = {"A-B": {"hw": 1.8}, "G-H": {"poly_yes": 0.4}}   # G-H: keine echten 1X2-Odds
        res = W.check_liga_odds_round_sane(_ctx("mls_default", fx, odds))
        self.assertTrue(res["ok"], res)

    def test_wm_skipped(self):
        odds = {"1-2": {"hw": 1.8}, "2-1": {"hw": 1.9}}
        self.assertIsNone(W.check_liga_odds_round_sane(_ctx("wm2026", FX, odds)))


if __name__ == "__main__":
    unittest.main()
