#!/usr/bin/env python3
"""
backtest_v3.py — BetEdge Pressure System Historical Validation
==============================================================
v3 vs. v2:
  • Live League Table Reconstruction — builds per-matchday standings from CSV
    results (no API calls needed — same source as match data)
  • Pressure System Simulation — mirrors calc_pressure() from update_dashboard.py
    using reconstructed tables: pressureRatio, mustWin, canDraw per team per game
  • Pressure Boosts applied to result / goals / draw scoring
  • Side-by-side comparison: v2 (no pressure) vs v3 (pressure-aware)
  • Validates statistically how much the pressure layer adds to pick accuracy

RUN:  python3 backtest_v3.py
OUT:  backtest_v3_report.html

Requires: pip install requests pandas
"""

import os, sys, json, math, time, webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

try:
    import requests
    import pandas as pd
except ImportError:
    print("📦  Installing required packages...")
    os.system(f"{sys.executable} -m pip install requests pandas --quiet")
    import requests
    import pandas as pd

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────
BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
SEASONS  = ["2223", "2324", "2425"]

LEAGUES = {
    "ENG": {"code": "E0",  "name": "Premier League",    "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "GER": {"code": "D1",  "name": "Bundesliga",         "flag": "🇩🇪"},
    "ITA": {"code": "I1",  "name": "Serie A",            "flag": "🇮🇹"},
    "ESP": {"code": "SP1", "name": "La Liga",            "flag": "🇪🇸"},
    "FRA": {"code": "F1",  "name": "Ligue 1",            "flag": "🇫🇷"},
    "NED": {"code": "N1",  "name": "Eredivisie",         "flag": "🇳🇱"},
    "POR": {"code": "P1",  "name": "Primeira Liga",      "flag": "🇵🇹"},
    "SCO": {"code": "SC0", "name": "Scottish Prem",      "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿"},
    "TUR": {"code": "T1",  "name": "Süper Lig",          "flag": "🇹🇷"},
    "BEL": {"code": "B1",  "name": "Belgian Pro League", "flag": "🇧🇪"},
    "AUT": {"code": "A1",  "name": "Österreich BL",      "flag": "🇦🇹"},
}

# Per-league structure: total teams, auto-relegation, playoff-relegation, CL spots
LEAGUE_CFGS = {
    "ENG": {"total": 20, "rel": 3, "rel_playoff": 0, "cl": 4, "rounds": 38},
    "GER": {"total": 18, "rel": 2, "rel_playoff": 1, "cl": 4, "rounds": 34},
    "ITA": {"total": 20, "rel": 3, "rel_playoff": 0, "cl": 4, "rounds": 38},
    "ESP": {"total": 20, "rel": 3, "rel_playoff": 0, "cl": 4, "rounds": 38},
    "FRA": {"total": 18, "rel": 3, "rel_playoff": 0, "cl": 4, "rounds": 34},
    "NED": {"total": 18, "rel": 1, "rel_playoff": 1, "cl": 3, "rounds": 34},
    "POR": {"total": 18, "rel": 2, "rel_playoff": 1, "cl": 3, "rounds": 34},
    "SCO": {"total": 12, "rel": 1, "rel_playoff": 1, "cl": 3, "rounds": 22},
    "TUR": {"total": 18, "rel": 3, "rel_playoff": 1, "cl": 4, "rounds": 34},
    "BEL": {"total": 16, "rel": 2, "rel_playoff": 0, "cl": 4, "rounds": 30},
    "AUT": {"total": 12, "rel": 2, "rel_playoff": 1, "cl": 3, "rounds": 22},
}

WARMUP_GAMES = 6

LG_CAPS = {
    "ENG": +0.05, "GER": +0.05, "ITA": -0.04, "FRA": -0.04,
    "ESP":  0.00, "NED": +0.03, "POR":  0.00, "SCO": +0.02,
    "TUR": +0.02, "BEL": +0.02, "AUT":  0.00,
}


# ─────────────────────────────────────────────────────────────────
#  STEP 1 — DOWNLOAD DATA (identical to v2)
# ─────────────────────────────────────────────────────────────────
def fetch_csv(season: str, code: str) -> Optional[pd.DataFrame]:
    url = BASE_URL.format(season=season, code=code)
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or len(r.text.strip()) < 100:
            return None
        from io import StringIO
        df = pd.read_csv(StringIO(r.text), encoding="utf-8", on_bad_lines="skip")
        if not {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}.issubset(df.columns):
            return None
        df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"])
        df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
        df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
        df = df.dropna(subset=["FTHG", "FTAG"])
        for col in ["HS", "AS", "HST", "AST"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            df = df.sort_values("Date")
        has_shots = {"HST", "AST"}.issubset(df.columns)
        print(f"    ✅ {season} {code}: {len(df)} Spiele {'(shots ✓)' if has_shots else '(shots ✗ → goals proxy)'}")
        return df
    except Exception as e:
        print(f"    ❌ {season} {code}: {e}")
        return None


def load_all_data() -> dict:
    all_data = {}
    for key, meta in LEAGUES.items():
        print(f"  {meta['flag']} {meta['name']}:")
        frames = []
        for season in SEASONS:
            df = fetch_csv(season, meta["code"])
            if df is not None:
                df["_league"] = key
                df["_season"] = season
                frames.append(df)
        if frames:
            all_data[key] = pd.concat(frames, ignore_index=True)
            print(f"    → {len(all_data[key])} Spiele total\n")
        else:
            print(f"    → Keine Daten verfügbar\n")
    return all_data


# ─────────────────────────────────────────────────────────────────
#  STEP 2 — ROLLING STATS ENGINE (from v2)
# ─────────────────────────────────────────────────────────────────
class TeamStats:
    def __init__(self):
        self.results_home   = []
        self.results_away   = []
        self.goals_scored   = []
        self.goals_conceded = []
        self.all_results    = []
        self.sot_home       = []
        self.sot_away       = []
        self.shots_home     = []
        self.shots_away     = []
        self.cs_home        = []
        self.cs_away        = []
        self.fts_home       = []
        self.fts_away       = []

    def home_win_rate(self, n=20) -> float:
        r = self.results_home[-n:]
        return r.count("W") / len(r) if r else 0.45

    def away_win_rate(self, n=20) -> float:
        r = self.results_away[-n:]
        return r.count("W") / len(r) if r else 0.30

    def form_score(self, n=6) -> float:
        r = self.all_results[-n:]
        if not r: return 0.5
        pts = sum(1.0 if x == "W" else 0.4 if x == "D" else 0.0 for x in r)
        return pts / len(r)

    def streak(self) -> int:
        if not self.all_results: return 0
        last  = self.all_results[-1]
        if last == "D": return 0
        count = 0
        for r in reversed(self.all_results):
            if r == last: count += 1 if last == "W" else -1
            else: break
        return count

    def avg_goals_scored(self, n=10) -> float:
        g = self.goals_scored[-n:]
        return sum(g) / len(g) if g else 1.4

    def avg_goals_conceded(self, n=10) -> float:
        g = self.goals_conceded[-n:]
        return sum(g) / len(g) if g else 1.3

    def games_played(self) -> int:
        return len(self.all_results)

    def xg_home(self, n=10) -> Optional[float]:
        sot   = self.sot_home[-n:]
        shots = self.shots_home[-n:]
        if not sot: return None
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 1.5
        return round(avg_sot * 0.35 + max(0, avg_shots - avg_sot) * 0.055, 3)

    def xg_away(self, n=10) -> Optional[float]:
        sot   = self.sot_away[-n:]
        shots = self.shots_away[-n:]
        if not sot: return None
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 1.5
        return round(avg_sot * 0.35 + max(0, avg_shots - avg_sot) * 0.055, 3)

    def clean_sheet_rate_home(self, n=15) -> float:
        cs = self.cs_home[-n:]
        return sum(cs) / len(cs) if cs else 0.25

    def clean_sheet_rate_away(self, n=15) -> float:
        cs = self.cs_away[-n:]
        return sum(cs) / len(cs) if cs else 0.25

    def failed_to_score_rate_home(self, n=15) -> float:
        fts = self.fts_home[-n:]
        return sum(fts) / len(fts) if fts else 0.20

    def failed_to_score_rate_away(self, n=15) -> float:
        fts = self.fts_away[-n:]
        return sum(fts) / len(fts) if fts else 0.20

    def record_home(self, scored, conceded, h_sot=None, h_shots=None):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_home.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)
        self.cs_home.append(1 if conceded == 0 else 0)
        self.fts_home.append(1 if scored == 0 else 0)
        if h_sot is not None and not math.isnan(h_sot):
            self.sot_home.append(h_sot)
            self.shots_home.append(h_shots if h_shots is not None and not math.isnan(h_shots) else h_sot * 2.5)

    def record_away(self, scored, conceded, a_sot=None, a_shots=None):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_away.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)
        self.cs_away.append(1 if conceded == 0 else 0)
        self.fts_away.append(1 if scored == 0 else 0)
        if a_sot is not None and not math.isnan(a_sot):
            self.sot_away.append(a_sot)
            self.shots_away.append(a_shots if a_shots is not None and not math.isnan(a_shots) else a_sot * 2.5)


