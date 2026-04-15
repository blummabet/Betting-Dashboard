#!/usr/bin/env python3
"""
BetEdge Dashboard — Auto-Update Script
Fetches live standings + fixtures from Sofascore and updates season-finish.html
"""

import urllib.request
import urllib.error
import json
import re
import os
import sys
import time
import http.client
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(SCRIPT_DIR, "season-finish.html")

LEAGUES = {
    "ENG": dict(tid=17,  apif_id=39,  name="Premier League",  flag="🏴󠁧󠁢󠁥󠁮󠁧󠁿", total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "GER": dict(tid=35,  apif_id=78,  name="Bundesliga",       flag="🇩🇪",         total=18, rounds=34, ucl=4, el=2, uecl=1, rel_playoff=1, rel=2),
    "ITA": dict(tid=23,  apif_id=135, name="Serie A",          flag="🇮🇹",         total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "ESP": dict(tid=8,   apif_id=140, name="La Liga",          flag="🇪🇸",         total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "FRA": dict(tid=34,  apif_id=61,  name="Ligue 1",          flag="🇫🇷",         total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "AUT": dict(tid=45,  apif_id=218, name="Österreich BL",    flag="🇦🇹",         total=12, rounds=32, ucl=2, el=1, uecl=0, rel_playoff=1, rel=2),
    "NED": dict(tid=37,  apif_id=88,  name="Eredivisie",       flag="🇳🇱",         total=18, rounds=34, ucl=2, el=2, uecl=0, rel_playoff=2, rel=1),
    "POR": dict(tid=238, apif_id=94,  name="Primeira Liga",    flag="🇵🇹",         total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "SCO": dict(tid=36,  apif_id=179, name="Scottish Prem",    flag="🏴󠁧󠁢󠁳󠁣󠁴󠁿", total=12, rounds=38, ucl=2, el=2, uecl=0, rel_playoff=1, rel=1),
    "TUR": dict(tid=52,  apif_id=203, name="Süper Lig",        flag="🇹🇷",         total=19, rounds=38, ucl=2, el=2, uecl=1, rel_playoff=0, rel=3),
    "SUI": dict(tid=57,  apif_id=207, name="Swiss SL",         flag="🇨🇭",         total=10, rounds=36, ucl=1, el=1, uecl=0, rel_playoff=1, rel=1),
    # ── Neue Ligen (Saison-Ende April/Mai) ──────────────────────────────────
    # BEL: 30 Runden Grunddurchgang + 10 Championship-Playoff-Runden für Top 6 → rounds=40
    "BEL": dict(tid=0,   apif_id=144, name="Jupiler Pro League", flag="🇧🇪",       total=16, rounds=40, ucl=2, el=1, uecl=1, rel_playoff=3, rel=1),
    "POL": dict(tid=0,   apif_id=106, name="Ekstraklasa",        flag="🇵🇱",       total=18, rounds=34, ucl=1, el=1, uecl=1, rel_playoff=2, rel=2),
    "HUN": dict(tid=0,   apif_id=271, name="NB I",               flag="🇭🇺",       total=12, rounds=33, ucl=1, el=1, uecl=1, rel_playoff=0, rel=2),
    "CRO": dict(tid=0,   apif_id=210, name="HNL",                flag="🇭🇷",       total=10, rounds=36, ucl=1, el=1, uecl=1, rel_playoff=1, rel=1),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "x-requested-with": "XMLHttpRequest",
}

# ── API-Football ─────────────────────────────────────────────────────────────

APIF_HOST = "v3.football.api-sports.io"
APIF_KEY  = os.environ.get("APISPORTS_KEY", "")
APIF_DELAY = 1.2  # seconds between calls (Pro plan rate limit)

def apif_get(endpoint, params):
    """Fetch from API-Football with rate limiting."""
    if not APIF_KEY:
        print("  ⚠ APISPORTS_KEY not set")
        return []
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path = f"/{endpoint}?{query}"
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=15)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        errors = data.get("errors", {})
        if isinstance(errors, dict) and errors:
            print(f"  ⚠ API-Football error on /{endpoint}: {errors}")
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ⚠ apif_get /{endpoint} error: {e}")
        return []
    finally:
        time.sleep(APIF_DELAY)

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch(url, silent_404=False):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if not (silent_404 and e.code == 404):
            print(f"  ⚠ Fetch error {url}: {e}")
        return None
    except Exception as e:
        print(f"  ⚠ Fetch error {url}: {e}")
        return None

def norm(name):
    n = name.lower()
    for prefix in ["fc ", "sv ", "sc ", "ac ", "rb ", "vfb ", "vfl ", "bsc ", "tsv ", "sk ", "as ", "ss "]:
        n = n.replace(prefix, " ")
    return re.sub(r"[^a-z0-9 ]", " ", n).strip()

def fmt_date(ts):
    d = datetime.fromtimestamp(ts)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"

def fmt_date_from_iso(iso_str):
    """Convert YYYY-MM-DD to DD.MM.YYYY"""
    if not iso_str or len(iso_str) < 10:
        return iso_str
    y, m, d = iso_str[:10].split("-")
    return f"{d}.{m}.{y}"

def fmt_time(ts):
    d = datetime.fromtimestamp(ts)
    return f"{d.hour:02d}:{d.minute:02d}"

def within_7_days(date_str):
    try:
        d, m, y = date_str.split(".")
        dt = datetime(int(y), int(m), int(d))
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return today <= dt <= today + timedelta(days=7)
    except:
        return False

def german_date(dt=None):
    if dt is None:
        dt = datetime.now()
    months = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
    return f"{dt.day}. {months[dt.month-1]} {dt.year}"

# ── Historical data ───────────────────────────────────────────────────────────

def fetch_team_form(team_id, season=2025):
    """Fetch last 10 finished games → form string + metrics (API-Football)."""
    resp = apif_get("fixtures", {"team": team_id, "season": season, "last": 10})
    if not resp:
        # Try season fallback
        resp = apif_get("fixtures", {"team": team_id, "season": season + 1, "last": 10})
    if not resp:
        return None

    finished = [fx for fx in resp
                if fx.get("fixture", {}).get("status", {}).get("short") in
                   ("FT", "AET", "PEN", "AWD", "WO")]
    finished.sort(key=lambda fx: fx["fixture"].get("timestamp", 0))

    results, gf_list, ga_list = [], [], []
    for fx in finished:
        is_home = fx["teams"]["home"]["id"] == team_id
        gf = (fx["goals"]["home"] if is_home else fx["goals"]["away"]) or 0
        ga = (fx["goals"]["away"] if is_home else fx["goals"]["home"]) or 0
        gf_list.append(gf)
        ga_list.append(ga)
        results.append("W" if gf > ga else ("D" if gf == ga else "L"))

    results = results[-6:]
    if not results:
        return None

    # Streak (same as original logic)
    streak = 1
    for i in range(len(results) - 2, -1, -1):
        if results[i] == results[-1]:
            streak += 1
        else:
            break
    if results[-1] == "L":   streak = -streak
    elif results[-1] == "D": streak = 0

    pts     = sum(3 if r == "W" else (1 if r == "D" else 0) for r in results)
    max_pts = len(results) * 3

    return {
        "form":            "".join(results),
        "formScore":       round(pts / max_pts, 2) if max_pts else 0.5,
        "streak":          streak,
        "goalsPerGame":    round(sum(gf_list[-6:]) / len(gf_list[-6:]), 1) if gf_list else 0.0,
        "concededPerGame": round(sum(ga_list[-6:]) / len(ga_list[-6:]), 1) if ga_list else 0.0,
    }


def fetch_team_injuries(team_id):
    """Fetch current injury/suspension list for a team from SofaScore.
    Tries multiple known endpoint variants (SofaScore API changes frequently).
    Returns dict with attack/defense counts and player notes, or None if unavailable.
    Note: only long-term absences are available; match-day decisions are not.
    """
    now_ts = datetime.now().timestamp()

    # Try known SofaScore injury endpoints (silent 404 — expected when endpoint unavailable)
    candidates = [
        f"https://api.sofascore.com/api/v1/team/{team_id}/injuries",
        f"https://api.sofascore.com/api/v1/team/{team_id}/players/missing",
    ]
    raw_injuries = None
    for url in candidates:
        data = fetch(url, silent_404=True)
        if data:
            # Normalise: endpoint may return {"injuries":[...]} or {"missingPlayers":[...]}
            raw_injuries = data.get("injuries") or data.get("missingPlayers") or []
            if raw_injuries:
                break

    if not raw_injuries:
        return None

    attack_count, defense_count = 0, 0
    notes = []

    for inj in raw_injuries:
        player   = inj.get("player") or {}
        pos      = player.get("position", "")          # F / M / D / G
        name     = player.get("name", "?")
        inj_info = (inj.get("playerTeamInjury") or inj.get("injury") or {})
        ret_ts   = inj_info.get("returnTimestamp") or inj_info.get("returnDate")

        # Skip already-recovered players
        if ret_ts and isinstance(ret_ts, (int, float)) and ret_ts < now_ts:
            continue

        if pos in ("F", "M"):
            attack_count += 1
        elif pos in ("D", "G"):
            defense_count += 1
        else:
            continue

        if ret_ts and isinstance(ret_ts, (int, float)):
            weeks_left = max(0, int((ret_ts - now_ts) / 604800))
            suffix = "bald zurück" if weeks_left == 0 else f"ca. {weeks_left} Wo."
        else:
            suffix = "unbekannte Dauer"
        notes.append(f"{name} ({suffix})")

    if attack_count == 0 and defense_count == 0:
        return None

    return {
        "attack":  attack_count,
        "defense": defense_count,
        "notes":   notes[:4],
    }


def fetch_h2h(home_id, away_id):
    """Fetch H2H stats using API-Football headtohead endpoint."""
    resp = apif_get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": 10})
    if not resp:
        return None

    home_wins, away_wins, draws = 0, 0, 0
    total_goals = []
    last_year = None

    for fx in resp:
        status = fx.get("fixture", {}).get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN"):
            continue
        h_id  = fx["teams"]["home"]["id"]
        h_win = fx["teams"]["home"].get("winner")
        a_win = fx["teams"]["away"].get("winner")
        # perspective: home_id is "home" team in our fixture
        if h_id == home_id:
            if h_win:   home_wins += 1
            elif a_win: away_wins += 1
            else:       draws += 1
        else:
            if a_win:   home_wins += 1
            elif h_win: away_wins += 1
            else:       draws += 1

        gh = fx["goals"]["home"] or 0
        ga = fx["goals"]["away"] or 0
        total_goals.append(gh + ga)

        ts = fx["fixture"].get("timestamp", 0)
        if ts:
            year = datetime.fromtimestamp(ts).year
            if last_year is None or year > last_year:
                last_year = year

    n = home_wins + away_wins + draws
    if n == 0:
        return None

    return {
        "games":           n,
        "homeWins":        home_wins,
        "draws":           draws,
        "awayWins":        away_wins,
        "avgGoals":        round(sum(total_goals) / n, 2) if total_goals else 2.5,
        "lastMeetingYear": last_year,
    }


def form_score_mod(form_data, is_red):
    """Return score modifier based on form. Range: -1.5 to +2.0"""
    if not form_data:
        return 0.0
    fs     = form_data.get("formScore", 0.5)
    streak = form_data.get("streak", 0)

    if is_red:
        # In danger zone: losing streak → panic → higher score
        if   streak <= -4: return  2.0
        elif streak <= -2: return  1.0
        elif fs < 0.25:    return  1.5
        elif streak >= 4:  return -1.0   # winning streak = breathing room
        elif streak >= 2:  return -0.5
        elif fs > 0.72:    return -0.5
        return 0.0
    else:
        # Title/UCL zone: form signals confidence but doesn't add pressure
        if   streak >= 5: return  0.5
        elif streak >= 3: return  0.3
        elif streak <= -4: return -0.5
        elif streak <= -2: return -0.3
        return 0.0


# ── Stakes calculation ────────────────────────────────────────────────────────

def pts_at_pos(standings, pos):
    for t in standings:
        if t["pos"] == pos:
            return t["pts"]
    return 0

def get_team_ppg(standings, pos):
    """Current points-per-game for the team at position `pos`."""
    for t in standings:
        if t["pos"] == pos:
            played = max(1, t.get("played", 1))
            return t["pts"] / played
    return 1.2  # conservative league-average fallback

def get_team_gd(standings, pos):
    """Goal difference for the team at position `pos`."""
    for t in standings:
        if t["pos"] == pos:
            return t.get("gd", 0)
    return 0

def comp_gain_est(standings, pos, rounds_left):
    """
    Estimate how many more points the team at `pos` will earn in the
    remaining rounds, based on their current PPG (clamped 0.8–2.4).
    This is used to project where a competitor will likely end up,
    rather than treating their current points as a frozen target.
    """
    ppg = max(0.8, min(2.4, get_team_ppg(standings, pos)))
    return round(rounds_left * ppg)

def calc_labels(team, standings, cfg):
    pos   = team["pos"]
    pts   = team["pts"]
    played = team["played"]
    rounds_left = max(0, cfg["rounds"] - played)
    labels = []

    leader_pts = pts_at_pos(standings, 1)
    gap_leader = leader_pts - pts

    # Title
    if pos == 1:
        labels.append({"l": "🏆 Titelkampf", "c": "gold"})
    elif pos <= 3 and gap_leader <= 6:
        labels.append({"l": "🏆 Titelchance", "c": "gold"})

    # UCL
    ucl = cfg["ucl"]
    pts_ucl = pts_at_pos(standings, ucl)
    pts_below_ucl = pts_at_pos(standings, ucl + 1)
    if pos <= ucl and (pts - pts_below_ucl) <= 3:
        labels.append({"l": "🔵 UCL sichern", "c": "blue"})
    elif pos > ucl and (pts_ucl - pts) <= 4:
        labels.append({"l": "🔵 UCL Jagd", "c": "blue"})

    # Europa League
    el = cfg["el"]
    if el > 0:
        el_cutoff = ucl + el
        pts_el = pts_at_pos(standings, el_cutoff)
        if ucl < pos <= el_cutoff and abs(pts - pts_el) <= 3:
            labels.append({"l": "🟠 EL sichern", "c": "orange"})
        elif pos > el_cutoff and (pts_el - pts) <= 3:
            labels.append({"l": "🟠 EL Jagd", "c": "orange"})

    # Relegation
    total      = cfg["total"]
    rel        = cfg["rel"]
    rel_ply    = cfg["rel_playoff"]
    rel_start  = total - rel + 1           # first relegated position
    ply_pos    = rel_start - rel_ply       # playoff position(s)
    safe_pos   = ply_pos - 1              # last fully safe position
    pts_safe   = pts_at_pos(standings, safe_pos) if safe_pos > 0 else 999

    if pos >= rel_start:
        labels.append({"l": "🔴 Abstieg", "c": "red"})
    elif rel_ply > 0 and ply_pos <= pos < rel_start:
        labels.append({"l": "🟡 Rel.-Playoff", "c": "yellow"})
        labels.append({"l": "🔴 Abstiegsgefahr", "c": "red"})
    elif (pts_safe - pts) <= 6 and pos >= safe_pos - 2:
        labels.append({"l": "🔴 Abstiegsgefahr", "c": "red"})

    return labels

def calc_motivation(team, labels, standings, cfg, rounds_left):
    """
    Computes motivationLevel for a team based on whether their season
    outcome is already mathematically confirmed or practically decided.

    'none'  – position confirmed (mathematically impossible to change outcome).
              Expect rotation, lower intensity — treat like a mid-table team for xG.
    'low'   – outcome practically decided: even accounting for the competitor's
              projected gains (at their current PPG), the gap is so large that
              a reversal would require a genuine miracle (need >75% of remaining
              points just to match where the competitor will likely end up).
    'full'  – actively fighting (default for all stake teams).

    Key change from naive version: 'low' now uses competitor-adjusted effective
    gaps rather than just the raw static point gap. This prevents falsely flagging
    a team as "nearly done" when the competitor they need to catch is also still
    playing and likely to keep earning points.
    """
    if not labels:
        return 'full'

    pos      = team["pos"]
    pts      = team["pts"]
    max_gain = rounds_left * 3   # maximum additional points any single team can earn

    is_gold   = any(l["c"] == "gold"   for l in labels)
    is_red    = any(l["c"] == "red"    for l in labels)
    is_blue   = any(l["c"] == "blue"   for l in labels)
    is_orange = any(l["c"] == "orange" for l in labels)

    # ── Title secured ──────────────────────────────────────────────────────────
    if is_gold and pos == 1:
        pts_2nd = pts_at_pos(standings, 2)
        gap     = pts - pts_2nd
        # 'none': even if 2nd wins ALL remaining games and we win 0, they can't catch us
        if gap > max_gain:  return 'none'
        # 'low': accounting for 2nd's realistic gain, our adjusted lead is > 15% of max_gain
        # i.e., even if they run at their average PPG, we'd still be comfortably ahead
        cg = comp_gain_est(standings, 2, rounds_left)
        if (gap - cg) > max_gain * 0.15:  return 'low'

    # ── UCL secured ────────────────────────────────────────────────────────────
    if is_blue and pos <= cfg["ucl"]:
        pts_below = pts_at_pos(standings, cfg["ucl"] + 1)
        gap       = pts - pts_below
        if gap > max_gain:  return 'none'
        cg = comp_gain_est(standings, cfg["ucl"] + 1, rounds_left)
        if (gap - cg) > max_gain * 0.15:  return 'low'

    # ── Europa League secured ──────────────────────────────────────────────────
    if is_orange:
        el_cutoff = cfg["ucl"] + cfg["el"]
        if pos <= el_cutoff:
            pts_below = pts_at_pos(standings, el_cutoff + 1)
            gap       = pts - pts_below
            if gap > max_gain:  return 'none'
            cg = comp_gain_est(standings, el_cutoff + 1, rounds_left)
            if (gap - cg) > max_gain * 0.15:  return 'low'

    # ── Mathematically relegated / practically doomed ─────────────────────────
    if is_red:
        total     = cfg["total"]
        rel       = cfg["rel"]
        rel_ply   = cfg["rel_playoff"]
        rel_start = total - rel + 1
        safe_pos  = rel_start - rel_ply - 1
        if safe_pos > 0:
            pts_safe      = pts_at_pos(standings, safe_pos)
            gap_to_safety = pts_safe - pts
            # 'none': we win everything, safe team wins nothing — still can't escape
            if gap_to_safety > max_gain:  return 'none'
            # 'low': competitor-adjusted — need >75% of max_gain just to match where
            # the safe team will likely end up at their current PPG
            cg = comp_gain_est(standings, safe_pos, rounds_left)
            if (gap_to_safety + cg) > max_gain * 0.75:  return 'low'

    return 'full'

def calc_pressure(team, labels, standings, cfg, rounds_left):
    """
    Computes concrete pressure metrics: how many points does this team
    actually need, and how desperate is their situation?

    Key improvements vs. naive gap calculation:
    - Competitor-aware: projects where the boundary team will END UP (using their
      current PPG), not just where they sit now. A team 3pts behind safety with 5
      rounds left looks fine on a static snapshot, but if the safe team averages
      1.5 PPG they'll likely gain ~8 more pts — making the real gap 11, not 3.
    - GD tiebreaker: when teams are level on points the team with better goal
      difference sits higher. A team that draws level but has inferior GD is still
      effectively behind — so we add 1pt to their required total.

    Returns dict with:
      pointsNeeded  – competitor-adjusted points required (0 = already secured)
      pressureRatio – pointsNeeded / max_gainable, 0.0–1.0
      mustWin       – True when team needs >65% of remaining points
      canDraw       – True when team needs <30% (draws acceptable)
    """
    if not labels:
        return {"pointsNeeded": 0, "pressureRatio": 0.0, "mustWin": False, "canDraw": True}

    pts      = team["pts"]
    team_gd  = team.get("gd", 0)
    max_gain = rounds_left * 3
    if max_gain == 0:
        return {"pointsNeeded": 0, "pressureRatio": 0.0, "mustWin": False, "canDraw": True}

    is_gold   = any(l["c"] == "gold"   for l in labels)
    is_red    = any(l["c"] == "red"    for l in labels)
    is_blue   = any(l["c"] == "blue"   for l in labels)
    is_orange = any(l["c"] == "orange" for l in labels)

    points_needed = 0

    if is_red:
        # ── Relegated / relegation danger: need to climb above safe position ──
        total     = cfg["total"]
        rel       = cfg["rel"]
        rel_ply   = cfg["rel_playoff"]
        rel_start = total - rel + 1
        safe_pos  = rel_start - rel_ply - 1
        if safe_pos > 0:
            pts_safe      = pts_at_pos(standings, safe_pos)
            gap_to_safety = pts_safe - pts
            # ── Confirmed relegated: cannot mathematically escape — zero pressure ──
            # Even winning every remaining game can't close the gap. motivationLevel
            # will be 'none'; mustWin must also be False so match score stays low.
            if gap_to_safety > max_gain:
                return {"pointsNeeded": 0, "pressureRatio": 0.0, "mustWin": False, "canDraw": True}
            safe_gd   = get_team_gd(standings, safe_pos)
            cg        = comp_gain_est(standings, safe_pos, rounds_left)
            # GD penalty: level on pts but inferior GD → still ranked below → +1
            gd_pen    = 1 if (pts >= pts_safe and team_gd < safe_gd) else 0
            # Competitor-adjusted target: where safe team will likely end up
            points_needed = max(0, (pts_safe + cg) - pts + 1 + gd_pen)
        else:
            points_needed = max_gain

    elif is_gold:
        pos = team["pos"]
        if pos == 1:
            # ── Title defender: keep at least 1pt ahead of 2nd's projected total ──
            pts_2nd   = pts_at_pos(standings, 2)
            second_gd = get_team_gd(standings, 2)
            cg        = comp_gain_est(standings, 2, rounds_left)
            gap       = pts - pts_2nd
            # GD penalty: 1pt lead but inferior GD → if they draw level, they pass us
            gd_pen    = 1 if (gap <= 1 and team_gd < second_gd) else 0
            # Need: our_pts + X  >=  pts_2nd + cg + 1  →  X >= cg - gap + 1
            points_needed = max(0, cg - gap + 1 + gd_pen)
        else:
            # ── Title chaser: need to exceed leader's projected final total ──
            pts_leader = pts_at_pos(standings, 1)
            leader_gd  = get_team_gd(standings, 1)
            cg         = comp_gain_est(standings, 1, rounds_left)
            gap_now    = pts_leader - pts
            gd_pen     = 1 if (gap_now <= 0 and team_gd < leader_gd) else 0
            points_needed = max(0, (pts_leader + cg) - pts + 1 + gd_pen)

    elif is_blue:
        ucl = cfg["ucl"]
        pos = team["pos"]
        if pos <= ucl:
            # ── UCL defender: stay ahead of the chaser's projected total ──
            pts_below  = pts_at_pos(standings, ucl + 1)
            below_gd   = get_team_gd(standings, ucl + 1)
            cg         = comp_gain_est(standings, ucl + 1, rounds_left)
            gap        = pts - pts_below
            gd_pen     = 1 if (gap <= 1 and team_gd < below_gd) else 0
            points_needed = max(0, cg - gap + 1 + gd_pen)
        else:
            # ── UCL chaser: exceed the current UCL team's projected total ──
            pts_ucl   = pts_at_pos(standings, ucl)
            ucl_gd    = get_team_gd(standings, ucl)
            cg        = comp_gain_est(standings, ucl, rounds_left)
            gap_now   = pts_ucl - pts
            gd_pen    = 1 if (gap_now <= 0 and team_gd < ucl_gd) else 0
            points_needed = max(0, (pts_ucl + cg) - pts + 1 + gd_pen)

    elif is_orange:
        ucl       = cfg["ucl"]
        el        = cfg.get("el", 0)
        el_cutoff = ucl + el
        pos       = team["pos"]
        if pos <= el_cutoff:
            # ── EL defender ──
            pts_below  = pts_at_pos(standings, el_cutoff + 1)
            below_gd   = get_team_gd(standings, el_cutoff + 1)
            cg         = comp_gain_est(standings, el_cutoff + 1, rounds_left)
            gap        = pts - pts_below
            gd_pen     = 1 if (gap <= 1 and team_gd < below_gd) else 0
            points_needed = max(0, cg - gap + 1 + gd_pen)
        else:
            # ── EL chaser ──
            pts_el    = pts_at_pos(standings, el_cutoff)
            el_gd     = get_team_gd(standings, el_cutoff)
            cg        = comp_gain_est(standings, el_cutoff, rounds_left)
            gap_now   = pts_el - pts
            gd_pen    = 1 if (gap_now <= 0 and team_gd < el_gd) else 0
            points_needed = max(0, (pts_el + cg) - pts + 1 + gd_pen)

    pressure_ratio = min(1.0, points_needed / max_gain)

    return {
        "pointsNeeded":  points_needed,
        "pressureRatio": round(pressure_ratio, 3),
        "mustWin":       pressure_ratio > 0.65,
        "canDraw":       pressure_ratio < 0.30,
    }


def calc_score(labels, rounds_left, form_data=None, pressure_ratio=None):
    is_red  = any(l["c"] == "red"  for l in labels)
    is_gold = any(l["c"] == "gold" for l in labels)
    is_blue = any(l["c"] == "blue" for l in labels)

    # Zone base — lower than before so pressure_ratio carries the differentiation
    if is_red and any("Abstieg" in l["l"] and "gefahr" not in l["l"] for l in labels):
        base = 6.5
    elif is_red:
        base = 5.5
    elif is_gold and any("Titelkampf" in l["l"] for l in labels):
        base = 6.5
    elif is_gold:
        base = 5.5
    elif is_blue:
        base = 5.0
    else:
        base = 4.5  # orange / yellow

    # Pressure-ratio is the primary driver (0-1 → adds 0-3.5 pts).
    # A team needing 90% of remaining points scores near-maximum;
    # one that can comfortably draw scores much lower.
    if pressure_ratio is not None:
        pressure_score = pressure_ratio * 3.5
    else:
        # Fallback: old urgency formula when pressure data unavailable
        urgency = max(0.0, min(1.5, (10 - rounds_left) / 7))
        pressure_score = urgency * 1.5

    score = base + pressure_score + form_score_mod(form_data, is_red)
    return min(10, round(score, 1))

def calc_match_score(home_stake, away_stake, h2h=None, rounds_left=99):
    hs  = (home_stake or {}).get("score", 0)
    as_ = (away_stake or {}).get("score", 0)
    hc  = [l["c"] for l in (home_stake or {}).get("labels", [])]
    ac  = [l["c"] for l in (away_stake or {}).get("labels", [])]
    max_s = max(hs, as_)
    min_s = min(hs, as_)
    both_red  = "red"  in hc and "red"  in ac
    both_gold = "gold" in hc and "gold" in ac
    both_blue = "blue" in hc and "blue" in ac
    any_red   = "red"  in hc or "red"  in ac
    any_gold  = "gold" in hc or "gold" in ac

    # ── Red-safe detection: red label but pressure=0/ptNeeded=0 (already rescued) ──
    h_pr = (home_stake or {}).get("pressureRatio", 0)
    a_pr = (away_stake or {}).get("pressureRatio", 0)
    h_pn = (home_stake or {}).get("pointsNeeded", 0)
    a_pn = (away_stake or {}).get("pointsNeeded", 0)
    h_mot = (home_stake or {}).get("motivationLevel", "full")
    a_mot = (away_stake or {}).get("motivationLevel", "full")
    h_red_safe = "red" in hc and h_mot != "none" and h_pr == 0 and h_pn == 0
    a_red_safe = "red" in ac and a_mot != "none" and a_pr == 0 and a_pn == 0
    any_red_safe = h_red_safe or a_red_safe
    both_red_safe = h_red_safe and a_red_safe

    score = max_s
    if both_red and both_red_safe:
        # Both red but already safe — low urgency, treat like normal bothStakes
        score = max_s + 0.2
    elif both_red:
        score = max_s + 1.0 + (min_s / 10) * 1.5
    elif both_gold:
        score = max_s + 0.75 + (min_s / 10) * 1.5
    elif any_gold and any_red and any_red_safe:
        # Gold vs red-safe: red team already rescued — no drama bonus
        score = max_s + 0.2 + (min_s / 10) * 0.2
    elif any_gold and any_red:
        score = max_s + 0.5 + (min_s / 10) * 0.5
    elif both_blue:
        score = max_s + 0.5 + (min_s / 10) * 0.5
    elif any_red and any_red_safe and home_stake and away_stake:
        # Red-safe vs non-red: minimal boost
        score = max_s + 0.15
    elif any_red and home_stake and away_stake:
        score = max_s + 0.4 + (min_s / 10) * 0.4
    elif home_stake and away_stake:
        score = max_s + 0.3

    # H2H bonus: very lopsided or balanced rivalry adds context
    if h2h and h2h.get("games", 0) >= 5:
        n  = h2h["games"]
        hw = h2h.get("homeWins", 0)
        aw = h2h.get("awayWins", 0)
        dr = h2h.get("draws", 0)
        # Perfectly balanced rivalry (lots of draws/split) = tight decider
        balance = 1 - abs(hw - aw) / n
        if balance >= 0.9 and dr / n >= 0.3:
            score += 0.3   # historically very even — anything can happen
        elif balance >= 0.8:
            score += 0.15

    # ── Season urgency ceiling: mirrors JS computeMatchScore() ceiling logic ────
    # Prevents extreme scores from appearing too early in the final stretch.
    # rl=1→12.0  rl=2→11.5  rl=3→11.0  rl=4→10.5  rl=5→10.0  rl=6→9.5
    # rl=7→9.0   rl=8→8.5   rl=9→8.0   rl≥10→7.5
    rl = rounds_left
    max_score = (12.0 if rl <= 1 else 11.5 if rl <= 2 else 11.0 if rl <= 3 else
                 10.5 if rl <= 4 else 10.0 if rl <= 5 else  9.5 if rl <= 6 else
                  9.0 if rl <= 7 else  8.5 if rl <= 8 else  8.0 if rl <= 9 else 7.5)

    return round(min(max_score, score) * 10) / 10

# ── Main fetch loop ───────────────────────────────────────────────────────────

def fetch_league(key, cfg):
    print(f"\n  {cfg['flag']} {cfg['name']}...")
    apif_id = cfg.get("apif_id")
    if not apif_id:
        print(f"  ⚠ Kein apif_id für {key} — übersprungen")
        return None

    # ── Standings ────────────────────────────────────────────────────────────
    standings = []
    for season in [2025, 2026]:
        resp = apif_get("standings", {"league": apif_id, "season": season})
        if resp:
            rows = resp[0].get("league", {}).get("standings", [[]])[0]
            standings = [
                {
                    "pos":    r["rank"],
                    "team":   r["team"]["name"],
                    "teamId": r["team"]["id"],
                    "pts":    r["points"],
                    "played": r["all"]["played"],
                    "gd":     r["goalsDiff"],
                }
                for r in rows
            ]
            if standings:
                break

    if not standings:
        print(f"  ⚠ Keine Standings für {cfg['name']}")
        return None

    # ── Upcoming fixtures (next 14 days) ─────────────────────────────────────
    today     = datetime.now()
    date_from = today.strftime("%Y-%m-%d")
    date_to   = (today + timedelta(days=14)).strftime("%Y-%m-%d")

    fixtures_raw = []
    for season in [2025, 2026]:
        resp = apif_get("fixtures", {
            "league":   apif_id,
            "season":   season,
            "from":     date_from,
            "to":       date_to,
            "timezone": "Europe/Vienna",
            "status":   "NS-TBD",
        })
        if resp:
            fixtures_raw = resp
            break

    fixtures = []
    for fx in fixtures_raw:
        raw_date = fx["fixture"].get("date", "")
        fixtures.append({
            "date":   fmt_date_from_iso(raw_date[:10]) if raw_date else "",
            "time":   raw_date[11:16] if len(raw_date) >= 16 else None,
            "home":   fx["teams"]["home"]["name"],
            "away":   fx["teams"]["away"]["name"],
            "homeId": fx["teams"]["home"]["id"],
            "awayId": fx["teams"]["away"]["id"],
            "eventId": fx["fixture"]["id"],
        })

    max_played  = max(t["played"] for t in standings) if standings else 0
    rounds_left = max(0, cfg["rounds"] - max_played)

    # ── Form for stake teams ──────────────────────────────────────────────────
    print(f"    Fetching form data for stake teams...")
    form_cache = {}
    for t in standings:
        labels = calc_labels(t, standings, cfg)
        if not labels:
            continue
        fd = fetch_team_form(t["teamId"])
        if fd:
            form_cache[t["team"]] = fd
            streak_str = f"+{fd['streak']}" if fd["streak"] > 0 else str(fd["streak"])
            print(f"      {t['team']}: {fd['form']}  streak={streak_str}  fs={fd['formScore']}")

    # ── Stake teams ───────────────────────────────────────────────────────────
    stake_teams = []
    for t in standings:
        labels = calc_labels(t, standings, cfg)
        if labels:
            form     = form_cache.get(t["team"])
            pressure = calc_pressure(t, labels, standings, cfg, rounds_left)
            score    = calc_score(labels, rounds_left, form, pressure["pressureRatio"])
            gd_str   = f"+{t['gd']}" if t["gd"] >= 0 else str(t["gd"])
            stake_teams.append({
                "pos": t["pos"], "team": t["team"], "pts": t["pts"],
                "played": t["played"], "gd": gd_str, "score": score,
                "labels": labels, "form": form,
                "pointsNeeded":  pressure["pointsNeeded"],
                "pressureRatio": pressure["pressureRatio"],
                "mustWin":       pressure["mustWin"],
                "canDraw":       pressure["canDraw"],
            })

    # ── Stake fixtures ────────────────────────────────────────────────────────
    # Build a teamId lookup from standings
    id_map = {t["team"]: t["teamId"] for t in standings}

    # Also build by norm for fuzzy matching
    norm_id_map = {norm(t["team"]): t["teamId"] for t in standings}

    def find_team_id(name):
        if name in id_map:
            return id_map[name]
        n = norm(name)
        if n in norm_id_map:
            return norm_id_map[n]
        for k, v in norm_id_map.items():
            if n in k or k in n:
                return v
        return None

    def find_team_data(name):
        stand_map = {t["team"]: t for t in standings}
        norm_stand = {norm(t["team"]): t for t in standings}
        if name in stand_map:
            return stand_map[name]
        n = norm(name)
        if n in norm_stand:
            return norm_stand[n]
        for k, v in norm_stand.items():
            if n in k or k in n:
                return v
        return None

    stake_fixtures = []
    for f in fixtures:
        ht = find_team_data(f["home"])
        at = find_team_data(f["away"])
        if not ht or not at:
            continue
        h_labels = calc_labels(ht, standings, cfg)
        a_labels = calc_labels(at, standings, cfg)
        if not h_labels and not a_labels:
            continue

        h_form = form_cache.get(f["home"]) or form_cache.get(ht["team"])
        a_form = form_cache.get(f["away"]) or form_cache.get(at["team"])

        h_pressure = calc_pressure(ht, h_labels, standings, cfg, rounds_left) if h_labels else {}
        a_pressure = calc_pressure(at, a_labels, standings, cfg, rounds_left) if a_labels else {}
        # Cache motivation so we can use it for both motivationLevel and mustWin override
        h_motiv = calc_motivation(ht, h_labels, standings, cfg, rounds_left) if h_labels else 'full'
        a_motiv = calc_motivation(at, a_labels, standings, cfg, rounds_left) if a_labels else 'full'
        home_stake = {"score": calc_score(h_labels, rounds_left, h_form, h_pressure.get("pressureRatio")),
                      "labels": h_labels,
                      "motivationLevel": h_motiv,
                      "pointsNeeded": h_pressure.get("pointsNeeded", 0),
                      "pressureRatio": h_pressure.get("pressureRatio", 0.0),
                      # mustWin=False when motiv='none': confirmed team has given up regardless of ratio
                      "mustWin": h_pressure.get("mustWin", False) and h_motiv != 'none',
                      "canDraw": h_pressure.get("canDraw", True)} if h_labels else None
        away_stake = {"score": calc_score(a_labels, rounds_left, a_form, a_pressure.get("pressureRatio")),
                      "labels": a_labels,
                      "motivationLevel": a_motiv,
                      "pointsNeeded": a_pressure.get("pointsNeeded", 0),
                      "pressureRatio": a_pressure.get("pressureRatio", 0.0),
                      # mustWin=False when motiv='none': confirmed team has given up regardless of ratio
                      "mustWin": a_pressure.get("mustWin", False) and a_motiv != 'none',
                      "canDraw": a_pressure.get("canDraw", True)} if a_labels else None

        # H2H using API-Football team IDs
        home_id = f.get("homeId") or find_team_id(f["home"])
        away_id = f.get("awayId") or find_team_id(f["away"])
        h2h = None
        if home_id and away_id:
            h2h = fetch_h2h(home_id, away_id)
            if h2h:
                print(f"      H2H {f['home']} vs {f['away']}: {h2h['homeWins']}H {h2h['draws']}X {h2h['awayWins']}A ({h2h['games']}G)")

        ms = calc_match_score(home_stake, away_stake, h2h, rounds_left)
        if ms < 5:
            continue
        stake_fixtures.append({
            "date": f["date"], "time": f.get("time"),
            "home": f["home"], "away": f["away"],
            "eventId": f.get("eventId"),
            "matchScore": ms, "bothStakes": bool(home_stake and away_stake),
            "homeStake": home_stake, "awayStake": away_stake,
            "homeForm": h_form, "awayForm": a_form,
            "h2h": h2h,
        })

    leader = standings[0] if standings else {"team": "?", "pts": 0}
    print(f"    ✓ {len(standings)} teams · {rounds_left}R left · {len(stake_fixtures)} stake fixtures")

    return {
        "name": cfg["name"], "flag": cfg["flag"], "roundsLeft": rounds_left,
        "leader": leader["team"], "leaderPts": leader["pts"],
        "stakeTeams": stake_teams, "fixtures": stake_fixtures,
    }

# ── Build JS object ───────────────────────────────────────────────────────────

def build_leagues_js(results):
    lines = ["const LEAGUES = {"]
    entries = []
    for key, data in results.items():
        st_json = json.dumps(data["stakeTeams"], ensure_ascii=False)
        fx_json = json.dumps(data["fixtures"],   ensure_ascii=False)
        entry = (
            f'  {key}:{{name:{json.dumps(data["name"],ensure_ascii=False)},'
            f'flag:{json.dumps(data["flag"],ensure_ascii=False)},'
            f'roundsLeft:{data["roundsLeft"]},'
            f'leader:{json.dumps(data["leader"],ensure_ascii=False)},'
            f'leaderPts:{data["leaderPts"]},\n'
            f'    stakeTeams:{st_json},\n'
            f'    fixtures:{fx_json}\n'
            f'  }}'
        )
        entries.append(entry)
    lines.append(",\n".join(entries))
    lines.append("};")
    return "\n".join(lines)

# ── Update HTML ───────────────────────────────────────────────────────────────

def update_html(new_leagues_js, today_str):
    if not os.path.exists(HTML_FILE):
        print(f"\n✗ Datei nicht gefunden: {HTML_FILE}")
        sys.exit(1)

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace LEAGUES block
    pattern = r'const LEAGUES = \{.*?\n\};'
    if not re.search(pattern, content, re.DOTALL):
        print("✗ LEAGUES-Block nicht gefunden in HTML-Datei")
        sys.exit(1)

    content = re.sub(pattern, new_leagues_js, content, flags=re.DOTALL)

    # Update date string
    content = re.sub(
        r'Stand \d{1,2}\. \w+ \d{4}',
        f'Stand {today_str}',
        content
    )

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✓ {HTML_FILE} aktualisiert")

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  BetEdge Dashboard — Daten-Update")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)
    print("\nFetching API-Football data...")

    results = {}
    for key, cfg in LEAGUES.items():
        data = fetch_league(key, cfg)
        if data:
            results[key] = data

    if not results:
        print("\n✗ Keine Daten erhalten. Prüfe deine Internetverbindung.")
        sys.exit(1)

    print(f"\n✓ {len(results)}/{len(LEAGUES)} Ligen erfolgreich geladen")

    new_js  = build_leagues_js(results)
    today_s = german_date()
    update_html(new_js, today_s)

    # ── Export matches_today.json for picks tracking ──────────────────────────
    matches_out = Path(__file__).parent / "matches_today.json"
    today_iso = datetime.now().strftime("%Y-%m-%d")
    export = []
    for key, data in results.items():
        for f in data["fixtures"]:
            if not f.get("eventId"):
                continue
            export.append({
                "league":      key,
                "leagueName":  data["name"],
                "leagueFlag":  data["flag"],
                "roundsLeft":  data["roundsLeft"],
                "date":        f["date"],
                "dateIso":     today_iso,
                "home":        f["home"],
                "away":        f["away"],
                "eventId":     f["eventId"],
                "matchScore":  f["matchScore"],
                "homeStake":   f.get("homeStake"),
                "awayStake":   f.get("awayStake"),
                "homeForm":    f.get("homeForm"),
                "awayForm":    f.get("awayForm"),
                "h2h":         f.get("h2h"),
            })
    with open(matches_out, "w", encoding="utf-8") as mf:
        json.dump(export, mf, ensure_ascii=False, indent=2)
    print(f"✓ matches_today.json geschrieben ({len(export)} Spiele)")

    # Summary
    all_fx = [(k, f) for k, d in results.items() for f in d["fixtures"] if within_7_days(f["date"])]
    all_fx.sort(key=lambda x: -x[1]["matchScore"])

    print(f"\n📅 Nächste 7 Tage: {len(all_fx)} High-Stakes Spiele")
    print("\n⭐ Top 5 Spiele:")
    for key, f in all_fx[:5]:
        flag = results[key]["flag"]
        print(f"   {flag} {f['home']} vs {f['away']}  [Score: {f['matchScore']}]  📅 {f['date']}")

    print(f"\n✅ Update abgeschlossen — {today_s}")
    print("   Öffne season-finish.html im Browser um die Änderungen zu sehen.\n")

# ─────────────────────────────────────────────────────────────────────────────
#  PICK RESOLVER — reads picks_history.json, fetches API-Football results,
#  resolves outcomes, writes picks_history.json back
# ─────────────────────────────────────────────────────────────────────────────

def _fuzzy_team(a, b):
    """Fuzzy team name match — mirrors JS _fuzzyTeam()."""
    import re
    def clean(s):
        s = s.lower()
        for pfx in ["fc ", "sc ", "sv ", "bv ", "1. ", "vfb ", "vfl ", "rb "]:
            s = s.replace(pfx, " ")
        return re.sub(r"[^a-z0-9 ]", " ", s).strip()
    ca, cb = clean(a), clean(b)
    if ca == cb: return True
    if ca in cb or cb in ca: return True
    wa = set(w for w in ca.split() if len(w) > 2)
    wb = set(w for w in cb.split() if len(w) > 2)
    overlap = len(wa & wb)
    return overlap >= 1 and overlap / max(len(wa), len(wb), 1) >= 0.5

def _determine_outcome(market, h, a):
    """Resolve a pick outcome from final score — mirrors JS _determineOutcome()."""
    goals = h + a
    m = (market or "").lower()
    if "über 3.5"  in m or "over 3.5"  in m: return "win" if goals > 3 else "loss"
    if "über 2.5"  in m or "over 2.5"  in m: return "win" if goals > 2 else "loss"
    if "über 1.5"  in m or "over 1.5"  in m: return "win" if goals > 1 else "loss"
    if "unter 2.5" in m or "under 2.5" in m: return "win" if goals < 3 else "loss"
    if "unter 1.5" in m or "under 1.5" in m: return "win" if goals < 2 else "loss"
    if "beide teams treffen: nein" in m:      return "win" if (h == 0 or a == 0) else "loss"
    if "beide teams treffen" in m or "btts" in m: return "win" if (h > 0 and a > 0) else "loss"
    if "dnb: heim"      in m: return "win" if h > a else ("void" if h == a else "loss")
    if "dnb: auswärts"  in m: return "win" if a > h else ("void" if h == a else "loss")
    if "doppelte chance: 1x" in m: return "win" if h >= a else "loss"
    if "doppelte chance: x2" in m: return "win" if a >= h else "loss"
    if "doppelte chance: 12" in m: return "win" if h != a else "loss"
    if "heimsieg"    in m or "home win"  in m: return "win" if h > a else "loss"
    if "auswärtssieg" in m or "away win" in m: return "win" if a > h else "loss"
    if "unentschieden" in m or ("draw" in m and "no bet" not in m): return "win" if h == a else "loss"
    if "handicap" in m:
        if "heim" in m or "home" in m: return "win" if h > a else "loss"
        if "auswärts" in m or "away" in m: return "win" if a > h else "loss"
    return None  # HZ / Ecken / Karten — can't auto-determine

def _apif_fetch_results(date_iso):
    """Fetch API-Football finished fixtures for a date (ISO: YYYY-MM-DD)."""
    fixtures = apif_get("fixtures", {"date": date_iso, "status": "FT-AET-PEN"})
    result = []
    for fx in fixtures:
        home = fx.get("teams", {}).get("home", {}).get("name", "")
        away = fx.get("teams", {}).get("away", {}).get("name", "")
        gh   = fx.get("goals", {}).get("home")
        ga   = fx.get("goals", {}).get("away")
        if home and away and gh is not None and ga is not None:
            result.append({"home": home, "away": away, "gh": gh, "ga": ga})
    return result

def resolve_pending_picks():
    """Read picks_history.json, resolve pending picks via API-Football, write back."""
    picks_file = os.path.join(SCRIPT_DIR, "picks_history.json")
    if not os.path.exists(picks_file):
        print("  ℹ  picks_history.json nicht gefunden — überspringe Pick-Auflösung")
        return

    with open(picks_file, "r", encoding="utf-8") as f:
        picks = json.load(f)

    pending_entries = [e for e in picks if any(p.get("result") is None for p in e.get("picks", []))]
    if not pending_entries:
        print("  ✓ Alle Picks bereits aufgelöst")
        return

    # Only try to resolve past dates (today or earlier)
    today = datetime.utcnow().date()
    past_pending = [e for e in pending_entries if e.get("dateIso", "9999") <= str(today)]
    if not past_pending:
        print(f"  ℹ  {len(pending_entries)} offene Picks — alle in der Zukunft, noch nicht auflösbar")
        return

    print(f"\n🎲 Löse {len(past_pending)} Einträge mit offenen Picks auf…")
    dates = sorted(set(e["dateIso"] for e in past_pending))
    resolved_total = 0

    for date_iso in dates:
        print(f"  📅 {date_iso} wird von API-Football geladen…", end=" ", flush=True)
        events = _apif_fetch_results(date_iso)
        if not events:
            print("keine Daten")
            continue
        print(f"{len(events)} Spiele")
        # Note: apif_get() already applies APIF_DELAY internally

        for entry in picks:
            if entry["dateIso"] != date_iso:
                continue
            if not any(p.get("result") is None for p in entry.get("picks", [])):
                continue

            # Find matching API-Football fixture
            ev = next((
                e for e in events
                if _fuzzy_team(e["home"], entry["home"])
                and _fuzzy_team(e["away"], entry["away"])
            ), None)

            if not ev:
                print(f"    ⚠  {entry['home']} vs {entry['away']} — nicht gefunden")
                continue

            h, a = ev["gh"], ev["ga"]
            entry["finalScore"] = f"{h}:{a}"

            for p in entry["picks"]:
                if p.get("result") is not None:
                    continue
                outcome = _determine_outcome(p["market"], h, a)
                if outcome is not None:
                    p["result"] = outcome
                    p["finalScore"] = f"{h}:{a}"
                    resolved_total += 1
                    icon = "✅" if outcome == "win" else ("↩️" if outcome == "void" else "❌")
                    print(f"    {icon} {entry['home']} {h}:{a} {entry['away']}  →  {p['market']} = {outcome}")

    with open(picks_file, "w", encoding="utf-8") as f:
        json.dump(picks, f, ensure_ascii=False, indent=2)

    print(f"\n  ✓ {resolved_total} Picks aufgelöst → picks_history.json aktualisiert")


if __name__ == "__main__":
    main()
    print("\n" + "─" * 60)
    resolve_pending_picks()
