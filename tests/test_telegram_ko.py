#!/usr/bin/env python3
"""test_telegram_ko.py — KO-Picks erscheinen in Morning-Card + Recap (28.06.2026, Lucas:
KO wurde nie gepostet, weil nur Gruppen iteriert wurden)."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import telegram_wm as T  # noqa: E402

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _wm(pick):
    return {
        "groups": {"A": {"teams": [{"id": "ZAF", "name": "Südafrika", "flag": "🇿🇦"},
                                   {"id": "CAN", "name": "Kanada", "flag": "🇨🇦"}],
                         "fixtures": []}},
        "koFixtures": [{"round": "R32", "matchNo": 73, "home": "ZAF", "away": "CAN",
                        "bothResolved": True, "kickoff": f"{TODAY}T19:00:00Z", "date": TODAY,
                        "venue": "Los Angeles", "roundLabel": "Sechzehntelfinale"}],
        "picks": {"KO-R32-ZAF-CAN": [pick]},
    }


class TestTelegramKO(unittest.TestCase):
    def test_morning_card_includes_ko(self):
        wm = _wm({"market": "Auswärtssieg", "verdict": "BET", "odds": 1.65, "convictionScore": 6})
        card = T.build_morning_card(wm, TODAY)
        self.assertIsNotNone(card, "KO-Spiel sollte eine Morning-Card erzeugen")
        self.assertIn("Sechzehntelfinale", card)   # Runden-Label statt „Gruppe X"
        self.assertIn("Südafrika", card)
        self.assertIn("Kanada", card)

    def test_recap_includes_ko(self):
        wm = _wm({"market": "Unter 2.5 Tore", "verdict": "ABWÄGEN", "odds": 1.65,
                  "convictionScore": 6, "result": "WIN"})
        card = T.build_recap_card(wm, TODAY)
        self.assertIsNotNone(card, "KO-Pick mit Ergebnis sollte im Recap sein")
        self.assertIn("Südafrika", card)
        self.assertIn("Unter 2.5", card)


if __name__ == "__main__":
    unittest.main()
