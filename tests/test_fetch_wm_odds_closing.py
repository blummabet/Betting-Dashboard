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


class TestDcOrientation(unittest.TestCase):
    """29.06.2026 (Lucas: BRA-JPN E_HOMEAWAY_SWAP): DC-Selbstheilung am 1X2-Anker."""

    def test_swapped_dc_detected(self):
        self.assertTrue(f.dc_contradicts_1x2(2.04, 4.5, 1.55, 1.24))   # BRA-JPN: Heim-Fav, aber dc1X>dcX2

    def test_consistent_dc_ok(self):
        self.assertFalse(f.dc_contradicts_1x2(2.04, 4.5, 1.24, 1.55))  # Heim-Fav + dc1X<dcX2

    def test_away_favorite_consistent(self):
        self.assertFalse(f.dc_contradicts_1x2(4.5, 2.04, 1.55, 1.24))  # Auswärts-Fav + dcX2<dc1X

    def test_missing_values_no_false_positive(self):
        self.assertFalse(f.dc_contradicts_1x2(2.0, 4.0, None, 1.3))


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

    def test_overnight_gap_game_now_captured(self):
        # Write-Side-Fix 21.06.2026: Spiel 7.5h vor Anpfiff (Nacht-Cron-Lücke 20→04 UTC).
        # Mit altem 6h-Fenster wurde KEIN Snapshot erfasst → In-Play-Fallback. Mit 9h ja.
        self.assertGreaterEqual(f.CLOSING_CAPTURE_WINDOW_H, 8.0)
        c = f.compute_closing(None, CUR, hours_to_ko=7.5, now_iso="T1")
        self.assertEqual(c["hw"], 2.0)        # jetzt als provisorisches Closing erfasst
        self.assertTrue(c["provisional"])

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


class TestMergeClosingLines(unittest.TestCase):
    """Phase 3: persistente Closing-Linien (wm_closing_lines.json)."""

    def test_takes_fresher_provisional(self):
        existing = {"A-B": {"hw": 2.2, "frozenAt": "T1", "provisional": True}}
        odds_out = {"A-B": {"odds_closing": {"hw": 2.0, "frozenAt": "T2", "provisional": True}}}
        out = f.merge_closing_lines(existing, odds_out)
        self.assertEqual(out["A-B"]["hw"], 2.0)   # T2 > T1 → frischer

    def test_final_never_downgraded(self):
        existing = {"A-B": {"hw": 1.9, "frozenAt": "T9", "final": True}}
        odds_out = {"A-B": {"odds_closing": {"hw": 2.0, "frozenAt": "T1", "provisional": True}}}
        out = f.merge_closing_lines(existing, odds_out)
        self.assertEqual(out["A-B"]["hw"], 1.9)   # final bleibt
        self.assertTrue(out["A-B"]["final"])

    def test_final_overwrites_provisional(self):
        existing = {"A-B": {"hw": 2.0, "frozenAt": "T1", "provisional": True}}
        odds_out = {"A-B": {"odds_closing": {"hw": 2.05, "frozenAt": "T2", "final": True}}}
        out = f.merge_closing_lines(existing, odds_out)
        self.assertTrue(out["A-B"]["final"])

    def test_skips_entries_without_closing(self):
        out = f.merge_closing_lines({}, {"A-B": {"hw": 2.0}})   # kein odds_closing
        self.assertEqual(out, {})


class TestImminentGuard(unittest.TestCase):
    """07.07.2026 (Lucas: CLV kaputt, weil Closing 1-7h veraltet). _has_imminent_kickoff steuert die
    quota-schonende Nah-am-Anpfiff-Capture: nur bei einem Spiel in [-20 … +90] min feuert der Fetch."""
    from datetime import datetime as _d, timezone as _t, timedelta as _td

    def _wm(self, minutes_to_ko, final=False):
        from datetime import datetime, timezone, timedelta
        ko = (datetime.now(timezone.utc) + timedelta(minutes=minutes_to_ko)).isoformat()
        wm = {"groups": {}, "koFixtures": [{"home": "AAA", "away": "BBB", "kickoff": ko}]}
        if final:
            wm["odds"] = {"AAA-BBB": {"odds_closing": {"final": True}}}
        return wm

    def test_imminent_true(self):
        self.assertTrue(f._has_imminent_kickoff(self._wm(30)))     # in 30 min

    def test_just_kicked_off_still_true(self):
        self.assertTrue(f._has_imminent_kickoff(self._wm(-10)))    # gerade angepfiffen (Finalisierung)

    def test_far_future_false(self):
        self.assertFalse(f._has_imminent_kickoff(self._wm(360)))   # 6h weg → No-Op

    def test_final_closing_skipped(self):
        self.assertFalse(f._has_imminent_kickoff(self._wm(30, final=True)))

    def test_no_fixtures_false(self):
        self.assertFalse(f._has_imminent_kickoff({"groups": {}, "koFixtures": []}))


if __name__ == "__main__":
    unittest.main()
