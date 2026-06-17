#!/usr/bin/env python3
"""
test_safer_line_derivation.py — Phase-1 Safer-Line-Ableitung (17.06.2026, Lucas).

Ein riskanter Steam-Pick (Über 3.5, Heimsieg) wird auf die nächst-sichere Linie als WETTE
umgelegt — SOLANGE deren Quote ≥ 1.35 bleibt. Sonst Original. Move bleibt These.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G


def _card(market, odds):
    return {"market": market, "odds": odds, "modelOdds": odds, "edgePP": 0,
            "info": "📉 Move", "source": "steam"}


class TestSaferLineDerivation(unittest.TestCase):
    def test_over35_to_over25(self):
        snap = {"o25": 1.64, "u25": 2.3, "o35": 2.59, "u35": 1.5}
        out = G._derive_safer_steam_line(_card("Über 3.5 Tore", 2.59), snap)
        self.assertTrue(out["safeDerived"])
        self.assertEqual(out["market"], "Über 2.5 Tore")
        self.assertEqual(out["odds"], 1.64)
        self.assertEqual(out["safeThesisMarket"], "Über 3.5 Tore")
        self.assertEqual(out["safeThesisOdds"], 2.59)

    def test_heimsieg_to_dc1x(self):
        snap = {"hw": 2.75, "dr": 3.4, "aw": 2.6, "dc1X": 1.53}
        out = G._derive_safer_steam_line(_card("Heimsieg", 2.75), snap)
        self.assertTrue(out["safeDerived"])
        self.assertEqual(out["market"], "Doppelte Chance — 1X")
        self.assertEqual(out["odds"], 1.53)

    def test_floor_keeps_original_totals(self):
        # sichere Linie unter 1.35 → Original behalten
        snap = {"o25": 1.20, "o35": 2.0}
        out = G._derive_safer_steam_line(_card("Über 3.5 Tore", 2.0), snap)
        self.assertFalse(out.get("safeDerived"))
        self.assertEqual(out["market"], "Über 3.5 Tore")

    def test_floor_keeps_original_homewin(self):
        # DC 1X unter 1.35 (starker Favorit) → Heimsieg bleibt (Lucas' Beispiel)
        snap = {"hw": 1.30, "dr": 5.0, "aw": 9.0, "dc1X": 1.10}
        out = G._derive_safer_steam_line(_card("Heimsieg", 1.30), snap)
        self.assertFalse(out.get("safeDerived"))
        self.assertEqual(out["market"], "Heimsieg")

    def test_exactly_135_switches(self):
        # genau 1.35 → wechselt (≥ 1.35)
        snap = {"o25": 1.35, "o35": 1.91}
        out = G._derive_safer_steam_line(_card("Über 3.5 Tore", 1.91), snap)
        self.assertTrue(out["safeDerived"])
        self.assertEqual(out["odds"], 1.35)

    def test_no_mapping_unchanged(self):
        # AH/BTTS haben keine Safer-Mapping (Phase 2) → unverändert
        snap = {"o25": 1.5}
        out = G._derive_safer_steam_line(_card("AH Heim -1.5", 2.6), snap)
        self.assertFalse(out.get("safeDerived"))
        self.assertEqual(out["market"], "AH Heim -1.5")

    def test_safe_line_missing_keeps_original(self):
        # sichere Linien-Quote fehlt im snap → Original
        out = G._derive_safer_steam_line(_card("Über 3.5 Tore", 2.59), {"o35": 2.59})
        self.assertFalse(out.get("safeDerived"))

    def test_safe_not_lower_keeps_original(self):
        # sichere Linie nicht echt niedriger (degeneriert) → Original
        snap = {"o25": 2.80, "o35": 2.59}
        out = G._derive_safer_steam_line(_card("Über 3.5 Tore", 2.59), snap)
        self.assertFalse(out.get("safeDerived"))


if __name__ == "__main__":
    unittest.main()
