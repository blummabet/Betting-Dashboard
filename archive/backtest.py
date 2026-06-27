#!/usr/bin/env python3
"""
backtest.py — Betting Dashboard Historical Calibration v2
==========================================================
v2 upgrades vs. original:
  • Shots-based xG  (SoT × 0.35 + (Shots-SoT) × 0.055) — mirrors live refresh_stats.py
  • Clean-Sheet + Failed-to-Score rates — from FTHG/FTAG, venue-split, rolling
  • Over 2.5 Hard Gate  (expGoals < 2.5 → no pick) — mirrors live season-finish.html
  • Liga-specific Over/Under caps — mirrors live lgCap lookup table
  • Updated BTTS scoring with CS/FTS dampeners
  • Updated Under 2.5 scoring with CS boost
  • HTML report: v2 methodology notes + "what changed" section

RUN: python3 backtest.py
OUTPUT: backtest_report.html

Requires: pip install requests pandas
"""

import os, sys, json, math, time, webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

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
BASE_URL  = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
SEASONS   = ["2223", "2324", "2425"]

LEAGUES = {
    "ENG": {"code": "E0",  "name": "Premier League",      "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "GER": {"code": "D1",  "name": "Bundesliga",           "flag": "🇩🇪"},
    "ITA": {"code": "I1",  "name": "Serie A",              "flag": "🇮🇹"},
    "ESP": {"code": "SP1", "name": "La Liga",              "flag": "🇪🇸"},
    "FRA": {"code": "F1",  "name": "Ligue 1",              "flag": "🇫🇷"},
    "NED": {"code": "N1",  "name": "Eredivisie",           "flag": "🇳🇱"},
    "POR": {"code": "P1",  "name": "Primeira Liga",        "flag": "🇵🇹"},
    "SCO": {"code": "SC0", "name": "Scottish Prem",        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿"},
    "TUR": {"code": "T1",  "name": "Süper Lig",            "flag": "🇹🇷"},
    "BEL": {"code": "B1",  "name": "Belgian Pro League",   "flag": "🇧🇪"},
    "AUT": {"code": "A1",  "name": "Österreich BL",        "flag": "🇦🇹"},
}

# Minimum games before rolling stats are considered reliable
WARMUP_GAMES = 6

# ── Liga-specific Over/Under caps (mirrors live lgCap table) ─────────────────
# Positive = torreich, negative = defensiv
LG_CAPS = {
    "ENG": +0.05, "GER": +0.05, "ITA": -0.04, "FRA": -0.04,
    "ESP":  0.00, "NED": +0.03, "POR":  0.00, "SCO": +0.02,
    "TUR": +0.02, "BEL": +0.02, "AUT":  0.00,
}

# ─────────────────────────────────────────────────────────────────
#  STEP 1 — DOWNLOAD DATA
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
        # Parse shots columns (not always present)
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
#  STEP 2 — ROLLING STATS ENGINE
# ─────────────────────────────────────────────────────────────────
class TeamStats:
    """Maintains rolling stats for one team. v2: adds shots, CS, FTS tracking."""

    def __init__(self):
        self.results_home   = []
        self.results_away   = []
        self.goals_scored   = []
        self.goals_conceded = []
        self.all_results    = []
        # v2: shots on target (per game, home/away split)
        self.sot_home       = []   # SoT when playing at home
        self.sot_away       = []   # SoT when playing away
        self.shots_home     = []   # total shots at home
        self.shots_away     = []   # total shots away
        # v2: clean sheet / failed-to-score (bool per game)
        self.cs_home        = []   # clean sheet as home team
        self.cs_away        = []   # clean sheet as away team
        self.fts_home       = []   # failed to score at home
        self.fts_away       = []   # failed to score away

    # ── Existing helpers ──────────────────────────────────────────
    def home_win_rate(self, n=20) -> float:
        r = self.results_home[-n:]
        return r.count("W") / len(r) if r else 0.45

    def away_win_rate(self, n=20) -> float:
        r = self.results_away[-n:]
        return r.count("W") / len(r) if r else 0.30

    def form_score(self, n=6) -> float:
        r = self.all_results[-n:]
        if not r: return 0.5
        pts = sum(1.0 if x=="W" else 0.4 if x=="D" else 0.0 for x in r)
        return pts / len(r)

    def streak(self) -> int:
        if not self.all_results: return 0
        last = self.all_results[-1]
        if last == "D": return 0
        count = 0
        for r in reversed(self.all_results):
            if r == last: count += 1 if last=="W" else -1
            else: break
        return count

    def avg_goals_scored(self, n=10) -> float:
        g = self.goals_scored[-n:]
        return sum(g)/len(g) if g else 1.4

    def avg_goals_conceded(self, n=10) -> float:
        g = self.goals_conceded[-n:]
        return sum(g)/len(g) if g else 1.3

    def games_played(self) -> int:
        return len(self.all_results)

    # ── v2: Shots-based xG ───────────────────────────────────────
    # Mirrors live refresh_stats.py: SoT × 0.35 + (Shots - SoT) × 0.055
    def xg_home(self, n=10) -> Optional[float]:
        """xG when playing at home. Returns None if no shots data."""
        sot = self.sot_home[-n:]
        shots = self.shots_home[-n:]
        if not sot: return None
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 1.5
        return round(avg_sot * 0.35 + max(0, avg_shots - avg_sot) * 0.055, 3)

    def xg_away(self, n=10) -> Optional[float]:
        """xG when playing away."""
        sot = self.sot_away[-n:]
        shots = self.shots_away[-n:]
        if not sot: return None
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 1.5
        return round(avg_sot * 0.35 + max(0, avg_shots - avg_sot) * 0.055, 3)

    # ── v2: Clean Sheet + Failed-to-Score rates ───────────────────
    def clean_sheet_rate_home(self, n=15) -> float:
        cs = self.cs_home[-n:]
        return sum(cs)/len(cs) if cs else 0.25

    def clean_sheet_rate_away(self, n=15) -> float:
        cs = self.cs_away[-n:]
        return sum(cs)/len(cs) if cs else 0.25

    def failed_to_score_rate_home(self, n=15) -> float:
        fts = self.fts_home[-n:]
        return sum(fts)/len(fts) if fts else 0.20

    def failed_to_score_rate_away(self, n=15) -> float:
        fts = self.fts_away[-n:]
        return sum(fts)/len(fts) if fts else 0.20

    # ── Record helpers ────────────────────────────────────────────
    def record_home(self, scored, conceded, h_sot=None, h_shots=None):
        result = "W" if scored>conceded else "D" if scored==conceded else "L"
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
        result = "W" if scored>conceded else "D" if scored==conceded else "L"
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
        self._store = defaultdict(lambda: {"home_wins":0,"draws":0,"away_wins":0,"n":0})

    def _key(self, home, away):
        return tuple(sorted([home, away]))

    def record(self, home, away, result):
        k = self._key(home, away)
        d = self._store[k]
        d["n"] += 1
        if result=="H":
            if home<away: d["home_wins"] += 1
            else:         d["away_wins"] += 1
        elif result=="A":
            if home<away: d["away_wins"] += 1
            else:         d["home_wins"] += 1
        else:
            d["draws"] += 1

    def get(self, home, away) -> dict:
        k = self._key(home, away)
        d = self._store[k]
        n = d["n"]
        if n < 3:
            return {"home_win_rate":0.45,"draw_rate":0.25,"away_win_rate":0.30,"n":n}
        hw = d["home_wins"]/n if home<=away else d["away_wins"]/n
        aw = d["away_wins"]/n if home<=away else d["home_wins"]/n
        return {"home_win_rate":hw,"draw_rate":d["draws"]/n,"away_win_rate":aw,"n":n}


# ─────────────────────────────────────────────────────────────────
#  STEP 3 — SCORING ENGINE v2
# ─────────────────────────────────────────────────────────────────

def score_heimsieg(hFS_home, hStreak, homeWinRate, homeAttStr, awayDefStr,
                   homeInForm, awayInForm, homePoor) -> float:
    sc = 0.40 + (hFS_home - 0.5)*1.20 + max(0, hStreak)*0.09 + homeWinRate*0.35
    if homeInForm and not awayInForm: sc += 0.28
    if homePoor:    sc -= 0.48
    if awayInForm and not homeInForm: sc -= 0.20
    return sc

def score_auswärtssieg(aFS_away, aStreak, awayWinRate, awayAttStr, homeDefStr,
                       awayInForm, homeInForm, awayPoor) -> float:
    sc = 0.26 + (aFS_away - 0.5)*1.20 + max(0, aStreak)*0.09 + awayWinRate*0.35
    if awayInForm and not homeInForm: sc += 0.28
    if awayPoor:    sc -= 0.48
    if homeInForm and not awayInForm: sc -= 0.20
    return sc

def score_draw(drawRate, hFS_home, aFS_away) -> float:
    sc = drawRate*0.85 + (0.22 if drawRate > 0.36 else 0)
    if abs(hFS_home - aFS_away) < 0.10: sc += 0.12
    return sc

# v2: Hard Gate + liga cap
def score_over25(expGoals, homeAttStr, awayAttStr, lg_cap=0.0) -> Optional[float]:
    if expGoals < 2.50:   # ← HARD GATE (mirrors live season-finish.html)
        return None
    sc = (expGoals - 2.5)*0.55 + (homeAttStr - 1.2)*0.18 + (awayAttStr - 1.0)*0.18
    sc += lg_cap
    return max(0.0, min(sc, 0.92))

# v2: liga cap + CS boost
def score_under25(expGoals, homeAttStr, awayAttStr, lg_cap=0.0,
                  homeCSR=0.0, awayCSR=0.0) -> float:
    sc = (2.5 - expGoals)*0.55 + max(0, 1.2 - homeAttStr)*0.18 + max(0, 1.0 - awayAttStr)*0.18
    sc -= lg_cap   # inverse: torreich liga → fewer under picks
    # v2: clean sheet rate boosts under (defensive teams → fewer goals)
    if homeCSR > 0.40: sc += 0.08
    elif homeCSR > 0.30: sc += 0.04
    if awayCSR > 0.35: sc += 0.06
    elif awayCSR > 0.25: sc += 0.03
    return max(0.0, min(sc, 0.92))

# v2: CS + FTS dampeners on BTTS
def score_btts(homeAttStr, awayAttStr, homeDefStr, awayDefStr,
               homeCSR=0.0, awayCSR=0.0, homeFTSR=0.0, awayFTSR=0.0) -> float:
    # Base scoring (unchanged from v1)
    if homeAttStr>1.30 and awayAttStr>1.10 and homeDefStr>0.90 and awayDefStr>0.90:
        sc = 0.75
    elif homeAttStr>1.15 and awayAttStr>0.95 and homeDefStr>0.85 and awayDefStr>0.85:
        sc = 0.55
    else:
        sc = 0.20
    # v2: Clean sheet rate dampens BTTS (team keeps clean sheets → other team doesn't score)
    if homeCSR > 0.40: sc -= 0.18
    elif homeCSR > 0.30: sc -= 0.10
    if awayCSR > 0.35: sc -= 0.15
    elif awayCSR > 0.25: sc -= 0.08
    # v2: Failed-to-score dampens BTTS (team can't score → BTTS less likely)
    if homeFTSR > 0.30: sc -= 0.12
    if awayFTSR > 0.28: sc -= 0.10
    return max(0.05, min(sc, 0.92))

def conf_label(sc, thresholds):
    high_t, med_t = thresholds
    if sc >= high_t: return "high"
    if sc >= med_t:  return "medium"
    return "low"

# Thresholds — calibrated from v1, will be re-evaluated from v2 results
THRESHOLDS = {
    "heimsieg":     (1.20, 0.68),
    "auswärtssieg": (1.08, 0.62),
    "draw":         (0.70, 0.45),
    "over25":       (0.50, 0.20),
    "under25":      (0.45, 0.18),
    "btts":         (0.70, 0.45),
}


def simulate_picks(row, home_stats: TeamStats, away_stats: TeamStats,
                   h2h: dict, league_key: str) -> list:
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

    # v2: Shots-based xG when available, fall back to goals proxy
    h_xg = home_stats.xg_home()    # None if no shot data
    a_xg = away_stats.xg_away()
    if h_xg is not None and a_xg is not None:
        expGoals = h_xg + a_xg      # shots-based total xG
        xg_source = "shots"
    else:
        expGoals = (hAtt + aDef + aAtt + hDef) / 2   # v1 proxy
        xg_source = "goals"

    # v2: CS / FTS rates
    homeCSR  = home_stats.clean_sheet_rate_home()
    awayCSR  = away_stats.clean_sheet_rate_away()
    homeFTSR = home_stats.failed_to_score_rate_home()
    awayFTSR = away_stats.failed_to_score_rate_away()

    # Liga cap
    lg_cap = LG_CAPS.get(league_key, 0.0)

    hFS_home = min(0.93, hHWR*0.55 + hFS*0.45)
    aFS_away = max(0.07, aAWR*0.55 + aFS*0.45)
    homeInForm = hStr >= 2 and hFS_home > 0.62
    awayInForm = aStr >= 2 and aFS_away > 0.56
    homePoor   = hStr <= -3 or hFS_home < 0.25
    awayPoor   = aStr <= -3 or aFS_away < 0.22

    hwRate = h2h["home_win_rate"]
    drRate = h2h["draw_rate"]
    awRate = h2h["away_win_rate"]

    picks = []

    # ── Result market ──────────────────────────────────────────────
    sc_h = score_heimsieg(hFS_home, hStr, hwRate, hAtt, aDef, homeInForm, awayInForm, homePoor)
    sc_a = score_auswärtssieg(aFS_away, aStr, awRate, aAtt, hDef, awayInForm, homeInForm, awayPoor)
    sc_d = score_draw(drRate, hFS_home, aFS_away)
    best_result = max([(sc_h,"heimsieg"),(sc_a,"auswärtssieg"),(sc_d,"draw")], key=lambda x: x[0])
    sc_r, mkt_r = best_result
    picks.append({"market": mkt_r, "sc": sc_r, "conf": conf_label(sc_r, THRESHOLDS[mkt_r]),
                  "xg_source": xg_source})

    # ── Goals market — v2: Hard Gate + liga cap ────────────────────
    sc_ov = score_over25(expGoals, hAtt, aAtt, lg_cap)  # None if Hard Gate triggered
    sc_un = score_under25(expGoals, hAtt, aAtt, lg_cap, homeCSR, awayCSR)

    if sc_ov is None:
        # Hard Gate: only under25 available
        picks.append({"market": "under25", "sc": sc_un, "conf": conf_label(sc_un, THRESHOLDS["under25"]),
                      "xg_source": xg_source, "hard_gated": True})
    elif sc_ov >= sc_un:
        picks.append({"market": "over25", "sc": sc_ov, "conf": conf_label(sc_ov, THRESHOLDS["over25"]),
                      "xg_source": xg_source, "hard_gated": False})
    else:
        picks.append({"market": "under25", "sc": sc_un, "conf": conf_label(sc_un, THRESHOLDS["under25"]),
                      "xg_source": xg_source, "hard_gated": False})

    # ── BTTS market — v2: CS/FTS dampeners ────────────────────────
    sc_bt = score_btts(hAtt, aAtt, hDef, aDef, homeCSR, awayCSR, homeFTSR, awayFTSR)
    picks.append({"market": "btts", "sc": sc_bt, "conf": conf_label(sc_bt, THRESHOLDS["btts"]),
                  "xg_source": xg_source})

    return picks


def evaluate_pick(market: str, home_goals: int, away_goals: int) -> bool:
    total = home_goals + away_goals
    if market == "heimsieg":     return home_goals > away_goals
    if market == "auswärtssieg": return away_goals > home_goals
    if market == "draw":         return home_goals == away_goals
    if market == "over25":       return total > 2.5
    if market == "under25":      return total < 2.5
    if market == "btts":         return home_goals > 0 and away_goals > 0
    return False


# ─────────────────────────────────────────────────────────────────
#  STEP 4 — ODDS EXTRACTION
# ─────────────────────────────────────────────────────────────────
def extract_odds(row: pd.Series, market: str) -> Optional[float]:
    candidates = {
        "heimsieg":     ["PSH",  "B365H", "BbAvH", "MaxH"],
        "auswärtssieg": ["PSA",  "B365A", "BbAvA", "MaxA"],
        "draw":         ["PSD",  "B365D", "BbAvD", "MaxD"],
        "over25":       ["PSC>2.5","B365>2.5","BbAv>2.5","Max>2.5","B365.1"],
        "under25":      ["PSC<2.5","B365<2.5","BbAv<2.5","Max<2.5","B365.2"],
        "btts":         [],
    }
    for col in candidates.get(market, []):
        if col in row.index:
            val = pd.to_numeric(row[col], errors="coerce")
            if pd.notna(val) and 1.05 <= val <= 25.0:
                return float(val)
    return None


# ─────────────────────────────────────────────────────────────────
#  STEP 5 — PROCESS ONE LEAGUE
# ─────────────────────────────────────────────────────────────────
def process_league(key: str, df: pd.DataFrame) -> list:
    results = []
    team_stats  = defaultdict(TeamStats)
    h2h_tracker = H2HTracker()

    has_shots = {"HST", "AST"}.issubset(df.columns)
    has_total_shots = {"HS", "AS"}.issubset(df.columns)
    shots_used = 0
    goals_used = 0

    for _, row in df.iterrows():
        home   = str(row["HomeTeam"]).strip()
        away   = str(row["AwayTeam"]).strip()
        hg     = int(row["FTHG"])
        ag     = int(row["FTAG"])
        ftr    = str(row["FTR"]).strip()
        season = row.get("_season", "")

        hs  = team_stats[f"{season}:{home}"]
        as_ = team_stats[f"{season}:{away}"]
        h2h = h2h_tracker.get(home, away)

        if hs.games_played() >= WARMUP_GAMES and as_.games_played() >= WARMUP_GAMES:
            picks = simulate_picks(row, hs, as_, h2h, key)
            for p in picks:
                correct = evaluate_pick(p["market"], hg, ag)
                odds    = extract_odds(row, p["market"])
                roi_contrib = ((odds - 1) if correct else -1.0) if odds is not None else None
                if p.get("xg_source") == "shots": shots_used += 1
                else: goals_used += 1
                results.append({
                    "league":     key,
                    "season":     season,
                    "market":     p["market"],
                    "conf":       p["conf"],
                    "sc":         round(p["sc"], 3),
                    "correct":    correct,
                    "odds":       odds,
                    "roi":        roi_contrib,
                    "xg_source":  p.get("xg_source", "goals"),
                    "hard_gated": p.get("hard_gated", False),
                })

        # v2: extract shots before updating stats
        h_sot  = float(row["HST"]) if has_shots and pd.notna(row.get("HST")) else None
        a_sot  = float(row["AST"]) if has_shots and pd.notna(row.get("AST")) else None
        h_shts = float(row["HS"])  if has_total_shots and pd.notna(row.get("HS")) else None
        a_shts = float(row["AS"])  if has_total_shots and pd.notna(row.get("AS")) else None

        hs.record_home(hg, ag, h_sot, h_shts)
        as_.record_away(ag, hg, a_sot, a_shts)
        h2h_tracker.record(home, away, ftr)

    return results


# ─────────────────────────────────────────────────────────────────
#  STEP 6 — AGGREGATE
# ─────────────────────────────────────────────────────────────────
def aggregate(all_results: list) -> dict:
    by_mc  = defaultdict(lambda: {"n":0,"hits":0,"roi_sum":0,"roi_n":0})
    by_lg  = defaultdict(lambda: {"n":0,"hits":0,"roi_sum":0,"roi_n":0})
    by_mkt = defaultdict(lambda: {"n":0,"hits":0,"roi_sum":0,"roi_n":0})
    shots_n, goals_n, gated_n = 0, 0, 0

    for r in all_results:
        mc  = (r["market"], r["conf"])
        for bucket in [by_mc[mc], by_lg[r["league"]], by_mkt[r["market"]]]:
            bucket["n"]    += 1
            bucket["hits"] += int(r["correct"])
            if r["roi"] is not None:
                bucket["roi_sum"] += r["roi"]
                bucket["roi_n"]   += 1
        if r.get("xg_source") == "shots": shots_n += 1
        else: goals_n += 1
        if r.get("hard_gated"): gated_n += 1

    def finalise(d):
        out = {}
        for k, v in d.items():
            hr  = v["hits"]/v["n"]*100 if v["n"] else 0
            roi = v["roi_sum"]/v["roi_n"]*100 if v["roi_n"] else None
            out[k] = {"n":v["n"],"hits":v["hits"],"hit_rate":round(hr,1),
                      "roi":round(roi,1) if roi is not None else None,
                      "roi_n":v["roi_n"]}
        return out

    return {
        "by_market_conf": finalise(by_mc),
        "by_league":      finalise(by_lg),
        "by_market":      finalise(by_mkt),
        "total":          len(all_results),
        "shots_n":        shots_n,
        "goals_n":        goals_n,
        "hard_gated_n":   gated_n,
    }


# ─────────────────────────────────────────────────────────────────
#  STEP 7 — HTML REPORT v2
# ─────────────────────────────────────────────────────────────────
MARKET_LABELS = {
    "heimsieg":     "🏠 Heimsieg",
    "auswärtssieg": "✈️ Auswärtssieg",
    "draw":         "🤝 Unentschieden",
    "over25":       "⚽ Über 2.5 Tore",
    "under25":      "🔒 Unter 2.5 Tore",
    "btts":         "🎯 Beide treffen",
}
CONF_LABELS = {"high":"★★★ Hoch","medium":"★★☆ Mittel","low":"★☆☆ Niedrig"}
LEAGUE_META = {k: v for k, v in LEAGUES.items()}

def roi_color(roi):
    if roi is None: return "#888"
    if roi >= 5:    return "#22c55e"
    if roi >= 0:    return "#a3e635"
    if roi >= -5:   return "#fb923c"
    return "#f85149"

def hitrate_color(hr):
    if hr >= 65: return "#22c55e"
    if hr >= 50: return "#a3e635"
    if hr >= 40: return "#fb923c"
    return "#f85149"

def fmt_roi(roi):
    if roi is None: return "–"
    return f"{'+'if roi>=0 else ''}{roi:.1f}%"

def fmt_hr(hr):
    return f"{hr:.1f}%"


def build_html_report(agg: dict) -> str:
    now   = datetime.now().strftime("%d.%m.%Y %H:%M")
    total = agg["total"]
    bmc   = agg["by_market_conf"]
    blg   = agg["by_league"]
    bmkt  = agg["by_market"]
    shots_pct = round(agg["shots_n"] / total * 100) if total else 0
    gated_n   = agg.get("hard_gated_n", 0)

    markets_order = ["heimsieg","auswärtssieg","draw","over25","under25","btts"]
    confs_order   = ["high","medium","low"]

    def mc_row(mkt, conf):
        key = (mkt, conf)
        d   = bmc.get(key, {"n":0,"hit_rate":0,"roi":None,"roi_n":0})
        if d["n"] < 10:
            return f"<tr><td>{MARKET_LABELS.get(mkt,mkt)}</td><td>{CONF_LABELS.get(conf,conf)}</td><td style='color:#555'>{d['n']}</td><td colspan='2' style='color:#555;font-style:italic'>zu wenig Daten</td></tr>"
        hr_col  = hitrate_color(d["hit_rate"])
        roi_col = roi_color(d["roi"])
        implied = {"high":75,"medium":60,"low":50}.get(conf, 55)
        diff    = d["hit_rate"] - implied
        diff_str = f"{'+'if diff>=0 else ''}{diff:.1f}pp vs. impliziert {implied}%"
        return f"""<tr>
          <td>{MARKET_LABELS.get(mkt,mkt)}</td>
          <td>{CONF_LABELS.get(conf,conf)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_col};font-weight:700">{fmt_hr(d['hit_rate'])}
              <span style="font-size:10px;color:#888;margin-left:4px">{diff_str}</span></td>
          <td style="color:{roi_col};font-weight:700">{fmt_roi(d['roi'])}
              <span style="font-size:10px;color:#888;margin-left:4px">(n={d['roi_n']:,})</span></td>
        </tr>"""

    cal_rows = "".join(mc_row(m,c) for m in markets_order for c in confs_order)

    def lg_row(key):
        meta = LEAGUE_META.get(key, {"name":key,"flag":""})
        d    = blg.get(key, {"n":0,"hit_rate":0,"roi":None})
        if d["n"] == 0: return ""
        return f"<tr><td>{meta.get('flag','')} {meta.get('name',key)}</td><td>{d['n']:,}</td><td style='color:{hitrate_color(d['hit_rate'])};font-weight:700'>{fmt_hr(d['hit_rate'])}</td><td style='color:{roi_color(d['roi'])};font-weight:700'>{fmt_roi(d['roi'])}</td></tr>"

    lg_rows  = "".join(lg_row(k) for k in sorted(blg.keys()))

    def mkt_row(mkt):
        d = bmkt.get(mkt, {"n":0,"hit_rate":0,"roi":None})
        if d["n"] == 0: return ""
        return f"<tr><td>{MARKET_LABELS.get(mkt,mkt)}</td><td>{d['n']:,}</td><td style='color:{hitrate_color(d['hit_rate'])};font-weight:700'>{fmt_hr(d['hit_rate'])}</td><td style='color:{roi_color(d['roi'])};font-weight:700'>{fmt_roi(d['roi'])}</td></tr>"

    mkt_rows = "".join(mkt_row(m) for m in markets_order)

    # Auto findings
    findings = []
    good = [(k,v) for k,v in bmc.items() if v["n"]>=50 and v["hit_rate"]>=60]
    bad  = [(k,v) for k,v in bmc.items() if v["n"]>=50 and v["hit_rate"]<45]
    good.sort(key=lambda x: x[1]["hit_rate"], reverse=True)
    bad.sort(key=lambda x: x[1]["hit_rate"])
    for (mkt,conf),v in good[:3]:
        findings.append(f"✅ <strong>{MARKET_LABELS.get(mkt,mkt)} ({CONF_LABELS.get(conf,conf)})</strong>: {v['hit_rate']:.1f}% Trefferquote bei {v['n']:,} Picks — gut kalibriert.")
    for (mkt,conf),v in bad[:3]:
        findings.append(f"⚠️ <strong>{MARKET_LABELS.get(mkt,mkt)} ({CONF_LABELS.get(conf,conf)})</strong>: nur {v['hit_rate']:.1f}% bei {v['n']:,} Picks — Schwachpunkt.")
    high_hits = sum(v["hits"] for k,v in bmc.items() if k[1]=="high"  and v["n"]>=20)
    high_n    = sum(v["n"]    for k,v in bmc.items() if k[1]=="high"  and v["n"]>=20)
    med_hits  = sum(v["hits"] for k,v in bmc.items() if k[1]=="medium" and v["n"]>=20)
    med_n     = sum(v["n"]    for k,v in bmc.items() if k[1]=="medium" and v["n"]>=20)
    if high_n and med_n:
        high_hr = high_hits/high_n*100
        med_hr  = med_hits/med_n*100
        if high_hr > med_hr + 5:
            findings.append(f"📈 <strong>★★★ schlägt ★★☆</strong> deutlich: {high_hr:.1f}% vs {med_hr:.1f}% — Kalibrierung wirkt.")
        elif abs(high_hr - med_hr) < 3:
            findings.append(f"⚠️ <strong>★★★ und ★★☆ performen fast gleich</strong> ({high_hr:.1f}% vs {med_hr:.1f}%) — High-Threshold weiter erhöhen.")

    # Hard Gate finding
    if gated_n > 0:
        findings.append(f"🛑 <strong>Over 2.5 Hard Gate</strong> hat {gated_n:,} Picks blockiert (expGoals &lt; 2.5) — diese Picks wurden als Under/kein-Tore umgeleitet. Korrekte Unterdrückung.")

    findings_html = "".join(f"<li style='margin-bottom:8px'>{f}</li>" for f in findings)

    # Threshold recommendation section
    threshold_rows = ""
    for mkt in markets_order:
        for conf in ["high", "medium"]:
            key = (mkt, conf)
            d   = bmc.get(key, {"n": 0, "hit_rate": 0})
            if d["n"] < 30: continue
            current_h, current_m = THRESHOLDS.get(mkt, (0.5, 0.2))
            current_t = current_h if conf == "high" else current_m
            hr = d["hit_rate"]
            # Recommendation: if HR too low → raise threshold; if HR very high with few picks → lower
            if conf == "high" and hr < 60 and d["n"] > 50:
                rec = f"⬆️ Threshold erhöhen (nur {hr:.0f}% Trefferquote)"
                rec_color = "#fb923c"
            elif conf == "high" and hr >= 68:
                rec = f"✅ Gut kalibriert ({hr:.0f}%)"
                rec_color = "#22c55e"
            elif conf == "medium" and hr < 48 and d["n"] > 100:
                rec = f"⬆️ Threshold erhöhen ({hr:.0f}% ≈ Zufall)"
                rec_color = "#f85149"
            elif conf == "medium" and hr >= 55:
                rec = f"✅ Gut kalibriert ({hr:.0f}%)"
                rec_color = "#22c55e"
            else:
                rec = f"➡️ Beobachten ({hr:.0f}%)"
                rec_color = "#888"
            threshold_rows += f"<tr><td>{MARKET_LABELS.get(mkt,mkt)}</td><td>{CONF_LABELS.get(conf,conf)}</td><td>{d['n']:,}</td><td style='color:{hitrate_color(hr)};font-weight:700'>{hr:.1f}%</td><td style='color:{rec_color}'>{rec}</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Backtest Report v2 — Betting Dashboard</title>
<style>
  * {{ box-sizing:border-box;margin:0;padding:0 }}
  body {{ background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:30px;max-width:1100px;margin:0 auto }}
  h1 {{ font-size:24px;font-weight:800;margin-bottom:4px }}
  h2 {{ font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#58a6ff;margin:28px 0 12px }}
  .meta {{ color:#888;font-size:13px;margin-bottom:20px }}
  .grid {{ display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px }}
  .card {{ background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px }}
  .stat-val {{ font-size:28px;font-weight:800;color:#58a6ff }}
  .stat-lbl {{ font-size:11px;color:#888;margin-top:2px }}
  .v2-badge {{ display:inline-block;background:rgba(56,139,253,.15);border:1px solid rgba(56,139,253,.4);color:#58a6ff;font-size:10px;font-weight:700;padding:1px 7px;border-radius:5px;margin-left:5px;vertical-align:middle }}
  table {{ width:100%;border-collapse:collapse;font-size:13px }}
  th {{ background:#21262d;color:#888;font-weight:600;padding:8px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.4px }}
  td {{ padding:9px 12px;border-bottom:1px solid #21262d }}
  tr:hover td {{ background:#161b22 }}
  .findings {{ background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 20px;list-style:none;font-size:13px;line-height:1.6 }}
  .section {{ background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin-bottom:20px;overflow-x:auto }}
  .note {{ background:#1c2128;border:1px solid #388bfd40;border-radius:8px;padding:14px 18px;font-size:12px;color:#8b949e;margin-top:20px;line-height:1.7 }}
  .changes {{ background:#162032;border:1px solid rgba(56,139,253,.3);border-radius:10px;padding:16px 20px;margin-bottom:24px;font-size:13px;line-height:1.7 }}
  .changes li {{ margin-bottom:5px }}
</style>
</head>
<body>
<h1>📊 Backtest Report <span class="v2-badge">v2</span></h1>
<div class="meta">Generiert: {now} · Datenbasis: football-data.co.uk · Saisons: {', '.join(SEASONS)}</div>

<div class="changes">
  <strong style="color:#58a6ff">🆕 v2 Upgrades gegenüber v1:</strong>
  <ul style="margin-top:8px;padding-left:18px">
    <li><strong>Shots-based xG</strong> — SoT × 0.35 + (Shots−SoT) × 0.055 (statt Tore/Spiel) · {shots_pct}% der Picks mit echten Schuss-Daten berechnet</li>
    <li><strong>Over 2.5 Hard Gate</strong> — expGoals &lt; 2.5 → kein Over-Pick · {gated_n:,} Picks blockiert und umgeleitet</li>
    <li><strong>Clean-Sheet- + Failed-to-Score-Rates</strong> — venue-split, rolling 15 Spiele · wirken auf Under 2.5 und BTTS</li>
    <li><strong>Liga-spezifische Caps</strong> — ENG/GER +0.05, ITA/FRA −0.04 etc. auf Over/Under-Score angewendet</li>
  </ul>
</div>

<div class="grid">
  <div class="card"><div class="stat-val">{total:,}</div><div class="stat-lbl">Picks total</div></div>
  <div class="card"><div class="stat-val">{len(blg)}</div><div class="stat-lbl">Ligen</div></div>
  <div class="card"><div class="stat-val">{shots_pct}%</div><div class="stat-lbl">Picks mit Shots-xG</div></div>
  <div class="card"><div class="stat-val">{gated_n:,}</div><div class="stat-lbl">Hard-Gate-Blocks</div></div>
</div>

<h2>🔍 Wichtigste Erkenntnisse</h2>
<ul class="findings">{findings_html}</ul>

<h2>🎯 Kalibrierung: Trefferquote &amp; ROI nach Markt + Konfidenz</h2>
<div class="section">
  <table>
    <tr><th>Markt</th><th>Konfidenz</th><th>Picks</th><th>Trefferquote</th><th>ROI (flat stake)</th></tr>
    {cal_rows}
  </table>
</div>

<h2>🔧 Threshold-Empfehlungen (basierend auf v2-Ergebnissen)</h2>
<div class="section">
  <table>
    <tr><th>Markt</th><th>Konfidenz</th><th>Picks</th><th>Trefferquote</th><th>Empfehlung</th></tr>
    {threshold_rows}
  </table>
</div>

<h2>⚽ Übersicht nach Markt</h2>
<div class="section">
  <table>
    <tr><th>Markt</th><th>Picks</th><th>Trefferquote</th><th>ROI</th></tr>
    {mkt_rows}
  </table>
</div>

<h2>🌍 Übersicht nach Liga</h2>
<div class="section">
  <table>
    <tr><th>Liga</th><th>Picks</th><th>Trefferquote</th><th>ROI</th></tr>
    {lg_rows}
  </table>
</div>

<div class="note">
  <strong>Methodik v2:</strong> Warmup {WARMUP_GAMES} Spiele pro Team (kein Look-Ahead) · Rolling: Form 6 Spiele, Tore/Shots 10 Spiele, CS/FTS 15 Spiele · xG = SoT×0.35+(Shots−SoT)×0.055 wenn verfügbar, sonst (hAtt+aDef+aAtt+hDef)/2 · Over 2.5 Hard Gate: expGoals &lt; 2.5 → kein Pick · Liga-Caps: ENG/GER +0.05, ITA/FRA −0.04, NED/SCO/TUR/BEL +0.02–0.03 · Nicht enthalten: Saisondruck, Motivation, Schiedsrichter, Formation — diese testen wir live über den Results-Tab.
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Betting Dashboard — Backtest Engine v2")
    print(f"  Saisons: {', '.join(SEASONS)}")
    print(f"  Ligen:   {', '.join(LEAGUES.keys())}")
    print("  Neu: Shots-xG · CS/FTS-Rates · Hard Gate · Liga-Caps")
    print("=" * 60)

    print("\n📥  Lade historische Daten...")
    all_data = load_all_data()
    if not all_data:
        print("❌  Keine Daten geladen.")
        return

    print("⚙️   Simuliere Picks (v2)...")
    all_results = []
    for key, df in all_data.items():
        meta = LEAGUES[key]
        print(f"  {meta['flag']} {meta['name']}: {len(df)} Spiele → ", end="", flush=True)
        t0  = time.time()
        res = process_league(key, df)
        all_results.extend(res)
        shots_pct = round(sum(1 for r in res if r["xg_source"]=="shots")/len(res)*100) if res else 0
        gated = sum(1 for r in res if r.get("hard_gated"))
        print(f"{len(res)} Picks · {shots_pct}% shots-xG · {gated} gated ({time.time()-t0:.1f}s)")

    print(f"\n  📊 Total: {len(all_results):,} Picks über alle Ligen")

    print("\n📈  Aggregiere...")
    agg = aggregate(all_results)

    print("\n" + "=" * 60)
    print("  TREFFERQUOTE nach Konfidenz (v2)")
    print("=" * 60)
    for conf in ["high","medium","low"]:
        total_c = sum(v["n"]    for k,v in agg["by_market_conf"].items() if k[1]==conf)
        hits_c  = sum(v["hits"] for k,v in agg["by_market_conf"].items() if k[1]==conf)
        if total_c:
            print(f"  {CONF_LABELS[conf]:20} {hits_c/total_c*100:.1f}%  ({hits_c:,}/{total_c:,})")
    print()
    print("  TREFFERQUOTE nach Markt:")
    for mkt in ["heimsieg","auswärtssieg","draw","over25","under25","btts"]:
        d = agg["by_market"].get(mkt, {"n":0,"hit_rate":0})
        if d["n"]:
            print(f"  {MARKET_LABELS.get(mkt,''):25} {d['hit_rate']:.1f}%  ({d['n']:,})")
    print(f"\n  Hard Gate Blocks: {agg['hard_gated_n']:,}")
    print(f"  Shots-xG used:    {agg['shots_n']:,} ({round(agg['shots_n']/agg['total']*100)}%)")

    out_path = Path(__file__).parent / "backtest_report.html"
    html = build_html_report(agg)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅  Report: {out_path}")
    webbrowser.open(str(out_path))


if __name__ == "__main__":
    main()
