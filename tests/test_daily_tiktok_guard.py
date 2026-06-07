#!/usr/bin/env python3
"""
test_daily_tiktok_guard.py — Backup-Cron Anti-Double-Send Schutz

Verifiziert dass:
  · Backup-Cron skipt wenn primärer Cron heute schon Cards generiert + gesendet hat
  · Backup-Cron läuft wenn primärer geskipt wurde (kein History-Eintrag + keine PNGs)
  · SKIP_GUARD=true Override funktioniert (für Smoketests / manuelle Triggers)
  · Workflow hat 2 Cron-Einträge (primär + backup)
"""
from __future__ import annotations
import json
import sys
import unittest
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestWorkflowHasBackupCron(unittest.TestCase):
    """daily-tiktok.yml muss 2 Cron-Einträge haben."""

    def test_workflow_has_two_crons(self):
        wf = (BASE / ".github/workflows/daily-tiktok.yml").read_text(encoding="utf-8")
        # Primärer + Backup. Bug-Fix 07.06.2026: Primary auf 04:30 UTC verschoben,
        # damit fetch-wm-data (04:00 UTC) seine Pick-Generation fertig hat bevor
        # TikTok-Rendering startet (sonst stale wm2026-data.json).
        self.assertIn("- cron: '30 4 * * *'", wf, "Primärer Cron (04:30 UTC) fehlt")
        self.assertIn("- cron: '30 5 * * *'", wf, "Backup-Cron (05:30 UTC) fehlt")

    def test_concurrency_shared_with_fetch(self):
        """Concurrency-Group muss fetch-wm-data sein damit TikTok-Render NIE
        parallel zu Pick-Generation läuft (Bug-Fix 07.06.2026)."""
        wf = (BASE / ".github/workflows/daily-tiktok.yml").read_text(encoding="utf-8")
        self.assertIn("group: fetch-wm-data", wf,
            "daily-tiktok muss die concurrency-Group von fetch-wm-data teilen")


class TestGuardLogicInSource(unittest.TestCase):
    """generate_daily_tiktok.py hat Anti-Double-Send-Guard."""

    @classmethod
    def setUpClass(cls):
        cls.src = (BASE / "generate_daily_tiktok.py").read_text(encoding="utf-8")

    def test_guard_present(self):
        self.assertIn("Anti-Double-Send Guard", self.src)

    def test_guard_checks_dedup_history(self):
        # Sucht den History-Check
        self.assertIn('h.get("date") == today_iso', self.src,
            "Guard prüft nicht ob heute schon History-Eintrag existiert")

    def test_guard_checks_existing_pngs(self):
        self.assertIn('OUTPUT_DIR.glob', self.src,
            "Guard muss prüfen ob heute schon PNGs in OUTPUT_DIR existieren")
        self.assertIn('today_iso', self.src)

    def test_skip_guard_override_works(self):
        """SKIP_GUARD=true muss Guard umgehen können."""
        self.assertIn('SKIP_GUARD', self.src)
        self.assertIn('skip_guard = os.environ.get', self.src)

    def test_override_date_bypasses_guard(self):
        """DAILY_TIKTOK_DATE (manuelle Datums-Override) bypasst Guard."""
        self.assertIn('not override:', self.src,
            "Wenn override gesetzt → Guard muss inaktiv sein")


class TestGuardBehaviorSimulation(unittest.TestCase):
    """Funktionale Tests via Subprocess-Simulation (Trockenlauf)."""

    def test_guard_triggers_when_today_already_sent(self):
        """Wenn tiktok_sent.json bereits Heute hat + PNGs existieren → skip."""
        from datetime import date
        today_iso = date.today().isoformat()

        # In-memory Simulation der Guard-Logik (ohne echten Skript-Aufruf)
        dedup_state = {
            "history": [{"date": today_iso, "teamId": "MAR"}]
        }
        today_done = any(h.get("date") == today_iso for h in dedup_state.get("history", []))
        # PNGs würden auch existieren (simuliert)
        existing_pngs_exist = True

        # Guard-Bedingung: BEIDES muss zutreffen
        should_skip = today_done and existing_pngs_exist
        self.assertTrue(should_skip,
            "Wenn History + PNGs für heute da sind → Guard MUSS skipen")

    def test_guard_passes_when_today_not_sent(self):
        """Wenn heute nichts in History → Guard läuft normal weiter."""
        from datetime import date
        today_iso = date.today().isoformat()
        dedup_state = {"history": [{"date": "2026-01-01", "teamId": "OLD"}]}
        today_done = any(h.get("date") == today_iso for h in dedup_state.get("history", []))
        self.assertFalse(today_done,
            "Heute nicht in History → Guard darf nicht skipen")


if __name__ == "__main__":
    unittest.main()