class H2HTracker:
    def __init__(self):
        self._store = defaultdict(lambda: {"home_wins": 0, "draws": 0, "away_wins": 0, "n": 0})

    def _key(self, home, away):
        return tuple(sorted([home, away]))

    def record(self, home, away, result):
        k = self._key(home, away)
        d = self._store[k]
        d["n"] += 1
        if result == "H":
            if home < away: d["home_wins"] += 1
            else:           d["away_wins"] += 1
        elif result == "A":
            if home < away: d["away_wins"] += 1
            else:           d["home_wins"] += 1
        else:
            d["draws"] += 1

    def get(self, home, away) -> dict:
        k = self._key(home, away)
        d = self._store[k]
        n = d["n"]
        if n < 3:
            return {"home_win_rate": 0.45, "draw_rate": 0.25, "away_win_rate": 0.30, "n": n}
        hw = d["home_wins"] / n if home <= away else d["away_wins"] / n
        aw = d["away_wins"] / n if home <= away else d["home_wins"] / n
        return {"home_win_rate": hw, "draw_rate": d["draws"] / n, "away_win_rate": aw, "n": n}


# ─────────────────────────────────────────────────────────────────
#  STEP 3 — LEAGUE TABLE (v3 NEW)
# ─────────────────────────────────────────────────────────────────
class LeagueTable:
    """
    Maintains a live league table for one season.
    Updated AFTER each match result is processed.
    Queried BEFORE the match to compute pressure on both teams.
    """

    def __init__(self):
        # team → {pts, w, d, l, gf, ga, gd, played}
        self._rows: dict = {}

    def _ensure(self, team: str):
        if team not in self._rows:
            self._rows[team] = {"pts": 0, "w": 0, "d": 0, "l": 0,
                                 "gf": 0, "ga": 0, "gd": 0, "played": 0}

    def update(self, home: str, away: str, hg: int, ag: int):
        self._ensure(home)
        self._ensure(away)
        h = self._rows[home]
        a = self._rows[away]
        h["gf"] += hg; h["ga"] += ag; h["gd"] += (hg - ag); h["played"] += 1
        a["gf"] += ag; a["ga"] += hg; a["gd"] += (ag - hg); a["played"] += 1
        if hg > ag:
            h["pts"] += 3; h["w"] += 1; a["l"] += 1
        elif hg < ag:
            a["pts"] += 3; a["w"] += 1; h["l"] += 1
        else:
            h["pts"] += 1; h["d"] += 1
            a["pts"] += 1; a["d"] += 1

    def snapshot(self) -> list:
        """Return sorted table: pts desc → gd desc → gf desc → team asc."""
        rows = [{"team": t, **v} for t, v in self._rows.items()]
        rows.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"], x["team"]))
        for i, r in enumerate(rows):
            r["pos"] = i + 1
        return rows

    def get_pts(self, snap: list, pos: int) -> int:
        """Return points of team at given position (1-indexed). 0 if not found."""
        if 1 <= pos <= len(snap):
            return snap[pos - 1]["pts"]
        return 0

    def team_pos(self, snap: list, team: str) -> Optional[int]:
        for r in snap:
            if r["team"] == team:
                return r["pos"]
        return None

    def team_pts(self, snap: list, team: str) -> int:
        for r in snap:
            if r["team"] == team:
                return r["pts"]
        return 0


# ─────────────────────────────────────────────────────────────────
#  STEP 4 — PRESSURE COMPUTATION (v3 NEW)
# ─────────────────────────────────────────────────────────────────
PressureTuple = Tuple[float, bool, bool]   # (pressureRatio, mustWin, canDraw)


