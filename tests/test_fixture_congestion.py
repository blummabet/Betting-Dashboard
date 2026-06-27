#!/usr/bin/env python3
"""test_fixture_congestion.py — Erschöpfungs-Signal (26.06.2026). Ruhetage aus Spielplan,
müdes Team faden / Gegner-Stau boosten, Unter-Hebel, früh None."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.fixture_congestion import (  # noqa: E402
    FixtureCongestionSignal, rest_days, congestion_factor)

SIG = FixtureCongestionSignal()


class TestPure(unittest.TestCase):
    def test_rest_days(self):
        sched = ["2026-08-15", "2026-08-19", "2026-08-22"]
        self.assertEqual(rest_days(sched, "2026-08-22"), 3)   # 19. → 22. = 3 Tage
        self.assertEqual(rest_days(sched, "2026-08-19"), 4)
        self.assertIsNone(rest_days(sched, "2026-08-15"))     # kein Vorgänger
        self.assertIsNone(rest_days([], "2026-08-22"))

    def test_congestion_factor(self):
        self.assertEqual(congestion_factor(2), 1.0)
        self.assertEqual(congestion_factor(3), 0.6)
        self.assertEqual(congestion_factor(5), 0.0)
        self.assertEqual(congestion_factor(None), 0.0)


class TestEvaluate(unittest.TestCase):
    def _ctx(self, sched, date_):
        return {"team_schedule": sched, "current_match_date": date_,
                "home_id": "H", "away_id": "A"}

    def test_fade_tired_home_boost_away(self):
        # Heim spielte vor 2 Tagen (müde), Auswärts vor 6 (frisch). Pick Auswärts → Boost.
        sched = {"H": ["2026-08-20", "2026-08-22"], "A": ["2026-08-16", "2026-08-22"]}
        res = SIG.evaluate({"market": "Auswärtssieg"}, self._ctx(sched, "2026-08-22"))
        self.assertIsNotNone(res)
        self.assertGreater(res.score, 0)

    def test_fade_own_tired_side(self):
        sched = {"H": ["2026-08-20", "2026-08-22"], "A": ["2026-08-16", "2026-08-22"]}
        res = SIG.evaluate({"market": "Heimsieg"}, self._ctx(sched, "2026-08-22"))
        self.assertIsNotNone(res)
        self.assertLess(res.score, 0)   # eigenes Team müde → Fade

    def test_both_rested_none(self):
        sched = {"H": ["2026-08-15", "2026-08-22"], "A": ["2026-08-15", "2026-08-22"]}
        self.assertIsNone(SIG.evaluate({"market": "Heimsieg"}, self._ctx(sched, "2026-08-22")))

    def test_first_matchday_none(self):
        sched = {"H": ["2026-08-15"], "A": ["2026-08-15"]}
        self.assertIsNone(SIG.evaluate({"market": "Heimsieg"}, self._ctx(sched, "2026-08-15")))

    def test_over_skipped(self):
        sched = {"H": ["2026-08-20", "2026-08-22"], "A": ["2026-08-16", "2026-08-22"]}
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5 Tore"}, self._ctx(sched, "2026-08-22")))


if __name__ == "__main__":
    unittest.main()
