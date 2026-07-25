#!/usr/bin/env python3
"""
test_league_pressure.py — Liga-Druck-Signal (25.06.2026, Lucas). Prüft: früh in der Saison 0
(Schläfer), Endspurt rampt hoch, Abstiegskämpfer→Sieg-Druck, gesichertes Mittelfeld→dead,
Dead-Rubber→Unter, beidseitig-Muss kein Über-Boost.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.league_pressure import (LeaguePressureSignal, team_pressure,
                                           _time_factor, LEAGUE_META)  # noqa: E402
from sharp_signals.base import market_side as _market_side  # noqa: E402  (konsolidiert in base)


def _standings20():
    # 20 Teams, Platz 1 = 80 Pkt, fallend; Mittelfeld dicht, Abstiegsplätze knapp.
    rows = []
    pts = [80, 70, 65, 62, 60, 58, 55, 50, 45, 44, 43, 42, 41, 40, 39, 38, 30, 28, 27, 20]
    for i, p in enumerate(pts):
        rows.append({"team": f"T{i+1}", "pos": i + 1, "points": p, "gd": 0})
    return rows


def _ctx(home, away, matchday, rows):
    return {"group_id": "ENG", "standings": {"ENG": rows},
            "matchday": matchday, "home_id": home, "away_id": away}


class TestHelpers(unittest.TestCase):
    def test_time_factor_early_zero(self):
        self.assertEqual(_time_factor(33, 38), 0.0)   # früh = 0

    def test_time_factor_late_high(self):
        self.assertGreater(_time_factor(3, 38), 0.7)   # Endspurt = hoch

    def test_market_side(self):
        self.assertEqual(_market_side("Heimsieg"), "home")
        self.assertEqual(_market_side("Auswärtssieg"), "away")
        self.assertEqual(_market_side("Unter 2.5 Tore"), "under")
        self.assertIsNone(_market_side("Beide Teams treffen — Ja"))


class TestTeamPressure(unittest.TestCase):
    def setUp(self):
        self.rows = _standings20()
        self.meta = LEAGUE_META["ENG"]

    def test_early_season_zero(self):
        # rounds_left 33 → tf 0 → kein Druck egal welcher Platz
        p, m, b = team_pressure(self.rows[17], self.rows, self.meta, 33)
        self.assertEqual(p, 0.0)

    def test_relegation_battle_late_wins(self):
        # Platz 18 (T18, 28 Pkt), 3 Runden offen → muss Punkte holen → win
        p, m, b = team_pressure(self.rows[17], self.rows, self.meta, 3)
        self.assertEqual(m, "win")
        self.assertGreater(p, 0.0)

    def test_secured_midtable_dead(self):
        # Mittelfeld gesichert (Platz 10), nichts mehr zu spielen → dead
        p, m, b = team_pressure(self.rows[9], self.rows, self.meta, 3)
        self.assertEqual(m, "dead")


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.sig = LeaguePressureSignal()
        self.rows = _standings20()

    def test_early_season_none(self):
        r = self.sig.evaluate({"market": "Heimsieg"}, _ctx("T18", "T10", 5, self.rows))
        self.assertIsNone(r)   # Schläfer

    def test_relegation_home_late_positive(self):
        # Heim T18 (Abstiegskampf) vs Auswärts T10 (gesichert), Runde 35
        r = self.sig.evaluate({"market": "Heimsieg"}, _ctx("T18", "T10", 35, self.rows))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_dead_rubber_under(self):
        # beide gesichertes Mittelfeld (T9 vs T10), spät → Unter-Boost
        r = self.sig.evaluate({"market": "Unter 2.5 Tore"}, _ctx("T9", "T10", 36, self.rows))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_no_over_boost(self):
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, _ctx("T18", "T10", 36, self.rows))
        self.assertIsNone(r)   # kein automatischer Über-Boost (Lucas-Nuance)

    def test_wm_group_noop(self):
        # WM-Gruppe (group_id 'A') nicht in LEAGUE_META → None
        ctx = {"group_id": "A", "standings": {"A": self.rows}, "matchday": 3,
               "home_id": "T1", "away_id": "T2"}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))


if __name__ == "__main__":
    unittest.main()
