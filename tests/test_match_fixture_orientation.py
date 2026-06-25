#!/usr/bin/env python3
"""
test_match_fixture_orientation.py — Ergebnis-Matching orientierungs-agnostisch (25.06.2026, Lucas:
MD3 nicht aufgelöst). API-Football ordnet Heim/Auswärts bei WM-Spielen teils anders zu als unser
Seed → strikter Reihenfolge-Match scheiterte → kein Ergebnis. Fix: Match per Team-Paar + Score nach
Team-ID gemappt.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_match_results as F   # noqa: E402
import wm_data_integrity as W       # noqa: E402

TEAM_IDS = {"MEX": 16, "CZE": 25}


def _api(home_id, away_id, hg, ag):
    return {"teams": {"home": {"id": home_id, "name": "H"}, "away": {"id": away_id, "name": "A"}},
            "goals": {"home": hg, "away": ag},
            "fixture": {"status": {"short": "FT"}}}


class TestMatchOrientation(unittest.TestCase):
    def test_direct(self):
        self.assertEqual(F.match_fixture(_api(16, 25, 2, 1), "MEX", "CZE", TEAM_IDS), "direct")

    def test_swapped(self):
        # API listet CZE als Heim (25), MEX als Auswärts (16) — unser Fixture ist MEX-CZE
        self.assertEqual(F.match_fixture(_api(25, 16, 1, 2), "MEX", "CZE", TEAM_IDS), "swapped")

    def test_no_match(self):
        self.assertIsNone(F.match_fixture(_api(99, 25, 1, 1), "MEX", "CZE", TEAM_IDS))

    def test_swapped_score_mapping_logic(self):
        # bei 'swapped' muss home_score = API-away sein. Verifiziert die Mapping-Regel direkt.
        api = _api(25, 16, 1, 2)   # CZE(25) 1 : MEX(16) 2  → unser MEX-Heim soll 2 bekommen
        o = F.match_fixture(api, "MEX", "CZE", TEAM_IDS)
        goals = api["goals"]
        home_score = goals["away"] if o == "swapped" else goals["home"]
        away_score = goals["home"] if o == "swapped" else goals["away"]
        self.assertEqual((home_score, away_score), (2, 1))   # MEX 2 : CZE 1 ✓


class TestPlayedGamesGuard(unittest.TestCase):
    def _run(self, fixtures):
        wm = {"groups": {"A": {"fixtures": fixtures}}, "picks": {}}
        res = W.run_checks(wm, {}, {}, {}, now=datetime(2026, 6, 25, 12, tzinfo=timezone.utc),
                           auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "played_games_resolved"), None)

    def test_played_no_result_flagged(self):
        c = self._run([{"home": "MEX", "away": "CZE",
                        "kickoff": "2026-06-25T01:00:00Z", "result": {"status": "NS"}}])
        self.assertFalse(c["ok"])

    def test_fresh_game_not_flagged(self):
        c = self._run([{"home": "A", "away": "B",
                        "kickoff": "2026-06-25T10:00:00Z", "result": {"status": "NS"}}])
        self.assertTrue(c["ok"])   # < 5h her → noch ok

    def test_resolved_passes(self):
        c = self._run([{"home": "A", "away": "B", "kickoff": "2026-06-25T01:00:00Z",
                        "result": {"status": "FT", "home_score": 1, "away_score": 0}}])
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
