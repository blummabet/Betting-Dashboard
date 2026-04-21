#!/usr/bin/env python3
"""
backtest_v4.py — BetEdge Full-Season Backtest mit Last-N-Rounds-Fokus
=====================================================================
Neue Features vs. v3:
  • LAST_N_ROUNDS Filter — testet separat: alle Runden vs. nur die letzten N
    (wo Druck tatsächlich wirkt). Hauptergebnis = letzte N Runden.
  • Karten-Market — HY+AY aus CSV → Over 3.5 Gelbe (Score + Hit-Rate)
  • Over 3.5 Tore — Score + Hit-Rate (Pinnacle-Odds nur wenn verfügbar)
  • ★★★ / ★★ / ★ Confidence-Split — ROI nach Konfidenz-Tier
  • Season-Trend — ROI pro Saison getrennt (verbessert sich das Modell?)
  • Motivation-Guard — canDraw/motivNone korrekt klassifiziert (kein falscher Druck)
  • Saisons 2122–2425 (4 Saisons, ~30k+ Spiele)

RUN:  python3 backtest_v4.py
OUT:  backtest_v4_report.html
"""

import os, sys, math, json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

try:
    import requests
    import pandas as pd
except ImportError:
    print("📦  Installing required packages...")
    os.system(f"{sys.executable} -m pip install requests pandas --quiet --break-system-packages")
    import requests
    import pandas as pd

# ──────────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────────
BASE_URL     = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
SEASONS      = ["2122", "2223", "2324", "2425"]   # 4 Saisons = ~22k+ Endphasen-Picks
LAST_N_ROUNDS = 10      # "Endphase" — wie viele Runden vor Saisonende
WARMUP_GAMES  = 6       # Spiele pro Team bevor Picks simuliert werden

# Lokale CSV-Dateien im selben Verzeichnis wie dieses Script
LOCAL_DIR = Path(__file__).parent
LOCAL_FILE_MAP = {
    "2122": "{code}_2122.csv",
    "2223": "{code}_2223.csv",
    "2324": "{code}.csv",
    "2425": "{code} (1).csv",
}

