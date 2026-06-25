#!/usr/bin/env python3
"""
generate_liga_picks.py — Liga-Picks über DENSELBEN Motor wie die WM (25.06.2026, Lucas: Liga auf
WM-Stack). Dünner Wrapper: setzt Dataset + Profil per Env und ruft generate_wm_picks.main().

  - COCOBET_DATASET=liga → generate_wm_picks liest liga-data.json + liga_*.json-Sibling-Dateien
    (fehlende → graceful kein-Signal, kein WM-Datenleck), KO/Quali-Schritte gegatet.
  - COCOBET_PROFILE=liga_default → Edge-Schwellen + disabled_markets der Liga, WM-only Signale aus.

WICHTIG: Env MUSS vor dem Import gesetzt sein (generate_wm_picks wertet WM_FILE/CONFIG/_FILE_PREFIX
beim Import aus).
"""
import os

os.environ.setdefault("COCOBET_DATASET", "liga")
os.environ.setdefault("COCOBET_PROFILE", "liga_default")

import generate_wm_picks  # noqa: E402  (nach Env-Setzung!)

if __name__ == "__main__":
    generate_wm_picks.main()