def calc_pressure_v3(team: str, snap: list, table: LeagueTable,
                     league_cfg: dict, rounds_left: int) -> PressureTuple:
    """
    Simplified pressure calc — mirrors logic of calc_pressure() in update_dashboard.py
    but works from a reconstructed CSV table snapshot.

    Returns (pressureRatio, mustWin, canDraw).
    pressureRatio: 0.0 (safe/dead-rubber) → 1.0 (desperate)
    mustWin:  pressureRatio > 0.65
    canDraw:  pressureRatio < 0.30
    """
    if not snap or rounds_left <= 0:
        return (0.0, False, True)

    total     = league_cfg["total"]
    rel       = league_cfg["rel"]
    rel_ply   = league_cfg.get("rel_playoff", 0)
    cl        = league_cfg.get("cl", 4)
    max_gain  = rounds_left * 3
    if max_gain == 0:
        return (0.0, False, True)

    pos      = table.team_pos(snap, team)
    team_pts = table.team_pts(snap, team)

    if pos is None:
        return (0.0, False, True)   # team not yet in table

    points_needed = 0

    # ── Relegation danger ────────────────────────────────────────
    rel_start = total - rel + 1           # first auto-relegated position
    safe_pos  = rel_start - rel_ply - 1  # last fully safe position

    if safe_pos < 1:
        safe_pos = total - rel            # fallback if playoff zone is 0

    if pos > safe_pos:
        # In relegation/playoff zone — need to climb above safe_pos
        pts_safe      = table.get_pts(snap, safe_pos)
        gap           = pts_safe - team_pts

        # Mathematically cannot escape → dead rubber, no pressure signal
        if gap > max_gain:
            return (0.0, False, True)

        # Competitor-adjusted: safe team will also gain points — rough estimate
        # Assume safe team earns ~1.2 PPG for remaining rounds
        comp_gain = min(max_gain, rounds_left * 1.2)
        points_needed = max(0, gap + round(comp_gain * 0.4))

        # Playoff zone (softer pressure): scale down by 40%
        if pos <= total - rel:
            points_needed = max(0, round(points_needed * 0.6))

    # ── Title/CL chase ───────────────────────────────────────────
    elif pos == cl + 1 or pos == cl + 2:
        # Just outside CL zone — chasing if gap is closeable
        pts_cl   = table.get_pts(snap, cl)
        gap      = pts_cl - team_pts
        if gap <= max_gain * 0.6:
            # Still in the race — moderate upward pressure
            points_needed = max(0, gap + 1)
            # Scale: chasing is less desperate than relegation battle
            points_needed = round(points_needed * 0.7)

    pressure_ratio = min(1.0, points_needed / max_gain) if max_gain > 0 else 0.0
    pressure_ratio = round(pressure_ratio, 3)

    return (pressure_ratio, pressure_ratio > 0.65, pressure_ratio < 0.30)


# ─────────────────────────────────────────────────────────────────
#  STEP 5 — SCORING ENGINE (v2 base + v3 pressure layer)
# ─────────────────────────────────────────────────────────────────

def score_heimsieg(hFS_home, hStreak, homeWinRate, homeAttStr, awayDefStr,
                   homeInForm, awayInForm, homePoor) -> float:
    sc = 0.40 + (hFS_home - 0.5) * 1.20 + max(0, hStreak) * 0.09 + homeWinRate * 0.35
    if homeInForm and not awayInForm: sc += 0.28
    if homePoor:    sc -= 0.48
    if awayInForm and not homeInForm: sc -= 0.20
    return sc

def score_auswärtssieg(aFS_away, aStreak, awayWinRate, awayAttStr, homeDefStr,
                       awayInForm, homeInForm, awayPoor) -> float:
    sc = 0.26 + (aFS_away - 0.5) * 1.20 + max(0, aStreak) * 0.09 + awayWinRate * 0.35
    if awayInForm and not homeInForm: sc += 0.28
    if awayPoor:    sc -= 0.48
    if homeInForm and not awayInForm: sc -= 0.20
    return sc

def score_draw(drawRate, hFS_home, aFS_away) -> float:
    sc = drawRate * 0.85 + (0.22 if drawRate > 0.36 else 0)
    if abs(hFS_home - aFS_away) < 0.10: sc += 0.12
    return sc

def score_over25(expGoals, homeAttStr, awayAttStr, lg_cap=0.0) -> Optional[float]:
    if expGoals < 2.50: return None   # Hard Gate
    sc = (expGoals - 2.5) * 0.55 + (homeAttStr - 1.2) * 0.18 + (awayAttStr - 1.0) * 0.18
    sc += lg_cap
    return max(0.0, min(sc, 0.92))

def score_under25(expGoals, homeAttStr, awayAttStr, lg_cap=0.0,
                  homeCSR=0.0, awayCSR=0.0) -> float:
    sc = (2.5 - expGoals) * 0.55 + max(0, 1.2 - homeAttStr) * 0.18 + max(0, 1.0 - awayAttStr) * 0.18
    sc -= lg_cap
    if homeCSR > 0.40: sc += 0.08
    elif homeCSR > 0.30: sc += 0.04
    if awayCSR > 0.35: sc += 0.06
    elif awayCSR > 0.25: sc += 0.03
    return max(0.0, min(sc, 0.92))

def score_btts(homeAttStr, awayAttStr, homeDefStr, awayDefStr,
               homeCSR=0.0, awayCSR=0.0, homeFTSR=0.0, awayFTSR=0.0) -> float:
    if homeAttStr > 1.30 and awayAttStr > 1.10 and homeDefStr > 0.90 and awayDefStr > 0.90:
        sc = 0.75
    elif homeAttStr > 1.15 and awayAttStr > 0.95 and homeDefStr > 0.85 and awayDefStr > 0.85:
        sc = 0.55
    else:
        sc = 0.20
    if homeCSR > 0.40: sc -= 0.18
    elif homeCSR > 0.30: sc -= 0.10
    if awayCSR > 0.35: sc -= 0.15
    elif awayCSR > 0.25: sc -= 0.08
    if homeFTSR > 0.30: sc -= 0.12
    if awayFTSR > 0.28: sc -= 0.10
    return max(0.05, min(sc, 0.92))

def conf_label(sc, thresholds):
    ht, mt = thresholds
    if sc >= ht: return "high"
    if sc >= mt: return "medium"
    return "low"

THRESHOLDS = {
    "heimsieg":     (1.20, 0.68),
    "auswärtssieg": (1.08, 0.62),
    "draw":         (0.70, 0.45),
    "over25":       (0.50, 0.20),
    "under25":      (0.45, 0.18),
    "btts":         (0.70, 0.45),
}


