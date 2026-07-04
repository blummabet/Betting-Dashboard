#!/usr/bin/env python3
"""test_ko_settlement_guard.py — Tripwire für den 90-Min-Settlement-Bug (03.07.2026, Lucas: ARG-CPV
Verlängerungstore fälschlich in „Unter 2.5/3.5" gerechnet; BEL-SEN latent). Der Guard muss (a) den Bug
fangen, wenn Verlängerungstore im Settlement landen, und (b) korrektes 90-Min-Settlement durchwinken."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from wm_data_integrity import IntegrityCtx, check_ko_settlement_ninety_min


def _fx(h, a, agg, status="AET", home="ARG", away="CPV"):
    r = {"status": status, "home_score": h, "away_score": a}
    if agg is not None:
        r["aggregateScore"] = {"home": agg[0], "away": agg[1]}
    return {"home": home, "away": away, "result": r}


def _run(fixtures, profile="wm2026"):
    ctx = IntegrityCtx({"_meta": {"profile": profile}, "groups": {}, "koFixtures": fixtures}, {}, {}, {})
    return check_ko_settlement_ninety_min(ctx)


class TestKoSettlementGuard(unittest.TestCase):
    def test_correct_90min_settlement_passes(self):
        # ARG-CPV korrekt: 90 Min 1:1, Verlängerungs-Endstand 3:2
        self.assertTrue(_run([_fx(1, 1, (3, 2))])["ok"])

    def test_extratime_goals_in_settlement_fails(self):
        # Revert-Fall: 90-Min-Stand fälschlich = Verlängerungs-Endstand 3:2 (AET → muss strikt < sein)
        res = _run([_fx(3, 2, (3, 2))])
        self.assertFalse(res["ok"])

    def test_settlement_greater_than_aggregate_fails(self):
        # unmöglich: Settlement mehr Tore als Gesamt
        self.assertFalse(_run([_fx(4, 2, (3, 2))])["ok"])

    def test_pen_no_extratime_goals_passes(self):
        # Elfmeter nach 1:1 ohne Verlängerungstore → 90 Min == Gesamt, kein AET-Strict
        self.assertTrue(_run([_fx(1, 1, (1, 1), status="PEN")])["ok"])

    def test_regular_ft_ignored(self):
        self.assertTrue(_run([_fx(2, 1, None, status="FT")])["ok"])

    def test_liga_skipped(self):
        self.assertIsNone(_run([_fx(3, 2, (3, 2))], profile="mls_default"))


if __name__ == "__main__":
    unittest.main()
