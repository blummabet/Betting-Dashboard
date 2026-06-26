#!/usr/bin/env python3
"""
test_fetch_liga_odds.py — Liga-Odds-Kern (25.06.2026, Lucas: Liga auf WM-Stack). Der wunde Punkt des
alten Liga-Frontends war das Team-Namens-Matching → hier robust getestet, plus Preis-Extraktion
(Heim/Auswärts korrekt, auch vertauscht) + Opening-Carry.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_odds as L  # noqa: E402


class TestNameMatch(unittest.TestCase):
    def test_norm_strips_rechtsform_accents(self):
        self.assertEqual(L._norm_name("Atlético Madrid"), "atletico madrid")
        self.assertEqual(L._norm_name("AC Milan"), "milan")
        self.assertEqual(L._norm_name("1. FC Köln"), "koln")

    def test_alias(self):
        self.assertEqual(L._norm_name("Internazionale"), "inter")
        self.assertEqual(L._norm_name("Wolverhampton Wanderers"), "wolves")

    def test_match_variants(self):
        self.assertTrue(L._names_match("Real Madrid", "Real Madrid CF"))
        self.assertTrue(L._names_match("Inter", "Internazionale"))
        self.assertTrue(L._names_match("Wolves", "Wolverhampton Wanderers"))
        self.assertTrue(L._names_match("Bayern München", "Bayern Munich"))

    def test_no_false_match(self):
        self.assertFalse(L._names_match("Real Madrid", "Real Sociedad"))
        self.assertFalse(L._names_match("Manchester City", "Manchester United"))


class TestEventMatch(unittest.TestCase):
    def _ev(self, h, a):
        return {"home_team": h, "away_team": a, "bookmakers": []}

    def test_direct(self):
        self.assertEqual(L.match_event_to_fixture(self._ev("Liverpool", "Chelsea"),
                                                  "Liverpool", "Chelsea"), "direct")

    def test_swapped(self):
        self.assertEqual(L.match_event_to_fixture(self._ev("Chelsea", "Liverpool"),
                                                  "Liverpool", "Chelsea"), "swapped")

    def test_none(self):
        self.assertIsNone(L.match_event_to_fixture(self._ev("Arsenal", "Chelsea"),
                                                   "Liverpool", "Everton"))


def _event_full(home, away):
    return {"home_team": home, "away_team": away, "bookmakers": [{
        "key": "pinnacle", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": home, "price": 1.80}, {"name": "Draw", "price": 3.6},
                {"name": away, "price": 4.5}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 2.5, "price": 1.95},
                {"name": "Under", "point": 2.5, "price": 1.90}]},
            {"key": "btts", "outcomes": [
                {"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}]},
        ]}]}


def _event_with_soft(home, away):
    # Pinnacle (sharp) + bet365 (soft) — für Public-Konsens-Extraktion.
    return {"home_team": home, "away_team": away, "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": 1.80}, {"name": "Draw", "price": 3.6},
            {"name": away, "price": 4.5}]}]},
        {"key": "bet365", "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": 1.70}, {"name": "Draw", "price": 3.7},
            {"name": away, "price": 5.0}]}]},
    ]}


class TestPublicConsensus(unittest.TestCase):
    def test_public_from_soft_book(self):
        p = L.extract_prices(_event_with_soft("Liverpool", "Chelsea"), "direct", "Liverpool", "Chelsea")
        self.assertEqual(p["hw"], 1.80)          # sharp = pinnacle
        self.assertEqual(p["public_hw"], 1.70)   # public = bet365
        self.assertEqual(p["public_bookmaker"], "bet365")

    def test_public_seeded_then_carried(self):
        pr1 = {"hw": 1.8, "dr": 3.6, "aw": 4.5, "bookmaker": "pinnacle",
               "public_hw": 1.7, "public_dr": 3.7, "public_aw": 5.0, "public_bookmaker": "bet365"}
        e1 = L.build_odds_entry(pr1, None, "2026-08-01T00:00:00Z")
        self.assertEqual(e1["public_hw_open"], 1.7)
        # Soft-Quote bewegt sich → Opening bleibt 1.7, public_hw aktualisiert
        pr2 = dict(pr1, public_hw=1.5)
        e2 = L.build_odds_entry(pr2, e1, "2026-08-10T00:00:00Z")
        self.assertEqual(e2["public_hw_open"], 1.7)
        self.assertEqual(e2["public_hw"], 1.5)


class TestExtractPrices(unittest.TestCase):
    def test_direct_mapping(self):
        p = L.extract_prices(_event_full("Liverpool", "Chelsea"), "direct", "Liverpool", "Chelsea")
        self.assertEqual((p["hw"], p["dr"], p["aw"]), (1.80, 3.6, 4.5))
        self.assertEqual((p["o25"], p["u25"]), (1.95, 1.90))
        self.assertEqual((p["bttsY"], p["bttsN"]), (1.85, 1.95))
        self.assertEqual(p["bookmaker"], "pinnacle")

    def test_swapped_mapping(self):
        # Event listet Chelsea als Heim — unser Fixture ist Liverpool(Heim) vs Chelsea
        ev = _event_full("Chelsea", "Liverpool")
        p = L.extract_prices(ev, "swapped", "Liverpool", "Chelsea")
        # Mapping per Name: Liverpool(unser Heim) hat im Event 4.5, Chelsea(unser Auswärts) 1.80.
        self.assertEqual(p["hw"], 4.5)   # Liverpool
        self.assertEqual(p["aw"], 1.80)  # Chelsea


class TestBuildEntry(unittest.TestCase):
    def test_opening_seeded_then_carried(self):
        e1 = L.build_odds_entry({"hw": 2.0, "dr": 3.4, "aw": 3.6, "bookmaker": "pinnacle"},
                                None, "2026-08-01T00:00:00Z")
        self.assertEqual(e1["odds_open"]["hw"], 2.0)
        # zweiter Lauf, Quote bewegt sich → Opening bleibt 2.0
        e2 = L.build_odds_entry({"hw": 1.7, "dr": 3.5, "aw": 4.5, "bookmaker": "pinnacle"},
                                e1, "2026-08-10T00:00:00Z")
        self.assertEqual(e2["odds_open"]["hw"], 2.0)   # Opening eingefroren
        self.assertEqual(e2["hw"], 1.7)                 # aktuelle Quote neu


if __name__ == "__main__":
    unittest.main()
