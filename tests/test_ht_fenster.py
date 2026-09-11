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
        # 07.09.2026: hier stand `assertGreater(spaet, 0, "Test wertlos")`. Das machte den Test
        # von der UHRZEIT abhaengig — um 07:30 UTC laeuft kein europaeisches Spiel, der
        # Schnappschuss enthielt 0 von 130 Spielen nach Minute 45, und die ganze Suite war rot,
        # obwohl nichts kaputt war. Zwoelfter Fall derselben Klasse in diesem Repo: ein Test
        # haelt einen MOMENT fest statt einer Regel.
        #
        # Die Regel selbst bleibt scharf: liegt auch nur ein Spiel nach der Pause im Feed, darf
        # keines davon einen HZ-Alert erzeugen (die Schleife oben prueft das). Liegt keines vor,
        # ist die Aussage nicht pruefbar — und „nicht pruefbar" ist ein Skip, kein Fehlschlag.
        if spaet == 0:
            self.skipTest("gerade kein Spiel nach der Pause im Feed — die Regel ist hier "
                          "nicht pruefbar (kein Befund, nur kein Material)")


class TestLinieSchonGerissen(unittest.TestCase):
    """🔴 12.09.2026 (Lucas: „aja und die push kam grad in public … nur dort ist grad pause oder
    so und die tore alle schon ewig her").

    Gemeldet: „HZ Over/Under 1.5 · Over 1.5 @1,47 · 85 % · €24,1K gematcht" fuer
    Al Ahli - Al-Hazm. Im Feed stand: **Minute 33, Stand 2:1 — drei Tore, alle in Halbzeit 1.**
    „Over 1.5" war laengst gewonnen; die €20,5K auf Over sind Geld von VOR den Toren.

    `ht_fenster_offen` liess es durch, und zwar voellig korrekt: 33 <= 45, `is_ht` false. Das
    FENSTER war offen, der MARKT nicht. Dieselbe Familie wie der Fix vom 05.09. („die Information
    war da und wurde nicht gefragt"), eine Ebene tiefer — damals fehlte die Minute, jetzt der
    Spielstand. Beide standen die ganze Zeit in `liveInfo`.
    """

    def _m(self, tore=None, minute=33, is_ht=False):
        li = {"time": minute, "is_ht": is_ht, "finished": False}
        if tore is not None:
            li["goal_v1"], li["goal_v2"] = tore
        return {"matchId": "ksa1", "home": "Al Ahli", "away": "Al-Hazm (KSA)",
                "league": "Saudi Professional League", "liveInfo": li,
                "markets": {"First Half Goals 1.5": {"runners": [
                    {"name": "Over 1.5 Goals", "vol": 20585.0, "odd": 1.47},
                    {"name": "Under 1.5 Goals", "vol": 3496.0, "odd": 2.60}]}}}

    def test_der_gemeldete_fall_geht_nicht_mehr_raus(self):
        m = self._m(tore=(2, 1))
        self.assertTrue(A.ht_fenster_offen(m), "das Fenster war offen — das war nie das Problem")
        self.assertFalse(A.ht_linie_offen(m, "First Half Goals 1.5"),
                         "drei Tore, Linie 1.5 — der Markt ist entschieden")
        self.assertIsNone(A._ht_one(m, "First Half Goals 1.5"))

    def test_vor_den_toren_geht_er_sehr_wohl_raus(self):
        """Die Gegenprobe. Ohne sie koennte die Regel alles sperren und der Test waere gruen."""
        m = self._m(tore=(0, 1))
        self.assertTrue(A.ht_linie_offen(m, "First Half Goals 1.5"))
        self.assertIsNotNone(A._ht_one(m, "First Half Goals 1.5", top_thr=1.0, rest_thr=1.0))

    def test_genau_auf_der_linie(self):
        """Bei Linie 1.5 entscheidet das zweite Tor. Eins ist noch offen, zwei nicht mehr."""
        self.assertTrue(A.ht_linie_offen(self._m(tore=(1, 0)), "First Half Goals 1.5"))
        self.assertFalse(A.ht_linie_offen(self._m(tore=(1, 1)), "First Half Goals 1.5"))

    def test_die_linie_kommt_aus_dem_namen(self):
        self.assertEqual(A._linie_aus_name("First Half Goals 1.5"), 1.5)
        self.assertEqual(A._linie_aus_name("First Half Goals 0.5"), 0.5)
        self.assertEqual(A._linie_aus_name("Over/Under 2.5 Goals"), None,
                         "die Linie steht dort nicht am Ende — kein Raten")
        self.assertIsNone(A._linie_aus_name("Half Time"))
        self.assertIsNone(A._linie_aus_name(None))

    def test_ein_1x2_markt_hat_keine_linie_und_bleibt_offen(self):
        """„Half Time" ist ein 1X2-Markt. Ihn ueber den Torstand zu sperren waere falsch — dort
        entscheidet weiter nur das Fenster."""
        self.assertTrue(A.ht_linie_offen(self._m(tore=(2, 1)), "Half Time"))

    def test_ohne_torangabe_sperrt_nichts(self):
        """Hier ausnahmsweise NICHT fail-closed: liefert ein Anbieter das Feld nicht, faellt sonst
        der ganze Kanal aus. Die Minute deckt diesen Fall bereits ab — das ist die zweite
        Sicherung, nicht die einzige."""
        for li in (None, (), ):
            pass
        m = self._m(tore=None)
        self.assertTrue(A.ht_linie_offen(m, "First Half Goals 1.5"))
        m2 = self._m(tore=(True, 1))
        self.assertTrue(A.ht_linie_offen(m2, "First Half Goals 1.5"),
                        "bool ist keine Torzahl")

    def test_tore_gefallen_unterscheidet_null_von_unbekannt(self):
        """Beim Provozieren aufgefallen: `tore_gefallen` gab bei fehlender Angabe 0 zurueck statt
        None, und die Suite blieb gruen — weil BEIDE Faelle in `ht_linie_offen` zu „offen" fuehren
        und der Unterschied dort nicht sichtbar ist. Er ist es trotzdem: 0 heisst „noch kein Tor",
        None heisst „wir wissen es nicht", und wer die Funktion spaeter anders benutzt, braucht
        die Unterscheidung. Also wird sie HIER geprueft, wo sie entsteht."""
        self.assertEqual(A.tore_gefallen({"liveInfo": {"goal_v1": 0, "goal_v2": 0}}), 0)
        self.assertEqual(A.tore_gefallen({"liveInfo": {"goal_v1": 2, "goal_v2": 1}}), 3)
        self.assertIsNone(A.tore_gefallen({"liveInfo": {}}))
        self.assertIsNone(A.tore_gefallen({}))
        self.assertIsNone(A.tore_gefallen({"liveInfo": {"goal_v1": 1}}))
        self.assertIsNone(A.tore_gefallen({"liveInfo": {"goal_v1": None, "goal_v2": 1}}))
        self.assertIsNone(A.tore_gefallen({"liveInfo": {"goal_v1": True, "goal_v2": 1}}),
                          "bool ist keine Torzahl — True+1 waere 2")

    def test_eine_ganzzahlige_linie_wird_nicht_zu_frueh_gesperrt(self):
        """Auch beim Provozieren aufgefallen: `<` gegen `<=` ist bei X,5-Linien nicht
        unterscheidbar, weil Tore ganzzahlig sind. Bei einer ganzzahligen Linie sehr wohl —
        bei „Goals 2" und 2 Toren ist der Markt nicht entschieden, sondern Push. Die Regel muss
        also stimmen, bevor so ein Markt auftaucht, nicht danach."""
        self.assertTrue(A.ht_linie_offen(self._m(tore=(1, 1)), "First Half Goals 2"),
                        "2 Tore bei Linie 2 ist Push, nicht entschieden")
        self.assertFalse(A.ht_linie_offen(self._m(tore=(2, 1)), "First Half Goals 2"))

    def test_die_fix_auswahl_ueberspringt_entschiedene_maerkte(self):
        """Zweite Aufrufstelle: der „HZ > FT"-Vergleich. Eine Tatsache mit einer
        Wahrscheinlichkeit zu vergleichen ist dort genauso falsch."""
        import inspect
        q = inspect.getsource(A)
        i = q.index("for name in FIX_HT_MARKETS:")
        self.assertIn("ht_linie_offen", q[i:i + 400])


if __name__ == "__main__":
    unittest.main()
