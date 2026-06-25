#!/usr/bin/env python3
"""
test_build_liga_data.py — Liga-Datenmodell im WM-Format (25.06.2026, Lucas: Liga auf WM-Stack).
Prüft den reinen Transformer build_groups: Ligen→„Gruppen", Teams/Elo, Fixtures, Runde→matchday,
Status-Mapping (nur beendete Spiele bekommen einen Score).
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import build_liga_data as B  # noqa: E402


def _standings(team_rows):
    return {"response": [{"league": {"standings": [
        [{"team": {"id": tid, "name": name, "logo": "x"}} for tid, name in team_rows]
    ]}}]}


def _fixtures(rows):
    # rows: (home_id, home_name, away_id, away_name, iso, round, short, hg, ag)
    resp = []
    for hid, hn, aid, an, iso, rnd, short, hg, ag in rows:
        resp.append({
            "fixture": {"date": iso, "status": {"short": short}, "venue": {"name": "Stadion"}},
            "teams": {"home": {"id": hid, "name": hn}, "away": {"id": aid, "name": an}},
            "goals": {"home": hg, "away": ag},
            "league": {"round": rnd},
        })
    return {"response": resp}


class TestSeason(unittest.TestCase):
    def test_summer_is_upcoming(self):
        self.assertEqual(B.current_season(datetime(2026, 6, 25, tzinfo=timezone.utc)), 2026)

    def test_spring_is_running(self):
        self.assertEqual(B.current_season(datetime(2026, 3, 1, tzinfo=timezone.utc)), 2025)


class TestParseRound(unittest.TestCase):
    def test_regular(self):
        self.assertEqual(B._parse_round("Regular Season - 1"), 1)
        self.assertEqual(B._parse_round("Regular Season - 38"), 38)

    def test_unparsable(self):
        self.assertIsNone(B._parse_round("Relegation Round"))


class TestBuildGroups(unittest.TestCase):
    def setUp(self):
        self.st = {"ENG": _standings([(40, "Liverpool"), (50, "Man City")])}
        self.fx = {"ENG": _fixtures([
            (40, "Liverpool", 50, "Man City", "2026-08-15T14:00:00+00:00",
             "Regular Season - 1", "NS", None, None),
            (50, "Man City", 40, "Liverpool", "2026-05-01T14:00:00+00:00",
             "Regular Season - 35", "FT", 2, 1),
        ])}

    def test_league_becomes_group(self):
        g = B.build_groups(self.st, self.fx)
        self.assertIn("ENG", g)
        self.assertEqual(g["ENG"]["name"], "Premier League")
        self.assertEqual(len(g["ENG"]["teams"]), 2)
        self.assertEqual(g["ENG"]["teams"][0]["id"], "40")   # ID als String

    def test_fixture_fields(self):
        g = B.build_groups(self.st, self.fx)
        fxs = g["ENG"]["fixtures"]
        self.assertEqual(len(fxs), 2)
        opener = next(f for f in fxs if f["matchday"] == 1)
        self.assertEqual((opener["home"], opener["away"]), ("40", "50"))
        self.assertEqual(opener["date"], "2026-08-15")
        self.assertIsNone(opener["result"])              # NS → kein Score

    def test_finished_has_result(self):
        g = B.build_groups(self.st, self.fx)
        done = next(f for f in g["ENG"]["fixtures"] if f["matchday"] == 35)
        self.assertEqual(done["result"]["status"], "FT")
        self.assertEqual((done["result"]["home_score"], done["result"]["away_score"]), (2, 1))

    def test_elo_injected(self):
        g = B.build_groups(self.st, self.fx, {"40": 2050})
        liv = next(t for t in g["ENG"]["teams"] if t["id"] == "40")
        self.assertEqual(liv["elo"], 2050)

    def test_all_five_leagues_present(self):
        g = B.build_groups({}, {})   # leere Responses → 5 leere Ligen, kein Crash
        self.assertEqual(set(g.keys()), {"ENG", "ESP", "GER", "ITA", "FRA"})
        self.assertEqual(g["ESP"]["fixtures"], [])


if __name__ == "__main__":
    unittest.main()
