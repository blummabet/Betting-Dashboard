"""
tests/test_fetch_wm_lineups.py — Unit-Tests für fetch_wm_lineups.py

Coverage:
  - Config-Loading
  - Kickoff-Datum-Berechnung
  - Lookahead/Lookback-Filter
  - Cache-Freshness Logik
  - Lineup-Parsing aus API-Football Response
  - State-Registry Sanity
"""
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestKickoffAndDue(unittest.TestCase):
    def setUp(self):
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_lineups"):
                del sys.modules[mod]
        import fetch_wm_lineups
        self.mod = fetch_wm_lineups

    def test_kickoff_parsing(self):
        ko = self.mod._kickoff_utc("2026-06-11", "19:00")
        self.assertIsNotNone(ko)
        self.assertEqual(ko.hour, 19)

    def test_kickoff_invalid(self):
        self.assertIsNone(self.mod._kickoff_utc("not-a-date", "19:00"))

    def test_is_fixture_due_within_lookahead(self):
        now = datetime.now(timezone.utc)
        ko_in_2h = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M").split()
        fx = {"date": ko_in_2h[0], "time": ko_in_2h[1]}
        self.assertTrue(self.mod._is_fixture_due(fx, now))

    def test_is_fixture_due_outside_lookahead(self):
        now = datetime.now(timezone.utc)
        ko_in_10h = (now + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M").split()
        fx = {"date": ko_in_10h[0], "time": ko_in_10h[1]}
        # Default lookahead = 3h
        self.assertFalse(self.mod._is_fixture_due(fx, now))

    def test_is_fixture_due_after_kickoff(self):
        # FIX 12.06.2026: lookback_hours auf 0 → ab Anpfiff NICHT mehr "due"
        # (Lineup ist pre-match; vorher 24h → Alerts/Fetches nach Spielende).
        now = datetime.now(timezone.utc)
        ko_2h_ago = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M").split()
        fx = {"date": ko_2h_ago[0], "time": ko_2h_ago[1]}
        self.assertFalse(self.mod._is_fixture_due(fx, now))

    def test_cache_fresh(self):
        now = datetime.now(timezone.utc)
        entry = {"fetchedAt": (now - timedelta(minutes=10)).isoformat()}
        self.assertTrue(self.mod._is_cache_fresh(entry))

    def test_cache_stale(self):
        now = datetime.now(timezone.utc)
        entry = {"fetchedAt": (now - timedelta(hours=2)).isoformat()}
        self.assertFalse(self.mod._is_cache_fresh(entry))

    def test_cache_missing_field(self):
        self.assertFalse(self.mod._is_cache_fresh({}))
        self.assertFalse(self.mod._is_cache_fresh(None))


class TestLineupParsing(unittest.TestCase):
    def setUp(self):
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_lineups"):
                del sys.modules[mod]
        import fetch_wm_lineups
        self.mod = fetch_wm_lineups

    def test_parse_lineup_entry(self):
        block = {"player": {"id": 1234, "name": "R. Jiménez", "pos": "F",
                            "grid": "1:3", "number": 9}}
        out = self.mod._parse_lineup_entry(block)
        self.assertEqual(out["id"], 1234)
        self.assertEqual(out["name"], "R. Jiménez")
        self.assertEqual(out["pos"], "F")

    def test_fetch_lineup_for_fixture_normal_response(self):
        payload = {
            "response": [
                {"team": {"id": 26, "name": "Mexico"},
                 "formation": "4-3-3",
                 "coach": {"name": "Trainer A"},
                 "startXI":     [{"player": {"id": 1, "name": "GK", "pos": "G"}}],
                 "substitutes": [{"player": {"id": 2, "name": "Sub1", "pos": "M"}}]},
                {"team": {"id": 31, "name": "South Africa"},
                 "formation": "4-2-3-1",
                 "coach": {"name": "Trainer B"},
                 "startXI":     [{"player": {"id": 11, "name": "GK2", "pos": "G"}}],
                 "substitutes": []},
            ]
        }
        with patch.object(self.mod, "_apif_get", return_value=payload):
            result = self.mod._fetch_lineup_for_fixture(99999)
        self.assertIsNotNone(result)
        self.assertEqual(result["home"]["formation"], "4-3-3")
        self.assertEqual(len(result["home"]["starting"]), 1)
        self.assertEqual(len(result["home"]["subs"]), 1)
        self.assertEqual(result["away"]["formation"], "4-2-3-1")

    def test_fetch_lineup_for_fixture_returns_none_on_empty(self):
        with patch.object(self.mod, "_apif_get",
                          return_value={"response": []}):
            result = self.mod._fetch_lineup_for_fixture(99999)
        self.assertIsNone(result)


class TestStateRegistry(unittest.TestCase):
    def test_lineups_registered(self):
        import json
        reg = json.loads((REPO / "state_files_registry.json").read_text(encoding="utf-8"))
        files = reg["categories"]["fetch_wm_data"]["files"]
        self.assertIn("wm_lineups.json", files)


class TestGenerateMergesLineups(unittest.TestCase):
    """Sanity: generate_wm_picks.py liest wm_lineups.json."""

    def test_lineups_load_code_present(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("wm_lineups.json", src)
        self.assertIn("lineups_data", src)


class TestWorkflowIntegration(unittest.TestCase):
    """Sanity: Workflow ruft fetch_wm_lineups.py auf."""

    def test_workflow_has_lineup_step(self):
        wf = (REPO / ".github" / "workflows" / "fetch-wm-data.yml").read_text(encoding="utf-8")
        self.assertIn("fetch_wm_lineups.py", wf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
