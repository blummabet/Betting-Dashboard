# -*- coding: utf-8 -*-
"""tests/test_poly_konvergenz.py — 16.09.2026

Lucas: „Ich seh die offenen 3 Trades auf Poly, die getriggert wurden, weil Pinnacle bewegt und
Poly scheinbar nicht … Koennen wir rueckwirkend auslesen, ob Poly ueberhaupt zu unseren Gunsten
anpasst? Weil eventuell machen die das nie und ist nur unsere Theorie."

Die Theorie traegt den ganzen Auto-Trader. Diese Tests halten fest, WORAN sie scheitern darf:
an einer unsauberen Kontrollgruppe, an einem einseitigen Ergebnis, an einer Untergrenze unter
null — und nicht daran, dass jemand die Schwelle so lange dreht, bis die Zahl passt.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import poly_konvergenz as K  # noqa: E402

T0 = datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)
KO = T0 + timedelta(hours=30)


def _daten(n=40):
    """n Spiele mit Anpfiff — die Schluessel sind `home-away`, wie in der Historie."""
    return {"groups": {"X": {"fixtures": [
        {"home": str(i), "away": "9" + str(i), "kickoff": KO.isoformat()} for i in range(n)]}}}


def _serie(poly, edge, start=T0, schritt_h=2.0):
    """Eine Snapshot-Reihe fuer den Ausgang `hw`. `poly`/`edge` sind gleich lange Listen."""
    return [{"ts": (start + timedelta(hours=schritt_h * k)).isoformat(),
             "poly_hw": p, "edge_hw": e} for k, (p, e) in enumerate(zip(poly, edge))]


def _hist(n, poly, edge):
    return {"%d-9%d" % (i, i): _serie(poly, edge) for i in range(n)}


class TestDieEinheit(unittest.TestCase):
    """Ein Spiel zaehlt EINMAL je Arm. Sonst zaehlt ein Spiel mit vierzig Snapshots so viel
    wie vierzig Spiele — und die Untergrenze wird zur Erfindung."""

    def test_ein_spiel_ein_datenpunkt_je_arm(self):
        h = {"1-91": _serie([0.30] * 6, [6.0] * 6)}
        z = K.beobachtungen(h, {"1-91": KO})
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0]["arm"], "dafuer")

    def test_gemessen_wird_bis_zum_letzten_kurs_vor_anpfiff(self):
        h = {"1-91": _serie([0.30, 0.31, 0.34], [6.0, 5.0, 2.0])}
        z = K.beobachtungen(h, {"1-91": KO})
        self.assertAlmostEqual(z[0]["polyPP"], 4.0, places=2)

    def test_snapshots_nach_anpfiff_zaehlen_nicht(self):
        """Nach dem Anpfiff bewegen sich beide Reihen wegen der Tore. Das hat mit der Frage
        nichts zu tun — und wuerde sie mit riesigen Bewegungen zumuellen."""
        h = {"1-91": _serie([0.30, 0.31, 0.95], [6.0, 5.0, -40.0],
                            start=KO - timedelta(hours=4), schritt_h=3.0)}
        z = K.beobachtungen(h, {"1-91": KO})
        self.assertEqual(z, [], "der Snapshot lag nach dem Anpfiff bzw. zu nah davor")

    def test_die_letzten_stunden_vor_anpfiff_loesen_nichts_aus(self):
        """`MIN_HOURS_BEFORE_MATCH` ist dieselbe Schranke, an der auch der Trigger haelt."""
        spaet = KO - timedelta(hours=1)
        h = {"1-91": [{"ts": spaet.isoformat(), "poly_hw": 0.3, "edge_hw": 9.0},
                      {"ts": (spaet + timedelta(minutes=20)).isoformat(),
                       "poly_hw": 0.4, "edge_hw": 0.0}]}
        self.assertEqual(K.beobachtungen(h, {"1-91": KO}), [])

    def test_platzhalter_preise_fliegen_raus(self):
        """0.0/1.0 sind „kein Markt", nicht „sicher" — ungefiltert erzeugen sie 70pp-Spruenge."""
        h = {"1-91": _serie([0.0, 0.5, 1.0], [9.0, 9.0, 9.0])}
        self.assertEqual(K.beobachtungen(h, {"1-91": KO}), [])


class TestDasUrteil(unittest.TestCase):
    def _bericht(self, hist, n=40):
        return K.bericht(hist, _daten(n))

    def test_der_gesunde_fall_heisst_zieht_nach(self):
        h = {}
        h.update(_hist(40, [0.30, 0.32, 0.35], [6.0, 4.0, 1.0]))                       # dafuer: Poly rauf
        for i in range(40, 80):                                            # dagegen: Poly runter
            h["%d-9%d" % (i, i)] = _serie([0.40, 0.38, 0.35], [-6.0, -4.0, -1.0])
        for i in range(80, 140):                                           # neutral: flach
            h["%d-9%d" % (i, i)] = _serie([0.50, 0.50, 0.50], [0.2, 0.2, 0.2])
        d = _daten(140)
        r = K.bericht(h, d)
        self.assertEqual(r["urteil"], "zieht nach", r["grund"])
        self.assertTrue(r["belegt"])
        self.assertEqual(r["arme"]["dafuer"]["spiele"], 40)

    def test_eine_driftende_kontrollgruppe_kippt_das_urteil(self):
        """Der wichtigste Test: bewegt sich auch die Kontrolle, misst die Rechnung den Drift
        der Reihe und nicht die Konvergenz. Dann darf nichts belegt sein."""
        h = {}
        h.update(_hist(40, [0.30, 0.32, 0.35], [6.0, 4.0, 1.0]))
        for i in range(80, 140):
            h["%d-9%d" % (i, i)] = _serie([0.50, 0.51, 0.53], [0.2, 0.2, 0.2])        # Kontrolle driftet
        r = K.bericht(h, _daten(140))
        self.assertEqual(r["urteil"], "Kontrolle unsauber")
        self.assertFalse(r["belegt"])

    def test_ein_einseitiges_ergebnis_ist_kein_beleg(self):
        """Nur der Fuer-Arm bewegt sich, der Spiegel nicht — das ist auch mit einem blossen
        Aufwaertsdrift der Preise vereinbar."""
        h = {}
        h.update(_hist(40, [0.30, 0.32, 0.35], [6.0, 4.0, 1.0]))
        for i in range(40, 80):
            h["%d-9%d" % (i, i)] = _serie([0.40, 0.42, 0.45], [-6.0, -9.0, -11.0])     # Poly laeuft WEG
        for i in range(80, 140):
            h["%d-9%d" % (i, i)] = _serie([0.50, 0.50, 0.50], [0.2, 0.2, 0.2])
        r = K.bericht(h, _daten(140))
        self.assertEqual(r["urteil"], "nur einseitig")
        self.assertFalse(r["belegt"])

    def test_ohne_untergrenze_ueber_null_kein_beleg(self):
        """Ein POSITIVER SCHNITT mit einer Schranke unter null: 34 Spiele −1 pp, 6 Spiele +9 pp
        ergeben +0,5 pp im Mittel und eine Untergrenze klar im Minus. Genau die Konstellation,
        an der ein Urteil am Punktschaetzer haengenbleiben wuerde — „ein Punktschaetzer
        entscheidet nichts" gilt auch hier."""
        h = {}
        for i in range(40):
            dp = 0.09 if i < 6 else -0.01
            h["%d-9%d" % (i, i)] = _serie([0.30, 0.30, round(0.30 + dp, 3)], [6.0, 4.0, 1.0])
        for i in range(80, 140):
            h["%d-9%d" % (i, i)] = _serie([0.50, 0.50, 0.50], [0.2, 0.2, 0.2])
        r = K.bericht(h, _daten(140))
        self.assertGreater(r["arme"]["dafuer"]["polyPP"], 0, "der SCHNITT ist positiv …")
        self.assertLess(r["arme"]["dafuer"]["polyUgPP"], 0, "… die Untergrenze nicht")
        self.assertEqual(r["urteil"], "kein Beleg")
        self.assertFalse(r["belegt"])

    def test_die_untergrenze_zaehlt_spiele_nicht_snapshots(self):
        """Fuenf Ausgaenge desselben Spiels sind EINE Beobachtung, nicht fuenf: sie tragen
        dieselbe Information. Ein Bootstrap ueber die Zeilen statt ueber die Spiele macht aus
        20 Spielen 125 „Belege" und die Schranke rund doppelt so eng.

        Aufbau: 20 Spiele mit −1 pp, 5 mit +9 pp, jeweils auf allen fuenf Ausgaengen. Ueber
        Zeilen gezogen laege die Untergrenze bei etwa +0,4 pp, ueber Spiele bei etwa −0,3 pp.
        """
        h = {}
        for i in range(25):
            dp = 0.09 if i < 5 else -0.01
            snaps = []
            for k, (e, pz) in enumerate(((6.0, 0.30), (4.0, 0.30), (1.0, round(0.30 + dp, 3)))):
                s = {"ts": (T0 + timedelta(hours=2.0 * k)).isoformat()}
                for o in K.AUSGAENGE:
                    s["poly_" + o], s["edge_" + o] = pz, e
                snaps.append(s)
            h["%d-9%d" % (i, i)] = snaps
        r = K.bericht(h, _daten(25))
        a = r["arme"]["dafuer"]
        self.assertEqual((a["n"], a["spiele"]), (125, 25))
        self.assertGreater(a["polyPP"], 0)
        self.assertLess(a["polyUgPP"], 0,
                        "die Untergrenze wurde ueber die Zeilen gezogen, nicht ueber die Spiele")
        self.assertFalse(r["belegt"])

    def test_zu_wenige_spiele_sind_kein_urteil(self):
        r = self._bericht(_hist(5, [0.30, 0.32, 0.35], [6.0, 4.0, 1.0]))
        self.assertEqual(r["urteil"], "zu wenig Daten")
        self.assertIsNone(r["arme"]["dafuer"]["polyUgPP"])

    def test_leere_historie_stuerzt_nicht_ab(self):
        r = K.bericht({}, _daten(3))
        self.assertEqual(r["urteil"], "zu wenig Daten")
        self.assertFalse(r["belegt"])


