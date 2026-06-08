#!/usr/bin/env python3
"""
fetch_wm_nt_xg.py — Nationalmannschafts-xG aus API-Football
============================================================

Holt für jedes der 48 WM-2026 Teams die letzten ~N Nationalmannschafts-Spiele
und aggregiert daraus `expected_goals` aus dem `/fixtures/statistics`-Endpoint
zu Team-Level xG-Stats.

Zielt auf die Coverage-Lücke ab: Understat liefert xG nur für Europa-Teams
(~15 von 48). Diese Pipeline liefert xG für die restlichen ~33 Teams
(CONMEBOL, AFC, AFR, CONCACAF, OFC) direkt aus Nationalmannschafts-Spielen.

Output (wm_nt_xg.json):
    {
      "MEX": {
        "xgForAvg":      1.32,
        "xgAgainstAvg":  0.85,
        "games":          7,
        "source":         "apif_fixtures_statistics",
        "fixture_ids":   [1234, 1235, ...],
        "updatedAt":     "2026-06-08T12:00:00+00:00"
      },
      ...
    }

Wird in `generate_wm_picks.py` mit dem existing `xgStats` Block (Understat)
gemerged — Understat hat Priorität, NT-xG füllt Lücken.

Refactor-Standards:
  - Config aus cocobet_config.json
  - state_files_registry.json: wm_nt_xg.json registriert
  - Tests in tests/test_fetch_wm_nt_xg.py
  - Liga-fähig: APIF_NAME_OVERRIDE wiederverwendet aus fetch_wm_squads.py

Run:    python3 fetch_wm_nt_xg.py [--force] [--team=MEX]
Cron:   Wöchentlich via fetch-wm-data.yml (vor generate_wm_picks)
"""
from __future__ import annotations
import json
import os
import sys
import time
import http.client
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path(__file__).parent
WM_FILE       = BASE / "wm2026-data.json"
OUTPUT_FILE   = BASE / "wm_nt_xg.json"
APIF_HOST     = "v3.football.api-sports.io"
APIF_KEY      = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")

# ── Config (cocobet_config.json profile.nt_xg) ────────────────────────────
DEFAULT_CFG = {
    "lookback_fixtures":   10,    # max letzte Spiele pro Team
    "min_fixtures":         3,    # darunter keine Aggregation
    "fixtures_max_age_days": 540, # älter als 1.5 Jahre ignorieren
    "request_delay_sec":   1.2,   # zwischen API-Calls
    "request_timeout_sec": 15,
    "skip_if_understat":  False,  # True: skip Teams die in xgStats schon Understat haben
}


def _load_cfg() -> dict:
    """Liest cocobet_config.json profile-spezifisch oder fällt auf Defaults."""
    try:
        cfg_path = BASE / "cocobet_config.json"
        if not cfg_path.exists():
            return DEFAULT_CFG
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        prof = raw["profiles"].get(active, {})
        override = prof.get("nt_xg") or {}
        return {**DEFAULT_CFG, **override}
    except Exception as e:
        print(f"⚠️  Config-Lookup fehlgeschlagen ({e}) — Defaults aktiv")
        return DEFAULT_CFG


CFG = _load_cfg()


# ── API-Football Team-Name-Mapping (wiederverwendet aus fetch_wm_squads.py) ─
# Single Source of Truth: hier explizit kopiert damit fetch_wm_nt_xg.py
# standalone läuft. Bei Updates BEIDE Files synchronisieren.
APIF_NAME_OVERRIDE: dict[str, str] = {
    "ARG": "Argentina", "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium",
    "BIH": "Bosnia", "BRA": "Brazil", "CAN": "Canada", "CIV": "Ivory Coast",
    "COD": "Congo DR", "COL": "Colombia", "CPV": "Cape Verde", "CRO": "Croatia",
    "CUW": "Curacao", "CZE": "Czech Republic", "DZA": "Algeria", "ECU": "Ecuador",
    "EGY": "Egypt", "ENG": "England", "ESP": "Spain", "FRA": "France",
    "GER": "Germany", "GHA": "Ghana", "HTI": "Haiti", "IRN": "Iran",
    "IRQ": "Iraq", "JOR": "Jordan", "JPN": "Japan", "KOR": "South Korea",
    "MAR": "Morocco", "MEX": "Mexico", "NED": "Netherlands", "NOR": "Norway",
    "NZL": "New Zealand", "PAN": "Panama", "POR": "Portugal", "PRY": "Paraguay",
    "QAT": "Qatar", "SAU": "Saudi Arabia", "SCO": "Scotland", "SEN": "Senegal",
    "SUI": "Switzerland", "SWE": "Sweden", "TUN": "Tunisia", "TUR": "Türkiye",
    "URU": "Uruguay", "USA": "United States", "UZB": "Uzbekistan", "ZAF": "South Africa",
}


