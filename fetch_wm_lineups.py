#!/usr/bin/env python3
"""
fetch_wm_lineups.py — WM Aufstellungen 1h vor Anpfiff
=======================================================

Holt für jedes Spiel mit Anpfiff in den nächsten N Stunden die offiziellen
Aufstellungen (Starting-11 + Bench) aus API-Football's `/fixtures/lineups`
Endpoint. Speichert pro Fixture die Lineup-Daten.

Wird vom `lineup_signal` (sharp_signals/lineup_signal.py) konsumiert um
Top-Scorer-Bank-Erkennung und Rotation-Detection zu liefern.

Output (wm_lineups.json):
    {
      "MEX-ZAF": {
        "fixture_id": 1234567,
        "kickoff": "2026-06-11T19:00:00+00:00",
        "home": {
          "team_id": 26,
          "team_name": "Mexico",
          "formation": "4-3-3",
          "coach": "...",
          "starting": [{"id": 1234, "name": "R. Jiménez", "pos": "F", "grid": "..."}],
          "subs":     [{"id": 5678, "name": "...", "pos": "M"}]
        },
        "away": {...},
        "fetchedAt": "2026-06-11T18:05:00+00:00"
      }
    }

Refactor-Standards:
  - Config aus cocobet_config.json profiles.<active>.lineups
  - state_files_registry.json: wm_lineups.json registriert
  - Tests in tests/test_fetch_wm_lineups.py
  - Liga-fähig: APIF_NAME_OVERRIDE wiederverwendet aus fetch_wm_nt_xg
  - Fail-safe: continue-on-error, idempotent (fetched fixtures werden cached)

Run:    python3 fetch_wm_lineups.py [--force] [--match=MEX-ZAF]
Cron:   Hourly (T-3h → T-0) via manage-wm-poly.yml oder eigener Workflow
"""
from __future__ import annotations
import json
import os
import sys
import time
import http.client
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE          = Path(__file__).parent
WM_FILE       = BASE / "wm2026-data.json"
OUTPUT_FILE   = BASE / "wm_lineups.json"
APIF_HOST     = "v3.football.api-sports.io"
APIF_KEY      = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")

# ── Config ────────────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "lookahead_hours":         3,    # nur Spiele in den nächsten N Stunden
    "lookback_hours":         24,    # falls Spiel schon angefangen: noch N Stunden zurück
    "min_minutes_before":     30,    # erst ab T-N min lineups verfügbar (~1h normal)
    "max_minutes_before":    180,    # T-3h obere Grenze
    "request_delay_sec":     1.0,
    "request_timeout_sec":    15,
    "cache_ttl_minutes":      45,    # nur neu fetchen wenn cache älter als N min
}


def _load_cfg() -> dict:
    try:
        cfg_path = BASE / "cocobet_config.json"
        if not cfg_path.exists():
            return DEFAULT_CFG
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        override = raw["profiles"].get(active, {}).get("lineups") or {}
        return {**DEFAULT_CFG, **override}
    except Exception:
        return DEFAULT_CFG


CFG = _load_cfg()


# ── HTTP-Layer ────────────────────────────────────────────────────────────


def _apif_get(path: str, timeout: int | None = None) -> dict | None:
    timeout = timeout or CFG["request_timeout_sec"]
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=timeout)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            print(f"   ⚠️  HTTP {resp.status} bei {path[:80]}")
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


# ── Fixture-Lookups ───────────────────────────────────────────────────────


def _load_wm_fixtures() -> list[dict]:
    """Liest die Fixtures aus wm2026-data.json."""
    if not WM_FILE.exists():
        return []
    try:
        with WM_FILE.open(encoding="utf-8") as f:
            wm = json.load(f)
        out = []
        for grp_id, grp in wm.get("groups", {}).items():
            for fx in grp.get("fixtures", []):
                if fx.get("date") and fx.get("home") and fx.get("away"):
                    out.append({
                        "match_key": f"{fx['home']}-{fx['away']}",
                        "home_id":   fx["home"],
                        "away_id":   fx["away"],
                        "date":      fx["date"],
                        "time":      fx.get("time", "21:00"),
                        "group":     grp_id,
                        "matchday":  fx.get("matchday"),
                    })
        return out
    except Exception as e:
        print(f"⚠️  Fehler beim Laden {WM_FILE.name}: {e}")
        return []


