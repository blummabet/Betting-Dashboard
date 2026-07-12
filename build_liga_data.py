#!/usr/bin/env python3
"""
build_liga_data.py — Top-5-Ligen in WM-Datenformat (25.06.2026, Lucas: Liga auf dem bewährten
WM-Stack statt das alte, fehleranfällige Liga-Frontend wiederzubeleben).

Erzeugt `liga-data.json` in EXAKT der Struktur von wm2026-data.json — eine Liga spielt dabei die
Rolle einer „Gruppe":
    { "groups": { "ENG": {name, flag, teams:[{id,name,elo}], fixtures:[{home,away,matchday,date,
      kickoff,venue,result}]}, "GER": {...}, ... }, "odds": {}, "picks": {}, "_meta": {...} }
Damit ziehen der bewährte WM-Renderer/Tracking/Odds/CLV/Signal-Engine fast unverändert auf den
Liga-Daten (WM-only Features via liga_default-Profil aus). Quoten füllt fetch_liga_odds.py separat.

`build_groups(...)` ist ein REINER Transformer (testbar). `main()` holt via API-Football und schreibt.
Team-„id" = API-Football-Team-ID als String (stabil); `name` für Anzeige + Odds-Matching (TheOddsAPI).
"""
from __future__ import annotations

import http.client
import json
import os
import re
import sys
from datetime import datetime, timezone

import cocobet_dataset as D

APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "")
BASE = os.path.dirname(os.path.abspath(__file__))
# 29.06.2026 (Lucas: MLS): dataset-aware — schreibt liga-data.json ODER mls-data.json je
# COCOBET_DATASET. Vorher hart liga-data.json.
OUT_FILE = str(D.data_file())

