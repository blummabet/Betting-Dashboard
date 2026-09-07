"""Der Fade der Betfair-Geldseite — 06.09.2026.

Lucas: „wenn wir sehen, dass die gespielten Sachen schlecht liefen, dann könnte man das ja auch
ins Positive umkehren und faden. Das könnte auch eine Strategie sein."

Durchgerechnet, und es trägt — aber nur an einer Stelle. Von 16 Markt×Seite-Schnitten über
15.945 abgerechnete Zeilen waren in Such- UND Prüfhälfte genau zwei positiv, beide vom selben
Typ (Ganzspiel-Torlinie, Geld auf UNTER):

    n=2.720   Geldseite trifft 59,2 % gegen 62,4 % implizit  →  -3,2 pp
    Fade nach 5 % Kommission:  Suche +5,5 %  ·  Prüfung +5,2 %

Der Grund, warum das überhaupt gehen kann: Betfair ist eine BÖRSE. Gemessener Overround über
138 Spiele: Median +0,3 %. Bei einem Buchmacher mit 5 % Overround bräuchte derselbe Fehler
-15 % auf der gespielten Seite, bevor sich das Faden lohnt.

Die Tests halten drei Dinge fest: die Regel, die Rechnung — und die Kontrolle. Ein Befund ohne
Kontrollgruppe ist eine Behauptung.
"""
import json
import unittest
from pathlib import Path

import fade_unter as F

BASE = Path(__file__).resolve().parents[1]


def _z(markt="Over/Under 2.5 Goals", fav="UNDER", odd=1.70, win=False, geg=None, vol=None,
       settled="2026-09-10T12:00:00+00:00"):
    z = {"market": markt, "fav": fav, "odd": odd, "entryOdd": odd, "win": win,
         "settledAt": settled}
    if geg is not None:
        z["entryGegenOdd"] = geg
        z["gegenOdd"] = geg
    if vol is not None:
        z["gegenVol"] = vol
    return z


class TestRegel(unittest.TestCase):
    def test_sie_greift_nur_auf_ganzspiel_torlinien_mit_geld_auf_unter(self):
        self.assertTrue(F.gilt(_z()))
        self.assertTrue(F.gilt(_z(markt="Over/Under 3.5 Goals")))
        self.assertFalse(F.gilt(_z(fav="OVER")), "Geld auf ÜBER ist der andere Fall — gemessen -8,3 %")
        self.assertFalse(F.gilt(_z(markt="First Half Goals 1.5")),
                         "die 1.-HZ-Linie ist eine KONTROLLE, kein Treffer — dort verliert der Fade")
        self.assertFalse(F.gilt(_z(markt="Match Odds", fav="H")))

    def test_die_maerkte_stehen_fest(self):
        """Die Regel ist vorregistriert. Wer sie erweitert, startet die Messung neu — deshalb
        soll eine Änderung hier laut sein und nicht nebenbei passieren."""
        self.assertEqual(F.MAERKTE, frozenset({"Over/Under 2.5 Goals", "Over/Under 3.5 Goals"}))
        self.assertEqual(F.GELD_SEITE, "UNDER")


class TestRechnung(unittest.TestCase):
    def test_kam_die_geldseite_verliert_der_fade_voll(self):
        w, _ = F.fade_rendite(_z(win=True, geg=2.40))
        self.assertEqual(w, -1.0)

    def test_kam_sie_nicht_zahlt_die_gegenseite_abzueglich_kommission(self):
        w, q = F.fade_rendite(_z(win=False, geg=2.40), kommission=0.05)
        self.assertEqual(q, "echt")
        self.assertAlmostEqual(w, (2.40 - 1.0) * 0.95, places=6)

    def test_der_echte_gegenpreis_schlaegt_die_rekonstruktion(self):
        """Sobald er erhoben ist, wird nicht mehr geschätzt. Das war der grösste Einwand
        gegen den Fund und ist der Grund, warum er ab heute mitgeschrieben wird."""
        _, q1 = F.fade_rendite(_z(geg=2.40))
        _, q2 = F.fade_rendite(_z(geg=None))
        self.assertEqual(q1, "echt")
        self.assertEqual(q2, "rekon")

    def test_ohne_jeden_preis_gibt_es_keine_zahl(self):
        z = _z(geg=None)
        z["odd"] = None
        z["entryOdd"] = None
        w, grund = F.fade_rendite(z)
        self.assertIsNone(w)
        self.assertIn("Preis", grund)

    def test_nicht_abgerechnete_zeilen_zaehlen_nicht(self):
        z = _z()
        z["win"] = None
        self.assertIsNone(F.fade_rendite(z)[0])

    def test_die_rekonstruktion_haengt_am_overround(self):
        """Der Fund hält bis ~1 % und stirbt bei 2 %. Das gehört geprüft, nicht geglaubt."""
        klein, _ = F.fade_rendite(_z(geg=None), overround=0.003)
        gross, _ = F.fade_rendite(_z(geg=None), overround=0.020)
        self.assertGreater(klein, gross)

    def test_eine_unhandelbare_gegenseite_erfindet_keinen_preis(self):
        w, grund = F.fade_rendite(_z(odd=1.005, geg=None))
        self.assertIsNone(w)
        self.assertIn("handelbar", grund)


