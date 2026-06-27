#!/usr/bin/env python3
"""test_liga_odds_match.py — pick_event_for_fixture (Fix 26.06.2026 „Spieltag 1 dann 20"): ein
Hinrunden-Event darf NICHT das Rückspiel-Fixture (gleiche Teams, anderes Datum) matchen."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_odds as O  # noqa: E402

EV_AUG = {"home_team": "Arsenal", "away_team": "Chelsea", "commence_time": "2026-08-15T14:00:00Z"}


class TestPickEvent(unittest.TestCase):
    def test_matches_correct_round_by_date(self):
        # Hinrunde (Arsenal Heim, 15.08.) → matcht das Aug-Event direkt
        got = O.pick_event_for_fixture([EV_AUG], "Arsenal", "Chelsea", "2026-08-15")
        self.assertIsNotNone(got)
        self.assertEqual(got[1], "direct")

    def test_rejects_reverse_fixture_far_date(self):
        # Rückspiel (Chelsea Heim, 10.01.) — selbe Teams, aber Monate später → KEIN Match,
        # obwohl match_event_to_fixture 'swapped' liefern würde.
        self.assertIsNone(O.pick_event_for_fixture([EV_AUG], "Chelsea", "Arsenal", "2027-01-10"))

    def test_swapped_same_date_ok(self):
        # Gleiches Datum, aber API hat Heim/Auswärts vertauscht → 'swapped' bleibt erlaubt.
        got = O.pick_event_for_fixture([EV_AUG], "Chelsea", "Arsenal", "2026-08-15")
        self.assertEqual(got[1], "swapped")

    def test_no_date_falls_back(self):
        # Ohne Fixture-Datum kein Datums-Gate (alte Toleranz) → erstes Team-Match.
        got = O.pick_event_for_fixture([EV_AUG], "Arsenal", "Chelsea", "")
        self.assertEqual(got[1], "direct")

    def test_picks_nearest_of_two(self):
        ev2 = {"home_team": "Arsenal", "away_team": "Chelsea", "commence_time": "2026-08-16T14:00:00Z"}
        got = O.pick_event_for_fixture([ev2, EV_AUG], "Arsenal", "Chelsea", "2026-08-15")
        self.assertEqual(O._event_date(got[0]), "2026-08-15")  # näher dran


if __name__ == "__main__":
    unittest.main()
