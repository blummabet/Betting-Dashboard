#!/usr/bin/env python3
"""
travel_alarm.py — Angle „Die unsichtbaren Gegner" (16.06.2026, Lucas).

Surface das dramatischste REISE- / HÖHEN- / HITZE-Faktum unter den nächsten Spielen.
Unser Alleinstellungsmerkmal (Base-Camp-Reise + Venue-Höhe + Match-Temperatur) als
TikTok-Story — komplett wett-frei (kein Quoten/Edge/Pinnacle-Vokabular).

Drei Sub-Angles, der Story-Engine-Selektor nimmt den höchsten Score:
  · Höhen-Alarm:  Venue ≥1500m (Mexiko-Stadt 2240m, Guadalajara …) → dünne Luft.
  · Reise-Alarm:  größte Base-Camp→Spielort-Distanz (Haversine) → Energie kostet.
  · Hitze-Alarm:  heißestes Spiel (≥30°C), extra Drama bei kälte-gewohnten Teams.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from wm_story_engine import StoryProposal, s_static, s_derived
from wm_story_angles.match_of_day import FLAG, _team_name

BASE = Path(__file__).parent.parent

# Kälte-/gemäßigt-gewohnte Teams → Hitze trifft sie härter (für Hitze-Drama-Bonus).
COLD_TEAMS = {"NOR", "SWE", "DEN", "ISL", "SCO", "ENG", "NED", "BEL", "GER",
              "POL", "CZE", "FIN", "IRL", "WAL", "SUI", "AUT", "UKR", "SRB", "CRO"}


def _load(name: str) -> dict:
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371.0
    r = math.radians
    a = (math.sin(r(lat2 - lat1) / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _venue_lookup(venue_name: str, venues: dict) -> dict | None:
    """Match fixture.venue ('Estadio Azteca, Mexico City') gegen venues per City-Substring."""
    if not venue_name:
        return None
    vn = venue_name.lower()
    for key, v in venues.items():
        city = (v.get("city") or key.replace("_", " ")).lower()
        if city and city in vn:
            return v
    return None


def _upcoming_fixtures(wm: dict) -> list[tuple]:
    """Fixtures heute + nächste 2 Tage, noch nicht beendet."""
    today = datetime.now(timezone.utc).date()
    out = []
    for g, gd in (wm.get("groups") or {}).items():
        for fx in gd.get("fixtures") or []:
            ko = fx.get("kickoff") or ""
            fd = fx.get("date") or ko[:10]
            try:
                d = (datetime.fromisoformat(ko.replace("Z", "+00:00")).date()
                     if ko else date.fromisoformat(fd))
            except Exception:
                continue
            if 0 <= (d - today).days <= 2 and \
               (fx.get("result") or {}).get("status") not in ("FT", "AET", "PEN"):
                out.append((g, fx))
    return out


def _matchup(home, away) -> str:
    return (f'<span class="acc">{_team_name(home)}</span> {FLAG.get(home,"")} '
            f'vs {_team_name(away)} {FLAG.get(away,"")}')


def _altitude_proposal(fixtures, venues) -> StoryProposal | None:
    cands = []
    for g, fx in fixtures:
        v = _venue_lookup(fx.get("venue"), venues)
        if v and (v.get("altitude_m") or 0) >= 1500:
            cands.append((g, fx, v))
    if not cands:
        return None
    g, fx, v = max(cands, key=lambda t: t[2].get("altitude_m", 0))
    alt = int(v.get("altitude_m") or 0)
    home, away = fx["home"], fx["away"]
    city = v.get("city") or (fx.get("venue", "").split(",")[-1].strip())
    score = min(0.58 + (alt - 1500) / 3000.0, 0.90)
    return StoryProposal(
        angle_id="travelAlarm", entity_key=f"alt:{g}-{home}-{away}",
        theme="hidden_factor", score=score,
        hook_slots={
            "big_number":   s_static(f"{alt}m"),
            "sub_title":    s_static(f"Höhe in {city}"),
            "hook_line_1":  s_static(_matchup(home, away)),
            "hook_line_2":  s_static('spielen, wo die <span class="yellow">Luft dünn wird.</span>'),
            "mystery_question": s_static("Wem geht zuerst die Puste aus?"),
            "highlight_fact": s_static(
                f"Auf {alt}m hat die Luft ~{int((alt/1000)*8)}% weniger Sauerstoff — "
                f"die letzten 20 Minuten werden zur Tortur."),
        },
        info_slots={
            "flag":      s_static(f"{FLAG.get(home,'🌍')} vs {FLAG.get(away,'🌍')}"),
            "name":      s_static(f"{_team_name(home)} vs {_team_name(away)}"),
            "role_line": s_static(f"Spielort {city} · {alt} Meter über dem Meer"),
            "stat1_val": s_static(f"{alt}m"),
            "stat1_lbl": s_static("Höhe"),
            "stat2_val": s_static("🫁"),
            "stat2_lbl": s_static("dünne Luft"),
            "stat3_val": s_static("20'"),
            "stat3_lbl": s_static("Schlussphase"),
            "closing_line": s_static(
                f"<strong>Höhe ist ein unsichtbarer Gegner.</strong> Wer nicht akklimatisiert "
                f"ist, dem brechen am Ende die Beine weg."),
            "quote_line":  s_static('Die Höhe spielt <span class="acc">immer mit.</span> ⛰️'),
            "data_source": s_static("Daten: Spielort-Höhe (Venue-Analyse)"),
        },
        reason=f"altitude={alt}m {city}")


def _travel_proposal(fixtures, venues, camps) -> StoryProposal | None:
    best = None  # (km, team, opp, fx, city)
    for g, fx in fixtures:
        v = _venue_lookup(fx.get("venue"), venues)
        if not v or v.get("lat") is None:
            continue
        city = v.get("city") or (fx.get("venue", "").split(",")[-1].strip())
        for team, opp in ((fx["home"], fx["away"]), (fx["away"], fx["home"])):
            camp = camps.get(team)
            if not camp:
                continue
            km = _haversine_km(camp.get("lat"), camp.get("lon"), v["lat"], v["lon"])
            if km >= 1500 and (best is None or km > best[0]):
                best = (km, team, opp, fx, city)
    if not best:
        return None
    km, team, opp, fx, city = best
    km_r = int(round(km / 50.0) * 50)
    score = min(0.52 + (km - 1500) / 6000.0, 0.86)
    camp_city = (camps.get(team) or {}).get("city", "ihrem Trainingslager")
    return StoryProposal(
        angle_id="travelAlarm", entity_key=f"trip:{team}-{km_r}",
        theme="hidden_factor", score=score,
        hook_slots={
            "big_number":   s_static(f"{km_r:,}".replace(",", ".") + " km"),
            "sub_title":    s_static(f"Anreise · {_team_name(team)}"),
            "hook_line_1":  s_static(f'<span class="acc">{_team_name(team)}</span> {FLAG.get(team,"")} reist'),
            "hook_line_2":  s_static('quer durch den <span class="yellow">Kontinent.</span>'),
            "mystery_question": s_static("Wie viel Energie kostet so eine Reise?"),
            "highlight_fact": s_static(
                f"Rund {km_r:,}".replace(",", ".") +
                f" km von {camp_city} zum Spielort {city} — mehr als von Wien nach New York."),
        },
        info_slots={
            "flag":      s_static(FLAG.get(team, "🌍")),
            "name":      s_static(_team_name(team)),
            "role_line": s_static(f"Trainingslager {camp_city} → Spielort {city}"),
            "stat1_val": s_static(f"{km_r:,}".replace(",", ".")),
            "stat1_lbl": s_static("Kilometer"),
            "stat2_val": s_static("✈️"),
            "stat2_lbl": s_static("vor dem Spiel"),
            "stat3_val": s_static("⚡"),
            "stat3_lbl": s_static("Energie"),
            "closing_line": s_static(
                f"<strong>Reise zehrt.</strong> Jeder Kilometer im Flieger kostet Frische — "
                f"und Frische entscheidet die engen Spiele."),
            "quote_line":  s_static('Die Reise spielt <span class="acc">immer mit.</span> ✈️'),
            "data_source": s_static("Daten: Reise-Analyse (Trainingslager → Spielort)"),
        },
        reason=f"trip={km_r}km {team}")


def _heat_proposal(fixtures, venues) -> StoryProposal | None:
    cands = []
    for g, fx in fixtures:
        temp = ((fx.get("weather") or {}).get("temp"))
        if isinstance(temp, (int, float)) and temp >= 30:
            cold = fx["home"] in COLD_TEAMS or fx["away"] in COLD_TEAMS
            cands.append((temp, cold, g, fx))
    if not cands:
        return None
    # heißestes Spiel, Kälte-Team als Tiebreaker-Bonus
    temp, cold, g, fx = max(cands, key=lambda t: (t[0] + (5 if t[1] else 0)))
    home, away = fx["home"], fx["away"]
    cold_team = home if home in COLD_TEAMS else (away if away in COLD_TEAMS else None)
    score = min(0.55 + (temp - 30) / 25.0 + (0.10 if cold_team else 0), 0.88)
    if cold_team:
        h1 = f'<span class="acc">{_team_name(cold_team)}</span> {FLAG.get(cold_team,"")} ist Kälte gewohnt —'
        fact = (f"{_team_name(cold_team)} spielt bei {int(round(temp))}°C. "
                f"Kälte-gewohnte Teams brechen in der Hitze spürbar ein.")
    else:
        h1 = _matchup(home, away)
        fact = f"{int(round(temp))}°C zum Anpfiff — bei der Hitze wird jeder Sprint teuer."
    return StoryProposal(
        angle_id="travelAlarm", entity_key=f"heat:{g}-{home}-{away}",
        theme="hidden_factor", score=score,
        hook_slots={
            "big_number":   s_static(f"{int(round(temp))}°C"),
            "sub_title":    s_static("Hitze zum Anpfiff"),
            "hook_line_1":  s_static(h1),
            "hook_line_2":  s_static('heute spielt die <span class="yellow">Sonne mit.</span>'),
            "mystery_question": s_static("Wer schmilzt in der Schlussphase?"),
            "highlight_fact": s_static(fact),
        },
        info_slots={
            "flag":      s_static(f"{FLAG.get(home,'🌍')} vs {FLAG.get(away,'🌍')}"),
            "name":      s_static(f"{_team_name(home)} vs {_team_name(away)}"),
            "role_line": s_static(f"{int(round(temp))}°C zum Anpfiff"),
            "stat1_val": s_static(f"{int(round(temp))}°C"),
            "stat1_lbl": s_static("Temperatur"),
            "stat2_val": s_static("☀️"),
            "stat2_lbl": s_static("volle Sonne"),
            "stat3_val": s_static("💦"),
            "stat3_lbl": s_static("Kräfteverschleiß"),
            "closing_line": s_static(
                f"<strong>Hitze ist ein Gegner ohne Trikot.</strong> Bei {int(round(temp))}°C "
                f"zählt am Ende, wer noch laufen kann."),
            "quote_line":  s_static('Die Sonne spielt <span class="acc">immer mit.</span> ☀️'),
            "data_source": s_static("Daten: Wetter-Vorhersage zum Anpfiff"),
        },
        reason=f"heat={temp}°C {home}-{away}")


def generate(today_iso: str) -> list[StoryProposal]:
    wm = _load("wm2026-data.json")
    if not wm:
        return []
    venues = (_load("wm_venues.json").get("venues")) or {}
    camps = (_load("wm_base_camps.json").get("camps")) or {}
    fixtures = _upcoming_fixtures(wm)
    if not fixtures:
        return []
    out = []
    for p in (_altitude_proposal(fixtures, venues),
              _travel_proposal(fixtures, venues, camps),
              _heat_proposal(fixtures, venues)):
        if p:
            out.append(p)
    return out
