#!/usr/bin/env python3
"""test_topscorer_momentum.py — Top-Torjäger-Signal (26.06.2026). Fetcher-Extraktion (treffsicherster
je Team) + Bedrohungs-Metrik + Boost auf Sieg/Über, Schläfer ohne Daten."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_topscorers as F  # noqa: E402
from sharp_signals.topscorer_momentum import TopscorerMomentumSignal, threat  # noqa: E402

SIG = TopscorerMomentumSignal()


class TestFetcherExtract(unittest.TestCase):
    def test_keeps_best_per_team(self):
        resp = [
            {"player": {"name": "Haaland"}, "statistics": [{"team": {"id": 50},
             "goals": {"total": 20}, "games": {"appearences": 25}}]},
            {"player": {"name": "Foden"}, "statistics": [{"team": {"id": 50},
             "goals": {"total": 8}, "games": {"appearences": 25}}]},
            {"player": {"name": "Salah"}, "statistics": [{"team": {"id": 40},
             "goals": {"total": 18}, "games": {"appearences": 26}}]},
        ]
        out = F.extract_team_topscorers(resp)
        self.assertEqual(out["50"]["name"], "Haaland")   # höhere Toranzahl gewinnt
        self.assertEqual(out["40"]["goals"], 18.0)


class TestThreat(unittest.TestCase):
    def test_gpg_normalised(self):
        self.assertEqual(threat({"goals": 14, "appearances": 20}), round(min(1.0, 0.7 / 0.7), 3))
        self.assertEqual(threat({"goals": 2, "appearances": 2}), 0.0)   # unter MIN_APPS
        self.assertEqual(threat({}), 0.0)


class TestEvaluate(unittest.TestCase):
    def _ctx(self, ts):
        return {"topscorers": ts, "home_id": "H", "away_id": "A"}

    def test_boost_home_with_scorer(self):
        ts = {"H": {"name": "X", "goals": 18, "appearances": 22}, "A": {"goals": 0, "appearances": 20}}
        res = SIG.evaluate({"market": "Heimsieg"}, self._ctx(ts))
        self.assertIsNotNone(res)
        self.assertGreater(res.score, 0)

    def test_over_with_two_scorers(self):
        ts = {"H": {"goals": 16, "appearances": 20}, "A": {"goals": 15, "appearances": 20}}
        res = SIG.evaluate({"market": "Über 2.5 Tore"}, self._ctx(ts))
        self.assertIsNotNone(res)
        self.assertGreater(res.score, 0)

    def test_no_data_none(self):
        self.assertIsNone(SIG.evaluate({"market": "Heimsieg"}, self._ctx({})))

    def test_under_skipped(self):
        ts = {"H": {"goals": 16, "appearances": 20}, "A": {"goals": 15, "appearances": 20}}
        self.assertIsNone(SIG.evaluate({"market": "Unter 2.5 Tore"}, self._ctx(ts)))


if __name__ == "__main__":
    unittest.main()
