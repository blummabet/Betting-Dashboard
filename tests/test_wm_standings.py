#!/usr/bin/env python3
"""
test_wm_standings.py — Gruppentabellen-Builder + Best-Dritte-Ranking (17.06.2026).

Anlass: standings war leer → incentive_signal tot, pressure_index halb tot. Builder füllt
wm["standings"] aus beendeten Ergebnissen. WC-2026-Regel: Top 2 + 8 beste Dritte → R32.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_standings as W


def _g(teams, fixtures):
    return {"teams": [{"id": t} for t in teams], "fixtures": fixtures}


def _fx(md, h, a, hs, as_, status="FT"):
    return {"matchday": md, "home": h, "away": a,
            "result": {"status": status, "home_score": hs, "away_score": as_}}


class TestBuildStandings(unittest.TestCase):
    def test_points_and_order(self):
        groups = {"A": _g(["MEX", "ZAF", "KOR", "CZE"], [
            _fx(1, "MEX", "ZAF", 2, 0),   # MEX 3P
            _fx(1, "KOR", "CZE", 2, 1),   # KOR 3P (gd+1), CZE 0
        ])}
        st = W.build_standings(groups)["A"]
        self.assertEqual(st[0]["team"], "MEX")   # 3P, gd+2
        self.assertEqual(st[1]["team"], "KOR")   # 3P, gd+1
        self.assertEqual(st[0]["points"], 3)
        self.assertEqual(st[0]["gd"], 2)
        self.assertEqual(st[3]["team"], "ZAF")   # 0P, gd-2 letzter

    def test_unplayed_stays_zero(self):
        groups = {"L": _g(["CRO", "ENG", "GHA", "PAN"], [])}
        st = W.build_standings(groups)["L"]
        self.assertEqual(len(st), 4)
        self.assertTrue(all(r["played"] == 0 and r["points"] == 0 for r in st))

    def test_ignores_unfinished(self):
        groups = {"A": _g(["X", "Y"], [_fx(1, "X", "Y", 3, 0, status="1H")])}
        st = W.build_standings(groups)["A"]
        self.assertTrue(all(r["played"] == 0 for r in st))

    def test_draw(self):
        groups = {"A": _g(["X", "Y"], [_fx(1, "X", "Y", 1, 1)])}
        st = W.build_standings(groups)["A"]
        self.assertTrue(all(r["points"] == 1 and r["played"] == 1 for r in st))


class TestThirdRanking(unittest.TestCase):
    def test_top8_qualify(self):
        # 12 Gruppen, jeweils ein 3.-Platz mit absteigenden Punkten/GD
        standings = {}
        for i in range(12):
            gid = chr(ord("A") + i)
            # 3.-Platz bekommt punkte = 12-i (absteigend) → A bester Dritter
            standings[gid] = [
                {"team": f"{gid}1", "points": 9, "gd": 5, "gf": 6, "pos": 1},
                {"team": f"{gid}2", "points": 6, "gd": 2, "gf": 4, "pos": 2},
                {"team": f"{gid}3", "points": 12 - i, "gd": 0, "gf": 2, "pos": 3},
                {"team": f"{gid}4", "points": 0, "gd": -7, "gf": 0, "pos": 4},
            ]
        tr = W.rank_third_placed(standings)
        self.assertEqual(len(tr), 12)
        quali = [t["team"] for t in tr if t["qualifies"]]
        self.assertEqual(len(quali), 8)
        self.assertEqual(tr[0]["team"], "A3")        # bester Dritter
        self.assertFalse(tr[8]["qualifies"])         # 9. Dritter raus


if __name__ == "__main__":
    unittest.main()
