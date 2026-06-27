#!/usr/bin/env python3
"""test_fetch_liga_elo.py — Club-Elo (26.06.2026). CSV-Parse + Namens-Match inkl. ClubElo-Kurznamen
und Länder-Einschränkung. Elo NUR als Team-Feld (kein Pick-Pfad)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_elo as E  # noqa: E402

CSV = ("Rank,Club,Country,Level,Elo,From,To\n"
       "1,Man City,ENG,1,2024.5,2026-06-22,2026-06-28\n"
       "2,Bayern,GER,1,1990.2,2026-06-22,2026-06-28\n"
       "3,Real Madrid,ESP,1,2010.0,2026-06-22,2026-06-28\n"
       "4,Inter,ITA,1,1955.9,2026-06-22,2026-06-28\n"
       "5,Paris SG,FRA,1,1999.1,2026-06-22,2026-06-28\n"
       "6,BadRow,ENG,1,,2026-06-22,2026-06-28\n")


class TestParse(unittest.TestCase):
    def test_parse_skips_bad_elo(self):
        rows = E.parse_clubelo_csv(CSV)
        self.assertEqual(len(rows), 5)  # BadRow (leere Elo) raus
        self.assertEqual(rows[0], {"club": "Man City", "country": "ENG", "elo": 2024})


class TestMatch(unittest.TestCase):
    def setUp(self):
        self.rows = E.parse_clubelo_csv(CSV)

    def test_alias_abbrev(self):
        teams = [{"id": "1", "name": "Manchester City"}]
        self.assertEqual(E.match_elo(teams, self.rows, "ENG"), {"1": 2024})

    def test_bayern_alias(self):
        teams = [{"id": "9", "name": "Bayern München"}]
        self.assertEqual(E.match_elo(teams, self.rows, "GER"), {"9": 1990})

    def test_psg_alias(self):
        teams = [{"id": "7", "name": "Paris Saint Germain"}]
        self.assertEqual(E.match_elo(teams, self.rows, "FRA"), {"7": 1999})

    def test_country_restriction_blocks_cross(self):
        # Englisches Team gegen ESP-Land gefiltert → kein Treffer
        teams = [{"id": "1", "name": "Manchester City"}]
        self.assertEqual(E.match_elo(teams, self.rows, "ESP"), {})

    def test_unmatched_returns_empty(self):
        teams = [{"id": "99", "name": "Sligo Rovers"}]
        self.assertEqual(E.match_elo(teams, self.rows, "ENG"), {})


if __name__ == "__main__":
    unittest.main()
