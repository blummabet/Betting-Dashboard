#!/usr/bin/env python3
"""test_weekly_sharp_recap.py — Sharp-Radar Wochenrückblick (25.07.2026).
Sichert die CLV-Auflösung (Entry ≤ ts / Pinnacle-Vorzug, Closing bevorzugt final),
die gesteamte-Seite-Logik, das Neutralband, Aktivität/Hold-Rate und den Wochen-Dedup."""
import os, sys, json, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("COCOBET_DATASET", "mls")
os.environ.setdefault("COCOBET_PROFILE", "mls_default")

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import weekly_sharp_recap as R


def _ts(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestSteamedSide(unittest.TestCase):
    def test_picks_max_positive_shift(self):
        s, sh = R._steamed_side({"hwShift": 1.0, "drShift": -0.5, "awShift": 4.2})
        self.assertEqual(s, "aw"); self.assertAlmostEqual(sh, 4.2)

    def test_none_when_no_positive(self):
        s, sh = R._steamed_side({"hwShift": -1.0, "drShift": -0.5, "awShift": -4.2})
        self.assertIsNone(s); self.assertEqual(sh, 0.0)


class TestClvMark(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(R._clv_mark(1.0), "✅")
        self.assertEqual(R._clv_mark(-1.0), "❌")
        self.assertEqual(R._clv_mark(0.0), "➖")     # Push
        self.assertEqual(R._clv_mark(0.04), "➖")    # innerhalb ±EPS


class TestEntryClosing(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        self.move_ts = base + timedelta(hours=2)
        self.snaps = [
            {"bk": "pinnacle", "ts": _ts(base),                     "aw": 3.0},
            {"bk": "public",   "ts": _ts(base + timedelta(hours=1)),"aw": 2.9},
            {"bk": "pinnacle", "ts": _ts(base + timedelta(hours=1, minutes=30)), "aw": 2.8},
            {"bk": "pinnacle", "ts": _ts(base + timedelta(hours=5)),"aw": 2.5},  # NACH move_ts
        ]

    def test_entry_is_last_pinnacle_at_or_before_ts(self):
        self.assertEqual(R._entry_odds(self.snaps, "aw", self.move_ts), 2.8)

    def test_closing_prefers_final_line(self):
        close = {"K": {"final": True, "aw": 2.4}}
        self.assertEqual(R._closing_odds("K", "aw", close, self.snaps), 2.4)

    def test_closing_falls_back_to_last_pinnacle(self):
        self.assertEqual(R._closing_odds("K", "aw", {}, self.snaps), 2.5)

    def test_closing_ignores_non_final(self):
        close = {"K": {"final": False, "aw": 9.9}}
        self.assertEqual(R._closing_odds("K", "aw", close, self.snaps), 2.5)


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self._saved = R.json_wm
        R.json_wm = {"groups": {"g": {"teams": [
            {"id": "H", "name": "Home FC"}, {"id": "A", "name": "Away FC"}]}}}

    def tearDown(self):
        R.json_wm = self._saved

    def test_counts_and_hold_rate(self):
        base = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        cutoff = base - timedelta(days=1)
        moves = [
            # aw steamte (aw entry 2.0 -> close 1.8 = kürzer = hielt) -> CLV+
            {"ts": _ts(base), "type": "steam", "key": "H-A", "homeId": "H", "awayId": "A",
             "hwShift": -1, "drShift": 0, "awShift": 3, "maxShift": 3},
            # hw steamte, aber close länger (1.5 -> 1.6) = zurückgedreht -> CLV-
            {"ts": _ts(base), "type": "sharp", "key": "H-A2", "homeId": "H", "awayId": "A",
             "hwShift": 2, "drShift": 0, "awShift": -2, "maxShift": 2},
            # außerhalb des Fensters -> ignoriert
            {"ts": _ts(base - timedelta(days=10)), "type": "cumul", "key": "H-A",
             "homeId": "H", "awayId": "A", "hwShift": 1, "drShift": 0, "awShift": 0, "maxShift": 1},
        ]
        hist = {
            "H-A":  [{"bk": "pinnacle", "ts": _ts(base - timedelta(hours=1)), "aw": 2.0}],
            "H-A2": [{"bk": "pinnacle", "ts": _ts(base - timedelta(hours=1)), "hw": 1.5}],
        }
        close = {"H-A":  {"final": True, "aw": 1.8},
                 "H-A2": {"final": True, "hw": 1.6}}
        st = R.analyze(moves, hist, close, cutoff)
        self.assertEqual(st["n"], 2)                       # 10d-alter Move raus
        self.assertEqual(st["counts"]["steam"], 1)
        self.assertEqual(st["clv_n"], 2)
        self.assertEqual(st["clv_held"], 1)                # nur der aw-Move hielt
        self.assertAlmostEqual(st["clv_hold_rate"], 50.0)


class TestWeekDedup(unittest.TestCase):
    def test_week_id_format(self):
        wid = R._week_id(datetime(2026, 7, 26, tzinfo=timezone.utc))
        self.assertRegex(wid, r"^2026-W\d{2}$")

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            R.STATE_FILE = Path(d) / "state.json"
            wk = "2026-W30"
            self.assertFalse(R._already_posted(wk))
            R._mark_posted(wk)
            self.assertTrue(R._already_posted(wk))
            self.assertFalse(R._already_posted("2026-W31"))


if __name__ == "__main__":
    unittest.main()
