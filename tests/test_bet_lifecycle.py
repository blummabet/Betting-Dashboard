#!/usr/bin/env python3
"""
test_bet_lifecycle.py — Zeitbewusster BET-Lebenszyklus (18.06.2026, Lucas)

ENTER BET: nur bei FRISCHEM Move (lastMoveH ≤ bet_entry_hurdle_h).
HOLD BET:  einmal BET, bleibt BET bis ein Reverser kommt — auch wenn der Move ruht.
EXIT BET:  Reverser (frisches Gegen-Geld) → Demote.

Der Hold-Mechanismus + die Entry-Hürde sitzen in generate_wm_picks.main(); hier testen wir
die Bausteine direkt (Guard) + die Entry-Hürden-Logik isoliert.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G  # noqa: E402
from wm_data_integrity import run_checks  # noqa: E402

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def _result(checks, cid):
    return next((c for c in checks if c["id"] == cid), None)


class TestEntryHurdleConfig(unittest.TestCase):
    def test_hurdle_loaded(self):
        self.assertEqual(G.BET_ENTRY_HURDLE_H, 48)

    def test_fresh_passes_stale_blocks(self):
        h = G.BET_ENTRY_HURDLE_H
        # Replikat der Entry-Bedingung: frisch (≤h) oder None (unmappbar) → ok
        def move_fresh(lmh):
            return (lmh is None) or (lmh <= h)
        self.assertTrue(move_fresh(6.0))     # frisch
        self.assertTrue(move_fresh(None))    # unmappbar → Hürde aus
        self.assertFalse(move_fresh(120.0))  # 5 Tage alt → kein Entry


class TestBetMoveFreshGuard(unittest.TestCase):
    def _run(self, picks):
        wm = {"groups": {}, "picks": picks}
        return run_checks(wm, {}, {}, {}, now=NOW, auto_bets={"bets": []}, history={})

    def test_stale_bet_without_hold_flagged(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "BET", "lastMoveH": 120.0}]}
        c = _result(self._run(picks), "bet_move_fresh")
        self.assertFalse(c["ok"])

    def test_stale_bet_but_held_ok(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "BET",
             "lastMoveH": 120.0, "betHeld": True}]}
        c = _result(self._run(picks), "bet_move_fresh")
        self.assertTrue(c["ok"])

    def test_fresh_bet_ok(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "BET", "lastMoveH": 6.0}]}
        c = _result(self._run(picks), "bet_move_fresh")
        self.assertTrue(c["ok"])

    def test_unmappable_bet_exempt(self):
        # lastMoveH None (AH/unmappbar) → Hürde greift bewusst nicht → kein Fail
        picks = {"A-1-AAA-BBB": [
            {"market": "AH Heim -1.5", "source": "steam", "verdict": "BET"}]}
        c = _result(self._run(picks), "bet_move_fresh")
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
