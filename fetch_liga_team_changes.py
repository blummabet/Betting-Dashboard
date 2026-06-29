#!/usr/bin/env python3
"""
fetch_liga_team_changes.py — Trainerwechsel + Schlüsselspieler-Abgänge (26.06.2026, Lucas).

Speist zwei Saisonstart-relevante Signale:
  · coach_change   — frischer Trainer → Neue-Trainer-Bounce (kurzfristiger Effekt).
  · transfer_shift — Schlüsselspieler-Abgang → Team geschwächt (Markt hinkt früh nach).

Pro Liga-Team: /coachs?team={id} (aktueller Trainer + Amtsantritt) + /transfers?team={id} (jüngste
Abgänge, gefiltert auf Schlüsselspieler aus squads/topScorers). Schreibt liga-data.json["coachChange"]
+ ["keyDepartures"]. Läuft NACH squads + topscorers (braucht deren Schlüsselspieler-Namen).
Reine Parser (parse_current_coach / key_departures) sind unit-getestet.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
import cocobet_dataset as D  # 29.06.2026: dataset-aware (MLS)
LIGA_FILE = D.data_file()   # 29.06.2026: liga-data.json ODER mls-data.json je COCOBET_DATASET
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "").strip()
COACH_WINDOW_DAYS = 75      # Trainer gilt als „frisch" bis ~2,5 Monate
TRANSFER_WINDOW_DAYS = 120  # Abgang gilt als jüngst bis ~4 Monate (Sommerfenster)
DELAY = 0.7


def _days_since(d: str, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(d)[:10])).days
    except (ValueError, TypeError):
        return None


def parse_current_coach(resp: list, team_id: str, today: date) -> dict | None:
    """/coachs?team-Response → {name, since, daysSince} des AKTUELLEN Trainers, falls Amtsantritt
    ≤ COACH_WINDOW_DAYS her. Aktuell = Career-Eintrag dieses Teams mit end=None. Reine Funktion."""
    best = None   # (daysSince, name, start)
    for coach in (resp or []):
        name = coach.get("name") or "?"
        for c in (coach.get("career") or []):
            if str((c.get("team") or {}).get("id")) != str(team_id):
                continue
            if c.get("end"):           # nur aktueller (laufender) Posten
                continue
            ds = _days_since(c.get("start"), today)
            if ds is None or ds < 0 or ds > COACH_WINDOW_DAYS:
                continue
            if best is None or ds < best[0]:
                best = (ds, name, str(c.get("start"))[:10])
    if best is None:
        return None
    return {"name": best[1], "since": best[2], "daysSince": best[0]}


def _name_match(a: str, b: str) -> bool:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    la, lb = a.split()[-1], b.split()[-1]   # Nachname-Fallback
    return la == lb and len(la) >= 4


def key_departures(resp: list, team_id: str, key_names: list, today: date) -> list:
    """/transfers?team-Response → [{name, date}] für SCHLÜSSELSPIELER (key_names), die jüngst (≤
    TRANSFER_WINDOW_DAYS) von diesem Team WEG transferiert wurden. Reine Funktion."""
    out = []
    for entry in (resp or []):
        pname = (entry.get("player") or {}).get("name") or ""
        if not any(_name_match(pname, k) for k in key_names):
            continue
        for t in (entry.get("transfers") or []):
            teams = t.get("teams") or {}
            if str((teams.get("out") or {}).get("id")) != str(team_id):
                continue
            ds = _days_since(t.get("date"), today)
            if ds is None or ds < 0 or ds > TRANSFER_WINDOW_DAYS:
                continue
            out.append({"name": pname, "date": str(t.get("date"))[:10]})
            break
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


def _key_names_for(team_id: str, squads: dict, topscorers: dict) -> list:
    names = []
    sq = squads.get(team_id) or {}
    for kp in (sq.get("key_players") or []):
        if kp.get("name"):
            names.append(kp["name"])
    if sq.get("name"):
        names.append(sq["name"])   # Top-Stürmer aus squads
    ts = topscorers.get(team_id) or {}
    if ts.get("name"):
        names.append(ts["name"])
    return list(dict.fromkeys(names))   # dedup, Reihenfolge erhalten


def main():
    print("=== fetch_liga_team_changes.py ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        sys.exit(0)
    if not LIGA_FILE.exists():
        print("  ❌  liga-data.json fehlt.")
        sys.exit(1)
    wm = json.loads(LIGA_FILE.read_text(encoding="utf-8"))
    squads = wm.get("squads") or {}
    topscorers = wm.get("topScorers") or {}
    today = date.today()
    coach_out: dict = {}
    dep_out: dict = {}
    team_ids = [t["id"] for g in (wm.get("groups") or {}).values() for t in (g.get("teams") or [])]
    for tid in team_ids:
        time.sleep(DELAY)
        cc = parse_current_coach(_apif_get(f"/coachs?team={tid}"), tid, today)
        if cc:
            coach_out[tid] = cc
        key_names = _key_names_for(tid, squads, topscorers)
        if key_names:
            time.sleep(DELAY)
            deps = key_departures(_apif_get(f"/transfers?team={tid}"), tid, key_names, today)
            if deps:
                dep_out[tid] = deps
    wm["coachChange"] = coach_out
    wm["keyDepartures"] = dep_out
    LIGA_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ {len(coach_out)} frische Trainer · {len(dep_out)} Teams mit Schlüssel-Abgang")


if __name__ == "__main__":
    main()