# Liga-Maps je Datensatz (API-Football league_id). Top-5: beste xG/Understat-Abdeckung.
LEAGUES_TOP5 = {
    "ENG": {"apif_id": 39,  "name": "Premier League", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "ESP": {"apif_id": 140, "name": "La Liga",        "flag": "🇪🇸"},
    "GER": {"apif_id": 78,  "name": "Bundesliga",     "flag": "🇩🇪"},
    "ITA": {"apif_id": 135, "name": "Serie A",        "flag": "🇮🇹"},
    "FRA": {"apif_id": 61,  "name": "Ligue 1",        "flag": "🇫🇷"},
}
# MLS (Brücken-Liga nach der WM). league_id 253 — beim 1. Lauf prüfen: 0 Fixtures ⇒ ID korrigieren.
LEAGUES_MLS = {
    "MLS": {"apif_id": 253, "name": "Major League Soccer", "flag": "🇺🇸"},
}

# Datensatz → Liga-Definitionen (mit Anzeige-Metadaten). 'liga' = Top-5, 'mls' = MLS.
_DATASET_LEAGUE_DEFS = {"liga": LEAGUES_TOP5, "mls": LEAGUES_MLS}


def _active_league_defs() -> dict:
    return _DATASET_LEAGUE_DEFS.get(D.active_dataset(), LEAGUES_TOP5)


def _crest(tid) -> str:
    """Liga-Teams haben keine Länder-Flagge → API-Football-Logo als Crest (25.06.2026, Lucas).
    Wird ins `flag`-Feld gelegt, damit es in ALLEN bestehenden flag-Stellen (Cards + Tracking)
    automatisch greift, ohne den Renderer anzufassen."""
    return (f'<img src="https://media.api-sports.io/football/teams/{tid}.png" '
            f'style="width:18px;height:18px;vertical-align:middle;object-fit:contain;" '
            f'loading="lazy" alt="">')


def current_season(now: datetime | None = None) -> int:
    """API-Football-Saison = Startjahr. Ab Juni zählt die kommende Saison (Sommer-Fenster)."""
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def _parse_round(round_str: str) -> int | None:
    """'Regular Season - 1' → 1. None wenn nicht parsebar (Playoff/Relegation etc.)."""
    m = re.search(r"(\d+)\s*$", str(round_str or ""))
    return int(m.group(1)) if m else None


def _status_map(short: str) -> str:
    """API-Football-Status → unser Schema (FT/AET/PEN beendet, sonst NS/LIVE)."""
    s = (short or "NS").upper()
    if s in ("FT", "AET", "PEN", "AWD", "WO"):
        return s
    if s in ("1H", "2H", "HT", "ET", "P", "LIVE", "INT", "BT"):
        return "LIVE"
    return "NS"


def build_groups(standings_by_league: dict, fixtures_by_league: dict,
                 elo_by_team: dict | None = None, league_defs: dict | None = None) -> dict:
    """REINER Transformer: API-Responses → groups-Struktur im WM-Format.
    standings_by_league: {league_key: <API /standings response>}
    fixtures_by_league:  {league_key: <API /fixtures response>}
    elo_by_team:         optional {team_id_str: elo}
    league_defs:         optional {code: {apif_id,name,flag}} — default = aktiver Datensatz
                         (Top-5 oder MLS). Explizit übergebbar für Tests.
    """
    elo_by_team = elo_by_team or {}
    league_defs = league_defs or _active_league_defs()
    groups = {}
    for lk, cfg in league_defs.items():
        # ── Teams aus Standings ──
        teams = []
        seen = set()
        st_resp = (standings_by_league.get(lk) or {})
        for blk in (st_resp.get("response") or []):
            league = (blk.get("league") or {})
            for table in (league.get("standings") or []):
                for row in (table or []):
                    t = (row.get("team") or {})
                    tid = t.get("id")
                    if tid is None or tid in seen:
                        continue
                    seen.add(tid)
                    teams.append({
                        "id":   str(tid),
                        "name": t.get("name") or str(tid),
                        "logo": t.get("logo") or f"https://media.api-sports.io/football/teams/{tid}.png",
                        "flag": _crest(tid),
                        "elo":  elo_by_team.get(str(tid)),
                    })
        # ── Fixtures ──
        fixtures = []
        fx_resp = (fixtures_by_league.get(lk) or {})
        for item in (fx_resp.get("response") or []):
            fxo = (item.get("fixture") or {})
            tm  = (item.get("teams") or {})
            gl  = (item.get("goals") or {})
            lg  = (item.get("league") or {})
            home = (tm.get("home") or {})
            away = (tm.get("away") or {})
            if home.get("id") is None or away.get("id") is None:
                continue
            iso = fxo.get("date")   # ISO mit TZ
            status_short = ((fxo.get("status") or {}).get("short")) or "NS"
            ourstat = _status_map(status_short)
            result = None
            if ourstat in ("FT", "AET", "PEN"):
                result = {"status": ourstat,
                          "home_score": gl.get("home"), "away_score": gl.get("away")}
            # Teams AUCH aus Fixtures ableiten (25.06.2026, Lucas: „nichts da"). Vorsaison hat noch
            # keine Standings → sonst blieben teams=[] obwohl Fixtures existieren.
            for _t in (home, away):
                _tid = _t.get("id")
                if _tid is not None and _tid not in seen:
                    seen.add(_tid)
                    teams.append({"id": str(_tid), "name": _t.get("name") or str(_tid),
                                  "logo": _t.get("logo") or f"https://media.api-sports.io/football/teams/{_tid}.png",
                                  "flag": _crest(_tid), "elo": elo_by_team.get(str(_tid))})
            fixtures.append({
                "home":     str(home.get("id")),
                "away":     str(away.get("id")),
                "homeName": home.get("name"),
                "awayName": away.get("name"),
                "matchday": _parse_round(lg.get("round")),
                "date":     (iso or "")[:10] or None,
                "kickoff":  iso,
                "venue":    ((fxo.get("venue") or {}).get("name")),
                "fid":      fxo.get("id"),   # API-Fixture-ID (für Post-Match-xG, 26.06.2026)
                "result":   result,
            })
        fixtures.sort(key=lambda f: (f.get("kickoff") or "", f.get("home") or ""))
        groups[lk] = {"name": cfg["name"], "flag": cfg["flag"],
                      "teams": teams, "fixtures": fixtures}
    return groups


# ───────────────────────── Live-Fetch (API-Football) ─────────────────────────

def _api_get(path: str) -> dict | None:
    if not APIF_KEY:
        return None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        conn.close()
        if resp.status != 200:
            print(f"  ⚠️  API-Football {resp.status} bei {path}: {raw[:160]}")
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"  ⚠️  API-Fehler {path}: {e}")
        return None


def merge_groups_preserve(old_groups, new_groups) -> tuple[dict, list]:
    """WIPE-SCHUTZ (12.07.2026, Lucas: „Liga-Cards kaputt"). Der API-Zugang lief über Nacht ab →
    /fixtures lieferte 0 Ergebnisse → build_liga_data überschrieb mls-data.json mit LEEREN groups
    (0 Teams/0 Fixtures). Die Liga-Cards-Ansicht merged mls-data.json mit → verwaiste Picks auf
    nicht-existente Fixtures/Teams → National-Ansicht kippte.

    Regel: eine Liga-Gruppe wird NIE mit LEER überschrieben, solange die bestehende Datei dafür
    Daten hat. Ligen, die im neuen Build ganz fehlen, bleiben ebenfalls erhalten.
    Returns (merged_groups, kept_league_keys). Rein/testbar."""
    old_groups = old_groups if isinstance(old_groups, dict) else {}
    new_groups = new_groups if isinstance(new_groups, dict) else {}
    merged: dict = {}
    kept: list = []
    for lk, g in new_groups.items():
        g = g or {}
        n_new = len(g.get("fixtures") or []) + len(g.get("teams") or [])
        old = old_groups.get(lk) or {}
        n_old = len(old.get("fixtures") or []) + len(old.get("teams") or [])
        if n_new == 0 and n_old > 0:
            merged[lk] = old          # API lieferte nichts → alten Stand BEHALTEN
            kept.append(lk)
        else:
            merged[lk] = g
    for lk, old in old_groups.items():   # Ligen die im Build ganz fehlen, aber alt da sind
        if lk not in merged:
            merged[lk] = old
            kept.append(lk)
    return merged, kept


