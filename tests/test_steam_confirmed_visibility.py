#!/usr/bin/env python3
"""
test_steam_confirmed_visibility.py — Bestätigte Steam-Moves bleiben sichtbar (17.06.2026).

Lucas' Sorge: ein Pinnacle-Move, der von Soft-Quoten bestätigt wird (Quote läuft
1.90 → 1.65 in unsere Richtung), konvergiert die Karten-Edge auf ~0 → der Pick wurde
bisher per `edgePP < min_edge` rausgefiltert. Damit verschwand genau die Wette, die die
Steam-These bestätigt. Fix: clvPP ≥ STEAM_CONFIRM_PP hält den Pick sichtbar (Badge
„Move bestätigt"), ohne ihn als frische Value-Wette zu präsentieren.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G


def _steam_confirmed(verdict_res):
    """Spiegelt die Inline-Bedingung in generate_wm_picks (Pick-Loop)."""
    return (verdict_res.get("clvPP", 0.0) >= G.STEAM_CONFIRM_PP
            and verdict_res["edgePP"] >= -10)


class TestSteamConfirmedVisibility(unittest.TestCase):
    def test_clv_pp_measures_line_move(self):
        # Quote 1.90 → 1.65: implied prob steigt ~+8pp → clvPP stark positiv
        v = G.compute_verdict(1.70, 1.65, 1.90, None, "under25")
        self.assertGreaterEqual(v["clvPP"], G.STEAM_CONFIRM_PP)

    def test_confirmed_converged_stays_visible(self):
        # Linie lief in unsere Richtung (open 1.90 → now 1.65), Modell ~fair → Edge klein/negativ
        v = G.compute_verdict(1.70, 1.65, 1.90, None, "under25")
        self.assertTrue(_steam_confirmed(v))   # bleibt sichtbar trotz konvergierter Edge

    def test_weak_move_not_confirmed(self):
        # nur leichte Bewegung (1.72 → 1.68) → clvPP < Schwelle → kein Steam-Confirmed
        v = G.compute_verdict(1.70, 1.68, 1.72, None, "under25")
        self.assertLess(v["clvPP"], G.STEAM_CONFIRM_PP)
        self.assertFalse(_steam_confirmed(v))

    def test_overshoot_not_confirmed(self):
        # Linie weit über fair geschossen → edge tief negativ (< −10) → NICHT als Ritt zeigen
        fake = {"clvPP": 6.0, "edgePP": -14}
        self.assertFalse(_steam_confirmed(fake))

    def test_threshold_is_configurable(self):
        self.assertIsInstance(G.STEAM_CONFIRM_PP, (int, float))
        self.assertGreater(G.STEAM_CONFIRM_PP, 0)


if __name__ == "__main__":
    unittest.main()