def _base_scores(home_stats: TeamStats, away_stats: TeamStats,
                 h2h: dict, league_key: str, row):
    """
    Computes all base scores (v2 logic, no pressure).
    Returns a dict with all intermediate values for reuse.
    """
    hFS    = home_stats.form_score()
    aFS    = away_stats.form_score()
    hStr   = home_stats.streak()
    aStr   = away_stats.streak()
    hHWR   = home_stats.home_win_rate()
    aAWR   = away_stats.away_win_rate()
    hAtt   = home_stats.avg_goals_scored()
    aAtt   = away_stats.avg_goals_scored()
    hDef   = home_stats.avg_goals_conceded()
    aDef   = away_stats.avg_goals_conceded()
    lg_cap = LG_CAPS.get(league_key, 0.0)

    h_xg   = home_stats.xg_home()
    a_xg   = away_stats.xg_away()
    if h_xg is not None and a_xg is not None:
        expGoals  = h_xg + a_xg
        xg_source = "shots"
    else:
        expGoals  = (hAtt + aDef + aAtt + hDef) / 2
        xg_source = "goals"

    homeCSR  = home_stats.clean_sheet_rate_home()
    awayCSR  = away_stats.clean_sheet_rate_away()
    homeFTSR = home_stats.failed_to_score_rate_home()
    awayFTSR = away_stats.failed_to_score_rate_away()

    hFS_home = min(0.93, hHWR * 0.55 + hFS * 0.45)
    aFS_away = max(0.07, aAWR * 0.55 + aFS * 0.45)
    homeInForm = hStr >= 2 and hFS_home > 0.62
    awayInForm = aStr >= 2 and aFS_away > 0.56
    homePoor   = hStr <= -3 or hFS_home < 0.25
    awayPoor   = aStr <= -3 or aFS_away < 0.22

    hwRate = h2h["home_win_rate"]
    drRate = h2h["draw_rate"]
    awRate = h2h["away_win_rate"]

    sc_h = score_heimsieg(hFS_home, hStr, hwRate, hAtt, aDef, homeInForm, awayInForm, homePoor)
    sc_a = score_auswärtssieg(aFS_away, aStr, awRate, aAtt, hDef, awayInForm, homeInForm, awayPoor)
    sc_d = score_draw(drRate, hFS_home, aFS_away)
    sc_ov = score_over25(expGoals, hAtt, aAtt, lg_cap)
    sc_un = score_under25(expGoals, hAtt, aAtt, lg_cap, homeCSR, awayCSR)
    sc_bt = score_btts(hAtt, aAtt, hDef, aDef, homeCSR, awayCSR, homeFTSR, awayFTSR)

    return dict(
        sc_h=sc_h, sc_a=sc_a, sc_d=sc_d,
        sc_ov=sc_ov, sc_un=sc_un, sc_bt=sc_bt,
        hFS_home=hFS_home, aFS_away=aFS_away,
        expGoals=expGoals, xg_source=xg_source, lg_cap=lg_cap,
    )


def picks_from_scores(bs: dict, label: str) -> list:
    """Convert base-score dict to 3 picks (result, goals, btts)."""
    sc_h, sc_a, sc_d = bs["sc_h"], bs["sc_a"], bs["sc_d"]
    sc_ov, sc_un, sc_bt = bs["sc_ov"], bs["sc_un"], bs["sc_bt"]
    xg_source = bs["xg_source"]

    picks = []

    # Result pick
    best_r = max([(sc_h, "heimsieg"), (sc_a, "auswärtssieg"), (sc_d, "draw")],
                 key=lambda x: x[0])
    sc_r, mkt_r = best_r
    picks.append({"market": mkt_r, "sc": sc_r, "conf": conf_label(sc_r, THRESHOLDS[mkt_r]),
                  "xg_source": xg_source, "label": label})

    # Goals pick (with Hard Gate)
    if sc_ov is None:
        picks.append({"market": "under25", "sc": sc_un,
                      "conf": conf_label(sc_un, THRESHOLDS["under25"]),
                      "xg_source": xg_source, "hard_gated": True, "label": label})
    elif sc_ov >= sc_un:
        picks.append({"market": "over25", "sc": sc_ov,
                      "conf": conf_label(sc_ov, THRESHOLDS["over25"]),
                      "xg_source": xg_source, "hard_gated": False, "label": label})
    else:
        picks.append({"market": "under25", "sc": sc_un,
                      "conf": conf_label(sc_un, THRESHOLDS["under25"]),
                      "xg_source": xg_source, "hard_gated": False, "label": label})

    # BTTS pick
    picks.append({"market": "btts", "sc": sc_bt,
                  "conf": conf_label(sc_bt, THRESHOLDS["btts"]),
                  "xg_source": xg_source, "label": label})

    return picks


def apply_pressure(bs: dict, h_pr: PressureTuple, a_pr: PressureTuple) -> dict:
    """
    v3: Apply pressure adjustments on top of base scores.

    Pressure signals mirror how real teams change their style:
    • mustWin home  → attack more → Heimsieg ↑, Draw ↓
    • mustWin away  → attack more → Auswärtssieg ↑, Draw ↓
    • Both mustWin  → open game → Over2.5 ↑, BTTS ↑
    • canDraw both  → cautious play → Draw ↑, Over2.5 ↓
    • High pressure → adrenaline → home advantage amplified
    """
    h_ratio, h_mw, h_cd = h_pr
    a_ratio, a_mw, a_cd = a_pr

    sc_h  = bs["sc_h"]
    sc_a  = bs["sc_a"]
    sc_d  = bs["sc_d"]
    sc_ov = bs["sc_ov"]
    sc_un = bs["sc_un"]
    sc_bt = bs["sc_bt"]

    # ── Result market ────────────────────────────────────────────
    if h_mw:
        sc_h += 0.14   # desperate home side pushes for win
        sc_d -= 0.09
    if a_mw:
        sc_a += 0.11   # away mustWin → same energy as home but diminished by travel
        sc_d -= 0.09
    if h_cd and a_cd:
        sc_d += 0.10   # both sides comfortable → more draws (dead rubbers)

    # ── Mild home pressure (chasing CL etc.) ────────────────────
    if not h_mw and h_ratio > 0.30:
        sc_h += h_ratio * 0.10   # proportional nudge

    # ── Goals / BTTS market ──────────────────────────────────────
    if h_mw and a_mw:
        # Both teams need a win → goalfest tendency
        if sc_ov is not None:
            sc_ov = min(0.92, sc_ov + 0.08)
        sc_un = max(0.05, sc_un - 0.06)
        sc_bt = min(0.92, sc_bt + 0.07)
    elif h_mw or a_mw:
        # One team desperately attacking → more goals, but other team defends
        if sc_ov is not None:
            sc_ov = min(0.92, sc_ov + 0.04)
        sc_bt = min(0.92, sc_bt + 0.03)

    if h_cd and a_cd:
        # Dead rubber → conservative → fewer goals
        if sc_ov is not None:
            sc_ov = max(0.0, sc_ov - 0.05)
        sc_un = min(0.92, sc_un + 0.04)
        sc_bt = max(0.05, sc_bt - 0.04)

    return dict(bs,
                sc_h=sc_h, sc_a=sc_a, sc_d=sc_d,
                sc_ov=sc_ov, sc_un=sc_un, sc_bt=sc_bt)


def evaluate_pick(market: str, hg: int, ag: int) -> bool:
    total = hg + ag
    if market == "heimsieg":     return hg > ag
    if market == "auswärtssieg": return ag > hg
    if market == "draw":         return hg == ag
    if market == "over25":       return total > 2.5
    if market == "under25":      return total < 2.5
    if market == "btts":         return hg > 0 and ag > 0
    return False


# ─────────────────────────────────────────────────────────────────
#  STEP 6 — ODDS EXTRACTION
# ─────────────────────────────────────────────────────────────────
def extract_odds(row: pd.Series, market: str) -> Optional[float]:
    candidates = {
        "heimsieg":     ["PSH",  "B365H", "BbAvH", "MaxH"],
        "auswärtssieg": ["PSA",  "B365A", "BbAvA", "MaxA"],
        "draw":         ["PSD",  "B365D", "BbAvD", "MaxD"],
        "over25":       ["PSC>2.5", "B365>2.5", "BbAv>2.5", "Max>2.5", "B365.1"],
        "under25":      ["PSC<2.5", "B365<2.5", "BbAv<2.5", "Max<2.5", "B365.2"],
        "btts":         [],
    }
    for col in candidates.get(market, []):
        if col in row.index:
            val = pd.to_numeric(row[col], errors="coerce")
            if pd.notna(val) and 1.05 <= val <= 25.0:
                return float(val)
    return None


