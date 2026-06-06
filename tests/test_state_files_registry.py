#!/usr/bin/env python3
"""Tests für state_files_registry.py — schützt gegen vergessene State-Files."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import state_files_registry


class TestRegistryStructure(unittest.TestCase):
    """Schema-Tests."""

    def setUp(self):
        self.reg = state_files_registry.load_registry()

    def test_has_categories_key(self):
        self.assertIn("categories", self.reg)

    def test_categories_have_owner_workflow(self):
        for name, cat in self.reg["categories"].items():
            self.assertIn("owner_workflow", cat,
                f"Kategorie '{name}' fehlt owner_workflow")
            self.assertIn("files", cat,
                f"Kategorie '{name}' fehlt files-Liste")

    def test_files_are_strings(self):
        for name, cat in self.reg["categories"].items():
            for f in cat["files"]:
                self.assertIsInstance(f, str,
                    f"File in '{name}' ist kein String: {f!r}")


class TestRegistryContent(unittest.TestCase):
    """Tests gegen Bug-Klassen die heute aufgetreten sind."""

    def test_telegram_log_in_all_relevant_categories(self):
        """telegram-log.json muss bei jedem Workflow der Telegram nutzt drin sein."""
        reg = state_files_registry.load_registry()
        telegram_workflows = ["fetch_wm_data", "daily_wm_story"]
        for wf in telegram_workflows:
            files = reg["categories"][wf]["files"]
            self.assertIn("telegram-log.json", files,
                f"telegram-log.json fehlt in {wf} — UI-Tracking-Bug")

    def test_edge_alert_dedup_in_fetch_wm_data(self):
        """Mein Fix von vorhin: wm_edge_alert_dedup.json MUSS in der Registry."""
        files = state_files_registry.get_files_for_category("fetch_wm_data")
        self.assertIn("wm_edge_alert_dedup.json", files,
            "wm_edge_alert_dedup.json muss in fetch_wm_data sein — sonst kein Dedup nach Push")

    def test_pick_changes_digest_state_in_fetch_wm_data(self):
        files = state_files_registry.get_files_for_category("fetch_wm_data")
        self.assertIn("pick_changes_digest_state.json", files,
            "pick_changes_digest_state.json muss persistiert werden — sonst täglich gleiche Changes")

    def test_position_health_in_manage_wm_poly(self):
        files = state_files_registry.get_files_for_category("manage_wm_poly")
        self.assertIn("position_health.json", files)
        self.assertIn("position_health_alerts.json", files,
            "position_health_alerts.json fehlt → 6h-Dedup für Health-Alerts wirkt nicht")


class TestRegistryApi(unittest.TestCase):
    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            state_files_registry.get_files_for_category("doesnt_exist")

    def test_list_categories_returns_list(self):
        cats = state_files_registry.list_categories()
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0)
        self.assertIn("fetch_wm_data", cats)


if __name__ == "__main__":
    unittest.main()
