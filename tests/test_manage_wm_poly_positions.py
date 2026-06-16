#!/usr/bin/env python3
"""
test_manage_wm_poly_positions.py — Sell-Pipeline Konstanten-Regression

Sicherstellt dass die Migration der Sell/Loss-Trigger-Konstanten von Hardcode
auf cocobet_config.json KEINE Werte-Änderung verursacht. Diese Schwellen
steuern reale Sell-Entscheidungen auf Polymarket (echtes USDC, live).

WM2026 muss alle Pre-Refactor-Werte exakt liefern.
AUTO_SELL_ENABLED bleibt bewusst Hardcode (Safety-Schalter) — Test prüft das.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Pre-Refactor-Hardcodes (Source of Truth für WM2026)
WM_EXPECTED = {
    "PROFIT_TARGET":           0.10,
    "PINN_GAP_PP":             1.5,
    "MIN_PROFIT_PP":           0.03,
    "AGE_DECAY_HOURS":         48,
    "AGE_DECAY_PROFIT_TARGET": 0.05,
    "SHARP_AGAINST_GAP_PP":    7.0,
    "LOSS_DEEP_PCT":           0.40,
    "LOSS_DEEP_HOURS_AHEAD":   12.0,
    "AGE_LOSS_HOURS":          36.0,
    "AGE_LOSS_THRESHOLD_PCT":  0.10,
    "NO_INPLAY_LOSS_SELL":     True,
    "PRE_MATCH_CLOSE_HOURS":   2,
}


def _reload_with_profile(profile: str):
    """Forciert Re-Load von cocobet_config + manage_wm_poly_positions."""
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import manage_wm_poly_positions
    importlib.reload(manage_wm_poly_positions)
    return manage_wm_poly_positions


class TestWMProfileMatchesHardcodes(unittest.TestCase):
    """KRITISCH: WM2026-Profil muss exakt Pre-Refactor-Werte liefern."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload_with_profile("wm2026")

    @classmethod
    def tearDownClass(cls):
        if cls.original_profile is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = cls.original_profile

    def test_all_constants_unchanged(self):
        for name, expected in WM_EXPECTED.items():
            with self.subTest(constant=name):
                actual = getattr(self.mod, name)
                self.assertEqual(actual, expected,
                    f"{name} weicht ab: code-default war {expected}, ist jetzt {actual}")

    def test_auto_sell_safety_flag_stays_false(self):
        """KRITISCH: AUTO_SELL_ENABLED muss IMMER False per Default sein.
        Verhindert versehentliches Live-Trading durch Config-Tippfehler."""
        self.assertFalse(self.mod.AUTO_SELL_ENABLED,
            "AUTO_SELL_ENABLED MUSS False bleiben (Safety-Master-Switch)")

    def test_uses_cfg_helper(self):
        """Module muss _cfg() Helper benutzen."""
        src = (Path(__file__).parent.parent / "manage_wm_poly_positions.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn("def _cfg(section: str, key: str, default):", src)
        self.assertIn('_cfg("sell", "profit_target"', src)
        self.assertIn('_cfg("sell", "sharp_against_gap_pp"', src)
        self.assertIn('_cfg("trade", "pre_match_close_hours"', src)

    def test_no_old_hardcodes_left(self):
        """Alte Hardcode-Zuweisungen sind raus."""
        src = (Path(__file__).parent.parent / "manage_wm_poly_positions.py").read_text(encoding="utf-8")
        forbidden = [
            "PROFIT_TARGET   = 0.10",
            "PINN_GAP_PP     = 1.5",
            "SHARP_AGAINST_GAP_PP    = 7.0",
            "LOSS_DEEP_PCT           = 0.40",
            "AGE_LOSS_HOURS          = 36.0",
            "NO_INPLAY_LOSS_SELL     = True",
        ]
        for token in forbidden:
            self.assertNotIn(token, src,
                f"Alter Hardcode noch im Code: '{token}'")

    def test_auto_sell_stays_hardcoded(self):
        """AUTO_SELL_ENABLED ist hardcoded, nicht via _cfg (Safety-Regel)."""
        src = (Path(__file__).parent.parent / "manage_wm_poly_positions.py").read_text(encoding="utf-8")
        self.assertIn("AUTO_SELL_ENABLED     = False", src,
            "AUTO_SELL_ENABLED muss als Hardcode-Literal stehen, nicht via _cfg")
        # Verifizieren: kein _cfg-Lookup für auto_sell_enabled
        self.assertNotIn('_cfg("sell", "auto_sell_enabled"', src,
            "AUTO_SELL_ENABLED darf NICHT via Config überschrieben werden")


class TestLigaProfileDiffers(unittest.TestCase):
    """Sanity: Liga-Profil liefert eigene (etwas aggressivere) Werte."""

    @classmethod
    def setUpClass(cls):
        cls.original_profile = os.environ.get("COCOBET_PROFILE")
        cls.mod = _reload_with_profile("liga_default")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("COCOBET_PROFILE", None)
        if cls.original_profile:
            os.environ["COCOBET_PROFILE"] = cls.original_profile
        _reload_with_profile("wm2026")

    def test_liga_has_lower_profit_target(self):
        """Liga nimmt früher Profit (0.08 statt 0.10)."""
        self.assertEqual(self.mod.PROFIT_TARGET, 0.08)

    def test_liga_has_shorter_age_decay(self):
        """Liga: Age-Decay schon nach 36h statt 48h."""
        self.assertEqual(self.mod.AGE_DECAY_HOURS, 36)

    def test_liga_pre_match_close_unchanged_for_liga(self):
        """Liga: pre_match_close_hours=1 (kommt aus trade-Section)."""
        self.assertEqual(self.mod.PRE_MATCH_CLOSE_HOURS, 1)

    def test_liga_auto_sell_still_off(self):
        """AUTO_SELL_ENABLED bleibt False auch bei Liga (Hardcode)."""
        self.assertFalse(self.mod.AUTO_SELL_ENABLED)


class TestConfigJsonHasAllSellKeys(unittest.TestCase):
    """cocobet_config.json muss alle vom Code abgefragten Sell-Keys enthalten."""

    REQUIRED_SELL_KEYS = [
        "profit_target", "pinn_gap_pp", "min_profit_pp",
        "age_decay_hours", "age_decay_profit_target",
        "sharp_against_gap_pp", "loss_deep_pct", "loss_deep_hours_ahead",
        "age_loss_hours", "age_loss_threshold_pct",
        "no_inplay_loss_sell",
    ]

    def test_wm2026_has_all_keys(self):
        import json
        cfg_path = Path(__file__).parent.parent / "cocobet_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        sell = cfg["profiles"]["wm2026"]["sell"]
        for key in self.REQUIRED_SELL_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, sell, f"WM2026 sell-section fehlt Key '{key}'")

    def test_liga_default_has_all_keys(self):
        import json
        cfg_path = Path(__file__).parent.parent / "cocobet_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        sell = cfg["profiles"]["liga_default"]["sell"]
        for key in self.REQUIRED_SELL_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, sell, f"liga_default sell-section fehlt Key '{key}'")

    def test_default_fallback_has_sell_section(self):
        """DEFAULT_FALLBACK in cocobet_config.py muss sell-Section haben."""
        from cocobet_config import DEFAULT_FALLBACK
        self.assertIn("sell", DEFAULT_FALLBACK)
        for key in self.REQUIRED_SELL_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, DEFAULT_FALLBACK["sell"])


