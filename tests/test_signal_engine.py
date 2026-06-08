#!/usr/bin/env python3
"""
test_signal_engine.py — Signal-Engine Foundation Tests

Deckt ab:
  · base.SignalResult struct
  · LeadLagBiasSignal: EARLY-Pfad, CONFIRMED-Pfad, kein-Move-Pfad
  · registry.evaluate_signals: gewichtete Kombination
  · update_signal_weights: Bayesian-Update Math + Smoothing
"""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


def _make_history(snaps_per_bk: dict) -> list[dict]:
    """Helper: Liste von Snapshots aus dict {bk: [(ts_offset_h, hw, dr, aw)]} bauen."""
    now = datetime.now(timezone.utc)
    out = []
    for bk, snaps in snaps_per_bk.items():
        for offset_h, hw, dr, aw in snaps:
            ts = (now - timedelta(hours=offset_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append({"ts": ts, "hw": hw, "dr": dr, "aw": aw, "bk": bk})
    return out


class TestSignalResult(unittest.TestCase):
    def test_dataclass_roundtrip(self):
        from sharp_signals.base import SignalResult
        r = SignalResult(score=2.5, confidence=0.7, evidence="test")
        d = r.to_dict()
        self.assertEqual(d["score"], 2.5)
        self.assertEqual(d["confidence"], 0.7)
        self.assertEqual(d["evidence"], "test")


class TestLeadLagBias(unittest.TestCase):
    """Lucas's Lead-Lag-Signal: EARLY + CONFIRMED."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.lead_lag_bias import LeadLagBiasSignal
        cls.sig = LeadLagBiasSignal()

    def _evaluate(self, market: str, history: list[dict]):
        pick = {"market": market}
        ctx = {"odds_history": history, "snapshot_ts": None}
        return self.sig.evaluate(pick, ctx)

    def test_no_signal_for_non_1x2_market(self):
        """O/U-/AH-Märkte nicht im 1X2-Lead-Lag-Scope."""
        history = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.50, 3.60)],
            "williamhill": [(20, 2.15, 3.40, 3.15), (1, 2.10, 3.45, 3.20)],
        })
        result = self._evaluate("Über 2.5 Tore", history)
        self.assertIsNone(result)

    def test_no_signal_when_no_pinn_move(self):
        history = _make_history({
            "pinnacle":    [(24, 1.91, 3.47, 4.46), (1, 1.91, 3.47, 4.46)],
            "williamhill": [(24, 1.95, 3.40, 4.40), (1, 1.95, 3.40, 4.40)],
        })
        result = self._evaluate("Heimsieg", history)
        self.assertIsNone(result, "Ohne Pinn-Bewegung darf das Signal nicht feuern")

    def test_early_signal_when_softbooks_lagging(self):
        """
        Pinnacle dropt Heim-Quote von 2.10 → 1.85 (Heim wahrscheinlicher).
        William Hill steht noch bei 2.10. → EARLY-Signal.
        """
        history = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.60, 3.60)],
            "williamhill": [(20, 2.10, 3.40, 3.20), (1, 2.10, 3.40, 3.20)],
        })
        result = self._evaluate("Heimsieg", history)
        self.assertIsNotNone(result, "Pinn-Move + Soft-Lag = EARLY")
        self.assertEqual(result.metadata["stage"], "early")
        self.assertGreater(result.score, 0, "Heim wahrscheinlicher → positiver Score")
        self.assertIn("Pinnacle", result.evidence)

    def test_confirmed_signal_when_softbooks_followed(self):
        """
        Pinnacle dropt Heim, William Hill UND Unibet sind nachgezogen.
        → CONFIRMED-Signal, stärker als EARLY.
        """
        history = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.60, 3.60)],
            "williamhill": [(20, 2.15, 3.40, 3.15), (1, 1.90, 3.55, 3.55)],
            "unibet":      [(24, 2.12, 3.42, 3.18), (1, 1.88, 3.58, 3.58)],
        })
        result = self._evaluate("Heimsieg", history)
        self.assertIsNotNone(result)
        self.assertEqual(result.metadata["stage"], "confirmed")
        self.assertGreater(result.score, 0)
        # CONFIRMED ist stärker als EARLY (gleiche Pinn-Move-Magnitude)
        # Vergleich: EARLY mit gleichem Pinn-Move
        history_early = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.60, 3.60)],
            "williamhill": [(20, 2.10, 3.40, 3.20), (1, 2.10, 3.40, 3.20)],
        })
        early = self._evaluate("Heimsieg", history_early)
        self.assertGreater(result.score, early.score,
            "CONFIRMED muss höheren Score haben als EARLY bei gleicher Pinn-Bewegung")


class TestPublicStaticBias(unittest.TestCase):
    """Public-Konsens vs Pinnacle → contrarian Pick wenn Public stark biased."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.public_static_bias import PublicStaticBiasSignal
        cls.sig = PublicStaticBiasSignal()

    def _evaluate(self, market: str, snap: dict):
        return self.sig.evaluate({"market": market}, {"odds_snapshot": snap})

    def test_no_signal_for_non_1x2(self):
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 1.80, "public_dr": 3.50, "public_aw": 4.50,
                "public_bookmaker": "bet365"}
        self.assertIsNone(self._evaluate("Über 2.5 Tore", snap))

    def test_no_signal_without_public_data(self):
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46}
        self.assertIsNone(self._evaluate("Heimsieg", snap))

    def test_no_signal_below_threshold(self):
        # Pinnacle und Public quasi identisch → keine Bias
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 1.90, "public_dr": 3.48, "public_aw": 4.45,
                "public_bookmaker": "bet365"}
        self.assertIsNone(self._evaluate("Heimsieg", snap))

    def test_positive_score_when_public_overbets_picked_outcome(self):
        """
        Public hat Heim auf 1.65 (60.6%), Pinnacle auf 1.91 (52.4%).
        Public überbettet Heim um ~8pp → Pick auf Heim ist contrarian → positiv.
        """
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 1.65, "public_dr": 3.80, "public_aw": 5.50,
                "public_bookmaker": "bet365"}
        result = self._evaluate("Heimsieg", snap)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)
        self.assertIn("über-bettet", result.evidence)
        self.assertIn("bet365", result.evidence)

    def test_negative_score_when_public_underbets_picked_outcome(self):
        """
        Public hat Heim auf 2.20 (45%), Pinnacle auf 1.91 (52%).
        Public unter-bettet Heim → Pick auf Heim folgt Public → kein Edge → negativ.
        """
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 2.20, "public_dr": 3.30, "public_aw": 3.80,
                "public_bookmaker": "bet365"}
        result = self._evaluate("Heimsieg", snap)
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)