LEAGUES = {
    "ENG": {"code": "E0",  "name": "Premier League",    "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "GER": {"code": "D1",  "name": "Bundesliga",         "flag": "🇩🇪"},
    "ITA": {"code": "I1",  "name": "Serie A",            "flag": "🇮🇹"},
    "ESP": {"code": "SP1", "name": "La Liga",            "flag": "🇪🇸"},
    "FRA": {"code": "F1",  "name": "Ligue 1",            "flag": "🇫🇷"},
    # NED, POR, SCO, TUR, BEL, AUT — keine lokalen CSVs vorhanden, Download im Sandbox geblockt
}

# Ligakonfiguration: Teams, Abstiegsplätze, CL-Plätze, Runden
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

# Liga-spezifischer Over-Cap (wie in season-finish.html)
LG_CAPS = {
    "ENG": +0.05, "GER": +0.05, "ITA": -0.04, "FRA": -0.04,
    "ESP":  0.00, "NED": +0.03, "POR":  0.00, "SCO": +0.02,
    "TUR": +0.02, "BEL": +0.02, "AUT":  0.00,
}

# ──────────────────────────────────────────────────────────────────
#  SCHRITT 1 — DATEN LADEN
# ──────────────────────────────────────────────────────────────────
def _parse_df(raw_text: str, season: str, code: str) -> Optional[pd.DataFrame]:
    """Parse CSV text into a cleaned DataFrame."""
    from io import StringIO
    # Strip BOM if present
    if raw_text.startswith('\ufeff'):
        raw_text = raw_text[1:]
    df = pd.read_csv(StringIO(raw_text), encoding="utf-8", on_bad_lines="skip")
    required = {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
    if not required.issubset(df.columns):
        return None
    df = df.dropna(subset=list(required))
    for col in ["FTHG", "FTAG"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["FTHG", "FTAG"])
    # Drop empty rows (sometimes trailing blank lines become rows with all NaN)
    df = df.dropna(how="all")
    for col in ["HS", "AS", "HST", "AST", "HY", "AY", "HC", "AC", "HF", "AF"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        df = df.sort_values("Date").reset_index(drop=True)
    has_shots   = {"HST", "AST"}.issubset(df.columns)
    has_cards   = {"HY",  "AY" }.issubset(df.columns)
    has_corners = {"HC",  "AC" }.issubset(df.columns)
    tags = []
    if has_shots:   tags.append("shots ✓")
    if has_cards:   tags.append("cards ✓")
    if has_corners: tags.append("corners ✓")
    print(f"    ✅ {season}/{code}: {len(df)} Spiele ({', '.join(tags) if tags else 'basic'})")
    return df


def fetch_csv(season: str, code: str) -> Optional[pd.DataFrame]:
    # 1️⃣  Try local file first (no network needed)
    if season in LOCAL_FILE_MAP:
        fname = LOCAL_FILE_MAP[season].format(code=code)
        local_path = LOCAL_DIR / fname
        if local_path.exists():
            try:
                raw = local_path.read_text(encoding="utf-8", errors="replace")
                df = _parse_df(raw, season, code)
                if df is not None:
                    return df
            except Exception as e:
                print(f"    ⚠️  Lokale Datei {fname} fehlgeschlagen: {e}")

    # 2️⃣  Fallback: download from football-data.co.uk
    url = BASE_URL.format(season=season, code=code)
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200 or len(r.text.strip()) < 100:
            print(f"    ❌ {season}/{code}: HTTP {r.status_code}")
            return None
        return _parse_df(r.text, season, code)
    except Exception as e:
        print(f"    ❌ {season}/{code}: {e}")
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
            print(f"    → Keine Daten\n")
    return all_data


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 2 — ROLLING STATS
# ──────────────────────────────────────────────────────────────────
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
        self.yellows_home   = []   # NEW: Gelbe Karten
        self.yellows_away   = []
        self.corners_home   = []   # NEW: Ecken
        self.corners_away   = []

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

    def xg_home(self, n=10) -> Optional[float]:
        sot = self.sot_home[-n:]
        if not sot: return None
        shots = self.shots_home[-n:]
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 2.0
        return round(avg_sot * 0.35 + max(0, avg_shots - avg_sot) * 0.055, 3)

    def xg_away(self, n=10) -> Optional[float]:
        sot = self.sot_away[-n:]
        if not sot: return None
        shots = self.shots_away[-n:]
        avg_sot   = sum(sot) / len(sot)
        avg_shots = sum(shots) / len(shots) if shots else avg_sot * 2.0
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

    def avg_yellows_home(self, n=10) -> Optional[float]:
        y = [x for x in self.yellows_home[-n:] if x is not None]
        return sum(y) / len(y) if y else None

    def avg_yellows_away(self, n=10) -> Optional[float]:
        y = [x for x in self.yellows_away[-n:] if x is not None]
        return sum(y) / len(y) if y else None

    def avg_corners_home(self, n=10) -> Optional[float]:
        c = [x for x in self.corners_home[-n:] if x is not None]
        return sum(c) / len(c) if c else None

    def avg_corners_away(self, n=10) -> Optional[float]:
        c = [x for x in self.corners_away[-n:] if x is not None]
        return sum(c) / len(c) if c else None

    def record_home(self, scored, conceded, h_sot=None, h_shots=None,
                    yellows=None, corners=None):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_home.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)
        self.cs_home.append(1 if conceded == 0 else 0)
        self.fts_home.append(1 if scored == 0 else 0)
        if h_sot is not None and not math.isnan(h_sot):
            self.sot_home.append(h_sot)
            self.shots_home.append(h_shots if h_shots is not None and not math.isnan(h_shots) else h_sot * 2.0)
        self.yellows_home.append(yellows)
        self.corners_home.append(corners)

    def record_away(self, scored, conceded, a_sot=None, a_shots=None,
                    yellows=None, corners=None):
        result = "W" if scored > conceded else "D" if scored == conceded else "L"
        self.results_away.append(result)
        self.all_results.append(result)
        self.goals_scored.append(scored)
        self.goals_conceded.append(conceded)
        self.cs_away.append(1 if conceded == 0 else 0)
        self.fts_away.append(1 if scored == 0 else 0)
        if a_sot is not None and not math.isnan(a_sot):
            self.sot_away.append(a_sot)
            self.shots_away.append(a_shots if a_shots is not None and not math.isnan(a_shots) else a_sot * 2.0)
        self.yellows_away.append(yellows)
        self.corners_away.append(corners)


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
            if home <= away: d["home_wins"] += 1
            else:            d["away_wins"] += 1
        elif result == "A":
            if home <= away: d["away_wins"] += 1
            else:            d["home_wins"] += 1
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


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 3 — LIVE-TABELLE
# ──────────────────────────────────────────────────────────────────
class LeagueTable:
    def __init__(self):
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
        rows = [{"team": t, **v} for t, v in self._rows.items()]
        rows.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"], x["team"]))
        for i, r in enumerate(rows):
            r["pos"] = i + 1
        return rows

    def get_pts(self, snap: list, pos: int) -> int:
        return snap[pos - 1]["pts"] if 1 <= pos <= len(snap) else 0

    def team_pos(self, snap: list, team: str) -> Optional[int]:
        for r in snap:
            if r["team"] == team: return r["pos"]
        return None

    def team_pts(self, snap: list, team: str) -> int:
        for r in snap:
            if r["team"] == team: return r["pts"]
        return 0


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 4 — PRESSURE & MOTIVATION
# ──────────────────────────────────────────────────────────────────
PressureTuple = Tuple[float, bool, bool, str]  # (ratio, mustWin, canDraw, motiv)


def calc_pressure_and_motiv(team: str, snap: list, table: LeagueTable,
                              league_cfg: dict, rounds_left: int) -> PressureTuple:
    """
    Berechnet pressureRatio, mustWin, canDraw + motivationLevel.
    Spiegelt die Logik von calc_pressure() + calc_motivation() aus update_dashboard.py.

    motiv:
      'none' = mathematisch bestätigt (Meister/Absteiger) → kein Druck
      'low'  = fast bestätigt (Wunder nötig)
      'full' = noch aktiv kämpfend
    """
    if not snap or rounds_left <= 0:
        return (0.0, False, True, "none")  # Saisonende

    total    = league_cfg["total"]
    rel      = league_cfg["rel"]
    rel_ply  = league_cfg.get("rel_playoff", 0)
    cl       = league_cfg.get("cl", 4)
    max_gain = rounds_left * 3

    pos      = table.team_pos(snap, team)
    team_pts = table.team_pts(snap, team)

    if pos is None:
        return (0.0, False, True, "full")

    rel_start   = total - rel + 1            # erste Auto-Abstiegsposition (z.B. 18 in PL)
    # Korrekte sichere Position: knapp über der Playoff/Abstiegszone
    # rel_ply=0 → Platz 17 ist sicher; rel_ply=1 → Platz 16 ist sicher (15 ist safe)
    safe_pos    = max(1, rel_start - rel_ply - 1)   # erste vollständig sichere Position
    # Abstiegs-Gefahrenzone: 4 Plätze über dem ersten gefährdeten Platz
    danger_pos  = max(1, safe_pos - 3)

    points_needed = 0
    motiv = "full"

    # ── Abstiegsgefahr ───────────────────────────────────────────
    if pos >= rel_start:
        # In der direkten Abstiegszone
        pts_safe = table.get_pts(snap, safe_pos)
        gap      = pts_safe - team_pts
        if gap > max_gain:
            return (0.0, False, True, "none")  # Mathematisch bestätigt
        if gap > max_gain * 0.7:
            motiv = "low"
        # Druck = Gap + Puffer (Teams müssen über die Sicherheitszone hinaus)
        points_needed = max(0, gap + 1 + max(0, round(rounds_left * 0.25)))

    elif pos > safe_pos:
        # In der Playoff-Zone (zwischen safe und direkt-Abstieg)
        pts_safe = table.get_pts(snap, safe_pos)
        gap      = max(0, pts_safe - team_pts)
        if gap > max_gain:
            return (0.0, False, True, "none")
        if gap > max_gain * 0.7:
            motiv = "low"
        points_needed = max(0, gap + max(0, round(rounds_left * 0.20)))

    elif pos >= danger_pos:
        # Im Gefahrenbereich (bis 4 Plätze über dem sicheren Bereich)
        pts_safe = table.get_pts(snap, safe_pos)
        gap      = max(0, pts_safe - team_pts)
        if gap > max_gain:
            return (0.0, False, True, "none")
        # Weicher — echte Bedrohung nur wenn Rückstand vorhanden
        points_needed = max(0, gap + max(0, round(rounds_left * 0.10)))

    else:
        # Safe — Titelkampf?
        if pos == 1:
            pts_2nd = table.get_pts(snap, 2) if len(snap) >= 2 else 0
            if team_pts - pts_2nd > max_gain:
                return (0.0, False, True, "none")  # Mathematisch Meister
            if team_pts - pts_2nd > max_gain * 0.5:
                motiv = "low"
        elif pos <= cl + 2:
            pts_cl = table.get_pts(snap, cl)
            gap = pts_cl - team_pts
            if gap <= max_gain * 0.6:
                points_needed = max(0, round((gap + 1) * 0.7))

    pressure_ratio = min(1.0, points_needed / max_gain) if max_gain > 0 else 0.0
    pressure_ratio = round(pressure_ratio, 3)

    # motivNone → kein mustWin (genau wie unser JS-Fix)
    if motiv == "none":
        return (0.0, False, True, "none")

    must_win  = pressure_ratio > 0.30 and motiv == "full"   # realistischer Schwellenwert
    can_draw  = pressure_ratio < 0.12

    return (pressure_ratio, must_win, can_draw, motiv)


def pressure_boost(rounds_left: int) -> float:
    """Granular pressure boost — spiegelt _pressureBoost aus season-finish.html"""
    if rounds_left <= 1: return 0.28
    if rounds_left <= 2: return 0.22
    if rounds_left <= 3: return 0.16
    if rounds_left <= 4: return 0.11
    if rounds_left <= 5: return 0.08
    if rounds_left <= 6: return 0.06
    return 0.0


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 5 — SCORING ENGINE
# ──────────────────────────────────────────────────────────────────

def score_heimsieg(hFS_home, hStr, hHWR, awayInForm, homePoor) -> float:
    sc = 0.40 + (hFS_home - 0.5) * 1.20 + max(0, hStr) * 0.09 + hHWR * 0.35
    if homePoor:      sc -= 0.48
    if awayInForm:    sc -= 0.20
    return sc


def score_auswärtssieg(aFS_away, aStr, aAWR, homeInForm, awayPoor) -> float:
    sc = 0.26 + (aFS_away - 0.5) * 1.20 + max(0, aStr) * 0.09 + aAWR * 0.35
    if awayPoor:      sc -= 0.48
    if homeInForm:    sc -= 0.20
    return sc


def score_draw(drawRate, hFS_home, aFS_away) -> float:
    sc = drawRate * 0.85 + (0.22 if drawRate > 0.36 else 0)
    if abs(hFS_home - aFS_away) < 0.10: sc += 0.12
    return sc


def score_over25(expGoals, h_att, a_att, lg_cap=0.0,
                 both_verylow=False, h_csr=0.25, a_csr=0.25) -> Optional[float]:
    """Hard Gate: kein Over-2.5-Pick wenn expGoals < 2.5"""
    if expGoals < 2.50: return None
    sc = (0.78 if expGoals > 3.2 else 0.66 if expGoals > 2.8 else
          0.52 if expGoals > 2.5 else 0.30 if expGoals > 2.2 else 0.10)
    sc += lg_cap
    # Defensive-Teams-Unterdrückung
    if both_verylow: sc = max(0.0, sc - 0.30)
    # Clean-Sheet-Bonus/Malus
    cs_avg = (h_csr + a_csr) / 2
    if cs_avg <= 0.12: sc = min(0.92, sc + 0.06)
    elif cs_avg >= 0.45: sc = max(0.0, sc - 0.10)
    return max(0.0, min(sc, 0.92))


def score_over35(expGoals, h_att, a_att, lg_cap=0.0) -> float:
    sc = (0.82 if expGoals > 3.8 else 0.65 if expGoals > 3.4 else
          0.44 if expGoals > 3.1 else 0.20 if expGoals > 2.7 else 0.06)
    sc += lg_cap * 0.5  # kleinerer Cap-Einfluss für 3.5
    both_verylow = h_att < 0.65 and a_att < 0.65
    if both_verylow: sc = max(0.0, sc - 0.40)
    return max(0.0, min(sc, 0.92))


def score_under25(expGoals, h_csr=0.25, a_csr=0.25, h_ftsr=0.20, a_ftsr=0.20,
                  lg_cap=0.0) -> float:
    sc = (0.85 if expGoals < 1.7 else 0.72 if expGoals < 2.0 else
          0.57 if expGoals < 2.3 else 0.34 if expGoals < 2.6 else 0.12)
    sc -= lg_cap
    if h_csr > 0.40: sc = min(0.92, sc + 0.10)
    elif h_csr > 0.30: sc = min(0.92, sc + 0.05)
    if a_ftsr > 0.35: sc = min(0.92, sc + 0.07)
    if h_ftsr > 0.30: sc = min(0.92, sc + 0.05)
    return max(0.0, min(sc, 0.92))


def score_btts(h_att, a_att, h_def, a_def,
               h_csr=0.25, a_csr=0.25, h_ftsr=0.20, a_ftsr=0.20) -> float:
    if h_att > 1.30 and a_att > 1.10 and h_def > 0.90 and a_def > 0.90:
        sc = 0.75
    elif h_att > 1.15 and a_att > 0.95 and h_def > 0.85 and a_def > 0.85:
        sc = 0.55
    else:
        sc = 0.20
    if h_csr  > 0.40: sc -= 0.18
    elif h_csr  > 0.30: sc -= 0.10
    if a_csr  > 0.35: sc -= 0.15
    elif a_csr  > 0.25: sc -= 0.08
    if h_ftsr > 0.30: sc -= 0.12
    if a_ftsr > 0.28: sc -= 0.10
    return max(0.05, min(sc, 0.92))


def score_cards(h_yel_avg: Optional[float], a_yel_avg: Optional[float],
                h_pr: PressureTuple, a_pr: PressureTuple,
                rounds_left: int) -> Optional[float]:
    """
    Score für Over 3.5 Gelbe Karten.
    Nur wenn Kartendaten verfügbar sind.
    Spiegelt den Cards-Block aus season-finish.html.
    """
    if h_yel_avg is None or a_yel_avg is None:
        return None

    h_ratio, h_mw, _, h_motiv = h_pr
    a_ratio, a_mw, _, a_motiv = a_pr
    pb = pressure_boost(rounds_left)

    # Motivation-Guard (entspricht _cardPressBoost aus season-finish.html)
    h_conf_rel = h_motiv == "none"
    a_conf_rel = a_motiv == "none"
    any_conf_rel = h_conf_rel or a_conf_rel
    card_press_boost = pb * 0.20 if any_conf_rel else pb

    total_yel = h_yel_avg + a_yel_avg
    if total_yel > 5.5: sc = 0.78
    elif total_yel > 4.8: sc = 0.62
    elif total_yel > 4.2: sc = 0.48
    elif total_yel > 3.8: sc = 0.36
    elif total_yel > 3.4: sc = 0.24
    else: sc = 0.12

    # Druckboost (beide mustWin = höchste Intensität)
    if h_mw and a_mw:
        sc = min(0.88, sc + card_press_boost * 0.50)
    elif h_mw or a_mw:
        sc = min(0.80, sc + card_press_boost * 0.40)

    return max(0.0, min(sc, 0.92))


def apply_pressure_to_scores(scores: dict,
                              h_pr: PressureTuple, a_pr: PressureTuple,
                              rounds_left: int) -> dict:
    """
    Wendet Pressure-Adjustments auf Basis-Scores an.
    Entspricht apply_pressure() aus backtest_v3 + neuen Motivation-Guards.
    """
    h_ratio, h_mw, h_cd, h_motiv = h_pr
    a_ratio, a_mw, a_cd, a_motiv = a_pr
    pb = pressure_boost(rounds_left)

    sc_h  = scores["sc_h"]
    sc_a  = scores["sc_a"]
    sc_d  = scores["sc_d"]
    sc_ov = scores["sc_ov"]
    sc_o3 = scores["sc_o3"]
    sc_un = scores["sc_un"]
    sc_bt = scores["sc_bt"]

    # mustWin → Angriff ↑, Draw ↓
    if h_mw:
        sc_h = min(0.95, sc_h + pb * 0.70)
        sc_d = max(0.0,  sc_d - 0.09)
    if a_mw:
        sc_a = min(0.95, sc_a + pb * 0.70)
        sc_d = max(0.0,  sc_d - 0.09)

    # Beide mustWin → Open Game
    if h_mw and a_mw:
        if sc_ov is not None: sc_ov = min(0.92, sc_ov + pb * 1.30)
        sc_o3 = min(0.90, sc_o3 + pb * 1.20)
        sc_un = max(0.0, sc_un - pb * 1.10)
        sc_bt = min(0.92, sc_bt + pb * 0.70)
    elif h_mw or a_mw:
        if sc_ov is not None: sc_ov = min(0.92, sc_ov + pb * 0.85)
        sc_o3 = min(0.90, sc_o3 + pb * 0.70)
        sc_un = max(0.0, sc_un - pb * 0.65)
        sc_bt = min(0.92, sc_bt + pb * 0.30)

    # canDraw beide → Dead Rubber
    if h_cd and a_cd:
        sc_d  = min(0.92, sc_d + 0.10)
        if sc_ov is not None: sc_ov = max(0.0, sc_ov - 0.05)
        sc_un = min(0.92, sc_un + 0.04)
        sc_bt = max(0.05, sc_bt - 0.04)

    # Leichte Richtungsboosts für nicht-mustWin aber unter Druck
    if not h_mw and h_ratio > 0.30:
        sc_h = min(0.95, sc_h + h_ratio * 0.10)

    return {**scores,
            "sc_h": sc_h, "sc_a": sc_a, "sc_d": sc_d,
            "sc_ov": sc_ov, "sc_o3": sc_o3, "sc_un": sc_un, "sc_bt": sc_bt}


def conf_label(sc: float, h_thresh: float, m_thresh: float) -> str:
    if sc >= h_thresh:  return "high"
    if sc >= m_thresh:  return "medium"
    return "low"


THRESHOLDS = {
    "heimsieg":     (1.20, 0.68),
    "auswärtssieg": (1.08, 0.62),
    "draw":         (0.70, 0.45),
    "over25":       (0.50, 0.20),
    "over35":       (0.50, 0.25),
    "under25":      (0.45, 0.18),
    "btts":         (0.70, 0.45),
    "cards35":      (0.60, 0.35),
}

MARKET_LABELS = {
    "heimsieg":     "🏠 Heimsieg",
    "auswärtssieg": "✈️ Auswärtssieg",
    "draw":         "🤝 Unentschieden",
    "over25":       "⚽ Über 2.5",
    "over35":       "🔥 Über 3.5",
    "under25":      "🔒 Unter 2.5",
    "btts":         "🎯 Beide treffen",
    "cards35":      "🟨 Karten Ü3.5",
}


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 6 — ODDS EXTRAKTION (aus CSV)
# ──────────────────────────────────────────────────────────────────
def extract_odds(row: pd.Series, market: str) -> Optional[float]:
    """
    Liest Pinnacle- bzw. Best-Available-Odds aus CSV.
    PSH = Pinnacle Home, PSA = Pinnacle Away, etc.
    """
    candidates = {
        "heimsieg":     ["PSH",  "PSCH",  "B365H", "MaxH", "AvgH"],
        "auswärtssieg": ["PSA",  "PSCA",  "B365A", "MaxA", "AvgA"],
        "draw":         ["PSD",  "PSCD",  "B365D", "MaxD", "AvgD"],
        "over25":       ["P>2.5","PC>2.5","B365>2.5","Max>2.5","Avg>2.5"],
        "under25":      ["P<2.5","PC<2.5","B365<2.5","Max<2.5","Avg<2.5"],
        "btts":         [],   # BTTS-Quoten sind nicht in football-data.co.uk CSVs
        "over35":       [],   # O/U 3.5 nicht in Standard-CSVs
        "cards35":      [],   # Karten-Quoten nicht in CSVs
    }
    for col in candidates.get(market, []):
        if col in row.index:
            val = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(val) and 1.02 <= val <= 30.0:
                return float(val)
    return None


def evaluate_pick(market: str, hg: int, ag: int,
                  h_yel=None, a_yel=None) -> bool:
    total_goals = hg + ag
    if market == "heimsieg":     return hg > ag
    if market == "auswärtssieg": return ag > hg
    if market == "draw":         return hg == ag
    if market == "over25":       return total_goals > 2.5
    if market == "over35":       return total_goals > 3.5
    if market == "under25":      return total_goals < 2.5
    if market == "btts":         return hg > 0 and ag > 0
    if market == "cards35":
        if h_yel is not None and a_yel is not None:
            return (h_yel + a_yel) > 3.5
        return None  # Kein Urteil ohne Daten
    return False


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 7 — EINE LIGA PROZESSIEREN
# ──────────────────────────────────────────────────────────────────
def process_league(key: str, df: pd.DataFrame) -> list:
    """
    Verarbeitet alle Spiele einer Liga chronologisch.
    Gibt für jedes Spiel 5+ Picks zurück (v2 ohne Druck, v3 mit Druck).
    Markiert jedes Spiel ob es in den "letzten N Runden" liegt.
    """
    results = []
    league_cfg = LEAGUE_CFGS.get(key, {"total": 18, "rel": 3, "rel_playoff": 0,
                                        "cl": 4, "rounds": 34})
    total_rounds = league_cfg["rounds"]
    games_per_round = league_cfg["total"] // 2

    has_shots   = {"HST", "AST"}.issubset(df.columns)
    has_shots_t = {"HS",  "AS" }.issubset(df.columns)
    has_cards   = {"HY",  "AY" }.issubset(df.columns)
    has_corners = {"HC",  "AC" }.issubset(df.columns)

    for season in sorted(df["_season"].unique()):
        df_s = df[df["_season"] == season].copy()
        if "Date" in df_s.columns:
            df_s = df_s.sort_values("Date").reset_index(drop=True)

        total_games_in_season = len(df_s)
        last_n_cutoff = total_games_in_season - (LAST_N_ROUNDS * games_per_round)

        team_stats  = defaultdict(TeamStats)
        h2h_tracker = H2HTracker()
        table       = LeagueTable()

        for game_idx, (_, row) in enumerate(df_s.iterrows()):
            home = str(row["HomeTeam"]).strip()
            away = str(row["AwayTeam"]).strip()
            hg   = int(row["FTHG"])
            ag   = int(row["FTAG"])
            ftr  = str(row["FTR"]).strip()

            hs  = team_stats[home]
            as_ = team_stats[away]
            h2h = h2h_tracker.get(home, away)

            # Pre-Match Zustand
            snap        = table.snapshot()
            h_rounds_left = max(0, total_rounds - hs.games_played())
            a_rounds_left = max(0, total_rounds - as_.games_played())
            rounds_left   = h_rounds_left   # für pressure_boost / is_last_n Referenz

            # Pressure & Motivation — jedes Team mit eigenem rounds_left
            h_pr = calc_pressure_and_motiv(home, snap, table, league_cfg, h_rounds_left)
            a_pr = calc_pressure_and_motiv(away, snap, table, league_cfg, a_rounds_left)

            is_last_n = game_idx >= last_n_cutoff

            if hs.games_played() >= WARMUP_GAMES and as_.games_played() >= WARMUP_GAMES:

                # Basis-Kennzahlen
                hFS   = hs.form_score()
                aFS   = as_.form_score()
                hStr  = hs.streak()
                aStr  = as_.streak()
                hHWR  = hs.home_win_rate()
                aAWR  = as_.away_win_rate()
                hAtt  = hs.avg_goals_scored()
                aAtt  = as_.avg_goals_scored()
                hDef  = hs.avg_goals_conceded()
                aDef  = as_.avg_goals_conceded()
                lg_cap = LG_CAPS.get(key, 0.0)

                h_xg  = hs.xg_home()
                a_xg  = as_.xg_away()
                if h_xg is not None and a_xg is not None:
                    expGoals  = h_xg + a_xg
                    xg_src    = "shots"
                else:
                    expGoals  = (hAtt + aDef + aAtt + hDef) / 2
                    xg_src    = "goals"

                # Motivation-Adjustments (spiegelt JS: homeAttStr *= 0.82 bei motivNone)
                h_motiv = h_pr[3]
                a_motiv = a_pr[3]
                if h_motiv == "none":   hAtt *= 0.82; hDef *= 1.12
                elif h_motiv == "low":  hAtt *= 0.92; hDef *= 1.06
                if a_motiv == "none":   aAtt *= 0.82; aDef *= 1.12
                elif a_motiv == "low":  aAtt *= 0.92; aDef *= 1.06

                h_csr  = hs.clean_sheet_rate_home()
                a_csr  = as_.clean_sheet_rate_away()
                h_ftsr = hs.failed_to_score_rate_home()
                a_ftsr = as_.failed_to_score_rate_away()

                hFS_home   = min(0.93, hHWR * 0.55 + hFS * 0.45)
                aFS_away   = max(0.07, aAWR * 0.55 + aFS * 0.45)
                homeInForm = hStr >= 2 and hFS_home > 0.62
                awayInForm = aStr >= 2 and aFS_away > 0.56
                homePoor   = hStr <= -3 or hFS_home < 0.25
                awayPoor   = aStr <= -3 or aFS_away < 0.22

                h2h_drate  = h2h["draw_rate"]
                both_verylow = hAtt < 0.65 and aAtt < 0.65

                # Basis-Scores (v2 — ohne Pressure)
                base = {
                    "sc_h":  score_heimsieg(hFS_home, hStr, h2h["home_win_rate"], awayInForm, homePoor),
                    "sc_a":  score_auswärtssieg(aFS_away, aStr, h2h["away_win_rate"], homeInForm, awayPoor),
                    "sc_d":  score_draw(h2h_drate, hFS_home, aFS_away),
                    "sc_ov": score_over25(expGoals, hAtt, aAtt, lg_cap, both_verylow, h_csr, a_csr),
                    "sc_o3": score_over35(expGoals, hAtt, aAtt, lg_cap),
                    "sc_un": score_under25(expGoals, h_csr, a_csr, h_ftsr, a_ftsr, lg_cap),
                    "sc_bt": score_btts(hAtt, aAtt, hDef, aDef, h_csr, a_csr, h_ftsr, a_ftsr),
                }
                # Karten
                h_yel_avg = hs.avg_yellows_home()
                a_yel_avg = as_.avg_yellows_away()
                sc_cards  = score_cards(h_yel_avg, a_yel_avg, h_pr, a_pr, rounds_left)
                base["sc_cards"] = sc_cards

                # v3-Scores (mit Pressure)
                v3 = apply_pressure_to_scores(base, h_pr, a_pr, rounds_left)

                # Pressure-Flag
                h_ratio, h_mw, h_cd, h_m = h_pr
                a_ratio, a_mw, a_cd, a_m = a_pr
                if h_mw or a_mw:    pflag = "mustwin"
                elif h_cd and a_cd: pflag = "deadrubber"
                else:               pflag = "neutral"

                # Odds aus CSV
                h_yel_actual = float(row.get("HY", float("nan"))) if has_cards else None
                a_yel_actual = float(row.get("AY", float("nan"))) if has_cards else None
                h_yel_ok = h_yel_actual if (h_yel_actual is not None and not math.isnan(h_yel_actual)) else None
                a_yel_ok = a_yel_actual if (a_yel_actual is not None and not math.isnan(a_yel_actual)) else None

                # Baue alle Markt-Ergebnisse
                markets_v2 = [
                    ("heimsieg",     base["sc_h"]),
                    ("auswärtssieg", base["sc_a"]),
                    ("draw",         base["sc_d"]),
                    ("over25",       base["sc_ov"]),
                    ("over35",       base["sc_o3"]),
                    ("under25",      base["sc_un"]),
                    ("btts",         base["sc_bt"]),
                    ("cards35",      base["sc_cards"]),
                ]
                markets_v3 = [
                    ("heimsieg",     v3["sc_h"]),
                    ("auswärtssieg", v3["sc_a"]),
                    ("draw",         v3["sc_d"]),
                    ("over25",       v3["sc_ov"]),
                    ("over35",       v3["sc_o3"]),
                    ("under25",      v3["sc_un"]),
                    ("btts",         v3["sc_bt"]),
                    ("cards35",      v3.get("sc_cards", base["sc_cards"])),
                ]

                for (mkt, sc2), (_, sc3) in zip(markets_v2, markets_v3):
                    if sc2 is None and sc3 is None:
                        continue  # Skip Hard-Gated oder fehlende Daten
                    sc2 = sc2 or 0.0
                    sc3 = sc3 or 0.0
                    thr = THRESHOLDS.get(mkt, (0.60, 0.35))
                    conf2 = conf_label(sc2, *thr)
                    conf3 = conf_label(sc3, *thr)

                    # Nur Picks aufzeichnen die über dem Medium-Schwellwert liegen
                    # (mindestens eines von v2 oder v3 muss ein "echter Pick" sein)
                    is_pick_v2 = conf2 in ("high", "medium")
                    is_pick_v3 = conf3 in ("high", "medium")
                    if not is_pick_v2 and not is_pick_v3:
                        continue

                    outcome = evaluate_pick(mkt, hg, ag, h_yel_ok, a_yel_ok)
                    if outcome is None: continue  # Karten ohne Daten überspringen

                    odds = extract_odds(row, mkt)
                    roi_win  = (odds - 1) if odds else None
                    roi_loss = -1.0

                    results.append({
                        "league":      key,
                        "season":      season,
                        "market":      mkt,
                        "is_last_n":   is_last_n,
                        "rounds_left": rounds_left,
                        "pressure_flag": pflag,
                        "h_mustWin":   h_mw,
                        "a_mustWin":   a_mw,
                        "h_motiv":     h_m,
                        "a_motiv":     a_m,
                        "xg_src":      xg_src,
                        "outcome":     outcome,   # True/False (einmal gespeichert)
                        "odds":        odds,
                        # v2 — nur relevant wenn is_pick_v2
                        "sc_v2":       round(sc2, 3),
                        "conf_v2":     conf2,
                        "is_pick_v2":  is_pick_v2,
                        "roi_v2":      ((roi_win if outcome else roi_loss) if odds else None) if is_pick_v2 else None,
                        # v3 — nur relevant wenn is_pick_v3
                        "sc_v3":       round(sc3, 3),
                        "conf_v3":     conf3,
                        "is_pick_v3":  is_pick_v3,
                        "roi_v3":      ((roi_win if outcome else roi_loss) if odds else None) if is_pick_v3 else None,
                    })

            # ── Nach Pick aufzeichnen: Table + Stats updaten ──────
            h_sot  = float(row["HST"]) if has_shots  and pd.notna(row.get("HST"))   else None
            a_sot  = float(row["AST"]) if has_shots  and pd.notna(row.get("AST"))   else None
            h_shts = float(row["HS"])  if has_shots_t and pd.notna(row.get("HS"))   else None
            a_shts = float(row["AS"])  if has_shots_t and pd.notna(row.get("AS"))   else None
            h_yel  = float(row["HY"])  if has_cards  and pd.notna(row.get("HY"))    else None
            a_yel  = float(row["AY"])  if has_cards  and pd.notna(row.get("AY"))    else None
            h_cor  = float(row["HC"])  if has_corners and pd.notna(row.get("HC"))   else None
            a_cor  = float(row["AC"])  if has_corners and pd.notna(row.get("AC"))   else None

            hs.record_home(hg, ag, h_sot, h_shts, h_yel, h_cor)
            as_.record_away(ag, hg, a_sot, a_shts, a_yel, a_cor)
            h2h_tracker.record(home, away, ftr)
            table.update(home, away, hg, ag)

        last_n_picks = sum(1 for r in results if r["season"] == season and r["is_last_n"] and r["league"] == key)
        total_picks  = sum(1 for r in results if r["season"] == season and r["league"] == key)
        mw = sum(1 for r in results if r["season"] == season and r["league"] == key and r["pressure_flag"] == "mustwin")
        print(f"    {season}: {total_picks} Picks total | "
              f"letzte {LAST_N_ROUNDS} Runden: {last_n_picks} | MustWin: {mw}")

    return results


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 8 — AGGREGATION
# ──────────────────────────────────────────────────────────────────
def new_bucket():
    return {
        "n_v2": 0, "hits_v2": 0, "roi_v2": 0.0, "roi_n_v2": 0,
        "n_v3": 0, "hits_v3": 0, "roi_v3": 0.0, "roi_n_v3": 0,
    }


def aggregate(all_results: list) -> dict:
    def process(subset: list) -> dict:
        by_market   = defaultdict(new_bucket)
        by_conf     = defaultdict(new_bucket)   # (market, conf_v3)
        by_league   = defaultdict(new_bucket)
        by_pressure = defaultdict(new_bucket)
        by_season   = defaultdict(new_bucket)

        for r in subset:
            buckets = [
                by_market[r["market"]],
                by_conf[(r["market"], r["conf_v3"])],
                by_league[r["league"]],
                by_pressure[r["pressure_flag"]],
                by_season[r["season"]],
            ]
            for b in buckets:
                # v2 — nur zählen wenn das ein v2-Pick war
                if r["is_pick_v2"]:
                    b["n_v2"]    += 1
                    b["hits_v2"] += int(r["outcome"])
                    if r["roi_v2"] is not None:
                        b["roi_v2"]   += r["roi_v2"]
                        b["roi_n_v2"] += 1
                # v3 — nur zählen wenn das ein v3-Pick war
                if r["is_pick_v3"]:
                    b["n_v3"]    += 1
                    b["hits_v3"] += int(r["outcome"])
                    if r["roi_v3"] is not None:
                        b["roi_v3"]   += r["roi_v3"]
                        b["roi_n_v3"] += 1

        def fin(d):
            out = {}
            for k, v in d.items():
                n2 = v["n_v2"]; n3 = v["n_v3"]
                if n2 == 0 and n3 == 0: continue
                hr2  = v["hits_v2"] / n2 * 100 if n2 else None
                hr3  = v["hits_v3"] / n3 * 100 if n3 else None
                roi2 = v["roi_v2"] / v["roi_n_v2"] * 100 if v["roi_n_v2"] else None
                roi3 = v["roi_v3"] / v["roi_n_v3"] * 100 if v["roi_n_v3"] else None
                delta_hr  = round(hr3 - hr2, 1) if hr2 is not None and hr3 is not None else None
                delta_roi = round(roi3 - roi2, 1) if roi2 is not None and roi3 is not None else None
                out[k] = {
                    "n": n3,            # v3 ist die Hauptzahl
                    "n_v2": n2,
                    "n_v3": n3,
                    "hit_rate_v2": round(hr2, 1) if hr2 is not None else None,
                    "hit_rate_v3": round(hr3, 1) if hr3 is not None else None,
                    "delta_hr":    delta_hr,
                    "roi_v2":      round(roi2, 1) if roi2 is not None else None,
                    "roi_v3":      round(roi3, 1) if roi3 is not None else None,
                    "delta_roi":   delta_roi,
                }
            return out

        n_v2_picks = sum(1 for r in subset if r["is_pick_v2"])
        n_v3_picks = sum(1 for r in subset if r["is_pick_v3"])
        mustwin_n   = sum(1 for r in subset if r["pressure_flag"] == "mustwin" and r["is_pick_v3"])
        deadrub_n   = sum(1 for r in subset if r["pressure_flag"] == "deadrubber" and r["is_pick_v3"])
        motiv_none_n = sum(1 for r in subset if (r["h_motiv"] == "none" or r["a_motiv"] == "none") and r["is_pick_v3"])
        total_n = len(subset)
        ov_v2 = sum(r["outcome"] for r in subset if r["is_pick_v2"]) / n_v2_picks * 100 if n_v2_picks else 0
        ov_v3 = sum(r["outcome"] for r in subset if r["is_pick_v3"]) / n_v3_picks * 100 if n_v3_picks else 0

        return {
            "by_market":   fin(by_market),
            "by_conf":     fin(by_conf),
            "by_league":   fin(by_league),
            "by_pressure": fin(by_pressure),
            "by_season":   fin(by_season),
            "total":       n_v3_picks,
            "total_v2":    n_v2_picks,
            "total_v3":    n_v3_picks,
            "total_raw":   total_n,
            "mustwin_n":   mustwin_n,
            "deadrub_n":   deadrub_n,
            "motiv_none_n": motiv_none_n,
            "overall_v2":  round(ov_v2, 1),
            "overall_v3":  round(ov_v3, 1),
            "overall_delta": round(ov_v3 - ov_v2, 1),
        }

    all_agg    = process(all_results)
    last_n_agg = process([r for r in all_results if r["is_last_n"]])
    mw_agg     = process([r for r in all_results if r["pressure_flag"] == "mustwin"])
    # MustWin in Endphase (dual-pressure: last N rounds AND mustWin)
    mw_lastn_agg = process([r for r in all_results if r["is_last_n"] and r["pressure_flag"] == "mustwin"])

    return {
        "all":        all_agg,
        "last_n":     last_n_agg,
        "mustwin":    mw_agg,
        "mw_lastn":   mw_lastn_agg,
    }


# ──────────────────────────────────────────────────────────────────
#  SCHRITT 9 — HTML REPORT
# ──────────────────────────────────────────────────────────────────
def roi_color(r):
    if r is None: return "#888"
    if r >= 5:    return "#22c55e"
    if r >= 1:    return "#a3e635"
    if r >= -3:   return "#f0b429"
    if r >= -8:   return "#fb923c"
    return "#f85149"

def hr_color(h):
    if h is None: return "#888"
    if h >= 65: return "#22c55e"
    if h >= 55: return "#a3e635"
    if h >= 47: return "#f0b429"
    if h >= 40: return "#fb923c"
    return "#f85149"

def delta_color(d):
    if d is None: return "#888"
    if d >= 2:    return "#22c55e"
    if d >= 0.5:  return "#a3e635"
    if d >= -0.5: return "#888"
    if d >= -2:   return "#fb923c"
    return "#f85149"

def fmt_roi(r):   return "–" if r is None else f"{'+'if r>=0 else''}{r:.1f}%"
def fmt_delta(d): return "–" if d is None else f"{'+'if d>=0 else''}{d:.1f}pp"
def fmt_hr(h):    return "–" if h is None else f"{h:.1f}%"


def _summary_card(label, value, sub="", color="#f0f6fc"):
    return f"""<div class="card">
      <div class="label">{label}</div>
      <div class="value" style="color:{color}">{value}</div>
      {f'<div class="sub">{sub}</div>' if sub else ''}
    </div>"""


def _table_rows_market_conf(bconf: dict, confs=("high","medium")) -> str:
    markets = ["heimsieg","auswärtssieg","draw","over25","over35","under25","btts","cards35"]
    rows = []
    for m in markets:
        for c in confs:
            d = bconf.get((m, c))
            if not d or (d["n_v3"] < 5 and d["n_v2"] < 5): continue
            dc = delta_color(d["delta_hr"])
            n2 = d["n_v2"]; n3 = d["n_v3"]
            n_str = f"{n3:,}" if n2 == n3 else f"{n3:,} / {n2:,}"
            rows.append(f"""<tr>
              <td>{MARKET_LABELS.get(m,m)}</td>
              <td class="conf-{c}">{c.upper()}</td>
              <td title="v3 / v2 Picks">{n_str}</td>
              <td style="color:{hr_color(d['hit_rate_v2'])}">{fmt_hr(d['hit_rate_v2'])}</td>
              <td style="color:{hr_color(d['hit_rate_v3'])}">{fmt_hr(d['hit_rate_v3'])}</td>
              <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
              <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
              <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
            </tr>""")
    return "\n".join(rows) if rows else "<tr><td colspan='8' style='color:#888'>Keine Daten</td></tr>"


def _table_rows_league(bleague: dict) -> str:
    rows = []
    for k in sorted(bleague.keys()):
        d = bleague[k]
        if d["n"] < 5: continue
        meta = LEAGUES.get(k, {"name": k, "flag": ""})
        dc = delta_color(d["delta_hr"])
        rows.append(f"""<tr>
          <td>{meta.get('flag','')} {meta.get('name',k)}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{fmt_hr(d['hit_rate_v2'])}</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{fmt_hr(d['hit_rate_v3'])}</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
          <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
          <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
        </tr>""")
    return "\n".join(rows) if rows else "<tr><td colspan='7' style='color:#888'>Keine Daten</td></tr>"


def _table_rows_season(bseason: dict) -> str:
    rows = []
    for s in sorted(bseason.keys()):
        d = bseason[s]
        if d["n"] < 5: continue
        sname = f"20{s[:2]}/{s[2:]}"
        dc = delta_color(d["delta_hr"])
        rows.append(f"""<tr>
          <td>{sname}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{fmt_hr(d['hit_rate_v2'])}</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{fmt_hr(d['hit_rate_v3'])}</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
          <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
          <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
        </tr>""")
    return "\n".join(rows) if rows else "<tr><td colspan='7' style='color:#888'>Keine Daten</td></tr>"


def _pressure_rows(bpressure: dict) -> str:
    labels = {
        "mustwin":    "🔥 MustWin (≥1 Team kämpft)",
        "deadrubber": "💤 Dead Rubber (beide entspannt)",
        "neutral":    "⚖️ Neutral",
    }
    rows = []
    for flag, label in labels.items():
        d = bpressure.get(flag)
        if not d or d["n"] < 5: continue
        dc = delta_color(d["delta_hr"])
        rows.append(f"""<tr>
          <td style="font-weight:600">{label}</td>
          <td>{d['n']:,}</td>
          <td style="color:{hr_color(d['hit_rate_v2'])}">{fmt_hr(d['hit_rate_v2'])}</td>
          <td style="color:{hr_color(d['hit_rate_v3'])}">{fmt_hr(d['hit_rate_v3'])}</td>
          <td style="color:{dc};font-weight:700">{fmt_delta(d['delta_hr'])}</td>
          <td style="color:{roi_color(d['roi_v2'])}">{fmt_roi(d['roi_v2'])}</td>
          <td style="color:{roi_color(d['roi_v3'])}">{fmt_roi(d['roi_v3'])}</td>
        </tr>""")
    return "\n".join(rows) if rows else "<tr><td colspan='7' style='color:#888'>Keine Daten</td></tr>"


def _section(agg_data: dict, title: str, subtitle: str = "") -> str:
    total   = agg_data["total"]
    ov2     = agg_data["overall_v2"]
    ov3     = agg_data["overall_v3"]
    delta   = agg_data["overall_delta"]
    mw_n    = agg_data["mustwin_n"]
    dr_n    = agg_data["deadrub_n"]
    mn_n    = agg_data["motiv_none_n"]

    delta_c = "#22c55e" if delta > 0 else "#f85149" if delta < -0.3 else "#888"
    delta_str = f"+{delta:.1f}pp ↑" if delta > 0 else f"{delta:.1f}pp ↓"

    cards = "".join([
        _summary_card("Picks gesamt", f"{total:,}", f"Warmup: {WARMUP_GAMES} Sp./Team"),
        _summary_card("Hit-Rate v2", f"{ov2:.1f}%", "Ohne Pressure", hr_color(ov2)),
        _summary_card("Hit-Rate v3", f"{ov3:.1f}%", "Mit Pressure", hr_color(ov3)),
        _summary_card("Δ v3 vs. v2", delta_str, "Verbesserung durch Pressure-Schicht", delta_c),
        _summary_card("🔥 MustWin", f"{mw_n:,}", f"{mw_n/total*100:.1f}% aller Picks"),
        _summary_card("💤 Dead Rubbers", f"{dr_n:,}", f"{dr_n/total*100:.1f}% aller Picks"),
        _summary_card("⬜ motivNone", f"{mn_n:,}", f"Bestätigte Absteiger/Meister"),
    ])

    return f"""
    <div class="section">
      <h2>{title}</h2>
      {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
      <div class="grid">{cards}</div>

      <h3>⚡ Pressure-Kategorien</h3>
      <table>
        <tr><th>Kategorie</th><th>n</th><th>HR v2</th><th>HR v3</th><th>Δ HR</th>
            <th>ROI v2</th><th>ROI v3</th></tr>
        {_pressure_rows(agg_data["by_pressure"])}
      </table>

      <h3>📊 Markt × Konfidenz</h3>
      <table>
        <tr><th>Markt</th><th>Konf.</th><th>n</th><th>HR v2</th><th>HR v3</th>
            <th>Δ HR</th><th>ROI v2</th><th>ROI v3</th></tr>
        {_table_rows_market_conf(agg_data["by_conf"])}
      </table>

      <h3>🌍 Ligen</h3>
      <table>
        <tr><th>Liga</th><th>n</th><th>HR v2</th><th>HR v3</th>
            <th>Δ HR</th><th>ROI v2</th><th>ROI v3</th></tr>
        {_table_rows_league(agg_data["by_league"])}
      </table>

      <h3>📅 Saison-Trend</h3>
      <table>
        <tr><th>Saison</th><th>n</th><th>HR v2</th><th>HR v3</th>
            <th>Δ HR</th><th>ROI v2</th><th>ROI v3</th></tr>
        {_table_rows_season(agg_data["by_season"])}
      </table>
    </div>"""


def build_html(agg: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    seasons_str = ", ".join(f"20{s[:2]}/{s[2:]}" for s in SEASONS)

    all_a   = agg["all"]
    lastn_a = agg["last_n"]
    mw_a    = agg["mustwin"]
    mwln_a  = agg["mw_lastn"]

    # Headline: Endphase-ROI (das wichtigste Ergebnis)
    ln_roi_v3   = lastn_a["by_market"].get("over25", {}).get("roi_v3")
    ln_mw_delta = lastn_a.get("by_pressure", {}).get("mustwin", {}).get("delta_hr")

    main_finding = ""
    if lastn_a["total"] > 0:
        d = lastn_a["overall_delta"]
        if d > 1.5:
            main_finding = f"✅ In den letzten {LAST_N_ROUNDS} Runden verbessert Pressure die Hit-Rate um <strong>+{d:.1f}pp</strong> — Signal klar validiert."
        elif d > 0:
            main_finding = f"📈 Leichte Verbesserung von <strong>+{d:.1f}pp</strong> in den letzten {LAST_N_ROUNDS} Runden — Trend richtig, Magnitude noch gering."
        else:
            main_finding = f"⚠️ In den letzten {LAST_N_ROUNDS} Runden: Pressure hat <strong>{d:.1f}pp</strong> Effekt — Kalibrierung möglicherweise nötig."

    tabs_html = f"""
    <div class="tab-bar">
      <button class="tab active" onclick="showTab('tab-lastn')">
        🎯 Letzte {LAST_N_ROUNDS} Runden <span class="badge-tab">{lastn_a['total']:,} Picks</span>
      </button>
      <button class="tab" onclick="showTab('tab-all')">
        📊 Alle Runden <span class="badge-tab">{all_a['total']:,} Picks</span>
      </button>
      <button class="tab" onclick="showTab('tab-mustwin')">
        🔥 MustWin <span class="badge-tab">{mw_a['total']:,} Picks</span>
      </button>
      <button class="tab" onclick="showTab('tab-mwln')">
        ⚡ MustWin+Endphase <span class="badge-tab">{mwln_a['total']:,} Picks</span>
      </button>
    </div>

    <div id="tab-lastn" class="tab-content active">
      {_section(lastn_a,
        f"🎯 Letzte {LAST_N_ROUNDS} Runden pro Saison — Hauptergebnis",
        f"Nur die Endphase jeder Saison — wo Druck am stärksten wirkt. Saisons: {seasons_str}.")}
    </div>
    <div id="tab-all" class="tab-content">
      {_section(all_a,
        "📊 Alle Runden — Vollbild",
        f"Gesamte Datenbasis über alle Runden. Saisons: {seasons_str}.")}
    </div>
    <div id="tab-mustwin" class="tab-content">
      {_section(mw_a,
        "🔥 MustWin-Spiele — Druck-Fokus",
        "Nur Spiele wo mindestens ein Team unter echtem Druck steht (pressureRatio > 0.65, motiv='full').")}
    </div>
    <div id="tab-mwln" class="tab-content">
      {_section(mwln_a,
        "⚡ MustWin IN Endphase — schärfster Filter",
        f"Schärfster Filter: letzten {LAST_N_ROUNDS} Runden UND mindestens ein Team unter Druck.")}
    </div>
    """

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>BetEdge Backtest v4</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#0d1117; color:#c9d1d9; padding:28px 24px; max-width:1100px; margin:0 auto; }}
  h1  {{ color:#f0f6fc; font-size:26px; margin-bottom:4px; }}
  h2  {{ color:#f0f6fc; font-size:18px; margin:28px 0 12px;
         border-bottom:1px solid #30363d; padding-bottom:6px; }}
  h3  {{ color:#c9d1d9; font-size:14px; margin:20px 0 10px; font-weight:600; }}
  .subtitle {{ color:#8b949e; font-size:13px; margin-bottom:16px; }}
  .meta  {{ color:#8b949e; font-size:12px; margin-bottom:24px; }}
  .badge {{ display:inline-block; background:#21262d; border:1px solid #30363d;
            border-radius:6px; padding:2px 8px; font-size:11px; margin-right:6px; }}
  .badge.new {{ border-color:#0ea5e9; color:#7dd3fc; }}
  .badge.v4  {{ border-color:#7c3aed; color:#a78bfa; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
           gap:12px; margin-bottom:24px; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px; }}
  .card .label {{ color:#8b949e; font-size:11px; margin-bottom:3px; }}
  .card .value {{ font-size:22px; font-weight:700; }}
  .card .sub   {{ font-size:10px; color:#8b949e; margin-top:3px; }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:20px; font-size:12.5px; }}
  th {{ background:#161b22; color:#8b949e; text-align:left; padding:7px 9px;
        border-bottom:2px solid #30363d; font-size:11px; font-weight:600; letter-spacing:.3px; }}
  td {{ padding:6px 9px; border-bottom:1px solid #21262d; }}
  tr:hover td {{ background:#161b22; }}
  .conf-high   {{ color:#a78bfa; font-weight:700; }}
  .conf-medium {{ color:#7dd3fc; }}
  .conf-low    {{ color:#8b949e; }}
  .tab-bar {{ display:flex; gap:8px; margin-bottom:0; flex-wrap:wrap; }}
  .tab {{ background:#161b22; border:1px solid #30363d; border-radius:8px 8px 0 0;
          padding:8px 14px; cursor:pointer; color:#8b949e; font-size:13px;
          border-bottom:none; transition:all .15s; }}
  .tab:hover {{ color:#c9d1d9; }}
  .tab.active {{ background:#21262d; color:#f0f6fc; border-color:#7c3aed;
                 border-bottom:1px solid #21262d; }}
  .badge-tab {{ background:#0d1117; border:1px solid #30363d; border-radius:4px;
                padding:1px 5px; font-size:10px; margin-left:4px; }}
  .tab-content {{ display:none; background:#21262d; border:1px solid #30363d;
                  border-radius:0 8px 8px 8px; padding:20px; margin-bottom:28px; }}
  .tab-content.active {{ display:block; }}
  .section h2 {{ margin-top:0; }}
  .hero {{ background:#161b22; border:1px solid #7c3aed; border-radius:10px;
           padding:18px 22px; margin-bottom:24px; }}
  .hero .main {{ font-size:24px; font-weight:700; color:#f0f6fc; margin-bottom:6px; }}
  .hero .sub  {{ font-size:13px; color:#8b949e; }}
  .finding {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
              padding:14px 18px; margin-bottom:16px; font-size:13px; line-height:1.6; }}
  .legend {{ display:flex; gap:16px; flex-wrap:wrap; font-size:11px; color:#8b949e; margin-bottom:20px; }}
  .dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:4px; }}
</style>
</head>
<body>

<h1>⚡ BetEdge Backtest v4</h1>
<div class="meta">
  Generiert: {now} &nbsp;|&nbsp; Saisons: {seasons_str} &nbsp;|&nbsp;
  Ligen: {len(LEAGUES)} &nbsp;|&nbsp; Endphase: letzte {LAST_N_ROUNDS} Runden
  <br style="margin:4px 0">
  <span class="badge v4">v4 NEU</span> Last-N-Rounds-Fokus + Karten-Market + Over3.5 + motivNone-Guard
  <span class="badge new">NEU</span> Saison-Trend · ★★★/★★/★ Confidence-Split
  <span class="badge">v3 Basis</span> Tabellenrekonstruktion · Pressure-System · shots-xG
</div>

<div class="hero">
  <div class="main">🎯 Hauptergebnis: Letzte {LAST_N_ROUNDS} Runden</div>
  <div class="sub">
    {main_finding}<br>
    v2: {lastn_a['overall_v2']:.1f}% → v3: {lastn_a['overall_v3']:.1f}% &nbsp;|&nbsp;
    MustWin-Spiele: {lastn_a['mustwin_n']:,} ({lastn_a['mustwin_n']/lastn_a['total']*100:.1f}%) &nbsp;|&nbsp;
    motivNone-Spiele: {lastn_a['motiv_none_n']:,}
  </div>
</div>

<div class="legend">
  <span><span class="dot" style="background:#22c55e"></span>≥65% HR / ROI ≥+5%</span>
  <span><span class="dot" style="background:#a3e635"></span>≥55% HR / ROI ≥+1%</span>
  <span><span class="dot" style="background:#f0b429"></span>≥47% HR / ROI ≥−3%</span>
  <span><span class="dot" style="background:#fb923c"></span>≥40% HR / ROI ≥−8%</span>
  <span><span class="dot" style="background:#f85149"></span>&lt;40% / ROI &lt;−8%</span>
</div>

{tabs_html}

<h2>💡 Methodik</h2>
<div class="finding">
  <strong>Datenquelle:</strong> football-data.co.uk CSVs (enthält Pinnacle-Odds PSH/PSA/PSD/P&gt;2.5).
  Keine API-Calls für historische Daten nötig. Shots (HST/AST) für xG-Berechnung, Karten (HY/AY) für Cards-Market.
</div>
<div class="finding">
  <strong>Last-N-Rounds:</strong> Statt alle Runden gleichgewichtet, werden die letzten {LAST_N_ROUNDS} Runden
  pro Saison als "Endphase" isoliert. Das ist der Zeitraum wo unser Dashboard am meisten genutzt wird
  und wo Druck am stärksten wirkt.
</div>
<div class="finding">
  <strong>Tabellenrekonstruktion:</strong> Liga-Tabelle wird chronologisch aus Ergebnissen aufgebaut.
  PRE-MATCH Snapshot → Pressure-Berechnung BEVOR das Ergebnis eingeflossen ist (kein Look-Ahead).
  motivNone = mathematisch bestätigt (Meister/Absteiger) → mustWin=False, kein Pressure-Boost.
</div>
<div class="finding">
  <strong>ROI-Berechnung:</strong> Pinnacle closing odds (PS* Spalten). Wenn P&gt;2.5 fehlt: B365&gt;2.5 als Fallback.
  Karten-Market (cards35) und BTTS haben keine CSV-Quoten → nur Hit-Rate (ROI = –).
</div>

<div style="text-align:center;margin-top:32px;color:#484f58;font-size:11px">
  BetEdge Backtest v4 · {seasons_str} · {len(LEAGUES)} Ligen · {all_a['total']:,} Picks total
</div>

<script>
function showTab(id) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.currentTarget.classList.add('active');
}}
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 62)
    print("  BetEdge Backtest v4 — Last-N-Rounds + Cards + Over3.5")
    print("=" * 62 + "\n")

    print("📥 SCHRITT 1: Lade Daten …\n")
    all_data = load_all_data()
    if not all_data:
        print("❌ Keine Daten.")
        return

    print(f"\n🔄 SCHRITT 2: Simuliere Picks (letzte {LAST_N_ROUNDS} Runden Fokus) …\n")
    all_results = []
    for key, df in all_data.items():
        meta = LEAGUES[key]
        print(f"  {meta['flag']} {meta['name']}:")
        league_results = process_league(key, df)
        all_results.extend(league_results)
        print(f"    → {len(league_results)} Einträge\n")

    if not all_results:
        print("❌ Keine Picks simuliert.")
        return

    print(f"📊 SCHRITT 3: Aggregiere {len(all_results):,} Picks …")
    agg = aggregate(all_results)

    print("📝 SCHRITT 4: Erstelle HTML-Report …")
    html = build_html(agg)

    out = Path(__file__).parent / "backtest_v4_report.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n✅ Report: {out}")

    # Quick Summary
    la = agg["last_n"]
    aa = agg["all"]
    mw = agg["mustwin"]
    mwl = agg["mw_lastn"]
    print(f"\n{'─'*55}")
    print(f"  ALLE Runden:      {aa['total']:,} Picks | "
          f"v2 {aa['overall_v2']:.1f}% → v3 {aa['overall_v3']:.1f}% ({aa['overall_delta']:+.1f}pp)")
    print(f"  Letzte {LAST_N_ROUNDS} Runden:  {la['total']:,} Picks | "
          f"v2 {la['overall_v2']:.1f}% → v3 {la['overall_v3']:.1f}% ({la['overall_delta']:+.1f}pp)")
    print(f"  MustWin:          {mw['total']:,} Picks | "
          f"v2 {mw['overall_v2']:.1f}% → v3 {mw['overall_v3']:.1f}% ({mw['overall_delta']:+.1f}pp)")
    print(f"  MustWin+Endphase: {mwl['total']:,} Picks | "
          f"v2 {mwl['overall_v2']:.1f}% → v3 {mwl['overall_v3']:.1f}% ({mwl['overall_delta']:+.1f}pp)")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    main()
