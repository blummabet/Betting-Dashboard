#!/usr/bin/env python3
"""
Tests für backtest_model_health.py
====================================
- Edge-Rekonstruktion (sc - 1/odds)*100
- PnL-Logik (Win/Loss/Push/Void)
- ROI-Aggregation
- Wilson-CI Sanity (50/100 → ~0.40-0.60)
- Sub-Modell-Mapping (Elo vs. Skellam)
- Bucket-Grenzen (<4, 4-6, 6-10, 10-15, 15+)
- Calibration-Bins
- Load-Pipeline mit kleinem Fake-File
"""
from __future__ import annotations
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest_model_health as bm


# ───────────────────────────────────────────────────────────────────
# Edge-Reconstruction
# ───────────────────────────────────────────────────────────────────
class TestEdgeReconstruction(unittest.TestCase):
    def test_positive_edge(self):
        # sc=0.60, odds=2.00 → implied=0.5, edge = 10pp
        self.assertAlmostEqual(bm.reconstruct_edge_pp(0.60, 2.00), 10.0, places=6)

    def test_zero_edge(self):
        # sc = implied probability → edge = 0
        self.assertAlmostEqual(bm.reconstruct_edge_pp(0.50, 2.00), 0.0, places=6)

    def test_negative_edge(self):
        # sc < implied → negativ
        self.assertAlmostEqual(bm.reconstruct_edge_pp(0.40, 2.00), -10.0, places=6)

    def test_high_odds(self):
        # sc=0.20, odds=5.00 → implied=0.20 → edge=0
        self.assertAlmostEqual(bm.reconstruct_edge_pp(0.20, 5.00), 0.0, places=6)


# ───────────────────────────────────────────────────────────────────
# PnL-Logik
# ───────────────────────────────────────────────────────────────────
class TestPnL(unittest.TestCase):
    def test_win_pays_odds_minus_one(self):
        self.assertAlmostEqual(bm.pnl_for("win", 2.00), 1.0)
        self.assertAlmostEqual(bm.pnl_for("win", 1.50), 0.5)
        self.assertAlmostEqual(bm.pnl_for("win", 3.50), 2.5)

    def test_loss_returns_minus_one(self):
        self.assertEqual(bm.pnl_for("loss", 2.00), -1.0)
        self.assertEqual(bm.pnl_for("loss", 5.00), -1.0)

    def test_push_returns_zero(self):
        self.assertEqual(bm.pnl_for("push", 2.00), 0.0)

    def test_void_returns_zero(self):
        self.assertEqual(bm.pnl_for("void", 2.00), 0.0)


