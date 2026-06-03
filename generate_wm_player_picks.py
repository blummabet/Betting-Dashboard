#!/usr/bin/env python3
"""
generate_wm_player_picks.py — Spieler-Wett-Vorschläge für WM 2026

Liest:
  • wm2026-player-props.json   (Markt-Quoten von TheOddsAPI, 6 Märkte)
  • wm2026-data.json           (Form, Squad, Travel-Daten)

Schreibt:
  • wm2026-player-picks.json   (kuratierte Top-Picks pro Match)

Logik (MVP — kann später um xG-pro-Spieler erweitert werden):

  HERO-PICK     → niedrigste Anytime-Scorer-Quote = bekannter Star
                  Quote 1.50-2.80, Star-Player-Filter

  VALUE-PICK    → mittlere Anytime-Quote 3.00-6.00 + Form-Bonus
                  "Geheimtipp" — guter Spieler, aber nicht im Rampenlicht

  STAT-PICK     → Shots/SoT-Over mit Line >= 1.5 + Quote 1.70-2.10
                  Quantitativ stärkster Markt für edge-Sucher

  CARD-PICK     → Player-to-Receive-Card bei Spielern mit Verwarn-Historie
                  Niche aber viral-tauglich (kommt erst wenn Markt da ist)

Edge-Heuristik:
  Falls beide Bookies (Pinnacle UND Mainstream) verfügbar → Edge berechnen.
  Sonst: kuratiert nach Quote/Markt-Logik (keine Edge-Behauptung).

Output-Struktur:
{
  "lastUpdate": "ISO",
  "picks": {
    "MEX-ZAF": [
      {
        "player":     "R. Jiménez",
        "teamId":     "MEX",
        "kind":       "HERO" | "VALUE" | "STAT" | "CARD",
        "market":     "Anytime Scorer" | "Shots Over 1.5" | ...,
        "marketKey":  "anytime_scorer" | "player_sot" | ...,
        "side":       "yes" | "over" | "under" | null,
        "line":       1.5 | null,
        "odds":       2.50,
        "bookmaker":  "pinnacle",
        "reason":     "Stürmer-Star, hat in 4 WMQ getroffen",
        "verdict":    "PICK" | "STAT",   (PICK = aktiv, STAT = nur Info-Card)
        "conf":       "high" | "medium" | "low"
      }
    ]
  }
}
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
PROPS_FILE  = BASE / "wm2026-player-props.json"
OUT_FILE    = BASE / "wm2026-player-picks.json"

VERBOSE = os.environ.get("VERBOSE", "0") == "1"

# Markt-Limits
HERO_ODDS_MIN  = 1.50
HERO_ODDS_MAX  = 2.80
VALUE_ODDS_MIN = 3.00
VALUE_ODDS_MAX = 6.50
STAT_ODDS_MIN  = 1.70
STAT_ODDS_MAX  = 2.20

MIN_LINE_SOT   = 0.5    # Schüsse aufs Tor: min 0.5 (sonst kein Spieler-Volumen)
MIN_LINE_SHOTS = 1.5    # Schüsse total: min 1.5


def _team_squad(wm: dict, team_id: str) -> list[dict]:
    """Liefert Squad-Liste eines Teams (über alle Gruppen suchen)."""
    for gdata in wm.get("groups", {}).values():
        for t in gdata.get("teams", []):
            if t.get("id") == team_id:
                return t.get("squad", [])
    return []


def _fuzzy_squad_match(props_name: str, squad: list[dict]) -> dict | None:
    """
    Verknüpft den Bookie-Spielernamen mit unserem Squad.
    Bookies liefern oft 'R. Jiménez' oder 'Raul Jimenez'.
    """
    if not squad:
        return None
    pn = props_name.lower().strip()
    pn_last = pn.split()[-1] if " " in pn else pn

    for player in squad:
        full = (player.get("name") or "").lower().strip()
        if not full:
            continue
        if full == pn:
            return player
        # Nachname-Match
        full_last = full.split()[-1]
        if full_last == pn_last and len(pn_last) > 3:
            return player
        # Initial + Nachname: "R. Jiménez" vs "Raul Jimenez"
        parts_pn = pn.split()
        parts_full = full.split()
        if (len(parts_pn) >= 2 and len(parts_full) >= 2 and
            parts_pn[-1] == parts_full[-1] and
            parts_pn[0].rstrip(".") in parts_full[0]):
            return player
    return None


def _guess_team_for_player(player_name: str, wm: dict, fx_home: str, fx_away: str) -> str | None:
    """Versucht, einen Bookie-Spieler einem der beiden Teams zuzuordnen."""
    h_squad = _team_squad(wm, fx_home)
    a_squad = _team_squad(wm, fx_away)
    if _fuzzy_squad_match(player_name, h_squad):
        return fx_home
    if _fuzzy_squad_match(player_name, a_squad):
        return fx_away
    return None


def _pick_hero(anytime: list[dict], wm: dict, fx_home: str, fx_away: str) -> dict | None:
    """Wählt den HERO-Pick (Top-Star mit niedrigster Quote)."""
    for entry in anytime:
        odds = entry.get("odds")
        if not odds or not (HERO_ODDS_MIN <= odds <= HERO_ODDS_MAX):
            continue
        team = _guess_team_for_player(entry["name"], wm, fx_home, fx_away)
        return {
            "player":     entry["name"],
            "teamId":     team or "?",
            "kind":       "HERO",
            "market":     "Anytime Scorer",
            "marketKey":  "anytime_scorer",
            "side":       "yes",
            "line":       None,
            "odds":       odds,
            "bookmaker":  entry.get("bookmaker", ""),
            "reason":     f"Top-Star, Markt-Favorit @{odds}",
            "verdict":    "PICK",
            "conf":       "high" if odds < 2.20 else "medium",
        }
    return None


def _pick_value(anytime: list[dict], wm: dict, fx_home: str, fx_away: str,
                form: dict, exclude_names: set[str]) -> dict | None:
    """Wählt den VALUE-Pick (mittlere Quote + bevorzugt aktives Team)."""
    candidates = []
    for entry in anytime:
        if entry["name"] in exclude_names:
            continue
        odds = entry.get("odds")
        if not odds or not (VALUE_ODDS_MIN <= odds <= VALUE_ODDS_MAX):
            continue
        team = _guess_team_for_player(entry["name"], wm, fx_home, fx_away)
        # Bevorzuge Spieler aus Team mit besserer Form
        team_form_score = 0
        if team:
            f = form.get(team) or {}
            team_form_score = (f.get("avgScored") or 0) - (f.get("avgConceded") or 0)
        candidates.append((team_form_score, entry, team))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    _, entry, team = candidates[0]
    return {
        "player":     entry["name"],
        "teamId":     team or "?",
        "kind":       "VALUE",
        "market":     "Anytime Scorer",
        "marketKey":  "anytime_scorer",
        "side":       "yes",
        "line":       None,
        "odds":       entry["odds"],
        "bookmaker":  entry.get("bookmaker", ""),
        "reason":     f"Geheimtipp — mittlere Quote, Team-Form positiv",
        "verdict":    "PICK",
        "conf":       "medium",
    }


def _pick_stat(sot: list[dict], shots: list[dict], wm: dict,
               fx_home: str, fx_away: str) -> dict | None:
    """Wählt den STAT-Pick (Schüsse aufs Tor bevorzugt, sonst Total Shots)."""
    # Priorität: SoT mit Line >= 0.5 und Quote 1.70-2.20
    for entry in sot or []:
        line = entry.get("line")
        over = entry.get("over")
        if not line or not over or line < MIN_LINE_SOT:
            continue
        if not (STAT_ODDS_MIN <= over <= STAT_ODDS_MAX):
            continue
        team = _guess_team_for_player(entry["name"], wm, fx_home, fx_away)
        return {
            "player":     entry["name"],
            "teamId":     team or "?",
            "kind":       "STAT",
            "market":     f"Schüsse aufs Tor Over {line}",
            "marketKey":  "player_sot",
            "side":       "over",
            "line":       line,
            "odds":       over,
            "bookmaker":  entry.get("bookmaker", ""),
            "reason":     f"Hohes Schussvolumen — Line {line}, fair gepreist",
            "verdict":    "PICK",
            "conf":       "medium",
        }

    # Fallback: Total Shots Over
    for entry in shots or []:
        line = entry.get("line")
        over = entry.get("over")
        if not line or not over or line < MIN_LINE_SHOTS:
            continue
        if not (STAT_ODDS_MIN <= over <= STAT_ODDS_MAX):
            continue
        team = _guess_team_for_player(entry["name"], wm, fx_home, fx_away)
        return {
            "player":     entry["name"],
            "teamId":     team or "?",
            "kind":       "STAT",
            "market":     f"Schüsse Over {line}",
            "marketKey":  "player_shots",
            "side":       "over",
            "line":       line,
            "odds":       over,
            "bookmaker":  entry.get("bookmaker", ""),
            "reason":     f"Schussvolumen — Line {line}, mittlere Quote",
            "verdict":    "PICK",
            "conf":       "medium",
        }
    return None


def _pick_first(first: list[dict], wm: dict, fx_home: str, fx_away: str,
                exclude_names: set[str]) -> dict | None:
    """First-Goalscorer als Viral-Pick (höhere Quote, kleiner Stake)."""
    if not first:
        return None
    # Nimm 2.-niedrigste Quote (favorite ist meistens HERO bereits)
    for entry in first[1:4]:
        if entry["name"] in exclude_names:
            continue
        odds = entry.get("odds")
        if not odds:
            continue
        if not (4.0 <= odds <= 11.0):
            continue
        team = _guess_team_for_player(entry["name"], wm, fx_home, fx_away)
        return {
            "player":     entry["name"],
            "teamId":     team or "?",
            "kind":       "FIRST",
            "market":     "Erster Torschütze",
            "marketKey":  "first_scorer",
            "side":       "yes",
            "line":       None,
            "odds":       odds,
            "bookmaker":  entry.get("bookmaker", ""),
            "reason":     f"Viral-Quote — {odds:.1f}-fach wenn er das erste Tor macht",
            "verdict":    "STAT",
            "conf":       "low",
        }
    return None


def generate_picks_for_match(odds_key: str, market_data: dict, wm: dict, form: dict) -> list[dict]:
    """Generiert kuratierte Picks für ein Match."""
    parts = odds_key.split("-")
    if len(parts) != 2:
        return []
    fx_home, fx_away = parts

    markets = market_data.get("markets", {})
    anytime = markets.get("anytime_scorer", [])
    first   = markets.get("first_scorer", [])
    sot     = markets.get("player_sot", [])
    shots   = markets.get("player_shots", [])

    picks: list[dict] = []
    used_names: set[str] = set()

    hero = _pick_hero(anytime, wm, fx_home, fx_away) if anytime else None
    if hero:
        picks.append(hero)
        used_names.add(hero["player"])

    value = _pick_value(anytime, wm, fx_home, fx_away, form, used_names) if anytime else None
    if value:
        picks.append(value)
        used_names.add(value["player"])

    stat = _pick_stat(sot, shots, wm, fx_home, fx_away)
    if stat:
        picks.append(stat)
        used_names.add(stat["player"])

    first_pick = _pick_first(first, wm, fx_home, fx_away, used_names) if first else None
    if first_pick:
        picks.append(first_pick)

    return picks


def main():
    if not PROPS_FILE.exists():
        print(f"⚠️  {PROPS_FILE.name} fehlt — kein Fetch bisher")
        OUT_FILE.write_text(json.dumps({"lastUpdate": datetime.now(timezone.utc).isoformat(),
                                          "picks": {}}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return

    with open(PROPS_FILE, encoding="utf-8") as f:
        props = json.load(f)

    if not props:
        print(f"  ℹ️  {PROPS_FILE.name} ist leer — Bookies noch nicht offen")
        OUT_FILE.write_text(json.dumps({"lastUpdate": datetime.now(timezone.utc).isoformat(),
                                          "picks": {}}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    form = wm.get("teamForm") or {}

    out: dict[str, list[dict]] = {}
    total_picks = 0
    matches_with_picks = 0

    print(f"🎯 generate_wm_player_picks.py — {len(props)} Matches mit Props")

    for odds_key, market_data in props.items():
        picks = generate_picks_for_match(odds_key, market_data, wm, form)
        if picks:
            out[odds_key] = picks
            total_picks += len(picks)
            matches_with_picks += 1
            kinds = ", ".join(p["kind"] for p in picks)
            print(f"  ✅ {odds_key}: {len(picks)} Picks ({kinds})")
        else:
            print(f"  ○ {odds_key}: keine geeigneten Picks (Quoten außerhalb Range?)")

    output = {
        "lastUpdate": datetime.now(timezone.utc).isoformat(),
        "picks":      out,
        "stats": {
            "matchesWithPicks": matches_with_picks,
            "totalPicks":       total_picks,
        }
    }
    OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {total_picks} Spieler-Picks für {matches_with_picks} Matches → {OUT_FILE.name}")


if __name__ == "__main__":
    main()
