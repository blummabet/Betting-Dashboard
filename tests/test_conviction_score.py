"""
tests/test_conviction_score.py — Tests + Anti-Drift für conviction_score.py

Architektur:
  - Sharp-Move-Trigger (Pinnacle bewegt, Softs hinterher)
  - 6 Familien à max-pt: sharp_money(3), form(2), context(2),
    realtime(2), market(1), model(1) = max 10
  - Verdict: ≥8 top, ≥6 abwaegen, ≥4 watch, <4 skip
  - Bayesian-Weights aus signal_weights.json
  - Config aus cocobet_config.json → profiles.<profile>.conviction_score
"""
import json
import os
import sys
import unittest
import importlib
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

os.environ.pop("COCOBET_PROFILE", None)
from conviction_score import (
    compute_conviction_score, detect_sharp_move,
    detect_opening_movement, _pick_direction, _load_config,
)


def _signal(name, score=1.0, confidence=0.6, evidence="test"):
    return {"name": name, "score": score, "confidence": confidence, "evidence": evidence}


# ──────────────────────────────────────────────────────────────────────────
#  Familien-Caps + Verdict-Thresholds
# ──────────────────────────────────────────────────────────────────────────
class TestFamilyCaps(unittest.TestCase):
    def test_sharp_money_max_3(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("lead_lag_bias"),
            _signal("steam_lag"),
            _signal("polymarket_sharp"),
        ], "combined_score_pp": 3.0, "n_positive_signals": 3}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertLessEqual(r["family_scores"]["sharp_money"], 3)

    def test_freshness_dampens_sharp_money(self):
        # 18.06.2026 (Lucas): ein stale/gedrehter Move darf sharp_money nicht voll kreditieren.
        base = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80,
                "source": "steam", "steamMovePP": 6.0, "entryBook": "soft", "softConfirmed": True}
        sig_out = {"signals": [_signal("lead_lag_bias"), _signal("steam_lag")],
                   "combined_score_pp": 3.0, "n_positive_signals": 2}
        # confirm / kein State → volle Sharp-Punkte
        full = compute_conviction_score({**base, "freshnessState": "confirm"}, sig_out, {})
        self.assertGreaterEqual(full["family_scores"]["sharp_money"], 2)
        # drift → gedeckelt auf 1
        drift = compute_conviction_score({**base, "freshnessState": "drift"}, sig_out, {})
        self.assertLessEqual(drift["family_scores"]["sharp_money"], 1)
        # reverse → 0
        rev = compute_conviction_score({**base, "freshnessState": "reverse"}, sig_out, {})
        self.assertEqual(rev["family_scores"]["sharp_money"], 0)
        # und drift kostet echte Gesamt-Punkte ggü. confirm
        self.assertLess(drift["score"], full["score"])

    def test_model_stack_max_3(self):
        # Familien-Restruktur 09.06.2026: form_trend + xg + h2h + injury → model_stack
        # plus Modell-Sanity wenn modelOdds ≤10pp vom Markt
        pick = {"market": "Unter 2.5 Tore", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("form_trend"),
            _signal("xg_strength"),
            _signal("h2h_pattern"),
            _signal("injury"),
        ], "combined_score_pp": 4.0, "n_positive_signals": 4}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertEqual(r["family_scores"]["model_stack"], 3)

    def test_score_clamped_to_10(self):
        # Alle 4 Familien max füllen (Restruktur 09.06.2026):
        # sharp_money(3) + model_stack(3) + context(3) + market(1) = 10
        pick = {"market": "Unter 2.5 Tore", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("lead_lag_bias"),
            _signal("form_trend"), _signal("xg_strength"), _signal("h2h_pattern"), _signal("injury"),
            _signal("travel_burden"), _signal("lineup_signal"), _signal("weather_signal"),
            _signal("incentive_signal"), _signal("pressure_index"),
            _signal("apif_predictions"), _signal("public_static_bias"),
        ], "combined_score_pp": 5.0, "n_positive_signals": 12}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertLessEqual(r["score"], 10)
        # Mit lead_lag + opening_movement potentiell + all families maxed → sollte ≥7 sein
        self.assertGreaterEqual(r["score"], 7)


