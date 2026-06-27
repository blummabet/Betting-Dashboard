#!/usr/bin/env python3
"""
fetch_wm_injuries.py — WM 2026 Verletzungs- & Suspensions-Daten
================================================================
Fetcht aktuelle Verletzungen und Sperren für alle WM-Teams via API-Football.

Drei Datenquellen (in dieser Reihenfolge versucht):
  1. /injuries?league=1&season=2026   — direkte WM-Verletzungsmeldungen
     (verfügbar ab WM-Start am 11. Juni — vorher leer)
  2. /sidelined?team={apif_id}        — aktuell gesperrte/verletzte Spieler
     pro Nationalmannschaft. Funktioniert auch pre-WM weil Klub-Daten
     hier reinfließen. Update 09.06.2026: vorher fehlte dieser Pfad
     komplett, daher kam pre-WM nichts an.
  3. /injuries?team={apif_id}&season=2025  — Fallback: NT-Spiele aus letzter
     Saison (Quali-Verletzungen). Nur wenn /sidelined leer war.

Output: wm2026-data.json["injuries"]
  {
    "FRA": {
      "updatedAt": "ISO",
      "players": [
        {"name": "K. Mbappé", "type": "Injury", "reason": "Hamstring", "status": "missing"}
      ]
    }
  }

Wird in generate_wm_ai_preview.py und generate_wm_match_pages.py eingelesen
um Previews und Pick-Bewertungen zu informieren.

Env-Variablen:
  APISPORTS_KEY — API-Football Key
"""

import http.client
import json
import os
import time
from datetime import datetime, timezone, date
from pathlib import Path

import cocobet_dataset as D

BASE      = Path(__file__).parent
# Dataset-bewusst (Single Source: cocobet_dataset): Liga liest/schreibt liga-data.json; League-
# Endpoint läuft über die 5 Top-Ligen, /sidelined pro Team bleibt generisch (Hauptquelle pre-Saison).
# Consumer (generate_wm_picks injury_discount) liest wm["injuries"] schon dataset-bewusst.
_IS_LIGA  = D.is_liga()
WM_FILE   = D.data_file()
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY  = os.environ.get("APISPORTS_KEY", "").strip()
DELAY     = 1.2

WM_LEAGUE  = 1       # FIFA World Cup
WM_SEASON  = 2026
WM_START   = date(2026, 6, 11)
LIGA_LEAGUES = D.leagues()
LIGA_SEASON  = D.season()


def apif_get(endpoint: str, params: dict) -> list:
    """API-Football GET → response list. Gibt [] bei Fehler zurück."""
    if not APIF_KEY:
        return []
    query = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", f"/{endpoint}?{query}",
                     headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        data = json.loads(raw)
        if data.get("errors"):
            errs = data["errors"]
            if errs and errs != [] and errs != {}:
                print(f"  ⚠️  API error /{endpoint}: {errs}")
                return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ❌ Request failed /{endpoint}: {e}")
        return []