# ───────────────────────────────────────────────────────────────────
# ROI-Aggregation
# ───────────────────────────────────────────────────────────────────
class TestAggregate(unittest.TestCase):
    def _make_row(self, result, odds=2.0, sc=0.55):
        return {
            "result": result,
            "odds": odds,
            "sc": sc,
            "pnl": bm.pnl_for(result, odds),
            "stake": 0.0 if result == "void" else 1.0,
        }

    def test_empty_returns_nan_roi(self):
        a = bm.aggregate([])
        self.assertEqual(a["n"], 0)
        self.assertTrue(math.isnan(a["roi"]))

    def test_perfect_winner(self):
        # 10 picks alle win @ 2.00 → ROI = +100%
        rows = [self._make_row("win", 2.00) for _ in range(10)]
        a = bm.aggregate(rows)
        self.assertEqual(a["n"], 10)
        self.assertEqual(a["n_wins"], 10)
        self.assertAlmostEqual(a["roi"], 100.0, places=4)
        self.assertEqual(a["win_rate"], 1.0)

    def test_perfect_loser(self):
        rows = [self._make_row("loss", 2.00) for _ in range(10)]
        a = bm.aggregate(rows)
        self.assertAlmostEqual(a["roi"], -100.0, places=4)
        self.assertEqual(a["win_rate"], 0.0)

    def test_mixed_5050(self):
        # 5 wins @ 2.00, 5 losses @ 2.00 → ROI = 0%
        rows = [self._make_row("win", 2.00) for _ in range(5)] + \
               [self._make_row("loss", 2.00) for _ in range(5)]
        a = bm.aggregate(rows)
        self.assertAlmostEqual(a["roi"], 0.0, places=4)
        self.assertAlmostEqual(a["win_rate"], 0.5, places=4)

    def test_push_in_stake_not_in_wr(self):
        # 1 win, 1 loss, 1 push → wr = 50%, stake_sum = 3, pnl_sum = 0
        rows = [
            self._make_row("win", 2.00),
            self._make_row("loss", 2.00),
            self._make_row("push", 2.00),
        ]
        a = bm.aggregate(rows)
        self.assertEqual(a["n_wl"], 2)
        self.assertEqual(a["n_pushes"], 1)
        self.assertAlmostEqual(a["win_rate"], 0.5, places=4)
        # PnL = +1 -1 +0 = 0, Stake = 1+1+1 = 3 → ROI = 0
        self.assertAlmostEqual(a["roi"], 0.0, places=4)

    def test_void_excluded_from_stake(self):
        # 1 win @ 2.00, 1 void → ROI=100% (void raus aus stake-sum)
        rows = [
            self._make_row("win", 2.00),
            self._make_row("void", 2.00),
        ]
        a = bm.aggregate(rows)
        self.assertEqual(a["n_voids"], 1)
        self.assertAlmostEqual(a["roi"], 100.0, places=4)

    def test_brier_score_perfect_known_vals(self):
        # sc=1.0 + win → term = 0;   sc=0.0 + loss → term = 0 → Brier=0
        rows = [
            {"result": "win", "sc": 1.0, "odds": 2.0, "pnl": 1.0, "stake": 1.0},
            {"result": "loss", "sc": 0.0, "odds": 2.0, "pnl": -1.0, "stake": 1.0},
        ]
        a = bm.aggregate(rows)
        self.assertAlmostEqual(a["brier"], 0.0, places=6)

    def test_brier_random_5050(self):
        # sc=0.5 immer, mixed result → Brier = 0.25
        rows = [self._make_row("win", 2.0, 0.5) for _ in range(50)] + \
               [self._make_row("loss", 2.0, 0.5) for _ in range(50)]
        a = bm.aggregate(rows)
        self.assertAlmostEqual(a["brier"], 0.25, places=4)


# ───────────────────────────────────────────────────────────────────
# Wilson-CI Sanity
# ───────────────────────────────────────────────────────────────────
class TestWilsonCI(unittest.TestCase):
    def test_50_of_100_centred_on_half(self):
        lo, hi = bm.wilson_ci(50, 100)
        # Bekanntes Resultat: ~[0.404, 0.596]
        self.assertGreater(lo, 0.39)
        self.assertLess(lo, 0.42)
        self.assertGreater(hi, 0.58)
        self.assertLess(hi, 0.61)

    def test_zero_trials(self):
        lo, hi = bm.wilson_ci(0, 0)
        self.assertEqual(lo, 0.0)
        self.assertEqual(hi, 0.0)

    def test_all_wins(self):
        # 10/10 → CI hat lower > 0, upper = 1.0
        lo, hi = bm.wilson_ci(10, 10)
        self.assertGreater(lo, 0.5)
        self.assertAlmostEqual(hi, 1.0, places=3)

    def test_all_losses(self):
        lo, hi = bm.wilson_ci(0, 10)
        self.assertAlmostEqual(lo, 0.0, places=3)
        self.assertLess(hi, 0.5)

    def test_ci_widens_with_smaller_n(self):
        _, hi_big = bm.wilson_ci(50, 100)
        _, hi_small = bm.wilson_ci(5, 10)
        # Small-n CI breiter
        self.assertGreater(hi_small - 0.5, hi_big - 0.5)


