#!/usr/bin/env python3
"""
test_learn_matchday_filter.py — Runde 1 (alte Engine) aus dem Lern-Loop ausschließen
(23.06.2026, Lucas). Ledger behält die Historie; Bayesian-Updater + Pick-Kalibrierung lernen
erst ab MD2, damit die alte ST1-Engine die neuen Gewichte nicht verwässert.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import update_signal_weights as U      # noqa: E402
import compute_pick_calibration as C   # noqa: E402


class TestMatchdayParse(unittest.TestCase):
    def test_from_matchkey(self):
        self.assertEqual(U._matchday_of({"matchKey": "A-1-MEX-ZAF"}), 1)
        self.assertEqual(U._matchday_of({"matchKey": "D-2-TUR-PRY"}), 2)
        self.assertEqual(C._matchday_of({"key": "L-3-ENG-PAN|Über 2.5 Tore"}), 3)

    def test_explicit_field_wins(self):
        self.assertEqual(U._matchday_of({"matchday": 2, "matchKey": "X-1-A-B"}), 2)

    def test_unparseable_none(self):
        self.assertIsNone(U._matchday_of({"matchKey": "weird"}))


class TestUpdaterFiltersMd1(unittest.TestCase):
    def test_md1_skipped_md2_kept(self):
        import json, tempfile, unittest.mock as mock
        from pathlib import Path
        recs = {"records": [
            {"matchKey": "A-1-MEX-ZAF", "result": "WIN", "signals": [{"name": "x", "score": 1}]},
            {"matchKey": "A-2-MEX-KOR", "result": "LOSS", "signals": [{"name": "x", "score": 1}]},
            {"matchKey": "L-3-ENG-PAN", "result": "WIN", "signals": [{"name": "x", "score": 1}]},
        ]}
        tmp = Path(tempfile.mkdtemp()) / "ledger.json"
        tmp.write_text(json.dumps(recs))
        with mock.patch.object(U, "LEDGER_FILE", tmp):
            out = U._load_results()
        mds = sorted(U._matchday_of(r) for r in out)
        self.assertEqual(mds, [2, 3], "MD1 muss raus, MD2+MD3 bleiben")


class TestCalibrationFiltersMd1(unittest.TestCase):
    def test_md1_excluded_from_calibration(self):
        ledger = {"records": [
            {"matchKey": "A-1-AAA-BBB", "result": "LOSS", "processVerdict": "DESERVED_LOSS",
             "market": "Heimsieg", "source": "model", "signals": []},
            {"matchKey": "A-2-AAA-CCC", "result": "WIN", "processVerdict": "JUSTIFIED",
             "market": "Heimsieg", "source": "model", "signals": []},
        ]}
        cal = C.compute(ledger)
        # Baseline darf nur den MD2-Win enthalten (= 1.0), nicht den MD1-Loss
        self.assertEqual(cal["_meta"]["baseline"], 1.0)
        self.assertEqual(cal["_meta"]["totalN"], 1)


if __name__ == "__main__":
    unittest.main()
