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

    def test_1x2_edge_hat_plausibilitaets_guard(self):
        """19.07.2026 — Platzhalter-Quoten (Remis 1.01 / Auswärts 1.04) dürfen KEINE Edge erzeugen.
        Der Telegram-Alert meldete Fake-Edges von +13-17pp aus solchen Platzhaltern. Der 1X2-
        Edge-Block MUSS über plausible_1x2 gegatet sein (dieselbe Bug-Klasse wie die Geister-Moves)."""
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertIn("from odds_plausibility import", src)
        # Kanonische gegatete De-Vig statt roher Marge: implausibel → None → keine Edge.
        self.assertIn("devig_1x2(pinn_hw, pinn_dr, pinn_aw)", src,
            "1X2-Edge-Berechnung nicht gegen Platzhalter-Quoten gegatet")

    def test_die_gemeldeten_platzhalter_sind_implausibel(self):
        """Genau die Quoten aus Lucas' Alerts müssen als implausibel erkannt werden."""
        from odds_plausibility import plausible_1x2
        self.assertFalse(plausible_1x2(2.0, 3.5, 1.04))   # Houston: Auswärts 1.04
        self.assertFalse(plausible_1x2(2.0, 1.01, 3.5))   # San Jose: Remis 1.01
        self.assertTrue(plausible_1x2(2.10, 3.40, 3.30))  # echte MLS-Quote bleibt

    def test_alert_label_datensatz_aware(self):
        """Alerts liefen unter „WM Edge Alert" auch für MLS-Spiele → Label muss aus dem Datensatz kommen."""
        src = (Path(__file__).parent.parent / "fetch_wm_poly_prices.py").read_text(encoding="utf-8")
        self.assertNotIn("<b>WM Edge Alert", src, "hartes WM-Label noch drin")
        self.assertIn("_ds_label", src)


class TestPolyMirrorNormalization(unittest.TestCase):
    """Regression: Polymarket-Spiegel (Heim/Auswärts vertauscht, SUI-CAN statt
    CAN-SUI) → poly landete unter Phantom-Key, echtes Fixture leer (84 statt 72
    odds-keys). _flip_poly_orientation dreht auf Fixture-Reihenfolge."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _reload("wm2026")

    def test_flip_swaps_home_away_keeps_symmetric(self):
        p = {"homeId": "SUI", "awayId": "CAN", "homeName": "Schweiz", "awayName": "Kanada",
             "hw": 0.55, "aw": 0.25, "dr": 0.20, "hwTokens": ["a"], "awTokens": ["b"],
             "poly_o25": 0.6, "poly_btts": 0.5}
        q = self.mod._flip_poly_orientation(p)
        self.assertEqual(q["homeId"], "CAN")
        self.assertEqual(q["awayId"], "SUI")
        self.assertEqual(q["hw"], 0.25)   # CAN-Sieg = vorher SUI-aw
        self.assertEqual(q["aw"], 0.55)   # SUI-Sieg = vorher SUI-hw
        self.assertEqual(q["hwTokens"], ["b"])
        self.assertEqual(q["awTokens"], ["a"])
        self.assertEqual(q["dr"], 0.20)        # symmetrisch bleibt
        self.assertEqual(q["poly_o25"], 0.6)   # symmetrisch bleibt
        self.assertEqual(q["poly_btts"], 0.5)

    def test_mirror_renormalizes_to_real_key(self):
        real = {"CAN-SUI"}
        prices = {"SUI-CAN": {"homeId": "SUI", "awayId": "CAN", "hw": 0.55, "aw": 0.25, "dr": 0.2}}
        norm = {}
        for k, p in prices.items():
            rk = f"{p.get('awayId')}-{p.get('homeId')}"
            if k not in real and rk in real:
                p = self.mod._flip_poly_orientation(p); k = rk
            norm[k] = p
        self.assertIn("CAN-SUI", norm)
        self.assertNotIn("SUI-CAN", norm)
        self.assertEqual(norm["CAN-SUI"]["hw"], 0.25)


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
