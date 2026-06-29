#!/usr/bin/env python3
"""
cocobet_dataset.py — EINE Quelle für die Dataset-Auflösung (26.06.2026, Konsolidierung).

Vorher war das `_IS_LIGA`-Boilerplate (COCOBET_DATASET lesen + Pfad-Ternär + Liga-Liga-Map +
Saison-Logik) in ~16 Dateien kopiert. Das hier ist die Single Source of Truth — jede Datei importiert
nur noch, was sie braucht, statt das Muster zu wiederholen.

  is_liga()            → True für JEDEN Klub-Datensatz (non-WM: liga, mls, …)
  active_dataset()     → "wm" | "liga" | "mls" | …
  active_profile()     → COCOBET_PROFILE, sonst dataset-Default
  file(wm, liga)       → dataset-passender Pfad (beide Namen explizit, weil das Namensschema
                         historisch variiert: liga_*, liga-*, wm_*, wm2026-*). Weitere Datensätze
                         leiten ihren Namen aus dem liga-Namen ab (liga→<dataset>), z.B. mls-data.json.
  data_file()          → Haupt-Datendatei (wm2026-data.json | liga-data.json | mls-data.json)
  prefix()             → "" | "liga_" | "mls_" (für {_FILE_PREFIX}-Geschwisterdateien)
  leagues()            → Liga-Map {Code: API-Football-League-ID} des aktiven Datensatzes
  season()             → LIGA_SEASON env, sonst current_season()
  current_season(now)  → API-Football-Saison (Startjahr; ab Juni die kommende)

Reine Helper, keine Seiteneffekte — überall importierbar, auch in Tests.

29.06.2026 (Lucas: MLS als Brücken-Liga nach der WM): von binär (wm/liga) auf N Datensätze
verallgemeinert. Neuer Datensatz = Eintrag in _DATASET_LEAGUES + _DATASET_PROFILE; file() leitet
den Dateinamen automatisch aus dem liga-Schema ab (liga→<dataset>). wm/liga-Verhalten unverändert.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Liga-Maps je Datensatz: Code → API-Football-League-ID. EINZIGE Definition.
LIGA_LEAGUES: dict[str, int] = {"ENG": 39, "ESP": 140, "GER": 78, "ITA": 135, "FRA": 61}
MLS_LEAGUES:  dict[str, int] = {"MLS": 253}   # Major League Soccer (API-Football league_id)

_DATASET_LEAGUES: dict[str, dict[str, int]] = {"liga": LIGA_LEAGUES, "mls": MLS_LEAGUES}
_DATASET_PROFILE: dict[str, str]            = {"wm": "wm2026", "liga": "liga_default", "mls": "mls_default"}


def active_dataset() -> str:
    return (os.environ.get("COCOBET_DATASET") or "wm").lower()


def is_liga() -> bool:
    """True für jeden Klub-Datensatz (alles außer WM). Steuert die „National/Liga"-Pfade
    im Renderer, Saison-Logik etc. — gilt damit auch für mls."""
    return active_dataset() != "wm"


def active_profile() -> str:
    return os.environ.get("COCOBET_PROFILE") or _DATASET_PROFILE.get(active_dataset(), "wm2026")


def file(wm: str, liga: str) -> Path:
    """Dataset-passender Pfad. Beide Namen explizit angeben (Namensschema variiert je Datei).
    Datensätze jenseits von wm/liga leiten ihren Namen aus dem liga-Namen ab (liga→<dataset>),
    z.B. liga-data.json→mls-data.json, liga_streaks.json→mls_streaks.json."""
    ds = active_dataset()
    if ds == "wm":
        return BASE / wm
    if ds == "liga":
        return BASE / liga
    return BASE / liga.replace("liga", ds)


def data_file() -> Path:
    return file("wm2026-data.json", "liga-data.json")


def prefix() -> str:
    ds = active_dataset()
    return "" if ds == "wm" else f"{ds}_"


def leagues() -> dict[str, int]:
    return dict(_DATASET_LEAGUES.get(active_dataset(), LIGA_LEAGUES))


def current_season(now: datetime | None = None) -> int:
    """API-Football-Saison = Startjahr. Ab Juni zählt die kommende Saison (Sommer-Fenster)."""
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def season() -> int:
    return int(os.environ.get("LIGA_SEASON") or current_season())
