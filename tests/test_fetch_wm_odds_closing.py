#!/usr/bin/env python3
"""
test_fetch_wm_odds_closing.py — CLV-Closing-Logik (16.06.2026).

Vorher wurde beim ersten Fetch NACH Anpfiff die aktuelle (In-Play-)Quote als Closing
eingefroren → verfälschtes CLV. Jetzt: letzter PRE-Anpfiff-Snapshot wird final,
In-Play-Odds überschreiben NIE die Closing-Linie.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_odds as f

CUR = {"hw": 2.0, "dr": 3.3, "aw": 3.8}
INPLAY = {"hw": 1.2, "dr": 5.0, "aw": 12.0}   # In-Play würde so aussehen


class TestComputeClosing(unittest.TestCase):
    def test_prematch_in_window_writes_provisional(self):
        c = f.compute_closing(None, CUR, hours_to_ko=2.0, now_iso="T1")
        self.assertEqual(c["hw"], 2.0)
        self.assertTrue(c["provisional"])
        self.assertNotIn("final", c)

    def test_prematch_outside_window_keeps_existing(self):
        existing = {"hw": 9.9, "provisional": True}
        c = f.compute_closing(existing, CUR, hours_to_ko=20.0, now_iso="T1")
        self.assertEqual(c, existing)   # 20h entfernt → noch nicht erfassen

    def test_prematch_overwrites_with_latest(self):
        existing = {"hw": 2.2, "dr": 3.1, "aw": 3.5, "provisional": True}
        c = f.compute_closing(existing, CUR, hours_to_ko=0.5, now_iso="T2")
        self.assertEqual(c["hw"], 2.0)   # näher am Anpfiff = überschreibt
        self.assertTrue(c["provisional"])

    def test_postkickoff_finalizes_last_prematch_not_inplay(self):
        existing = {"hw": 2.0, "dr": 3.3, "aw": 3.8, "provisional": True}
        # Anpfiff vorbei: aktuelle Odds wären In-Play — dürfen NICHT übernommen werden
        c = f.compute_closing(existing, INPLAY, hours_to_ko=-0.1, now_iso="T3")
        self.assertEqual(c["hw"], 2.0)          # letzter pre-match Wert, NICHT 1.2
        self.assertTrue(c["final"])
        self.assertFalse(c["provisional"])

    def test_final_never_changes(self):
        existing = {"hw": 2.0, "final": True}
        c = f.compute_closing(existing, INPLAY, hours_to_ko=-5.0, now_iso="T4")
        self.assertEqual(c, existing)

    def test_postkickoff_no_prematch_returns_none(self):
        # Kein pre-match Snapshot erfasst → None → Caller nutzt last_known-Fallback
        c = f.compute_closing(None, CUR, hours_to_ko=-1.0, now_iso="T5")
        self.assertIsNone(c)

    def test_no_kickoff_time_keeps_existing(self):
        existing = {"hw": 2.0, "provisional": True}
        self.assertEqual(f.compute_closing(existing, CUR, None, "T6"), existing)


if __name__ == "__main__":
    unittest.main()
