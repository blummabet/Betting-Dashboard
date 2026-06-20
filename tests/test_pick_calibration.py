#!/usr/bin/env python3
"""
test_pick_calibration.py — Lern-Ebene 2: Segment-Kalibrierung (20.06.2026, Lucas)

compute_pick_calibration aggregiert prozess-justierte Performance je Segment; generate_wm_picks
wendet daraus einen SEHR KLEINEN, gedeckelten Conviction-Nudge an — erst ab min_picks.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import compute_pick_calibration as C  # noqa: E402


def _rec(source, pv=None, result=None, conv=None):
    r = {"key": f"{source}-{id(object())}", "market": "x", "signals": [{"name": "s", "score": 1}]}
    r["source"] = source
    if pv:     r["processVerdict"] = pv
    if result: r["result"] = result
    if conv is not None: r["convictionScore"] = conv
    return r


class TestCompute(unittest.TestCase):
    def test_segment_delta_process_adjusted(self):
        # steam: 2× JUSTIFIED(1.0) + 2× UNLUCKY(0.35) → 0.675; model: 2× DESERVED_LOSS(0) + 2× LUCKY(0.65) → 0.325
        recs = ([_rec("steam", pv="JUSTIFIED") for _ in range(2)]
                + [_rec("steam", pv="UNLUCKY") for _ in range(2)]
                + [_rec("model", pv="DESERVED_LOSS") for _ in range(2)]
                + [_rec("model", pv="LUCKY") for _ in range(2)])
        cal = C.compute({"records": recs})
        self.assertEqual(cal["_meta"]["totalN"], 8)
        self.assertAlmostEqual(cal["segments"]["steam"]["procWin"], 0.675, places=2)
        self.assertAlmostEqual(cal["segments"]["model"]["procWin"], 0.325, places=2)
        # delta = seg − baseline(0.5)
        self.assertGreater(cal["segments"]["steam"]["delta"], 0)
        self.assertLess(cal["segments"]["model"]["delta"], 0)

    def test_unlucky_loss_softer_than_deserved(self):
        # Ein verlorener-aber-verdienter (UNLUCKY) Pick zieht das Segment NICHT auf 0.
        cal = C.compute({"records": [_rec("steam", pv="UNLUCKY")]})
        self.assertGreater(cal["segments"]["steam"]["procWin"], 0.0)

    def test_raw_result_fallback(self):
        # Ohne processVerdict → binäres WIN/LOSS.
        cal = C.compute({"records": [_rec("model", result="WIN"), _rec("model", result="LOSS")]})
        self.assertAlmostEqual(cal["segments"]["model"]["procWin"], 0.5, places=2)

    def test_conviction_buckets(self):
        recs = [_rec("model", result="WIN", conv=8), _rec("model", result="LOSS", conv=2)]
        cal = C.compute({"records": recs})
        self.assertEqual(cal["convictionBuckets"]["high"]["n"], 1)
        self.assertEqual(cal["convictionBuckets"]["low"]["n"], 1)

    def test_empty_ledger_safe(self):
        cal = C.compute({"records": []})
        self.assertEqual(cal["_meta"]["totalN"], 0)
        self.assertIsNone(cal["_meta"]["baseline"])


class TestNudgeGate(unittest.TestCase):
    """generate_wm_picks._calibration_nudge: gedeckelt + erst ab min_picks + min_segment_n."""

    def setUp(self):
        import generate_wm_picks as G
        self.G = G

    def _set(self, totalN, seg_n, delta):
        self.G._PICK_CALIBRATION = {
            "_meta": {"totalN": totalN},
            "segments": {"steam": {"n": seg_n, "delta": delta}},
        }

    def test_below_min_picks_zero(self):
        self._set(self.G.CAL_MIN_PICKS - 1, 99, 0.3)
        self.assertEqual(self.G._calibration_nudge({"source": "steam"}), 0.0)

    def test_thin_segment_zero(self):
        self._set(self.G.CAL_MIN_PICKS + 50, self.G.CAL_MIN_SEG_N - 1, 0.3)
        self.assertEqual(self.G._calibration_nudge({"source": "steam"}), 0.0)

    def test_capped_at_max(self):
        self._set(self.G.CAL_MIN_PICKS + 50, 99, 0.5)   # 0.5*scale weit über cap
        n = self.G._calibration_nudge({"source": "steam"})
        self.assertLessEqual(abs(n), self.G.CAL_MAX_NUDGE + 1e-9)
        self.assertGreater(n, 0)

    def test_model_segment_default(self):
        # Pick ohne source → 'model'-Segment; fehlt im Cal → 0.
        self._set(self.G.CAL_MIN_PICKS + 50, 99, 0.5)
        self.assertEqual(self.G._calibration_nudge({"market": "x"}), 0.0)


if __name__ == "__main__":
    unittest.main()
