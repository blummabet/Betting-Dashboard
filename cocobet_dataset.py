#!/usr/bin/env python3
"""
cocobet_dataset.py — EINE Quelle für die Dataset-Auflösung (26.06.2026, Konsolidierung).

Vorher war das `_IS_LIGA`-Boilerplate (COCOBET_DATASET lesen + Pfad-Ternär + Liga-Liga-Map +
Saison-Logik) in ~16 Dateien kopiert. Das hier ist die Single Source of Truth — jede Datei importiert
nur noch, was sie braucht, statt das Muster zu wiederholen.

  is_liga()            → True im Liga-Modus (COCOBET_DATASET=liga)
  active_dataset()     → "liga" | "wm"
  active_profile()     → COCOBET_PROFILE, sonst dataset-Default
  file(wm, liga)       → dataset-passender Pfad (beide Namen explizit, weil das Namensschema
                         historisch variiert: liga_*, liga-*, wm_*, wm2026-*)
  data_file()          → Haupt-Datendatei (wm2026-data.json | liga-data.json)
  prefix()             → "" | "liga_" (für {_FILE_PREFIX}-Geschwisterdateien)
  leagues()            → Top-5-Liga-Map {Code: API-Football-League-ID}
  season()             → LIGA_SEASON env, sonst current_season()
  current_season(now)  → API-Football-Saison (Startjahr; ab Juni die kommende)

Reine Helper, keine Seiteneffekte — überall importierbar, auch in Tests.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Top-5-Ligen: Code → API-Football-League-ID. EINZIGE Definition (vorher in 5 Dateien hartkodiert).
LIGA_LEAGUES: dict[str, int] = {"ENG": 39, "ESP": 140, "GER": 78, "ITA": 135, "FRA": 61}


def active_dataset() -> str:
    return (os.environ.get("COCOBET_DATASET") or "wm").lower()


def is_liga() -> bool:
    return active_dataset() == "liga"


def active_profile() -> str:
    return os.environ.get("COCOBET_PROFILE") or ("liga_default" if is_liga() else "wm2026")


def file(wm: str, liga: str) -> Path:
    """Dataset-passender Pfad. Beide Namen explizit angeben (Namensschema variiert je Datei)."""
    return BASE / (liga if is_liga() else wm)


def data_file() -> Path:
    return file("wm2026-data.json", "liga-data.json")


def prefix() -> str:
    return "liga_" if is_liga() else ""


def leagues() -> dict[str, int]:
    return dict(LIGA_LEAGUES)


def current_season(now: datetime | None = None) -> int:
    """API-Football-Saison = Startjahr. Ab Juni zählt die kommende Saison (Sommer-Fenster)."""
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def season() -> int:
    return int(os.environ.get("LIGA_SEASON") or current_season())
