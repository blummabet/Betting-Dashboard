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

# Aktualitätsfenster für Ausfälle (13.07.2026). /injuries?league&season liefert je FIXTURE einen
# Eintrag → über eine Saison entsteht ein Archiv statt eines Ausfallstands. Ein Ausfall, der zuletzt
# vor >21 Tagen gemeldet wurde, ist mit hoher Wahrscheinlichkeit ausgeheilt. Bewusst großzügig:
# lieber ein Eintrag zu viel als eine echte Verletzung zu übersehen.
INJURY_RECENT_DAYS = int(os.environ.get("INJURY_RECENT_DAYS", "21"))


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

    # ── 13.07.2026 (Lucas: „MLS startet Freitag — haben wir die Saisondaten am Schirm?") ──
    #
    # BEFUND: Für die MLS standen 116 „Verletzte" bei einem 30-Mann-Kader — mehr Ausfälle als
    # Spieler. Grund: /injuries?league&season liefert einen Eintrag JE FIXTURE. Über eine Saison
    # mit 15 gespielten Runden sammelt sich so ein ARCHIV aller je gefehlten Spieler an, nicht der
    # aktuelle Ausfallstand. Bei der WM (ein Turnier über 4 Wochen) fiel das nie auf.
    #
    # Wäre das ins injury-Signal gelaufen, hätten wir jedem Team eine halbe Mannschaft „verletzt"
    # gerechnet — bei jedem Spiel, dauerhaft. Dass das Signal bisher schwieg, war Glück, kein Schutz.
    #
    # FIX (universal, gilt für WM + Liga + MLS):
    #   1. je Spieler nur den JÜNGSTEN Eintrag behalten (Dedup)
    #   2. nur Einträge aus dem Aktualitätsfenster — ältere Ausfälle sind längst ausgeheilt
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    def _fix_date(e):
        raw = ((e.get("fixture") or {}).get("date") or "")[:10]
        try:
            return _dt.fromisoformat(raw).date()
        except ValueError:
            return None

    heute  = _dt.now(_tz.utc).date()
    fenster = heute - _td(days=INJURY_RECENT_DAYS)

    # Jüngster Eintrag je (Team, Spieler) gewinnt.
    latest: dict[tuple, tuple] = {}
    for e in entries:
        team_name = (e.get("team") or {}).get("name", "")
        pname     = (e.get("player") or {}).get("name", "?")
        if not team_name:
            continue
        d = _fix_date(e)
        key = (team_name, pname)
        vorher = latest.get(key)
        if vorher is None or (d and (vorher[0] is None or d > vorher[0])):
            latest[key] = (d, e)

    by_team: dict[str, list] = {}
    verworfen_alt = 0
    for (team_name, pname), (d, e) in latest.items():
        # Kein Datum → behalten (nicht beurteilbar; ein Fehlurteil wäre schlimmer als ein Eintrag zu viel).
        if d is not None and d < fenster:
            verworfen_alt += 1
            continue
        by_team.setdefault(team_name, []).append({
            "name":    pname,
            "type":    e.get("type", "Unknown"),        # "Injury" oder "Suspension"
            "reason":  e.get("reason", ""),             # z.B. "Hamstring"
            "status":  "missing",
            "fixture": ((e.get("fixture") or {}).get("date") or ""),
        })

    roh = len(entries)
    behalten = sum(len(v) for v in by_team.values())
    print(f"  ✅ {behalten} aktuelle Ausfälle für {len(by_team)} Teams "
          f"(aus {roh} Roh-Einträgen · {roh - len(latest)} Duplikate, "
          f"{verworfen_alt} älter als {INJURY_RECENT_DAYS} Tage)")
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
        # 13.07.2026: Season war hart auf WM_SEASON — im Liga-Modus die falsche Saison.
        entries = apif_get("injuries", {"team": apif_id,
                                        "season": LIGA_SEASON if _IS_LIGA else WM_SEASON})
        if not entries:
            continue

        # 13.07.2026: Dedup gab es hier schon — aber es gewann der ERSTE Eintrag (also der
        # ÄLTESTE Ausfall) und alte Einträge wurden nie verworfen. Über eine Saison landete so
        # ein im Februar verletzter, längst genesener Spieler dauerhaft im „aktuell verletzt".
        # Jetzt: jüngster Eintrag gewinnt + Aktualitätsfenster (wie im League-Pfad).
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        fenster = _dt.now(_tz.utc).date() - _td(days=INJURY_RECENT_DAYS)

        neueste: dict = {}
        for e in entries:
            name = (e.get("player") or {}).get("name", "?")
            raw  = ((e.get("fixture") or {}).get("date") or "")[:10]
            try:
                d = _dt.fromisoformat(raw).date()
            except ValueError:
                d = None
            vor = neueste.get(name)
            if vor is None or (d and (vor[0] is None or d > vor[0])):
                neueste[name] = (d, e)

        team_entries = []
        for name, (d, e) in neueste.items():
            if d is not None and d < fenster:
                continue                      # längst ausgeheilt → kein aktueller Ausfall
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

    # ── Schritt 4b: Positionen aus dem Kader-Cache nachtragen (21.07.2026, Lucas) ──
    # Der /injuries-Endpoint liefert KEINE Position → für MLS stand überall None → „(?)" + Backup-
    # Unterschätzung. squad_cache.json (teams[apifId].starters) hat name+pos → per Nachname joinen.
    try:
        import injury_positions as _ip
        _sc_path = BASE / "squad_cache.json"
        _sc = json.loads(_sc_path.read_text(encoding="utf-8")) if _sc_path.exists() else {}
        _n = _ip.enrich_injuries({k: v for k, v in injuries_out.items() if k != "_meta"}, _sc)
        print(f"  🩹 {_n} Verletzten-Positionen aus dem Kader angereichert")
    except Exception as _e:
        print(f"  ⚠️  Positions-Anreicherung übersprungen: {_e}")

    # ── Schritt 5: Speichern ───────────────────────────────────────────────────
    wm["injuries"] = injuries_out
    WM_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {WM_FILE.name}[\"injuries\"] geschrieben")
    print(f"   Teams mit Daten: {teams_with_data}/{len(team_map)}")


if __name__ == "__main__":
    main()
