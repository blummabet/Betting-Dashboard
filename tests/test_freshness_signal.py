#!/usr/bin/env python3
"""
test_freshness_signal.py — Frische als lernbares Signal (18.06.2026, Lucas)

freshness_leg liest den vom Frische-Modell berechneten Zustand (confirm/drift/reverse) vom
Pick und gibt einen signierten Score: confirm + (Win-bestätigend), reverse − (Loss-bestätigend),
drift 0 (neutral). Fließt durch Registry → Ledger → Bayesian-Weight (richtungs-bewusst).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.freshness_signal import FreshnessLegSignal  # noqa: E402
from sharp_signals.registry import ACTIVE_SIGNALS, evaluate_signals  # noqa: E402


def _pick(state, rmv, snaps=6):
    return {"market": "Heimsieg", "odds": 2.3, "modelOdds": 2.0,
            "source": "steam", "freshnessState": state, "recentMovePP": rmv,
            "legSnaps": snaps, "legHours": 70}


class TestFreshnessSignal(unittest.TestCase):
    def setUp(self):
        self.s = FreshnessLegSignal()

    def test_confirm_positive(self):
        r = self.s.evaluate(_pick("confirm", 9.6), {})
        self.assertGreater(r.score, 0)
        self.assertEqual(r.metadata["state"], "confirm")

    def test_reverse_negative(self):
        r = self.s.evaluate(_pick("reverse", -9.1), {})
        self.assertLess(r.score, 0)

    def test_drift_neutral(self):
        r = self.s.evaluate(_pick("drift", 0.3, snaps=2), {})
        self.assertEqual(r.score, 0.0)
        self.assertLessEqual(r.confidence, 0.5)

    def test_capped(self):
        # Extremer Move wird gedeckelt (max_signal_pp)
        r = self.s.evaluate(_pick("confirm", 40.0), {})
        self.assertLessEqual(r.score, 4.0)
        r2 = self.s.evaluate(_pick("reverse", -40.0), {})
        self.assertGreaterEqual(r2.score, -4.0)

    def test_none_without_state(self):
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg"}, {}))
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg", "freshnessState": "confirm"}, {}))  # kein rmv

    def test_more_snaps_more_confidence(self):
        lo = self.s.evaluate(_pick("confirm", 6.0, snaps=3), {}).confidence
        hi = self.s.evaluate(_pick("confirm", 6.0, snaps=10), {}).confidence
        self.assertGreater(hi, lo)

    def test_registered_and_flows_to_output(self):
        self.assertTrue(any(x.name() == "freshness_leg" for x in ACTIVE_SIGNALS))
        out = evaluate_signals(_pick("reverse", -9.1), {"matchKey": "X", "odds_history": []})
        names = [s["name"] for s in out["signals"]]
        self.assertIn("freshness_leg", names)
        # negatives Signal zieht das combined adjustment runter (Verdict-Override)
        self.assertLess(out["combined_score_pp"], 0)


if __name__ == "__main__":
    unittest.main()
