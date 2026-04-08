#!/usr/bin/env python3
"""
backtest.py — Betting Dashboard Historical Calibration
======================================================
Downloads 3 seasons of match data from football-data.co.uk,
simulates our getBettingPicks scoring logic, and measures
how well each confidence level (★★★ / ★★☆ / ★☆☆) actually
predicts the outcome.

RUN: python3 backtest.py
OUTPUT: backtest_report.html  (opens automatically in browser)

Requires: pip install requests pandas
"""

import os, sys, json, math, time, webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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
SEASONS   = ["2223", "2324", "2425"]   # 3 seasons = ~10 000 matches

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
    "GRE": {"code": "G1",  "name": "Super League Greece",  "flag": "🇬🇷"},
    "AUT": {"code": "A1",  "name": "Österreich BL",        "flag": "🇦🇹"},
}

# Minimum games before rolling stats are considered reliable
WARMUP_GAMES = 6

# ─────────────────────────────────────────────────────────────────
#  STEP 1 — DOWNLOAD DATA
# ─────────────────────────────────────────────────────────────────
def fetch_csv(season: str, code: str) -> pd.DataFrame | None:
    url = BASE_URL.format(season=season, code=code)
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or len(r.text.strip()) < 100:
            return None
        from io import StringIO
        df = pd.read_csv(StringIO(r.text), encoding="utf-8", on_bad_lines="skip")
        # Minimal required columns
        if not {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}.issubset(df.columns):
            return None
        df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"])
        df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
        df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
        df = df.dropna(subset=["FTHG", "FTAG"])
        # Parse date
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            df = df.sort_values("Date")
        print(f"    ✅ {season} {code}: {len(df)} Spiele")
        return df
    except Exception as e:
        print(f"    ❌ {season} {code}: {e}")
        return None


def load_all_data() -> dict:
    """Returns {league_key: [df_season1, df_season2, ...]}"""
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
    """Maintains rolling stats for one team across the season."""

    def __init__(self):
        self.results_home  = []   # list of 'W'/'D'/'L' at home
        self.results_away  = []   # list of 'W'/'D'/'L' away
        self.goals_scored  = []   # all goals scored
        self.goals_conceded= []   # all goals conceded
        self.all_results   = []   # overall last-N results (chronological)

    def home_win_rate(self, n=20) -> float:
        r = self.results_home[-n:]
        if not r: return 0.45
        return r.count("W") / len(r)

    def away_win_rate(self, n=20) -> float:
        r = self.results_away[-n:]
        if not r: return 0.30
        return r.count("W") / len(r)

    def form_score(self, n=6) -> float:
        """0–1 form score over last n games (W=1, D=0.4, L=0)."""
        r = self.all_results[-n:]
        if not r: return 0.5
        pts = sum(1.0 if x == "W" else 0.4 if x == "D" else 0.0 for x in r)
        return pts / len(r)

    def streak(self) -> int:
        """Positive = consecutive wins, negative = consecutive losses."""
        if not self.all_results: return 0
        last = self.all_results[-1]
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

    def record_home(self, scored, conceded):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_home.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)

    def record_away(self, scored, conceded):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_away.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)


class H2HTracker:
    """Tracks head-to-head history for team pairs."""

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
            else: d["away_wins"] += 1
        elif result == "A":
            if home < away: d["away_wins"] += 1
            else: d["home_wins"] += 1
        else:
            d["draws"] += 1

    def get(self, home, away) -> dict:
        k = self._key(home, away)
        d = self._store[k]
        n = d["n"]
        if n < 3:
            return {"home_win_rate": 0.45, "draw_rate": 0.25, "away_win_rate": 0.30, "n": n}
        # Orient relative to current home/away
        if home <= away:
            hw = d["home_wins"] / n
            aw = d["away_wins"] / n
        else:
            hw = d["away_wins"] / n
            aw = d["home_wins"] / n
        return {"home_win_rate": hw, "draw_rate": d["draws"] / n, "away_win_rate": aw, "n": n}


# ─────────────────────────────────────────────────────────────────
#  STEP 3 — SCORING ENGINE (mirrors getBettingPicks JS logic)
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

