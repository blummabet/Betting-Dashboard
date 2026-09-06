"""Eine entschiedene Messung wird nicht in Hoffnung umgeschrieben — 06.09.2026.

Lucas über die oberste Kachel: „da versteh ich zwar nicht, was da wirklich angezeigt wird und
wieso, aber ist halt alles schon zu komplex."

Ein Teil davon war kein Verständnisproblem, sondern ein Widerspruch in der Zeile selbst:

    🔒 Poly-Auswahl · von Betfair bestätigt
       Kandidat — „59 von 60 Plays SEIT der Anmeldung — noch 1"
       dieselbe Zeile:  n=59 · ROI −9,4 % · ROI-Untergrenze **−30,6 %**

„Noch ein Play" liest sich wie kurz vor der Freigabe. Die Zahl daneben sagt das Gegenteil: bei
59 Plays und einer Untergrenze von −30,6 % dreht ein einzelner Play nichts mehr. Klasse:
*ein Satz behauptet, was die Zahl daneben widerlegt* — ausgerechnet in der obersten Kachel.

Das Ziel-n aus der Vorregistrierung bleibt (niemand hört auf zu messen, sobald die Zahl
gefällt) — aber der Zählstand wandert in den Grund, statt das Urteil zu überschreiben.
"""
import unittest

import freigabe as F


class TestEntschiedenBleibtEntschieden(unittest.TestCase):
    def _row(self, renditen, clvs=None, letzter="2026-09-06T12:00:00Z"):
        return F.bewerte("Test", "poly", renditen, clvs if clvs is not None else [0.0] * len(renditen),
                         letzter=letzter, now=None)

    def test_klar_negativ_ist_kein_kandidat(self):
        """Der Kern: eine Schublade mit belegter Negativ-Untergrenze ist beantwortet."""
        r = self._row([-0.5 - (i % 3) * 0.05 for i in range(59)])
        self.assertIsNotNone(r["roiLb"])
        self.assertLessEqual(r["roiLb"], F.MIN_ROI_LB)
        self.assertEqual(r["status"], "geprueft")
        self.assertNotIn("noch", r["grund"].lower(),
                         "der Grund darf nicht nach 'gleich geschafft' klingen")

    def test_unter_der_mindestzahl_bleibt_es_offen(self):
        """Ohne Untergrenze gibt es nichts zu entscheiden — dann ist 'sammelt' richtig."""
        r = self._row([0.2] * 12)
        self.assertIsNone(r["roiLb"])
        self.assertIn(r["status"], ("sammelt", "kandidat"))

    def test_positiver_roi_ohne_clv_wird_nicht_freigegeben(self):
        """Fail-closed: ohne CLV bleibt Glück und Kante ununterscheidbar. Zwei Betfair-
        Schubladen mit belegtem ROI (+36 % bzw. +5,4 %) stehen genau deshalb auf 'geprueft'."""
        r = F.bewerte("Test", "betfair", [0.4 + (i % 3) * 0.05 for i in range(40)], [],
                      letzter="2026-09-06T12:00:00Z")
        self.assertGreater(r["roiLb"], 0)
        self.assertEqual(r["status"], "geprueft")
        self.assertIn("CLV", r["grund"])

    def test_negativer_clv_blockt_trotz_belegtem_roi(self):
        """Der reale Fall „Public-Kandidaten": ROI +19,6 % mit Untergrenze +0,63 %, aber
        CLV-Untergrenze −2,53 pp. Der Markt widerspricht — also keine Freigabe."""
        r = F.bewerte("Test", "poly", [0.4 + (i % 3) * 0.05 for i in range(40)],
                      [-2.0 - (i % 3) * 0.1 for i in range(40)],
                      letzter="2026-09-06T12:00:00Z")
        self.assertGreater(r["roiLb"], 0)
        self.assertLess(r["clvLb"], 0)
        self.assertEqual(r["status"], "geprueft")

    def test_beides_belegt_gibt_frei(self):
        r = F.bewerte("Test", "poly", [0.4 + (i % 3) * 0.05 for i in range(40)],
                      [2.0 + (i % 3) * 0.1 for i in range(40)],
                      letzter="2026-09-06T12:00:00Z")
        self.assertEqual(r["status"], "freigegeben")


