#!/usr/bin/env python3
"""test_content_dataset_aware.py — Content-Layer dataset-aware (01.07.2026, Lucas: „Content für MLS/
Liga"). generate_wm_ai_preview / generate_daily_tiktok / telegram_wm waren hart auf wm2026-data.json →
liefen nie für MLS/Liga. Dieser Test friert die dataset-aware Auflösung ein (WM unverändert, mls/liga
eigene Dateien → keine Kreuz-Kontamination)."""
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _resolve(dataset: str) -> dict:
    prev = os.environ.get("COCOBET_DATASET")
    os.environ["COCOBET_DATASET"] = dataset
    try:
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import generate_wm_ai_preview as A
        import generate_daily_tiktok as T
        import telegram_wm as G
        for m in (A, T, G):
            importlib.reload(m)
        return {
            "ai_wm":   os.path.basename(str(A.WM_FILE)),
            "tt_wm":   os.path.basename(str(T.WM_FILE)),
            "tt_out":  T.OUTPUT_DIR.name,
            "tt_dedup": T.DEDUP_FILE.name,
            "tg_wm":   os.path.basename(str(G.WM_FILE)),
            "tg_log":  os.path.basename(str(G.LOG_FILE)),
        }
    finally:
        if prev is None:
            os.environ.pop("COCOBET_DATASET", None)
        else:
            os.environ["COCOBET_DATASET"] = prev


class TestContentDatasetAware(unittest.TestCase):
    def test_wm_unchanged(self):
        r = _resolve("wm")
        self.assertEqual(r["ai_wm"], "wm2026-data.json")
        self.assertEqual(r["tt_wm"], "wm2026-data.json")
        self.assertEqual(r["tt_out"], "daily-tiktok")
        self.assertEqual(r["tt_dedup"], "tiktok_sent.json")
        self.assertEqual(r["tg_wm"], "wm2026-data.json")
        self.assertEqual(r["tg_log"], "telegram-log.json")

    def test_mls_isolated(self):
        r = _resolve("mls")
        self.assertEqual(r["ai_wm"], "mls-data.json")
        self.assertEqual(r["tt_wm"], "mls-data.json")
        self.assertEqual(r["tt_out"], "mls_daily-tiktok")
        self.assertEqual(r["tt_dedup"], "mls_tiktok_sent.json")
        self.assertEqual(r["tg_wm"], "mls-data.json")
        self.assertEqual(r["tg_log"], "mls-telegram-log.json")

    @classmethod
    def tearDownClass(cls):
        _resolve("wm")   # Module auf Default zurück, damit andere Tests nicht kontaminiert werden


if __name__ == "__main__":
    unittest.main()
