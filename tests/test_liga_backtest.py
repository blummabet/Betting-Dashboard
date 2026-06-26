#!/usr/bin/env python3
"""
test_liga_backtest.py — Pilot-Backtest-Kerne (26.06.2026, Lucas). Rekonstruktion (Form/Tabelle),
market_won, replay (point-in-time + Warmup) + Aggregation. Engine injiziert → kein API/keine echten Signale.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import liga_backtest as B  # noqa: E402


class TestMarketWon(unittest.TestCase):
    def test_all(self):
        self.assertTrue(B.market_won("Heimsieg", 2, 0))
        self.assertFalse(B.market_won("Heimsieg", 1, 1))
        self.assertTrue(B.market_won("Auswärtssieg", 0, 1))
        self.assertTrue(B.market_won("Über 2.5 Tore", 2, 1))
        self.assertFalse(B.market_won("Über 2.5 Tore", 1, 1))
        self.assertTrue(B.market_won("Unter 2.5 Tore", 1, 1))


class TestForm(unittest.TestCase):
    def test_form_entry_avg_last_n(self):
        # 6 Spiele → nur die letzten 5 zählen
        res = [(1, 0), (2, 2), (0, 3), (1, 1), (3, 0), (2, 1)]
        f = B.form_entry(res)
        self.assertEqual(f["games"], 5)
        self.assertAlmostEqual(f["avgScored"], (2 + 0 + 1 + 3 + 2) / 5, places=2)

    def test_empty(self):
        self.assertEqual(B.form_entry([])["games"], 0)


class TestStandings(unittest.TestCase):
    def test_pos_by_points_then_gd(self):
        table = {"A": {"points": 9, "gf": 8, "ga": 2},
                 "B": {"points": 9, "gf": 5, "ga": 4},   # gleiche Pkt, schlechtere GD
                 "C": {"points": 3, "gf": 2, "ga": 6}}
        rows = B.standings_rows(table)
        self.assertEqual([r["team"] for r in rows], ["A", "B", "C"])
        self.assertEqual(rows[0]["pos"], 1)


class TestReplay(unittest.TestCase):
    def test_warmup_and_ledger(self):
        # Fake-Engine: „mag" Heimsieg immer (score +1), sonst 0.
        def fake(pick, ctx):
            sc = 1.0 if pick["market"] == "Heimsieg" else 0.0
            return {"signals": [{"name": "fake_home", "score": sc}]}
        # 5 Spiele Team X vs wechselnde Gegner, X gewinnt immer 1:0
        matches = [{"home": "X", "away": g, "hs": 1, "as_": 0, "matchday": i + 1}
                   for i, g in enumerate(["A", "B", "C", "D", "E"])]
        # Gegner brauchen auch Historie → künstlich: jeder Gegner hat vorab 4 Spiele
        warm = []
        for g in ["A", "B", "C", "D", "E", "X"]:
            for _ in range(4):
                warm.append({"home": g, "away": "Z", "hs": 1, "as_": 1, "matchday": 0})
        led = B.replay(warm + matches, fake)
        # Nach Warmup feuert fake_home auf Heimsieg → won=True (X gewinnt 1:0)
        home_calls = [e for e in led if e["signal"] == "fake_home" and e["market"] == "Heimsieg"
                      and e["score"] > 0]
        self.assertTrue(len(home_calls) >= 5)
        self.assertTrue(all(e["won"] for e in home_calls if e["market"] == "Heimsieg"))

    def test_aggregate_hitrate(self):
        ledger = [{"signal": "s", "market": "Heimsieg", "score": 1.0, "won": True},
                  {"signal": "s", "market": "Heimsieg", "score": 1.0, "won": False},
                  {"signal": "s", "market": "Heimsieg", "score": 1.0, "won": True},
                  {"signal": "s", "market": "Heimsieg", "score": 0.1, "won": False}]  # zu klein → ignoriert
        agg = B.aggregate(ledger)
        self.assertEqual(agg["perSignal"]["s"]["calls"], 3)
        self.assertAlmostEqual(agg["perSignal"]["s"]["hitRate"], round(2 / 3, 3), places=3)


class TestPhase2(unittest.TestCase):
    def test_xg_entry_real_vs_fallback(self):
        self.assertEqual(B.xg_entry([(1.2, 0.8), (1.5, 1.0)])["source"], "none")   # <3 → kein echtes xG
        e = B.xg_entry([(1.2, 0.8), (1.5, 1.0), (2.0, 0.5)])
        self.assertEqual(e["source"], "apif_real")
        self.assertAlmostEqual(e["xgForAvg"], (1.2 + 1.5 + 2.0) / 3, places=2)

    def test_fd_date_iso(self):
        self.assertEqual(B._fd_date_iso("15/08/2025"), "2025-08-15")
        self.assertEqual(B._fd_date_iso("05/01/26"), "2026-01-05")

    def test_parse_fd_csv(self):
        csv = ("Date,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
               "15/08/2025,Liverpool,Chelsea,1.80,3.60,4.50,1.95,1.90\n")
        rows = B.parse_fd_csv(csv)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["oddsH"], rows[0]["o25"]), (1.80, 1.95))

    def test_attach_odds_matches(self):
        matches = [{"date": "2025-08-15T14:00:00+00:00", "homeName": "Liverpool", "awayName": "Chelsea"}]
        fd = [{"date": "15/08/2025", "home": "Liverpool", "away": "Chelsea",
               "oddsH": 1.8, "oddsD": 3.6, "oddsA": 4.5, "o25": 1.95, "u25": 1.9}]
        n = B.attach_odds(matches, fd)
        self.assertEqual(n, 1)
        self.assertEqual(matches[0]["odds"]["Heimsieg"], 1.8)

    def test_aggregate_roi(self):
        # 2 positive Calls auf Heimsieg @2.0: 1 gewonnen (+1.0), 1 verloren (-1.0) → ROI 0%
        led = [{"signal": "s", "market": "Heimsieg", "score": 1.0, "won": True, "odds": 2.0},
               {"signal": "s", "market": "Heimsieg", "score": 1.0, "won": False, "odds": 2.0}]
        agg = B.aggregate(led)
        self.assertEqual(agg["perSignal"]["s"]["bets"], 2)
        self.assertEqual(agg["perSignal"]["s"]["roiPct"], 0.0)


if __name__ == "__main__":
    unittest.main()
