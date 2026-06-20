"""
tests/test_apif_predictions.py — Tests für ApifPredictionsSignal + Fetcher

Coverage:
  - Signal: confirmatory (+) vs warnend (-)
  - Signal: min_diff_pp Threshold, max_credible_pp Filter
  - Signal: Outcome-Mapping 1X2/DNB
  - Signal: Returns None bei fehlenden Daten
  - Fetcher: _parse_percent (String "62%" → 0.62)
  - Fetcher: _fetch_prediction normalisiert percent zu Summe ≈ 1
  - Fetcher: _is_cache_fresh, _is_upcoming Lookahead
  - Registry: Signal registriert + unique group
  - Workflow: Step in fetch-wm-data.yml
"""
import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.apif_predictions import ApifPredictionsSignal, _outcome_key


class TestOutcomeMapping(unittest.TestCase):
    def test_heimsieg(self):
        self.assertEqual(_outcome_key("Heimsieg"), "home")
    def test_auswartssieg(self):
        self.assertEqual(_outcome_key("Auswärtssieg"), "away")
    def test_unentschieden(self):
        self.assertEqual(_outcome_key("Unentschieden"), "draw")
    def test_dnb(self):
        self.assertEqual(_outcome_key("DNB: Heimteam"), "home")
        self.assertEqual(_outcome_key("DNB: Auswärtsteam"), "away")
    def test_over_under_returns_none(self):
        self.assertIsNone(_outcome_key("Über 2.5 Tore"))
        self.assertIsNone(_outcome_key("Unter 2.5 Tore"))


class TestSignalEvaluation(unittest.TestCase):
    def setUp(self):
        self.sig = ApifPredictionsSignal()

    def _ctx(self, apif_pct, pinn_odds=(1.50, 4.00, 7.00)):
        """Pinnacle 1.50/4.00/7.00 → devigged ≈ 0.62/0.23/0.13."""
        return {
            "matchKey":      "MEX-ZAF",
            "apif_predictions": {
                "MEX-ZAF": {"percent": apif_pct}
            },
            "odds_snapshot": {"hw": pinn_odds[0], "dr": pinn_odds[1], "aw": pinn_odds[2]},
        }

    def test_placeholder_advice_skipped(self):
        """API-Football „No predictions available" → kein Signal (17.06.2026 Audit)."""
        ctx = self._ctx({"home": 0.33, "draw": 0.33, "away": 0.33})
        ctx["apif_predictions"]["MEX-ZAF"]["advice"] = "No predictions available"
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_flat_percent_skipped(self):
        """Flache 0.33/0.33/0.33 (Platzhalter ohne advice) → kein Signal."""
        ctx = self._ctx({"home": 0.33, "draw": 0.33, "away": 0.34})
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_confirmatory_positive(self):
        """APIF gibt Heim mit 75% an, Pinnacle 62% → +13pp diff → confirmatory."""
        ctx = self._ctx({"home": 0.75, "draw": 0.15, "away": 0.10})
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertIn("höher", r.evidence)

    def test_warning_negative(self):
        """APIF gibt Heim mit 40%, Pinnacle 62% → -22pp → max_credible exceed → None."""
        ctx = self._ctx({"home": 0.40, "draw": 0.30, "away": 0.30})
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        # -22pp > max_credible_pp (20) → None
        self.assertIsNone(r)

    def test_moderate_warning(self):
        """APIF gibt Heim mit 50%, Pinnacle 62% → -12pp → warnend negativ."""
        ctx = self._ctx({"home": 0.50, "draw": 0.30, "away": 0.20})
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)
        self.assertIn("Vorsicht", r.evidence)

    def test_below_min_diff_returns_none(self):
        """APIF gibt Heim mit 64%, Pinnacle 62% → 2pp → unter Threshold → None."""
        ctx = self._ctx({"home": 0.64, "draw": 0.23, "away": 0.13})
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNone(r)

    def test_no_predictions_returns_none(self):
        ctx = {"matchKey": "MEX-ZAF", "apif_predictions": {},
               "odds_snapshot": {"hw": 1.50, "dr": 4.00, "aw": 7.00}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_no_pinnacle_returns_none(self):
        ctx = {"matchKey": "MEX-ZAF",
               "apif_predictions": {"MEX-ZAF": {"percent": {"home": 0.75}}},
               "odds_snapshot": {}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_over_under_market_returns_none(self):
        """Signal feuert NUR für 1X2/DNB — nicht für O/U."""
        ctx = self._ctx({"home": 0.75, "draw": 0.15, "away": 0.10})
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx))