def _kickoff_utc(date_str: str, time_str: str) -> datetime | None:
    """Konvertiert YYYY-MM-DD + HH:MM (lokal Wien) → UTC datetime."""
    try:
        # Annahme: time ist lokale Spielort-Zeit (vereinfacht UTC+0 für MVP)
        # In Produktion: per Venue-Timezone konvertieren.
        return datetime.fromisoformat(f"{date_str}T{time_str}:00+00:00")
    except Exception:
        return None


def _is_fixture_due(fx: dict, now_utc: datetime) -> bool:
    """Spiel pfeift in lookahead-Range an?"""
    ko = _kickoff_utc(fx["date"], fx["time"])
    if ko is None:
        return False
    delta = (ko - now_utc).total_seconds() / 60.0   # minuten bis Anpfiff
    # Nur wenn -lookback < delta < lookahead
    if delta < -CFG["lookback_hours"] * 60:
        return False
    if delta > CFG["lookahead_hours"] * 60:
        return False
    return True


def _is_cache_fresh(entry: dict) -> bool:
    """Existing entry frisch (<TTL)?"""
    if not entry:
        return False
    try:
        ts = datetime.fromisoformat(entry["fetchedAt"])
        age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
        return age_min < CFG["cache_ttl_minutes"]
    except Exception:
        return False


# ── Lineup-Lookup ─────────────────────────────────────────────────────────


def _find_apif_fixture_id(home_name: str, away_name: str, ko: datetime) -> int | None:
    """
    Sucht die API-Football fixture_id für ein Spiel über Datum.
    Nutzt /fixtures?date=YYYY-MM-DD und sucht nach Heim/Auswärts-Namen.
    """
    date_str = ko.strftime("%Y-%m-%d")
    data = _apif_get(f"/fixtures?date={date_str}")
    if not data or not data.get("response"):
        return None
    target_h = home_name.lower().strip()
    target_a = away_name.lower().strip()
    for fx in data["response"]:
        teams = fx.get("teams", {})
        h_name = (teams.get("home") or {}).get("name", "").lower().strip()
        a_name = (teams.get("away") or {}).get("name", "").lower().strip()
        if (target_h in h_name or h_name in target_h) and \
           (target_a in a_name or a_name in target_a):
            return (fx.get("fixture") or {}).get("id")
    return None


def _parse_lineup_entry(player_block: dict) -> dict:
    """Konvertiert API-Football's player-Block zu unserem flachen Format."""
    p = (player_block or {}).get("player", {})
    return {
        "id":   p.get("id"),
        "name": p.get("name", ""),
        "pos":  p.get("pos", ""),   # G/D/M/F
        "grid": p.get("grid"),       # "1:1" etc. für Formation-Position
        "num":  p.get("number"),
    }


def _fetch_lineup_for_fixture(fixture_id: int) -> dict | None:
    """Holt /fixtures/lineups?fixture=ID und konvertiert zu unserem Schema."""
    data = _apif_get(f"/fixtures/lineups?fixture={fixture_id}")
    if not data or not data.get("response") or len(data["response"]) < 2:
        return None
    home_block, away_block = data["response"][:2]

    def _team_dict(block):
        return {
            "team_id":   (block.get("team") or {}).get("id"),
            "team_name": (block.get("team") or {}).get("name"),
            "formation": block.get("formation"),
            "coach":     (block.get("coach") or {}).get("name"),
            "starting":  [_parse_lineup_entry(p) for p in (block.get("startXI") or [])],
            "subs":      [_parse_lineup_entry(p) for p in (block.get("substitutes") or [])],
        }

    return {"home": _team_dict(home_block), "away": _team_dict(away_block)}


