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

    def test_negative_score_when_public_overbets_picked_outcome(self):
        """
        13.08.2026 (Lucas-Fix, fade-the-public richtig herum): Public Heim 60.6%, Pinnacle 52.4%.
        Public ueberbettet Heim ~8pp -> ein Pick AUF Heim sitzt auf der oeffentlich aufgeblasenen
        Seite -> NEGATIV. (Vorher faelschlich als positiv/contrarian gewertet.)
        """
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 1.65, "public_dr": 3.80, "public_aw": 5.50,
                "public_bookmaker": "bet365"}
        result = self._evaluate("Heimsieg", snap)
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)
        self.assertIn("überbewertet", result.evidence)
        self.assertIn("bet365", result.evidence)

    def test_positive_score_when_public_underbets_picked_outcome(self):
        """
        13.08.2026 (Lucas-Fix): Public Heim 45%, Pinnacle 52%. Public unterschaetzt Heim -> dort liegt
        der Value, den Pinnacle hoeher sieht -> Pick auf Heim nimmt ihn gegen die Masse -> POSITIV.
        (Vorher faelschlich als negativ gewertet.)
        """
        snap = {"hw": 1.91, "dr": 3.47, "aw": 4.46,
                "public_hw": 2.20, "public_dr": 3.30, "public_aw": 3.80,
                "public_bookmaker": "bet365"}
        result = self._evaluate("Heimsieg", snap)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)


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

    def test_ou_signal_for_travel_burden(self):
        # NEU 09.06.2026: Travel dämpft Tore → Unter-Bias, halber Effekt vs 1X2
        travel = {"ZAF": {"legs": [{"matchday_to": 1, "km": 4000,
                                    "rest_days": 2, "burden": "critical"}]}}
        r_over = self._evaluate("Über 2.5 Tore", travel)
        self.assertIsNotNone(r_over)
        self.assertLess(r_over.score, 0)
        r_under = self._evaluate("Unter 2.5 Tore", travel)
        self.assertIsNotNone(r_under)
        self.assertGreater(r_under.score, 0)

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


class TestInjurySignal(unittest.TestCase):
    """Positionsbewusst — GK, DEF, MID, FWD verschieden gewichtet."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.injury_signal import InjurySignal
        cls.sig = InjurySignal()

    def _evaluate(self, market, injuries, home="MEX", away="ZAF"):
        return self.sig.evaluate(
            {"market": market},
            {"home_id": home, "away_id": away, "injuries": injuries}
        )

    def test_no_signal_when_no_injuries(self):
        self.assertIsNone(self._evaluate("Heimsieg", {}))

    def test_gk_injury_has_higher_impact_than_defender(self):
        """Torwart-Ausfall ist gewichtiger als Verteidiger-Ausfall."""
        gk_out = {"ZAF": {"players": [{"name": "Williams", "position": "GK"}]}}
        df_out = {"ZAF": {"players": [{"name": "Mbatha", "position": "CB"}]}}
        s_gk = self._evaluate("Heimsieg", gk_out)
        s_df = self._evaluate("Heimsieg", df_out)
        # Bei beiden picked Heim, gegnerischer Ausfall → positiver Score
        self.assertGreater(s_gk.score, s_df.score,
            "GK-Ausfall muss mehr Boost geben als CB")

    def test_multiple_injuries_accumulate(self):
        """3 Ausfälle > 1 Ausfall (bis zum Cap)."""
        one = {"ZAF": {"players": [{"name": "Williams", "position": "GK"}]}}
        many = {"ZAF": {"players": [
            {"name": "Williams", "position": "GK"},
            {"name": "Mbatha", "position": "CB"},
            {"name": "Lebese", "position": "CM"},
        ]}}
        self.assertGreater(self._evaluate("Heimsieg", many).score,
                           self._evaluate("Heimsieg", one).score)

    def test_own_team_injury_hurts_pick(self):
        """Wenn das gepickte Team einen Top-Spieler verliert → negativ."""
        result = self._evaluate(
            "Heimsieg",
            {"MEX": {"players": [{"name": "Vega", "position": "GK"}]}}
        )
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)


class TestFormTrend(unittest.TestCase):
    """Form-Differenz der letzten Spiele."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.form_trend import FormTrendSignal
        cls.sig = FormTrendSignal()

    def test_positive_for_better_home_form(self):
        ctx = {"home_id": "MEX", "away_id": "ZAF",
               "form": {
                   "MEX": {"games": 5, "avgScored": 2.4, "avgConceded": 0.6},
                   "ZAF": {"games": 5, "avgScored": 1.0, "avgConceded": 2.0},
               }}
        result = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)

    def test_no_signal_with_too_few_games(self):
        ctx = {"home_id": "MEX", "away_id": "ZAF",
               "form": {"MEX": {"games": 2, "avgScored": 3.0, "avgConceded": 0.0},
                        "ZAF": {"games": 2, "avgScored": 0.0, "avgConceded": 5.0}}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))


