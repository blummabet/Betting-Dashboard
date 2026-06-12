"""
tests/test_fetch_wm_nt_xg.py — Tests für NT-xG Pipeline

Coverage:
  - Config-Loading mit Profile-Override
  - APIF-Name-Override-Mapping
  - aggregate_team_xg() mit Mock-Daten
  - HTTP-Layer mit Mock-Responses
  - Save/Load Round-Trip
  - xG-Extraction aus statistics-Antworten (mehrere Label-Varianten)
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestConfigLoading(unittest.TestCase):
    def setUp(self):
        # Reload module to ensure fresh CFG
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_nt_xg"):
                del sys.modules[mod]

    def test_defaults_when_no_config_file(self):
        with patch("pathlib.Path.exists", return_value=False):
            import fetch_wm_nt_xg
            self.assertEqual(fetch_wm_nt_xg.DEFAULT_CFG["lookback_fixtures"], 10)
            self.assertEqual(fetch_wm_nt_xg.DEFAULT_CFG["min_fixtures"], 3)
            self.assertFalse(fetch_wm_nt_xg.DEFAULT_CFG["skip_if_understat"])

    def test_apif_name_override_completeness(self):
        """Alle 48 WM-Teams müssen ein APIF-Name-Mapping haben."""
        import fetch_wm_nt_xg
        names = fetch_wm_nt_xg.APIF_NAME_OVERRIDE
        # mind. 48 Einträge, alle 3-stellig
        self.assertGreaterEqual(len(names), 48)
        for our_id, apif_name in names.items():
            self.assertEqual(len(our_id), 3, f"Bad ID: {our_id}")
            self.assertIsInstance(apif_name, str)
            self.assertGreater(len(apif_name), 1)


class TestXGExtraction(unittest.TestCase):
    """Tests für die statistics → xG Extraktion."""

    def setUp(self):
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_nt_xg"):
                del sys.modules[mod]
        import fetch_wm_nt_xg
        self.mod = fetch_wm_nt_xg

    def _mock_apif_get(self, response_payload):
        """Hilfsfunktion: Patch _apif_get um eine fixe Response zurückzugeben."""
        return patch.object(self.mod, "_apif_get", return_value=response_payload)

    def test_extracts_expected_goals_lowercase_underscore(self):
        """API-Football Standard-Label: 'expected_goals'."""
        payload = {
            "response": [
                {"team": {"id": 26}, "statistics": [
                    {"type": "expected_goals", "value": "1.45"},
                    {"type": "Ball Possession", "value": "55%"},
                ]},
                {"team": {"id": 31}, "statistics": [
                    {"type": "expected_goals", "value": 0.82},
                ]},
            ]
        }
        with self._mock_apif_get(payload):
            out = self.mod._extract_xg_from_statistics(99999)
        self.assertEqual(out[26]["xg"], 1.45)
        self.assertEqual(out[31]["xg"], 0.82)

    def test_extracts_expected_goals_titlecase_spaces(self):
        """Manche Ligen labeln 'Expected Goals' mit Leerzeichen."""
        payload = {
            "response": [
                {"team": {"id": 1}, "statistics": [
                    {"type": "Expected Goals", "value": "2.10"}]},
            ]
        }
        with self._mock_apif_get(payload):
            out = self.mod._extract_xg_from_statistics(1)
        self.assertEqual(out[1]["xg"], 2.10)

    def test_extracts_xg_label(self):
        """Manche Quellen nur 'xG' als Label."""
        payload = {
            "response": [
                {"team": {"id": 5}, "statistics": [
                    {"type": "xG", "value": "0.75"}]},
            ]
        }
        with self._mock_apif_get(payload):
            out = self.mod._extract_xg_from_statistics(1)
        self.assertEqual(out[5]["xg"], 0.75)

    def test_returns_empty_when_no_xg_field(self):
        """Wenn keine xG-Stat existiert: leeres Dict."""
        payload = {
            "response": [
                {"team": {"id": 1}, "statistics": [
                    {"type": "Total Shots", "value": "12"},
                    {"type": "Ball Possession", "value": "48%"},
                ]},
            ]
        }
        with self._mock_apif_get(payload):
            out = self.mod._extract_xg_from_statistics(1)
        self.assertEqual(out, {})

    def test_skips_null_xg_values(self):
        """Null- oder Empty-Werte werden übersprungen."""
        payload = {
            "response": [
                {"team": {"id": 1}, "statistics": [
                    {"type": "expected_goals", "value": None}]},
                {"team": {"id": 2}, "statistics": [
                    {"type": "expected_goals", "value": ""}]},
                {"team": {"id": 3}, "statistics": [
                    {"type": "expected_goals", "value": "1.50"}]},
            ]
        }
        with self._mock_apif_get(payload):
            out = self.mod._extract_xg_from_statistics(1)
        self.assertNotIn(1, out)
        self.assertNotIn(2, out)
        self.assertEqual(out[3]["xg"], 1.50)

    def test_returns_empty_on_request_failure(self):
        with self._mock_apif_get(None):
            out = self.mod._extract_xg_from_statistics(1)
        self.assertEqual(out, {})


class TestAggregation(unittest.TestCase):
    """Tests für aggregate_team_xg() — End-to-End mit Mocks."""

    def setUp(self):
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_nt_xg"):
                del sys.modules[mod]
        import fetch_wm_nt_xg
        self.mod = fetch_wm_nt_xg
        # Player-Endpoint im Test aus (sonst echte _apif_get-Calls)
        self.mod.CFG = {**self.mod.DEFAULT_CFG, "request_delay_sec": 0,
                        "fetch_player_stats": False}

    @staticmethod
    def _row(xg, inside, on):
        """Rich-Stats-Zeile wie _extract_fixture_stats sie liefert."""
        return {"xg": xg, "xgsim": round(0.118 * inside + 0.10 * on, 3),
                "inside": inside, "outside": 0.0, "on": on, "total": inside,
                "blocked": 0.0, "saves": 0.0}

    def test_aggregates_xg_from_multiple_fixtures(self):
        """Klassiker: 3 Fixtures mit echtem xG → Aggregat = Avg."""
        fixtures = [
            {"id": 100, "home_id": 26, "away_id": 31, "date": "2025-01-01T00:00:00+00:00"},
            {"id": 101, "home_id": 31, "away_id": 26, "date": "2024-11-01T00:00:00+00:00"},
            {"id": 102, "home_id": 26, "away_id": 99, "date": "2024-09-01T00:00:00+00:00"},
        ]
        per_fixture = {
            100: {26: self._row(1.5, 10, 5), 31: self._row(0.8, 4, 2)},
            101: {31: self._row(1.2, 8, 4), 26: self._row(0.6, 5, 2)},
            102: {26: self._row(2.0, 12, 6), 99: self._row(0.4, 3, 1)},
        }
        with patch.object(self.mod, "_list_recent_fixtures", return_value=fixtures), \
             patch.object(self.mod, "_extract_fixture_stats",
                          side_effect=lambda fid: per_fixture.get(fid, {})):
            result = self.mod.aggregate_team_stats(26, "MEX")
        self.assertIsNotNone(result)
        self.assertEqual(result["games"], 3)
        self.assertEqual(result["xgGames"], 3)
        self.assertAlmostEqual(result["xgForAvg"], (1.5 + 0.6 + 2.0) / 3, places=2)
        self.assertAlmostEqual(result["xgAgainstAvg"], (0.8 + 1.2 + 0.4) / 3, places=2)
        self.assertIsNotNone(result["xgSimForAvg"])  # Proxy immer berechnet
        self.assertEqual(result["source"], "apif_fixtures_statistics")

    def test_returns_none_when_too_few_fixtures(self):
        with patch.object(self.mod, "_list_recent_fixtures", return_value=[{"id": 1, "home_id": 26, "away_id": 31}]):
            result = self.mod.aggregate_team_stats(26, "MEX")
        self.assertIsNone(result)

    def test_xgsim_when_no_real_xg(self):
        """Kernfall: KEIN echtes xG → xgForAvg=None, aber xgSimForAvg da (Lücken-Fill)."""
        fixtures = [
            {"id": 100, "home_id": 26, "away_id": 31, "date": "2025-01-01T00:00:00+00:00"},
            {"id": 101, "home_id": 26, "away_id": 31, "date": "2024-12-01T00:00:00+00:00"},
            {"id": 102, "home_id": 26, "away_id": 31, "date": "2024-11-01T00:00:00+00:00"},
        ]
        per_fixture = {fid: {26: self._row(None, 10, 5), 31: self._row(None, 3, 1)}
                       for fid in (100, 101, 102)}
        with patch.object(self.mod, "_list_recent_fixtures", return_value=fixtures), \
             patch.object(self.mod, "_extract_fixture_stats",
                          side_effect=lambda fid: per_fixture.get(fid, {})):
            result = self.mod.aggregate_team_stats(26, "MEX")
        self.assertIsNotNone(result)
        self.assertEqual(result["games"], 3)
        self.assertEqual(result["xgGames"], 0)
        self.assertIsNone(result["xgForAvg"])             # kein echtes xG
        self.assertAlmostEqual(result["xgSimForAvg"], 0.118 * 10 + 0.10 * 5, places=2)


class TestSaveLoad(unittest.TestCase):
    """Test atomares Save + Reload."""

    def setUp(self):
        for mod in list(sys.modules):
            if mod.startswith("fetch_wm_nt_xg"):
                del sys.modules[mod]
        import fetch_wm_nt_xg
        self.mod = fetch_wm_nt_xg

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.mod.OUTPUT_FILE = Path(tmpdir) / "wm_nt_xg.json"
            data = {
                "MEX": {"xgForAvg": 1.32, "xgAgainstAvg": 0.85, "games": 7,
                        "source": "apif_fixtures_statistics",
                        "fixture_ids": [1, 2, 3], "updatedAt": "2026-06-08"}
            }
            self.mod._save_output(data)
            loaded = self.mod._load_existing()
            self.assertEqual(loaded, data)

    def test_load_returns_empty_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.mod.OUTPUT_FILE = Path(tmpdir) / "nonexistent.json"
            self.assertEqual(self.mod._load_existing(), {})


class TestStateRegistry(unittest.TestCase):
    """Sanity: state_files_registry.json muss wm_nt_xg.json enthalten."""

    def test_nt_xg_registered_in_fetch_wm_data(self):
        registry_path = REPO / "state_files_registry.json"
        with registry_path.open(encoding="utf-8") as f:
            reg = json.load(f)
        fetch_files = reg["categories"]["fetch_wm_data"]["files"]
        self.assertIn("wm_nt_xg.json", fetch_files)


class TestGenerateWmPicksMerge(unittest.TestCase):
    """Sanity: generate_wm_picks.py liest wm_nt_xg.json und merged es."""

    def test_merge_code_present(self):
        gen_path = REPO / "generate_wm_picks.py"
        src = gen_path.read_text(encoding="utf-8")
        self.assertIn("wm_nt_xg.json", src,
                      "generate_wm_picks.py muss wm_nt_xg.json lesen für NT-xG-Merge")
        self.assertIn("NT-xG", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
