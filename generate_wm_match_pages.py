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
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "matches", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Dataset-Modus (Single Source: cocobet_dataset): Liga → Liga-Match-Pages (liga-{slug}.json +
# liga-index.json), gleiches Template. WM-only Quellen (poly/props/smartmoney) für Liga =
# nicht-existente Pfade → load_json gibt {} → leer.
import cocobet_dataset as D
_IS_LIGA     = D.is_liga()
# 13.07.2026 (MLS-Audit) — 🔴 D.is_liga() ist auch für MLS True → der MLS-Lauf schrieb
# matches/liga-*.json und ÜBERSCHRIEB matches/liga-index.json mit MLS-Inhalten. Ergebnis:
# 0 MLS-Match-Pages (171 wm-, 65 liga-, 0 mls-) UND beschädigte Liga-Seiten.
_PFX         = D.active_dataset()
WM_FILE      = str(D.data_file())
HISTORY_FILE = str(D.file("wm2026-odds-history.json", "liga-odds-history.json"))
POLY_FILE    = str(D.file("wm_poly_prices.json", "liga_poly_prices.json"))
PROPS_FILE   = str(D.file("wm2026-player-props.json", "liga_player_props.json"))
SMARTMONEY_FILE = str(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json"))

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


def model_probs_from_elo(home_elo: float, away_elo: float, home_is_cohost: bool = False):
    """
    Modell-Wahrscheinlichkeiten aus Elo. EINZIGE Quelle ist generate_wm_picks.
    elo_probabilities() — kein eigener Kopie der Formel mehr (21.06.2026, Lucas:
    „nicht das wir was doppelt machen"). Lazy-Import wegen Zirkularität
    (generate_wm_picks ruft diesen Builder auf). Returns (pHome%, pDraw%, pAway%).
    """
    from generate_wm_picks import elo_probabilities   # lazy: vermeidet Zirkel-Import
    p = elo_probabilities(home_elo, away_elo, home_is_cohost)
    return (
        round(p["pH"] * 100, 1),
        round(p["pD"] * 100, 1),
        round(p["pA"] * 100, 1),
    )


def fmt_rate(v):
    """Convert 0-1 float to percentage float, or leave as-is if already ≥1."""
    if v is None:
        return None
    return round(v * 100, 1) if v <= 1.0 else round(v, 1)


# ── Build one JSON payload ─────────────────────────────────────────────────────

def _match_player_spotlights(wm: dict, home_id: str, away_id: str) -> list[dict]:
    """
    Gibt Player Spotlights zurück die zu diesem Spiel gehören.
    Schaut in wm["playerSpotlights"] nach Spielern beider Teams.
    """
    all_spots = wm.get("playerSpotlights", {})
    result = []
    for week_spots in all_spots.values():
        for spot in week_spots:
            if spot.get("teamId") in (home_id, away_id):
                # Vollständige Spotlight-Daten aus wm["squads"] anreichern
                player = wm.get("squads", {}).get(spot["teamId"])
                if player:
                    spot = dict(spot)
                    spot["player"] = player
                    # Flag + Name aus Gruppe
                    for gdata in wm.get("groups", {}).values():
                        for t in gdata.get("teams", []):
                            if t["id"] == spot["teamId"]:
                                spot["teamFlag"] = t.get("flag", "🏳")
                                spot["teamName"] = t.get("name", spot["teamId"])
                    result.append(spot)
    return result


def generate_bet_insights(home_id, away_id, home_form, away_form, h2h, home_team, away_team) -> list[dict]:
    """
    Generiert kontextuelle Wett-Insights aus Form/H2H-Daten.
    Returns list of {icon, text, type} — max 6 Insights.
    form fields already normalised: over25Rate/bttsRate in %, avgScored/avgConceded as per-game floats.
    """
    insights = []

    def add(icon, text, kind):
        insights.append({"icon": icon, "text": text, "type": kind})

    for team_id, form, team in [(home_id, home_form, home_team), (away_id, away_form, away_team)]:
        if not form:
            continue
        name = team.get("name", team_id)
        last5  = form.get("last5",  [])
        last10 = form.get("last10", [])

        # Unbeaten streak (W or D in a row from most recent)
        unbeaten = 0
        for r in reversed(last10):
            if r in ("W", "D"):
                unbeaten += 1
            else:
                break
        if unbeaten >= 5:
            add("🔥", f"{name} seit {unbeaten} Spielen ungeschlagen", "streak")
        elif unbeaten >= 3:
            add("📈", f"{name} seit {unbeaten} Spielen ohne Niederlage", "streak")

        # Win streak
        wins = 0
        for r in reversed(last5):
            if r == "W":
                wins += 1
            else:
                break
        if wins >= 3:
            add("⚡", f"{name} – {wins} Siege in Folge", "streak")

        # Loss streak (red flag)
        losses = 0
        for r in reversed(last5):
            if r == "L":
                losses += 1
            else:
                break
        if losses >= 3:
            add("⚠️", f"{name} zuletzt {losses} Niederlagen in Folge", "warning")

        # Over 2.5 rate
        o25 = form.get("over25Rate")
        if o25 is not None and o25 >= 65:
            add("⚽", f"{name}: Over 2.5 in {round(o25)}% der letzten Spiele", "goals")
        elif o25 is not None and o25 <= 30:
            add("🛡️", f"{name}: Nur {round(o25)}% der Spiele über 2.5 Tore", "defense")

        # BTTS rate
        btts = form.get("bttsRate")
        if btts is not None and btts >= 65:
            add("🔄", f"{name}: Beide Teams trafen in {round(btts)}% der Spiele", "btts")

        # Scoring average — high or low
        avg_s = form.get("avgScored")
        avg_c = form.get("avgConceded")
        if avg_s is not None and avg_s >= 2.2:
            add("🎯", f"{name}: Ø {avg_s:.1f} Tore/Spiel — starke Offensive", "goals")
        elif avg_s is not None and avg_s < 0.9:
            add("😴", f"{name}: Nur Ø {avg_s:.1f} Tore/Spiel — schwache Offensive", "warning")
        if avg_c is not None and avg_c <= 0.6:
            add("🏰", f"{name}: Ø nur {avg_c:.1f} Gegentore — defensive Mauer", "defense")

    # H2H insights
    if h2h:
        games = h2h.get("games", 0)
        hn    = home_team.get("name", home_id)
        an    = away_team.get("name", away_id)
        if games >= 3:
            hw = h2h.get("homeWins", 0)
            dr = h2h.get("draws",    0)
            aw = h2h.get("awayWins", 0)

            if hw >= round(games * 0.6):
                add("📊", f"H2H: {hn} gewann {hw}/{games} Direktbegegnungen", "h2h")
            elif aw >= round(games * 0.6):
                add("📊", f"H2H: {an} dominiert – {aw} von {games} Siegen", "h2h")
            elif dr >= round(games * 0.4):
                add("🤝", f"H2H: {dr} Unentschieden in {games} Direktbegegnungen — Remis-Tendenz", "h2h")

            avg_g = h2h.get("avgGoals")
            if avg_g:
                if float(avg_g) >= 3.2:
                    add("🔥", f"H2H: Ø {float(avg_g):.1f} Tore/Spiel — torhungrige Partien", "goals")
                elif float(avg_g) < 1.8:
                    add("🛡️", f"H2H: Ø {float(avg_g):.1f} Tore/Spiel — taktische Duelle", "defense")

            o25_h = h2h.get("over25Rate")
            if o25_h is not None and float(o25_h) >= 70:
                add("⚽", f"H2H: Over 2.5 in {round(float(o25_h))}% der Direktbegegnungen", "goals")

    return insights[:6]


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


def poisson_xg(home_form, away_form, home_elo: float, away_elo: float, home_is_cohost: bool = False):
    """
    Schätzt Expected Goals (xG) via Poisson-Modell aus Form-Daten.
    Fallback auf Elo-basierte Schätzung wenn Form-Daten fehlen.
    Returns (xg_home, xg_away) als float.
    """
    WM_AVG = 2.3  # historischer WM-Schnitt: ~2.3 Tore/Spiel

    h_scored = h_conceded = a_scored = a_conceded = None

    if home_form and home_form.get('games', 0) >= 3:
        h_scored   = home_form.get('avgScored',   0)
        h_conceded = home_form.get('avgConceded', 0)

    if away_form and away_form.get('games', 0) >= 3:
        a_scored   = away_form.get('avgScored',   0)
        a_conceded = away_form.get('avgConceded', 0)

    import math
    p_home = 1.0 / (1.0 + 10.0 ** (-(home_elo - away_elo) / 400.0))
    if home_is_cohost:
        p_home = min(0.90, p_home + 0.04)
    p_away = 1.0 - p_home

    if h_scored is not None and a_conceded is not None:
        xg_home = round((h_scored + a_conceded) / 2, 2)
    else:
        xg_home = round(WM_AVG * p_home * 0.95, 2)

    if a_scored is not None and h_conceded is not None:
        xg_away = round((a_scored + h_conceded) / 2, 2)
    else:
        xg_away = round(WM_AVG * p_away * 1.05, 2)

    return xg_home, xg_away


def _smartmoney_all(_cache={}):
    """Smart-Money (wm_poly_smartmoney.json) einmal laden + memoizen. {} wenn fehlt."""
    if "d" not in _cache:
        raw = load_json(SMARTMONEY_FILE) or {}
        d = raw.get("matches", raw)
        _cache["d"] = d if isinstance(d, dict) else {}
    return _cache["d"]


# 13.07.2026 (MLS-Audit): war hart wm_lineups → MLS-Match-Pages zeigten NIE eine Aufstellung,
# obwohl fetch_wm_lineups mls_lineups.json schreibt.
LINEUPS_FILE = str(D.file("wm_lineups.json", "liga_lineups.json"))

def _lineups_all(_cache={}):
    """Aufstellungen (wm_lineups.json) einmal laden + memoizen. {} wenn fehlt."""
    if "d" not in _cache:
        d = load_json(LINEUPS_FILE) or {}
        _cache["d"] = d if isinstance(d, dict) else {}
    return _cache["d"]


def _lineup_for(home_id, away_id):
    """Schlanke Aufstellung (Formation/Trainer/Start-XI mit grid/Bank) fürs Payload.
    None wenn (noch) keine veröffentlicht — Aufstellungen kommen ~1h vor Anpfiff."""
    lu = _lineups_all().get(f"{home_id}-{away_id}") or {}
    def _slim(side):
        if not isinstance(side, dict) or not side.get("starting"):
            return None
        return {
            "formation": side.get("formation"),
            "coach":     side.get("coach"),
            "starting":  [{"name": p.get("name"), "pos": p.get("pos"),
                           "grid": p.get("grid"), "num": p.get("num")}
                          for p in (side.get("starting") or [])],
            "subs":      [{"name": p.get("name"), "pos": p.get("pos"), "num": p.get("num")}
                          for p in (side.get("subs") or [])],
        }
    h, a = _slim(lu.get("home")), _slim(lu.get("away"))
    if not h and not a:
        return None
    return {"home": h, "away": a, "kickoff": lu.get("kickoff")}


# ── Serien (compute_streaks) fürs Match-Payload (29.06.2026, Lucas: Serien auf die Event-Page) ──
def _streaks_index(_cache={}):
    """{wm_,liga_,mls_}streaks.json einmal laden + nach teamId indizieren (dataset-aware)."""
    if "d" not in _cache:
        data = load_json(str(D.file("wm_streaks.json", "liga_streaks.json"))) or {}
        idx = {}
        for s in (data.get("streaks") or []):
            idx.setdefault(str(s.get("teamId")), []).append(s)
        _cache["d"] = idx
    return _cache["d"]


def _streaks_for_match(home_id, away_id):
    """Heim-Team bevorzugt Heim-Serie, Auswärts-Team Auswärts-Serie, sonst Gesamt (Venue-Dedup wie
    die Card). Schlankes Payload für die Event-Page. None wenn keine Serien."""
    def _pick(team_id, pref):
        by_type, score = {}, (lambda v: 2 if v == pref else (1 if v == "all" else 0))
        for s in _streaks_index().get(str(team_id), []):
            cur = by_type.get(s.get("type"))
            if cur is None or score(s.get("venue")) > score(cur.get("venue")):
                by_type[s.get("type")] = s
        return list(by_type.values())
    ms = _pick(home_id, "H") + _pick(away_id, "A")
    ms.sort(key=lambda s: -(s.get("length") or 0))
    out = [{
        "team": s.get("team"), "teamId": s.get("teamId"), "type": s.get("type"),
        "market": s.get("market"), "length": s.get("length"), "venue": s.get("venue"),
        "ratePct": s.get("ratePct"), "oppSupportPct": s.get("oppSupportPct"),
        "seq": s.get("seq"), "continuation": s.get("continuation"),
        "next": s.get("next"), "signalInfo": s.get("signalInfo"),
    } for s in ms[:6]]
    return out or None


def build_payload(group_id, group_data, fixture, team_lookup, wm, history=None, ai_previews=None, poly_lookup=None):
    home_id = fixture["home"]
    away_id = fixture["away"]
    home_team = team_lookup[home_id]
    away_team = team_lookup[away_id]

    date = fixture["date"]
    slug = f"{_PFX}-{home_id.lower()}-vs-{away_id.lower()}-{date}"
    # KO-Spiele haben 'round' (R32/R16/…) statt 'matchday' → pick_key "KO-R32-…" wie generate_wm_picks.
    _md = fixture.get("matchday") or fixture.get("round") or "KO"
    pick_key = f"{group_id}-{_md}-{home_id}-{away_id}"
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

    # Model probabilities — direkt aus Elo-Modell (konsistent und vollständig)
    co_host = home_id in CO_HOSTS
    mod_home, mod_draw, mod_away = model_probs_from_elo(home_elo, away_elo, co_host)

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

    # xG: echte API-Football Werte wenn vorhanden, sonst Poisson-Fallback
    xg_stats   = wm.get("xgStats", {})
    home_xg_d  = xg_stats.get(home_id)
    away_xg_d  = xg_stats.get(away_id)

    if home_xg_d and away_xg_d and home_xg_d.get("games", 0) >= 3 and away_xg_d.get("games", 0) >= 3:
        # Blend: (home_attack + away_defence) / 2 — same logic as Poisson but with real xG rates
        xg_home = round((home_xg_d["xgForAvg"] + away_xg_d["xgAgainstAvg"]) / 2, 2)
        xg_away = round((away_xg_d["xgForAvg"] + home_xg_d["xgAgainstAvg"]) / 2, 2)
        xg_source = "api_football"
    elif home_xg_d and home_xg_d.get("games", 0) >= 3:
        # Only home xG available — mix with Poisson for away
        _, xg_away_fb = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_home = round(home_xg_d["xgForAvg"], 2)
        xg_away = xg_away_fb
        xg_source = "partial"
    elif away_xg_d and away_xg_d.get("games", 0) >= 3:
        # Only away xG available — mix with Poisson for home
        xg_home_fb, _ = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_home = xg_home_fb
        xg_away = round(away_xg_d["xgForAvg"], 2)
        xg_source = "partial"
    else:
        xg_home, xg_away = poisson_xg(home_form, away_form, home_elo, away_elo, home_id in CO_HOSTS)
        xg_source = "poisson"

    # Polymarket data (from wm_poly_prices.json)
    poly_fix = (poly_lookup or {}).get(odds_key)
    poly_out = None
    if poly_fix:
        poly_out = {
            "hw":          poly_fix.get("poly_hw"),
            "dr":          poly_fix.get("poly_dr"),
            "aw":          poly_fix.get("poly_aw"),
            "o25":         poly_fix.get("poly_o25"),
            "u25":         poly_fix.get("poly_u25"),
            "btts":        poly_fix.get("poly_btts"),
            "vol":         poly_fix.get("vol"),
            "edge_hw":     poly_fix.get("edge_hw"),
            "edge_dr":     poly_fix.get("edge_dr"),
            "edge_aw":     poly_fix.get("edge_aw"),
            "edge_o25":    poly_fix.get("edge_o25"),
            "edge_u25":    poly_fix.get("edge_u25"),
            "bestEdge":    poly_fix.get("bestEdge"),
            "bestEdgeKey": poly_fix.get("bestEdgeKey"),
            "steamLag":    poly_fix.get("steamLag"),
            "hasPinnacle": poly_fix.get("hasPinnacle"),
            "slug":        poly_fix.get("slug"),
            "moreMktSlug": poly_fix.get("moreMktSlug"),
        }

    # Player props (anytime scorer) — aus wm2026-player-props.json (keyed by matchKey)
    # fetch_wm_player_props.py schreibt: { "MEX-ZAF": { "players": [{name, teamId, odds}, ...] } }
    # Wir transformieren zu { "MEX": {"anytime": 2.50}, "ZAF": {"anytime": 3.50} }
    player_props_out = {home_id: None, away_id: None}
    props_file_data = load_json(PROPS_FILE) or {}
    match_props = props_file_data.get(h2h_key)  # h2h_key = "MEX-ZAF"
    if match_props and isinstance(match_props.get("players"), list):
        team_best: dict[str, float] = {}
        for p in match_props["players"]:
            tid  = p.get("teamId")
            odds = p.get("odds")
            if tid and odds:
                # Beste (niedrigste) Quote pro Team behalten
                if tid not in team_best or odds < team_best[tid]:
                    team_best[tid] = float(odds)
        for tid, best_odds in team_best.items():
            player_props_out[tid] = {"anytime": best_odds}

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

    # Bet Insights (rule-based, from form + H2H — must be after h2h_out is set)
    bet_insights = generate_bet_insights(
        home_id, away_id,
        home_form, away_form,
        h2h_out,
        home_team, away_team,
    )

    # Pinnacle- + Soft-Bookie-Odds-Strips (Opening → jetzt) für die Match-Page-Strips
    _oo = (odds_raw or {}).get("odds_open") or {}
    pinn_odds = None
    if odds_raw and odds_raw.get("hw"):
        pinn_odds = {
            "openH": _oo.get("hw"), "openD": _oo.get("dr"), "openA": _oo.get("aw"),
            "nowH": odds_raw.get("hw"), "nowD": odds_raw.get("dr"), "nowA": odds_raw.get("aw"),
            "book": odds_raw.get("bookmaker") or "Pinnacle",
        }
    soft_odds = None
    if odds_raw and odds_raw.get("public_hw"):
        soft_odds = {
            "openH": odds_raw.get("public_hw_open"), "openD": odds_raw.get("public_dr_open"),
            "openA": odds_raw.get("public_aw_open"),
            "nowH": odds_raw.get("public_hw"), "nowD": odds_raw.get("public_dr"),
            "nowA": odds_raw.get("public_aw"),
            "book": odds_raw.get("public_bookmaker") or "Soft-Books",
        }

    # Smart-Money (Polymarket-Wallet-Verteilung) für dieses Spiel
    smart_money = _smartmoney_all().get(odds_key)

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
        "matchday":   _md,
        "round":      fixture.get("round"),
        "roundLabel": fixture.get("roundLabel"),
        "pickKey":    pick_key,
        "homeElo":    home_elo,
        "awayElo":    away_elo,
        "eloDiff":    elo_diff,
        "xgHome":     xg_home,
        "xgAway":     xg_away,
        "xgSource":   xg_source,  # "api_football" | "partial" | "poisson"
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
        # AI Preview
        "aiPreview":     (ai_previews or {}).get(pick_key, {}).get("text"),
        "aiTgSnippet":   (ai_previews or {}).get(pick_key, {}).get("tgSnippet"),
        # Player Spotlights
        "playerSpotlights": _match_player_spotlights(wm, home_id, away_id),
        # Aufstellung (wm_lineups.json, ~T-1h) — Formation/Trainer/Start-XI/Bank
        "lineups": _lineup_for(home_id, away_id),
        # Serien (compute_streaks) — Heim/Auswärts-passend, lebendig (Matchup + Signale + seqViz)
        "streaks": _streaks_for_match(home_id, away_id),
        # Squad key players (with extended stats: shots, cards, rating, etc.)
        "squads": {
            home_id: wm.get("squads", {}).get(home_id),
            away_id: wm.get("squads", {}).get(away_id),
        },
        # Corner averages per team (from fetch_wm_corners.py)
        "cornersHome": wm.get("cornersForm", {}).get(home_id),
        "cornersAway": wm.get("cornersForm", {}).get(away_id),
        # Injuries & Suspensions (from fetch_wm_injuries.py, ab WM-Start)
        "injuriesHome": wm.get("injuries", {}).get(home_id, {}).get("players"),
        "injuriesAway": wm.get("injuries", {}).get(away_id, {}).get("players"),
        # Bet Insights + Polymarket + Player Props
        "betInsights":   bet_insights,
        "polyData":      poly_out,
        "pinnOdds":      pinn_odds,
        "softOdds":      soft_odds,
        "smartMoney":    smart_money,
        "playerProps":   player_props_out,
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
        # Meta — ISO 8601 für browser-kompatibles Parsing (Safari/Firefox sind strikt).
        # Vorher "06.06.2026 06:57 UTC" → Safari gab Invalid Date → "Aktualisiert vor 43866m" Bug.
        "generatedAt":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generatedAtHuman": datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),  # für Anzeige falls gebraucht
    }
    return slug, payload


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    wm = load_json(WM_FILE)
    if not wm:
        print(f"ERROR: {WM_FILE} not found.")
        return

    history     = load_json(HISTORY_FILE) or {}
    ai_previews = wm.get("aiPreviews", {})
    poly_raw    = load_json(POLY_FILE) or {}
    poly_lookup = {f["key"]: f for f in poly_raw.get("allFixtures", [])}
    print(f"  Odds history: {len(history)} Fixtures mit Snapshots")
    print(f"  AI Previews: {len(ai_previews)} gecacht")
    print(f"  Polymarket:  {len(poly_lookup)} Fixtures geladen")

    # Build flat team lookup {id -> team_dict}
    team_lookup = {}
    for group_data in wm["groups"].values():
        for t in group_data.get("teams", []):
            team_lookup[t["id"]] = t

    generated = 0
    slugs = []

    # Liga: nur „live" Spiele bepagen (Quoten da ODER ≤2 Wochen) — sonst 1066 statt ~40 Seiten.
    _odds = wm.get("odds") or {}
    _two_weeks = (datetime.utcnow().date() + timedelta(days=14)).isoformat()
    _today = datetime.utcnow().date().isoformat()

    for group_id, group_data in wm["groups"].items():
        for fixture in group_data.get("fixtures", []):
            home_id = fixture.get("home")
            away_id = fixture.get("away")
            if not home_id or not away_id:
                continue
            if _IS_LIGA:
                _d = (fixture.get("date") or "")[:10]
                _live = (f"{home_id}-{away_id}" in _odds) or (_today <= _d <= _two_weeks)
                if not _live:
                    continue
            if home_id not in team_lookup or away_id not in team_lookup:
                print(f"  SKIP: unknown team {home_id} or {away_id}")
                continue

            slug, payload = build_payload(group_id, group_data, fixture, team_lookup, wm, history, ai_previews, poly_lookup)
            out_path = os.path.join(DATA_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            slugs.append(slug)
            generated += 1
            print(f"  ✓ {payload['home']} vs {payload['away']}  [{slug}.json]")

    # KO-Spiele (30.06.2026, Lucas: „Event-Pages komplett leer in der KO-Phase"): liegen in koFixtures,
    # nicht groups → wurden nie bepaged. Synthetische „KO"-Gruppe mit globaler Team-Union; der Slug
    # (wm-{h}-vs-{a}-{date}) matcht exakt den [↗ Analyse]-Link der KO-Card. Nur bothResolved Paarungen.
    if not _IS_LIGA:
        _ko_group = {"name": "K.-o.-Runde", "teams": list(team_lookup.values()), "fixtures": []}
        for fixture in (wm.get("koFixtures") or []):
            home_id, away_id = fixture.get("home"), fixture.get("away")
            if not home_id or not away_id:
                continue
            if home_id not in team_lookup or away_id not in team_lookup:
                print(f"  SKIP KO: unknown team {home_id} or {away_id}")
                continue
            slug, payload = build_payload("KO", _ko_group, fixture, team_lookup, wm,
                                          history, ai_previews, poly_lookup)
            out_path = os.path.join(DATA_DIR, f"{slug}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            slugs.append(slug)
            generated += 1
            print(f"  ✓ {payload['home']} vs {payload['away']}  [KO {slug}.json]")

    # Index (dataset-bewusst: wm-index.json bzw. liga-index.json)
    index_path = os.path.join(BASE, "matches", f"{_PFX}-index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "slugs": slugs,
            "generated": datetime.utcnow().isoformat(),
            "count": generated,
        }, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n✅ Generated {generated} {_PFX.upper()} match pages → matches/data/{_PFX}-*.json")
    print(f"   Index: matches/{_PFX}-index.json")
    print(f"   Template: matches/wm-match.html")


if __name__ == "__main__":
    main()