def score_over25(expGoals, homeAttStr, awayAttStr) -> float:
    sc = (expGoals - 2.5) * 0.55 + (homeAttStr - 1.2) * 0.18 + (awayAttStr - 1.0) * 0.18
    return sc

def score_under25(expGoals, homeAttStr, awayAttStr) -> float:
    sc = (2.5 - expGoals) * 0.55 + max(0, 1.2 - homeAttStr) * 0.18 + max(0, 1.0 - awayAttStr) * 0.18
    return sc

def score_btts(homeAttStr, awayAttStr, homeDefStr, awayDefStr) -> float:
    if homeAttStr > 1.30 and awayAttStr > 1.10 and homeDefStr > 0.90 and awayDefStr > 0.90:
        return 0.75
    if homeAttStr > 1.15 and awayAttStr > 0.95 and homeDefStr > 0.85 and awayDefStr > 0.85:
        return 0.55
    return 0.20

def conf_label(sc, thresholds):
    high_t, med_t = thresholds
    if sc >= high_t: return "high"
    if sc >= med_t:  return "medium"
    return "low"

# Thresholds after our recent calibration (raised from original)
THRESHOLDS = {
    "heimsieg":    (1.20, 0.68),
    "auswärtssieg":(1.08, 0.62),
    "draw":        (0.70, 0.45),
    "over25":      (0.50, 0.20),
    "under25":     (0.45, 0.18),
    "btts":        (0.70, 0.45),
}


def simulate_picks(row, home_stats: TeamStats, away_stats: TeamStats, h2h: dict) -> list:
    """
    Given pre-match rolling stats, generate picks with conf labels.
    Returns list of {market, conf, sc, correct (filled later)}.
    """
    hFS    = home_stats.form_score()
    aFS    = away_stats.form_score()
    hStr   = home_stats.streak()
    aStr   = away_stats.streak()
    hHWR   = home_stats.home_win_rate()
    aAWR   = away_stats.away_win_rate()
    hAtt   = home_stats.avg_goals_scored()
    aAtt   = away_stats.avg_goals_scored()
    hDef   = home_stats.avg_goals_conceded()   # how many home concedes avg
    aDef   = away_stats.avg_goals_conceded()   # how many away concedes avg

    # Venue-adjusted form (mirrors JS hFS_home / aFS_away)
    hFS_home = min(0.93, hHWR * 0.55 + hFS * 0.45)
    aFS_away = max(0.07, aAWR * 0.55 + aFS * 0.45)

    homeInForm = hStr >= 2 and hFS_home > 0.62
    awayInForm = aStr >= 2 and aFS_away > 0.56
    homePoor   = hStr <= -3 or hFS_home < 0.25
    awayPoor   = aStr <= -3 or aFS_away < 0.22

    hwRate = h2h["home_win_rate"]
    drRate = h2h["draw_rate"]
    awRate = h2h["away_win_rate"]

    expGoals = (hAtt + aDef + aAtt + hDef) / 2

    picks = []

    # ── Result market ──
    sc_h = score_heimsieg(hFS_home, hStr, hwRate, hAtt, aDef, homeInForm, awayInForm, homePoor)
    sc_a = score_auswärtssieg(aFS_away, aStr, awRate, aAtt, hDef, awayInForm, homeInForm, awayPoor)
    sc_d = score_draw(drRate, hFS_home, aFS_away)
    best_result = max([(sc_h, "heimsieg"), (sc_a, "auswärtssieg"), (sc_d, "draw")], key=lambda x: x[0])
    sc_r, mkt_r = best_result
    picks.append({"market": mkt_r, "sc": sc_r, "conf": conf_label(sc_r, THRESHOLDS[mkt_r])})

    # ── Goals market ──
    sc_ov = score_over25(expGoals, hAtt, aAtt)
    sc_un = score_under25(expGoals, hAtt, aAtt)
    if sc_ov >= sc_un:
        picks.append({"market": "over25", "sc": sc_ov, "conf": conf_label(sc_ov, THRESHOLDS["over25"])})
    else:
        picks.append({"market": "under25", "sc": sc_un, "conf": conf_label(sc_un, THRESHOLDS["under25"])})

    # ── BTTS market ──
    sc_bt = score_btts(hAtt, aAtt, hDef, aDef)
    picks.append({"market": "btts", "sc": sc_bt, "conf": conf_label(sc_bt, THRESHOLDS["btts"])})

    return picks


