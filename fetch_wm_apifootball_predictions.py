#!/usr/bin/env python3
"""
fetch_wm_apifootball_predictions.py — Externes Modell zum Cross-Check
========================================================================

Holt das Pricing-Modell von API-Football per `/predictions?fixture={id}`
für anstehende WM-Spiele. API-Football's Modell ist UNABHÄNGIG von unserem
Skellam+Elo Hybrid → liefert ein echtes externes Modell für Cross-Check.

Output (wm_apif_predictions.json):
    {
      "MEX-ZAF": {
        "fixture_id": 1234567,
        "kickoff":    "2026-06-11T19:00:00+00:00",
        "percent": {
          "home": 0.62,        # API-Football's implied prob
          "draw": 0.22,
          "away": 0.16
        },
        "advice":         "Mexico to win",
        "winner_team_id": 26,
        "winner_team":    "Mexico",
        "comparison":     {...},      # raw block für Modal/Debug
        "fetchedAt":      "..."
      }
    }

Wird vom Signal `apif_predictions` (sharp_signals/apif_predictions.py)
konsumiert: vergleicht API-Football's implied prob mit Pinnacle für den
gepickten Outcome — bei Übereinstimmung confirmatory positiv, bei Divergenz
warnend negativ.

Refactor-Standards:
  - Config aus cocobet_config.json profiles.<active>.apif_predictions
  - state_files_registry.json: wm_apif_predictions.json registriert
  - Tests in tests/test_fetch_wm_apifootball_predictions.py
  - Liga-fähig: APIF_NAME_OVERRIDE Reuse
  - Cached 24h pro Fixture (Predictions ändern sich kaum)

Run:    python3 fetch_wm_apifootball_predictions.py [--force] [--match=MEX-ZAF]
Cron:   Täglich via fetch-wm-data.yml (vor generate_wm_picks)
"""
from __future__ import annotations
import json
import os
import sys
import time
import http.client
from datetime import datetime, timezone, timedelta
from pathlib import Path

import cocobet_dataset as D

BASE          = Path(__file__).parent
# Dataset-bewusst (Single Source: cocobet_dataset): Liga liest/schreibt liga-* Dateien, nutzt die fid
# am Fixture (build_liga_data) → kein WM-Fixture-Map-Umweg. Consumer (generate_wm_picks) lädt schon
# {_FILE_PREFIX}apif_predictions.json. WM-Verhalten unverändert.
_IS_LIGA      = D.is_liga()
WM_FILE       = D.data_file()
OUTPUT_FILE   = D.file("wm_apif_predictions.json", "liga_apif_predictions.json")
APIF_HOST     = "v3.football.api-sports.io"
APIF_KEY      = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")

DEFAULT_CFG = {
    "lookahead_days":         7,    # nur Spiele in den nächsten N Tagen
    "request_delay_sec":    1.0,
    "request_timeout_sec":   15,
    "cache_ttl_hours":        24,   # frisch genug wenn cache < N h alt
}


def _load_cfg() -> dict:
    try:
        cfg_path = BASE / "cocobet_config.json"
        if not cfg_path.exists():
            return DEFAULT_CFG
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        override = raw["profiles"].get(active, {}).get("apif_predictions") or {}
        return {**DEFAULT_CFG, **override}
    except Exception:
        return DEFAULT_CFG


CFG = _load_cfg()


# ── HTTP-Layer ────────────────────────────────────────────────────────────


def _apif_get(path: str) -> dict | None:
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=CFG["request_timeout_sec"])
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


def _team_name_from_id(team_id: str) -> str:
    try:
        from fetch_wm_nt_xg import APIF_NAME_OVERRIDE
        return APIF_NAME_OVERRIDE.get(team_id, team_id)
    except Exception:
        return team_id


# ── WM-Fixtures-Lookup (FIX 09.06.2026) ────────────────────────────────────
# Vorher: pro Spiel /fixtures?date=YYYY-MM-DD globalen Fixture-Pool durchsuchen
# + Team-Name-Fuzzy-Match. Fragil weil Teamnamen DE/EN driften und API
# pro Tag nur N Treffer liefert. Jetzt: 1 Call /fixtures?league=1&season=2026
# am Anfang, baut Map (home_apif_id, away_apif_id) → fixture_id.

_WM_FIXTURE_MAP: dict[tuple[int, int], int] | None = None


def _build_wm_fixture_map(team_ids: dict[str, int]) -> dict[tuple[int, int], int]:
    """Holt alle WM-Fixtures auf einmal und mappt sie via APIF-Team-IDs."""
    print("   🔍 Lade WM-Fixture-Pool (/fixtures?league=1&season=2026)…")
    data = _apif_get("/fixtures?league=1&season=2026")
    if not data or not data.get("response"):
        print("   ⚠️  WM-Fixture-Pool leer — fallback auf Datum-Suche pro Spiel")
        return {}
    mapping: dict[tuple[int, int], int] = {}
    for fx in data["response"]:
        teams = fx.get("teams", {}) or {}
        h = ((teams.get("home") or {}).get("id"))
        a = ((teams.get("away") or {}).get("id"))
        fid = ((fx.get("fixture") or {}).get("id"))
        if h and a and fid:
            mapping[(int(h), int(a))] = int(fid)
    print(f"   ✅ {len(mapping)} WM-Fixtures gemappt")
    return mapping


