"""
test_telegram_wm_format.py — Format-Garantien für die Telegram-WM-Karten (21.06.2026, Lucas:
„schade dass kein Guard das sieht, immer ich muss es sehen"). Fängt die Klasse von Content-
Regressionen, die Lucas manuell entdeckt hat:
  · veralteter fixer Signal-Nenner („X/14 Signale") — wir haben 19 Signale
  · zu viel Elo (rohe Elo-Zahlen, „Elo-Gap N Pkt", „laut Elo-Modell")
  · Tech-Jargon-Fußzeile (Poisson)

Baut die echten Morning-/Recap-Karten aus wm2026-data.json und prüft die Invarianten.
"""
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import telegram_wm  # noqa: E402

FORBIDDEN = ["/14", "Elo:", "Elo-Gap", "laut Elo", "Poisson", "Signalen stützen"]


def _all_cards():
    wm = json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
    dates = set()
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            if fx.get("date"):
                dates.add(fx["date"])
    cards = []
    for d in sorted(dates):
        for fn in (telegram_wm.build_morning_card, telegram_wm.build_recap_card):
            try:
                msg = fn(wm, d)
            except Exception:
                msg = None
            if msg:
                cards.append((d, fn.__name__, msg))
    return cards


class TestTelegramWmFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = _all_cards()

    def test_at_least_one_card(self):
        self.assertTrue(self.cards, "Keine Karte gebaut — Fixture/Datenproblem")

    def test_no_forbidden_substrings(self):
        for d, fn, msg in self.cards:
            for bad in FORBIDDEN:
                with self.subTest(date=d, fn=fn, bad=bad):
                    self.assertNotIn(bad, msg, f"{fn} @ {d} enthält verbotenes '{bad}'")

    def test_signal_line_uses_dynamic_count(self):
        # Wenn eine Signal-Zeile vorkommt, dann im neuen Format „N Signale dafür" —
        # nie mit fixem Nenner.
        for d, fn, msg in self.cards:
            if "Signale dafür" in msg or "Signale stützen" in msg:
                with self.subTest(date=d, fn=fn):
                    self.assertIn("Signale dafür", msg)
                    self.assertNotIn("Signale stützen", msg)


if __name__ == "__main__":
    unittest.main()