def main():
    season = int(os.environ.get("LIGA_SEASON") or current_season())
    print(f"=== build_liga_data.py — Saison {season} ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen (läuft nur im Workflow).")
        sys.exit(0)

    league_defs = _active_league_defs()
    print(f"  Datensatz: {D.active_dataset()} · Ligen: {list(league_defs)}")
    standings_by_league, fixtures_by_league = {}, {}
    for lk, cfg in league_defs.items():
        lid = cfg["apif_id"]
        standings_by_league[lk] = _api_get(f"/standings?league={lid}&season={season}") or {}
        fixtures_by_league[lk]  = _api_get(f"/fixtures?league={lid}&season={season}") or {}
        nfx = len((fixtures_by_league[lk].get("response") or []))
        print(f"  {lk}: {nfx} Fixtures geladen")
        if nfx == 0:
            print(f"  ⚠️  {lk}: 0 Fixtures — league_id {lid} oder Saison {season} prüfen!")

    # Elo aus vorhandenem Cache (optional), Schlüssel = team_id-String
    elo = {}
    for cache in ("stats_cache.json", "league_fallback_cache.json"):
        p = os.path.join(BASE, cache)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    _c = json.load(f)
                # bestmöglich: nach {id: elo} durchsuchen (defensiv, Struktur variiert)
                def _scan(o):
                    if isinstance(o, dict):
                        if "id" in o and "elo" in o and o.get("elo"):
                            elo.setdefault(str(o["id"]), o["elo"])
                        for v in o.values():
                            _scan(v)
                    elif isinstance(o, list):
                        for v in o:
                            _scan(v)
                _scan(_c)
            except Exception:
                pass

    groups = build_groups(standings_by_league, fixtures_by_league, elo, league_defs)

    # Bestehende liga-data.json mergen (odds/picks/Opening NICHT überschreiben)
    wm = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, encoding="utf-8") as f:
                wm = json.load(f)
        except Exception:
            wm = {}
    # ── WIPE-SCHUTZ (12.07.2026, Lucas: „Liga-Cards kaputt") ─────────────────────────────
    merged_groups, kept = merge_groups_preserve(wm.get("groups"), groups)
    if kept:
        print(f"  🛡️  API lieferte 0 Daten für {sorted(set(kept))} — bestehende Gruppen BEHALTEN "
              f"(kein Wipe). API-Key/Quota prüfen!")
    if sum(len(g.get("fixtures") or []) for g in merged_groups.values()) == 0:
        print("  ❌  Kein einziges Fixture (API-Ausfall/Key abgelaufen?) — Datei NICHT "
              "überschrieben, alter Stand bleibt erhalten.")
        sys.exit(1)

    wm["groups"] = merged_groups
    groups = merged_groups
    # teamIds-Identitäts-Map (25.06.2026, Lucas): Liga-Team-id IST schon die API-Football-ID →
    # so funktioniert der WM-Form-/H2H-Fetcher (nutzt wm["teamIds"][code]=api_id) direkt für Liga.
    _tids = {}
    for g in groups.values():
        for t in g.get("teams", []):
            try:
                _tids[t["id"]] = int(t["id"])
            except Exception:
                pass
    wm["teamIds"] = _tids
    wm.setdefault("odds", {})
    wm.setdefault("picks", {})
    wm.setdefault("_meta", {})
    wm["_meta"]["profile"] = D.active_profile()
    wm["_meta"]["season"] = season
    wm["_meta"]["dataUpdatedAt"] = datetime.now(timezone.utc).isoformat()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)
    n_fx = sum(len(g["fixtures"]) for g in groups.values())
    n_tm = sum(len(g["teams"]) for g in groups.values())
    print(f"  ✅ liga-data.json: {len(groups)} Ligen · {n_tm} Teams · {n_fx} Fixtures")


if __name__ == "__main__":
    main()
