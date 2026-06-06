#!/usr/bin/env python3
"""
test_fetch_wm_poly_prices.py — Alert-Schwellen Regression

Sicherstellt dass ALERT_EDGE_MIN_PP, EDGE_DEDUP_HOURS (inline) und
max_alerts_per_run nach der Config-Migration identisch zu Pre-Refactor sind.

Beide Pipelines (fetch_wm_poly_prices + detect_wm_sharp_moves) senden in den
PRIVATEN TRADES-Channel — Edge-Daten dürfen niemals an die Public CocoBet-2450.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload(profile: str):
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import fetch_wm_poly_prices
    importlib.reload(fetch_wm_poly_prices)
    return fetch_wm_poly_prices


class TestWMProfileMatches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_alert_edge_min_pp(self):
        self.assertEqual(self.mod.ALERT_EDGE_MIN_PP, 5.0)

    def test_delta_window_h_stays_hardcoded(self):
        """DELTA_WINDOW_H bleibt 24 — reine Computation-Konstante."""
        self.assertEqual(self.mod.DELTA_WINDOW_H, 24)

    def test_uses_cfg_helper(self):
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("telegram", "alert_edge_min_pp"', src)
        self.assertIn('_cfg("dedup_hours", "edge_alert"', src)
        self.assertIn('_cfg("telegram", "max_alerts_per_run"', src)

    def test_no_inline_dedup_hardcode(self):
        """EDGE_DEDUP_HOURS = 12 muss raus, ersetzt durch _cfg-Lookup."""
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertNotIn("EDGE_DEDUP_HOURS = 12\n", src,
            "Alter Hardcode EDGE_DEDUP_HOURS = 12 noch im Code")

    def test_no_inline_max_alerts_hardcode(self):
        """[:4] muss durch _max_alerts ersetzt sein."""
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertNotIn("[:4]  # max 4 Alerts pro Run", src)


class TestLigaProfileDiffers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload("wm2026")

    def test_liga_alert_pp_lower(self):
        """Liga: niedrigere Edge-Schwelle (mehr Alerts)."""
        self.assertEqual(self.mod.ALERT_EDGE_MIN_PP, 4.0)


class TestSendsToTradesChannelOnly(unittest.TestCase):
    """KRITISCH: Edge-Alerts NIEMALS an Public Channel."""

    def test_uses_trades_chat_id_not_public(self):
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        # Public CocoBet-Channel-Var darf hier NICHT auftauchen
        self.assertIn("TELEGRAM_TRADES_CHAT_ID", src,
            "Trades-Chat-ID muss verwendet werden")
        # Wenn TELEGRAM_CHAT_ID auftaucht, muss es Privacy-kommentiert sein
        # (vermutlich nicht — wir nutzen nur TRADES)
        for line in src.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "TELEGRAM_CHAT_ID" in stripped and "TRADES" not in stripped:
                # Findet sich der Public-Var-Name in non-Trades-Kontext?
                self.fail(f"Public TELEGRAM_CHAT_ID in non-Trades-Kontext: {stripped}")


if __name__ == "__main__":
    unittest.main()