class TestMengeUndSchranke(unittest.TestCase):
    def test_unter_der_mindestzahl_gibt_es_kein_urteil(self):
        m = F._menge([_z(win=(i % 2 == 0), geg=2.4) for i in range(10)])
        self.assertEqual(m["n"], 10)
        self.assertIsNone(m["roiUg"])
        self.assertFalse(m["belegt"])

    def test_belegt_heisst_untergrenze_ueber_null(self):
        m = F._menge([_z(win=False, geg=2.4) for _ in range(60)])
        self.assertTrue(m["belegt"])
        self.assertGreater(m["roiUg"], 0)

    def test_der_vorsprung_der_geldseite_steht_mit_dabei(self):
        """Eine Trefferquote ohne die Quoten ist keine Zahl — deshalb immer gegen die eigene
        implizite Wahrscheinlichkeit."""
        m = F._menge([_z(win=(i < 30), geg=2.4, odd=2.0) for i in range(60)])
        self.assertEqual(m["treffer"], 50.0)
        self.assertEqual(m["implizit"], 50.0)
        self.assertEqual(m["vorsprungPP"], 0.0)

    def test_die_leere_menge_erfindet_nichts(self):
        m = F._menge([])
        self.assertEqual(m["n"], 0)
        self.assertIsNone(m["roi"])
        self.assertIsNone(m["roiUg"])
        self.assertFalse(m["belegt"])


class TestBilanzTrenntFundUndBeleg(unittest.TestCase):
    def test_rueckblick_und_vorreg_werden_nie_vermischt(self):
        alt = [_z(win=False, geg=2.4, settled="2026-09-01T12:00:00+00:00") for _ in range(50)]
        neu = [_z(win=False, geg=2.4, settled="2026-09-10T12:00:00+00:00") for _ in range(7)]
        b = F.bilanz(alt + neu)
        self.assertEqual(b["rueckblick"]["n"], 50)
        self.assertEqual(b["vorreg"]["n"], 7)
        self.assertIsNone(b["vorreg"]["roiUg"], "7 Plays tragen keine Schranke")

    def test_mit_geld_ist_eine_teilmenge_von_vorreg(self):
        neu = ([_z(win=False, geg=2.4, vol=5.0) for _ in range(10)]
               + [_z(win=False, geg=2.4, vol=900.0) for _ in range(10)])
        b = F.bilanz(neu)
        self.assertEqual(b["vorreg"]["n"], 20)
        self.assertEqual(b["mitGeld"]["n"], 10,
                         "eine Gegenseite mit €5 ist kein Preis, den man bekommt")

    def test_ohne_volumen_zaehlt_die_zeile_nicht_als_bespielbar(self):
        """Fehlende Information ist keine Liquidität."""
        b = F.bilanz([_z(win=False, geg=2.4) for _ in range(10)])
        self.assertEqual(b["mitGeld"]["n"], 0)


