#!/usr/bin/env python3
"""test_compute_clv_summary.py — CLV-Bilanz-Aggregation (28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import compute_clv_summary as C  # noqa: E402


def _pick(source="steam", result="WIN", clv=None, market="Heimsieg", excluded=False, verdict="BET"):
    p = {"source": source, "result": result, "market": market, "verdict": verdict}
    if excluded:
        p["trackingExcluded"] = True
    if clv is not None:
        p["clvPP"] = clv
        p["clvResolved"] = True
    return p


class TestSummary(unittest.TestCase):
    def test_overall_avg_beat_coverage(self):
        wm = {"picks": {
            "ENG-1-che-ars": [_pick(clv=3.0, market="Heimsieg")],          # beat
            "ENG-1-liv-mci": [_pick(clv=-1.0, market="Über 2.5 Tore")],    # not beat
            "ESP-2-rma-fcb": [_pick(clv=5.0, market="Beide Teams treffen — Ja")],  # beat
            "ESP-2-atm-sev": [_pick(clv=None)],   # aufgelöst, aber kein Closing → nur Abdeckung
        }}
        s = C.build_summary(wm)
        ov = s["overall"]
        self.assertEqual(ov["n"], 3)
        self.assertAlmostEqual(ov["avgClvPP"], round((3.0 - 1.0 + 5.0) / 3, 2))
        self.assertAlmostEqual(ov["pctBeatClose"], round(2 / 3 * 100, 1))
        self.assertEqual(ov["coverage"], {"withClosing": 3, "resolved": 4, "pct": 75.0})

    def test_ignores_nonsteam_excluded_unresolved(self):
        wm = {"picks": {
            "ENG-1-a-b": [_pick(source="model", clv=9.0)],     # nicht steam
            "ENG-1-c-d": [_pick(excluded=True, clv=9.0)],       # ausgeschlossen
            "ENG-1-e-f": [_pick(result="", clv=9.0)],          # nicht aufgelöst
        }}
        s = C.build_summary(wm)
        self.assertEqual(s["overall"]["n"], 0)
        self.assertIsNone(s["overall"]["avgClvPP"])
        self.assertEqual(s["overall"]["coverage"]["resolved"], 0)

    def test_by_market_league_time(self):
        wm = {"picks": {
            "ENG-1-a-b": [_pick(clv=2.0, market="Heimsieg")],
            "ENG-1-c-d": [_pick(clv=4.0, market="Über 2.5 Tore")],
            "ESP-3-e-f": [_pick(clv=-2.0, market="Doppelte Chance — 1X")],
        }}
        s = C.build_summary(wm)
        self.assertIn("1X2/DNB", s["byMarket"])
        self.assertIn("Über/Unter", s["byMarket"])
        self.assertIn("Doppelte Chance", s["byMarket"])
        self.assertEqual(s["byLeague"]["ENG"]["n"], 2)
        self.assertEqual(s["byLeague"]["ESP"]["n"], 1)
        buckets = [b["bucket"] for b in s["byTime"]]
        self.assertEqual(buckets, ["1", "3"])   # nach Spieltag sortiert

    def test_by_verdict_and_bet_rate(self):
        wm = {"picks": {
            "ENG-1-a-b": [_pick(clv=2.0, verdict="BET")],
            "ENG-1-c-d": [_pick(clv=-1.0, verdict="ABWÄGEN")],
            "ENG-1-e-f": [_pick(clv=4.0, verdict="ABWÄGEN")],
            "ESP-1-g-h": [_pick(clv=None, result="", verdict="BET")],   # ungespielt, zählt in BET-Quote
        }}
        s = C.build_summary(wm)
        # CLV-Split nur über aufgelöste-mit-Closing
        self.assertEqual(s["byVerdict"]["BET"]["n"], 1)
        self.assertEqual(s["byVerdict"]["ABWÄGEN"]["n"], 2)
        # BET-Quote über ALLE Picks (auch ungespielt): ENG 1 BET / 3 = 33.3%, ESP 1/1 = 100%
        self.assertEqual(s["betRate"]["byLeague"]["ENG"], 33.3)
        self.assertEqual(s["betRate"]["byLeague"]["ESP"], 100.0)
        self.assertEqual(s["betRate"]["overall"], 50.0)   # 2 BET / 4 gesamt

    def test_market_category(self):
        self.assertEqual(C.market_category("Über 2.5 Tore"), "Über/Unter")
        self.assertEqual(C.market_category("Beide Teams treffen — Nein"), "BTTS")
        self.assertEqual(C.market_category("Doppelte Chance — X2"), "Doppelte Chance")
        self.assertEqual(C.market_category("AH Heim -1.5"), "Handicap")
        self.assertEqual(C.market_category("Heimsieg"), "1X2/DNB")


if __name__ == "__main__":
    unittest.main()
