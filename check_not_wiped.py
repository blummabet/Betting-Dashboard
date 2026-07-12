#!/usr/bin/env python3
"""
check_not_wiped.py — Harter Pre-Commit-Stopp gegen Daten-Wipes (12.07.2026, Lucas).

ANLASS: Der API-Zugang lief nachts ab → ein Fetcher schrieb mls-data.json leer (0 Teams/0
Fixtures, 292 verwaiste picks) → die Liga-Cards kippten. Die Workflows liefen ALLE Schritte mit
`|| true` und machten danach ein bedingungsloses `git add` — es gab also NICHTS, was einen
gewipten Datensatz vom Commit abgehalten hätte.

Dieses Skript läuft im Workflow VOR dem Commit, OHNE `|| true`:
  · Datensatz leer (0 Fixtures oder 0 Teams) → Exit 1 → Job wird ROT, nichts wird committet.
  · Verwaiste Picks ohne Fixtures → Exit 1 (genau das Muster, das die Cards killte).

Lieber ein roter Workflow als stiller Datenverlust im Live-Frontend.
Der eigentliche Schutz sitzt in den Fetchern (safe_write.py); das hier ist das letzte Netz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cocobet_dataset as D


def check(data: dict) -> list:
    """Gibt eine Liste von Fehlern zurück (leer = gesund). Rein/testbar."""
    problems = []
    groups = data.get("groups") or {}
    n_fx = sum(len(g.get("fixtures") or []) for g in groups.values())
    n_tm = sum(len(g.get("teams") or []) for g in groups.values())
    n_picks = len(data.get("picks") or {})
    if not groups:
        problems.append("groups fehlt/leer")
    if n_fx == 0:
        problems.append("0 Fixtures über alle Gruppen")
    if n_tm == 0:
        problems.append("0 Teams über alle Gruppen")
    if n_picks > 0 and n_fx == 0:
        problems.append(f"{n_picks} picks-Keys, aber 0 Fixtures — verwaiste Pick-Leichen")
    return problems


def main() -> int:
    path = Path(str(D.data_file()))
    if not path.exists():
        print(f"  ⏭️  {path.name} existiert nicht — nichts zu prüfen.")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ WIPE-CHECK {path.name}: kein valides JSON ({e}) — Commit gestoppt.")
        return 1

    problems = check(data)
    if problems:
        print(f"❌ WIPE-CHECK {path.name}: Datensatz sieht LEER-GESCHRIEBEN aus — Commit gestoppt!")
        for p in problems:
            print(f"     · {p}")
        print("   → API-Key/Quota/Ausfall prüfen. Der alte Stand im Repo bleibt unangetastet.")
        return 1

    groups = data.get("groups") or {}
    n_fx = sum(len(g.get("fixtures") or []) for g in groups.values())
    n_tm = sum(len(g.get("teams") or []) for g in groups.values())
    print(f"  ✅ Wipe-Check {path.name}: {len(groups)} Gruppen · {n_tm} Teams · {n_fx} Fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
