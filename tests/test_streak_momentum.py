#!/usr/bin/env python3
"""test_streak_momentum.py — Serien-als-Signal (29.06.2026, Lucas). Klein, gegated, gedeckelt."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.streak_momentum import StreakMomentumSignal, DEFAULTS

MAX_PP = DEFAULTS["max_pp"]


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
        # 04.07.2026: BTTS ist jetzt persistenz-gedämpft (0.45, Backtest negativ) → eine EINZELNE
        # Serie reicht oft nicht mehr; beide Teams stapeln über die Schwelle.
        r = self.sig.evaluate({"market": "Beide Teams treffen"},
                              _ctx([_streak("42", "bttsYes", 6, 78)], [_streak("50", "bttsYes", 6, 78)]))
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


class TestStreakMomentumResult(unittest.TestCase):
    """25.07.2026 (Lucas: „5 Siege in Folge sollten die 1X2 beeinflussen"): Sieg-/Ungeschlagen-
    Serien wirken auf den Ergebnis-Markt (asymmetrisch: nur die gebackte Seite stützt)."""
    def setUp(self):
        self.sig = StreakMomentumSignal()

    def test_win_streak_supports_home_win(self):
        r = self.sig.evaluate({"market": "Heimsieg"},
                              _ctx([_streak("42", "win", 7, 90, "H")]))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertLessEqual(r.score, MAX_PP)

    def test_opponent_win_streak_opposes_home_win(self):
        r = self.sig.evaluate({"market": "Heimsieg"},
                              _ctx(away_streaks=[_streak("50", "win", 7, 90, "A")]))
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_unbeaten_streak_supports_double_chance_x2(self):
        r = self.sig.evaluate({"market": "Doppelte Chance — X2"},
                              _ctx(away_streaks=[_streak("50", "unbeaten", 8, 90, "A")]))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_goal_streak_does_not_fire_on_win_pick(self):
        # Nur eine Tor-Serie (kein Sieg/ungeschlagen) → Ergebnis-Pfad findet nichts → feuert nicht.
        r = self.sig.evaluate({"market": "Heimsieg"},
                              _ctx([_streak("42", "over25", 8, 90, "H")]))
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