class TestTravelBurden(unittest.TestCase):
    """Anreise + Höhe als Modifikator. Killer-Signal."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.travel_burden import TravelBurdenSignal
        cls.sig = TravelBurdenSignal()

    def _evaluate(self, market, travel, home="MEX", away="ZAF", matchday=1):
        return self.sig.evaluate(
            {"market": market},
            {"home_id": home, "away_id": away, "matchday": matchday, "travel": travel}
        )

    def test_no_signal_for_non_1x2(self):
        travel = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                    "rest_days": 2, "burden": "critical"}]}}
        self.assertIsNone(self._evaluate("Über 2.5 Tore", travel))

    def test_no_signal_when_both_teams_local(self):
        travel = {"MEX": {"legs": [{"matchday_to": 1, "km": 200, "rest_days": 5}]},
                  "ZAF": {"legs": [{"matchday_to": 1, "km": 300, "rest_days": 5}]}}
        self.assertIsNone(self._evaluate("Heimsieg", travel))

    def test_positive_score_for_home_pick_when_away_critical(self):
        """Auswärts reist 4000km mit 2 Tagen Pause → Pick auf Heim = positiv."""
        travel = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                    "rest_days": 2, "burden": "critical"}]}}
        result = self._evaluate("Heimsieg", travel)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)
        self.assertIn("✈️", result.evidence)

    def test_negative_score_for_away_pick_when_away_critical(self):
        """Pick stützt Auswärts, aber Auswärts reist critical → negativ."""
        travel = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                    "rest_days": 2, "burden": "critical"}]}}
        result = self._evaluate("Auswärtssieg", travel)
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)

    def test_altitude_adds_score(self):
        """Höhenwechsel ≥ 1500m gibt extra Score."""
        travel_low_alt = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                            "rest_days": 2, "burden": "critical",
                                            "alt_shift": 0}]}}
        travel_high_alt = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                             "rest_days": 2, "burden": "critical",
                                             "alt_shift": 2200}]}}
        low  = self._evaluate("Heimsieg", travel_low_alt)
        high = self._evaluate("Heimsieg", travel_high_alt)
        self.assertGreater(high.score, low.score,
            "Höhenwechsel sollte den Score weiter erhöhen")


class TestRegistryEvaluateSignals(unittest.TestCase):
    """evaluate_signals kombiniert mehrere Signale gewichtet."""

    def test_returns_combined_score(self):
        from sharp_signals.registry import evaluate_signals
        # Pick + Context wo Lead-Lag triggern WIRD (EARLY)
        history = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.60, 3.60)],
            "williamhill": [(20, 2.10, 3.40, 3.20), (1, 2.10, 3.40, 3.20)],
        })
        pick = {"market": "Heimsieg"}
        ctx  = {"odds_history": history}
        # Default-Weights (alles 1.0)
        out = evaluate_signals(pick, ctx, weights={})
        self.assertIn("signals", out)
        self.assertGreater(len(out["signals"]), 0,
            "Bei Heimsieg + Lead-Lag-Pattern sollte mindestens ein Signal triggern")
        # combined_score sollte positiv sein (Lead-Lag sagt: Heim wahrscheinlicher)
        self.assertGreater(out["combined_score_pp"], 0)

    def test_weights_dampen_signals_correctly(self):
        from sharp_signals.registry import evaluate_signals
        history = _make_history({
            "pinnacle":    [(20, 2.10, 3.40, 3.20), (1, 1.85, 3.60, 3.60)],
            "williamhill": [(20, 2.10, 3.40, 3.20), (1, 2.10, 3.40, 3.20)],
        })
        pick = {"market": "Heimsieg"}
        ctx  = {"odds_history": history}
        # Mit Weight 1.0 vs 0.5 → bei 0.5 sollte der Score halbiert sein
        out_full = evaluate_signals(pick, ctx, weights={
            "lead_lag_bias": {"weight": 1.0}
        })
        out_half = evaluate_signals(pick, ctx, weights={
            "lead_lag_bias": {"weight": 0.5}
        })
        # Beide combined_score sind der gleiche Mean (weighted), aber das
        # individuelle weighted_score sollte halbiert sein
        self.assertEqual(len(out_full["signals"]), len(out_half["signals"]))
        if out_full["signals"]:
            self.assertAlmostEqual(
                out_half["signals"][0]["weighted_score"],
                out_full["signals"][0]["weighted_score"] * 0.5,
                places=2,
            )


class TestUpdateSignalWeights(unittest.TestCase):
    """Bayesian-Update: Win-Rate steigert Weight, Loss-Rate senkt sie."""

    def test_winning_signal_increases_weight(self):
        """Signal das immer richtig liegt → weight > 1.0."""
        import update_signal_weights as upd
        # Mock-Picks: 20 mal lead_lag_bias mit score=+2 getriggered, alle gewonnen
        picks = []
        for _ in range(20):
            picks.append({
                "result": "win",
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            results_file = Path(td) / "wm_results.json"
            weights_file = Path(td) / "signal_weights.json"
            results_file.write_text(json.dumps({"picks": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "RESULTS_FILE", results_file), \
                 patch.object(upd, "WEIGHTS_FILE", weights_file):
                w = upd.update_weights()
        self.assertGreater(w["lead_lag_bias"]["weight"], 1.0,
            "Signal das 20/20 richtig liegt → weight > 1.0")
        self.assertEqual(w["lead_lag_bias"]["n_observations"], 20)

    def test_losing_signal_decreases_weight(self):
        """Signal das nie richtig liegt → weight < 1.0."""
        import update_signal_weights as upd
        picks = []
        for _ in range(20):
            picks.append({
                "result": "loss",
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            results_file = Path(td) / "wm_results.json"
            weights_file = Path(td) / "signal_weights.json"
            results_file.write_text(json.dumps({"picks": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "RESULTS_FILE", results_file), \
                 patch.object(upd, "WEIGHTS_FILE", weights_file):
                w = upd.update_weights()
        self.assertLess(w["lead_lag_bias"]["weight"], 1.0,
            "Signal das 20/20 falsch liegt → weight < 1.0")

    def test_smoothing_keeps_few_observations_near_prior(self):
        """Bei n=3 darf das Weight noch nicht extrem ausschlagen."""
        import update_signal_weights as upd
        picks = []
        for _ in range(3):
            picks.append({
                "result": "win",
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            results_file = Path(td) / "wm_results.json"
            weights_file = Path(td) / "signal_weights.json"
            results_file.write_text(json.dumps({"picks": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "RESULTS_FILE", results_file), \
                 patch.object(upd, "WEIGHTS_FILE", weights_file):
                w = upd.update_weights()
        # Mit Smoothing sollte weight nahe 1.0 sein, nicht im Sanity-Bound
        self.assertGreater(w["lead_lag_bias"]["weight"], 0.95)
        self.assertLess(w["lead_lag_bias"]["weight"], 1.25,
            "Bei nur 3 Beobachtungen darf das Weight noch nicht extrem ausschlagen")


if __name__ == "__main__":
    unittest.main()