# ── HTTP-Layer ────────────────────────────────────────────────────────────


def _apif_get(path: str, timeout: int = 15) -> dict | None:
    """
    GET-Call zu API-Football mit Header-Auth. Returns parsed JSON oder None.
    Logged Errors mit Status-Code.
    """
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=timeout)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            print(f"   ⚠️  HTTP {resp.status} bei {path[:80]}: {body[:200]}")
            return None
        return json.loads(body)
    except Exception as e:
        print(f"   ⚠️  Request-Fehler bei {path[:80]}: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _find_team_id(team_name: str) -> int | None:
    """Sucht die API-Football Team-ID für eine Nationalmannschaft."""
    data = _apif_get(f"/teams?name={team_name.replace(' ', '%20')}")
    if not data or not data.get("response"):
        return None
    # Filter: nur Nationalmannschaften (kein Club)
    for entry in data["response"]:
        team = entry.get("team", {})
        if team.get("national") is True:
            return team.get("id")
    # Fallback: erstes Result
    return data["response"][0].get("team", {}).get("id")


def _list_recent_fixtures(team_id: int, max_n: int) -> list[dict]:
    """
    Holt die letzten `max_n` Spiele des Teams (status=Finished).
    Filtert nach Alter (CFG.fixtures_max_age_days).
    """
    cutoff_ts = time.time() - CFG["fixtures_max_age_days"] * 86400
    data = _apif_get(f"/fixtures?team={team_id}&last={max_n}")
    if not data or not data.get("response"):
        return []
    fixtures = []
    for fx in data["response"]:
        fixture = fx.get("fixture", {})
        status_short = (fixture.get("status") or {}).get("short", "")
        if status_short not in ("FT", "AET", "PEN"):
            continue
        try:
            ts = datetime.fromisoformat(
                fixture["date"].replace("Z", "+00:00")).timestamp()
            if ts < cutoff_ts:
                continue
        except Exception:
            pass
        fixtures.append({
            "id":   fixture.get("id"),
            "date": fixture.get("date"),
            "home_id": (fx.get("teams") or {}).get("home", {}).get("id"),
            "away_id": (fx.get("teams") or {}).get("away", {}).get("id"),
        })
    return fixtures


def _extract_xg_from_statistics(fixture_id: int) -> dict[int, dict]:
    """
    Holt /fixtures/statistics?fixture=ID und extrahiert expected_goals pro Team.
    Returns {team_id: {"xg": float}} oder {} falls nicht verfügbar.
    """
    data = _apif_get(f"/fixtures/statistics?fixture={fixture_id}")
    if not data or not data.get("response"):
        return {}
    out: dict[int, dict] = {}
    for team_stats in data["response"]:
        team_id = (team_stats.get("team") or {}).get("id")
        stats_list = team_stats.get("statistics") or []
        xg_val = None
        for s in stats_list:
            name = (s.get("type") or "").lower().replace("_", " ").strip()
            # API-Football labelt unterschiedlich je Liga:
            #   "expected_goals", "Expected Goals", "xG"
            if "expected goals" in name or name == "xg":
                v = s.get("value")
                # Werte kommen oft als String "1.23" oder None
                if v is None or v == "":
                    continue
                try:
                    xg_val = float(str(v))
                except (ValueError, TypeError):
                    continue
                break
        if xg_val is not None and team_id:
            out[team_id] = {"xg": xg_val}
    return out


# ── Aggregations-Kern ─────────────────────────────────────────────────────


def aggregate_team_xg(team_apif_id: int, our_id: str) -> dict | None:
    """
    Aggregiert xG für ein Team aus den letzten N Nationalmannschafts-Spielen.

    Returns:
      {
        "xgForAvg":     float,
        "xgAgainstAvg": float,
        "games":        int,
        "source":       "apif_fixtures_statistics",
        "fixture_ids":  list[int],
        "updatedAt":    iso8601
      }
      oder None wenn nicht genug Daten.
    """
    fixtures = _list_recent_fixtures(team_apif_id, CFG["lookback_fixtures"])
    if len(fixtures) < CFG["min_fixtures"]:
        print(f"   ↪ {our_id}: nur {len(fixtures)} Fixtures gefunden — überspringe")
        return None

    xg_for_total = 0.0
    xg_ag_total  = 0.0
    games        = 0
    fixture_ids  = []

    for fx in fixtures:
        time.sleep(CFG["request_delay_sec"])
        team_xgs = _extract_xg_from_statistics(fx["id"])
        if team_apif_id not in team_xgs:
            continue
        # Gegner-ID bestimmen
        opp_id = fx["away_id"] if fx["home_id"] == team_apif_id else fx["home_id"]
        if opp_id is None or opp_id not in team_xgs:
            continue
        xg_for_total += team_xgs[team_apif_id]["xg"]
        xg_ag_total  += team_xgs[opp_id]["xg"]
        games        += 1
        fixture_ids.append(fx["id"])

    if games < CFG["min_fixtures"]:
        print(f"   ↪ {our_id}: nur {games} Fixtures mit xG-Daten — überspringe")
        return None

    return {
        "xgForAvg":     round(xg_for_total / games, 3),
        "xgAgainstAvg": round(xg_ag_total / games, 3),
        "games":        games,
        "source":       "apif_fixtures_statistics",
        "fixture_ids":  fixture_ids,
        "updatedAt":    datetime.now(timezone.utc).isoformat(),
    }


# ── Main-Pipeline ─────────────────────────────────────────────────────────


def _load_wm_teams() -> list[str]:
    """Liest die 48 WM-Teams aus wm2026-data.json."""
    if not WM_FILE.exists():
        print(f"⚠️  {WM_FILE.name} nicht gefunden")
        return []
    try:
        with WM_FILE.open(encoding="utf-8") as f:
            wm = json.load(f)
        groups = wm.get("groups", {})
        teams = []
        for grp in groups.values():
            for t in (grp.get("teams") or []):
                if isinstance(t, dict) and t.get("id"):
                    teams.append(t["id"])
        return teams
    except Exception as e:
        print(f"⚠️  Fehler beim Laden {WM_FILE.name}: {e}")
        return []


def _load_existing() -> dict:
    """Liest wm_nt_xg.json oder gibt leeres Dict zurück."""
    if not OUTPUT_FILE.exists():
        return {}
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_output(data: dict) -> None:
    """Speichert atomar."""
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUTPUT_FILE)


