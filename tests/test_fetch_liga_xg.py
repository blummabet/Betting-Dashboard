#!/usr/bin/env python3
"""
test_fetch_liga_xg.py — Liga-xG-Aggregation (25.06.2026, Lucas). Prüft den reinen Transformer +
die apply-Schleife (injizierte aggregate-Funktion → kein API nötig): source→apif_real bei echtem
xG, Staleness-Skip, Schreiben pro Team-id.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_xg as X  # noqa: E402


class TestBuildEntry(unittest.TestCase):
    def test_real_xg_source(self):
        e = X.build_xg_entry({"xgForAvg": 1.6, "xgAgainstAvg": 0.9, "xgGames": 6,
                              "source": "apif_fixtures_statistics"})
        self.assertEqual(e["source"], "apif_real")   # zählbar für xg_strength

    def test_no_real_xg_keeps_source(self):
        e = X.build_xg_entry({"xgForAvg": None, "xgGames": 0, "xgSimForAvg": 1.1,
                              "source": "apif_fixtures_statistics"})
        self.assertEqual(e["source"], "apif_fixtures_statistics")

    def test_none(self):
        self.assertIsNone(X.build_xg_entry(None))


class TestApply(unittest.TestCase):
    def _wm(self):
        return {"groups": {"ENG": {"teams": [{"id": "40"}, {"id": "50"}]}}, "xgStats": {}}

    def test_writes_per_team(self):
        wm = self._wm()
        calls = []
        def fake(api_id, our_id):
            calls.append((api_id, our_id))
            return {"xgForAvg": 1.5, "xgAgainstAvg": 1.0, "xgGames": 5, "games": 8,
                    "source": "apif_fixtures_statistics"}
        n = X.apply_to_wm(wm, fake)
        self.assertEqual(n, 2)
        self.assertEqual(calls, [(40, "40"), (50, "50")])   # api_id als int, our_id als str
        self.assertEqual(wm["xgStats"]["40"]["source"], "apif_real")

    def test_skips_fresh_und_angereichert(self):
        # Frisch UND bereits angereichert (keyPassesForAvg da) → übersprungen.
        wm = self._wm()
        wm["xgStats"]["40"] = {"xgForAvg": 1.2, "keyPassesForAvg": 9.1,
                               "updatedAt": datetime.now(timezone.utc).isoformat()}
        called = []
        def fake(api_id, our_id):
            called.append(our_id)
            return {"xgForAvg": 1.0, "xgGames": 4}
        X.apply_to_wm(wm, fake)
        self.assertEqual(called, ["50"])   # 40 frisch+angereichert → übersprungen

    def test_reichert_frische_basis_an(self):
        # 06.07.2026 (Lucas): frische Basis-xgStats von fetch_wm_corners (KEINE keyPassesForAvg)
        # darf NICHT übersprungen werden — sonst fehlen die Shot-Quality-Extras dauerhaft.
        wm = self._wm()
        wm["xgStats"]["40"] = {"xgForAvg": 1.2, "xgAgainstAvg": 1.0, "games": 7,
                               "updatedAt": datetime.now(timezone.utc).isoformat()}
        called = []
        def fake(api_id, our_id):
            called.append(our_id)
            return {"xgForAvg": 1.5, "xgAgainstAvg": 0.9, "xgGames": 6, "games": 8,
                    "keyPassesForAvg": 9.4, "ratingAvg": 7.1}
        X.apply_to_wm(wm, fake)
        self.assertEqual(sorted(called), ["40", "50"])   # 40 wird angereichert, nicht übersprungen
        self.assertEqual(wm["xgStats"]["40"]["keyPassesForAvg"], 9.4)

    def test_aggregate_none_skipped(self):
        wm = self._wm()
        n = X.apply_to_wm(wm, lambda a, o: None)
        self.assertEqual(n, 0)
        self.assertEqual(wm["xgStats"], {})


if __name__ == "__main__":
    unittest.main()