class TestWasDieZahlSagt(unittest.TestCase):
    def test_netto_zieht_den_halben_spread_ab(self):
        """Die Bewegung ist die des MIDS. Wir kaufen den Ask — brutto ist keine Geldaussage."""
        h = {}
        h.update(_hist(40, [0.30, 0.32, 0.35], [6.0, 4.0, 1.0]))
        for i in range(40, 80):
            h["%d-9%d" % (i, i)] = _serie([0.40, 0.38, 0.35], [-6.0, -4.0, -1.0])
        for i in range(80, 140):
            h["%d-9%d" % (i, i)] = _serie([0.50, 0.50, 0.50], [0.2, 0.2, 0.2])
        r = K.bericht(h, _daten(140))
        self.assertAlmostEqual(r["nettoPP"], r["arme"]["dafuer"]["polyPP"] - K.SPREAD_PP, places=2)

    def test_wer_die_luecke_schliesst_wird_getrennt_ausgewiesen(self):
        """Eine Luecke, die sich nur schliesst, weil Pinnacle zurueckkommt, ist fuer uns
        wertlos — also darf sie nicht als Konvergenz durchgehen."""
        h = {}
        for i in range(40):                       # Poly steht still, der Fair kommt zurueck
            h["%d-9%d" % (i, i)] = _serie([0.30, 0.30, 0.30], [8.0, 4.0, 0.0])
        r = K.bericht(h, _daten(40))
        self.assertEqual(r["arme"]["dafuer"]["polyPP"], 0.0)
        self.assertEqual(r["arme"]["dafuer"]["polyAnteil"], 0.0)

    def test_der_anteil_ist_eins_wenn_poly_alles_macht(self):
        h = {}
        for i in range(40):                       # der Fair steht, Poly laeuft hin
            h["%d-9%d" % (i, i)] = _serie([0.30, 0.34, 0.38], [8.0, 4.0, 0.0])
        r = K.bericht(h, _daten(40))
        self.assertEqual(r["arme"]["dafuer"]["polyAnteil"], 1.0)

    def test_die_schwelle_steht_nicht_zweimal_im_repo(self):
        """Der Trigger und diese Messung muessen dieselbe Kante meinen — sonst misst das eine
        nicht, was das andere tut."""
        import auto_wm_poly_trigger as A
        self.assertEqual(K.SCHWELLE_PP, A.AUTO_TRIGGER_EDGE_PP)
        self.assertEqual(K.MIN_H_VOR_ANPFIFF, A.MIN_HOURS_BEFORE_MATCH)