def load_wm() -> dict:
    try:
        return json.loads(WM_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ wm2026-data.json nicht lesbar: {e}")
        return {}


def get_all_team_ids(wm: dict) -> dict[str, str]:
    """Gibt {our_id: team_name} für alle 48 WM-Teams zurück."""
    result = {}
    for gdata in wm.get("groups", {}).values():
        for t in gdata.get("teams", []):
            result[t["id"]] = t.get("name", t["id"])
    return result


def fetch_wm_injuries_league() -> dict[str, list]:
    """
    Holt Verletzungen via /injuries?league=&season=. WM: league=1/season=2026. Liga: über die 5
    Top-Ligen (LIGA_LEAGUES/LIGA_SEASON) iteriert + gemerged. Gibt {} zurück wenn keine Daten.
    """
    league_seasons = ([(lid, LIGA_SEASON) for lid in LIGA_LEAGUES.values()]
                      if _IS_LIGA else [(WM_LEAGUE, WM_SEASON)])
    entries = []
    for lid, season in league_seasons:
        print(f"  📡 Fetching /injuries?league={lid}&season={season}…")
        time.sleep(DELAY)
        entries.extend(apif_get("injuries", {"league": lid, "season": season}) or [])

    if not entries:
        print("  ℹ️  Keine Verletzungsdaten — Saison noch nicht begonnen oder API leer.")
        return {}

    by_team: dict[str, list] = {}
    for e in entries:
        player = e.get("player", {})
        team   = e.get("team", {})
        fix    = e.get("fixture", {})

        team_name = team.get("name", "")
        inj_type  = e.get("type", "Unknown")       # "Injury" or "Suspension"
        inj_reason = e.get("reason", "")           # e.g. "Hamstring"

        if not team_name:
            continue

        entry = {
            "name":    player.get("name", "?"),
            "type":    inj_type,
            "reason":  inj_reason,
            "status":  "missing",
            "fixture": fix.get("date", ""),
        }

        by_team.setdefault(team_name, []).append(entry)

    print(f"  ✅ {sum(len(v) for v in by_team.values())} Einträge für {len(by_team)} Teams")
    return by_team


def fetch_sidelined_per_team(team_map: dict[str, str], team_ids: dict[str, int]) -> dict[str, list]:
    """
    Per-Team-Ausfälle via /injuries?team={id}&season={season}.

    FIX 11.06.2026: Vorher wurde /sidelined?team aufgerufen — aber der
    /sidelined-Endpoint von API-Football akzeptiert KEINEN team-Parameter
    (nur player/coach) → 47× "The Team field do not exist." → 0 Teams.
    /injuries?team&season ist der valide team-Level-Endpoint und liefert
    WM-Turnier-Ausfälle, sobald sie gemeldet werden.

    Returns: {our_id: [entry, …]}
    """
    print("  📡 Fetching /injuries?team=<id>&season=… für alle Teams…")
    result: dict[str, list] = {}
    queried, hits = 0, 0

    for our_id, our_name in team_map.items():
        apif_id = team_ids.get(our_id)
        if not apif_id:
            continue
        queried += 1
        time.sleep(DELAY)
        entries = apif_get("injuries", {"team": apif_id, "season": WM_SEASON})
        if not entries:
            continue

        team_entries = []
        seen: set = set()
        for e in entries:
            player = e.get("player", {})
            name   = player.get("name", "?")
            if name in seen:        # API listet pro Fixture — pro Spieler nur 1×
                continue
            seen.add(name)
            team_entries.append({
                "name":    name,
                "type":    e.get("type", "Unknown"),    # "Missing Fixture" / "Questionable"
                "reason":  e.get("reason", ""),          # "Injury" / "Suspended" / konkret
                "status":  "missing",
                "fixture": (e.get("fixture") or {}).get("date", ""),
            })

        if team_entries:
            result[our_id] = team_entries
            hits += 1
            print(f"    ✅ {our_id} ({our_name}): {len(team_entries)} Ausfall/Ausfälle")

    print(f"  📊 /injuries?team: {hits}/{queried} Teams mit Ausfällen")
    return result


def match_team_name(our_name: str, api_name: str) -> bool:
    """Fuzzy-Match zwischen unserem Teamnamen und API-Namen."""
    def norm(s):
        return s.lower().strip().replace("ü","u").replace("é","e").replace("ö","o")
    n1, n2 = norm(our_name), norm(api_name)
    return n1 == n2 or n1 in n2 or n2 in n1


def main():
    print("=== fetch_wm_injuries.py ===")
    now_ts = datetime.now(timezone.utc).isoformat()
    today  = date.today()

    if not APIF_KEY:
        print("  ❌ APISPORTS_KEY nicht gesetzt — Abbruch")
        return

    wm = load_wm()
    if not wm:
        return

    team_map = get_all_team_ids(wm)  # {our_id: name}
    team_ids = wm.get("teamIds", {})  # {our_id: apif_team_id}
    print(f"  📋 {len(team_map)} WM-Teams ({len(team_ids)} mit APIF-ID)")

    # ── Schritt 1: Verletzungen via League-Endpoint ────────────────────────────
    # Vor Saison-/Turnierstart gibt dieser Endpoint typischerweise nichts zurück → /sidelined-Fallback.
    days_until_wm = 0 if _IS_LIGA else (WM_START - today).days
    if not _IS_LIGA:
        print(f"  📅 Tage bis WM-Start: {days_until_wm}")

    injuries_by_name = fetch_wm_injuries_league()

    # ── Schritt 2: Team-IDs auflösen (Name → our_id) ───────────────────────────
    injuries_out: dict[str, dict] = wm.get("injuries", {})

    if injuries_by_name:
        for our_id, our_name in team_map.items():
            matched_key = None
            for api_name in injuries_by_name:
                if match_team_name(our_name, api_name):
                    matched_key = api_name
                    break
            if matched_key:
                injuries_out[our_id] = {
                    "updatedAt": now_ts,
                    "source":    "wm_league",
                    "players":   injuries_by_name[matched_key],
                }
                print(f"  ✅ {our_id} ({our_name}): "
                      f"{len(injuries_by_name[matched_key])} Einträge")

    # ── Schritt 3: /sidelined Fallback pro Team (deeper-check 09.06.2026) ──────
    # League-Endpoint pre-WM leer. /sidelined liefert aktuelle Klub-Ausfälle
    # für NT-Spieler und ist daher pre-WM die Hauptquelle.
    if team_ids:
        sidelined = fetch_sidelined_per_team(team_map, team_ids)
        for our_id, players in sidelined.items():
            # Nicht überschreiben wenn League-Endpoint schon Daten lieferte
            if our_id in injuries_out and injuries_out[our_id].get("players"):
                continue
            injuries_out[our_id] = {
                "updatedAt": now_ts,
                "source":    "sidelined",
                "players":   players,
            }

    # ── Schritt 4: _meta-Eintrag aktualisieren ─────────────────────────────────
    teams_with_data = sum(1 for k, v in injuries_out.items()
                          if k != "_meta" and isinstance(v, dict) and v.get("players"))
    injuries_out["_meta"] = {
        "updatedAt":      now_ts,
        "daysUntilWM":    days_until_wm,
        "status":         "pre_tournament" if days_until_wm > 0 else "live",
        "teamsWithData":  teams_with_data,
    }

    # ── Schritt 5: Speichern ───────────────────────────────────────────────────
    wm["injuries"] = injuries_out
    WM_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {WM_FILE.name}[\"injuries\"] geschrieben")
    print(f"   Teams mit Daten: {teams_with_data}/{len(team_map)}")


if __name__ == "__main__":
    main()
