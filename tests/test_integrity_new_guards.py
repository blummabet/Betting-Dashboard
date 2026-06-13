"""
test_integrity_new_guards.py — Guards für die Fehlerquellen vom 13./14.06.2026
(Auto-Bet-Kickoff, Resolved-Status-Propagation, AH-Leiter, Match-Stats, Soft-Book-
History). Daten werden injiziert (kein Disk-Lazy-Load), damit der Test deterministisch ist.
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from wm_data_integrity import run_checks  # noqa: E402

NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _result(checks, cid):
    return next((c for c in checks if c["id"] == cid), None)


class TestNewIntegrityGuards(unittest.TestCase):
    def _run(self, wm, auto_bets=None, history=None):
        return run_checks(wm, {}, {}, {}, now=NOW,
                          auto_bets={"bets": auto_bets or []},
                          history=history if history is not None else {})

    def test_autobet_without_kickoff_fails(self):
        wm = {"groups": {}}   # kein Fixture → keine Kickoff-Auflösung
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "autobet_kickoff")
        self.assertFalse(c["ok"])

    def test_autobet_with_kickoff_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-20T19:00:00Z"}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "autobet_kickoff")
        self.assertTrue(c["ok"])

    def test_finished_game_with_placed_bet_flagged(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-13T19:00:00Z",
             "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "resolved_status_propagated")
        self.assertFalse(c["ok"])

    def test_finished_game_resolved_bet_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-13T19:00:00Z",
             "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "lost"}]
        c = _result(self._run(wm, bets), "resolved_status_propagated")
        self.assertTrue(c["ok"])

    def test_finished_without_stats_flagged(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        c = _result(self._run(wm), "finished_has_stats")
        self.assertFalse(c["ok"])

    def test_finished_with_stats_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "result": {"status": "FT", "home_score": 1, "away_score": 1,
             "stats": {"xgTotal": 3.0, "homeXg": 0.6, "awayXg": 2.4}}}]}}}
        c = _result(self._run(wm), "finished_has_stats")
        self.assertTrue(c["ok"])

    def test_soft_book_history_all_pinnacle_flagged(self):
        wm = {"groups": {}}
        # 24 Snapshots, alle nur Pinnacle → lead_lag kann nie feuern
        hist = {"QAT-SUI": [{"ts": "x", "bk": "pinnacle"} for _ in range(24)]}
        c = _result(self._run(wm, history=hist), "soft_book_history")
        self.assertFalse(c["ok"])

    def test_soft_book_history_with_public_ok(self):
        wm = {"groups": {}}
        hist = {"QAT-SUI": [{"ts": "x", "bk": "pinnacle"} for _ in range(20)]
                + [{"ts": "x", "bk": "public"} for _ in range(4)]}
        c = _result(self._run(wm, history=hist), "soft_book_history")
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
