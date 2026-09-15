#!/usr/bin/env python3
"""
tests/test_trading_anker.py — 14.09.2026 (Lucas: „kannst du mir die Logik beim Trading checken,
das wo wir die Pinni-Odd als Anreiz nehmen").

Drei Funde aus dem Durchgang, alle hier festgehalten:

  1. Der Stale-Schutz prüfte das MAXIMUM über alle Spiele — also den FRISCHESTEN Zeitstempel.
     Gemessen: frischester 2,6 h (Gate grün), gleichzeitig 20 von 94 Spielen mit Odds älter als
     24 h, die ältesten 430 h.
  2. Bei Totals/BTTS/Spreads wurde das Buch weggeworfen. 22,5 % der Snapshots mit Pinnacle-1X2
     hatten einen O/U-Overround über 5 % — also einen weichen Anker, ohne dass es je feststellbar
     gewesen wäre.
  3. Die proportionale De-Vig hebt die Edge genau auf der billigen Seite an (+1,47pp unter 40¢),
     und dort lagen alle drei bisherigen Auto-Trades.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AUTO_TRIGGER_ENABLED", "false")

import auto_wm_poly_trigger as A      # noqa: E402
import odds_plausibility as OP        # noqa: E402

JETZT = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)


class DerAnkerMussVonHeuteSein(unittest.TestCase):

    def _fix(self, stunden_alt):
        ts = (JETZT - timedelta(hours=stunden_alt)).isoformat()
        return {"home": "A", "away": "B", "pinnTs": ts}

    def test_frischer_anker_ist_ok(self):
        self.assertFalse(A.odds_zu_alt(self._fix(2.6), JETZT))

    def test_alter_anker_wird_erkannt(self):
        """⭐ Der echte Fall: 430 Stunden alte Odds gegen einen Live-Poly-Preis."""
        self.assertTrue(A.odds_zu_alt(self._fix(430), JETZT))

    def test_die_grenze_liegt_beim_konfigurierten_limit(self):
        self.assertFalse(A.odds_zu_alt(self._fix(23.9), JETZT))
        self.assertTrue(A.odds_zu_alt(self._fix(24.1), JETZT))

    def test_ein_frisches_spiel_rettet_kein_altes(self):
        """Der Kern des Fundes: das globale Gate nimmt das MAXIMUM. Hier zählt jedes Spiel
        für sich — sonst hält ein einziger frischer Zeitstempel das Tor für alle offen."""
        frisch, alt = self._fix(1.0), self._fix(300)
        self.assertFalse(A.odds_zu_alt(frisch, JETZT))
        self.assertTrue(A.odds_zu_alt(alt, JETZT), "das alte Spiel darf nicht mitdurchrutschen")

    def test_ohne_zeitstempel_wird_nicht_blockiert(self):
        """Übergang: Datensätze aus einem Lauf vor dem 14.09. tragen `pinnTs` nicht. Blockieren
        hiesse, den Handel stillzulegen, bis die Pipeline einmal durch ist."""
        self.assertFalse(A.odds_zu_alt({"home": "A"}, JETZT))

    def test_kaputter_zeitstempel_behauptet_nichts(self):
        self.assertFalse(A.odds_zu_alt({"pinnTs": "gestern"}, JETZT))
        self.assertIsNone(A.odds_alter_h({"pinnTs": "gestern"}, JETZT))

    def test_der_kandidaten_filter_wendet_es_an(self):
        """Die Funktion nützt nichts, wenn der Kandidaten-Lauf sie nicht fragt."""
        import inspect
        self.assertIn("odds_zu_alt(fix)", inspect.getsource(A.find_trigger_candidates))


class DiePowerDeVigLaeuftMitEntscheidetAberNichts(unittest.TestCase):
    """Sie wird gemessen, nicht angewendet — bis der CLV in ein paar Wochen entscheidet."""

    def test_power_verteilt_die_marge_anders_als_proportional(self):
        hw, dr, aw = 1.55, 4.20, 6.50        # klarer Favorit, echter Markt
        prop = OP.devig_1x2(hw, dr, aw)
        pw = OP.devig_1x2_power(hw, dr, aw)
        self.assertIsNotNone(prop)
        self.assertIsNotNone(pw)
        self.assertGreater(pw["home"], prop["home"], "power gibt dem Favoriten mehr")
        self.assertLess(pw["away"], prop["away"], "und dem Aussenseiter weniger")

    def test_beide_summieren_sich_auf_eins(self):
        for f in (OP.devig_1x2(2.1, 3.5, 3.6), OP.devig_1x2_power(2.1, 3.5, 3.6)):
            self.assertAlmostEqual(sum(f.values()), 1.0, places=2)

    def test_zwei_wege_markt(self):
        p = OP.devig_power([1.50, 2.70])
        self.assertAlmostEqual(sum(p), 1.0, places=3)

    def test_ohne_marge_kein_ergebnis(self):
        """Summe der impliziten <= 1 heisst: keine Marge zu verteilen. Dann nichts behaupten."""
        self.assertIsNone(OP.devig_power([2.0, 2.0]))

    def test_platzhalter_quoten_kommen_nicht_durch(self):
        """Dasselbe Gate wie bei devig_1x2 — sonst waere die Messung aus Fake-Quoten gebaut."""
        self.assertIsNone(OP.devig_1x2_power(1.01, 1.04, 1.02))
        self.assertIsNone(OP.devig_power([0.5, 3.0]))

    def test_der_scharfe_pfad_bleibt_die_proportionale(self):
        """⭐ Bis zur Entscheidung darf sich am Handel nichts aendern. Die Edge, auf die gesetzt
        wird, kommt weiter aus `devig_1x2` — `fairPow_*` wird nur mitgeschrieben."""
        import inspect
        quelle = inspect.getsource(__import__("fetch_wm_poly_prices"))
        self.assertIn("edge_hw = round((fair_hw - p[\"hw\"]) * 100, 1)", quelle)
        self.assertNotIn("fairPow_hw - p[", quelle)
        self.assertIn("fairPow_hw", quelle, "die Messung muss aber mitlaufen")


class DasBuchHinterDemAnkerWirdMitgeschrieben(unittest.TestCase):
    """Die Felder heissen `pinn_o25`, das Buch war aber nicht festgehalten — und in 22,5 % der
    Faelle ist es nicht Pinnacle."""

    def test_fetch_merkt_sich_das_buch_je_markt(self):
        quelle = (Path(__file__).resolve().parent.parent / "fetch_liga_odds.py").read_text(encoding="utf-8")
        for feld in ("bookmaker_totals", "bookmaker_btts", "bookmaker_spreads"):
            self.assertIn(feld, quelle, f"{feld} wird nicht mitgeschrieben")

    def test_kein_markt_kein_buch(self):
        """Ohne Outcomes darf auch kein Buch behauptet werden — sonst steht dort ein Name
        fuer eine Linie, die es nicht gibt."""
        quelle = (Path(__file__).resolve().parent.parent / "fetch_liga_odds.py").read_text(encoding="utf-8")
        self.assertIn('if t_outs or at_outs:', quelle)
        self.assertIn('if b_outs:', quelle)
        self.assertIn('if sp_outs:', quelle)

    def test_die_preise_tragen_es_weiter(self):
        quelle = (Path(__file__).resolve().parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertIn('"pinnBooks"', quelle)
        self.assertIn('bookmaker_totals', quelle)


if __name__ == "__main__":
    unittest.main()