# ── Main-Pipeline ─────────────────────────────────────────────────────────


def _load_existing() -> dict:
    if not OUTPUT_FILE.exists():
        return {}
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_output(data: dict) -> None:
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUTPUT_FILE)


def _team_name_from_id(team_id: str) -> str:
    """
    Konvertiert unseren 3-Buchstaben-Team-Code zu API-Football-Namen.
    Importiert das Mapping aus fetch_wm_nt_xg um Single-Source-Of-Truth zu wahren.
    """
    try:
        from fetch_wm_nt_xg import APIF_NAME_OVERRIDE
        return APIF_NAME_OVERRIDE.get(team_id, team_id)
    except Exception:
        return team_id


def main():
    args = sys.argv[1:]
    force      = "--force" in args
    only_match = next((a.split("=", 1)[1] for a in args if a.startswith("--match=")), None)

    print("=== fetch_wm_lineups.py ===\n")
    print(f"   lookahead={CFG['lookahead_hours']}h, lookback={CFG['lookback_hours']}h, "
          f"cache_ttl={CFG['cache_ttl_minutes']}min\n")

    fixtures = _load_wm_fixtures()
    if only_match:
        fixtures = [fx for fx in fixtures if fx["match_key"] == only_match]
    if not fixtures:
        print("⚠️  Keine Fixtures gefunden")
        return 1

    now_utc = datetime.now(timezone.utc)
    existing = _load_existing()

    due = [fx for fx in fixtures if _is_fixture_due(fx, now_utc)]
    print(f"   {len(due)} Spiele im Lookahead-Range (von {len(fixtures)} total)")

    if not due:
        print("   Keine Spiele in den nächsten Stunden — sauberer Exit")
        return 0

    new_count = 0
    cached_count = 0
    fail_count = 0

    for fx in due:
        mk = fx["match_key"]
        entry = existing.get(mk)
        if not force and _is_cache_fresh(entry):
            cached_count += 1
            print(f"   ✓ {mk}: Cache frisch ({entry.get('fetchedAt', '?')[:19]}) — skip")
            continue

        home_name = _team_name_from_id(fx["home_id"])
        away_name = _team_name_from_id(fx["away_id"])
        ko = _kickoff_utc(fx["date"], fx["time"])

        print(f"\n🔎 {mk} ({home_name} vs {away_name}) @ {fx['date']} {fx['time']}:")

        # Lookup fixture_id (re-use cached wenn vorhanden)
        fixture_id = (entry or {}).get("fixture_id")
        if not fixture_id:
            time.sleep(CFG["request_delay_sec"])
            fixture_id = _find_apif_fixture_id(home_name, away_name, ko)
            if not fixture_id:
                print(f"   ⚠️  APIF fixture_id nicht gefunden — skip")
                fail_count += 1
                continue
            print(f"   ↪ APIF fixture_id: {fixture_id}")

        time.sleep(CFG["request_delay_sec"])
        lineup = _fetch_lineup_for_fixture(fixture_id)
        if lineup is None:
            print(f"   ⚠️  Lineup noch nicht verfügbar (zu früh?)")
            fail_count += 1
            continue

        entry_new = {
            "fixture_id": fixture_id,
            "kickoff":    ko.isoformat() if ko else None,
            "home":       lineup["home"],
            "away":       lineup["away"],
            "fetchedAt":  datetime.now(timezone.utc).isoformat(),
        }
        existing[mk] = entry_new
        new_count += 1
        print(f"   ✅ Lineups geholt: "
              f"{len(lineup['home']['starting'])}+{len(lineup['home']['subs'])} | "
              f"{len(lineup['away']['starting'])}+{len(lineup['away']['subs'])} "
              f"({lineup['home']['formation']} vs {lineup['away']['formation']})")
        _save_output(existing)

    print(f"\n=== Done: {new_count} neu, {cached_count} cached, {fail_count} fail ===")
    print(f"   → {OUTPUT_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