# ─────────────────────────────────────────────────────────────────
#  STEP 7 — PROCESS ONE LEAGUE (v3: dual simulation)
# ─────────────────────────────────────────────────────────────────
def process_league(key: str, df: pd.DataFrame) -> list:
    """
    For each season in this league:
      • Rebuild the live table from match results (chronologically)
      • Compute pressure BEFORE each match
      • Run BOTH v2 (no pressure) and v3 (pressure-aware) picks
      • Record both sets of results for comparison
    """
    results = []
    league_cfg = LEAGUE_CFGS.get(key, {"total": 18, "rel": 3, "rel_playoff": 0,
                                        "cl": 4, "rounds": 34})

    has_shots       = {"HST", "AST"}.issubset(df.columns)
    has_total_shots = {"HS",  "AS" }.issubset(df.columns)

    for season in df["_season"].unique():
        df_s = df[df["_season"] == season].copy()
        if "Date" in df_s.columns:
            df_s = df_s.sort_values("Date")

        team_stats  = defaultdict(TeamStats)
        h2h_tracker = H2HTracker()
        table       = LeagueTable()
        total_rounds = league_cfg["rounds"]
        gp_count = 0

        for _, row in df_s.iterrows():
            home   = str(row["HomeTeam"]).strip()
            away   = str(row["AwayTeam"]).strip()
            hg     = int(row["FTHG"])
            ag     = int(row["FTAG"])
            ftr    = str(row["FTR"]).strip()

            hs  = team_stats[home]
            as_ = team_stats[away]
            h2h = h2h_tracker.get(home, away)

            # ── Pressure from PRE-MATCH table snapshot ────────────
            snap       = table.snapshot()
            hp_played  = hs.games_played()
            rounds_left = max(0, total_rounds - hp_played)
            h_pr = calc_pressure_v3(home, snap, table, league_cfg, rounds_left)
            a_pr = calc_pressure_v3(away, snap, table, league_cfg, rounds_left)

            # ── Only simulate after warmup ────────────────────────
            if hs.games_played() >= WARMUP_GAMES and as_.games_played() >= WARMUP_GAMES:
                gp_count += 1

                bs     = _base_scores(hs, as_, h2h, key, row)
                bs_v3  = apply_pressure(bs, h_pr, a_pr)

                picks_v2 = picks_from_scores(bs,    "v2")
                picks_v3 = picks_from_scores(bs_v3, "v3")

                # picks are always 3: [result, goals, btts]
                for p2, p3 in zip(picks_v2, picks_v3):
                    correct_v2 = evaluate_pick(p2["market"], hg, ag)
                    correct_v3 = evaluate_pick(p3["market"], hg, ag)
                    odds_v2    = extract_odds(row, p2["market"])
                    odds_v3    = extract_odds(row, p3["market"])
                    roi_v2     = ((odds_v2 - 1) if correct_v2 else -1.0) if odds_v2 else None
                    roi_v3     = ((odds_v3 - 1) if correct_v3 else -1.0) if odds_v3 else None

                    h_ratio, h_mw, h_cd = h_pr
                    a_ratio, a_mw, a_cd = a_pr
                    pressure_flag = "mustwin" if (h_mw or a_mw) else \
                                    "deadrubber" if (h_cd and a_cd) else "neutral"

                    results.append({
                        "league":      key,
                        "season":      season,
                        # v2
                        "market_v2":   p2["market"],
                        "conf_v2":     p2["conf"],
                        "sc_v2":       round(p2["sc"], 3),
                        "correct_v2":  correct_v2,
                        "odds_v2":     odds_v2,
                        "roi_v2":      roi_v2,
                        # v3
                        "market_v3":   p3["market"],
                        "conf_v3":     p3["conf"],
                        "sc_v3":       round(p3["sc"], 3),
                        "correct_v3":  correct_v3,
                        "odds_v3":     odds_v3,
                        "roi_v3":      roi_v3,
                        # pressure info
                        "h_pressure":  round(h_ratio, 3),
                        "a_pressure":  round(a_ratio, 3),
                        "h_mustWin":   h_mw,
                        "a_mustWin":   a_mw,
                        "pressure_flag": pressure_flag,
                        "market_changed": p2["market"] != p3["market"],
                        "xg_source":   p2.get("xg_source", "goals"),
                        "hard_gated":  p2.get("hard_gated", False),
                    })

            # ── Update tracking AFTER pick recorded ──────────────
            h_sot  = float(row["HST"]) if has_shots and pd.notna(row.get("HST")) else None
            a_sot  = float(row["AST"]) if has_shots and pd.notna(row.get("AST")) else None
            h_shts = float(row["HS"])  if has_total_shots and pd.notna(row.get("HS")) else None
            a_shts = float(row["AS"])  if has_total_shots and pd.notna(row.get("AS")) else None

            hs.record_home(hg, ag, h_sot, h_shts)
            as_.record_away(ag, hg, a_sot, a_shts)
            h2h_tracker.record(home, away, ftr)
            table.update(home, away, hg, ag)   # table updated LAST

        print(f"    {season}: {gp_count} Picks simuliert (Pressure-Games: "
              f"{sum(1 for r in results if r['season']==season and r['pressure_flag']=='mustwin')})")

    return results


# ─────────────────────────────────────────────────────────────────
#  STEP 8 — AGGREGATE (dual: v2 vs v3)
# ─────────────────────────────────────────────────────────────────
def agg_bucket():
    return {"n":0,"hits_v2":0,"hits_v3":0,"roi_v2":0,"roi_v3":0,"roi_n_v2":0,"roi_n_v3":0}

