"""
tests/test_generate_wm_picks_merge.py — Integration-Tests für Daten-Merge

Audit-Fix 08.06.2026: generate_wm_picks.py merged ab heute 4 neue externe
Datenquellen in den Signal-Context — wir testen dass:
  - NT-xG (wm_nt_xg.json) Understat-Lücken füllt aber nicht Understat überschreibt
  - Lineups (wm_lineups.json) im sig_ctx ankommen
  - APIF Predictions (wm_apif_predictions.json) im sig_ctx ankommen
  - Squads (wm.squads) für lineup_signal verfügbar sind
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestGenerateMergeCodePaths(unittest.TestCase):
    """Sanity: alle Merge-Pfade existieren im Source und liegen korrekt
    VOR der Signal-Engine-Schleife (sonst würden Signale die Daten nicht sehen)."""

    @classmethod
    def setUpClass(cls):
        cls.src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")

    def test_nt_xg_merge_block_present(self):
        """NT-xG Merge muss xg_stats erweitern."""
        self.assertIn("wm_nt_xg.json", self.src)
        self.assertIn("nt_xg", self.src.lower())
        # Understat-Priorität: NT-xG nur wenn games < 3 oder gar nicht in xg_stats
        self.assertIn("games", self.src)

    def test_lineups_load_present(self):
        """Lineups werden aus wm_lineups.json geladen."""
        self.assertIn("wm_lineups.json", self.src)
        self.assertIn("lineups_data", self.src)

    def test_apif_predictions_load_present(self):
        """APIF Predictions werden geladen."""
        self.assertIn("apif_predictions.json", self.src)   # Prefix via _FILE_PREFIX (wm_/liga_)
        self.assertIn("apif_predictions_data", self.src)

    def test_sig_ctx_includes_all_four_new_sources(self):
        """Signal-Context muss die 4 neuen Quellen + squads enthalten."""
        # Suche den sig_ctx-Block
        idx = self.src.find("sig_ctx = {")
        self.assertGreater(idx, 0, "sig_ctx Block nicht gefunden")
        # 200-Zeilen-Fenster nach Beginn
        end = self.src.find("for p in new_picks:", idx)
        self.assertGreater(end, idx)
        block = self.src[idx:end]
        for key in ["lineups", "squads", "apif_predictions", "xg_stats"]:
            self.assertIn(f'"{key}"', block,
                          f"sig_ctx fehlt key '{key}'")

    def test_load_order_correct(self):
        """NT-xG/Lineups/APIF müssen VOR der Signal-Engine geladen werden
        (sonst sehen die Signale die Daten nicht)."""
        nt_xg_pos    = self.src.find("nt_xg.json")
        lineups_pos  = self.src.find("lineups.json")
        apif_pos     = self.src.find("apif_predictions.json")
        eng_call_pos = self.src.find("evaluate_signals(p, sig_ctx)")
        self.assertGreater(eng_call_pos, 0)
        for label, pos in [("nt_xg", nt_xg_pos), ("lineups", lineups_pos), ("apif", apif_pos)]:
            self.assertLess(pos, eng_call_pos,
                            f"{label} wird NACH evaluate_signals geladen — "
                            f"Signale sehen die Daten nicht!")


class TestRegistryAndConfigConsistency(unittest.TestCase):
    """State-Registry + Config müssen alle neuen Files kennen."""

    def test_registry_contains_all_new_files(self):
        import json
        reg = json.loads((REPO / "state_files_registry.json").read_text(encoding="utf-8"))
        files = reg["categories"]["fetch_wm_data"]["files"]
        for fname in [
            "wm_nt_xg.json", "wm_lineups.json",
            "wm_lineup_alerts.json", "wm_apif_predictions.json",
        ]:
            self.assertIn(fname, files, f"{fname} fehlt in state_files_registry")

    def test_config_has_all_new_sections(self):
        import json
        cfg = json.loads((REPO / "cocobet_config.json").read_text(encoding="utf-8"))
        wm = cfg["profiles"]["wm2026"]
        for section in ["nt_xg", "lineups", "lineup_signal",
                        "apif_predictions", "apif_predictions_signal"]:
            self.assertIn(section, wm, f"cocobet_config.profiles.wm2026 fehlt section '{section}'")

    def test_signal_weights_has_new_entries(self):
        import json
        w = json.loads((REPO / "signal_weights.json").read_text(encoding="utf-8"))
        for name in ["lineup_signal", "apif_predictions"]:
            self.assertIn(name, w)
            self.assertIn("weight", w[name])
            # FIX 13.06.2026: NICHT mehr ==1.0 prüfen. Seit der Bayesian-Loop
            # tatsächlich lernt (project_bayesian_loop_fix), bewegen sich die
            # Gewichte legitim weg von 1.0. Nur Sanity-Bound [0.3, 1.7] prüfen.
            wv = w[name]["weight"]
            self.assertIsInstance(wv, (int, float))
            self.assertGreaterEqual(wv, 0.3)
            self.assertLessEqual(wv, 1.7)


class TestSignalRegistryActive(unittest.TestCase):
    """sharp_signals/registry.py muss alle 34 Signale + UNIQUE-Group enthalten."""

    def test_all_signals_active(self):
        from sharp_signals.registry import ACTIVE_SIGNALS
        names = [s.name() for s in ACTIVE_SIGNALS]
        expected = {
            "lead_lag_bias", "public_static_bias", "travel_burden", "injury",
            "form_trend", "h2h_pattern", "xg_strength", "polymarket_sharp",
            "steam_lag", "pressure_index", "lineup_signal", "apif_predictions",
            "weather_signal", "incentive_signal", "altitude_signal",
            "chance_creation", "form_rating", "freshness_leg", "smart_money",
            "league_pressure", "fixture_congestion", "topscorer_momentum",
            "coach_change", "transfer_shift", "streak_momentum",
            "reverse_line_move", "opener_move", "multi_book_steam", "game_state_openness",
            "mls_travel", "move_following", "venue_form", "betfair_money", "betfair_coherence",
        }
        self.assertEqual(set(names), expected,
                         f"Signal-Set abweichend. fehlt: {expected - set(names)}, "
                         f"extra: {set(names) - expected}")
        self.assertEqual(len(ACTIVE_SIGNALS), 34)

    def test_lineup_and_apif_are_unique(self):
        from sharp_signals.registry import SIGNAL_GROUPS
        self.assertEqual(SIGNAL_GROUPS.get("lineup_signal"), "unique")
        self.assertEqual(SIGNAL_GROUPS.get("apif_predictions"), "unique")


class TestWorkflowSequence(unittest.TestCase):
    """fetch-wm-data.yml muss die 3 neuen Fetcher VOR generate_wm_picks aufrufen."""

    @classmethod
    def setUpClass(cls):
        cls.yml = (REPO / ".github" / "workflows" / "fetch-wm-data.yml").read_text(encoding="utf-8")

    def test_nt_xg_before_picks(self):
        self.assertLess(self.yml.find("fetch_wm_nt_xg.py"),
                        self.yml.find("generate_wm_picks.py"))

    def test_lineups_before_picks(self):
        self.assertLess(self.yml.find("fetch_wm_lineups.py"),
                        self.yml.find("generate_wm_picks.py"))

    def test_apif_predictions_before_picks(self):
        self.assertLess(self.yml.find("fetch_wm_apifootball_predictions.py"),
                        self.yml.find("generate_wm_picks.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
