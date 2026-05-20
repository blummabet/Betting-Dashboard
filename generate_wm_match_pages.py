#!/usr/bin/env python3
"""
generate_wm_match_pages.py
Reads wm2026-data.json and writes one JSON per fixture to matches/data/wm-{slug}.json.

Slug format: wm-{home_lower}-vs-{away_lower}-{date}
e.g.  wm-mex-vs-zaf-2026-06-11

Run: python3 generate_wm_match_pages.py
"""

import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "matches", "data")
os.makedirs(DATA_DIR, exist_ok=True)

WM_FILE      = os.path.join(BASE, "wm2026-data.json")
HISTORY_FILE = os.path.join(BASE, "wm2026-odds-history.json")

CO_HOSTS = {"MEX", "USA", "CAN"}

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upset_score(home_elo, away_elo):
    gap = abs(home_elo - away_elo)
    if gap < 50:   return 9
    if gap < 100:  return 7
    if gap < 150:  return 6
    if gap < 200:  return 4
    if gap < 300:  return 2
    return 1


def devig(h, d, a):
    """De-vig 1X2 odds to implied win probabilities (%)."""
    try:
        margin = 1/h + 1/d + 1/a
        return (
            round(1/h / margin * 100, 1),
            round(1/d / margin * 100, 1),
            round(1/a / margin * 100, 1),
        )
    except (ZeroDivisionError, TypeError):
        return None, None, None


def model_probs_from_picks(picks):
    """
    Extract model-implied probabilities from pick entries.
    Looks for picks whose market covers home/draw/away.
    Returns (probHome, probDraw, probAway) or (None, None, None).
    """
    home_prob = draw_prob = away_prob = None
    for p in (picks or []):
        market = (p.get("market") or "").lower()
        mo = p.get("modelOdds")
        if mo and mo > 0:
            prob = round(100 / mo, 1)
            if any(kw in market for kw in ("heimsieg", "home win", "1x2 home")):
                home_prob = prob
            elif any(kw in market for kw in ("unentschieden", "draw", "1x2 draw")):
                draw_prob = prob
            elif any(kw in market for kw in ("auswärtssieg", "away win", "1x2 away")):
                away_prob = prob
    return home_prob, draw_prob, away_prob


def fmt_rate(v):
    """Convert 0-1 float to percentage float, or leave as-is if already ≥1."""
    if v is None:
        return None
    return round(v * 100, 1) if v <= 1.0 else round(v, 1)


# ── Build one JSON payload ─────────────────────────────────────────────────────

def build_odds_history(history: dict, odds_key: str) -> list[dict]:
    """
    Gibt die letzten 20 Snapshots für ein Fixture zurück.
    Format: [{ts, hw, dr, aw, hwShift, awShift}]
    hwShift/awShift = implied prob shift vs vorheriger Snapshot.
    """
    snaps = history.get(odds_key, [])
    if not snaps:
        return []

    # Maximale 20 Einträge (letzte zuerst für Chart)
    subset = snaps[-20:]
    result = []
    for i, s in enumerate(subset):
        entry = {
            "ts":  s.get("ts", ""),
            "hw":  s.get("hw"),
            "dr":  s.get("dr"),
            "aw":  s.get("aw"),
        }
        # Shift zum vorherigen Snapshot
        if i > 0:
            prev = subset[i - 1]
            def _pp(o):
                return round(100 / o, 2) if o and o > 0 else None
            ph, nh = _pp(prev.get("hw")), _pp(s.get("hw"))
            pa, na = _pp(prev.get("aw")), _pp(s.get("aw"))
            entry["hwShift"] = round(nh - ph, 2) if ph and nh else 0
            entry["awShift"] = round(na - pa, 2) if pa and na else 0
        else:
            entry["hwShift"] = 0
            entry["awShift"] = 0
        result.append(entry)
    return result


