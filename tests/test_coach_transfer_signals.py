#!/usr/bin/env python3
"""test_coach_transfer_signals.py — coach_change + transfer_shift (26.06.2026): Fetcher-Parser
(aktueller Trainer im Fenster, Schlüssel-Abgang) + Signal-Richtungen."""
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_team_changes as F  # noqa: E402
from sharp_signals.coach_change import CoachChangeSignal, bounce  # noqa: E402
from sharp_signals.transfer_shift import TransferShiftSignal, shift  # noqa: E402

TODAY = date(2026, 8, 20)


class TestCoachParse(unittest.TestCase):
    def test_recent_current_coach(self):
        resp = [{"name": "Neucoach", "career": [{"team": {"id": 50}, "start": "2026-07-20", "end": None}]}]
        cc = F.parse_current_coach(resp, "50", TODAY)
        self.assertEqual(cc["name"], "Neucoach")
        self.assertEqual(cc["daysSince"], 31)

    def test_old_coach_ignored(self):
        resp = [{"name": "Altcoach", "career": [{"team": {"id": 50}, "start": "2024-01-01", "end": None}]}]
        self.assertIsNone(F.parse_current_coach(resp, "50", TODAY))

    def test_ended_spell_ignored(self):
        resp = [{"name": "Weg", "career": [{"team": {"id": 50}, "start": "2026-08-01", "end": "2026-08-10"}]}]
        self.assertIsNone(F.parse_current_coach(resp, "50", TODAY))


class TestDepartures(unittest.TestCase):
    def test_key_player_out(self):
        resp = [{"player": {"name": "Star Striker"},
                 "transfers": [{"date": "2026-07-15", "teams": {"out": {"id": 50}, "in": {"id": 9}}}]}]
        deps = F.key_departures(resp, "50", ["Star Striker"], TODAY)
        self.assertEqual(len(deps), 1)

    def test_non_key_ignored(self):
        resp = [{"player": {"name": "Reserve Guy"},
                 "transfers": [{"date": "2026-07-15", "teams": {"out": {"id": 50}, "in": {"id": 9}}}]}]
        self.assertEqual(F.key_departures(resp, "50", ["Star Striker"], TODAY), [])


class TestSignals(unittest.TestCase):
    def test_coach_bounce_home(self):
        ctx = {"coach_change": {"H": {"name": "C", "daysSince": 10}}, "home_id": "H", "away_id": "A"}
        res = CoachChangeSignal().evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(res)
        self.assertGreater(res.score, 0)

    def test_bounce_decay(self):
        self.assertEqual(bounce({"daysSince": 0}), 1.0)
        self.assertEqual(bounce({"daysSince": 90}), 0.0)

    def test_transfer_weakens_own_side(self):
        ctx = {"key_departures": {"H": [{"name": "X", "date": "2026-07-01"}]}, "home_id": "H", "away_id": "A"}
        res = TransferShiftSignal().evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(res)
        self.assertLess(res.score, 0)   # eigenes Team verlor Schlüsselspieler → Sieg gedämpft

    def test_shift_scale(self):
        self.assertEqual(shift([{"name": "a"}]), 0.6)
        self.assertEqual(shift([]), 0.0)


if __name__ == "__main__":
    unittest.main()
