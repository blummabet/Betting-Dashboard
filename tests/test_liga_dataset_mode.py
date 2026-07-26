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


class TestSignalGating(unittest.TestCase):
    """WM-only Signale müssen im liga_default-Profil deaktiviert sein (sonst feuert z.B. Incentive
    auf der Liga-Tabelle). 25.06.2026, Lucas."""
    def _disabled(self, profile=None):
        env = dict(os.environ)
        env.pop("COCOBET_PROFILE", None)
        if profile:
            env["COCOBET_PROFILE"] = profile
        snip = "import sharp_signals.registry as r; print(','.join(sorted(r._DISABLED_SIGNALS)))"
        return set(filter(None, subprocess.check_output(
            [sys.executable, "-c", snip], cwd=str(REPO), env=env).decode().strip().split(",")))

    def test_liga_disables_wm_only(self):
        d = self._disabled("liga_default")
        for s in ("incentive_signal", "altitude_signal", "weather_signal",
                  "travel_burden", "smart_money", "polymarket_sharp", "pressure_index"):
            self.assertIn(s, d)

    def test_liga_keeps_generic(self):
        d = self._disabled("liga_default")
        # Generische Signale (Form/xG/H2H/Pinnacle-vs-Soft) bleiben aktiv.
        for s in ("form_trend", "h2h_pattern", "xg_strength", "lead_lag_bias"):
            self.assertNotIn(s, d)
        # steam_lag ist Pinn-vs-POLY (Poly-spezifisch) → für Liga deaktiviert (27.06.2026),
        # bis Polymarket Ligen listet. Sharp Radar deckt Liga-Steam (Pinn-vs-Soft) ab.
        self.assertIn("steam_lag", d)

    def test_wm_disables_only_top5_mls_signals(self):
        # WM = Nationalteams + winterisiert: die Top-5-/MLS-spezifischen Signale sind bewusst aus.
        # move_following (nur auf Top-5-Historie validiert) + venue_form (Klub-Heim/Auswaerts-Daten).
        self.assertEqual(self._disabled(None), {"move_following", "venue_form"})


class TestLearningLoopDataset(unittest.TestCase):
    """Lern-Loop nutzt eigene Liga-Dateien (25.06.2026, Lucas: getrennte Liga-Gewichte)."""
    def _val(self, expr, dataset):
        env = dict(os.environ)
        env.pop("COCOBET_DATASET", None)
        if dataset:
            env["COCOBET_DATASET"] = dataset
        return subprocess.check_output([sys.executable, "-c", expr], cwd=str(REPO), env=env).decode().strip()

    def test_weights_path_liga(self):
        self.assertEqual(self._val(
            "import sharp_signals.registry as r; print(r._weights_path().name)", "liga"),
            "liga_signal_weights.json")

    def test_weights_path_wm(self):
        self.assertEqual(self._val(
            "import sharp_signals.registry as r; print(r._weights_path().name)", None),
            "signal_weights.json")

    def test_ledger_paths_liga(self):
        out = self._val("import build_signal_ledger as b, update_signal_weights as u; "
                        "print(b.LEDGER_FILE.name, u.WEIGHTS_FILE.name, u.MIN_LEARN_MATCHDAY)", "liga")
        self.assertEqual(out, "liga_signal_ledger.json liga_signal_weights.json 1")


class TestResolverDataset(unittest.TestCase):
    def test_resolve_picks_wm_default(self):
        self.assertEqual(_file_for("resolve_wm_picks", "WM_FILE", None), "wm2026-data.json")

    def test_resolve_picks_liga(self):
        self.assertEqual(_file_for("resolve_wm_picks", "WM_FILE", "liga"), "liga-data.json")

    def test_steam_clv_liga(self):
        self.assertEqual(_file_for("resolve_steam_clv", "WM", "liga"), "liga-data.json")


if __name__ == "__main__":
    unittest.main()
