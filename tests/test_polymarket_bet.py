#!/usr/bin/env python3
"""
test_polymarket_bet.py — Stake + Bankroll-Limits Regression

KRITISCH: polymarket_bet.py platziert echte USDC-Orders auf Polymarket.
STAKE_USDC + DAILY_BET_CAP + DAILY_STAKE_CAP_USDC + MIN_BALANCE_BUFFER
müssen exakt mit auto_wm_poly_trigger.py übereinstimmen, sonst kann ein Pfad
(manuell) andere Limits haben als der andere (auto). Dieser Test sichert das.
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
    import polymarket_bet
    importlib.reload(polymarket_bet)
    import auto_wm_poly_trigger
    importlib.reload(auto_wm_poly_trigger)
    return polymarket_bet, auto_wm_poly_trigger


class TestWMProfileMatchesHardcodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_stake_usdc(self):
        self.assertEqual(self.pm.STAKE_USDC, 5.5)

    def test_daily_bet_cap(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, 8)

    def test_daily_stake_cap_usdc(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, 50.0)

    def test_min_balance_buffer(self):
        self.assertEqual(self.pm.MIN_BALANCE_BUFFER, 1.0)

    def test_chain_id_stays_hardcoded(self):
        """CHAIN_ID=137 (Polygon) bleibt Netzwerk-Konstante, kein Config-Tuning."""
        self.assertEqual(self.pm.CHAIN_ID, 137)
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        # CHAIN_ID darf NICHT via _cfg geladen werden — falsche Chain = Fehler
        self.assertIn("CHAIN_ID     = 137", src)
        self.assertNotIn('_cfg("trade", "chain_id"', src)


class TestConsistencyWithAutoTrigger(unittest.TestCase):
    """KRITISCH: Manuelle + Auto-Bets müssen IDENTISCHE Limits sehen.
    Sonst könnte z.B. manuell bei 9. Bet noch passieren obwohl Auto bei 8 schon stoppt."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_stake_identical(self):
        self.assertEqual(self.pm.STAKE_USDC, self.at.FLAT_STAKE_USDC,
            "polymarket_bet STAKE_USDC und auto_trigger FLAT_STAKE_USDC müssen gleich sein")

    def test_daily_bet_cap_identical(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, self.at.DAILY_BET_CAP)

    def test_daily_stake_cap_identical(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, self.at.DAILY_STAKE_CAP_USDC)

    def test_min_balance_buffer_identical(self):
        self.assertEqual(self.pm.MIN_BALANCE_BUFFER, self.at.MIN_BALANCE_BUFFER)


class TestSourceClean(unittest.TestCase):
    def test_uses_cfg_helper(self):
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn('_cfg("trade", "stake_usdc_flat"', src)
        self.assertIn('_cfg("trade", "daily_bet_cap"', src)
        self.assertIn('_cfg("trade", "daily_stake_cap_usdc"', src)
        self.assertIn('_cfg("trade", "min_balance_buffer"', src)

    def test_no_old_hardcodes(self):
        src = (Path(__file__).parent.parent / "polymarket_bet.py").read_text(encoding="utf-8")
        forbidden = [
            "STAKE_USDC   = 5.5        # €5",
            "DAILY_BET_CAP        = 8       # max",
            "DAILY_STAKE_CAP_USDC = 50.0    # max",
            "MIN_BALANCE_BUFFER   = 1.0     # USDC die nach",
        ]
        for token in forbidden:
            self.assertNotIn(token, src, f"Alter Hardcode noch da: {token}")


class TestLigaProfileDiffers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.pm, cls.at = _reload("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload("wm2026")

    def test_liga_higher_bet_cap(self):
        self.assertEqual(self.pm.DAILY_BET_CAP, 12)

    def test_liga_higher_stake_cap(self):
        self.assertEqual(self.pm.DAILY_STAKE_CAP_USDC, 80.0)

    def test_liga_stake_unchanged(self):
        """Stake bleibt 5.5 USDC auch im Liga-Mode."""
        self.assertEqual(self.pm.STAKE_USDC, 5.5)


if __name__ == "__main__":
    unittest.main()
