#!/usr/bin/env python3
"""
test_preseason_dedup.py — Defense-in-Depth Dedup für Pre-Season-Post

Bug 07.06.2026: Pre-Season kam 2× am selben Tag (Steam-Lag-Erklärung um 06:00
+ 10:00 Wien). wm_preseason_sent.json wird erst am Workflow-Ende committed —
wenn der Push failed, sieht der nächste Cron noch alten State.

Fix: telegram_wm_preseason.already_sent_today() prüft jetzt 2 Quellen:
  1. wm_preseason_sent.json (lokal, kann race-betroffen sein)
  2. telegram-log.json (committed nach jedem Send, robust)
"""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestAlreadySentTodayCheckBothSources(unittest.TestCase):
    """already_sent_today() muss BEIDE Quellen prüfen."""

    @classmethod
    def setUpClass(cls):
        import telegram_wm_preseason as mod
        cls.mod = mod

    def test_returns_true_when_sent_file_has_today(self):
        today = date.today().isoformat()
        with tempfile.TemporaryDirectory() as td:
            sent_file = Path(td) / "sent.json"
            log_file  = Path(td) / "log.json"
            sent_file.write_text(json.dumps({"lastSent": today, "history": [today]}))
            log_file.write_text("[]")
            with patch.object(self.mod, "SENT_FILE", sent_file), \
                 patch.object(self.mod, "LOG_FILE", log_file):
                self.assertTrue(self.mod.already_sent_today(),
                    "Wenn wm_preseason_sent.json heute drin hat → True")

    def test_returns_true_when_only_log_has_today(self):
        """KRITISCH: wenn State-File alt (commit failed), aber log hat heute → True."""
        today = date.today().isoformat()
        with tempfile.TemporaryDirectory() as td:
            sent_file = Path(td) / "sent.json"
            log_file  = Path(td) / "log.json"
            # State-File hat NICHT heute (commit failed)
            sent_file.write_text(json.dumps({"lastSent": "2026-01-01", "history": []}))
            # Aber log hat heute
            log_file.write_text(json.dumps([
                {"type": "preseason", "sentAt": f"{today}T06:30:00Z"}
            ]))
            with patch.object(self.mod, "SENT_FILE", sent_file), \
                 patch.object(self.mod, "LOG_FILE", log_file):
                self.assertTrue(self.mod.already_sent_today(),
                    "Log-Backup muss greifen wenn State-File alt ist (Hauptfix)")

    def test_returns_false_when_nothing_today(self):
        with tempfile.TemporaryDirectory() as td:
            sent_file = Path(td) / "sent.json"
            log_file  = Path(td) / "log.json"
            sent_file.write_text(json.dumps({"lastSent": "2026-01-01"}))
            log_file.write_text(json.dumps([
                {"type": "preseason", "sentAt": "2026-01-01T06:00:00Z"}
            ]))
            with patch.object(self.mod, "SENT_FILE", sent_file), \
                 patch.object(self.mod, "LOG_FILE", log_file):
                self.assertFalse(self.mod.already_sent_today(),
                    "Wenn keine Quelle heute hat → False")

    def test_history_fallback_in_sent_file(self):
        """Wenn lastSent versehentlich überschrieben, history fängt es ab."""
        today = date.today().isoformat()
        with tempfile.TemporaryDirectory() as td:
            sent_file = Path(td) / "sent.json"
            log_file  = Path(td) / "log.json"
            # lastSent ist alt aber history hat heute
            sent_file.write_text(json.dumps({"lastSent": "2026-01-01", "history": [today]}))
            log_file.write_text("[]")
            with patch.object(self.mod, "SENT_FILE", sent_file), \
                 patch.object(self.mod, "LOG_FILE", log_file):
                self.assertTrue(self.mod.already_sent_today())

    def test_handles_corrupt_files_gracefully(self):
        with tempfile.TemporaryDirectory() as td:
            sent_file = Path(td) / "sent.json"
            log_file  = Path(td) / "log.json"
            sent_file.write_text("CORRUPT")
            log_file.write_text("ALSO CORRUPT")
            with patch.object(self.mod, "SENT_FILE", sent_file), \
                 patch.object(self.mod, "LOG_FILE", log_file):
                # Soll nicht crashen, returnt False
                self.assertFalse(self.mod.already_sent_today())


if __name__ == "__main__":
    unittest.main()
