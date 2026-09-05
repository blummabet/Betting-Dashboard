#!/usr/bin/env python3
"""
05.09.2026 (Lucas): „🔵 Betfair Halftime Flow · HZ Over/Under 1.5 · Over 1.5 @1.74 …
da ist grad 50 min. Und kommt als Push in public."

Der Halbzeit-Markt war zu dem Zeitpunkt entschieden. `ht_alert` feuerte in der 20., in der
PAUSE und in der 70. exakt gleich: die Spielminute stand die ganze Zeit in `liveInfo.time`,
dazu ein eigenes `is_ht`-Flag — beides wurde nirgends gelesen.

Gemessen im Bestand am selben Tag: 36 von 36 Live-Spielen jenseits der 46. fuehren weiter
HZ-Maerkte mit Volumen im Feed. Die Quelle raeumt sie nicht ab.
"""
import unittest

import betfair_alerts as A


def _spiel(minute=None, is_ht=False, finished=False, vol_over=15308.0, vol_under=2492.0):
    return {"matchId": "x1", "home": "FC Dordrecht", "away": "Jong AZ Alkmaar",
            "league": "Dutch Eerste Divisie", "kickoff": "2026-09-05T18:00:00Z",
            "liveInfo": {"time": minute, "is_ht": is_ht, "finished": finished},
            "markets": {"First Half Goals 1.5": {"runners": [
                {"name": "Over 1.5 Goals", "vol": vol_over, "odd": 1.74},
                {"name": "Under 1.5 Goals", "vol": vol_under, "odd": 2.30}]}}}


class TestFenster(unittest.TestCase):
    def test_vor_Anpfiff_offen(self):
        """Ohne Live-Minute gibt es kein Fenster zu schliessen — der HZ-Markt ist regulaer."""
        self.assertTrue(A.ht_fenster_offen(_spiel(None)))
        self.assertTrue(A.ht_fenster_offen({}))

    def test_erste_Haelfte_offen(self):
        for mi in (0, 1, 20, 44, 45):
            self.assertTrue(A.ht_fenster_offen(_spiel(mi)), f"Minute {mi}")

    def test_Pause_zu(self):
        """Die Nachspielzeit der ersten Haelfte meldet Betfair weiter als 45 — die Pause
        trennt `is_ht`, nicht die Minute. Deshalb beide Kriterien."""
        self.assertFalse(A.ht_fenster_offen(_spiel(45, is_ht=True)))

    def test_zweite_Haelfte_zu(self):
        for mi in (46, 50, 70, 90, 103):
            self.assertFalse(A.ht_fenster_offen(_spiel(mi)), f"Minute {mi}")

    def test_beendet_zu(self):
        self.assertFalse(A.ht_fenster_offen(_spiel(90, finished=True)))
        self.assertFalse(A.ht_fenster_offen(_spiel(None, finished=True)))

    def test_unlesbare_Minute_ist_keine_Erlaubnis(self):
        self.assertFalse(A.ht_fenster_offen(_spiel("halbzeit")))


class TestAlert(unittest.TestCase):
    def test_der_reale_Fall_geht_nicht_mehr_raus(self):
        """Dordrecht v Jong AZ, 50. Minute, €17.8K auf Over 1.5 HZ."""
        self.assertIsNone(A.ht_alert(_spiel(50)))

    def test_in_der_ersten_Haelfte_unveraendert(self):
        a = A.ht_alert(_spiel(20))
        self.assertIsNotNone(a, "das Signal selbst bleibt — nur sein Fenster ist begrenzt")
        self.assertEqual(a["mktLabel"], "HZ Over/Under 1.5")
        self.assertEqual(a["leadName"], "Over 1.5 Goals")

    def test_vor_Anpfiff_unveraendert(self):
        self.assertIsNotNone(A.ht_alert(_spiel(None)))

    def test_die_Pause_selbst_ist_schon_zu_spaet(self):
        self.assertIsNone(A.ht_alert(_spiel(45, is_ht=True)))
        self.assertIsNotNone(A.ht_alert(_spiel(45, is_ht=False)))


class TestGegenEchteDaten(unittest.TestCase):
    from pathlib import Path as _Path
    DATEI = _Path(__file__).resolve().parent.parent / "betfair_prices.json"

    def test_kein_HZ_Alert_jenseits_der_Halbzeit(self):
        """Der Test, der den Fund gefunden haette: gegen den echten Feed, nicht gegen eine
        Fixture. Die Quelle liefert HZ-Maerkte weiter, wir duerfen sie nur nicht mehr melden."""
        if not self.DATEI.exists():
            self.skipTest("Artefakt nicht vorhanden")
        import json
        d = json.loads(self.DATEI.read_text(encoding="utf-8"))
        ms = d.get("matches") or d.get("spiele") or (d if isinstance(d, list) else [])
        if isinstance(ms, dict):
            ms = list(ms.values())
        spaet = 0
        for m in ms:
            li = m.get("liveInfo") or {}
            t = li.get("time")
            if not (li.get("is_ht") or (isinstance(t, (int, float)) and t > 45)):
                continue
            spaet += 1
            self.assertIsNone(A.ht_alert(m),
                              f"{m.get('home')} v {m.get('away')} Min {t}: HZ-Alert nach der Pause")
        self.assertGreater(spaet, 0, "keine Spiele nach der Pause im Feed — Test wertlos")


if __name__ == "__main__":
    unittest.main()