class TestBoardBleibtLesbar(unittest.TestCase):
    def test_keine_zeile_verspricht_was_ihre_zahl_widerlegt(self):
        """Gegen das echte Artefakt: keine Zeile darf 'noch N Plays' sagen, während ihre
        eigene Untergrenze die Sache schon entschieden hat."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "freigabe.json"
        if not p.exists():
            self.skipTest("freigabe.json fehlt")
        d = json.loads(p.read_text(encoding="utf-8"))
        schuldig = [a["schublade"] for a in (d.get("alle") or [])
                    if a.get("roiLb") is not None and a["roiLb"] <= 0
                    and a.get("status") in ("kandidat", "sammelt")
                    and "noch" in str(a.get("grund", ""))]
        self.assertEqual(schuldig, [],
                         "Diese Zeilen versprechen Fortschritt, obwohl sie gemessen negativ "
                         "sind: " + ", ".join(schuldig))


if __name__ == "__main__":
    unittest.main()


class TestBetfairSchubladenNutzenDieEchteSchranke(unittest.TestCase):
    """06.09.2026, Lucas: „ok, da hat es noch nichts rein geschafft? … könnte für immer leer
    sein eigentlich."

    Beim Nachrechnen: von drei Schubladen, die auf dem Board die ROI-Hürde nahmen, waren ZWEI
    ein Artefakt der Betfair-Näherung. `freigabe.py` rekonstruierte eine eigene Untergrenze aus
    n/hitRate/roi, obwohl `betfair_track_record.json` für denselben Eimer längst eine aus den
    Rohzeilen mitschreibt (`roiUg`). Bei genau diesen beiden kam sie im VORZEICHEN anders heraus:

        Half Time                                n=1840   Näherung +0,43 %   roiUg −0,26 %
        Sky Bet League 2 · First Half Goals 1.5  n=  33   Näherung +4,63 %   roiUg −0,05 %

    Zwei Untergrenzen für dieselbe Menge — die zweite entstand hier, nicht dort.
    """

    def _rec(self, roi_ug):
        return {"byMarket": {"Half Time": {"n": 1840, "hitRate": 0.4022, "roi": 0.0536,
                                           "roiUg": roi_ug, "nClvBf": 1840, "avgClvBf": 0.04}}}

    def test_die_untergrenze_kommt_aus_dem_produzenten(self):
        r = F.betfair_schubladen(self._rec(-0.0026))[0]
        self.assertEqual(r["roiLb"], -0.0026)
        self.assertFalse(r["naeherung"], "mit echter Schranke ist es keine Naeherung mehr")
        self.assertEqual(r["status"], "geprueft")

    def test_ohne_roiUg_bleibt_die_naeherung_und_sagt_es(self):
        rec = self._rec(None)
        rec["byMarket"]["Half Time"].pop("roiUg")
        r = F.betfair_schubladen(rec)[0]
        self.assertIsNotNone(r["roiLb"])
        self.assertTrue(r["naeherung"])

    def test_gemessener_clv_wird_nicht_als_fehlend_ausgegeben(self):
        """„kein CLV im Ledger" und „CLV gemessen, aber ohne Streuung" sind zwei verschiedene
        Zustaende. Kein Urteil ist etwas anderes als ein gemessenes Nein."""
        r = F.betfair_schubladen(self._rec(0.02))[0]
        self.assertGreater(r["roiLb"], 0)
        self.assertEqual(r["clv"], 0.04)
        self.assertIn("Streuung", r["grund"])
        self.assertNotEqual(r["status"], "freigegeben", "ohne CLV-Untergrenze keine Freigabe")

    def test_ohne_jeden_clv_sagt_der_grund_genau_das(self):
        rec = self._rec(0.02)
        rec["byMarket"]["Half Time"].pop("avgClvBf")
        r = F.betfair_schubladen(rec)[0]
        self.assertIn("gar kein CLV", r["grund"])

    def test_gegen_den_echten_bestand_nimmt_keine_betfair_schublade_die_huerde(self):
        """Stand 06.09.: null. Nimmt eine die Huerde, schlaegt dieser Test an — und DAS ist
        die Nachricht."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "betfair_track_record.json"
        if not p.exists():
            self.skipTest("kein Track-Record")
        rows = F.betfair_schubladen(json.loads(p.read_text(encoding="utf-8")))
        pos = [r["schublade"] for r in rows if r.get("roiLb") is not None and r["roiLb"] > 0]
        self.assertEqual(pos, [], f"Neu ueber der ROI-Huerde: {pos} — bitte ansehen.")


