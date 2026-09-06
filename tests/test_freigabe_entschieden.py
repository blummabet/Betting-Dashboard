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
