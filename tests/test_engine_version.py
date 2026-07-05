#!/usr/bin/env python3
"""test_engine_version.py — version-aware Lernen (04.07.2026, Lucas: „damit künftige Engine-
Änderungen den Ledger nicht mehr mischen"). Friert Stempel + Version-Filter + Guard ein."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestEngineVersionConfig(unittest.TestCase):
    def test_per_profil(self):
        _prev_p = os.environ.pop("COCOBET_PROFILE", None)   # Env-Leak aus anderen Tests neutralisieren
        try:
            for ds, exp in (("wm", "v2"), ("liga", "v1"), ("mls", "v1")):
                os.environ["COCOBET_DATASET"] = ds
                os.environ.pop("COCOBET_PROFILE", None)
                import cocobet_dataset as D
                importlib.reload(D)
                self.assertEqual(D.engine_version(), exp)
        finally:
            os.environ["COCOBET_DATASET"] = "wm"
            if _prev_p is not None:
                os.environ["COCOBET_PROFILE"] = _prev_p


class TestStampImmutable(unittest.TestCase):
    """Stempel-Logik: set-if-absent — bestehende Stempel NIE überschreiben (Immutabilität)."""
    def test_set_if_absent(self):
        picks = {"A-1-X-Y": [
            {"verdict": "BET", "market": "Heimsieg"},                 # neu → stempeln
            {"verdict": "BET", "market": "Über 2.5 Tore", "engineVersion": "v1"},  # alt → behalten
        ]}
        ev = "v2"
        for plist in picks.values():
            for p in plist:
                if not p.get("engineVersion"):
                    p["engineVersion"] = ev
        self.assertEqual(picks["A-1-X-Y"][0]["engineVersion"], "v2")   # neu gestempelt
        self.assertEqual(picks["A-1-X-Y"][1]["engineVersion"], "v1")   # alt unangetastet


class TestLedgerCarriesVersion(unittest.TestCase):
    def test_record_hat_version(self):
        import build_signal_ledger as B
        importlib.reload(B)
        wm = {"groups": {}, "koFixtures": [
            {"home": "X", "away": "Y", "round": "R32",
             "result": {"status": "FT", "stats": {"homeXg": 2.0, "awayXg": 0.5}}}],
            "picks": {"KO-R32-X-Y": [
                {"verdict": "BET", "market": "Heimsieg", "result": "WIN", "engineVersion": "v2",
                 "signals": [{"name": "form_trend", "score": 2.0}]}]}}
        obs = B.collect_observations(wm)
        self.assertEqual(obs[0]["engineVersion"], "v2")


class TestVersionFilter(unittest.TestCase):
    def _load(self, recs):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset as D, update_signal_weights as U
        importlib.reload(D); importlib.reload(U)
        f = Path(tempfile.mktemp(suffix=".json"))
        f.write_text(json.dumps({"records": recs}), encoding="utf-8")
        U.LEDGER_FILE = f
        try:
            return U._load_results()
        finally:
            f.unlink()

    def test_nur_aktuelle_version(self):
        kept = self._load([
            {"engineVersion": "v2", "result": "WIN", "matchKey": "A-3-X-Y", "signals": [{"name": "s", "score": 1}]},
            {"engineVersion": "v1", "result": "WIN", "matchKey": "A-3-P-Q", "signals": [{"name": "s", "score": 1}]},
        ])
        keys = {r["matchKey"] for r in kept}
        self.assertIn("A-3-X-Y", keys)      # v2 aktuell → lernen
        self.assertNotIn("A-3-P-Q", keys)   # v1 alt → raus

    def test_legacy_ohne_stempel_matchday_fallback(self):
        kept = self._load([
            {"result": "WIN", "matchKey": "A-1-L-M", "signals": [{"name": "s", "score": 1}]},   # MD1 → raus
            {"result": "WIN", "matchKey": "A-3-N-O", "signals": [{"name": "s", "score": 1}]},   # MD3 → lernen
        ])
        keys = {r["matchKey"] for r in kept}
        self.assertNotIn("A-1-L-M", keys)
        self.assertIn("A-3-N-O", keys)


class TestGuard(unittest.TestCase):
    def test_flaggt_ungestempelte_actionable(self):
        import wm_data_integrity as W
        importlib.reload(W)
        wm = {"picks": {"A-1-X-Y": [
            {"verdict": "BET", "market": "Heimsieg"},                       # ohne Stempel → flag
            {"verdict": "BET", "market": "Über 2.5 Tore", "engineVersion": "v2"},  # ok
            {"verdict": "NOBET", "market": "Unter 2.5 Tore"},               # NOBET → egal
        ]}}
        ctx = W.IntegrityCtx(wm, {}, {}, {})
        res = W.check_engine_version_stamped(ctx)
        self.assertFalse(res.get("ok"))
        self.assertEqual(len(res.get("failures", [])), 1)   # nur der ungestempelte BET

    def test_alle_gestempelt_gruen(self):
        import wm_data_integrity as W
        importlib.reload(W)
        wm = {"picks": {"A-1-X-Y": [
            {"verdict": "BET", "market": "Heimsieg", "engineVersion": "v2"}]}}
        ctx = W.IntegrityCtx(wm, {}, {}, {})
        self.assertTrue(W.check_engine_version_stamped(ctx).get("ok"))


if __name__ == "__main__":
    unittest.main()