def evaluate_pick(market: str, home_goals: int, away_goals: int) -> bool:
    total = home_goals + away_goals
    if market == "heimsieg":    return home_goals > away_goals
    if market == "auswärtssieg":return away_goals > home_goals
    if market == "draw":        return home_goals == away_goals
    if market == "over25":      return total > 2.5
    if market == "under25":     return total < 2.5
    if market == "btts":        return home_goals > 0 and away_goals > 0
    return False


# ─────────────────────────────────────────────────────────────────
#  STEP 4 — ODDS EXTRACTION (for ROI calculation)
# ─────────────────────────────────────────────────────────────────
def extract_odds(row: pd.Series, market: str) -> float | None:
    """Try to extract bookmaker odds for the given market."""
    # Pinnacle preferred (PSH/PSD/PSA), fallback Bet365, then BbAv
    candidates = {
        "heimsieg":    ["PSH",  "B365H", "BbAvH", "MaxH"],
        "auswärtssieg":["PSA",  "B365A", "BbAvA", "MaxA"],
        "draw":        ["PSD",  "B365D", "BbAvD", "MaxD"],
        "over25":      ["PSC>2.5","B365>2.5","BbAv>2.5","Max>2.5","B365.1"],
        "under25":     ["PSC<2.5","B365<2.5","BbAv<2.5","Max<2.5","B365.2"],
        "btts":        [],  # rarely in CSVs
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
    """Returns list of pick results for all evaluated matches."""
    results = []
    team_stats    = defaultdict(TeamStats)
    h2h_tracker   = H2HTracker()

    for _, row in df.iterrows():
        home = str(row["HomeTeam"]).strip()
        away = str(row["AwayTeam"]).strip()
        hg   = int(row["FTHG"])
        ag   = int(row["FTAG"])
        ftr  = str(row["FTR"]).strip()   # H / D / A
        season = row.get("_season", "")

        hs = team_stats[f"{season}:{home}"]
        as_ = team_stats[f"{season}:{away}"]
        h2h = h2h_tracker.get(home, away)

        # Only evaluate after warmup
        if hs.games_played() >= WARMUP_GAMES and as_.games_played() >= WARMUP_GAMES:
            picks = simulate_picks(row, hs, as_, h2h)
            for p in picks:
                correct = evaluate_pick(p["market"], hg, ag)
                odds    = extract_odds(row, p["market"])
                roi_contrib = None
                if odds is not None:
                    roi_contrib = (odds - 1) if correct else -1.0
                results.append({
                    "league":   key,
                    "season":   season,
                    "market":   p["market"],
                    "conf":     p["conf"],
                    "sc":       round(p["sc"], 3),
                    "correct":  correct,
                    "odds":     odds,
                    "roi":      roi_contrib,
                })

        # Update rolling stats AFTER pick evaluation (no look-ahead)
        hs.record_home(hg, ag)
        as_.record_away(ag, hg)
        h2h_tracker.record(home, away, ftr)

    return results


# ─────────────────────────────────────────────────────────────────
#  STEP 6 — AGGREGATE & REPORT
# ─────────────────────────────────────────────────────────────────
def aggregate(all_results: list) -> dict:
    """Aggregate pick results into calibration tables."""
    from collections import defaultdict

    # By (market, conf)
    by_mc  = defaultdict(lambda: {"n": 0, "hits": 0, "roi_sum": 0, "roi_n": 0})
    # By league overall
    by_lg  = defaultdict(lambda: {"n": 0, "hits": 0, "roi_sum": 0, "roi_n": 0})
    # By market overall
    by_mkt = defaultdict(lambda: {"n": 0, "hits": 0, "roi_sum": 0, "roi_n": 0})

    for r in all_results:
        mc  = (r["market"], r["conf"])
        lg  = r["league"]
        mkt = r["market"]

        for bucket in [by_mc[mc], by_lg[lg], by_mkt[mkt]]:
            bucket["n"]    += 1
            bucket["hits"] += int(r["correct"])
            if r["roi"] is not None:
                bucket["roi_sum"] += r["roi"]
                bucket["roi_n"]   += 1

    def finalise(d):
        out = {}
        for k, v in d.items():
            hit_rate = v["hits"] / v["n"] * 100 if v["n"] else 0
            roi      = v["roi_sum"] / v["roi_n"] * 100 if v["roi_n"] else None
            out[k] = {"n": v["n"], "hits": v["hits"], "hit_rate": round(hit_rate, 1),
                      "roi": round(roi, 1) if roi is not None else None,
                      "roi_n": v["roi_n"]}
        return out

    return {
        "by_market_conf": finalise(by_mc),
        "by_league":      finalise(by_lg),
        "by_market":      finalise(by_mkt),
        "total":          len(all_results),
    }


# ─────────────────────────────────────────────────────────────────
#  STEP 7 — HTML REPORT
# ─────────────────────────────────────────────────────────────────
MARKET_LABELS = {
    "heimsieg":    "🏠 Heimsieg",
    "auswärtssieg":"✈️ Auswärtssieg",
    "draw":        "🤝 Unentschieden",
    "over25":      "⚽ Über 2.5 Tore",
    "under25":     "🔒 Unter 2.5 Tore",
    "btts":        "🎯 Beide treffen",
}
CONF_LABELS = {"high": "★★★ Hoch", "medium": "★★☆ Mittel", "low": "★☆☆ Niedrig"}
LEAGUE_META = {k: v for k, v in LEAGUES.items()}


def roi_color(roi):
    if roi is None:   return "#888"
    if roi >= 5:      return "#22c55e"
    if roi >= 0:      return "#a3e635"
    if roi >= -5:     return "#fb923c"
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


def build_html_report(agg: dict, league_agg: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    total = agg["total"]
    bmc   = agg["by_market_conf"]
    blg   = agg["by_league"]
    bmkt  = agg["by_market"]

    # Build market+conf table rows
    markets_order = ["heimsieg", "auswärtssieg", "draw", "over25", "under25", "btts"]
    confs_order   = ["high", "medium", "low"]

    def mc_row(mkt, conf):
        key = (mkt, conf)
        d   = bmc.get(key, {"n": 0, "hit_rate": 0, "roi": None, "roi_n": 0})
        if d["n"] < 10:
            return f"""<tr>
              <td>{MARKET_LABELS.get(mkt, mkt)}</td>
              <td>{CONF_LABELS.get(conf, conf)}</td>
              <td style="color:#555">{d['n']}</td>
              <td colspan="2" style="color:#555;font-style:italic">zu wenig Daten</td>
            </tr>"""
        hr_col  = hitrate_color(d["hit_rate"])
        roi_col = roi_color(d["roi"])
        # Implied probability from our model vs actual hit rate
        # high = implied ~75%, medium = ~60%, low = ~50%
        implied = {"high": 75, "medium": 60, "low": 50}.get(conf, 55)
        diff    = d["hit_rate"] - implied
        diff_str = f"{'+'if diff>=0 else ''}{diff:.1f}pp vs. impliziert {implied}%"
        return f"""<tr>
          <td>{MARKET_LABELS.get(mkt, mkt)}</td>
          <td>{CONF_LABELS.get(conf, conf)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_col};font-weight:700">{fmt_hr(d['hit_rate'])}
              <span style="font-size:10px;font-weight:400;color:#888;margin-left:4px">{diff_str}</span></td>
          <td style="color:{roi_col};font-weight:700">{fmt_roi(d['roi'])}
              <span style="font-size:10px;font-weight:400;color:#888;margin-left:4px">(n={d['roi_n']:,})</span></td>
        </tr>"""

    cal_rows = "".join(mc_row(m, c) for m in markets_order for c in confs_order)

    # League summary rows
    def lg_row(key):
        meta = LEAGUE_META.get(key, {"name": key, "flag": ""})
        d    = blg.get(key, {"n": 0, "hit_rate": 0, "roi": None})
        if d["n"] == 0: return ""
        hr_col  = hitrate_color(d["hit_rate"])
        roi_col = roi_color(d["roi"])
        return f"""<tr>
          <td>{meta.get('flag','')} {meta.get('name', key)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_col};font-weight:700">{fmt_hr(d['hit_rate'])}</td>
          <td style="color:{roi_col};font-weight:700">{fmt_roi(d['roi'])}</td>
        </tr>"""

    lg_rows = "".join(lg_row(k) for k in sorted(blg.keys()))

    # Market summary rows
    def mkt_row(mkt):
        d = bmkt.get(mkt, {"n": 0, "hit_rate": 0, "roi": None})
        if d["n"] == 0: return ""
        hr_col  = hitrate_color(d["hit_rate"])
        roi_col = roi_color(d["roi"])
        return f"""<tr>
          <td>{MARKET_LABELS.get(mkt, mkt)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_col};font-weight:700">{fmt_hr(d['hit_rate'])}</td>
          <td style="color:{roi_col};font-weight:700">{fmt_roi(d['roi'])}</td>
        </tr>"""

    mkt_rows = "".join(mkt_row(m) for m in markets_order)

    # Key findings (auto-generated)
    findings = []

    # Find best and worst market+conf combos (min 50 picks)
    good = [(k, v) for k, v in bmc.items() if v["n"] >= 50 and v["hit_rate"] >= 60]
    bad  = [(k, v) for k, v in bmc.items() if v["n"] >= 50 and v["hit_rate"] < 45]
    good.sort(key=lambda x: x[1]["hit_rate"], reverse=True)
    bad.sort(key=lambda x: x[1]["hit_rate"])

    for (mkt, conf), v in good[:3]:
        findings.append(f"✅ <strong>{MARKET_LABELS.get(mkt, mkt)} ({CONF_LABELS.get(conf, conf)})</strong>: "
                        f"{v['hit_rate']:.1f}% Trefferquote bei {v['n']:,} Picks "
                        f"— Modell ist hier gut kalibriert.")

    for (mkt, conf), v in bad[:3]:
        findings.append(f"⚠️ <strong>{MARKET_LABELS.get(mkt, mkt)} ({CONF_LABELS.get(conf, conf)})</strong>: "
                        f"nur {v['hit_rate']:.1f}% Trefferquote bei {v['n']:,} Picks "
                        f"— Schwachpunkt, Gewichtungen überdenken.")

    # High vs medium overall performance
    high_hits  = sum(v["hits"] for k, v in bmc.items() if k[1] == "high"  and v["n"] >= 20)
    high_n     = sum(v["n"]    for k, v in bmc.items() if k[1] == "high"  and v["n"] >= 20)
    med_hits   = sum(v["hits"] for k, v in bmc.items() if k[1] == "medium" and v["n"] >= 20)
    med_n      = sum(v["n"]    for k, v in bmc.items() if k[1] == "medium" and v["n"] >= 20)
    if high_n and med_n:
        high_hr = high_hits / high_n * 100
        med_hr  = med_hits  / med_n  * 100
        if high_hr > med_hr + 5:
            findings.append(f"📈 <strong>★★★ Picks schlagen ★★☆</strong> deutlich: "
                            f"{high_hr:.1f}% vs {med_hr:.1f}% — Schwellenwert-Kalibrierung wirkt.")
        elif abs(high_hr - med_hr) < 3:
            findings.append(f"⚠️ <strong>★★★ und ★★☆ performen fast gleich</strong> "
                            f"({high_hr:.1f}% vs {med_hr:.1f}%) — High-Threshold sollte weiter erhöht werden.")

    findings_html = "".join(f"<li style='margin-bottom:8px'>{f}</li>" for f in findings)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Backtest Report — Betting Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 30px; }}
  h1 {{ font-size: 24px; font-weight: 800; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px;
       color: #58a6ff; margin: 28px 0 12px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 28px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 18px; }}
  .stat-val {{ font-size: 36px; font-weight: 800; color: #58a6ff; }}
  .stat-lbl {{ font-size: 12px; color: #888; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #21262d; color: #888; font-weight: 600; padding: 8px 12px; text-align: left;
       font-size: 11px; text-transform: uppercase; letter-spacing: .4px; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #21262d; }}
  tr:hover td {{ background: #161b22; }}
  .findings {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px;
               padding: 18px 20px; list-style: none; font-size: 13px; line-height: 1.6; }}
  .section {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px;
              padding: 16px; margin-bottom: 20px; overflow-x: auto; }}
  .note {{ background: #1c2128; border: 1px solid #388bfd40; border-radius: 8px;
           padding: 12px 16px; font-size: 12px; color: #8b949e; margin-top: 20px; line-height: 1.6; }}
</style>
</head>
<body>
<h1>📊 Backtest Report — Betting Dashboard</h1>
<div class="meta">Generiert: {now} · Datenbasis: football-data.co.uk · Saisons: {', '.join(SEASONS)}</div>

<div class="grid">
  <div class="card">
    <div class="stat-val">{total:,}</div>
    <div class="stat-lbl">Analysierte Picks total</div>
  </div>
  <div class="card">
    <div class="stat-val">{len(blg)}</div>
    <div class="stat-lbl">Ligen mit Daten</div>
  </div>
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

<h2>⚽ Übersicht nach Markt (alle Konfidenzen)</h2>
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
  <strong>Methodik:</strong> Jeder Match wird erst nach mindestens {WARMUP_GAMES} gespielten Partien pro Team ausgewertet (kein Look-Ahead).
  Rolling Stats basieren auf den letzten 6 Spielen (Form) bzw. 10 Spielen (Tore/Gegentore).
  ROI = (Gewinn/Verlust je 1€ Einsatz) bei Flat-Staking mit verfügbaren Pinnacle- oder Bet365-Quoten.
  Stake-Labels (Gold/Rot) und Elo-Daten sind im Backtest <em>nicht</em> enthalten — sie testen die Kern-Signale
  (Form, H2H, Tore) isoliert. Das ist bewusst: so sehen wir die Basis-Performance ohne Saisonkontext.
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Betting Dashboard — Backtest Engine")
    print(f"  Saisons: {', '.join(SEASONS)}")
    print(f"  Ligen:   {', '.join(LEAGUES.keys())}")
    print("=" * 60)

    # 1. Download
    print("\n📥  Lade historische Daten...")
    all_data = load_all_data()

    if not all_data:
        print("❌  Keine Daten geladen. Bitte Internetverbindung prüfen.")
        return

    # 2. Simulate picks
    print("⚙️   Simuliere Picks...")
    all_results = []
    league_agg  = {}
    for key, df in all_data.items():
        meta = LEAGUES[key]
        print(f"  {meta['flag']} {meta['name']}: {len(df)} Spiele → ", end="", flush=True)
        t0 = time.time()
        res = process_league(key, df)
        all_results.extend(res)
        print(f"{len(res)} Picks ({time.time()-t0:.1f}s)")

    print(f"\n  📊 Total: {len(all_results):,} Picks über alle Ligen")

    # 3. Aggregate
    print("\n📈  Aggregiere Ergebnisse...")
    agg = aggregate(all_results)

    # 4. Print quick summary to console
    print("\n" + "=" * 60)
    print("  KALIBRIERUNG — Trefferquote nach Konfidenz")
    print("=" * 60)
    for conf in ["high", "medium", "low"]:
        total_c = sum(v["n"]    for k, v in agg["by_market_conf"].items() if k[1] == conf)
        hits_c  = sum(v["hits"] for k, v in agg["by_market_conf"].items() if k[1] == conf)
        if total_c:
            print(f"  {CONF_LABELS[conf]:20} {hits_c/total_c*100:.1f}% ({hits_c:,}/{total_c:,} Picks)")
    print()
    print("  TREFFERQUOTE nach Markt:")
    for mkt in ["heimsieg", "auswärtssieg", "draw", "over25", "under25", "btts"]:
        d = agg["by_market"].get(mkt, {"n":0,"hit_rate":0})
        if d["n"]:
            print(f"  {MARKET_LABELS.get(mkt,''):25} {d['hit_rate']:.1f}% ({d['n']:,} Picks)")

    # 5. Save HTML report
    out_path = Path(__file__).parent / "backtest_report.html"
    html = build_html_report(agg, league_agg)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✅  Report gespeichert: {out_path}")
    print("🌐  Öffne im Browser...")
    webbrowser.open(str(out_path))


if __name__ == "__main__":
    main()
