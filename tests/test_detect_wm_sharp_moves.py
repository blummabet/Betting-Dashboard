#!/usr/bin/env python3
"""
test_detect_wm_sharp_moves.py — Sharp-Radar Konstanten-Regression

Sicherstellt dass nach Config-Migration die Sharp-Move-Schwellen identisch
zu Pre-Refactor bleiben. Pinnacle-Drift-Alerts gehen an Trades-Channel.
"""
from __future__ import annotations
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


WM_EXPECTED = {
    "ALERT_PP":         5,
    "ALERT_PP_BIG":     10,
    "CUMUL_PP":         8,
    "SNAP_WINDOW_DAYS": 14,
    "MAX_ALERTS":       6,
}


def _reload(profile: str):
    os.environ["COCOBET_PROFILE"] = profile
    import cocobet_config
    importlib.reload(cocobet_config)
    cocobet_config.reload_config()
    import detect_wm_sharp_moves
    importlib.reload(detect_wm_sharp_moves)
    return detect_wm_sharp_moves


class TestWMProfileMatchesHardcodes(unittest.TestCase):
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

    def test_all_constants_unchanged(self):
        for name, expected in WM_EXPECTED.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(self.mod, name), expected,
                    f"{name} hat sich geändert — Pre-Refactor war {expected}")

    def test_uses_cfg_helper(self):
        src = (Path(__file__).parent.parent / "detect_wm_sharp_moves.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import CONFIG as _CFG", src)
        self.assertIn("def _cfg(section: str, key: str, default):", src)
        for cfg_key in ("alert_edge_min_pp", "alert_steam_pp", "alert_cumul_pp",
                        "snap_window_days", "max_sharp_alerts_per_run"):
            with self.subTest(key=cfg_key):
                self.assertIn(f'"{cfg_key}"', src,
                    f"Config-Key '{cfg_key}' wird nicht abgefragt")

    def test_no_old_hardcodes_left(self):
        src = (Path(__file__).parent.parent / "detect_wm_sharp_moves.py").read_text(encoding="utf-8")
        forbidden = [
            "ALERT_PP         = 5",
            "ALERT_PP_BIG     = 10",
            "CUMUL_PP         = 8",
            "SNAP_WINDOW_DAYS = 14",
            "MAX_ALERTS       = 6",
        ]
        for token in forbidden:
            self.assertNotIn(token, src, f"Alter Hardcode noch da: {token}")


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

    def test_liga_more_sensitive(self):
        """Liga: niedrigere Schwellen, mehr Sharp-Alerts (8 statt 6)."""
        self.assertEqual(self.mod.ALERT_PP, 4)
        self.assertEqual(self.mod.ALERT_PP_BIG, 8)
        self.assertEqual(self.mod.CUMUL_PP, 6)
        self.assertEqual(self.mod.MAX_ALERTS, 8)


class TestConfigJsonHasAllKeys(unittest.TestCase):
    REQUIRED_TELEGRAM_KEYS = [
        "max_alerts_per_run", "max_sharp_alerts_per_run",
        "alert_edge_min_pp", "alert_cumul_pp", "alert_steam_pp",
        "snap_window_days",
    ]

    def test_wm2026_has_all_keys(self):
        import json
        cfg = json.loads((Path(__file__).parent.parent / "cocobet_config.json").read_text(encoding="utf-8"))
        tg = cfg["profiles"]["wm2026"]["telegram"]
        for key in self.REQUIRED_TELEGRAM_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, tg)

    def test_liga_default_has_all_keys(self):
        import json
        cfg = json.loads((Path(__file__).parent.parent / "cocobet_config.json").read_text(encoding="utf-8"))
        tg = cfg["profiles"]["liga_default"]["telegram"]
        for key in self.REQUIRED_TELEGRAM_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, tg)


class TestSendsToTradesChannelOnly(unittest.TestCase):
    """KRITISCH: Sharp-Move-Alerts NIEMALS an Public Channel."""

    def test_uses_trades_chat_id(self):
        src = (Path(__file__).parent.parent / "detect_wm_sharp_moves.py").read_text(encoding="utf-8")
        self.assertIn("TELEGRAM_TRADES_CHAT_ID", src)


class TestRadarPinnacleStreamOnly(unittest.TestCase):
    """23.06.2026 (Lucas): Radar mischte public+pinnacle aus derselben History-Liste →
    Phantom-Drift (prev=Pinnacle vs curr=public, opening Pinnacle vs curr public). Fix: nur
    bk!=public verwenden."""

    def setUp(self):
        import detect_wm_sharp_moves as D
        importlib.reload(D)
        self.D = D
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Snapshots innerhalb des Fensters; ts t-3d, t-2d, t-1d
        self.ts = [(now - timedelta(days=d)).isoformat() for d in (3, 2, 1)]

    def _wm(self):
        # Fixture in der Zukunft, sonst überspringt der Radar (angepfiffen/vorbei)
        from datetime import datetime, timezone, timedelta
        ko = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        d = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        return {"groups": {"X": {
            "teams": [{"id": "AAA", "name": "A", "flag": "🅰"},
                      {"id": "BBB", "name": "B", "flag": "🅱"}],
            "fixtures": [{"home": "AAA", "away": "BBB", "kickoff": ko, "date": d}],
        }}, "picks": {}}

    def _hist(self, pinn_dr, pub_dr):
        # interleaved wie in der echten History: je ts ein pinnacle- + ein public-Snap
        snaps = []
        for i, t in enumerate(self.ts):
            snaps.append({"ts": t, "hw": 2.0, "dr": pinn_dr[i], "aw": 4.0, "bk": "pinnacle"})
            snaps.append({"ts": t, "hw": 2.0, "dr": pub_dr[i], "aw": 4.0, "bk": "public"})
        return {"AAA-BBB": snaps}

    def test_flat_pinnacle_no_phantom_from_public(self):
        # Pinnacle flach (3.0), public bewegt stark (3.0→2.3) → NACH Fix kein Move
        moves = self.D.analyze_moves(self._hist([3.0, 3.0, 3.0], [3.0, 2.6, 2.3]),
                                     self._wm(), {})
        self.assertEqual([m for m in moves if m["key"] == "AAA-BBB"], [],
                         "Public-Bewegung darf keinen Sharp-Move auslösen")

    def test_real_pinnacle_move_detected_on_pinnacle_only(self):
        # Pinnacle bewegt real (3.19→2.30 ≈ +12pp kumulativ), public flach
        moves = self.D.analyze_moves(self._hist([3.19, 2.60, 2.30], [3.0, 3.0, 3.0]),
                                     self._wm(), {})
        m = next((x for x in moves if x["key"] == "AAA-BBB"), None)
        self.assertIsNotNone(m, "echter Pinnacle-Move muss erkannt werden")
        self.assertEqual(m["opening_snap"].get("bk"), "pinnacle")
        self.assertEqual(m["curr"].get("bk"), "pinnacle")
        self.assertEqual(m["prev"].get("bk"), "pinnacle")


if __name__ == "__main__":
    unittest.main()
