#!/usr/bin/env python3
"""test_steam_edge.py — ehrlicher Steam-Edge (25.07.2026).
Sichert den zentralisierten _steam_edge_pp: Break-Even = 1/odds (kein x1.03),
AH (model=None) = ehrlich 0."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G


class TestSteamEdge(unittest.TestCase):
    def test_ah_none_model_is_honest_zero(self):
        # AH: _steam_model_odds gibt None -> keine eigene Fair-Linie -> Edge ehrlich 0
        self.assertEqual(G._steam_edge_pp(None, 1.90), 0)

    def test_invalid_inputs_zero(self):
        self.assertEqual(G._steam_edge_pp(2.0, 1.0), 0)
        self.assertEqual(G._steam_edge_pp(1.0, 2.0), 0)
        self.assertEqual(G._steam_edge_pp(0, 2.0), 0)

    def test_break_even_is_one_over_odds_no_vig_multiplier(self):
        # model==entry: Edge = (0.96/2 - 1/2)*100 = -2pp (nur MODEL_MARGIN, KEIN x1.03).
        # Die alte Formel gab (0.96/2 - 1.03/2)*100 = -3.5 -> round -4. Neu = -2.
        self.assertEqual(G._steam_edge_pp(2.0, 2.0), -2)

    def test_positive_edge_when_model_shorter(self):
        # Modell-Fair kuerzer als gespielte Quote -> positiver Edge.
        # (0.96/1.8 - 1/2.0)*100 = (0.5333-0.5)*100 = 3.33 -> 3
        self.assertEqual(G._steam_edge_pp(1.8, 2.0), 3)

    def test_no_1_03_multiplier_in_live_sites(self):
        # Regressionswaechter: die Live-Steam-Edge darf das x1.03 nicht wieder einschmuggeln.
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        # In _steam_edge_pp und den 3 Call-Sites kein '* 1.03'. Legacy compute_verdict ist separat.
        after_helper = src.split("def _steam_edge_pp", 1)[1]
        # bis zum naechsten grossen Abschnitt (Reverser-Map) schauen — deckt die 3 Sites ab
        live_region = after_helper.split("_REVERSER_COUNTER_MAP", 1)[0]
        self.assertNotIn("* 1.03", live_region)


if __name__ == "__main__":
    # ohne pytest lauffaehig
    unittest.main(verbosity=2)
