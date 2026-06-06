#!/usr/bin/env python3
"""
test_remaining_python_files.py — Regression-Tests für die letzten 4 Python-Files

Deckt ab:
  · monitor_open_positions.py  (Score-Schwellen + Faktor-Gewichte)
  · steam_lag_monitor.py        (Sell-Trigger + Tier-Klassifikation)
  · telegram_wm.py              (Morning/Recap Edge-Filter)
  · generate_daily_tiktok.py    (TikTok Team-Dedup-Fenster)

Alle WM2026-Werte müssen exakt mit Pre-Refactor übereinstimmen.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload_all(profile: str):
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import monitor_open_positions; importlib.reload(monitor_open_positions)
    import steam_lag_monitor;       importlib.reload(steam_lag_monitor)
    import telegram_wm;             importlib.reload(telegram_wm)
    import generate_daily_tiktok;   importlib.reload(generate_daily_tiktok)
    return (monitor_open_positions, steam_lag_monitor,
            telegram_wm, generate_daily_tiktok)


class TestMonitorOpenPositions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.m, _, _, _ = _reload_all("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_all("wm2026")

    def test_score_thresholds(self):
        self.assertEqual(self.m.SCORE_OK, 80)
        self.assertEqual(self.m.SCORE_WATCH, 60)
        self.assertEqual(self.m.SCORE_WARNING, 40)
        self.assertEqual(self.m.SCORE_CRITICAL, 0)

    def test_factor_weights(self):
        self.assertEqual(self.m.W_EDGE, 30)
        self.assertEqual(self.m.W_PINN, 20)
        self.assertEqual(self.m.W_CLV, 15)
        self.assertEqual(self.m.W_TIME, 5)

    def test_w_total_sum(self):
        """W_TOTAL muss Summe der Einzelgewichte sein — derived, nicht config."""
        self.assertEqual(self.m.W_TOTAL,
                         self.m.W_EDGE + self.m.W_PINN + self.m.W_CLV + self.m.W_TIME)
        self.assertEqual(self.m.W_TOTAL, 70)

    def test_uses_cfg(self):
        src = (Path(__file__).parent.parent / "monitor_open_positions.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("monitor", "score_ok"', src)
        self.assertIn('_cfg("monitor", "w_edge"', src)


class TestSteamLagMonitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        _, cls.s, _, _ = _reload_all("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_all("wm2026")

    def test_sell_thresholds(self):
        self.assertEqual(self.s.SELL_VELOCITY_PP_H, 0.3)
        self.assertEqual(self.s.SELL_EDGE_THRESHOLD, 1.5)
        self.assertEqual(self.s.SELL_MIN_ENTRY_EDGE, 2.5)
        self.assertEqual(self.s.HIGH_CONF_EDGE_MIN, 3.0)

    def test_signal_thresholds(self):
        self.assertEqual(self.s.MIN_EDGE_PP, 1.5)
        self.assertEqual(self.s.SIGNAL_EDGE_PP, 2.0)
        self.assertEqual(self.s.CONVERGED_EDGE_PP, 1.0)
        self.assertEqual(self.s.TRADE_TIER_EDGE_PP, 5.0)

    def test_min_trackable_derived(self):
        """MIN_TRACKABLE_ENTRY = CONVERGED + 1.0 — derived."""
        self.assertEqual(self.s.MIN_TRACKABLE_ENTRY, self.s.CONVERGED_EDGE_PP + 1.0)
        self.assertEqual(self.s.MIN_TRACKABLE_ENTRY, 2.0)

    def test_log_limits(self):
        self.assertEqual(self.s.MAX_SNAPSHOTS, 50)
        self.assertEqual(self.s.SIGNAL_TTL_DAYS, 30)

    def test_trade_tier_matches_auto_trigger(self):
        """TRADE_TIER_EDGE_PP muss zu AUTO_TRIGGER_EDGE_PP passen (=5.0).
        Auto-Trigger schiesst bei 4.0 los — Tracking-Tier liegt bei 5.0 bewusst
        höher, damit nur die wirklich getradeten Signale auch im trade-Tier sind."""
        import auto_wm_poly_trigger
        # Memory: AUTO_TRIGGER_EDGE_PP wurde auf 4.0 gesenkt, aber Steam-TRADE_TIER
        # bleibt bei 5.0 als analytischer Schwellenwert. Klar dokumentiert.
        self.assertEqual(self.s.TRADE_TIER_EDGE_PP, 5.0)
        self.assertEqual(auto_wm_poly_trigger.AUTO_TRIGGER_EDGE_PP, 4.0)

    def test_classify_entry_tier_works(self):
        """Funktionaler Check der Tier-Klassifikation."""
        self.assertEqual(self.s._classify_entry_tier(6.0, False), "trade")
        self.assertEqual(self.s._classify_entry_tier(3.0, False), "track")
        self.assertEqual(self.s._classify_entry_tier(1.0, False), "sub_threshold")

    def test_uses_cfg(self):
        src = (Path(__file__).parent.parent / "steam_lag_monitor.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("steam", "trade_tier_edge_pp"', src)


class TestTelegramWM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        _, _, cls.t, _ = _reload_all("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_all("wm2026")

    def test_edge_filters(self):
        self.assertEqual(self.t.MIN_BET_EDGE, 4)
        self.assertEqual(self.t.MIN_ABW_EDGE, 4)

    def test_uses_cfg(self):
        src = (Path(__file__).parent.parent / "telegram_wm.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("telegram", "min_bet_edge_pp"', src)


class TestGenerateDailyTiktok(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        _, _, _, cls.d = _reload_all("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_all("wm2026")

    def test_dedup_window(self):
        self.assertEqual(self.d.DEDUP_WINDOW_DAYS, 7)

    def test_uses_cfg(self):
        src = (Path(__file__).parent.parent / "generate_daily_tiktok.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("tiktok", "dedup_window_days"', src)


class TestLigaProfileDiffers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.m, cls.s, cls.t, cls.d = _reload_all("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_all("wm2026")

    def test_monitor_more_sensitive(self):
        """Liga: niedrigere Score-Schwellen (mehr Alerts)."""
        self.assertEqual(self.m.SCORE_OK, 75)
        self.assertEqual(self.m.SCORE_WATCH, 55)

    def test_steam_more_sensitive(self):
        """Liga: niedrigere Edge-Schwellen + niedriger Trade-Tier."""
        self.assertEqual(self.s.SIGNAL_EDGE_PP, 1.8)
        self.assertEqual(self.s.TRADE_TIER_EDGE_PP, 4.0)

    def test_telegram_more_picks(self):
        """Liga: niedrigerer Edge-Cutoff für Picks (3 statt 4)."""
        self.assertEqual(self.t.MIN_BET_EDGE, 3)
        self.assertEqual(self.t.MIN_ABW_EDGE, 3)

    def test_tiktok_shorter_dedup(self):
        """Liga: 5 Tage Team-Dedup (kürzer da mehr Spiele)."""
        self.assertEqual(self.d.DEDUP_WINDOW_DAYS, 5)


class TestConfigJsonHasAllKeys(unittest.TestCase):
    REQUIRED = {
        "monitor": ["score_ok", "score_watch", "score_warning", "score_critical",
                    "w_edge", "w_pinn", "w_clv", "w_time"],
        "steam": ["sell_velocity_pp_h", "sell_edge_threshold", "sell_min_entry_edge",
                  "high_conf_edge_min", "min_edge_pp", "signal_edge_pp",
                  "converged_edge_pp", "trade_tier_edge_pp",
                  "max_snapshots", "signal_ttl_days"],
        "tiktok": ["dedup_window_days"],
    }
    REQUIRED_TELEGRAM = ["min_bet_edge_pp", "min_abw_edge_pp"]

    def _load_cfg(self):
        import json
        return json.loads((Path(__file__).parent.parent / "cocobet_config.json").read_text(encoding="utf-8"))

    def test_wm2026_has_all_sections(self):
        cfg = self._load_cfg()
        for section, keys in self.REQUIRED.items():
            with self.subTest(section=section):
                self.assertIn(section, cfg["profiles"]["wm2026"])
                for key in keys:
                    self.assertIn(key, cfg["profiles"]["wm2026"][section])

    def test_wm2026_telegram_extended(self):
        cfg = self._load_cfg()
        for key in self.REQUIRED_TELEGRAM:
            with self.subTest(key=key):
                self.assertIn(key, cfg["profiles"]["wm2026"]["telegram"])

    def test_liga_default_has_all_sections(self):
        cfg = self._load_cfg()
        for section, keys in self.REQUIRED.items():
            with self.subTest(section=section):
                self.assertIn(section, cfg["profiles"]["liga_default"])
                for key in keys:
                    self.assertIn(key, cfg["profiles"]["liga_default"][section])


if __name__ == "__main__":
    unittest.main()
