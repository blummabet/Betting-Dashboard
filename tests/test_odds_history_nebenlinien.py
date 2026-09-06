"""Die Odds-Zeitreihe muss auch Nebenlinien mitschreiben — 06.09.2026.

Anlass (gemessen, nicht vermutet): von 318 abgerechneten Picks trugen 162 kein einziges
Preis/Geld-Signal. Preis-Signale sind die einzige Signalfamilie mit belegtem CLV-Zusammenhang
(r = +0,35, p = 0,0001); die Staerke-Signale liegen bei r = +0,003. Die blinde Haelfte war
fast vollstaendig Ueber/Unter und BTTS.

Zwei Ursachen in `append_snapshot`, beide hier festgehalten:
  1. BTTS wurde geholt, gemittelt und im Eintrag getragen — aber NIE in die Zeitreihe
     geschrieben (0 von 27.086 Snapshots in liga+mls).
  2. Das Schreib-Gate fragte nur nach 1X2. Eine reine Tor-Bewegung bei stehendem 1X2
     erzeugte keinen Snapshot — die O/U-Zeitreihe war ein Nebenprodukt der 1X2-Zeitreihe.

Die Tests halten die REGEL fest ("jede Bewegung, die wir kennen, kommt in die Zeitreihe"),
nicht den heutigen Feldbestand.
"""
import unittest

import fetch_liga_odds as F


PREISE = {"hw": 2.10, "dr": 3.40, "aw": 3.60,
          "o25": 1.85, "u25": 1.95, "bttsY": 1.72, "bttsN": 2.05,
          "public_hw": 2.05, "public_dr": 3.45, "public_aw": 3.70,
          "public_o25": 1.88, "public_u25": 1.92,
          "public_bttsY": 1.75, "public_bttsN": 2.00}


def _pinn(snaps):
    return [s for s in snaps if s.get("bk") != "public"]


class TestSnapChangedGate(unittest.TestCase):
    def test_ohne_letzten_snap_immer_schreiben(self):
        self.assertTrue(F._snap_changed(None, 2.0, 3.4, 3.6))

    def test_1x2_bewegung_schreibt(self):
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6}
        self.assertTrue(F._snap_changed(last, 2.1, 3.4, 3.6))

    def test_alles_gleich_schreibt_nicht(self):
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6, "o25": 1.85}
        self.assertFalse(F._snap_changed(last, 2.0, 3.4, 3.6, {"o25": 1.85}))

    def test_reine_ou_bewegung_schreibt_jetzt(self):
        """Der Kern des Fehlers: 1X2 steht, die Torlinie bewegt sich — das ist Bewegung."""
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6, "o25": 1.85}
        self.assertTrue(F._snap_changed(last, 2.0, 3.4, 3.6, {"o25": 1.92}))

    def test_reine_btts_bewegung_schreibt_jetzt(self):
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6, "bttsY": 1.72}
        self.assertTrue(F._snap_changed(last, 2.0, 3.4, 3.6, {"bttsY": 1.80}))

    def test_fehlende_nebenlinie_erzwingt_keinen_snap(self):
        """None heisst 'diesmal nicht geliefert' — das ist keine Bewegung."""
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6, "o25": 1.85}
        self.assertFalse(F._snap_changed(last, 2.0, 3.4, 3.6, {"o25": None}))

    def test_alte_signatur_gilt_weiter(self):
        """Bestehende Aufrufer ohne `neben` duerfen sich nicht aendern."""
        last = {"hw": 2.0, "dr": 3.4, "aw": 3.6}
        self.assertFalse(F._snap_changed(last, 2.0, 3.4, 3.6))


class TestAppendSnapshot(unittest.TestCase):
    def test_btts_landet_in_der_zeitreihe(self):
        h = {}
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z")
        p = _pinn(h["1-2"])[0]
        self.assertEqual(p["bttsY"], 1.72)
        self.assertEqual(p["bttsN"], 2.05)
        pub = [s for s in h["1-2"] if s.get("bk") == "public"][0]
        self.assertEqual(pub["bttsY"], 1.75)
        self.assertEqual(pub["bttsN"], 2.00)

    def test_ou_bleibt_erhalten(self):
        h = {}
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z")
        p = _pinn(h["1-2"])[0]
        self.assertEqual(p["o25"], 1.85)
        self.assertEqual(p["u25"], 1.95)

    def test_zweiter_lauf_ohne_bewegung_haengt_nichts_an(self):
        h = {}
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z")
        n = len(h["1-2"])
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:15:00Z")
        self.assertEqual(len(h["1-2"]), n, "unveraenderte Preise duerfen die Zeitreihe nicht aufblaehen")

    def test_nur_die_torlinie_bewegt_sich(self):
        h = {}
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z")
        n = len(_pinn(h["1-2"]))
        spaeter = dict(PREISE, o25=1.72, u25=2.10)
        F.append_snapshot(h, "1-2", spaeter, "2026-09-06T10:15:00Z")
        self.assertEqual(len(_pinn(h["1-2"])), n + 1,
                         "eine reine Tor-Bewegung muss einen Snapshot erzeugen")
        self.assertEqual(_pinn(h["1-2"])[-1]["o25"], 1.72)

    def test_nur_btts_bewegt_sich(self):
        h = {}
        F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z")
        n = len(_pinn(h["1-2"]))
        spaeter = dict(PREISE, bttsY=1.60, bttsN=2.25)
        F.append_snapshot(h, "1-2", spaeter, "2026-09-06T10:15:00Z")
        self.assertEqual(len(_pinn(h["1-2"])), n + 1)
        self.assertEqual(_pinn(h["1-2"])[-1]["bttsY"], 1.60)

    def test_ohne_btts_quote_kein_leeres_feld(self):
        """Fehlende Quote schreibt keinen Platzhalter — sonst liest ein Signal spaeter 'None'
        als Preis."""
        h = {}
        ohne = {k: v for k, v in PREISE.items() if "btts" not in k.lower()}
        F.append_snapshot(h, "1-2", ohne, "2026-09-06T10:00:00Z")
        self.assertNotIn("bttsY", _pinn(h["1-2"])[0])

    def test_nach_anpfiff_kein_snapshot(self):
        h = {}
        self.assertEqual(F.append_snapshot(h, "1-2", PREISE, "2026-09-06T10:00:00Z", post_ko=True), 0)
        self.assertEqual(h.get("1-2", []), [])


if __name__ == "__main__":
    unittest.main()
