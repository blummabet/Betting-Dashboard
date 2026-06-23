#!/usr/bin/env python3
"""
test_nobet.py — NOBET-Kategorie (23.06.2026, Lucas): ein Pick, der mal BET/ABWÄGEN war und dessen
Value gekippt ist (z.B. COL-COD Unter), verschwindet nicht lautlos, sondern bleibt als verdict=NOBET
mit Grund. Schatten-Ergebnis rein informativ — NIE in P&L/Win-Rate/Lernen/Trading.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G       # noqa: E402
import build_signal_ledger as L     # noqa: E402


class TestCarryNobet(unittest.TestCase):
    def test_dropped_pick_becomes_nobet(self):
        existing = [{"market": "Unter 2.5 Tore", "verdict": "ABWÄGEN", "odds": 1.67}]
        new = []  # diesmal kein Pick mehr
        out = G._carry_nobet(existing, new, {"u25": 1.84}, "2026-06-23T18:00:00Z")
        self.assertEqual(len(out), 1)
        nb = out[0]
        self.assertEqual(nb["verdict"], "NOBET")
        self.assertEqual(nb["origVerdict"], "ABWÄGEN")
        self.assertIsNone(nb["result"])
        self.assertIn("Edge weg", nb["nobetReason"])  # 1.67 → 1.84 = gegen den Pick

    def test_still_a_pick_no_nobet(self):
        existing = [{"market": "Unter 2.5 Tore", "verdict": "ABWÄGEN", "odds": 1.67}]
        new = [{"market": "Unter 2.5 Tore", "verdict": "BET", "odds": 1.70}]
        out = G._carry_nobet(existing, new, {}, "t")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["verdict"], "BET")  # echter Pick gewinnt, kein NOBET

    def test_skip_and_beobachten_not_carried(self):
        existing = [{"market": "Heimsieg", "verdict": "SKIP"},
                    {"market": "Über 2.5 Tore", "verdict": "BEOBACHTEN"}]
        out = G._carry_nobet(existing, [], {}, "t")
        self.assertEqual(out, [])  # nur ex-BET/ABWÄGEN werden NOBET

    def test_existing_nobet_persists(self):
        existing = [{"market": "Unter 2.5 Tore", "verdict": "NOBET",
                     "origVerdict": "ABWÄGEN", "origOdds": 1.67, "nobetReason": "x"}]
        out = G._carry_nobet(existing, [], {}, "t2")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["verdict"], "NOBET")
        self.assertEqual(out[0]["origVerdict"], "ABWÄGEN")  # Original bleibt erhalten


class TestNobetExcludedFromLedger(unittest.TestCase):
    def test_nobet_not_in_ledger(self):
        wm = {"picks": {"K-2-COL-COD": [
            {"market": "Unter 2.5 Tore", "verdict": "NOBET", "shadowResult": "WIN",
             "result": None, "signals": [{"name": "x", "score": 1}]},
            {"market": "Auswärtssieg", "verdict": "BET", "result": "WIN",
             "signals": [{"name": "y", "score": 1}]},
        ]}}
        obs = L.collect_observations(wm)
        markets = {o["market"] for o in obs}
        self.assertIn("Auswärtssieg", markets)
        self.assertNotIn("Unter 2.5 Tore", markets)  # NOBET fliegt raus


class TestValidatorTreatsNobetNonActive(unittest.TestCase):
    def test_nobet_no_missing_field_error(self):
        import validate_wm_picks as V
        issues = []
        # NOBET ohne odds/edge → darf KEINE E_MISSING_FIELD/E_VERDICT-Fehler werfen
        wm = {"groups": {"K": {"fixtures": [{"home": "COL", "away": "COD"}]}}}
        V.validate_pick("K-2-COL-COD", {"market": "Unter 2.5 Tore", "verdict": "NOBET"},
                        wm, issues)
        errs = [i for i in issues if i["level"] == "error"]
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