# ── Fixture-Lookup ────────────────────────────────────────────────────────


def _load_wm_fixtures() -> tuple[list[dict], dict[str, int]]:
    """Returns (fixtures_list, team_ids_dict). team_ids: {our_id → apif_id}"""
    if not WM_FILE.exists():
        return [], {}
    try:
        with WM_FILE.open(encoding="utf-8") as f:
            wm = json.load(f)
        def _mk(fx):
            return {
                "match_key": f"{fx['home']}-{fx['away']}",
                "home_id":   fx["home"],
                "away_id":   fx["away"],
                "date":      fx["date"],
                # Liga-Fixtures haben kickoff (ISO) statt time → HH:MM ableiten.
                "time":      (fx.get("kickoff") or "")[11:16] or fx.get("time", "21:00"),
                "fid":       fx.get("fid"),   # API-Fixture-ID (Liga) → direkt, kein Lookup
            }
        out = []
        for grp in wm.get("groups", {}).values():
            for fx in grp.get("fixtures", []):
                if fx.get("date") and fx.get("home") and fx.get("away"):
                    out.append(_mk(fx))
        # KO-Spiele liegen in koFixtures, nicht groups (06.07.2026, Lucas: wiederkehrender
        # KO-Datenpfad-Bug → apif-Prognose fehlte für Achtel-/Viertelfinale). Nur bothResolved.
        for fx in wm.get("koFixtures", []):
            if fx.get("date") and fx.get("home") and fx.get("away"):
                out.append(_mk(fx))
        return out, wm.get("teamIds", {}) or {}
    except Exception:
        return [], {}


def _is_upcoming(fx: dict, now_utc: datetime) -> bool:
    """Match in den nächsten lookahead_days und noch nicht angepfiffen?"""
    try:
        ko = datetime.fromisoformat(f"{fx['date']}T{fx['time']}:00+00:00")
    except Exception:
        return False
    delta_days = (ko - now_utc).total_seconds() / 86400.0
    if delta_days < -0.5:
        return False   # schon vorbei
    if delta_days > CFG["lookahead_days"]:
        return False
    return True


def _is_cache_fresh(entry: dict) -> bool:
    if not entry or not entry.get("fetchedAt"):
        return False
    try:
        ts = datetime.fromisoformat(entry["fetchedAt"])
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        return age_h < CFG["cache_ttl_hours"]
    except Exception:
        return False


# ── API-Football Calls ────────────────────────────────────────────────────


def _find_apif_fixture_id(home_name: str, away_name: str, ko: datetime,
                          home_apif: int | None = None,
                          away_apif: int | None = None) -> int | None:
    """
    Sucht fixture_id. Primärpfad (FIX 09.06.2026): WM-Fixture-Map per APIF-ID.
    Fallback: /fixtures?date= + Team-Name-Match (alte Logik).
    """
    # Primär: WM-Fixture-Map (vorher initialisiert)
    if _WM_FIXTURE_MAP and home_apif and away_apif:
        fid = _WM_FIXTURE_MAP.get((int(home_apif), int(away_apif)))
        if fid:
            return fid

    # Fallback: Datums-Suche + Name-Match
    data = _apif_get(f"/fixtures?date={ko.strftime('%Y-%m-%d')}")
    if not data or not data.get("response"):
        return None
    h_target = home_name.lower().strip()
    a_target = away_name.lower().strip()
    for fx in data["response"]:
        teams = fx.get("teams", {})
        hn = (teams.get("home") or {}).get("name", "").lower().strip()
        an = (teams.get("away") or {}).get("name", "").lower().strip()
        if (h_target in hn or hn in h_target) and (a_target in an or an in a_target):
            return (fx.get("fixture") or {}).get("id")
    return None


def _parse_percent(s) -> float | None:
    """API-Football liefert percent als String '62%' — konvertiert zu 0-1 float."""
    if s is None:
        return None
    try:
        return float(str(s).rstrip("%").strip()) / 100.0
    except (ValueError, TypeError):
        return None


