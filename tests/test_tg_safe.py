#!/usr/bin/env python3
"""test_tg_safe.py — Telegram-sichere Flaggen (25.07.2026).
Sichert, dass <img>-Klub-Logos zu ⚽ werden (sonst HTTP 400) und WM-Emoji durchlaufen."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tg_safe import safe_flag


class TestSafeFlag(unittest.TestCase):
    def test_img_logo_becomes_ball(self):
        self.assertEqual(safe_flag('<img src="https://x/1.png">'), "⚽")

    def test_emoji_passthrough(self):
        self.assertEqual(safe_flag("🇪🇸"), "🇪🇸")
        self.assertEqual(safe_flag("🏳"), "🏳")

    def test_empty_and_none(self):
        self.assertEqual(safe_flag(""), "⚽")
        self.assertEqual(safe_flag(None), "⚽")

    def test_custom_fallback(self):
        self.assertEqual(safe_flag("<img>", fallback=""), "")

    def test_any_angle_bracket_is_unsafe(self):
        self.assertEqual(safe_flag("<b>x</b>"), "⚽")


if __name__ == "__main__":
    unittest.main()
