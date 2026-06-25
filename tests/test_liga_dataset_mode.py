#!/usr/bin/env python3
"""
test_liga_dataset_mode.py — Dataset-Modus von generate_wm_picks (25.06.2026, Lucas: Liga auf WM-Stack).
COCOBET_DATASET=liga muss auf liga-data.json + liga_-Prefix umschalten; Default bleibt WM. Per
Subprozess, weil die Modul-Konstanten beim Import (env-abhängig) ausgewertet werden.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
_SNIP = "import generate_wm_picks as g; print(g.IS_LIGA, g._FILE_PREFIX, g.WM_FILE.name, g._HISTORY_FILE)"


def _run(dataset=None):
    env = dict(os.environ)
    env.pop("COCOBET_DATASET", None)
    if dataset:
        env["COCOBET_DATASET"] = dataset
    out = subprocess.check_output([sys.executable, "-c", _SNIP], cwd=str(REPO), env=env)
    return out.decode().strip().split()


class TestDatasetMode(unittest.TestCase):
    def test_wm_default(self):
        is_liga, prefix, fname, hist = _run(None)
        self.assertEqual(is_liga, "False")
        self.assertEqual(prefix, "wm_")
        self.assertEqual(fname, "wm2026-data.json")
        self.assertEqual(hist, "wm2026-odds-history.json")

    def test_liga_mode(self):
        is_liga, prefix, fname, hist = _run("liga")
        self.assertEqual(is_liga, "True")
        self.assertEqual(prefix, "liga_")
        self.assertEqual(fname, "liga-data.json")
        self.assertEqual(hist, "liga-odds-history.json")


def _file_for(module, attr, dataset):
    env = dict(os.environ)
    env.pop("COCOBET_DATASET", None)
    if dataset:
        env["COCOBET_DATASET"] = dataset
    snip = f"import {module} as m, os; print(os.path.basename(str(m.{attr})))"
    return subprocess.check_output([sys.executable, "-c", snip], cwd=str(REPO), env=env).decode().strip()


class TestResolverDataset(unittest.TestCase):
    def test_resolve_picks_wm_default(self):
        self.assertEqual(_file_for("resolve_wm_picks", "WM_FILE", None), "wm2026-data.json")

    def test_resolve_picks_liga(self):
        self.assertEqual(_file_for("resolve_wm_picks", "WM_FILE", "liga"), "liga-data.json")

    def test_steam_clv_liga(self):
        self.assertEqual(_file_for("resolve_steam_clv", "WM", "liga"), "liga-data.json")


if __name__ == "__main__":
    unittest.main()
