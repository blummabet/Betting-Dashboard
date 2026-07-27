#!/usr/bin/env python3
"""test_ledger_key_tolerance.py — 27.07.2026 (Lucas: „lernt MLS wirklich?").
Pick-Key und Fixture-Key divergieren im Matchday (Pick MLS-17-… vs Fixture MLS-16-…).
_lookup_stats muss trotzdem die Match-Stats finden (spieltag-agnostischer Fallback),
sonst bekommt der Grader kein xG → kein Verdict → Ledger lernt nicht."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import build_signal_ledger as B


class TestKeyTolerance(unittest.TestCase):
    def _wm(self):
        return {"groups": {"MLS": {"fixtures": [
            {"home": "1614", "away": "1601", "matchday": 16,
             "result": {"status": "FT", "stats": {"xgTotal": 2.1, "xgHome": 1.4, "xgAway": 0.7}}}]}}}

    def test_exact_key_hits(self):
        look = B._build_stats_lookup(self._wm())
        self.assertIsNotNone(B._lookup_stats(look, "MLS-16-1614-1601"))

    def test_matchday_mismatch_still_hits(self):
        # Pick sagt Spieltag 17, Fixture ist 16 gespeichert → agnostischer Fallback greift
        look = B._build_stats_lookup(self._wm())
        s = B._lookup_stats(look, "MLS-17-1614-1601")
        self.assertIsNotNone(s)
        self.assertEqual(s["xgHome"], 1.4)

    def test_unknown_game_misses(self):
        look = B._build_stats_lookup(self._wm())
        self.assertIsNone(B._lookup_stats(look, "MLS-17-9999-8888"))


if __name__ == "__main__":
    unittest.main()