def aggregate(all_results: list) -> dict:
    by_mkt_conf = defaultdict(agg_bucket)  # (market, conf_v2)
    by_league   = defaultdict(agg_bucket)
    by_market   = defaultdict(agg_bucket)
    by_pressure = defaultdict(agg_bucket)  # "mustwin" / "deadrubber" / "neutral"

    for r in all_results:
        mc  = (r["market_v2"], r["conf_v2"])
        pflag = r["pressure_flag"]

        for bucket in [by_mkt_conf[mc], by_league[r["league"]],
                       by_market[r["market_v2"]], by_pressure[pflag]]:
            bucket["n"] += 1
            bucket["hits_v2"] += int(r["correct_v2"])
            bucket["hits_v3"] += int(r["correct_v3"])
            if r["roi_v2"] is not None:
                bucket["roi_v2"] += r["roi_v2"]; bucket["roi_n_v2"] += 1
            if r["roi_v3"] is not None:
                bucket["roi_v3"] += r["roi_v3"]; bucket["roi_n_v3"] += 1

    def finalise(d):
        out = {}
        for k, v in d.items():
            n = v["n"]
            hr2  = v["hits_v2"] / n * 100 if n else 0
            hr3  = v["hits_v3"] / n * 100 if n else 0
            roi2 = v["roi_v2"] / v["roi_n_v2"] * 100 if v["roi_n_v2"] else None
            roi3 = v["roi_v3"] / v["roi_n_v3"] * 100 if v["roi_n_v3"] else None
            out[k] = {
                "n": n,
                "hit_rate_v2": round(hr2, 1),
                "hit_rate_v3": round(hr3, 1),
                "delta_hr":    round(hr3 - hr2, 1),
                "roi_v2":      round(roi2, 1) if roi2 is not None else None,
                "roi_v3":      round(roi3, 1) if roi3 is not None else None,
                "delta_roi":   round(roi3 - roi2, 1) if (roi2 and roi3) else None,
            }
        return out

    # Extra: market-changed stats
    changed      = [r for r in all_results if r["market_changed"]]
    mustwin_game = [r for r in all_results if r["pressure_flag"] == "mustwin"]
    deadrubber   = [r for r in all_results if r["pressure_flag"] == "deadrubber"]

    return {
        "by_mkt_conf": finalise(by_mkt_conf),
        "by_league":   finalise(by_league),
        "by_market":   finalise(by_market),
        "by_pressure": finalise(by_pressure),
        "total":       len(all_results),
        "changed_n":   len(changed),
        "mustwin_n":   len(mustwin_game),
        "deadrubber_n": len(deadrubber),
    }


# ─────────────────────────────────────────────────────────────────
#  STEP 9 — HTML REPORT
# ─────────────────────────────────────────────────────────────────
MARKET_LABELS = {
    "heimsieg":     "🏠 Heimsieg",
    "auswärtssieg": "✈️ Auswärtssieg",
    "draw":         "🤝 Unentschieden",
    "over25":       "⚽ Über 2.5",
    "under25":      "🔒 Unter 2.5",
    "btts":         "🎯 Beide treffen",
}
CONF_LABELS = {"high": "★★★ Hoch", "medium": "★★☆ Mittel", "low": "★☆☆ Niedrig"}
PRESSURE_LABELS = {
    "mustwin":    "🔥 MustWin (≥1 Team unter Druck)",
    "deadrubber": "💤 Dead Rubber (beide entspannt)",
    "neutral":    "⚖️ Neutral",
}

def delta_color(d):
    if d is None: return "#888"
    if d >= 2:    return "#22c55e"
    if d >= 0.5:  return "#a3e635"
    if d >= -0.5: return "#888"
    if d >= -2:   return "#fb923c"
    return "#f85149"

def roi_color(roi):
    if roi is None: return "#888"
    if roi >= 5:    return "#22c55e"
    if roi >= 0:    return "#a3e635"
    if roi >= -5:   return "#fb923c"
    return "#f85149"

def hr_color(hr):
    if hr >= 65: return "#22c55e"
    if hr >= 50: return "#a3e635"
    if hr >= 40: return "#fb923c"
    return "#f85149"

def fmt_roi(r):
    if r is None: return "–"
    return f"{'+'if r>=0 else ''}{r:.1f}%"

def fmt_delta(d):
    if d is None: return "–"
    return f"{'+'if d>=0 else ''}{d:.1f}pp"


