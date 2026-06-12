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
import urllib.parse
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
    # ── xGsim: schuss-basierter xG-Proxy ─────────────────────────────────────
    # Kalibriert 12.06.2026 via Chrome-MCP gegen 92 Spiele mit ECHTEM xG
    # (Premier League + La Liga). OLS ohne Intercept: xg ≈ 0.118·inside + 0.10·on,
    # R²=0.78, RMSE=0.47. Außerhalb-16er-Schüsse ~0 → ignoriert. Damit kriegen
    # auch Teams OHNE echtes API-xG (CONMEBOL/AFC/Afrika, deren Freundschafts-
    # spiele kein xG liefern, aber Schuss-Aufschlüsselung schon) eine echte
    # Chancen-Qualität statt schwachem Tor-Form-Proxy.
    "xgsim_w_inside":      0.118,
    "xgsim_w_on":          0.10,
    "fetch_player_stats":  True,  # /fixtures/players für Schlüsselpässe + Rating
    "refresh_age_days":    3,     # Team neu ziehen wenn älter (WM: alle ~3 Tage
                                  # neue Spiele → echtes WM-xG fließt zeitnah ein)
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
    """Sucht die API-Football Team-ID für eine Nationalmannschaft.
    FIX 09.06.2026: urllib.parse.quote statt naivem replace — Sonderzeichen
    (Türkiye=ü, später ggf. ñ/ç) werden jetzt korrekt URL-encoded.
    """
    data = _apif_get(f"/teams?name={urllib.parse.quote(team_name)}")
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