class TestH2HPattern(unittest.TestCase):
    """H2H Win-Rate."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.h2h_pattern import H2HPatternSignal
        cls.sig = H2HPatternSignal()

    def test_positive_for_dominant_home_h2h(self):
        ctx = {"h2h": {"games": 8, "homeWins": 6, "draws": 1, "awayWins": 1}}
        result = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)
        self.assertIn("⚔️", result.evidence)

    def test_no_signal_below_sample_threshold(self):
        # Schwelle wurde 09.06.2026 von 5 auf 2 gesenkt. 1 Spiel ist immer noch zu wenig.
        ctx = {"h2h": {"games": 1, "homeWins": 1, "draws": 0, "awayWins": 0}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))


class TestXGStrength(unittest.TestCase):
    """xG-basierter Team-Stärke-Vergleich."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.xg_strength import XGStrengthSignal
        cls.sig = XGStrengthSignal()

    def test_positive_when_home_xg_better(self):
        ctx = {"home_id": "NED", "away_id": "SWE",
               "xg_stats": {
                   "NED": {"xgForAvg": 2.5, "xgAgainstAvg": 0.5, "games": 7},
                   "SWE": {"xgForAvg": 1.0, "xgAgainstAvg": 1.6, "games": 7},
               }}
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertIn("xG", r.evidence)

    def test_no_signal_with_too_few_games(self):
        ctx = {"home_id": "NED", "away_id": "SWE",
               "xg_stats": {
                   "NED": {"xgForAvg": 2.5, "xgAgainstAvg": 0.5, "games": 2},
                   "SWE": {"xgForAvg": 1.0, "xgAgainstAvg": 1.6, "games": 2},
               }}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))


class TestPolymarketSharp(unittest.TestCase):
    """Polymarket vs Pinnacle."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.polymarket_sharp import PolymarketSharpSignal
        cls.sig = PolymarketSharpSignal()

    def test_no_signal_when_volume_too_low(self):
        ctx = {"odds_snapshot": {"hw": 1.91, "dr": 3.47, "aw": 4.46},
               "poly_snapshot": {"poly_hw": 0.6, "poly_dr": 0.25, "poly_aw": 0.15,
                                 "poly_vol": 500}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_positive_when_poly_confirms_pick(self):
        # Pinnacle implied hw ~52%, Polymarket sees hw 60% → bestätigt Heim-Pick
        ctx = {"odds_snapshot": {"hw": 1.91, "dr": 3.47, "aw": 4.46},
               "poly_snapshot": {"poly_hw": 0.60, "poly_dr": 0.27, "poly_aw": 0.13,
                                 "poly_vol": 20000}}
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)


class TestSteamLagSignal(unittest.TestCase):
    """Pinnacle-Move + Polymarket-Lag."""

    @classmethod
    def setUpClass(cls):
        from sharp_signals.steam_lag import SteamLagSignal
        cls.sig = SteamLagSignal()

    def _build_history(self, t1, t2):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        return [
            {"ts": (now - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             **t1, "bk": "pinnacle"},
            {"ts": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             **t2, "bk": "pinnacle"},
        ]

    def test_no_signal_when_volume_too_low(self):
        hist = self._build_history(
            {"hw": 2.10, "dr": 3.40, "aw": 3.20},
            {"hw": 1.85, "dr": 3.60, "aw": 3.60})
        ctx = {"odds_history": hist,
               "poly_snapshot": {"poly_hw": 0.50, "poly_dr": 0.28, "poly_aw": 0.22,
                                 "poly_vol": 100}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))


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
                # 06.09.2026: der Loop lernt seit heute gegen den PREIS. Ein Pick ohne Quote
                # ist keine Beobachtung mehr — nicht aus Strenge, sondern weil ohne Quote
                # gar nicht feststeht, ob 20 Siege gut oder schlecht waren. 2.00 = der Markt
                # sagte 50/50, 20 Siege sind also ein echter Beitrag.
                "result": "win", "odds": 2.00,
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "wm_signal_ledger.json"
            weights_file = Path(td) / "signal_weights.json"
            ledger_file.write_text(json.dumps({"records": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "LEDGER_FILE", ledger_file), \
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
                "result": "loss", "odds": 2.00,
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "wm_signal_ledger.json"
            weights_file = Path(td) / "signal_weights.json"
            ledger_file.write_text(json.dumps({"records": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "LEDGER_FILE", ledger_file), \
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
                # 06.09.2026: der Loop lernt seit heute gegen den PREIS. Ein Pick ohne Quote
                # ist keine Beobachtung mehr — nicht aus Strenge, sondern weil ohne Quote
                # gar nicht feststeht, ob 20 Siege gut oder schlecht waren. 2.00 = der Markt
                # sagte 50/50, 20 Siege sind also ein echter Beitrag.
                "result": "win", "odds": 2.00,
                "signals": [{"name": "lead_lag_bias", "score": 2.0}]
            })
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "wm_signal_ledger.json"
            weights_file = Path(td) / "signal_weights.json"
            ledger_file.write_text(json.dumps({"records": picks}))
            weights_file.write_text(json.dumps({}))
            with patch.object(upd, "LEDGER_FILE", ledger_file), \
                 patch.object(upd, "WEIGHTS_FILE", weights_file):
                w = upd.update_weights()
        # Mit Smoothing sollte weight nahe 1.0 sein, nicht im Sanity-Bound
        self.assertGreater(w["lead_lag_bias"]["weight"], 0.95)
        self.assertLess(w["lead_lag_bias"]["weight"], 1.25,
            "Bei nur 3 Beobachtungen darf das Weight noch nicht extrem ausschlagen")


if __name__ == "__main__":
    unittest.main()
