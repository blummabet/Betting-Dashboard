#!/usr/bin/env python3
"""
player_spotlight.py — Angle: Live-Spieler-Spotlight

Aktiv ab 1. WM-Spieltag (11.6.2026). Vorher: zieht aus wm2026-data.playerSpotlights
falls bereits etwas drinsteht (Squad-Spotlight von API-Sports).

Logik:
  · Falls Live-Spielergebnisse: Top-Scorer / Top-Assists des Turniers bisher
  · Sonst: kuratiertes playerSpotlights aus Squad-Daten
  · Nur Player die heute oder morgen ein Spiel haben (Relevanz)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from wm_story_engine import StoryProposal, Slot, s_from, s_static, s_derived, DATA
from wm_story_angles.match_of_day import TEAM_NAMES, FLAG, _team_name


def _team_plays_soon(wm: dict, team_id: str, today_iso: str) -> tuple[bool, str | None]:
    """True wenn team_id heute oder morgen ein Spiel hat."""
    today = today_iso[:10]
    try:
        today_dt = datetime.fromisoformat(today_iso.replace("Z", "+00:00"))
        tomorrow = (today_dt + timedelta(days=1)).date().isoformat()
    except Exception:
        tomorrow = today
    for gdata in (wm.get("groups") or {}).values():
        for fx in gdata.get("fixtures", []):
            if team_id in (fx.get("home"), fx.get("away")):
                ko = (fx.get("kickoff") or "")[:10]
                if ko in (today, tomorrow):
                    return True, ko
    return False, None


def generate(today_iso: str | None = None) -> list[StoryProposal]:
    """Generiert Spieler-Spotlights für relevante Spieler heute/morgen."""
    today_iso = today_iso or datetime.now(timezone.utc).isoformat()
    wm = DATA.get("wm2026-data.json")
    if not wm:
        return []

    spotlights = wm.get("playerSpotlights") or {}
    if not spotlights:
        return []   # noch nichts kuratiert

    proposals: list[StoryProposal] = []

    for player_key, ps in spotlights.items():
        if not isinstance(ps, dict):
            continue
        team_id = ps.get("teamId") or ps.get("team")
        if not team_id:
            continue
        plays_soon, match_date = _team_plays_soon(wm, team_id, today_iso)
        if not plays_soon:
            continue

        name = ps.get("name") or player_key
        role = ps.get("role") or "Spieler"
        # Robuste Zahlenfelder
        goals   = ps.get("seasonGoals") or ps.get("goals") or 0
        assists = ps.get("seasonAssists") or ps.get("assists") or 0
        club    = ps.get("club") or "?"

        # Score: hoch wenn (Goals + Assists) hoch + Team spielt bald
        ga = float(goals) + float(assists) * 0.5
        score = min(0.32 + ga / 45.0, 0.82)

        # Tor-Beteiligung = die knackige Zahl (Tore + Vorlagen)
        involvement = int(goals) + int(assists)
        # Punch je nach Output (16.06.2026, Lucas: „mit Punch")
        if involvement >= 30:
            punch_h2 = 'war diese Saison eine <span class="yellow">Maschine.</span>'
            punch_fact = f"{involvement} Tore + Vorlagen in einer Saison. Der Mann hört nicht auf."
        elif involvement >= 15:
            punch_h2 = 'traf diese Saison <span class="yellow">am Fließband.</span>'
            punch_fact = f"An {involvement} Treffern direkt beteiligt — heute will er nachlegen."
        else:
            punch_h2 = 'kann ein Spiel <span class="yellow">allein entscheiden.</span>'
            punch_fact = f"{int(goals)} Tore, {int(assists)} Vorlagen — der Unterschiedsspieler."

        proposals.append(StoryProposal(
            angle_id="playerSpotlight",
            entity_key=f"player:{player_key}",
            theme="player_pick",
            score=score,
            hook_slots={
                "big_number":   s_from(
                    str(int(goals)),
                    source=f"playerSpotlights.{player_key}.seasonGoals",
                    raw=goals,
                ),
                "sub_title":    s_static(f"Saisontore · {name}"),
                "hook_line_1":  s_static(f'<span class="acc">{name}</span> {FLAG.get(team_id,"")}'),
                "hook_line_2":  s_static(punch_h2),
                "mystery_question": s_static("Stoppt ihn heute jemand?"),
                "highlight_fact": s_derived(
                    punch_fact,
                    sources=[f"playerSpotlights.{player_key}.seasonGoals",
                             f"playerSpotlights.{player_key}.seasonAssists"],
                ),
            },
            info_slots={
                "flag":      s_static(FLAG.get(team_id, "🌍")),
                "name":      s_static(name),
                "role_line": s_static(f"{role} · {_team_name(team_id)} · {club}"),
                "stat1_val": s_from(str(int(goals)),
                                    source=f"playerSpotlights.{player_key}.seasonGoals", raw=goals),
                "stat1_lbl": s_static("Tore"),
                "stat2_val": s_from(str(int(assists)),
                                    source=f"playerSpotlights.{player_key}.seasonAssists", raw=assists),
                "stat2_lbl": s_static("Vorlagen"),
                "stat3_val": s_static(str(involvement)),
                "stat3_lbl": s_static("direkt beteiligt"),
                "closing_line": s_static(
                    f"<strong>{name}</strong> war diese Saison an {involvement} Treffern direkt "
                    f"beteiligt. Genau so einer entscheidet ein WM-Spiel."
                ),
                "quote_line":   s_static(f'Merk dir den <span class="acc">Namen.</span> 🎯'),
                "data_source":  s_static("Daten: Saison-Statistik 2024/25"),
            },
            reason=f"{name} ({team_id}) G={goals} A={assists} inv={involvement} spielt {match_date}",
        ))

    return proposals