class TestGegenDenEchtenBestand(unittest.TestCase):
    """Der Befund vom 16.09., festgehalten. Bricht er weg, ist DAS die Nachricht."""

    def _echt(self, hist_name, daten_name):
        base = Path(__file__).resolve().parent.parent
        import json
        hp, dp = base / hist_name, base / daten_name
        if not hp.exists() or not dp.exists():
            self.skipTest("keine Historie")
        return K.bericht(json.loads(hp.read_text(encoding="utf-8")),
                         json.loads(dp.read_text(encoding="utf-8")))

    def test_liga_zieht_nach(self):
        r = self._echt("liga-poly-history.json", "liga-data.json")
        if r["arme"]["dafuer"]["spiele"] < K.MIN_SPIELE:
            self.skipTest("zu duenn")
        self.assertEqual(r["urteil"], "zieht nach", r["grund"])
        self.assertGreater(r["arme"]["dafuer"]["polyUgPP"], 0)

    def test_die_kontrollgruppe_liegt_flach(self):
        """Ohne sie waere der Befund eine Behauptung — Stand 16.09.: −0,06 pp auf 243 Spielen."""
        r = self._echt("liga-poly-history.json", "liga-data.json")
        n = r["arme"]["neutral"]
        if not n["n"]:
            self.skipTest("keine Kontrollgruppe")
        self.assertLess(abs(n["polyPP"]), 0.5, "die Kontrollgruppe driftet: %+.2f pp" % n["polyPP"])
