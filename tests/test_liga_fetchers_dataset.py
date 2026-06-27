#!/usr/bin/env python3
"""test_liga_fetchers_dataset.py — Liga-Dataset-Awareness der Fetcher (26.06.2026).
apif: _load_wm_fixtures trägt fid + leitet time aus kickoff ab. injury: League-Liste + liga-Datei."""
import json
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_apifootball_predictions as A  # noqa: E402


class TestApifLigaFixtures(unittest.TestCase):
    def test_load_fixtures_carries_fid_and_time(self):
        data = {"teamIds": {"42": 42},
                "groups": {"ENG": {"fixtures": [
                    {"home": "42", "away": "1346", "date": "2026-08-21",
                     "kickoff": "2026-08-21T19:00:00+00:00", "fid": 1557367}]}}}
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp = Path(f.name)
        old = A.WM_FILE
        try:
            A.WM_FILE = tmp
            fx, tids = A._load_wm_fixtures()
        finally:
            A.WM_FILE = old
            os.unlink(tmp)
        self.assertEqual(len(fx), 1)
        self.assertEqual(fx[0]["fid"], 1557367)
        self.assertEqual(fx[0]["time"], "19:00")          # aus kickoff abgeleitet
        self.assertEqual(fx[0]["match_key"], "42-1346")


class TestInjuryLigaConfig(unittest.TestCase):
    def test_liga_constants_present(self):
        import fetch_wm_injuries as I
        self.assertEqual(set(I.LIGA_LEAGUES.values()), {39, 140, 78, 135, 61})
        self.assertTrue(hasattr(I, "_IS_LIGA"))


if __name__ == "__main__":
    unittest.main()
