#!/usr/bin/env python3
"""
test_dedup_seed_files.py — Stellt sicher dass alle Dedup-State-Files
als Seed im Repo existieren (mindestens leere {}).

Wenn ein Dedup-File fehlt:
  · Code schreibt es zwar selbst, ABER:
  · Beim Workflow-Pull wäre kein State vorhanden → Alerts kommen erneut
  · Race: zwischen 2 parallelen Workflows könnte einer den State überschreiben

Lösung: Seed-Files MÜSSEN als leere {} im Repo committed sein.
Test fängt zukünftige Drift.
"""
from __future__ import annotations
import json
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent

# State-Files die der Dedup-Mechanismus liest UND als Seed im Repo sein müssen
SEED_DEDUP_FILES = [
    "wm_edge_alert_dedup.json",       # fetch_wm_poly_prices.py
    "wm_sharp_dedup.json",            # detect_wm_sharp_moves.py
    "steam_lag_sell_dedup.json",      # steam_lag_monitor.py
    "tiktok_sent.json",               # generate_daily_tiktok.py
    "pick_changes_digest_state.json", # send_pick_changes_digest.py
    "track_record_state.json",        # generate_track_record_card.py
    "position_health_alerts.json",    # monitor_open_positions.py
    "wm_preseason_sent.json",         # telegram_wm_preseason.py
]


class TestDedupSeedFilesExist(unittest.TestCase):
    """Jedes State-File muss als Seed im Repo existieren."""

    def test_all_seed_files_present(self):
        missing = []
        for fname in SEED_DEDUP_FILES:
            f = BASE / fname
            if not f.exists():
                missing.append(fname)
        if missing:
            self.fail(
                f"Dedup-Seed-Files fehlen im Repo: {missing}\n"
                f"  Erstelle leere {{}} oder [] Files als Seed:\n"
                + "\n".join(f"  echo '{{}}' > {f}" for f in missing)
            )

    def test_all_seed_files_are_valid_json(self):
        for fname in SEED_DEDUP_FILES:
            f = BASE / fname
            if not f.exists():
                continue  # in test_all_seed_files_present gefangen
            with self.subTest(file=fname):
                try:
                    json.loads(f.read_text(encoding="utf-8"))
                except Exception as e:
                    self.fail(f"{fname}: invalid JSON — {e}")


class TestRegistryHasAllSeedFiles(unittest.TestCase):
    """Jedes Seed-Dedup-File muss in state_files_registry.json sein
    (sonst wird es vom Workflow nicht committet → Drift)."""

    def test_seed_files_in_registry(self):
        reg = json.loads((BASE / "state_files_registry.json").read_text(encoding="utf-8"))
        # Sammle alle Files aus allen Kategorien
        all_files = set()
        for cat in reg.get("categories", {}).values():
            for f in cat.get("files", []):
                all_files.add(f)
        missing_from_reg = [f for f in SEED_DEDUP_FILES if f not in all_files]
        if missing_from_reg:
            self.fail(
                f"Folgende Seed-Files nicht im state_files_registry.json: {missing_from_reg}\n"
                f"  → Workflow committet sie nicht → State geht verloren zwischen Runs."
            )


if __name__ == "__main__":
    unittest.main()
