#!/usr/bin/env python3
"""
test_new_microstructure_signals.py — RLM-Proxy, Opener-Move, Multi-Book-Steam, Game-State
(09.07.2026, Lucas: neue Liga-Signale nach Experten-Konsultation — Fokus Mikrostruktur/Timing).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.reverse_line_move import ReverseLineMoveSignal
from sharp_signals.opener_move import OpenerMoveSignal
from sharp_signals.multi_book_steam import MultiBookSteamSignal
from sharp_signals.game_state_openness import GameStateOpennessSignal


class TestReverseLineMove(unittest.TestCase):
    sig = ReverseLineMoveSignal()

    def test_rlm_favor(self):
        # Pick Heim; Public meidet Heim (public_hw lang), Pinnacle zieht ZU Heim (kürzer als Opening)
        snap = {"hw": 1.80, "dr": 3.6, "aw": 4.5, "public_hw": 2.30, "public_dr": 3.4, "public_aw": 3.2,
                "odds_open": {"hw": 2.10, "dr": 3.5, "aw": 3.6}}
        r = self.sig.evaluate({"market": "Heimsieg"}, {"odds_snapshot": snap})
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_rlm_warn(self):
        # Pick Heim; Public überbettet Heim (public_hw kurz), Pinnacle zieht WEG (länger als Opening)
        snap = {"hw": 2.10, "dr": 3.5, "aw": 3.4, "public_hw": 1.75, "public_dr": 3.6, "public_aw": 4.6,
                "odds_open": {"hw": 1.85, "dr": 3.6, "aw": 4.2}}
        r = self.sig.evaluate({"market": "Heimsieg"}, {"odds_snapshot": snap})
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_no_move_no_signal(self):
        snap = {"hw": 1.90, "dr": 3.5, "aw": 4.0, "public_hw": 1.92, "public_dr": 3.5, "public_aw": 3.95,
                "odds_open": {"hw": 1.90, "dr": 3.5, "aw": 4.0}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, {"odds_snapshot": snap}))


class TestOpenerMove(unittest.TestCase):
    sig = OpenerMoveSignal()

    def test_early_move_fires(self):
        hist = [
            {"ts": "2026-08-10T08:00:00+00:00", "bk": "pinnacle", "hw": 2.10, "dr": 3.5, "aw": 3.5},
            {"ts": "2026-08-10T14:00:00+00:00", "bk": "pinnacle", "hw": 1.85, "dr": 3.6, "aw": 4.2},
            {"ts": "2026-08-11T20:00:00+00:00", "bk": "pinnacle", "hw": 1.80, "dr": 3.6, "aw": 4.4},
        ]
        r = self.sig.evaluate({"market": "Heimsieg"}, {"odds_history": hist})
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_no_early_move(self):
        hist = [
            {"ts": "2026-08-10T08:00:00+00:00", "bk": "pinnacle", "hw": 1.85, "dr": 3.6, "aw": 4.2},
            {"ts": "2026-08-10T14:00:00+00:00", "bk": "pinnacle", "hw": 1.86, "dr": 3.6, "aw": 4.1},
        ]
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, {"odds_history": hist}))


class TestMultiBookSteam(unittest.TestCase):
    sig = MultiBookSteamSignal()

    def test_two_sharps_agree(self):
        # Pinnacle + Betfair beide kürzer (höhere Heim-Wkt) als Public → korroboriert
        snap = {"hw": 1.80, "dr": 3.6, "aw": 4.6, "bf_hw": 1.83, "bf_dr": 3.6, "bf_aw": 4.5,
                "public_hw": 2.15, "public_dr": 3.5, "public_aw": 3.4}
        r = self.sig.evaluate({"market": "Heimsieg"}, {"odds_snapshot": snap})
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_only_one_sharp_no_signal(self):
        # Nur Pinnacle divergiert, Betfair ~= Public → keine Korroboration
        snap = {"hw": 1.80, "dr": 3.6, "aw": 4.6, "bf_hw": 2.15, "bf_dr": 3.5, "bf_aw": 3.4,
                "public_hw": 2.15, "public_dr": 3.5, "public_aw": 3.4}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, {"odds_snapshot": snap}))


def _standings():
    pts = {1: 76, 2: 73, 3: 66, 4: 63, 5: 60, 6: 58, 7: 55, 8: 50, 9: 45, 10: 40,
           11: 38, 12: 36, 13: 34, 14: 32, 15: 30, 16: 28, 17: 24, 18: 20, 19: 18, 20: 15}
    return [{"team": f"T{i}", "pos": i, "points": pts[i]} for i in range(1, 21)]


class TestGameStateOpenness(unittest.TestCase):
    sig = GameStateOpennessSignal()

    def _ctx(self):
        return {"group_id": "ENG", "matchday": 35, "standings": {"ENG": _standings()},
                "home_id": "T2", "away_id": "T10"}   # T2 Titel-Muss-Sieg, T10 dead

    def test_asymmetric_desperation_over(self):
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, self._ctx())
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_btts_fires_too(self):
        r = self.sig.evaluate({"market": "Beide Teams treffen — Ja"}, self._ctx())
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_under_no_signal(self):
        self.assertIsNone(self.sig.evaluate({"market": "Unter 2.5 Tore"}, self._ctx()))

    def test_early_season_quiet(self):
        ctx = self._ctx(); ctx["matchday"] = 3
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx))


if __name__ == "__main__":
    unittest.main()
