"""tests/test_pick_push_ledger.py — 30.08.2026

Das Schattenbuch ist die Gegenprobe zum Gegensignal-Filter: es schreibt auch die AUSSORTIERTEN
Picks mit und rechnet sie ab. Ohne das koennte der Schnitt sich nicht widerlegen lassen.

Der heikelste Punkt ist der Einfrier-Zeitpunkt. Gemessen ueber 14 Tage blieben 87% der Picks in
ihrem Signal-Zustand, 13% kippten noch (4 von sauber zu Gegensignal, 2 zurueck). Beim ersten
Sehen einzufrieren waere also falsch — und nach Anpfiff weiterzuschreiben erst recht, weil ein
Pick dann nachtraeglich in die gerade besser aussehende Schublade wandern koennte.
"""
import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _wm(ko_h=5, **pickkw):
    ko = (NOW + timedelta(hours=ko_h)).isoformat().replace("+00:00", "Z")
    p = {"verdict": "ABWÄGEN", "market": "Über 2.5 Tore", "odds": 1.9,
         "signalCountPos": 3, "signalCountNeg": 0}
    p.update(pickkw)
    return {"groups": {"A": {"teams": [{"id": "MEX", "name": "Mexiko"}, {"id": "ZAF", "name": "Südafrika"}],
                             "fixtures": [{"home": "MEX", "away": "ZAF", "matchday": 1, "kickoff": ko}]}},
            "koFixtures": [], "picks": {"A-1-MEX-ZAF": [p]}}


class Buch(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state
        importlib.reload(pick_announce_state)
        import pick_push_ledger as L
        importlib.reload(L)
        self.L = L

    def test_beide_seiten_landen_im_buch(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertEqual(len(led), 1)
        self.assertTrue(led[0]["push"])
        led2 = self.L.erfassen([], _wm(signalCountNeg=2), "wm", NOW)
        self.assertEqual(len(led2), 1)
        self.assertFalse(led2[0]["push"], "die Aussortierten muessen mitgeschrieben werden")
        self.assertTrue(led2[0]["gegensignal"])

    def test_stand_wird_bis_zum_anpfiff_fortgeschrieben(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertTrue(led[0]["push"])
        # Ein Gegensignal taucht spaeter auf, das Spiel laeuft noch:
        led = self.L.erfassen(led, _wm(signalCountNeg=1), "wm", NOW + timedelta(hours=1))
        self.assertEqual(len(led), 1, "kein Duplikat")
        self.assertFalse(led[0]["push"], "der Stand muss dem folgen, was der Filter zuletzt sah")

    def test_nach_anpfiff_wird_eingefroren(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        # Spiel laeuft: iter_pick_units liefert nichts mehr -> Zeile bleibt stehen
        spaet = NOW + timedelta(hours=9)
        led2 = self.L.erfassen(led, _wm(signalCountNeg=5), "wm", spaet)
        self.assertEqual(len(led2), 1)
        self.assertTrue(led2[0]["push"], "nach Anpfiff darf sich der Stand nicht mehr drehen")

    def test_abgerechnete_zeile_wird_nie_wieder_angefasst(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW),
                               _wm(result="WIN"), "wm", NOW)
        self.assertEqual(led[0]["status"], "abgerechnet")
        self.assertTrue(led[0]["win"])
        led2 = self.L.erfassen(led, _wm(signalCountNeg=4), "wm", NOW)
        self.assertTrue(led2[0]["push"])
        self.assertEqual(led2[0]["sigNeg"], 0)

    def test_void_ist_kein_verlust(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW),
                               _wm(result="VOID"), "wm", NOW)
        self.assertEqual(led[0]["status"], "void")
        self.assertIsNone(led[0]["win"])
        self.assertEqual(self.L.schubladen(led), {}, "VOID darf in keiner Schublade landen")

    def test_offen_bleibt_offen(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW), _wm(), "wm", NOW)
        self.assertEqual(led[0]["status"], "offen")
        self.assertEqual(self.L.schubladen(led), {})

    def test_schubladen_trennen_gepusht_von_aussortiert(self):
        led = [
            {"k": "wm|a", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
             "push": True, "odds": 2.0, "win": True, "settledAt": "2026-08-29T10:00:00Z"},
            {"k": "wm|b", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
             "push": False, "odds": 2.0, "win": False, "settledAt": "2026-08-29T11:00:00Z"},
            {"k": "wm|c", "dataset": "wm", "verdict": "BET", "status": "abgerechnet",
             "push": True, "odds": 2.0, "win": True, "settledAt": "2026-08-29T12:00:00Z"},
        ]
        s = self.L.schubladen(led)
        self.assertEqual(set(s), {"ABWÄGEN · gepusht", "ABWÄGEN · aussortiert"},
                         "BET gehoert nicht in diese Frage — der Filter fasst ihn nicht an")
        self.assertEqual(s["ABWÄGEN · gepusht"]["renditen"], [1.0])
        self.assertEqual(s["ABWÄGEN · aussortiert"]["renditen"], [-1.0])

    def test_unbrauchbare_quote_fliegt_raus(self):
        led = [{"k": "wm|a", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
                "push": True, "odds": o, "win": True, "settledAt": "2026-08-29T10:00:00Z"}
               for o in (None, 1.0, 0)]
        self.assertEqual(self.L.schubladen(led), {})

    def test_wurde_gepusht_kennt_den_unterschied_zu_unbekannt(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertIs(self.L.wurde_gepusht(led, "wm", "A-1-MEX-ZAF", "Über 2.5 Tore"), True)
        self.assertIsNone(self.L.wurde_gepusht(led, "wm", "A-1-MEX-ZAF", "Gibtsnicht"),
                          "None heisst: steht nicht im Buch. Nicht: wurde nicht gepusht.")


class Register(unittest.TestCase):
    def test_beide_schubladen_landen_im_freigabe_register(self):
        import freigabe
        importlib.reload(freigabe)
        led = []
        for i in range(40):
            led.append({"k": f"wm|g{i}", "dataset": "wm", "verdict": "ABWÄGEN",
                        "status": "abgerechnet", "push": True, "odds": 2.0,
                        "win": i % 3 != 0, "settledAt": "2026-08-29T10:00:00Z"})
            led.append({"k": f"wm|s{i}", "dataset": "wm", "verdict": "ABWÄGEN",
                        "status": "abgerechnet", "push": False, "odds": 2.0,
                        "win": i % 3 == 0, "settledAt": "2026-08-29T10:00:00Z"})
        z = {r["schublade"]: r for r in freigabe.push_schubladen(
            led, now=datetime(2026, 8, 29, 18, tzinfo=timezone.utc))}
        self.assertEqual(set(z), {"ABWÄGEN · gepusht", "ABWÄGEN · aussortiert"})
        self.assertGreater(z["ABWÄGEN · gepusht"]["roi"], z["ABWÄGEN · aussortiert"]["roi"])
        # Ohne CLV je Pick bleibt auch die bessere Schublade unter „freigegeben".
        self.assertNotEqual(z["ABWÄGEN · gepusht"]["status"], "freigegeben")

    def test_leeres_buch_erzeugt_keine_zeile(self):
        import freigabe
        importlib.reload(freigabe)
        self.assertEqual(freigabe.push_schubladen([]), [])


if __name__ == "__main__":
    unittest.main()
