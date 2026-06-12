"""
tests/test_tiktok_story.py — Card-Story muss zum Markt passen.

Bug 12.06.2026: TikTok-Card-Story war hardcoded "Edge auf den Underdog" für jede
Edge ≥10pp — falsch für Tor-Märkte (Über/Unter) und Favoriten-Picks (USA Über 1.5).
"Underdog/Außenseiter" darf NUR bei echten Auswärts-Picks vorkommen.
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("gdt", REPO / "generate_daily_tiktok.py")
gdt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gdt)

_AWAY_WORDS = ("underdog", "außenseiter", "aussenseiter")


def _story(market, edge=11):
    return gdt._pick_story_line({"market": market, "edge_pp": edge,
                                 "name_h": "USA", "name_a": "Paraguay"})


class TestPickStoryLine(unittest.TestCase):
    def test_over_goals_no_underdog(self):
        s = _story("Über 1.5 Tore")
        self.assertNotIn("underdog", s.lower())
        self.assertNotIn("außenseiter", s.lower())
        self.assertIn("Tor", s)

    def test_under_goals_no_underdog(self):
        s = _story("Unter 2.5 Tore")
        self.assertTrue(all(w not in s.lower() for w in _AWAY_WORDS))
        self.assertIn("Tor", s)

    def test_home_win_names_home_not_underdog(self):
        s = _story("Heimsieg")
        self.assertIn("USA", s)
        self.assertTrue(all(w not in s.lower() for w in _AWAY_WORDS))

    def test_away_win_may_say_underdog(self):
        s = _story("Auswärtssieg")
        self.assertIn("Paraguay", s)  # benennt das Auswärtsteam

    def test_btts_no_underdog(self):
        self.assertTrue(all(w not in _story("BTTS").lower() for w in _AWAY_WORDS))

    def test_consistency_guard(self):
        # Guard fängt jede künftige Drift: Underdog-Text bei Nicht-Auswärts = inkonsistent
        self.assertFalse(gdt._story_market_consistent("Edge auf den Underdog.", "Über 1.5 Tore"))
        self.assertFalse(gdt._story_market_consistent("Edge auf Außenseiter X.", "Heimsieg"))
        self.assertTrue(gdt._story_market_consistent("Edge auf Außenseiter Paraguay.", "Auswärtssieg"))
        self.assertTrue(gdt._story_market_consistent("Starker Tor-Edge.", "Über 1.5 Tore"))

    def test_every_market_passes_own_guard(self):
        # Jede vom Generator erzeugte Story muss ihren eigenen Markt-Guard bestehen.
        for mk in ["Über 1.5 Tore", "Unter 2.5 Tore", "Heimsieg", "Auswärtssieg",
                   "DNB: Auswärtsteam", "BTTS", "Doppelte Chance", "Über 3.5 Tore"]:
            self.assertTrue(gdt._story_market_consistent(_story(mk), mk),
                            f"Story für '{mk}' ist nicht markt-konsistent: {_story(mk)}")


if __name__ == "__main__":
    unittest.main()