# ───────────────────────────────────────────────────────────────────
# Sub-Modell-Mapping
# ───────────────────────────────────────────────────────────────────
class TestSubModelMapping(unittest.TestCase):
    def test_elo_markets(self):
        for k in ["homeWin", "awayWin", "draw",
                  "dc1X", "dcX2", "dc12", "dnb_heimteam"]:
            self.assertEqual(bm.classify_market(k), "elo",
                             f"{k} sollte 'elo' sein")

    def test_skellam_markets(self):
        for k in ["ah_home:-0.5", "ah_away:-0.75",
                  "over25", "under25", "over35", "over_2_25_tore",
                  "btts", "noBtts",
                  "corners_over:9.5", "corners_under:7.5",
                  "cards35", "cards45",
                  "ht_btts", "ht_over05",
                  "1_hz_heimsieg", "1_hz_under_0_5_tore",
                  "team_goals_over:1.5", "team_goals_home_over:1.5"]:
            self.assertEqual(bm.classify_market(k), "skellam",
                             f"{k} sollte 'skellam' sein")

    def test_unknown_market(self):
        self.assertEqual(bm.classify_market(""), "unknown")
        self.assertEqual(bm.classify_market("foobar"), "unknown")

    def test_no_skellam_keys_in_elo_set(self):
        """Sanity: kein Konflikt zwischen den beiden Sets."""
        for k in bm.ELO_MARKET_KEYS:
            # Diese Keys sollten in classify als 'elo' rauskommen
            self.assertEqual(bm.classify_market(k), "elo")


# ───────────────────────────────────────────────────────────────────
# Edge-Bucket
# ───────────────────────────────────────────────────────────────────
class TestEdgeBucket(unittest.TestCase):
    def test_lowest_bucket(self):
        self.assertEqual(bm.edge_bucket_of(0.0), "<4pp")
        self.assertEqual(bm.edge_bucket_of(3.99), "<4pp")
        self.assertEqual(bm.edge_bucket_of(-10), "<4pp")

    def test_mid_buckets(self):
        self.assertEqual(bm.edge_bucket_of(4.0), "4-6pp")
        self.assertEqual(bm.edge_bucket_of(5.99), "4-6pp")
        self.assertEqual(bm.edge_bucket_of(6.0), "6-10pp")
        self.assertEqual(bm.edge_bucket_of(9.99), "6-10pp")
        self.assertEqual(bm.edge_bucket_of(10.0), "10-15pp")
        self.assertEqual(bm.edge_bucket_of(14.99), "10-15pp")

    def test_top_bucket(self):
        self.assertEqual(bm.edge_bucket_of(15.0), "15+pp")
        self.assertEqual(bm.edge_bucket_of(39.99), "15+pp")


# ───────────────────────────────────────────────────────────────────
# Calibration-Bins
# ───────────────────────────────────────────────────────────────────
class TestCalibration(unittest.TestCase):
    def test_empty_returns_empty_list(self):
        self.assertEqual(bm.calibration_bins([]), [])

    def test_basic_bin_aggregation(self):
        rows = [
            {"sc": 0.10, "result": "win"},
            {"sc": 0.12, "result": "loss"},
            {"sc": 0.60, "result": "win"},
            {"sc": 0.62, "result": "win"},
        ]
        bins = bm.calibration_bins(rows, step=0.05)
        # Bin 0.10-0.15 sollte n=2, observed=0.5 enthalten
        target = next((b for b in bins if abs(b["bin_low"] - 0.10) < 1e-6), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["n"], 2)
        self.assertAlmostEqual(target["observed_win_rate"], 0.5, places=4)

    def test_pushes_excluded_from_calibration(self):
        rows = [
            {"sc": 0.50, "result": "push"},
            {"sc": 0.50, "result": "void"},
        ]
        bins = bm.calibration_bins(rows)
        self.assertEqual(bins, [])