def _num(v):
    """Robust → float|None. Akzeptiert '63%', '1.23', 12, None, ''."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_fixture_stats(fixture_id: int) -> dict[int, dict]:
    """
    Holt /fixtures/statistics?fixture=ID und extrahiert pro Team ALLE Felder,
    die wir für Signale brauchen — plus den kalibrierten xGsim-Proxy.

    Returns {team_id: {
        "xg": float|None,      # echtes API-xG (oft None bei Friendlies)
        "xgsim": float,        # 0.118·inside + 0.10·on  (immer berechenbar)
        "inside": float, "outside": float, "on": float, "total": float,
        "blocked": float, "saves": float,
    }}
    """
    data = _apif_get(f"/fixtures/statistics?fixture={fixture_id}")
    if not data or not data.get("response"):
        return {}
    w_in = CFG.get("xgsim_w_inside", 0.118)
    w_on = CFG.get("xgsim_w_on", 0.10)
    out: dict[int, dict] = {}
    for team_stats in data["response"]:
        team_id = (team_stats.get("team") or {}).get("id")
        if not team_id:
            continue
        m: dict[str, object] = {}
        xg_val = None
        for s in (team_stats.get("statistics") or []):
            t = (s.get("type") or "")
            key = t.lower().replace("_", " ").strip()
            m[key] = s.get("value")
            if "expected goals" in key or key == "xg":
                xg_val = _num(s.get("value"))
        inside  = _num(m.get("shots insidebox"))  or 0.0
        outside = _num(m.get("shots outsidebox")) or 0.0
        on      = _num(m.get("shots on goal"))    or 0.0
        total   = _num(m.get("total shots"))      or 0.0
        blocked = _num(m.get("blocked shots"))    or 0.0
        saves   = _num(m.get("goalkeeper saves")) or 0.0
        out[team_id] = {
            "xg":      xg_val,
            "xgsim":   round(w_in * inside + w_on * on, 3),
            "inside":  inside, "outside": outside, "on": on, "total": total,
            "blocked": blocked, "saves": saves,
        }
    return out


def _extract_xg_from_statistics(fixture_id: int) -> dict[int, dict]:
    """Backward-Compat-Wrapper (Tests + Altpfade): nur {team_id: {"xg": float}}
    für Teams mit echtem xG."""
    return {tid: {"xg": v["xg"]}
            for tid, v in _extract_fixture_stats(fixture_id).items()
            if v.get("xg") is not None}


def _extract_player_aggregates(fixture_id: int) -> dict[int, dict]:
    """
    Holt /fixtures/players?fixture=ID → pro Team: Schlüsselpässe (Chancen-
    Kreation) + minutengewichtetes Ø-Spieler-Rating (Form/Qualität).
    Returns {team_id: {"keyPasses": float, "ratingAvg": float|None}} oder {}.
    """
    data = _apif_get(f"/fixtures/players?fixture={fixture_id}")
    if not data or not data.get("response"):
        return {}
    out: dict[int, dict] = {}
    for team_block in data["response"]:
        tid = (team_block.get("team") or {}).get("id")
        if not tid:
            continue
        kp = 0.0
        r_weighted = 0.0
        r_minutes = 0.0
        for p in (team_block.get("players") or []):
            st = (p.get("statistics") or [{}])[0] or {}
            key = ((st.get("passes") or {}).get("key"))
            if key is not None:
                kp += _num(key) or 0.0
            rating = _num((st.get("games") or {}).get("rating"))
            mins = _num((st.get("games") or {}).get("minutes")) or 0.0
            if rating is not None and mins > 0:
                r_weighted += rating * mins
                r_minutes += mins
        out[tid] = {
            "keyPasses": kp,
            "ratingAvg": round(r_weighted / r_minutes, 2) if r_minutes > 0 else None,
        }
    return out


# ── Aggregations-Kern ─────────────────────────────────────────────────────


def _avg(total: float, n: int, nd: int = 3):
    return round(total / n, nd) if n > 0 else None


def aggregate_team_stats(team_apif_id: int, our_id: str) -> dict | None:
    """
    Aggregiert Rich-Stats für ein Team aus den letzten N Spielen:
      · xgForAvg/xgAgainstAvg  — ECHTES API-xG (nur über Spiele die es haben)
      · xgSimForAvg/AgainstAvg — kalibrierter Schuss-Proxy (über ALLE Spiele)
      · shotsInsideForAvg, sotForAvg, savesForAvg, blocksForAvg
      · keyPassesForAvg (Chancen-Kreation), ratingAvg (Form), via Spieler-Endpoint
    `games` = Spiele mit Schuss-Statistik (Basis für xgSim & Co.);
    `xgGames` = Teilmenge mit echtem xG. Returns None bei zu wenig Daten.
    """
    fixtures = _list_recent_fixtures(team_apif_id, CFG["lookback_fixtures"])
    if len(fixtures) < CFG["min_fixtures"]:
        print(f"   ↪ {our_id}: nur {len(fixtures)} Fixtures gefunden — überspringe")
        return None

    acc = {k: 0.0 for k in ("xg_for", "xg_ag", "sim_for", "sim_ag",
                            "inside_for", "sot_for", "saves_for", "blocks_for",
                            "kp_for", "rating_w", "rating_min")}
    games = 0        # Spiele mit Schuss-Statistik (Team + Gegner)
    xg_games = 0     # Teilmenge mit echtem xG (Team + Gegner)
    fixture_ids: list[int] = []
    want_players = bool(CFG.get("fetch_player_stats", True))

    for fx in fixtures:
        time.sleep(CFG["request_delay_sec"])
        stats = _extract_fixture_stats(fx["id"])
        me = stats.get(team_apif_id)
        if not me:
            continue
        opp_id = fx["away_id"] if fx["home_id"] == team_apif_id else fx["home_id"]
        opp = stats.get(opp_id) if opp_id is not None else None
        if not opp:
            continue
        games += 1
        fixture_ids.append(fx["id"])
        acc["sim_for"] += me["xgsim"]
        acc["sim_ag"]  += opp["xgsim"]
        acc["inside_for"] += me["inside"]
        acc["sot_for"]    += me["on"]
        acc["saves_for"]  += me["saves"]
        acc["blocks_for"] += me["blocked"]
        if me["xg"] is not None and opp["xg"] is not None:
            acc["xg_for"] += me["xg"]
            acc["xg_ag"]  += opp["xg"]
            xg_games += 1
        if want_players:
            time.sleep(CFG["request_delay_sec"])
            pl = _extract_player_aggregates(fx["id"])
            mp = pl.get(team_apif_id)
            if mp:
                acc["kp_for"] += mp["keyPasses"]
                if mp["ratingAvg"] is not None:
                    acc["rating_w"]  += mp["ratingAvg"]
                    acc["rating_min"] += 1

    if games < CFG["min_fixtures"]:
        print(f"   ↪ {our_id}: nur {games} Fixtures mit Statistik — überspringe")
        return None

    return {
        # echtes xG (None wenn kein einziges Spiel echtes xG hatte)
        "xgForAvg":     _avg(acc["xg_for"], xg_games),
        "xgAgainstAvg": _avg(acc["xg_ag"], xg_games),
        "xgGames":      xg_games,
        # Schuss-Proxy (immer vorhanden)
        "xgSimForAvg":     _avg(acc["sim_for"], games),
        "xgSimAgainstAvg": _avg(acc["sim_ag"], games),
        # Roh-Aggregate für weitere Signale
        "shotsInsideForAvg": _avg(acc["inside_for"], games, 2),
        "sotForAvg":         _avg(acc["sot_for"], games, 2),
        "savesForAvg":       _avg(acc["saves_for"], games, 2),
        "blocksForAvg":      _avg(acc["blocks_for"], games, 2),
        "keyPassesForAvg":   _avg(acc["kp_for"], games, 2) if want_players else None,
        "ratingAvg":         _avg(acc["rating_w"], int(acc["rating_min"]), 2),
        "games":        games,
        "source":       "apif_fixtures_statistics",
        "fixture_ids":  fixture_ids,
        "updatedAt":    datetime.now(timezone.utc).isoformat(),
    }


# Backward-Compat-Alias (Altpfade/Tests rufen evtl. aggregate_team_xg)
aggregate_team_xg = aggregate_team_stats


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

    # FIX 09.06.2026 — APIF-Team-IDs direkt aus wm2026-data.json["teamIds"] laden.
    # Vorher: pro Team /teams?name=… Anfrage → scheiterte bei BIH/USA/CPV/TUR
    # (Name-Match-Mismatch + Encoding-Bug). Wir haben die IDs schon, also nutzen.
    direct_team_ids: dict[str, int] = {}
    try:
        with WM_FILE.open(encoding="utf-8") as f:
            _wm = json.load(f)
        direct_team_ids = _wm.get("teamIds", {}) or {}
        if direct_team_ids:
            print(f"   Direct-IDs aus wm2026-data.json: {len(direct_team_ids)} Teams")
    except Exception:
        pass

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
                if (time.time() - ts) < CFG.get("refresh_age_days", 3) * 86400:
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
        # Primär: direct teamIds aus wm2026-data.json (kein API-Call nötig)
        team_id = direct_team_ids.get(our_id)
        if team_id:
            try: team_id = int(team_id)
            except Exception: team_id = None
        # Fallback: Name-Search via API
        if not team_id:
            time.sleep(CFG["request_delay_sec"])
            team_id = _find_team_id(apif_name)
        if not team_id:
            print(f"   ⚠️  Team-ID nicht gefunden (weder direct noch via Name-Search)")
            fail_count += 1
            continue

        result = aggregate_team_stats(team_id, our_id)
        if result is None:
            fail_count += 1
            continue

        existing[our_id] = result
        new_count += 1
        _real = "echt" if result.get("xgForAvg") is not None else "sim"
        _xgf = result.get("xgForAvg")
        _xgf = _xgf if _xgf is not None else result.get("xgSimForAvg")
        print(f"   ✅ xG-For: {_xgf} ({_real}), xGsim-For: {result['xgSimForAvg']}, "
              f"KeyPässe: {result.get('keyPassesForAvg')}, Rating: {result.get('ratingAvg')} "
              f"({result['games']} games, {result.get('xgGames',0)} mit echtem xG)")
        # Atomar nach jedem Team — fail-safe gegen Abbrüche
        _save_output(existing)

    print(f"\n=== Done: {new_count} neu, {skip_count} skipped, {fail_count} fail ===")
    print(f"   → {OUTPUT_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
