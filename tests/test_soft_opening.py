#!/usr/bin/env python3
"""
test_soft_opening.py — Soft-Eröffnung darf nicht je Lauf auf „Jetzt" zurückgesetzt werden
(22.06.2026, Lucas: „Opening==Jetzt auf fast jeder Card").

Root-Cause: fetch_wm_odds baut den Odds-Eintrag je Lauf frisch und ersetzt ihn komplett
(odds_out[key]=new_entry). odds_open wurde aus existing übernommen, public_*_open NICHT →
fetch_wm_multibook_odds (set-once-if-None) re-initialisierte das Soft-Opening auf den aktuellen
Konsens. Fix: fetch_wm_odds.carry_soft_open schleppt public_*_open mit + Guard fängt es künftig.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_odds as F            # noqa: E402
import wm_data_integrity as W        # noqa: E402


class TestCarrySoftOpen(unittest.TestCase):
    def test_existing_opening_preserved(self):
        existing = {"public_hw_open": 1.95, "public_dr_open": 3.4, "public_aw_open": 4.1}
        new = {"public_hw": 1.80, "public_dr": 3.5, "public_aw": 4.4}   # frisch, ohne _open
        F.carry_soft_open(existing, new)
        self.assertEqual(new["public_hw_open"], 1.95)   # Eröffnung bleibt, NICHT 1.80
        self.assertEqual(new["public_aw_open"], 4.1)

    def test_no_existing_opening_leaves_new_untouched(self):
        new = {"public_hw": 1.80}
        F.carry_soft_open({}, new)
        self.assertNotIn("public_hw_open", new)         # nichts zu übernehmen → nichts erfinden

    def test_does_not_overwrite_already_present(self):
        existing = {"public_hw_open": 1.95}
        new = {"public_hw": 1.80, "public_hw_open": 1.90}   # schon gesetzt
        F.carry_soft_open(existing, new)
        self.assertEqual(new["public_hw_open"], 1.95)   # existing ist die Wahrheitsquelle


class TestSoftOpeningGuard(unittest.TestCase):
    def _run(self, odds, history):
        res = W.run_checks({"groups": {}, "picks": {}, "odds": odds}, {}, {}, {},
                           now=datetime(2026, 6, 22, tzinfo=timezone.utc),
                           auto_bets={"bets": []}, history=history)
        return next((x for x in res if x["id"] == "soft_opening_captured"), None)

    def _soft_hist(self, first, last):
        # Soft-Zeitreihe (bk=public): bewegt sich von first → last
        return [{"bk": "public", "hw": first}, {"bk": "public", "hw": last}]

    def _odds(self, n, open_val):
        return {f"M{i}-X{i}": {"public_hw": 2.3, "public_hw_open": open_val} for i in range(n)}

    def _hist(self, n, first, last):
        return {f"M{i}-X{i}": self._soft_hist(first, last) for i in range(n)}

    def test_frozen_openings_flagged(self):
        # Soft-Linie bewegte sich (2.6→2.3), aber Opening == Jetzt (2.3) → Bug
        c = self._run(self._odds(5, 2.3), self._hist(5, 2.6, 2.3))
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])

    def test_real_openings_pass(self):
        # Soft bewegte sich UND Opening (2.6) ≠ Jetzt (2.3) → echt erfasst
        c = self._run(self._odds(5, 2.6), self._hist(5, 2.6, 2.3))
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])

    def test_flat_soft_not_flagged(self):
        # Soft-Linie real flach (2.3→2.3) → Opening==Jetzt ist korrekt, kein Flag
        c = self._run(self._odds(5, 2.3), self._hist(5, 2.3, 2.3))
        self.assertIsNone(c)   # keine bewegte Soft-Linie → keine Aussage

    def test_no_history_no_verdict(self):
        c = self._run(self._odds(5, 2.3), {})
        self.assertIsNone(c)


if __name__ == "__main__":
    unittest.main()
