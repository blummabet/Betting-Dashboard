#!/usr/bin/env python3
"""
test_detect_pick_changes_reason.py — Banner-Text-Korrektheit

Bug 07.06.2026: Bei Edge-Delta ohne Quote-Änderung zeigte der Banner
"Edge +3pp (3.45 → 3.45)" — das wirkt wie ein Bug obwohl es ein Modell-Update
ist (Form-/xG-Refresh). Fix: bei `abs(odds_delta) < 0.005` zeigen wir explizit
"Edge +3pp · Modell-Update @3.45" damit der User sofort versteht was passiert.

Regression-Test damit der Banner-Text nicht zurückrutscht.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import detect_pick_changes as mod


class TestEdgeChangeReason(unittest.TestCase):
    """_diff_pick() reason-String muss bei identischer Quote anders aussehen."""

    def _diff(self, old_edge, new_edge, old_odds, new_odds, verdict="BET"):
        old = {"verdict": verdict, "edgePP": old_edge, "odds": old_odds, "trackingExcluded": False}
        new = {"verdict": verdict, "edgePP": new_edge, "odds": new_odds, "trackingExcluded": False}
        return mod._make_reason(old, new)

    def test_edge_up_with_identical_odds_says_modell_update(self):
        """Identische Quote (3.45 → 3.45), +3pp Edge → 'Modell-Update'-Label."""
        kind, reason = self._diff(old_edge=4, new_edge=7, old_odds=3.45, new_odds=3.45)
        self.assertEqual(kind, "edge_up")
        self.assertIn("Modell-Update", reason,
            f"Bei identischer Quote muss 'Modell-Update' im Text sein — bekam: {reason}")
        self.assertIn("3.45", reason)
        self.assertNotIn("3.45 → 3.45", reason,
            "Identische Quoten zweimal anzeigen ist irreführend")

    def test_edge_up_with_real_quote_movement_shows_arrow(self):
        """Echte Quote-Bewegung (1.83 → 1.95) zeigt weiterhin Pfeil-Format."""
        kind, reason = self._diff(old_edge=4, new_edge=8, old_odds=1.83, new_odds=1.95)
        self.assertEqual(kind, "edge_up")
        self.assertIn("1.83 → 1.95", reason)
        self.assertNotIn("Modell-Update", reason)

    def test_edge_down_with_tiny_movement_treated_as_market(self):
        """Quote-Drop 1.61 → 1.60 ist > 0.005 → klassisches Pfeil-Format."""
        kind, reason = self._diff(old_edge=-3, new_edge=-6, old_odds=1.61, new_odds=1.60)
        self.assertEqual(kind, "edge_down")
        self.assertIn("1.61 → 1.60", reason)
        self.assertNotIn("Modell-Update", reason)

    def test_edge_floored_rounding_still_caught(self):
        """Quote 3.451 → 3.453 wird gerundet auf 3.45, beide Mal — Modell-Update."""
        kind, reason = self._diff(old_edge=5, new_edge=9, old_odds=3.451, new_odds=3.453)
        self.assertEqual(kind, "edge_up")
        self.assertIn("Modell-Update", reason)


if __name__ == "__main__":
    unittest.main()