def build_payload(group_id, group_data, fixture, team_lookup, wm, history=None):
    home_id = fixture["home"]
    away_id = fixture["away"]
    home_team = team_lookup[home_id]
    away_team = team_lookup[away_id]

    date = fixture["date"]
    slug = f"wm-{home_id.lower()}-vs-{away_id.lower()}-{date}"
    pick_key = f"{group_id}-{fixture['matchday']}-{home_id}-{away_id}"
    odds_key = f"{home_id}-{away_id}"
    h2h_key  = f"{home_id}-{away_id}"

    home_elo = home_team.get("elo") or 1500
    away_elo = away_team.get("elo") or 1500
    elo_diff = home_elo - away_elo  # signed (positive = home stronger)

    # Picks
    picks_raw = wm.get("picks", {}).get(pick_key, [])

    # Odds
    odds_raw = wm.get("odds", {}).get(odds_key)
    odds_out = None
    if odds_raw:
        odds_out = {
            "home":    odds_raw.get("hw"),
            "draw":    odds_raw.get("dr"),
            "away":    odds_raw.get("aw"),
            "over25":  odds_raw.get("o25"),
            "under25": odds_raw.get("u25"),
            "btts":    odds_raw.get("btts"),
            "noBtts":  odds_raw.get("no_btts"),
        }

    # Win probabilities (de-vigged market)
    prob_home = prob_draw = prob_away = None
    if odds_raw and odds_raw.get("hw") and odds_raw.get("dr") and odds_raw.get("aw"):
        prob_home, prob_draw, prob_away = devig(odds_raw["hw"], odds_raw["dr"], odds_raw["aw"])

    # Model probabilities from picks
    mod_home, mod_draw, mod_away = model_probs_from_picks(picks_raw)

    # Form
    form = wm.get("form", {})
    home_form = form.get(home_id)
    away_form = form.get(away_id)

    # Normalise rate fields (some sources store as 0-1, want as 0-100 for display)
    def normalise_form(f):
        if not f:
            return None
        out = dict(f)
        for k in ("over25Rate", "bttsRate"):
            if k in out and out[k] is not None:
                out[k] = fmt_rate(out[k])
        return out

    home_form = normalise_form(home_form)
    away_form = normalise_form(away_form)

    # H2H
    h2h_raw = wm.get("h2h", {}).get(h2h_key)
    h2h_out = None
    if h2h_raw:
        g = h2h_raw.get("games") or 1
        h2h_out = {
            "games":      h2h_raw.get("games", 0),
            "homeWins":   h2h_raw.get("homeWins", 0),
            "draws":      h2h_raw.get("draws", 0),
            "awayWins":   h2h_raw.get("awayWins", 0),
            "avgGoals":   h2h_raw.get("avgGoals"),
            "over25Rate": fmt_rate(h2h_raw.get("over25Rate")),
            "bttsRate":   fmt_rate(h2h_raw.get("bttsRate")),
            "homeBar":    round(h2h_raw.get("homeWins", 0) / g * 100),
            "drawBar":    round(h2h_raw.get("draws", 0) / g * 100),
            "awayBar":    round(h2h_raw.get("awayWins", 0) / g * 100),
        }

    # Group teams + fixtures (for group table / context)
    group_teams = group_data.get("teams", [])
    group_fixtures = group_data.get("fixtures", [])

    payload = {
        "slug":       slug,
        "home":       home_team["name"],
        "homeId":     home_id,
        "homeFlag":   home_team.get("flag", ""),
        "away":       away_team["name"],
        "awayId":     away_id,
        "awayFlag":   away_team.get("flag", ""),
        "date":       date,
        "time":       fixture.get("time", ""),
        "venue":      fixture.get("venue", ""),
        "group":      group_id,
        "groupName":  group_data.get("name", f"Gruppe {group_id}"),
        "matchday":   fixture["matchday"],
        "pickKey":    pick_key,
        "homeElo":    home_elo,
        "awayElo":    away_elo,
        "eloDiff":    elo_diff,
        "upsetScore": upset_score(home_elo, away_elo),
        "homeConf":   home_team.get("confederation", ""),
        "awayConf":   away_team.get("confederation", ""),
        "coHostBonus": home_id in CO_HOSTS,
        "coHostTeam":  home_team["name"] if home_id in CO_HOSTS else None,
        # Probabilities
        "probHome":  prob_home,
        "probDraw":  prob_draw,
        "probAway":  prob_away,
        "modHome":   mod_home,
        "modDraw":   mod_draw,
        "modAway":   mod_away,
        # Data sections
        "picks":         picks_raw,
        "odds":          odds_out,
        "oddsOpen":      odds_raw.get("odds_open") if odds_raw else None,
        "oddsHistory":   build_odds_history(history or {}, odds_key),
        "homeForm":      home_form,
        "awayForm":      away_form,
        "h2h":           h2h_out,
        "homeTeams":     group_teams,
        "groupFixtures": group_fixtures,
        # Meta
        "generatedAt": datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),
    }
    return slug, payload


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    wm = load_json(WM_FILE)
    if not wm:
        print(f"ERROR: {WM_FILE} not found.")
        return

    history = load_json(HISTORY_FILE) or {}
    print(f"  Odds history: {len(history)} Fixtures mit Snapshots")

    # Build flat team lookup {id -> team_dict}
    team_lookup = {}
    for group_data in wm["groups"].values():
        for t in group_data.get("teams", []):
            team_lookup[t["id"]] = t

    generated = 0
    slugs = []

    for group_id, group_data in wm["groups"].items():
        for fixture in group_data.get("fixtures", []):
            home_id = fixture.get("home")
            away_id = fixture.get("away")
            if not home_id or not away_id:
                continue
            if home_id not in team_lookup or away_id not in team_lookup:
                print(f"  SKIP: unknown team {home_id} or {away_id}")
                continue

            slug, payload = build_payload(group_id, group_data, fixture, team_lookup, wm, history)
            out_path = os.path.join(DATA_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            slugs.append(slug)
            generated += 1
            print(f"  ✓ {payload['home']} vs {payload['away']}  [{slug}.json]")

    # Write WM-specific index
    index_path = os.path.join(BASE, "matches", "wm-index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "slugs": slugs,
            "generated": datetime.utcnow().isoformat(),
            "count": generated,
        }, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅ Generated {generated} WM match pages → matches/data/wm-*.json")
    print(f"   Index: matches/wm-index.json")
    print(f"   Template: matches/wm-match.html")


if __name__ == "__main__":
    main()