def main():
    args = sys.argv[1:]
    force      = "--force" in args
    only_team  = next((a.split("=", 1)[1] for a in args if a.startswith("--team=")), None)

    print("=== fetch_wm_nt_xg.py ===\n")
    print(f"   Config: lookback={CFG['lookback_fixtures']}, "
          f"min_fixtures={CFG['min_fixtures']}, "
          f"max_age={CFG['fixtures_max_age_days']}d, "
          f"skip_understat={CFG['skip_if_understat']}\n")

    teams = _load_wm_teams()
    if only_team:
        teams = [t for t in teams if t == only_team]
    if not teams:
        print("⚠️  Keine Teams gefunden — Abbruch")
        return 1

    existing = _load_existing()

    # Optional: Teams die schon Understat-xG haben überspringen
    skip_understat_teams: set[str] = set()
    if CFG["skip_if_understat"]:
        try:
            with WM_FILE.open(encoding="utf-8") as f:
                wm = json.load(f)
            understat = wm.get("xgStats", {})
            skip_understat_teams = {
                tid for tid, v in understat.items()
                if isinstance(v, dict) and (v.get("source") or "understat") == "understat"
            }
        except Exception:
            pass

    print(f"   Zu verarbeitende Teams: {len(teams)}")
    if skip_understat_teams:
        print(f"   Überspringe (Understat-xG vorhanden): {len(skip_understat_teams)}")

    new_count = 0
    skip_count = 0
    fail_count = 0

    for our_id in teams:
        if our_id in skip_understat_teams:
            skip_count += 1
            continue

        # Soft-skip: wenn schon vorhanden und nicht --force, nur refreshen falls > 14 Tage alt
        if not force and our_id in existing:
            try:
                ts = datetime.fromisoformat(existing[our_id]["updatedAt"]).timestamp()
                if (time.time() - ts) < 14 * 86400:
                    print(f"   ✓ {our_id} aktuell ({existing[our_id]['games']} games) — skip")
                    skip_count += 1
                    continue
            except Exception:
                pass

        apif_name = APIF_NAME_OVERRIDE.get(our_id)
        if not apif_name:
            print(f"   ⚠️  {our_id}: kein APIF-Name-Mapping — skip")
            fail_count += 1
            continue

        print(f"\n🔎 {our_id} ({apif_name}):")
        time.sleep(CFG["request_delay_sec"])
        team_id = _find_team_id(apif_name)
        if not team_id:
            print(f"   ⚠️  Team-ID nicht gefunden")
            fail_count += 1
            continue

        result = aggregate_team_xg(team_id, our_id)
        if result is None:
            fail_count += 1
            continue

        existing[our_id] = result
        new_count += 1
        print(f"   ✅ xG-For: {result['xgForAvg']}, xG-Against: {result['xgAgainstAvg']} "
              f"({result['games']} games)")
        # Atomar nach jedem Team — fail-safe gegen Abbrüche
        _save_output(existing)

    print(f"\n=== Done: {new_count} neu, {skip_count} skipped, {fail_count} fail ===")
    print(f"   → {OUTPUT_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