class TestMlsContextFamily(unittest.TestCase):
    """25.07.2026 (Lucas: „Kontext 0/3 bei MLS"): league_pressure + mls_travel müssen
    in die Kontext-Familie zählen (die WM-Kontext-Signale sind im MLS-Profil aus)."""

    def test_mls_travel_scores_context_point(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [_signal("mls_travel", score=1.8, confidence=0.65)],
                   "combined_score_pp": 1.8, "n_positive_signals": 1}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertGreaterEqual(r["family_scores"]["context"], 1)
        self.assertTrue(any("mls_travel" in e for e in r["evidence"]))

    def test_league_pressure_scores_context_point(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [_signal("league_pressure", score=1.2, confidence=0.6)],
                   "combined_score_pp": 1.2, "n_positive_signals": 1}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertGreaterEqual(r["family_scores"]["context"], 1)
        self.assertTrue(any("league_pressure" in e for e in r["evidence"]))

    def test_negative_mls_travel_no_context_point(self):
        # Reise-Nachteil (score<0) darf keinen Conviction-Punkt geben.
        pick = {"market": "Auswärtssieg", "odds": 2.4, "modelOdds": 2.3}
        sig_out = {"signals": [_signal("mls_travel", score=-1.07, confidence=0.65)],
                   "combined_score_pp": -1.07, "n_positive_signals": 0}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertEqual(r["family_scores"]["context"], 0)

    def test_context_capped_at_3(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("mls_travel"), _signal("league_pressure"), _signal("lineup_signal"),
            _signal("travel_burden"), _signal("weather_signal"),
        ], "combined_score_pp": 3.0, "n_positive_signals": 5}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertLessEqual(r["family_scores"]["context"], 3)


class TestFamilyRegistrySync(unittest.TestCase):
    """25.07.2026: SSOT-Guard. Ein neues Registry-context/incentive-Signal darf nicht
    STILL aus der Conviction fallen (das war der MLS-Kontext-0/3-Gap). Es muss entweder
    in einer Conviction-Familie gewertet ODER in CONTEXT_UNCREDITED dokumentiert sein."""

    def test_no_context_signal_silently_dropped(self):
        from conviction_score import CONVICTION_FAMILIES, CONTEXT_UNCREDITED
        from sharp_signals.registry import SIGNAL_GROUPS
        credited = {s for names in CONVICTION_FAMILIES.values() for s in names}
        registry_context = {sig for sig, fam in SIGNAL_GROUPS.items()
                            if fam in ("context", "incentive")}
        unaccounted = registry_context - credited - CONTEXT_UNCREDITED
        self.assertEqual(unaccounted, set(),
                         f"Registry-Kontext/Anreiz-Signale ohne Conviction-Zuordnung: {unaccounted} — "
                         f"in eine CONVICTION_FAMILIES-Familie aufnehmen oder in CONTEXT_UNCREDITED dokumentieren.")

    def test_context_family_has_mls_signals(self):
        from conviction_score import CONVICTION_FAMILIES
        self.assertIn("league_pressure", CONVICTION_FAMILIES["context"])
        self.assertIn("mls_travel", CONVICTION_FAMILIES["context"])

    def test_uncredited_not_double_counted(self):
        # Was als „ungewertet" markiert ist, darf nicht doch in einer Familie stehen.
        from conviction_score import CONVICTION_FAMILIES, CONTEXT_UNCREDITED
        credited = {s for names in CONVICTION_FAMILIES.values() for s in names}
        self.assertEqual(credited & CONTEXT_UNCREDITED, set())


class TestVerdictThresholds(unittest.TestCase):
    def test_top_at_8(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("lead_lag_bias"), _signal("polymarket_sharp"),
            _signal("form_trend"), _signal("h2h_pattern"),
            _signal("travel_burden"), _signal("incentive_signal"),
            _signal("lineup_signal"),
            _signal("apif_predictions"),
        ], "combined_score_pp": 4.0, "n_positive_signals": 8}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertGreaterEqual(r["score"], 8)
        self.assertEqual(r["verdict"], "top")

    def test_abwaegen_at_6(self):
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [
            _signal("lead_lag_bias"), _signal("polymarket_sharp"),
            _signal("form_trend"), _signal("h2h_pattern"),
            _signal("travel_burden"), _signal("incentive_signal"),
        ], "combined_score_pp": 3.0, "n_positive_signals": 6}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertGreaterEqual(r["score"], 6)
        self.assertIn(r["verdict"], ("abwaegen", "top"))

    def test_skip_low_score(self):
        pick = {"market": "Heimsieg", "odds": 5.0, "modelOdds": 1.80}  # 60pp halluzination
        sig_out = {"signals": [], "combined_score_pp": 0, "n_positive_signals": 0}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertLess(r["score"], 4)
        self.assertEqual(r["verdict"], "skip")


# ──────────────────────────────────────────────────────────────────────────
#  Modell-Sanity Familie
# ──────────────────────────────────────────────────────────────────────────
class TestModellSanity(unittest.TestCase):
    def test_model_close_to_market_grants_point(self):
        # Modell 1.80 vs Markt 1.85 → ~1.5pp Diff → Modell-Sanity in model_stack-Familie
        pick = {"market": "Heimsieg", "odds": 1.85, "modelOdds": 1.80}
        sig_out = {"signals": [], "combined_score_pp": 0, "n_positive_signals": 0}
        r = compute_conviction_score(pick, sig_out, {})
        self.assertGreaterEqual(r["family_scores"]["model_stack"], 1)

    def test_model_hallucinates_no_point(self):
        # Modell 1.80 vs Markt 4.0 → ~30pp Diff → keine Modell-Sanity-Bonus
        pick = {"market": "Auswärtssieg", "odds": 4.0, "modelOdds": 1.80}
        sig_out = {"signals": [], "combined_score_pp": 0, "n_positive_signals": 0}
        r = compute_conviction_score(pick, sig_out, {})
        # Halluzination: model_stack ohne Form-/xG-Signale + ohne Modell-Sanity = 0
        self.assertEqual(r["family_scores"]["model_stack"], 0)


