#!/usr/bin/env python3
"""
generate_mls_picks.py — MLS-Picks über DENSELBEN Motor wie WM/Liga (29.06.2026, Lucas: MLS als
Brücken-Liga nach der WM). Dünner Wrapper: setzt Dataset + Profil per Env und ruft
generate_wm_picks.main().

  - COCOBET_DATASET=mls → generate_wm_picks liest mls-data.json + mls_*.json-Sibling-Dateien.
  - COCOBET_PROFILE=mls_default → MLS-Edge-Schwellen; Reise/Höhe/Wetter folgen in Phase 2.

WICHTIG: Env MUSS vor dem Import gesetzt sein (generate_wm_picks wertet Pfade beim Import aus).
"""
import os

os.environ.setdefault("COCOBET_DATASET", "mls")
os.environ.setdefault("COCOBET_PROFILE", "mls_default")

import generate_wm_picks  # noqa: E402  (nach Env-Setzung!)

if __name__ == "__main__":
    generate_wm_picks.main()