def build_html(agg: dict, all_results: list) -> str:
    now   = datetime.now().strftime("%d.%m.%Y %H:%M")
    total = agg["total"]
    bmc   = agg["by_mkt_conf"]
    blg   = agg["by_league"]
    bm    = agg["by_market"]
    bp    = agg["by_pressure"]

    markets  = ["heimsieg", "auswärtssieg", "draw", "over25", "under25", "btts"]
    confs    = ["high", "medium", "low"]

    # ── Key headline numbers ─────────────────────────────────────
    mustwin_d  = bp.get("mustwin",    {"hit_rate_v2": 0,"hit_rate_v3": 0,"delta_hr": 0,"n": 0})
    deadrub_d  = bp.get("deadrubber", {"hit_rate_v2": 0,"hit_rate_v3": 0,"delta_hr": 0,"n": 0})
    neutral_d  = bp.get("neutral",    {"hit_rate_v2": 0,"hit_rate_v3": 0,"delta_hr": 0,"n": 0})

    overall_v2 = sum(r["correct_v2"] for r in all_results) / total * 100 if total else 0
    overall_v3 = sum(r["correct_v3"] for r in all_results) / total * 100 if total else 0
    overall_delta = overall_v3 - overall_v2

    # ── Pressure breakdown table rows ───────────────────────────
    def p_row(flag, label):
        d = bp.get(flag, {"n": 0, "hit_rate_v2": 0, "hit_rate_v3": 0, "delta_hr": 0,
                          "roi_v2": None, "roi_v3": None, "delta_roi": None})
        if d["n"] < 5: return ""
        dc = delta_color(d["delta_hr"])
        return f"""<tr>
          <td style="font-weight:600">{label}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{d['hit_rate_v2']:.1f}%</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{d['hit_rate_v3']:.1f}%</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
          <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
          <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
          <td style="color:{delta_color(d['delta_roi'])}">{fmt_delta(d['delta_roi'])}</td>
        </tr>"""

    pressure_rows = "".join(p_row(f, l) for f, l in PRESSURE_LABELS.items())

    # ── Market×Conf table rows ────────────────────────────────
    def mc_row(mkt, conf):
        d = bmc.get((mkt, conf), {"n": 0, "hit_rate_v2": 0, "hit_rate_v3": 0,
                                   "delta_hr": 0, "roi_v2": None, "roi_v3": None})
        if d["n"] < 10: return ""
        dc = delta_color(d["delta_hr"])
        return f"""<tr>
          <td>{MARKET_LABELS.get(mkt, mkt)}</td>
          <td>{CONF_LABELS.get(conf, conf)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{d['hit_rate_v2']:.1f}%</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{d['hit_rate_v3']:.1f}%</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
          <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
          <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
        </tr>"""

    mc_rows = "".join(mc_row(m, c) for m in markets for c in confs)

    # ── League table rows ────────────────────────────────────────
    def lg_row(key):
        meta = LEAGUES.get(key, {"name": key, "flag": ""})
        d    = blg.get(key, {"n": 0, "hit_rate_v2": 0, "hit_rate_v3": 0, "delta_hr": 0})
        if d["n"] == 0: return ""
        dc = delta_color(d["delta_hr"])
        return f"""<tr>
          <td>{meta.get('flag','')} {meta.get('name', key)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{d['hit_rate_v2']:.1f}%</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{d['hit_rate_v3']:.1f}%</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
        </tr>"""

    lg_rows = "".join(lg_row(k) for k in sorted(blg.keys()))

    # ── Auto-findings ────────────────────────────────────────────
    findings = []

    # Overall delta
    if abs(overall_delta) < 0.3:
        findings.append(f"⚖️ <strong>Gesamteffekt minimal:</strong> Pressure-Schicht ändert Gesamttrefferquote um nur {fmt_delta(overall_delta)} — das ist statistisch nicht signifikant. Beide Modelle performen vergleichbar.")
    elif overall_delta > 0:
        findings.append(f"✅ <strong>Pressure verbessert Gesamtquote um {fmt_delta(overall_delta)}</strong> ({overall_v2:.1f}% → {overall_v3:.1f}%) — der Druckindikator hilft.")
    else:
        findings.append(f"⚠️ <strong>Pressure verschlechtert Gesamtquote um {fmt_delta(overall_delta)}</strong> — Kalibrierung der Druckgewichte notwendig.")

    # MustWin finding
    if mustwin_d["n"] > 50:
        if mustwin_d["delta_hr"] >= 2:
            findings.append(f"🔥 <strong>MustWin-Spiele:</strong> v3 schlägt v2 um {fmt_delta(mustwin_d['delta_hr'])} ({mustwin_d['hit_rate_v2']:.1f}% → {mustwin_d['hit_rate_v3']:.1f}%) bei {mustwin_d['n']:,} Spielen — Druck-Signal klar validiert.")
        elif mustwin_d["delta_hr"] > 0:
            findings.append(f"📈 <strong>MustWin-Spiele:</strong> leichte Verbesserung von {fmt_delta(mustwin_d['delta_hr'])} — Trend in die richtige Richtung, aber zu schwach für sichere Aussage.")
        else:
            findings.append(f"⚠️ <strong>MustWin-Spiele:</strong> kein Vorteil durch Pressure ({fmt_delta(mustwin_d['delta_hr'])}). Möglicherweise überschätzen wir den Druckeffekt.")

    # Dead rubber finding
    if deadrub_d["n"] > 20:
        if deadrub_d["delta_hr"] >= 1.5:
            findings.append(f"💤 <strong>Dead Rubbers:</strong> Pressure-Dämpfung hilft bei entspannten Spielen: +{deadrub_d['delta_hr']:.1f}pp.")
        elif deadrub_d["delta_hr"] < -1:
            findings.append(f"⚠️ <strong>Dead Rubbers:</strong> Pressure-Dämpfung schadet bei entspannten Spielen: {deadrub_d['delta_hr']:.1f}pp — Dead-Rubber-Anpassung überdenken.")

    # Changed picks
    pct_changed = agg["changed_n"] / total * 100 if total else 0
    findings.append(f"🔄 <strong>{agg['changed_n']:,} Picks ({pct_changed:.1f}%)</strong> wurden durch Pressure von v2 zu v3 geändert (anderer Markt). "
                    f"MustWin-Spiele: {agg['mustwin_n']:,} ({agg['mustwin_n']/total*100:.1f}%). Dead Rubbers: {agg['deadrubber_n']:,}.")

    # Best pressure improvement by league
    best_lg_delta = max(blg.items(), key=lambda x: x[1]["delta_hr"]) if blg else None
    if best_lg_delta:
        k, d = best_lg_delta
        meta = LEAGUES.get(k, {"name": k, "flag": ""})
        findings.append(f"🏆 <strong>Stärkster Pressure-Effekt:</strong> {meta.get('flag','')} {meta.get('name', k)} mit +{d['delta_hr']:.1f}pp durch v3 — Liga mit besonders klaren Drucksituationen.")

    findings_html = "".join(f"<li style='margin-bottom:10px'>{f}</li>" for f in findings)

    # ── Delta legend ─────────────────────────────────────────────
    delta_good = overall_delta >= 0
    headline_badge = (
        f"<span style='color:#22c55e;font-size:28px;font-weight:700'>+{overall_delta:.1f}pp ↑</span> v3 besser als v2"
        if delta_good else
        f"<span style='color:#fb923c;font-size:28px;font-weight:700'>{overall_delta:.1f}pp ↓</span> v2 besser als v3"
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>BetEdge Backtest v3 — Pressure Validation</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 24px; }}
  h1 {{ color: #f0f6fc; font-size: 26px; margin-bottom: 6px; }}
  h2 {{ color: #f0f6fc; font-size: 18px; margin: 28px 0 12px; padding-bottom: 6px;
        border-bottom: 1px solid #30363d; }}
  .subtitle {{ color: #8b949e; margin-bottom: 24px; font-size: 13px; }}
  .badge {{ display:inline-block; background:#21262d; border:1px solid #30363d;
            border-radius:6px; padding:3px 10px; font-size:12px; margin-right:8px; }}
  .badge.v3  {{ border-color:#7c3aed; color:#a78bfa; }}
  .badge.new {{ border-color:#0ea5e9; color:#7dd3fc; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
           gap:16px; margin-bottom:28px; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; }}
  .card .label {{ color:#8b949e; font-size:12px; margin-bottom:4px; }}
  .card .value {{ font-size:24px; font-weight:700; color:#f0f6fc; }}
  .card .sub   {{ font-size:11px; color:#8b949e; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:24px; font-size:13px; }}
  th {{ background:#161b22; color:#8b949e; text-align:left; padding:8px 10px;
        border-bottom:2px solid #30363d; font-size:12px; font-weight:600; }}
  td {{ padding:7px 10px; border-bottom:1px solid #21262d; }}
  tr:hover td {{ background:#161b22; }}
  .findings {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
               padding:18px 22px; margin-bottom:24px; }}
  .findings ul {{ padding-left:18px; }}
  .delta-hero {{ background:#161b22; border:1px solid #7c3aed; border-radius:10px;
                 padding:20px 24px; margin-bottom:24px; text-align:center; }}
  .legend {{ display:flex; gap:18px; flex-wrap:wrap; font-size:12px; color:#8b949e;
             margin-bottom:20px; }}
  .legend span {{ display:flex; align-items:center; gap:6px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
</style>
</head>
<body>
<h1>⚡ BetEdge Backtest v3 — Pressure System Validation</h1>
<div class="subtitle">
  Generiert: {now} &nbsp;|&nbsp; Saisons: {', '.join(SEASONS)} &nbsp;|&nbsp;
  Ligen: {len(LEAGUES)} &nbsp;|&nbsp; Picks gesamt: {total:,}
  <br style="margin:4px 0">
  <span class="badge v3">v3 NEU</span> Live-Tabellen-Rekonstruktion aus CSV-Resultaten
  <span class="badge new">NEU</span> Pressure-System: pressureRatio / mustWin / canDraw
  <span class="badge">v2 Basis</span> shots-xG · CS/FTS-Raten · Hard Gate · liga-Caps
</div>

<div class="delta-hero">
  <div style="font-size:14px;color:#8b949e;margin-bottom:8px">Gesamteffekt Pressure-Schicht (v3 vs. v2)</div>
  {headline_badge}
  <div style="font-size:13px;color:#8b949e;margin-top:8px">
    v2: {overall_v2:.1f}% &nbsp;→&nbsp; v3: {overall_v3:.1f}% &nbsp;|&nbsp;
    MustWin-Spiele: {agg['mustwin_n']:,} &nbsp;|&nbsp; Picks geändert: {agg['changed_n']:,}
  </div>
</div>

<div class="grid">
  <div class="card">
    <div class="label">Picks gesamt</div>
    <div class="value">{total:,}</div>
    <div class="sub">nach Warmup ({WARMUP_GAMES} Spiele)</div>
  </div>
  <div class="card">
    <div class="label">🔥 MustWin-Spiele</div>
    <div class="value">{agg['mustwin_n']:,}</div>
    <div class="sub">{agg['mustwin_n']/total*100:.1f}% aller Picks — mind. 1 Team unter Druck</div>
  </div>
  <div class="card">
    <div class="label">💤 Dead Rubbers</div>
    <div class="value">{agg['deadrubber_n']:,}</div>
    <div class="sub">{agg['deadrubber_n']/total*100:.1f}% — beide Teams entspannt</div>
  </div>
  <div class="card">
    <div class="label">🔄 Picks geändert</div>
    <div class="value">{agg['changed_n']:,}</div>
    <div class="sub">{agg['changed_n']/total*100:.1f}% — v2≠v3 Markt</div>
  </div>
</div>

<div class="legend">
  <span><span class="dot" style="background:#22c55e"></span>Hit-Rate ≥65% / Delta ≥+2pp</span>
  <span><span class="dot" style="background:#a3e635"></span>≥50% / ≥+0.5pp</span>
  <span><span class="dot" style="background:#888"></span>Neutral</span>
  <span><span class="dot" style="background:#fb923c"></span>&lt;50% / negativ</span>
  <span><span class="dot" style="background:#f85149"></span>&lt;40% / stark negativ</span>
</div>

<h2>🔍 Auto-Findings</h2>
<div class="findings"><ul>{findings_html}</ul></div>

<h2>⚡ Pressure-Kategorien: v2 vs. v3 Vergleich</h2>
<p style="color:#8b949e;font-size:12px;margin-bottom:12px">
  Kernfrage: Hilft das Pressure-Signal in den Situationen wo es am meisten wirken sollte?
</p>
<table>
  <tr>
    <th>Kategorie</th><th>n</th>
    <th>HR v2</th><th>HR v3</th><th>Δ HR</th>
    <th>ROI v2</th><th>ROI v3</th><th>Δ ROI</th>
  </tr>
  {pressure_rows}
</table>

<h2>📊 Markt × Konfidenz (v2 vs. v3)</h2>
<table>
  <tr>
    <th>Markt</th><th>Konfidenz</th><th>n</th>
    <th>HR v2</th><th>HR v3</th><th>Δ HR</th>
    <th>ROI v2</th><th>ROI v3</th>
  </tr>
  {mc_rows}
</table>

<h2>🌍 Ligen-Übersicht (v2 vs. v3)</h2>
<table>
  <tr><th>Liga</th><th>n</th><th>HR v2</th><th>HR v3</th><th>Δ HR</th></tr>
  {lg_rows}
</table>

<h2>💡 Methodische Hinweise</h2>
<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;font-size:13px;color:#8b949e;line-height:1.7">
  <p><strong style="color:#c9d1d9">Tabellenrekonstruktion statt API-Calls:</strong>
  Die Liga-Tabelle wird aus den CSV-Resultaten selbst rekonstruiert (chronologisch).
  Dies liefert denselben Informationsgehalt wie API-Football /standings?round=X —
  ohne ~570 API-Calls und unabhängig von Rate-Limits.</p>
  <br>
  <p><strong style="color:#c9d1d9">Pressure-Berechnung:</strong>
  pressureRatio = (benötigte Punkte / maximal erreichbare Punkte).
  Safe-Position = Gesamtteams − Abstiegsplätze − Playoff-Plätze.
  Competitor-adjusted: der safe-Team gewinnt ebenfalls ~1.2 PPG weiter.
  mustWin wenn pressureRatio &gt; 0.65, canDraw wenn &lt; 0.30.</p>
  <br>
  <p><strong style="color:#c9d1d9">Pressure-Adjustments:</strong>
  mustWin home → Heimsieg +0.14, Draw −0.09.
  mustWin away → Auswärtssieg +0.11, Draw −0.09.
  Beide mustWin → Over2.5 +0.08, BTTS +0.07.
  Beide canDraw → Draw +0.10, Over2.5 −0.05.</p>
  <br>
  <p><strong style="color:#c9d1d9">Warmup:</strong> {WARMUP_GAMES} Spiele pro Team &amp; Saison
  bevor Picks simuliert werden (vermeidet Kaltstartfehler).</p>
</div>

<div style="text-align:center;margin-top:32px;color:#484f58;font-size:11px">
  BetEdge Backtest v3 · Saisons {', '.join(SEASONS)} · {len(LEAGUES)} Ligen
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  BetEdge Backtest v3 — Pressure System Validation")
    print("=" * 60 + "\n")

    # Step 1: Download CSVs
    print("📥 SCHRITT 1: Daten laden …\n")
    all_data = load_all_data()

    if not all_data:
        print("❌ Keine Daten verfügbar. Internetverbindung prüfen.")
        return

    # Step 2: Simulate
    print("\n🔄 SCHRITT 2: Simuliere Picks (v2 ohne Druck / v3 mit Druck) …\n")
    all_results = []
    for key, df in all_data.items():
        meta = LEAGUES[key]
        print(f"  {meta['flag']} {meta['name']}:")
        league_results = process_league(key, df)
        all_results.extend(league_results)
        print(f"    → {len(league_results)} Einträge gesammelt\n")

    if not all_results:
        print("❌ Keine Picks simuliert.")
        return

    # Step 3: Aggregate
    print(f"\n📊 SCHRITT 3: Aggregiere {len(all_results):,} Picks …")
    agg = aggregate(all_results)

    # Step 4: Build report
    print("\n📝 SCHRITT 4: Erstelle HTML-Report …")
    html = build_html(agg, all_results)

    out_path = Path(__file__).parent / "backtest_v3_report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅ Report gespeichert: {out_path}")

    # Step 5: Print quick summary
    print("\n" + "─" * 50)
    overall_v2 = sum(r["correct_v2"] for r in all_results) / len(all_results) * 100
    overall_v3 = sum(r["correct_v3"] for r in all_results) / len(all_results) * 100
    print(f"  Picks gesamt:   {len(all_results):,}")
    print(f"  Hit-Rate v2:    {overall_v2:.1f}%")
    print(f"  Hit-Rate v3:    {overall_v3:.1f}%")
    print(f"  Delta:          {overall_v3-overall_v2:+.1f}pp")
    print(f"  MustWin-Spiele: {agg['mustwin_n']:,}")
    print(f"  Dead Rubbers:   {agg['deadrubber_n']:,}")
    print("─" * 50 + "\n")

    try:
        webbrowser.open(out_path.as_uri())
    except Exception:
        pass


if __name__ == "__main__":
    main()
