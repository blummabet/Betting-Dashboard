"""tests/test_h2h_richtung.py — 04.09.2026

Lucas: „es wird mal wieder Zeit für einen Cards-Check."

Auf der Venezia-Card stand woertlich:

    ⚔️ Aus den letzten 4 Duellen: im Schnitt 1.2 Tore (Linie 2.5) ·
       in 25% fielen ueber 2.5 Tore → spricht fuer Ueber 2.5.

daneben der Wert **-3,5pp**. Die Zahlen waren richtig, der Satz sagte das Gegenteil: 1,2 Tore
im Schnitt und 25% Ueber-Quote sprechen ersichtlich GEGEN Ueber 2,5. Dasselbe auf der
Elche-Card (2,2 Tore, 40% → „spricht fuer Ueber 2.5", Wert -1,0pp).

Die Ursache: `side_str` kam aus der PICK-Richtung (`ou_dir`), der Schluss-Satz war damit
unabhaengig vom Ergebnis immer zustimmend. Wer nur die Begruendung liest — und dafuer ist sie
da — bekam ein Argument fuer den Pick, wo das Signal dagegen sprach.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_signals.h2h_pattern import H2HPatternSignal


def ctx(avg, over_rate, games=10):
    return {"h2h": {"games": games, "avgGoals": avg, "over25Rate": over_rate}}


class OuRichtung(unittest.TestCase):
    def setUp(self):
        self.sig = H2HPatternSignal()

    def _lauf(self, markt, avg, rate, games=10):
        return self.sig.evaluate({"market": markt}, ctx(avg, rate, games))

    def test_der_reale_venezia_fall(self):
        """4 Duelle, 1,2 Tore im Schnitt, 25% ueber 2,5 — bei einem Ueber-Pick."""
        r = self._lauf("Über 2.5 Tore", 1.2, 0.25, games=4)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0, "das Signal spricht gegen den Pick")
        self.assertIn("spricht gegen Über 2.5", r.evidence)
        self.assertNotIn("spricht für Über", r.evidence)

    def test_der_reale_elche_fall(self):
        r = self._lauf("Über 2.5 Tore", 2.2, 0.40)
        self.assertLess(r.score, 0)
        self.assertIn("spricht gegen", r.evidence)

    def test_zustimmung_bleibt_zustimmung(self):
        r = self._lauf("Über 2.5 Tore", 3.4, 0.70)
        self.assertGreater(r.score, 0)
        self.assertIn("spricht für Über 2.5", r.evidence)

    def test_auch_bei_unter_picks_stimmt_die_richtung(self):
        gegen = self._lauf("Unter 2.5 Tore", 3.6, 0.75)
        self.assertLess(gegen.score, 0)
        self.assertIn("spricht gegen Unter 2.5", gegen.evidence)
        fuer = self._lauf("Unter 2.5 Tore", 1.4, 0.20)
        self.assertGreater(fuer.score, 0)
        self.assertIn("spricht für Unter 2.5", fuer.evidence)

    def test_die_zahlen_bleiben_unveraendert_im_satz(self):
        """Nur der Schluss aendert sich — die Belege selbst waren nie falsch."""
        r = self._lauf("Über 2.5 Tore", 1.2, 0.25, games=4)
        self.assertIn("im Schnitt 1.2 Tore (Linie 2.5)", r.evidence)
        self.assertIn("in 25% fielen über 2.5 Tore", r.evidence)


class BttsRichtung(unittest.TestCase):
    """Dieselbe Krankheit im BTTS-Zweig: „passt zu" galt auch dort, wo das Signal dagegen lief."""

    def setUp(self):
        self.sig = H2HPatternSignal()

    def _lauf(self, markt, rate):
        return self.sig.evaluate({"market": markt}, {"h2h": {"games": 10, "bttsRate": rate}})

    def test_gegenlaeufiges_btts_sagt_das_auch(self):
        r = self._lauf("Beide Teams treffen — Ja", 0.20)
        self.assertLess(r.score, 0)
        self.assertIn("spricht gegen", r.evidence)
        self.assertNotIn("passt zu", r.evidence)

    def test_stuetzendes_btts_passt_weiterhin(self):
        r = self._lauf("Beide Teams treffen — Ja", 0.80)
        self.assertGreater(r.score, 0)
        self.assertIn("passt zu", r.evidence)
