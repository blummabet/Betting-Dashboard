#!/usr/bin/env python3
"""
test_xg_thin_coverage.py — Dünne-xG-Abdeckung-Dämpfer (15.06.2026, ESP-CPV-Anlass).

Hat ein Team GAR KEINE echten xG-Spiele (nur Schuss-/Form-Proxy, z.B. Kap Verde),
soll xg_strength nur die CONFIDENCE dämpfen — Richtung/Score bleiben. Sichtbar in Evidence.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.xg_strength import XGStrengthSignal

_FORM = {"ESP": {"games": 5, "avgScored": 2.9, "avgConceded": 0.6},
         "CPV": {"games": 5, "avgScored": 1.4, "avgConceded": 1.1}}


def _ctx(cpv_xggames, cpv_source=None):
    cpv = {"xgForAvg": 1.2 if cpv_xggames else 0.0, "xgAgainstAvg": 1.1 if cpv_xggames else 0.0,
           "games": 3, "xgGames": cpv_xggames}
    if cpv_source:
        cpv["source"] = cpv_source
    return {"home_id": "ESP", "away_id": "CPV", "form": _FORM, "xg_stats": {
        "ESP": {"xgForAvg": 3.21, "xgAgainstAvg": 0.54, "games": 8, "xgGames": 5, "source": "apif_real"},
        "CPV": cpv}}


class TestThinXgCoverage(unittest.TestCase):
    def setUp(self):
        self.sig = XGStrengthSignal()

    def test_thin_coverage_lowers_confidence_not_score(self):
        covered = self.sig.evaluate({"market": "Beide Teams treffen — Ja"}, _ctx(2, "apif_real"))
        thin = self.sig.evaluate({"market": "Beide Teams treffen — Ja"}, _ctx(0))
        self.assertIsNotNone(covered)
        self.assertIsNotNone(thin)
        # Score (Richtung/Magnitude) identisch, nur Confidence runter
        self.assertEqual(covered.score, thin.score)
        self.assertLess(thin.confidence, covered.confidence)

    def test_thin_coverage_marked_in_evidence(self):
        thin = self.sig.evaluate({"market": "Beide Teams treffen — Ja"}, _ctx(0))
        self.assertIn("dünne xG-Abdeckung", thin.evidence)

    def test_full_coverage_no_marker(self):
        covered = self.sig.evaluate({"market": "Beide Teams treffen — Ja"}, _ctx(4, "apif_real"))
        self.assertNotIn("dünne xG-Abdeckung", covered.evidence)

    def test_real_xg_games_counts_real_xg(self):
        # Understat-Team ohne xgGames-Feld, aber echtes xgForAvg → abgedeckt
        e = {"xgForAvg": 1.5, "xgAgainstAvg": 1.0, "games": 12, "source": "understat"}
        self.assertEqual(XGStrengthSignal._real_xg_games(e), 12)
        # FIX 29.06.2026: Rich-Schema (fetch_wm_nt_xg) — echtes xgForAvg, ABER kein source/xgGames
        # (genau die WM/Liga-Realität). Muss als echtes xG zählen, nicht als Proxy.
        rich = {"xgForAvg": 1.986, "xgAgainstAvg": 1.2, "games": 9, "xgSimForAvg": 1.01}
        self.assertEqual(XGStrengthSignal._real_xg_games(rich), 9)
        # Proxy-only-Team: KEIN echtes xG (xgForAvg None, nur xGsim) → 0
        self.assertEqual(XGStrengthSignal._real_xg_games(
            {"xgForAvg": None, "xgSimForAvg": 1.0, "games": 5}), 0)
        # explizit xgGames=0 (lean Aggregator, kein echtes xG) → 0
        self.assertEqual(XGStrengthSignal._real_xg_games(
            {"xgForAvg": None, "games": 5, "xgGames": 0}), 0)
        # shot_proxy: xgForAvg = xGsim-Fallback, source-getaggt → KEIN echtes xG → 0
        self.assertEqual(XGStrengthSignal._real_xg_games(
            {"xgForAvg": 1.1, "xgSimForAvg": 1.1, "games": 6, "source": "shot_proxy"}), 0)


if __name__ == "__main__":
    unittest.main()
