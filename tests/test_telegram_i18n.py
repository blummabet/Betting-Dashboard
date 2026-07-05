#!/usr/bin/env python3
"""test_telegram_i18n.py — DE+EN Public-Picks (04.07.2026, Lucas: „Picks deutsch UND englisch").
Friert die Übersetzungsschicht ein: DE bleibt 1:1, EN übersetzt Teams/Märkte/Runden/Labels."""
import json
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
os.environ["SKIP_TELEGRAM"] = "true"

import telegram_i18n as I18N


class TestTranslators(unittest.TestCase):
    def test_teams_en(self):
        self.assertEqual(I18N.team_name("EGY", "Ägypten", "en"), "Egypt")
        self.assertEqual(I18N.team_name("CPV", "Kap Verde", "en"), "Cape Verde")
        self.assertEqual(I18N.team_name("EGY", "Ägypten", "de"), "Ägypten")   # DE unverändert
        # Vereine (kein FIFA-Code) fallen auf den Originalnamen zurück
        self.assertEqual(I18N.team_name("Sevilla", "Sevilla", "en"), "Sevilla")

    def test_markets_en(self):
        self.assertEqual(I18N.market_label("Unter 2.5 Tore", "en"), "Under 2.5 Goals")
        self.assertEqual(I18N.market_label("Beide Teams treffen — Ja", "en"), "Both Teams to Score — Yes")
        self.assertEqual(I18N.market_label("Doppelte Chance — 1X", "en"), "Double Chance — 1X")
        self.assertEqual(I18N.market_label("Heimsieg", "en"), "Home Win")
        self.assertEqual(I18N.market_label("AH Heim −1.5", "en"), "AH Home −1.5")
        # Komma → Punkt fürs internationale Publikum
        self.assertEqual(I18N.market_label("Über 2,5 Tore", "en"), "Over 2.5 Goals")
        # DE bleibt unverändert
        self.assertEqual(I18N.market_label("Unter 2.5 Tore", "de"), "Unter 2.5 Tore")

    def test_rounds_en(self):
        self.assertEqual(I18N.round_label("Sechzehntelfinale", "en"), "Round of 32")
        self.assertEqual(I18N.round_label("Achtelfinale", "en"), "Round of 16")
        self.assertEqual(I18N.round_label("Achtelfinale", "de"), "Achtelfinale")

    def test_upset_en(self):
        self.assertIn("UPSET", I18N.upset_label(8, "en"))
        self.assertIn("UPSET", I18N.upset_label(8, "de"))


class TestMorningBilingual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import telegram_wm as W
        cls.W = W
        cls.wm = json.loads((REPO / "wm2026-data.json").read_text(encoding="utf-8"))
        # Datum mit Spielen finden
        import datetime
        cls.date = None
        for off in range(0, 12):
            d = (datetime.date.today() - datetime.timedelta(days=off)).isoformat()
            if W.build_morning_card(cls.wm, d, "de"):
                cls.date = d
                break

    def test_de_bleibt_deutsch(self):
        if not self.date:
            self.skipTest("kein Spieltag in den Daten")
        de = self.W.build_morning_card(self.wm, self.date, "de")
        self.assertIn("WM 2026", de)
        self.assertNotIn("World Cup", de)

    def test_en_ist_englisch(self):
        if not self.date:
            self.skipTest("kein Spieltag in den Daten")
        en = self.W.build_morning_card(self.wm, self.date, "en")
        self.assertIn("World Cup 2026", en)
        self.assertNotIn("WM 2026", en)
        self.assertNotIn(" Uhr", en)        # Zeit-Suffix raus
        self.assertNotIn("Abwägen", en)     # → Lean
        self.assertNotIn("Tore", en)        # Märkte übersetzt


if __name__ == "__main__":
    unittest.main()