class TestFunctionsStillWork(unittest.TestCase):
    """Smoketest: hours_until_match noch funktional, MARKET_TO_PRICE_KEY intakt."""

    def test_market_to_price_key_unchanged(self):
        import manage_wm_poly_positions as m
        importlib.reload(m)
        self.assertEqual(m.MARKET_TO_PRICE_KEY["Heimsieg"], "hw")
        self.assertEqual(m.MARKET_TO_PRICE_KEY["Over 2.5 Tore"], "o25")

    def test_hours_until_match_works(self):
        from manage_wm_poly_positions import hours_until_match
        # Past date
        result = hours_until_match("2020-01-01T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertLess(result, 0)
        # Empty
        self.assertIsNone(hours_until_match(""))


class TestAutoSourceClassifier(unittest.TestCase):
    """FIX 15.06.2026: auto_steam (Steam-Lag) muss als Auto gelten.
    Vorher exakter ==-Vergleich → Telegram 'MANUELLER BET' + kein Auto-Sell."""

    def test_auto_and_auto_steam_are_auto(self):
        from telegram_trades import is_auto_source
        self.assertTrue(is_auto_source("auto"))
        self.assertTrue(is_auto_source("auto_steam"))   # Steam-Lag = der NED-TUN-Fall
        self.assertTrue(is_auto_source("auto_ah"))       # zukünftige auto_*-Variante

    def test_manual_and_empty_are_not_auto(self):
        from telegram_trades import is_auto_source
        self.assertFalse(is_auto_source("manual"))
        self.assertFalse(is_auto_source(""))
        self.assertFalse(is_auto_source(None))

    def test_manage_uses_same_classifier(self):
        import manage_wm_poly_positions as mm
        self.assertTrue(mm.is_auto_source("auto_steam"))

    def test_telegram_label_for_auto_steam(self):
        import telegram_trades as t
        sent = {}
        orig = t.send_trades_message
        t.send_trades_message = lambda text: sent.setdefault("text", text) or True
        try:
            t.notify_trade_opened(
                home="Niederlande", away="Tunesien", market="Under 2.5 Tore",
                stake=5.5, poly_price=0.42, source="auto_steam",
            )
        finally:
            t.send_trades_message = orig
        self.assertIn("AUTO-BET", sent["text"])
        self.assertNotIn("MANUELLER", sent["text"])


class TestAhBttsValuation(unittest.TestCase):
    """FIX 16.06.2026 (Geld-Bug): AH/BTTS-Positionen über den exakten Token bewerten,
    NICHT über den Moneyline-Fallback 'hw'. USA-AUS 'AH Heim -1.5' wurde mit der
    Heimsieg-Quote (0.615) statt dem AH-Token (0.345) bewertet → Schein-+80% → Fehl-Sell."""

    def setUp(self):
        import json, tempfile
        import manage_wm_poly_positions as m
        self.m = m
        cache = {"allFixtures": [{
            "homeId": "USA", "awayId": "AUS",
            "poly_hw": 0.615,                       # Moneyline (FALSCHE Quelle)
            "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.345,
                          "tokens": ["AHTOK_YES", "AHTOK_NO"]}],
            "poly_btts": 0.46, "poly_btts_no": 0.54,
            "poly_btts_tokens": ["BTTSYES", "BTTSNO"],
        }]}
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(cache, self.tmp); self.tmp.close()
        self._orig = m.PRICES_FILE
        m.PRICES_FILE = self.tmp.name

    def tearDown(self):
        import os
        self.m.PRICES_FILE = self._orig
        os.unlink(self.tmp.name)

    def _pos(self, market, token):
        return {"market": market, "tokenId": token, "homeId": "USA", "awayId": "AUS",
                "entryPrice": 0.335, "priceKey": None, "placedAt": "2026-06-16T09:00:00Z",
                "matchDate": "2026-06-19"}

    def test_ah_uses_token_price_not_moneyline(self):
        pos = self.m.check_position(self._pos("AH Heim -1.5", "AHTOK_YES"))
        self.assertEqual(pos["currentPrice"], 0.345)   # AH-Token, NICHT 0.615
        self.assertLess(pos["pnlPct"], 10)             # kein +80% Schein-Profit
        self.assertFalse(pos.get("sellSignal"))

    def test_btts_yes_uses_btts_price(self):
        pos = self.m.check_position(self._pos("Beide Teams treffen — Ja", "BTTSYES"))
        self.assertEqual(pos["currentPrice"], 0.46)

    def test_btts_no_uses_no_price(self):
        pos = self.m.check_position(self._pos("Beide Teams treffen — Nein", "BTTSNO"))
        self.assertEqual(pos["currentPrice"], 0.54)

    def test_unknown_token_no_sell(self):
        pos = self.m.check_position(self._pos("AH Heim -1.5", "GIBTSNICHT"))
        self.assertIsNone(pos["currentPrice"])
        self.assertFalse(pos.get("sellSignal"))


if __name__ == "__main__":
    unittest.main()
