#!/usr/bin/env python3
"""
player_pick_picker.py — Tagesweise besten Spieler-Pick für TikTok-Card finden.

Liest:
  • wm2026-player-picks.json    (kuratierte Picks aus generate_wm_player_picks.py)
  • wm2026-data.json            (für Fixture/Team-Details)
  • player_pick_sent.json       (Dedup, max 1 Pick pro Spieler in 14 Tagen)

Liefert Card-Config für generate_daily_tiktok.py.

Auswahllogik (Priorität):
  1. PICK-verdict Spieler aus Matches in den nächsten 0-3 Tagen
  2. HERO oder STAT-Kind bevorzugt (HERO = Stürmer-Star, STAT = Schussvolumen)
  3. Nicht in letzten 14 Tagen schon gepostet
  4. Bei mehreren Kandidaten: niedrigste Quote first (sicherer Pick)
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

BASE         = Path(__file__).parent
PICKS_FILE   = BASE / "wm2026-player-picks.json"
WM_FILE      = BASE / "wm2026-data.json"
DEDUP_FILE   = BASE / "player_pick_sent.json"

DEDUP_DAYS = 14
KIND_PRIORITY = {"HERO": 0, "STAT": 1, "VALUE": 2, "FIRST": 3}


def _load_dedup() -> dict:
    if DEDUP_FILE.exists():
        try:
            return json.loads(DEDUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"history": []}


def save_dedup(state: dict) -> None:
    DEDUP_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _recent_player_names(state: dict, today_iso: str) -> set[str]:
    cutoff = (date.fromisoformat(today_iso) - timedelta(days=DEDUP_DAYS)).isoformat()
    return {
        h.get("player", "") for h in state.get("history", [])
        if h.get("date", "1900-01-01") >= cutoff
    }


def _find_fixture(wm: dict, fx_home: str, fx_away: str):
    """Liefert (fixture_dict, group_data) oder (None, None)."""
    for gkey, gdata in wm.get("groups", {}).items():
        for fx in gdata.get("fixtures", []):
            if fx["home"] == fx_home and fx["away"] == fx_away:
                return fx, gdata
    return None, None


def _team_meta(group_data: dict, team_id: str) -> dict:
    if not group_data:
        return {}
    for t in group_data.get("teams", []):
        if t.get("id") == team_id:
            return t
    return {}


def get_daily_player_pick(today_iso: str) -> dict | None:
    """
    Liefert Card-Config:
    {
      "kind": "player_pick",
      "player": "...",
      "config": {  # für player_pick_card(**config)
        "player_name": "...", "team_flag": "🇲🇽", ...
      },
      "match_key": "MEX-ZAF"
    }
    oder None wenn nichts geeignet.
    """
    if not PICKS_FILE.exists():
        return None
    if not WM_FILE.exists():
        return None

    try:
        picks_data = json.loads(PICKS_FILE.read_text(encoding="utf-8"))
        wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    picks_by_match = picks_data.get("picks") or {}
    if not picks_by_match:
        return None

    dedup = _load_dedup()
    excluded = _recent_player_names(dedup, today_iso)

    today = date.fromisoformat(today_iso)
    horizon = today + timedelta(days=3)

    candidates: list[dict] = []
    for match_key, pick_list in picks_by_match.items():
        parts = match_key.split("-")
        if len(parts) != 2:
            continue
        fx_home, fx_away = parts
        fx, gdata = _find_fixture(wm, fx_home, fx_away)
        if not fx:
            continue
        try:
            fx_date = date.fromisoformat(fx["date"])
        except Exception:
            continue
        if not (today <= fx_date <= horizon):
            continue

        for pk in pick_list:
            if pk.get("verdict") != "PICK":
                continue
            if pk.get("player", "") in excluded:
                continue
            kind = pk.get("kind", "VALUE")
            score = KIND_PRIORITY.get(kind, 9)
            odds = pk.get("odds") or 99
            # Sortier-Tupel: niedrigerer Wert = besser
            candidates.append({
                "sort_key": (score, odds, fx_date.toordinal()),
                "pick": pk,
                "fx": fx,
                "gdata": gdata,
                "match_key": match_key,
            })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["sort_key"])
    best = candidates[0]
    pk = best["pick"]
    fx = best["fx"]
    gdata = best["gdata"]
    match_key = best["match_key"]

    fx_home, fx_away = match_key.split("-")
    team_meta = _team_meta(gdata, pk.get("teamId") or fx_home)
    opp_id = fx_away if (pk.get("teamId") == fx_home) else fx_home
    opp_meta = _team_meta(gdata, opp_id)

    # Kickoff-Label
    try:
        kickoff = datetime.fromisoformat(f"{fx['date']}T{fx.get('time','19:00')}:00")
        weekday_de = {0:"Mo",1:"Di",2:"Mi",3:"Do",4:"Fr",5:"Sa",6:"So"}[kickoff.weekday()]
        kickoff_label = f"{weekday_de} {kickoff.strftime('%d.%m.')} · {kickoff.strftime('%H:%M')}"
    except Exception:
        kickoff_label = fx.get("date", "")

    config = {
        "player_name":    pk["player"],
        "team_flag":      team_meta.get("flag", "🏳️"),
        "team_name":      team_meta.get("name", pk.get("teamId", "?")),
        "opponent_flag":  opp_meta.get("flag", "🏳️"),
        "opponent_name":  opp_meta.get("name", opp_id),
        "market_label":   pk.get("market", "Spieler-Markt"),
        "odds":           float(pk.get("odds", 0)),
        "bookmaker":      pk.get("bookmaker", ""),
        "reason_line":    pk.get("reason", ""),
        "confidence":     pk.get("conf", "medium"),
        "kickoff_label":  kickoff_label,
    }

    return {
        "kind":      "player_pick",
        "player":    pk["player"],
        "config":    config,
        "match_key": match_key,
    }
