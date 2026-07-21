#!/usr/bin/env python3
"""
injury_positions.py — Verletzten-Spielern ihre Position anreichern (21.07.2026, Lucas, MLS-Cards).

ANLASS: Der API-Football `/injuries`-Endpoint liefert NUR Name + Grund, KEINE Position. Für MLS
standen deshalb alle Verletzten mit `position: None` in der Daten → jede Injury zeigte „(?)" und
wurde im injury_signal als Backup unterschätzt (impact_BACKUP statt DEF/MID/FWD-Penalty).

FIX: die Position aus dem Kader-Cache (`squad_cache.json`, teams[apifId].starters = {id,name,pos})
per Namens-Join nachtragen. Gematcht wird über den NACHNAMEN (akzent-normalisiert), weil Injuries
„S. Reguilon" liefern, der Kader „Sergio Reguilón" — der Nachname ist der stabile gemeinsame Teil.
Kollidiert ein Nachname im Team (zwei Spieler), bleibt er ambig → nicht raten (Position bleibt None).

Reine Funktionen, ohne Netz/Disk testbar. `enrich_team_injuries` mutiert die players-Liste in-place.
"""
from __future__ import annotations

import re
import unicodedata


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", _strip_accents(str(s or "")).lower()).strip()


def _lastname(name: str) -> str:
    """Nachname als Join-Key: „S. Reguilon" → „reguilon", „Sergio Reguilón" → „reguilon".
    Einzelne Initialen (ein Buchstabe, evtl. mit Punkt) werden verworfen."""
    toks = [t for t in _norm(name).split() if len(t) > 1]
    return toks[-1] if toks else ""


def build_position_map(squad_cache: dict, team_id) -> dict:
    """{nachname: pos_code}. Bevorzugt die VOLLE `posMap` (alle Spieler inkl. Ersatz — Verletzte sind
    oft keine Starter); Fallback auf `starters` (nur Start-11), falls eine ältere Cache-Version keine
    posMap hat. Ambige Nachnamen → weggelassen. Fehlt das Team → leeres Dict."""
    teams = (squad_cache or {}).get("teams") or {}
    team = teams.get(str(team_id)) or teams.get(team_id) or {}
    if isinstance(team, dict) and isinstance(team.get("posMap"), dict) and team["posMap"]:
        return dict(team["posMap"])
    starters = team.get("starters") if isinstance(team, dict) else None
    counts, pos = {}, {}
    for p in (starters or []):
        if not isinstance(p, dict):
            continue
        ln = _lastname(p.get("name"))
        pc = p.get("pos") or p.get("position")
        if not ln or not pc:
            continue
        counts[ln] = counts.get(ln, 0) + 1
        pos[ln] = pc
    return {ln: pc for ln, pc in pos.items() if counts.get(ln) == 1}


def enrich_team_injuries(players: list, pos_map: dict) -> int:
    """Fehlende Positionen in-place aus pos_map (nachname→pos) füllen. Gibt Anzahl angereicherter
    Spieler zurück. Bereits gesetzte Positionen bleiben unangetastet."""
    n = 0
    for p in (players or []):
        if not isinstance(p, dict) or p.get("position"):
            continue
        pc = pos_map.get(_lastname(p.get("name")))
        if pc:
            p["position"] = pc
            n += 1
    return n


def enrich_injuries(injuries: dict, squad_cache: dict) -> int:
    """Ganzen injuries-Block ({teamId: {players:[...]}}) anreichern. Gibt Gesamtzahl gefüllter
    Positionen zurück. Robust: fehlt der Kader eines Teams, bleibt es unverändert."""
    total = 0
    for team_id, info in (injuries or {}).items():
        players = info.get("players") if isinstance(info, dict) else None
        if not players:
            continue
        total += enrich_team_injuries(players, build_position_map(squad_cache, team_id))
    return total
