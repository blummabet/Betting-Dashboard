#!/usr/bin/env python3
"""test_player_streaks.py — Spieler-Serien (06.07.2026, Lucas): Torserie/Torbeteiligung/Zu-Null
aus dem player_form_ledger + Team-Elimination-Filter im Digest."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import compute_player_streaks as P
import telegram_streaks as TS


def _row(pid, tid, ts, goals=0, assists=0, minutes=90, name="X"):
    return {"playerId": pid, "teamId": tid, "ts": ts, "goals": goals,
            "assists": assists, "minutes": minutes, "name": name}


def _lineups():
    # numerische teamId 16 → Mexico → MEX; GK id 900
    return {"MEX-ZAF": {"kickoff": "2026-06-11T21:00:00+00:00",
                        "home": {"team_id": 16, "team_name": "Mexico",
                                 "starting": [{"id": 900, "name": "Keeper", "pos": "G"}]},
                        "away": {"team_id": 99, "team_name": "South Africa", "starting": []}}}


def _streaks_alive():
    return [{"teamId": "MEX", "team": "Mexiko", "flag": "🇲🇽", "type": "scored",
             "venue": "all", "next": {"oppName": "USA", "date": "2026-07-10"}}]


class TestPlayerGoalStreaks(unittest.TestCase):
    def test_torserie_trailing_run(self):
        # 3 Tore in Folge (jüngste zuletzt), davor ein torloses Spiel
        recs = [_row(1, 16, "2026-06-01", goals=0), _row(1, 16, "2026-06-05", goals=1),
                _row(1, 16, "2026-06-09", goals=2), _row(1, 16, "2026-06-13", goals=1)]
        out = P.player_goal_streaks(recs, {16: "MEX"}, P.build_alive_map(_streaks_alive()))
        goals = [s for s in out if s["type"] == "goals"]
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["length"], 3)
        self.assertEqual(goals[0]["teamCode"], "MEX")

    def test_torbeteiligung_nur_wenn_laenger_als_torserie(self):
        # Tor nur im letzten, Assists davor → involvement (4) > goals (1)
        recs = [_row(1, 16, "2026-06-01", assists=1), _row(1, 16, "2026-06-05", assists=1),
                _row(1, 16, "2026-06-09", assists=1), _row(1, 16, "2026-06-13", goals=1)]
        out = P.player_goal_streaks(recs, {16: "MEX"}, P.build_alive_map(_streaks_alive()))
        types = {s["type"]: s["length"] for s in out}
        self.assertEqual(types.get("involvement"), 4)
        self.assertNotIn("goals", types)  # goals-Run nur 1 < MIN_GOALS_LEN(2)

    def test_ausgeschiedenes_team_raus(self):
        # Team MEX NICHT alive (leere alive-Map) → keine Serie
        recs = [_row(1, 16, "2026-06-05", goals=1), _row(1, 16, "2026-06-09", goals=1)]
        out = P.player_goal_streaks(recs, {16: "MEX"}, {})
        self.assertEqual(out, [])

    def test_run_bricht_bei_torlosem_spiel(self):
        recs = [_row(1, 16, "2026-06-05", goals=1), _row(1, 16, "2026-06-09", goals=0),
                _row(1, 16, "2026-06-13", goals=1)]
        out = P.player_goal_streaks(recs, {16: "MEX"}, P.build_alive_map(_streaks_alive()))
        self.assertEqual(out, [])  # jüngster Run nur 1 < MIN_GOALS_LEN


class TestTeamMaps(unittest.TestCase):
    def test_id_zu_code_und_gk(self):
        id2code, gk = P.build_team_maps(_lineups())
        self.assertEqual(id2code.get(16), "MEX")
        self.assertEqual(gk.get(16, {}).get("id"), 900)


class TestCleanSheet(unittest.TestCase):
    def test_zu_null_aus_team_serie(self):
        streaks = _streaks_alive() + [{"teamId": "MEX", "team": "Mexiko", "flag": "🇲🇽",
                                       "type": "cleanSheet", "venue": "all", "length": 3,
                                       "seq": [True, True, True],
                                       "next": {"oppName": "USA", "date": "2026-07-10"}}]
        id2code, gk = P.build_team_maps(_lineups())
        out = P.gk_cleansheet_streaks(streaks, id2code, gk, P.build_alive_map(streaks))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Keeper")
        self.assertEqual(out[0]["length"], 3)

    def test_venue_variante_ignoriert(self):
        streaks = _streaks_alive() + [{"teamId": "MEX", "type": "cleanSheet", "venue": "H",
                                       "length": 5, "next": {"oppName": "USA"}}]
        id2code, gk = P.build_team_maps(_lineups())
        out = P.gk_cleansheet_streaks(streaks, id2code, gk, P.build_alive_map(streaks))
        self.assertEqual(out, [])  # nur venue=all


class TestDigestElimination(unittest.TestCase):
    def test_ausgeschiedenes_team_nicht_im_digest(self):
        streaks = [
            {"teamId": "FRA", "team": "Frankreich", "type": "scored", "venue": "all", "length": 15,
             "continuation": {"state": "intakt"}, "next": {"oppName": "Marokko"}},
            {"teamId": "BRA", "team": "Brasilien", "type": "scored", "venue": "all", "length": 12,
             "continuation": {"state": "intakt"}, "next": None},  # ausgeschieden
        ]
        msg = TS.build_streaks_digest(streaks)
        self.assertIn("Frankreich", msg)
        self.assertNotIn("Brasilien", msg)

    def test_spieler_sektion_erscheint(self):
        players = [{"playerId": 1, "name": "Haaland", "team": "Norwegen", "flag": "🇳🇴",
                    "type": "goals", "length": 8, "next": {"oppName": "England"}}]
        msg = TS.build_streaks_digest([], players=players)
        self.assertIn("Spieler in Form", msg)
        self.assertIn("Haaland", msg)


if __name__ == "__main__":
    unittest.main()
