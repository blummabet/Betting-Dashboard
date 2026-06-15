#!/usr/bin/env python3
"""
test_poly_handicap.py — Poly-Handicap-Edges (15.06.2026).

Polymarket bietet Spread-Märkte (Team (-1.5), Team (-2.5)). fetch_wm_poly_prices
parst sie + de-viggt fair aus der Pinnacle-AH-Leiter (nach HEIM-Linie geschlüsselt).
Nur EXAKTE Linien-Treffer → kein mismatched-line-Edge.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_poly_prices as f


class TestAhEdges(unittest.TestCase):
    def setUp(self):
        # CAN-QAT echte Pinnacle-Leiter (Heim-Favorit): [home_odds, away_odds]
        self.ladder = {"-1.5": [1.77, 2.05], "-2.5": [3.05, 1.36], "-0.5": [1.24, 4.1]}

    def test_home_handicap_edge_exact_line(self):
        poly_home = {-1.5: {"yes": 0.50, "tokens": ["tk15"]}}
        edges = f.compute_ah_edges(poly_home, {}, self.ladder)
        self.assertEqual(len(edges), 1)
        e = edges[0]
        # fair = devig(1.77, 2.05) ≈ 0.5366 → edge ≈ +3.7pp
        self.assertAlmostEqual(e["fair"], 0.5366, places=3)
        self.assertAlmostEqual(e["edge"], 3.7, places=1)
        self.assertEqual(e["side"], "home")
        self.assertEqual(e["tokens"], ["tk15"])

    def test_away_handicap_maps_to_positive_home_line(self):
        # Away covers -1.5 = Heim +1.5 → ladder key "1.5" (hier NICHT vorhanden) → skip
        edges = f.compute_ah_edges({}, {-1.5: {"yes": 0.4, "tokens": ["a"]}}, self.ladder)
        self.assertEqual(edges, [])
        # mit +1.5 in der Leiter → away-Edge wird berechnet
        ladder2 = {**self.ladder, "1.5": [2.05, 1.77]}  # home +1.5, away -1.5
        edges2 = f.compute_ah_edges({}, {-1.5: {"yes": 0.50, "tokens": ["a"]}}, ladder2)
        self.assertEqual(len(edges2), 1)
        self.assertEqual(edges2[0]["side"], "away")
        # fair away = devig(away_odds=1.77, home_odds=2.05) ≈ 0.5366
        self.assertAlmostEqual(edges2[0]["fair"], 0.5366, places=3)

    def test_missing_line_skipped(self):
        # Poly-Linie -3.5, Pinnacle hat sie nicht → übersprungen (kein Schätzen)
        edges = f.compute_ah_edges({-3.5: {"yes": 0.2, "tokens": ["x"]}}, {}, self.ladder)
        self.assertEqual(edges, [])

    def test_no_yes_price_skipped(self):
        edges = f.compute_ah_edges({-1.5: {"yes": None, "tokens": ["x"]}}, {}, self.ladder)
        self.assertEqual(edges, [])

    def test_devig_2way(self):
        self.assertAlmostEqual(f._devig_2way(1.77, 2.05), 0.5366, places=3)
        self.assertIsNone(f._devig_2way(1.0, 2.0))   # ungültige Quote
        self.assertIsNone(f._devig_2way(None, 2.0))

    def test_mirror_immune_team_id_lookup(self):
        # Mirror-Bug-Regression (15.06.2026): Poly listet ENG-PAN als PAN-ENG.
        # Spreads team-ID-geschlüsselt → richtige Seite trotz Spiegelung.
        spreads = {"England": {-1.5: {"yes": 0.54, "tokens": ["eng"]}},
                   "Panama":  {-1.5: {"yes": 0.0235, "tokens": ["pan"]}}}
        by_team = {tid: lines for team, lines in spreads.items()
                   if (tid := f.resolve_team_id(team))}
        self.assertEqual(set(by_team), {"ENG", "PAN"})
        # Fixture ENG-PAN: home=ENG → Englands Spread (0.54), NICHT Panamas 0.0235
        ladder = {"-1.5": [1.45, 2.7]}
        edges = f.compute_ah_edges(by_team.get("ENG", {}), by_team.get("PAN", {}), ladder)
        home = [e for e in edges if e["side"] == "home"][0]
        self.assertEqual(home["poly"], 0.54)        # Englands Preis, nicht Panamas
        self.assertEqual(home["tokens"], ["eng"])   # Englands Token


if __name__ == "__main__":
    unittest.main()
