#!/usr/bin/env python3
"""Tests für cocobet_config.py — Config-Loader + Profile-Switch."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cocobet_config


class TestConfigLoading(unittest.TestCase):
    """Validiert dass Config korrekt lädt."""

    def test_active_profile_default_is_wm2026(self):
        # Bei sauberem ENV ist WM-Profile aktiv
        if "COCOBET_PROFILE" in os.environ:
            self.skipTest("ENV-Override gesetzt")
        cocobet_config.reload_config()
        # Pre-Tournament-Schwelle ist nur in WM-Profile > 0
        self.assertGreater(cocobet_config.CONFIG["trade"]["pre_tournament_edge_pp"], 0)

    def test_all_required_sections_present(self):
        """Alle Pflicht-Sections sind nach Merge mit Default vorhanden."""
        required = ["edge", "odds", "underdog", "trade", "dedup_hours", "telegram"]
        for s in required:
            self.assertIn(s, cocobet_config.CONFIG,
                f"Section '{s}' fehlt in Config")

    def test_get_config_dotted_path(self):
        val = cocobet_config.get_config("trade.pre_match_close_hours")
        self.assertIsInstance(val, (int, float))
        self.assertGreater(val, 0)

    def test_get_config_invalid_path_returns_default(self):
        val = cocobet_config.get_config("foo.bar.baz", default="DEFAULT")
        self.assertEqual(val, "DEFAULT")

    def test_get_config_invalid_path_no_default_returns_none(self):
        val = cocobet_config.get_config("foo.bar.baz")
        self.assertIsNone(val)


class TestProfileSwitching(unittest.TestCase):
    """Profile-Wechsel zur Laufzeit."""

    def setUp(self):
        self._original_env = os.environ.get("COCOBET_PROFILE")

    def tearDown(self):
        if self._original_env is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = self._original_env
        cocobet_config.reload_config()

    def test_env_override_switches_to_liga(self):
        os.environ["COCOBET_PROFILE"] = "liga_default"
        cocobet_config.reload_config()
        # Liga hat keine Pre-Tournament-Phase
        self.assertEqual(cocobet_config.CONFIG["trade"]["pre_tournament_edge_pp"], 0)

    def test_env_override_switches_to_wm(self):
        os.environ["COCOBET_PROFILE"] = "wm2026"
        cocobet_config.reload_config()
        # WM hat Pre-Tournament-Phase
        self.assertGreater(cocobet_config.CONFIG["trade"]["pre_tournament_edge_pp"], 0)

    def test_unknown_profile_falls_back(self):
        os.environ["COCOBET_PROFILE"] = "doesnt_exist"
        cocobet_config.reload_config()
        # Fallback liefert Default-Werte
        self.assertIn("edge", cocobet_config.CONFIG)
        self.assertIn("trade", cocobet_config.CONFIG)


class TestProfileDifferences(unittest.TestCase):
    """Validiert dass WM- und Liga-Profile inhaltlich unterschiedlich sind."""

    def setUp(self):
        self._original_env = os.environ.get("COCOBET_PROFILE")

    def tearDown(self):
        if self._original_env is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = self._original_env
        cocobet_config.reload_config()

    def test_wm_is_more_restrictive_than_liga(self):
        """WM 1X2-BET-Schwelle ≥ Liga 1X2-BET-Schwelle (WM konservativer)."""
        os.environ["COCOBET_PROFILE"] = "wm2026"
        cocobet_config.reload_config()
        wm_bet = cocobet_config.CONFIG["edge"]["bet_threshold_1x2"]

        os.environ["COCOBET_PROFILE"] = "liga_default"
        cocobet_config.reload_config()
        liga_bet = cocobet_config.CONFIG["edge"]["bet_threshold_1x2"]

        self.assertGreaterEqual(wm_bet, liga_bet,
            f"WM bet-threshold ({wm_bet}) soll restriktiver sein als Liga ({liga_bet})")


class TestRawJsonValid(unittest.TestCase):
    """Validiert dass cocobet_config.json valides JSON ist."""

    def test_json_is_valid(self):
        path = Path(__file__).parent.parent / "cocobet_config.json"
        if not path.exists():
            self.skipTest("cocobet_config.json fehlt")
        with open(path) as f:
            data = json.load(f)
        self.assertIn("profiles", data)
        self.assertIn("active", data["profiles"])

    def test_active_profile_exists_in_profiles(self):
        path = Path(__file__).parent.parent / "cocobet_config.json"
        if not path.exists():
            self.skipTest("cocobet_config.json fehlt")
        with open(path) as f:
            data = json.load(f)
        active = data["profiles"]["active"]
        self.assertIn(active, data["profiles"],
            f"Active profile '{active}' nicht in profiles definiert")



class TestPlayerStatsPerProfile(unittest.TestCase):
    """25.07.2026 (Lucas: „mit vergangenen Spielen lernen"): keyPasses + minutengewichtetes
    Spieler-Rating kommen aus /fixtures/players und speisen chance_creation + form_rating —
    UND deren Lern-Loop: ohne die Felder feuern beide Signale nie, sammeln nie Beobachtungen
    und koennen nie Gewicht verdienen. Fuer MLS war nt_xg.fetch_player_stats=false → beide
    Signale dauerhaft tot (keyPassesForAvg/ratingAvg = null fuer alle Teams).

    Geprueft wird der AUFGELOESTE CFG, den aggregate_team_stats real nutzt
    (fetch_wm_nt_xg._load_cfg ueber den Profil-Merge), nicht der JSON-Wortlaut — im Subprozess,
    weil CFG ein Modul-Singleton ist (Import-Zeitpunkt) und ENV die Suite sonst verschmutzt.
    liga_default bleibt bewusst aus (eigene Quota-Entscheidung, separat zu treffen)."""

    def _resolved(self, profile: str) -> str:
        repo = Path(__file__).parent.parent
        r = subprocess.run(
            [sys.executable, "-c",
             "import fetch_wm_nt_xg as N; print(N.CFG['fetch_player_stats'])"],
            cwd=repo, capture_output=True, text=True, timeout=90,
            env={**os.environ, "COCOBET_PROFILE": profile})
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        return r.stdout.strip()

    def test_mls_zieht_spielerstats(self):
        self.assertEqual(self._resolved("mls_default"), "True",
            "MLS muss /fixtures/players ziehen — sonst bleiben chance_creation + form_rating tot")

    def test_wm_zieht_spielerstats(self):
        self.assertEqual(self._resolved("wm2026"), "True")


if __name__ == "__main__":
    unittest.main()