# ──────────────────────────────────────────────────────────────────────────
#  Sharp-Move Detection
# ──────────────────────────────────────────────────────────────────────────
class TestSharpMoveDetection(unittest.TestCase):
    def test_no_history_no_trigger(self):
        pick = {"market": "Heimsieg"}
        r = detect_sharp_move(pick, {"odds_history": []}, _load_config())
        self.assertIsNone(r)

    def test_pick_direction(self):
        self.assertEqual(_pick_direction("Heimsieg"), "home")
        self.assertEqual(_pick_direction("Auswärtssieg"), "away")
        self.assertEqual(_pick_direction("Über 2.5 Tore"), "over")
        self.assertEqual(_pick_direction("Unter 1.5 Tore"), "under")


# ──────────────────────────────────────────────────────────────────────────
#  Opening-Movement
# ──────────────────────────────────────────────────────────────────────────
class TestOpeningMovement(unittest.TestCase):
    def test_in_pick_direction_detected(self):
        # Pinnacle 2.0 → 1.7 (drop) für Heimsieg-Pick = +Move
        pick = {"market": "Heimsieg"}
        ctx = {"odds_history": [
            {"ts": "2026-06-01T00:00:00Z", "pinn_hw": 2.0},
            {"ts": "2026-06-09T00:00:00Z", "pinn_hw": 1.7},
        ]}
        r = detect_opening_movement(pick, ctx, _load_config())
        self.assertIsNotNone(r)
        self.assertTrue(r["in_pick_direction"])
        self.assertGreater(r["move_pp"], 3.0)

    def test_against_pick_direction(self):
        pick = {"market": "Heimsieg"}
        ctx = {"odds_history": [
            {"ts": "2026-06-01T00:00:00Z", "pinn_hw": 1.7},
            {"ts": "2026-06-09T00:00:00Z", "pinn_hw": 2.0},
        ]}
        r = detect_opening_movement(pick, ctx, _load_config())
        self.assertFalse(r["in_pick_direction"])


# ──────────────────────────────────────────────────────────────────────────
#  Profile-Switch
# ──────────────────────────────────────────────────────────────────────────
class TestProfileSwitch(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COCOBET_PROFILE", None)
        from conviction_score import _load_config

    def test_wm2026_defaults(self):
        os.environ.pop("COCOBET_PROFILE", None)
        cfg = _load_config()
        self.assertEqual(cfg["sharp_move"]["min_pinn_move_pp"], 5.0)
        self.assertEqual(cfg["verdict_thresholds"]["top"], 8)

    def test_liga_default_has_different_thresholds(self):
        os.environ["COCOBET_PROFILE"] = "liga_default"
        cfg = _load_config()
        # Liga hat min_hours_since_open = 12 (länger als WM)
        self.assertEqual(cfg["sharp_move"]["min_hours_since_open"], 12)


# ──────────────────────────────────────────────────────────────────────────
#  Anti-Drift: Config-Felder sind konfigurierbar (nicht hardcoded)
# ──────────────────────────────────────────────────────────────────────────
class TestAntiDrift(unittest.TestCase):
    """
    Wenn jemand die Conviction-Score-Konstanten direkt im Code hardcoded
    statt aus Config zu lesen, brechen diese Tests.
    """
    def test_thresholds_from_config_not_hardcoded(self):
        src = (REPO / "conviction_score.py").read_text(encoding="utf-8")
        # _load_config muss verwendet werden
        self.assertIn("_load_config()", src,
            "Conviction-Score muss _load_config() nutzen, nicht hardcoded Werte")
        # cfg-Lookups müssen vorkommen
        self.assertIn('cfg["verdict_thresholds"]', src)
        self.assertIn('cfg["family_caps"]', src)

    def test_signal_weights_loaded(self):
        src = (REPO / "conviction_score.py").read_text(encoding="utf-8")
        self.assertIn("_load_signal_weights", src,
            "Bayesian-Weights müssen aus signal_weights.json gelesen werden")

    def test_compute_conviction_in_generate_wm_picks(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("compute_conviction_score", src,
            "compute_conviction_score muss in generate_wm_picks.py aufgerufen werden")
        self.assertIn("convictionScore", src,
            "convictionScore-Feld muss an Picks angehängt werden")

    def test_renderer_shows_conviction(self):
        src = (REPO / "wm2026-renderer.js").read_text(encoding="utf-8")
        self.assertIn("convictionScore", src,
            "Renderer muss convictionScore-Feld anzeigen")
        self.assertIn("Conviction", src.replace("conviction", "Conviction"))


if __name__ == "__main__":
    unittest.main()