class TestFetcherHelpers(unittest.TestCase):
    def setUp(self):
        for m in list(sys.modules):
            if m.startswith("fetch_wm_apifootball"):
                del sys.modules[m]
        import fetch_wm_apifootball_predictions as f
        self.mod = f

    def test_parse_percent_string(self):
        self.assertEqual(self.mod._parse_percent("62%"), 0.62)
        self.assertEqual(self.mod._parse_percent("8.5%"), 0.085)

    def test_parse_percent_invalid(self):
        self.assertIsNone(self.mod._parse_percent(None))
        self.assertIsNone(self.mod._parse_percent("invalid"))

    def test_fetch_prediction_normalizes(self):
        """Wenn APIF percent nicht ≈ 100% summiert wird, re-normalisieren."""
        payload = {
            "response": [{
                "predictions": {
                    "percent": {"home": "50%", "draw": "30%", "away": "30%"},  # = 110%
                    "advice": "Mexico to win",
                    "winner": {"id": 26, "name": "Mexico"},
                },
                "comparison": {},
            }]
        }
        with patch.object(self.mod, "_apif_get", return_value=payload):
            r = self.mod._fetch_prediction(1)
        s = r["percent"]["home"] + r["percent"]["draw"] + r["percent"]["away"]
        self.assertAlmostEqual(s, 1.0, places=2)

    def test_fetch_prediction_returns_none_on_empty(self):
        with patch.object(self.mod, "_apif_get", return_value={"response": []}):
            self.assertIsNone(self.mod._fetch_prediction(1))

    def test_is_cache_fresh(self):
        now = datetime.now(timezone.utc)
        fresh = {"fetchedAt": (now - timedelta(hours=1)).isoformat()}
        stale = {"fetchedAt": (now - timedelta(hours=48)).isoformat()}
        self.assertTrue(self.mod._is_cache_fresh(fresh))
        self.assertFalse(self.mod._is_cache_fresh(stale))
        self.assertFalse(self.mod._is_cache_fresh({}))

    def test_is_upcoming(self):
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=2)
        far  = now + timedelta(days=20)
        past = now - timedelta(days=2)
        self.assertTrue(self.mod._is_upcoming(
            {"date": soon.strftime("%Y-%m-%d"), "time": soon.strftime("%H:%M")}, now))
        self.assertFalse(self.mod._is_upcoming(
            {"date": far.strftime("%Y-%m-%d"), "time": far.strftime("%H:%M")}, now))
        self.assertFalse(self.mod._is_upcoming(
            {"date": past.strftime("%Y-%m-%d"), "time": past.strftime("%H:%M")}, now))


class TestRegistryAndConfig(unittest.TestCase):
    def test_signal_registered(self):
        from sharp_signals.registry import ACTIVE_SIGNALS, SIGNAL_GROUPS
        names = [s.name() for s in ACTIVE_SIGNALS]
        self.assertIn("apif_predictions", names)
        self.assertEqual(SIGNAL_GROUPS.get("apif_predictions"), "unique")

    def test_signal_weight_present(self):
        w = json.loads((REPO / "signal_weights.json").read_text(encoding="utf-8"))
        self.assertIn("apif_predictions", w)

    def test_state_file_registered(self):
        reg = json.loads((REPO / "state_files_registry.json").read_text(encoding="utf-8"))
        files = reg["categories"]["fetch_wm_data"]["files"]
        self.assertIn("wm_apif_predictions.json", files)

    def test_workflow_has_step(self):
        wf = (REPO / ".github" / "workflows" / "fetch-wm-data.yml").read_text(encoding="utf-8")
        self.assertIn("fetch_wm_apifootball_predictions.py", wf)

    def test_generate_picks_loads_predictions(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("wm_apif_predictions.json", src)
        self.assertIn("apif_predictions_data", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