# ───────────────────────────────────────────────────────────────────
# Bootstrap-CI Sanity
# ───────────────────────────────────────────────────────────────────
class TestBootstrap(unittest.TestCase):
    def test_deterministic_with_seed(self):
        pnls = [1.0, -1.0, 0.5, -1.0, 1.5, -1.0, 0.8, -1.0, 1.2, -1.0]
        stakes = [1.0] * 10
        ci1 = bm.bootstrap_roi_ci(pnls, stakes, resamples=500, seed=42)
        ci2 = bm.bootstrap_roi_ci(pnls, stakes, resamples=500, seed=42)
        self.assertEqual(ci1, ci2)

    def test_returns_nan_for_tiny_sample(self):
        ci = bm.bootstrap_roi_ci([1.0], [1.0])
        self.assertTrue(math.isnan(ci[0]))


# ───────────────────────────────────────────────────────────────────
# Load-Pipeline (End-to-End mit Mini-Fake-File)
# ───────────────────────────────────────────────────────────────────
class TestLoadPicks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpfile = Path(self.tmpdir.name) / "fake_history.json"
        data = [{
            "id": "test-1",
            "dateIso": "2026-05-01",
            "league": "DE1",
            "picks": [
                {"market": "Heimsieg", "marketKey": "homeWin", "conf": "high",
                 "sc": 0.60, "odds": 2.00, "result": "win"},
                {"market": "Over 2.5", "marketKey": "over25", "conf": "medium",
                 "sc": 0.55, "odds": 1.80, "result": "loss"},
                {"market": "BTTS", "marketKey": "btts", "conf": "medium",
                 "sc": 0.50, "odds": 1.85, "result": "void"},
                {"market": "Über 9.5 Ecken", "marketKey": "corners_over:9.5",
                 "conf": "low", "sc": 0.58, "odds": 1.83, "result": "push"},
                # Should be skipped: missing sc
                {"market": "Foo", "marketKey": "homeWin", "conf": "low",
                 "sc": None, "odds": 2.0, "result": "win"},
                # Should be skipped: not resolved
                {"market": "Bar", "marketKey": "homeWin", "conf": "low",
                 "sc": 0.5, "odds": 2.0, "result": None},
            ]
        }]
        with open(self.tmpfile, "w") as f:
            json.dump(data, f)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_picks_basic(self):
        rows = bm.load_picks(self.tmpfile)
        # 4 valid rows (win, loss, void, push); 2 skipped
        self.assertEqual(len(rows), 4)

    def test_load_picks_classifies_submodel(self):
        rows = bm.load_picks(self.tmpfile)
        # homeWin → elo, over25 → skellam, btts → skellam, corners_over → skellam
        elos = [r for r in rows if r["sub_model"] == "elo"]
        skels = [r for r in rows if r["sub_model"] == "skellam"]
        self.assertEqual(len(elos), 1)
        self.assertEqual(len(skels), 3)

    def test_load_picks_edges_reconstructed(self):
        rows = bm.load_picks(self.tmpfile)
        # homeWin: sc=0.60, odds=2.00 → edge = 10pp
        hw = next(r for r in rows if r["marketKey"] == "homeWin")
        self.assertAlmostEqual(hw["edge_pp"], 10.0, places=4)

    def test_build_report_runs_without_error(self):
        rows = bm.load_picks(self.tmpfile)
        md, results = bm.build_report(rows)
        self.assertIn("Headline", md)
        self.assertIn("Sub-Modell", md)
        self.assertIn("Calibration", md)
        self.assertIn("headline", results)
        self.assertIn("by_sub_model", results)


# ───────────────────────────────────────────────────────────────────
# Format-Helpers
# ───────────────────────────────────────────────────────────────────
class TestFormatHelpers(unittest.TestCase):
    def test_fmt_pct_nan(self):
        self.assertEqual(bm.fmt_pct(float("nan")), "n/a")

    def test_fmt_pct_signed(self):
        self.assertEqual(bm.fmt_pct(5.234, signed=True), "+5.23%")
        self.assertEqual(bm.fmt_pct(-5.234, signed=True), "-5.23%")

    def test_warn_marker(self):
        self.assertEqual(bm.warn_marker(29), " ⚠️")
        self.assertEqual(bm.warn_marker(30), "")
        self.assertEqual(bm.warn_marker(100), "")


if __name__ == "__main__":
    unittest.main()