class TestEntfernungZumBeleg(unittest.TestCase):
    """„In 12 Plays nächste Chance" war nicht die Entfernung zur Freigabe — 06.09.2026.

    Lucas: „ok, da hat es noch nichts rein geschafft? In 12 Plays nächste Chance. Kann aber dann
    wieder sein, dass nichts gezeigt wird. Sprich könnte für immer leer sein eigentlich."

    Nachgerechnet an der stärksten lebendigen Schublade:

        Konjunktion · Top-5 + MLS   n=15
          ROI  Schnitt +9,7 %   Streuung 0,958  ->  Untergrenze>0 ab n≈263  (noch ~248)
          CLV  Schnitt +1,91pp  Streuung 2,980  ->  Untergrenze>0 ab n≈7    (erfüllt)

    Auf dem Board stand „noch 15". `MIN_N`=30 ist die Zahl, ab der überhaupt GERECHNET wird —
    nicht die, ab der etwas belegt ist. Bei Renditen ist die Streuung rund zehnmal so groß wie
    der Schnitt; genau deshalb ist CLV der schnelle und ROI der langsame Richter.
    """

    def test_die_hochrechnung_faellt_mit_der_streuung(self):
        eng = F.noetiges_n([0.10, 0.11, 0.09, 0.10, 0.10])
        weit = F.noetiges_n([1.2, -0.9, 1.1, -0.8, 0.9])
        self.assertIsNotNone(eng)
        self.assertIsNotNone(weit)
        self.assertLess(eng, weit, "mehr Streuung muss mehr Plays verlangen, nicht weniger")

    def test_ohne_positiven_schnitt_gibt_es_keine_zahl(self):
        """Warten ist dann keine Strategie — mehr Plays bestaetigen das Minus."""
        self.assertIsNone(F.noetiges_n([-0.1, -0.2, 0.05, -0.3]))
        self.assertIsNone(F.noetiges_n([0.0, 0.0, 0.0]))

    def test_zu_wenige_werte_erfinden_nichts(self):
        self.assertIsNone(F.noetiges_n([]))
        self.assertIsNone(F.noetiges_n([0.5]))
        self.assertIsNone(F.noetiges_n(None))

    def test_die_zahl_stimmt_mit_der_untergrenze_ueberein(self):
        """Der Test der Rechnung selbst: bei genau `noetiges_n` Werten derselben Verteilung
        muss `untergrenze` tatsaechlich ueber null liegen — sonst ist die Zahl geraten."""
        muster = [0.9, -0.6, 0.8, -0.5, 0.7, -0.4]
        k = F.noetiges_n(muster)
        self.assertIsNotNone(k)
        viele = (muster * (k // len(muster) + 2))[:k]
        self.assertGreater(F.untergrenze(viele), 0)
        knapp = (muster * (k // len(muster) + 2))[:max(2, int(k * 0.5))]
        self.assertLessEqual(F.untergrenze(knapp) or -1, 0,
                             "bei halber Stichprobe darf sie noch NICHT belegt sein")

    def test_der_grund_nennt_die_echte_entfernung(self):
        """Eine Zeile, die „noch 15" sagt, waehrend ~248 gemeint sind, ist derselbe Fehler wie
        eine Prosa, die ihre eigene Zahl daneben widerlegt."""
        r = F.bewerte("Test", "betfair", [0.9, -0.6, 0.8, -0.5, 0.7, -0.4] * 2,
                      [2.0, 1.5, 2.5, 1.0, 2.2, 1.8] * 2, letzter="2026-09-06T12:00:00Z")
        self.assertEqual(r["status"], "kandidat")
        self.assertIn("Plays nötig", r["grund"])
        self.assertIsNotNone(r["noetigNRoi"])
        self.assertGreater(r["noetigNRoi"], r["n"])

    def test_belegter_clv_wird_bei_offenem_roi_genannt(self):
        """Der reale Fall: CLV schon belegt, ROI weit weg. Wer nur „noch 15" liest, sieht nicht,
        dass die eine Huerde langst genommen ist und die ANDERE blockiert."""
        r = F.bewerte("Test", "betfair", [0.9, -0.6, 0.8, -0.5, 0.7, -0.4] * 2,
                      [2.0, 1.9, 2.1, 2.0, 1.95, 2.05] * 2, letzter="2026-09-06T12:00:00Z")
        self.assertIn("CLV ist bereits belegt", r["grund"])

    def test_reife_schubladen_bekommen_keine_hochrechnung_in_den_grund(self):
        """Ab n>=MIN_N steht dort ein URTEIL. Eine Hochrechnung daneben wuerde es aufweichen."""
        r = F.bewerte("Test", "poly", [-0.5] * 40, [0.0] * 40, letzter="2026-09-06T12:00:00Z")
        self.assertEqual(r["status"], "geprueft")
        self.assertNotIn("nötig", r["grund"])

    def test_gegen_den_echten_bestand_ist_die_entfernung_groesser_als_der_balken(self):
        """Haelt den Stand vom 06.09. fest: mindestens eine Kandidaten-Zeile braucht mehr Plays
        als der Balken (n/30) suggeriert. Wird das eines Tages falsch, ist das die Nachricht."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "freigabe.json"
        if not p.exists():
            self.skipTest("freigabe.json fehlt")
        d = json.loads(p.read_text(encoding="utf-8"))
        kand = d.get("kandidaten") or []
        if not kand:
            self.skipTest("keine Kandidaten")
        for r in kand:
            if r.get("noetigNRoi") is None:
                continue
            self.assertIsInstance(r["noetigNRoi"], int)
        weit = [r for r in kand if (r.get("noetigNRoi") or 0) > (d.get("regeln", {}).get("minN") or 30)]
        self.assertTrue(weit, "keine Zeile braucht mehr als die Mindestzahl — bitte nachsehen, "
                              "das waere neu")
