#!/usr/bin/env python3
"""
fetch_liga_topscorers.py — Top-Torjäger der Top-5-Ligen (26.06.2026, Lucas Spieler-Layer).

Holt /players/topscorers?league=&season= pro Liga und schreibt je Team den treffsichersten Spieler
nach liga-data.json["topScorers"] = {teamId: {name, goals, appearances}}. Quelle für das Signal
topscorer_momentum (Team mit heißem Stürmer → Angriffs-Edge auf Sieg/Über).

Liga-only (Klub-Daten). Früh in der Saison dünn (wenige Tore) → Signal feuert erst mit Daten. Reine
Funktion extract_team_topscorers (testbar); main holt via API-Football (APISPORTS_KEY).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent
LIGA_FILE = D.data_file()   # 29.06.2026: liga-data.json ODER mls-data.json je COCOBET_DATASET
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "").strip()
LIGA_LEAGUES = D.leagues()
LIGA_SEASON = D.season()
DELAY = 1.0


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_team_topscorers(response: list) -> dict:
    """/players/topscorers-Response → {team_id(str): {name, goals, appearances}} mit dem
    treffsichersten Spieler je Team. Reine Funktion (testbar)."""
    out: dict = {}
    for entry in (response or []):
        player = entry.get("player") or {}
        st = (entry.get("statistics") or [{}])[0] or {}
        tid = ((st.get("team") or {}).get("id"))
        goals = _num((st.get("goals") or {}).get("total")) or 0.0
        apps = _num((st.get("games") or {}).get("appearences")) or 0.0
        if tid is None:
            continue
        key = str(tid)
        if key not in out or goals > out[key]["goals"]:
            out[key] = {"name": player.get("name") or "?", "goals": goals,
                        "appearances": apps}
    return out


def _apif_get(path: str) -> list:
    if not APIF_KEY:
        return []
    import http.client
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8", "replace"))
        conn.close()
        return data.get("response", []) if resp.status == 200 else []
    except Exception as e:
        print(f"  ⚠️  API {path}: {e}")
        return []


def main():
    print("=== fetch_liga_topscorers.py ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        sys.exit(0)
    if not LIGA_FILE.exists():
        print("  ❌  liga-data.json fehlt.")
        sys.exit(1)
    wm = json.loads(LIGA_FILE.read_text(encoding="utf-8"))
    ts_out: dict = dict(wm.get("topScorers") or {})
    total = 0
    for code, lid in LIGA_LEAGUES.items():
        time.sleep(DELAY)
        resp = _apif_get(f"/players/topscorers?league={lid}&season={LIGA_SEASON}")
        team_ts = extract_team_topscorers(resp)
        ts_out.update(team_ts)
        total += len(team_ts)
        print(f"    {code}: {len(team_ts)} Teams mit Top-Torjäger")
    wm["topScorers"] = ts_out
    LIGA_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ topScorers für {total} Teams → liga-data.json")


if __name__ == "__main__":
    main()
