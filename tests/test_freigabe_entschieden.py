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
