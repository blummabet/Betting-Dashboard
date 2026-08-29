"""tests/test_pinn_move.py — 29.08.2026

Der Pinnacle-Move war tot. Gemessen wurde gegen den unmittelbar vorigen Snapshot; der Scan
laeuft alle ~15 Minuten, gelegentlich zweimal in vier Minuten. Ueber 40 echte Spiele gab es
genau zwei verschiedene Werte: -0.0 und 1.2. Als Bedingung ("Pinni move da") war das wertlos.

Diese Tests halten die neue Definition fest: Bewegung ueber das FENSTER, nur vor Anpfiff,
Luecken werden uebersprungen statt als Null gelesen.
"""
import unittest
from datetime import datetime, timedelta, timezone

import betfair_consensus as BC


def snap(minuten_vor_ko, home, draw=0.25, away=None, ko=None):
    ko = ko or datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
    away = away if away is not None else round(1.0 - home - draw, 4)
    return {"ts": (ko - timedelta(minutes=minuten_vor_ko)).isoformat().replace("+00:00", "Z"),
            "pinn": [home, draw, away]}


KO = "2026-08-29T20:00:00Z"


class PinnMove(unittest.TestCase):
    def test_fenster_statt_letzter_schritt(self):
        # Der Kern des Bugs: Pinnacle zieht ueber zwei Stunden 6pp, aber zwischen den letzten
        # beiden Snapshots nur 0.2pp. Alt wurden daraus 0.2 gemeldet, also nichts.
        hist = [snap(120, 0.50), snap(90, 0.52), snap(60, 0.545), snap(30, 0.558)]
        pm = BC.pinn_move(hist, [0.56, 0.25, 0.19], "home", KO)
        self.assertAlmostEqual(pm["movePP"], 6.0, places=1)
        self.assertAlmostEqual(pm["stepPP"], 0.2, places=1)
        self.assertTrue(pm["move"], "6pp ueber das Fenster ist eine Bewegung")
        self.assertTrue(pm["laeuft"], "der letzte Schritt zieht in dieselbe Richtung")

    def test_doppellauf_verschiebt_den_schritt_nicht(self):
        # Zwei Laeufe im Abstand von Minuten mit identischem Preis: der letzte ECHTE Schritt
        # ist der davor, nicht die Null dazwischen.
        hist = [snap(120, 0.50), snap(40, 0.55), snap(35, 0.55)]
        pm = BC.pinn_move(hist, [0.55, 0.25, 0.20], "home", KO)
        self.assertAlmostEqual(pm["stepPP"], 5.0, places=1)

    def test_live_zaehlt_nicht(self):
        hist = [snap(120, 0.50)]
        self.assertIsNone(BC.pinn_move(hist, [0.69, 0.20, 0.11], "home", KO, live=True),
                          "ein Repricing nach einem Tor ist ein Spielstand, keine Sharp-Bewegung")

    def test_snapshots_nach_anpfiff_fliegen_raus(self):
        # Aus der echten Historie: 0.50 -> 0.69 innerhalb eines Laufs, weil ein Tor fiel.
        hist = [snap(60, 0.50), snap(-20, 0.69)]   # der zweite liegt NACH dem Anpfiff
        pm = BC.pinn_move(hist, [0.51, 0.25, 0.24], "home", KO)
        self.assertAlmostEqual(pm["movePP"], 1.0, places=1)
        self.assertEqual(pm["n"], 2, "nur der Vor-Anpfiff-Snapshot plus das aktuelle Reading")

    def test_luecke_wird_uebersprungen_nicht_als_null_gelesen(self):
        hist = [snap(120, 0.50), {"ts": "2026-08-29T19:00:00Z"}, snap(30, 0.54)]
        pm = BC.pinn_move(hist, [0.55, 0.25, 0.20], "home", KO)
        self.assertAlmostEqual(pm["movePP"], 5.0, places=1)
        self.assertEqual(pm["n"], 3)

    def test_ohne_historie_kein_move(self):
        self.assertIsNone(BC.pinn_move([], [0.5, 0.25, 0.25], "home", KO))
        self.assertIsNone(BC.pinn_move(None, [0.5, 0.25, 0.25], "home", KO))
        self.assertIsNone(BC.pinn_move([snap(60, 0.5)], None, "home", KO))

    def test_rauschen_ist_kein_move(self):
        hist = [snap(120, 0.500)]
        pm = BC.pinn_move(hist, [0.504, 0.25, 0.246], "home", KO)
        self.assertFalse(pm["move"], "0.4pp ist Rauschen")
        self.assertAlmostEqual(pm["movePP"], 0.4, places=1)

    def test_gegenbewegung(self):
        hist = [snap(120, 0.60), snap(30, 0.55)]
        pm = BC.pinn_move(hist, [0.54, 0.25, 0.21], "home", KO)
        self.assertLess(pm["movePP"], 0)
        self.assertTrue(pm["move"])
        self.assertTrue(pm["laeuft"], "faellt weiter — die Bewegung laeuft, nur gegen uns")

    def test_einzelner_snapshot_als_dict_bleibt_lesbar(self):
        # Rueckwaerts-Kompatibilitaet: build_game bekam frueher genau einen Snapshot.
        pm = BC.pinn_move({"pinn": [0.50, 0.25, 0.25]}, [0.55, 0.25, 0.20], "home", None)
        self.assertAlmostEqual(pm["movePP"], 5.0, places=1)

    def test_seite_zaehlt(self):
        hist = [snap(120, 0.50, draw=0.25)]
        pm = BC.pinn_move(hist, [0.55, 0.25, 0.20], "away", KO)
        self.assertAlmostEqual(pm["movePP"], -5.0, places=1)
        self.assertIsNone(BC.pinn_move(hist, [0.55, 0.25, 0.20], None, KO))


class Fenster(unittest.TestCase):
    def test_mindestabstand_haelt_das_fenster_offen(self):
        # 24 Snapshots × >=20 Min statt 8 × 15 Min: das Fenster deckt Stunden statt Minuten.
        self.assertGreaterEqual(BC.HIST_KEEP * BC.SNAP_MIN_ABSTAND_MIN, 8 * 60,
                                "das Fenster muss mindestens acht Stunden tragen")


if __name__ == "__main__":
    unittest.main()
