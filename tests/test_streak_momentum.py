#!/usr/bin/env python3
"""test_streak_momentum.py — Serien-als-Signal (29.06.2026, Lucas). Klein, gegated, gedeckelt."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.streak_momentum import StreakMomentumSignal, MAX_PP


def _streak(team, stype, length, rate, venue="all"):
    return {"teamId": team, "team": team, "type": stype, "length": length,
            "ratePct": rate, "venue": venue, "market": stype}


def _ctx(home_streaks=None, away_streaks=None):
    return {"home_id": "42", "away_id": "50",
            "streaks": {"42": home_streaks or [], "50": away_streaks or []}}


class TestStreakMomentum(unittest.TestCase):
    def setUp(self):
        self.sig = StreakMomentumSignal()

    def test_over_streak_supports_over_pick(self):
        r = self.sig.evaluate({"market": "Über 2.5 Tore"},
                              _ctx([_streak("42", "over25", 6, 75)], [_streak("50", "over25", 5, 70)]))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertLessEqual(r.score, MAX_PP)

    def test_opposing_streak_negative(self):
        # Über-Pick, aber Heim hat eine starke UNTER-Serie → Signal warnt (negativ)
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, _ctx([_streak("42", "under25", 6, 78)]))
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_capped(self):
        big = [_streak("42", "over25", 8, 95)]
        big2 = [_streak("50", "over25", 8, 95)]
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, _ctx(big, big2))
        self.assertLessEqual(r.score, MAX_PP)

    def test_btts_market(self):
        r = self.sig.evaluate({"market": "Beide Teams treffen"},
                              _ctx([_streak("42", "bttsYes", 6, 72)]))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_non_streak_market_none(self):
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"},
                          _ctx([_streak("42", "over25", 7, 80)])))

    def test_no_streaks_none(self):
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"}, _ctx()))

    def test_short_or_weak_streak_ignored(self):
        # Länge 3 (< MIN) und schwache Rate → kein Feuern
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"},
                          _ctx([_streak("42", "over25", 3, 52)])))

    def test_in_form_family(self):
        from sharp_signals.registry import SIGNAL_GROUPS
        self.assertEqual(SIGNAL_GROUPS.get("streak_momentum"), "form")


if __name__ == "__main__":
    unittest.main()