def _fetch_prediction(fixture_id: int) -> dict | None:
    """Holt /predictions?fixture=ID und extrahiert das wichtige."""
    data = _apif_get(f"/predictions?fixture={fixture_id}")
    if not data or not data.get("response"):
        return None
    pred = data["response"][0] if data["response"] else {}
    predictions = pred.get("predictions") or {}
    teams = pred.get("teams") or {}
    percent = predictions.get("percent") or {}

    p_home = _parse_percent(percent.get("home"))
    p_draw = _parse_percent(percent.get("draw"))
    p_away = _parse_percent(percent.get("away"))
    if p_home is None or p_away is None:
        return None
    # Re-normalize falls Summe nicht == 1
    s = (p_home or 0) + (p_draw or 0) + (p_away or 0)
    if s > 0 and abs(s - 1.0) > 0.02:
        p_home /= s
        if p_draw is not None:
            p_draw /= s
        p_away /= s

    winner = predictions.get("winner") or {}
    return {
        "percent": {
            "home": round(p_home, 4) if p_home is not None else None,
            "draw": round(p_draw, 4) if p_draw is not None else None,
            "away": round(p_away, 4) if p_away is not None else None,
        },
        "advice":         predictions.get("advice"),
        "winner_team_id": winner.get("id"),
        "winner_team":    winner.get("name"),
        "comparison":     pred.get("comparison"),
    }


# ── Main ──────────────────────────────────────────────────────────────────


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


def main():
    args = sys.argv[1:]
    force      = "--force" in args
    only_match = next((a.split("=", 1)[1] for a in args if a.startswith("--match=")), None)

    print("=== fetch_wm_apifootball_predictions.py ===\n")
    print(f"   lookahead={CFG['lookahead_days']}d, cache_ttl={CFG['cache_ttl_hours']}h\n")

    fixtures, team_ids = _load_wm_fixtures()
    if only_match:
        fixtures = [fx for fx in fixtures if fx["match_key"] == only_match]
    if not fixtures:
        print("⚠️  Keine Fixtures gefunden")
        return 1

    now_utc = datetime.now(timezone.utc)
    upcoming = [fx for fx in fixtures if _is_upcoming(fx, now_utc)]
    existing = _load_existing()

    # FIX 09.06.2026: WM-Fixture-Map einmalig laden statt pro Spiel /fixtures?date=
    # Liga (26.06.2026): überspringen — die fid steht direkt am Fixture (build_liga_data).
    global _WM_FIXTURE_MAP
    if upcoming and team_ids and not _IS_LIGA:
        _WM_FIXTURE_MAP = _build_wm_fixture_map(team_ids)
    else:
        _WM_FIXTURE_MAP = {}

    print(f"   {len(upcoming)} Spiele im Lookahead-Range (von {len(fixtures)} total)\n")

    new_count = cached_count = fail_count = 0

    for fx in upcoming:
        mk = fx["match_key"]
        entry = existing.get(mk)
        if not force and _is_cache_fresh(entry):
            cached_count += 1
            continue

        try:
            ko = datetime.fromisoformat(f"{fx['date']}T{fx['time']}:00+00:00")
        except Exception:
            fail_count += 1
            continue

        home_name = _team_name_from_id(fx["home_id"])
        away_name = _team_name_from_id(fx["away_id"])
        print(f"🔎 {mk} ({home_name} vs {away_name}):")

        # Liga: fid direkt vom Fixture (kein Lookup). WM: aus Cache/Map/Datum.
        fixture_id = (entry or {}).get("fixture_id") or fx.get("fid")
        if not fixture_id:
            # Erst aus WM-Fixture-Map (kein Extra-Call), dann Datums-Fallback
            home_apif = team_ids.get(fx["home_id"])
            away_apif = team_ids.get(fx["away_id"])
            fixture_id = _find_apif_fixture_id(home_name, away_name, ko,
                                               home_apif, away_apif)
            if not fixture_id:
                time.sleep(CFG["request_delay_sec"])
                # Try again with fallback path (Datums-Suche ohne ID-Hint)
                fixture_id = _find_apif_fixture_id(home_name, away_name, ko)
            if not fixture_id:
                print(f"   ⚠️  fixture_id nicht gefunden — skip")
                fail_count += 1
                continue
            else:
                source = "wm-map" if (home_apif and away_apif and
                                      _WM_FIXTURE_MAP.get((int(home_apif), int(away_apif)))) else "date-fallback"
                print(f"   🔗 fixture_id {fixture_id} ({source})")

        time.sleep(CFG["request_delay_sec"])
        pred = _fetch_prediction(fixture_id)
        if pred is None:
            print(f"   ⚠️  Predictions nicht verfügbar — skip")
            fail_count += 1
            continue

        existing[mk] = {
            "fixture_id": fixture_id,
            "kickoff":    ko.isoformat(),
            **pred,
            "fetchedAt":  datetime.now(timezone.utc).isoformat(),
        }
        new_count += 1
        pc = pred["percent"]
        print(f"   ✅ APIF prob: H={pc.get('home')} D={pc.get('draw')} A={pc.get('away')}"
              + (f" · {pred['advice']}" if pred.get("advice") else ""))
        _save_output(existing)

    # Datei IMMER schreiben (auch 0 neu) — sonst entsteht nie ein committbares
    # File solange API-Football WC2026 noch nicht listet. So existiert der Feed,
    # wird vom Registry-git-add erfasst und füllt sich automatisch sobald Daten da.
    _save_output(existing)

    print(f"\n=== Done: {new_count} neu, {cached_count} cached, {fail_count} fail ===")
    print(f"   → {OUTPUT_FILE.name} ({len(existing)} Einträge gesamt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
