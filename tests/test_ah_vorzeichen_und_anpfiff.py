"""31.10.2026 (Cards-Audit): zwei Fehler, die echte Bilanz/Posts betrafen.

1. AH auf das Auswärtsteam mit Minus-Linie wurde wie Plus gewertet (abs der Linie):
   Schalke 0:0 Bayern „AH Auswärts −1.5" war WIN statt LOSS.
2. Die Morgen-Karte nahm Spiele auf, die schon liefen oder vorbei waren
   (Como–Roma, Anpfiff 10:30Z, gepostet 13:45Z).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resolve_wm_picks import _ah_result  # noqa: E402


class AhVorzeichen(unittest.TestCase):
    def test_auswaerts_minus_wie_im_audit(self):
        self.assertEqual(_ah_result("ah auswärts −1.5", 0 - 0)[0], "LOSS")     # Schalke 0:0 Bayern
        self.assertEqual(_ah_result("ah auswärts −1.5", 0 - 1)[0], "LOSS")     # Brest 0:1 PSG
        self.assertEqual(_ah_result("ah auswärts −1.25", 1 - 0), ("LOSS", 1.0))  # Betis 1:0 Real
        self.assertEqual(_ah_result("ah auswärts −0.75", 1 - 2), ("WIN", 0.5))   # Marseille 1:2 PSG
        self.assertEqual(_ah_result("ah auswärts −1.75", 2 - 4), ("WIN", 0.5))   # Levante 2:4 Barça

    def test_heim_unveraendert(self):
        self.assertEqual(_ah_result("ah heim −1.5", 2), ("WIN", 1.0))
        self.assertEqual(_ah_result("ah heim −1", 1), ("VOID", 1.0))
        self.assertEqual(_ah_result("ah heim −1.25", 1), ("LOSS", 0.5))

    def test_plus_linien(self):
        self.assertEqual(_ah_result("ah heim +0.5", 0)[0], "WIN")
        self.assertEqual(_ah_result("ah auswärts +1.5", 1)[0], "WIN")


class MorgenKarteNurOffeneSpiele(unittest.TestCase):
    def test_angepfiffene_spiele_fallen_raus(self):
        import telegram_wm as T
        jetzt = datetime.now(timezone.utc)
        tag = jetzt.strftime("%Y-%m-%d") if jetzt.hour >= 8 else (jetzt - timedelta(days=1)).strftime("%Y-%m-%d")
        def fx(h, a, ko):
            return {"home": h, "away": a, "matchday": 1, "kickoff": ko.isoformat(), "date": tag}
        vorbei = max(datetime.fromisoformat(tag + "T08:30:00+00:00"), jetzt - timedelta(hours=3))
        if vorbei >= jetzt:
            self.skipTest("Tagesfenster hat gerade erst begonnen")
        spaeter = jetzt + timedelta(hours=2)
        pick = lambda: [{"verdict": "BET", "market": "Heimsieg", "odds": 1.8, "conviction": 9}]
        wm = {"groups": {"A": {"teams": [{"id": t, "name": t} for t in ("AAA", "BBB", "CCC", "DDD")],
                               "fixtures": [fx("AAA", "BBB", vorbei), fx("CCC", "DDD", spaeter)]}},
              "picks": {f"A-1-AAA-BBB": pick(), f"A-1-CCC-DDD": pick()}}
        karte = T.build_morning_card(wm, tag, "de") or ""
        self.assertIn("CCC", karte)          # das spätere Spiel steht drin (Test nicht leer)
        self.assertNotIn("AAA", karte)


if __name__ == "__main__":
    unittest.main()


class WienerZeitImWinter(unittest.TestCase):
    """31.10.2026: Anstoßzeiten waren fest UTC+2 — seit der Zeitumstellung am 25.10. eine Stunde zu spät."""

    def test_notify_winterzeit(self):
        import notify_new_picks as N
        jetzt = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(N._kickoff_wien({"kickoff": "2026-10-26T19:30:00Z"}, jetzt), " · 20:30")   # PSG–Lyon

    def test_notify_sommerzeit_unveraendert(self):
        import notify_new_picks as N
        jetzt = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(N._kickoff_wien({"kickoff": "2026-09-01T18:45:00Z"}, jetzt), " · 20:45")
