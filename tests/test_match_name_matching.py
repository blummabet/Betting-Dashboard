#!/usr/bin/env python3
"""tests/test_match_name_matching.py — Namens-Matching für Event-Page Betfair/Poly (19.08.2026, Lucas).

_mscore matcht Event-Page-Teamnamen gegen Betfair-/Poly-Outcome-Labels. Frueher len(inter)/max(...) →
Kurz-vs-Lang-Namen (Poly „Brighton" vs Event „Brighton Hove Albion") fielen durch. Jetzt Containment
(min-Nenner) + Guard gegen generische Einzel-Token (city/united)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_match_pages as G


class TestNameMatching(unittest.TestCase):
    def _match(self, a, b):
        return G._mscore(a, b) >= 0.5

    def test_short_vs_long_variants_match(self):
        # Containment: der kuerzere Name geht im laengeren auf
        self.assertTrue(self._match("Brighton Hove Albion", "Brighton"))
        self.assertTrue(self._match("Inter", "Inter Milan"))
        self.assertTrue(self._match("Villarreal CF", "Villarreal"))

    def test_distinctive_single_token_matches(self):
        # 'athletic'/'sporting'/'racing' sind distinktiv (Athletic Bilbao, …) → duerfen matchen
        self.assertTrue(self._match("Athletic Club", "Athletic Bilbao"))

    def test_generic_single_token_does_not_match(self):
        # nur ein generischer Token (city/united) reicht NICHT
        self.assertFalse(self._match("Leeds United", "Newcastle United"))
        self.assertFalse(self._match("Manchester City", "Leicester City"))

    def test_exact_match(self):
        self.assertTrue(self._match("Manchester City", "Manchester City"))

    def test_empty_and_nonoverlap(self):
        self.assertEqual(G._mscore("", "Anything"), 0.0)
        self.assertFalse(self._match("Bayern Munich", "Borussia Dortmund"))


if __name__ == "__main__":
    unittest.main()
