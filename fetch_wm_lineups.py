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

import cocobet_dataset as D

BASE          = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → Lineups für liga-data.json,
# Output liga_lineups.json (das generate_wm_picks im liga-Modus liest).
_IS_LIGA      = D.is_liga()
WM_FILE       = D.data_file()
OUTPUT_FILE   = D.file("wm_lineups.json", "liga_lineups.json")
ALERT_DEDUP   = D.file("wm_lineup_alerts.json", "liga_lineup_alerts.json")
APIF_HOST     = "v3.football.api-sports.io"
APIF_KEY      = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")

# Telegram (Trades-Channel, NIEMALS Public)
TELEGRAM_TOKEN          = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_TRADES_CHAT_ID = os.environ.get("TELEGRAM_TRADES_CHAT_ID", "")
SKIP_TELEGRAM           = os.environ.get("SKIP_TELEGRAM", "").lower() == "true"

# ── Config ────────────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "lookahead_hours":         3,    # nur Spiele in den nächsten N Stunden
    "lookback_hours":          0,    # FIX 12.06.2026: ab Anpfiff NICHT mehr (war 24 →
                                     # Lineups/Alerts liefen bis 24h nach Spielende). Lineup
                                     # ist Pre-Match. Alert hat zusätzlich harten ko-Guard.
    "min_minutes_before":     30,    # erst ab T-N min lineups verfügbar (~1h normal)
    "max_minutes_before":    180,    # T-3h obere Grenze
    "request_delay_sec":     1.0,
    "request_timeout_sec":    15,
    "cache_ttl_minutes":      45,    # nur neu fetchen wenn cache älter als N min
    # ── Alert-Konfiguration ──────────────────────────────────────────
    "alert_min_goals":         2,    # nur key-player (≥N Saison-Tore)
    "alert_enabled":        True,
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
                        "kickoff":   fx.get("kickoff"),   # echte UTC-Zeit (Poly/API-Football)
                        "group":     grp_id,
                        "matchday":  fx.get("matchday"),
                    })
        # 04.07.2026 (Lucas: „seit KO-Modus feuert der Aufstellungs-Check nie"): KO-Spiele liegen
        # in koFixtures, NICHT in groups. Ohne sie holte der Fetcher nie KO-Aufstellungen →
        # wm_lineups.json hatte keine KO-Einträge → lineup_signal konnte in der K.-o.-Phase nie
        # feuern. date fehlt manchen KO-Fixtures → aus kickoff ableiten. Nur beidseitig aufgelöste.
        for kf in (wm.get("koFixtures") or []):
            if not (kf.get("home") and kf.get("away")):
                continue
            _ko = kf.get("kickoff") or ""
            _date = kf.get("date") or (_ko[:10] if len(_ko) >= 10 else None)
            if not _date:
                continue
            out.append({
                "match_key": f"{kf['home']}-{kf['away']}",
                "home_id":   kf["home"],
                "away_id":   kf["away"],
                "date":      _date,
                "time":      kf.get("time", "21:00"),
                "kickoff":   kf.get("kickoff"),
                "group":     "KO",
                "matchday":  kf.get("round"),
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
    # FIX 11.06.2026: echte UTC-kickoff bevorzugen. fx['time'] ist Wien-Lokalzeit,
    # _kickoff_utc behandelt sie fälschlich als UTC → T-1h-Fenster lag ~2h zu spät,
    # die Aufstellung wurde NIE im echten Fenster geholt (wm_lineups.json blieb leer).
    ko = None
    if fx.get("kickoff"):
        try:
            ko = datetime.fromisoformat(str(fx["kickoff"]).replace("Z", "+00:00"))
        except Exception:
            ko = None
    if ko is None:
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


_WC_FIXMAP = None   # (apif_home_id, apif_away_id) → fixture_id
def _build_wc_fixmap() -> dict:
    """Baut einmalig die WC-Fixture-Map über APIF-Team-IDs. Robust gegen
    Namens-Schreibweisen (FIX 11.06.2026: Name-Match 'südafrika' vs 'South Africa'
    scheiterte → wm_lineups.json blieb komplett leer)."""
    global _WC_FIXMAP
    if _WC_FIXMAP is not None:
        return _WC_FIXMAP
    _WC_FIXMAP = {}
    # Liga (25.06.2026): Fixmap über die 5 Top-Ligen + aktuelle Saison statt WM-league=1.
    # Liga-Team-id = API-id → (home_id, away_id)→fixture_id-Lookup greift direkt.
    if _IS_LIGA:
        _season = D.season()
        _queries = [f"/fixtures?league={lid}&season={_season}" for lid in D.leagues().values()]
    else:
        _queries = ["/fixtures?league=1&season=2026"]
    for _q in _queries:
        data = _apif_get(_q)
        for fx in ((data or {}).get("response") or []):
            t = fx.get("teams") or {}
            h = (t.get("home") or {}).get("id")
            a = (t.get("away") or {}).get("id")
            fid = (fx.get("fixture") or {}).get("id")
            if h and a and fid:
                _WC_FIXMAP[(int(h), int(a))] = fid
    return _WC_FIXMAP


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


# ── Telegram-Alert für Top-Scorer-Bench/Missing ───────────────────────────


def _normalize_name(s: str) -> str:
    """Akzent-normalisierter Vergleich (gleiche Logik wie lineup_signal)."""
    if not s:
        return ""
    s = s.lower().strip()
    repl = {
        "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a", "ā": "a", "å": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e", "ē": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i", "ī": "i", "ı": "i",
        "ó": "o", "ò": "o", "ô": "o", "ö": "o", "õ": "o", "ō": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u", "ū": "u",
        "ñ": "n", "ç": "c", "ß": "ss",
        "ğ": "g", "ş": "s", "ž": "z", "š": "s", "č": "c", "ć": "c",
        "đ": "d", "ł": "l", "ń": "n", "ý": "y",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def _player_in_lineup(player_name: str, players: list) -> bool:
    """Robuster Name-Match (Last-Name ≥3 chars)."""
    target = _normalize_name(player_name)
    if not target:
        return False
    target_last = target.split()[-1] if " " in target else target
    for p in players or []:
        pname = _normalize_name(p.get("name", ""))
        if not pname:
            continue
        if len(target) >= 5 and (target in pname or pname in target):
            return True
        pname_last = pname.split()[-1] if " " in pname else pname
        if target_last == pname_last and len(target_last) >= 3:
            return True
    return False


def _classify_scorer(scorer: dict, team_lineup: dict) -> str:
    """Returns 'missing' | 'benched' | 'starting' | 'unknown'."""
    if not scorer or not scorer.get("name"):
        return "unknown"
    if (scorer.get("goals") or 0) < CFG["alert_min_goals"]:
        return "unknown"
    name = scorer["name"]
    if _player_in_lineup(name, team_lineup.get("starting") or []):
        return "starting"
    if _player_in_lineup(name, team_lineup.get("subs") or []):
        return "benched"
    return "missing"


def _load_alert_dedup() -> dict:
    if not ALERT_DEDUP.exists():
        return {}
    try:
        return json.loads(ALERT_DEDUP.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_alert_dedup(data: dict) -> None:
    tmp = ALERT_DEDUP.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ALERT_DEDUP)


def _send_telegram(text: str) -> bool:
    """Sendet Nachricht an TRADES-Channel (privat). Returns ob erfolgreich."""
    if SKIP_TELEGRAM:
        print(f"   ↪ SKIP_TELEGRAM=true — würde senden: {text[:60]}...")
        return False
    if not TELEGRAM_TOKEN or not TELEGRAM_TRADES_CHAT_ID:
        print(f"   ⚠️  TELEGRAM_TOKEN oder TRADES_CHAT_ID nicht gesetzt — Alert übersprungen")
        return False
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id":    TELEGRAM_TRADES_CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print(f"   ⚠️  Telegram-Send fehlgeschlagen: {e}")
        return False


def _emit_lineup_alerts(match_key: str, entry: dict, squads: dict,
                        fixtures_meta: dict, dedup: dict) -> int:
    """
    Prüft pro Team ob der Top-Scorer fehlt/auf Bank ist und sendet Telegram-Alert.
    Dedup pro (match_key + team_id + status) — ein Alert pro Pick-Veränderung.
    Returns Anzahl gesendeter Alerts.
    """
    if not CFG.get("alert_enabled", True):
        return 0

    sent = 0
    home_id = (entry.get("home") or {}).get("team_id_internal") or fixtures_meta.get("home_id")
    away_id = (entry.get("away") or {}).get("team_id_internal") or fixtures_meta.get("away_id")
    home_name = fixtures_meta.get("home_name", home_id)
    away_name = fixtures_meta.get("away_name", away_id)
    ko_iso = entry.get("kickoff", "")
    ko_dt = None
    try:
        ko_dt = datetime.fromisoformat(ko_iso)
        if ko_dt.tzinfo is None:
            ko_dt = ko_dt.replace(tzinfo=timezone.utc)
        ko_str = ko_dt.strftime("%H:%M")
    except Exception:
        ko_str = "?"

    # FIX 12.06.2026: KEIN Lineup-Alert nach Anpfiff. lookback_hours hielt Spiele
    # bis Stunden NACH Kickoff "due" (MEX-ZAF-Alert 23:41 UTC, Spiel 19:00 UTC vorbei).
    # Lineup-Info ist nur PRE-MATCH sinnvoll (Engine passt Goals-Picks VOR dem Spiel an).
    if ko_dt is not None and ko_dt <= datetime.now(timezone.utc):
        return 0

    for team_label, team_id, team_name, scorer, team_lineup in [
        ("🏠 Heim",   home_id, home_name, squads.get(home_id, {}), entry.get("home", {})),
        ("✈ Auswärts", away_id, away_name, squads.get(away_id, {}), entry.get("away", {})),
    ]:
        status = _classify_scorer(scorer, team_lineup)
        if status in ("starting", "unknown"):
            continue

        # Dedup-Key: match + team_id + status (status-flip = neuer Alert)
        dk = f"{match_key}|{team_id}|{status}"
        if dk in dedup.get("seen", {}):
            continue

        status_emoji = "🚨" if status == "missing" else "⚠️"
        status_text  = "FEHLT komplett" if status == "missing" else "auf der BANK"
        text = (
            f"{status_emoji} <b>LINEUP-ALERT</b>\n"
            f"{home_name} vs {away_name} · Anpfiff {ko_str}\n\n"
            f"{team_label} <b>{team_name}</b>: "
            f"<b>{scorer.get('name')}</b> ({scorer.get('goals')} Saison-Tore) {status_text}\n\n"
            f"<i>→ Engine wird Goals-Picks beim nächsten Run anpassen</i>"
        )

        if _send_telegram(text):
            dedup.setdefault("seen", {})[dk] = {
                "ts":     datetime.now(timezone.utc).isoformat(),
                "team":   team_id,
                "player": scorer.get("name"),
                "status": status,
            }
            sent += 1
            print(f"   📨 Alert gesendet: {team_name} {scorer.get('name')} {status}")

    if sent:
        _save_alert_dedup(dedup)
    return sent


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
    # FIX 12.06.2026 — Doppel-Send: NUR der */15-Watcher (wm-lineup-watcher.yml) darf
    # Lineup-Alerts senden. fetch-wm-data ruft dasselbe Script (Daten-Refresh), lief
    # aber zu den :00-Crons GLEICHZEITIG mit dem Watcher → beide laden den Dedup-Marker
    # von origin (ohne den neuen Alert), beide senden, erst danach committet einer →
    # 2× Alert. --no-alerts (in fetch-wm-data gesetzt) macht diesen Lauf rein daten-
    # holend. Ein einziger Sender = kein Race, analog Morning-Card-Fix.
    no_alerts  = "--no-alerts" in args or os.environ.get("LINEUP_ALERTS_OFF", "").lower() == "true"

    print("=== fetch_wm_lineups.py ===" + ("  [NO-ALERTS]" if no_alerts else "") + "\n")
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

    # Squads aus wm2026-data laden für Alert-Logik (Top-Scorer pro Team)
    squads = {}
    apif_ids = {}   # our_code → apif_team_id (für robuste fixture_id-Auflösung)
    try:
        with WM_FILE.open(encoding="utf-8") as f:
            _wmd = json.load(f)
        squads = _wmd.get("squads", {}) or {}
        for code, aid in (_wmd.get("teamIds") or {}).items():
            try:
                apif_ids[code] = int(aid)
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    alert_dedup = _load_alert_dedup()

    new_count = 0
    cached_count = 0
    fail_count = 0
    alert_count = 0

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

        # Lookup fixture_id — primär über APIF-Team-IDs (robust), sonst Name-Match.
        fixture_id = (entry or {}).get("fixture_id")
        if not fixture_id:
            h_ap, a_ap = apif_ids.get(fx["home_id"]), apif_ids.get(fx["away_id"])
            if h_ap and a_ap:
                fixture_id = _build_wc_fixmap().get((h_ap, a_ap))
                if fixture_id:
                    print(f"   ↪ fixture_id via Team-ID-Map: {fixture_id}")
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

        # ── Telegram-Alert: Top-Scorer fehlt/auf Bank? ───────────────────
        fixtures_meta = {
            "home_id":   fx["home_id"],
            "away_id":   fx["away_id"],
            "home_name": _team_name_from_id(fx["home_id"]),
            "away_name": _team_name_from_id(fx["away_id"]),
        }
        sent = 0 if no_alerts else _emit_lineup_alerts(mk, entry_new, squads, fixtures_meta, alert_dedup)
        alert_count += sent

    print(f"\n=== Done: {new_count} neu, {cached_count} cached, {fail_count} fail, "
          f"{alert_count} Telegram-Alerts gesendet ===")
    print(f"   → {OUTPUT_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