class TestKontrollgruppe(unittest.TestCase):
    def test_die_kontrolle_ist_teil_des_artefakts(self):
        """Ohne sie ist der Befund eine Behauptung. Sie steht deshalb IM Artefakt, nicht in
        einer Fussnote."""
        b = F.bilanz([_z() for _ in range(5)])
        self.assertIn("kontrolle", b)

    def test_gegen_den_echten_bestand_verliert_der_fade_in_den_kontrollmaerkten(self):
        """Der wichtigste Test der Datei. Wo die Geldseite recht hat, MUSS derselbe Fade
        verlieren — sonst misst die Konstruktion sich selbst und der Befund oben ist wertlos.
        Stand 06.09.: Match Odds H -4,6 %, BTTS YES -6,9 %, 1.HZ 1,5 UNDER -7,5 %."""
        p = BASE / "betfair_track_results.json"
        if not p.exists():
            self.skipTest("kein Ledger")
        import betfair_track_store as S
        k = F._kontrolle(S.load(str(p)))
        if not k:
            self.skipTest("Kontrollmaerkte zu duenn")
        schuldig = [x for x in k if x["roi"] is not None and x["roi"] > 0]
        self.assertEqual(schuldig, [],
                         "Der Fade gewinnt in einem Kontrollmarkt — dann erzeugt die Rechnung "
                         "eine Kante aus sich selbst: " + str(schuldig))

    def test_der_befund_steht_gegen_den_echten_bestand(self):
        """Hält den Stand fest, aus dem die Regel stammt. Bricht er weg, ist das die Nachricht."""
        p = BASE / "betfair_track_results.json"
        if not p.exists():
            self.skipTest("kein Ledger")
        import betfair_track_store as S
        m = F._menge([z for z in S.load(str(p)) if F.gilt(z)])
        self.assertGreater(m["n"], 1000)
        self.assertLess(m["vorsprungPP"], 0,
                        "die Geldseite trifft nicht mehr schlechter als implizit — dann ist der "
                        "ganze Fund weg und die Schublade gehoert abgemeldet")


class TestOffeneListe(unittest.TestCase):
    def _prices(self):
        return {"matches": [{
            "matchId": 1, "home": "A", "away": "B", "league": "L", "kickoff": "2026-09-08T18:00:00Z",
            "liveInfo": {"finished": False},
            "markets": {"Over/Under 2.5 Goals": {"runners": [
                {"name": "Under 2.5 Goals", "odd": 1.70, "vol": 5000.0},
                {"name": "Over 2.5 Goals", "odd": 2.35, "vol": 900.0}]}}}]}

    def test_ein_passendes_spiel_erscheint_mit_der_gegenseite(self):
        o = F.offen(self._prices())
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]["geldAuf"], "Under 2.5 Goals")
        self.assertEqual(o[0]["spielen"], "Over 2.5 Goals")
        self.assertEqual(o[0]["spielenOdd"], 2.35)
        self.assertTrue(o[0]["bespielbar"])

    def test_geld_auf_ueber_erscheint_nicht(self):
        p = self._prices()
        r = p["matches"][0]["markets"]["Over/Under 2.5 Goals"]["runners"]
        r[0]["vol"], r[1]["vol"] = 900.0, 5000.0
        self.assertEqual(F.offen(p), [])

    def test_duenne_gegenseite_bleibt_sichtbar_aber_markiert(self):
        """Sie verschwinden zu lassen waere bequem und falsch — dann sähe die Regel breiter
        anwendbar aus, als sie ist."""
        p = self._prices()
        p["matches"][0]["markets"]["Over/Under 2.5 Goals"]["runners"][1]["vol"] = 5.0
        o = F.offen(p)
        self.assertEqual(len(o), 1)
        self.assertFalse(o[0]["bespielbar"])

    def test_beendete_spiele_stehen_nicht_in_der_liste(self):
        p = self._prices()
        p["matches"][0]["liveInfo"]["finished"] = True
        self.assertEqual(F.offen(p), [])


class TestVorregistrierung(unittest.TestCase):
    def test_die_schublade_ist_angemeldet(self):
        import vorregistrierung as VR
        self.assertIn("fade_unter", VR.ZUSCHNITTE)
        z = VR.ZUSCHNITTE["fade_unter"]
        self.assertEqual(z["zielN"], 200)
        self.assertTrue(z["pruef"]({"market": "Over/Under 2.5 Goals", "fav": "UNDER"}))
        self.assertFalse(z["pruef"]({"market": "Over/Under 2.5 Goals", "fav": "OVER"}))

    def test_die_schublade_rechnet_die_gegenseite_nicht_die_geldseite(self):
        """Der Fehler, der hier am leichtesten passiert: die Rohzeile durchreichen. Dann
        rechnet `_rendite` odd/win — also die Geldseite — und die Schublade misst das
        GEGENTEIL von dem, was ihr Name sagt."""
        import freigabe as FG
        plays = FG._fade_unter_plays()
        if not plays:
            self.skipTest("kein Ledger")
        self.assertTrue(all("pnl" in p and p.get("stake") == 1.0 for p in plays))
        self.assertTrue(all("odd" not in p for p in plays),
                        "eine `odd` im Play laesst _rendite die Geldseite rechnen")


if __name__ == "__main__":
    unittest.main()
