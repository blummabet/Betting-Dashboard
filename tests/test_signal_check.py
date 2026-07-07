#!/usr/bin/env python3
"""test_signal_check.py — Signal-Check (06.07.2026, Lucas): isoliertes Content-Feature.
Prüft Klassifikation, Output-Struktur, KEIN Verdict, und die harte Isolation (kein Mutieren
der Pick-Daten)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import signal_check as SC


class TestClassify(unittest.TestCase):
    def test_vorzeichen(self):
        self.assertEqual(SC._classify(2.5), "confirm")
        self.assertEqual(SC._classify(-2.5), "contradict")
        self.assertEqual(SC._classify(0.0), "neutral")
        self.assertEqual(SC._classify(0.01), "neutral")   # unter EPS


class TestReason(unittest.TestCase):
    def _mk(self, label):
        return {"name": label, "label": label, "evidence": "", "dir": "confirm"}

    def test_mehrheit_dafuer(self):
        r = SC._reason("Frankreich Sieg", [self._mk("die Formkurve")], [], "Heimsieg")
        self.assertIn("stützen", r)

    def test_mehrheit_dagegen(self):
        r = SC._reason("Frankreich Sieg", [], [self._mk("die Aufstellung")], "Heimsieg")
        self.assertIn("kritisch", r)

    def test_keine_signale(self):
        r = SC._reason("X", [], [], "Heimsieg")
        self.assertIn("keine belastbare", r)


class TestOutputAndIsolation(unittest.TestCase):
    def _wm(self):
        return json.loads((Path(__file__).parent.parent / "wm2026-data.json").read_text(encoding="utf-8"))

    def test_struktur_und_kein_verdict(self):
        wm = self._wm()
        res = SC.run_signal_check(wm, "MEX", "ZAF", "Heimsieg")
        for k in ("confirm", "contradict", "silent", "score", "headline", "reason", "disclaimer"):
            self.assertIn(k, res)
        # NIE ein Pick-Verdict
        blob = json.dumps(res, ensure_ascii=False)
        for forbidden in ("BET", "ABWÄGEN", "SKIP", "stake", "edgePP"):
            self.assertNotIn(forbidden, blob)
        self.assertIn("kein Wettaufruf", res["disclaimer"])

    def test_isolation_wm_nicht_mutiert(self):
        wm = self._wm()
        before = json.dumps(wm, ensure_ascii=False, sort_keys=True)
        SC.run_signal_check(wm, "MEX", "ZAF", "Heimsieg")
        after = json.dumps(wm, ensure_ascii=False, sort_keys=True)
        self.assertEqual(before, after, "run_signal_check darf das wm-Dict NICHT verändern")

    def test_side_mapping(self):
        wm = self._wm()
        self.assertEqual(SC.run_signal_check(wm, "MEX", "ZAF", "Heimsieg")["side"], "home")
        self.assertEqual(SC.run_signal_check(wm, "MEX", "ZAF", "Über 2.5 Tore")["side"], "over")


if __name__ == "__main__":
    unittest.main()
