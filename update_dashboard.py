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
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(SCRIPT_DIR, "season-finish.html")

LEAGUES = {
    "ENG": dict(tid=17,  name="Premier League",  flag="🏴󠁧󠁢󠁥󠁮󠁧󠁿", total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "GER": dict(tid=35,  name="Bundesliga",       flag="🇩🇪",         total=18, rounds=34, ucl=4, el=2, uecl=1, rel_playoff=1, rel=2),
    "ITA": dict(tid=23,  name="Serie A",          flag="🇮🇹",         total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "ESP": dict(tid=8,   name="La Liga",          flag="🇪🇸",         total=20, rounds=38, ucl=4, el=2, uecl=1, rel_playoff=0, rel=3),
    "FRA": dict(tid=34,  name="Ligue 1",          flag="🇫🇷",         total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "AUT": dict(tid=45,  name="Österreich BL",    flag="🇦🇹",         total=12, rounds=32, ucl=2, el=1, uecl=0, rel_playoff=1, rel=2),
    "NED": dict(tid=37,  name="Eredivisie",       flag="🇳🇱",         total=18, rounds=34, ucl=2, el=2, uecl=0, rel_playoff=2, rel=1),
    "POR": dict(tid=238, name="Primeira Liga",    flag="🇵🇹",         total=18, rounds=34, ucl=3, el=2, uecl=1, rel_playoff=1, rel=2),
    "SCO": dict(tid=36,  name="Scottish Prem",    flag="🏴󠁧󠁢󠁳󠁣󠁴󠁿", total=12, rounds=38, ucl=2, el=2, uecl=0, rel_playoff=1, rel=1),
    "TUR": dict(tid=52,  name="Süper Lig",        flag="🇹🇷",         total=19, rounds=38, ucl=2, el=2, uecl=1, rel_playoff=0, rel=3),
    "SUI": dict(tid=57,  name="Swiss SL",         flag="🇨🇭",         total=10, rounds=36, ucl=1, el=1, uecl=0, rel_playoff=1, rel=1),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "x-requested-with": "XMLHttpRequest",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
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

def fetch_team_form(team_id):
    """Fetch last 6 finished games for a team → form string + metrics."""
    data = fetch(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0")
    if not data or not data.get("events"):
        return None

    events = sorted(data["events"], key=lambda e: e.get("startTimestamp", 0))
    results, gf_list, ga_list = [], [], []

    for e in events:
        if e.get("status", {}).get("type") != "finished":
            continue
        hs  = (e.get("homeScore") or {}).get("current") or 0
        as_ = (e.get("awayScore") or {}).get("current") or 0
        is_home = e["homeTeam"]["id"] == team_id
        gf = hs if is_home else as_
        ga = as_ if is_home else hs
        gf_list.append(gf); ga_list.append(ga)
        results.append("W" if gf > ga else ("D" if gf == ga else "L"))

    results = results[-6:]  # keep last 6
    if not results:
        return None

    # Streak: count consecutive same result from the end
    streak = 1
    for i in range(len(results) - 2, -1, -1):
        if results[i] == results[-1]:
            streak += 1
        else:
            break
    if results[-1] == "L": streak = -streak
    elif results[-1] == "D": streak = 0

    pts     = sum(3 if r == "W" else (1 if r == "D" else 0) for r in results)
    max_pts = len(results) * 3

    return {
        "form":            "".join(results),
        "formScore":       round(pts / max_pts, 2) if max_pts else 0.5,
        "streak":          streak,
        "goalsPerGame":    round(sum(gf_list[-6:]) / len(gf_list[-6:]), 1) if gf_list else 0,
        "concededPerGame": round(sum(ga_list[-6:]) / len(ga_list[-6:]), 1) if ga_list else 0,
    }


def fetch_team_injuries(team_id):
    """Fetch current injury/suspension list for a team from SofaScore.
    Returns dict with attack/defense counts and player notes, or None on failure.
    Long-term absences (returnDate in future) are included.
    Short-term match-day decisions are NOT available via this endpoint.
    """
    from datetime import datetime
    data = fetch(f"https://api.sofascore.com/api/v1/team/{team_id}/injuries")
    if not data or not data.get("injuries"):
        return None

    now_ts = datetime.now().timestamp()
    attack_count, defense_count = 0, 0
    notes = []

    for inj in data.get("injuries", []):
        player   = inj.get("player") or {}
        pos      = player.get("position", "")         # F / M / D / G
        name     = player.get("name", "?")
        inj_info = (inj.get("playerTeamInjury") or inj.get("injury") or {})
        ret_ts   = inj_info.get("returnTimestamp") or inj_info.get("returnDate")

        # Skip if already recovered (return date in the past)
        if ret_ts and isinstance(ret_ts, (int, float)) and ret_ts < now_ts:
            continue

        # Position categories
        if pos in ("F", "M"):
            attack_count += 1
        elif pos in ("D", "G"):
            defense_count += 1
        else:
            continue  # ignore unknown positions

        # Build human-readable note
        if ret_ts and isinstance(ret_ts, (int, float)):
            weeks_left = max(0, int((ret_ts - now_ts) / 604800))
            suffix = f"bald zurück" if weeks_left == 0 else f"ca. {weeks_left} Wo."
        else:
            suffix = "unbekannte Dauer"
        notes.append(f"{name} ({suffix})")

    if attack_count == 0 and defense_count == 0:
        return None

    return {
        "attack":  attack_count,
        "defense": defense_count,
        "notes":   notes[:4],  # cap at 4 entries for UI display
    }


def fetch_h2h(event_id):
    """Fetch H2H stats for a given upcoming event.
    Sofascore returns aggregate wins/draws/losses in teamDuel — no per-match data.
    """
    data = fetch(f"https://api.sofascore.com/api/v1/event/{event_id}/h2h")
    if not data:
        return None

    td = data.get("teamDuel")
    if not td:
        return None

    home_wins = td.get("homeWins", 0)
    draws     = td.get("draws",    0)
    away_wins = td.get("awayWins", 0)
    n = home_wins + draws + away_wins
    if n == 0:
        return None

    return {
        "games":    n,
        "homeWins": home_wins,
        "draws":    draws,
        "awayWins": away_wins,
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

def calc_score(labels, rounds_left, form_data=None):
    is_red  = any(l["c"] == "red"  for l in labels)
    is_gold = any(l["c"] == "gold" for l in labels)
    is_blue = any(l["c"] == "blue" for l in labels)
    urgency = max(0.0, min(1.5, (10 - rounds_left) / 7))

    if is_red and any("Abstieg" in l["l"] and "gefahr" not in l["l"] for l in labels):
        base = 8
    elif is_red:
        base = 7
    elif is_gold and any("Titelkampf" in l["l"] for l in labels):
        base = 8
    elif is_gold:
        base = 7
    elif is_blue:
        base = 6
    else:
        base = 5

    score = base + urgency * 2 + form_score_mod(form_data, is_red)
    return min(10, round(score))

def calc_match_score(home_stake, away_stake, h2h=None):
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

    score = max_s
    if both_red:
        score = max_s + 1.0 + (min_s / 10) * 1.5
    elif both_gold:
        score = max_s + 0.75 + (min_s / 10) * 1.5
    elif any_gold and any_red:
        score = max_s + 0.5 + (min_s / 10) * 0.5
    elif both_blue:
        score = max_s + 0.5 + (min_s / 10) * 0.5
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

    return round(min(12.0, score) * 10) / 10

# ── Main fetch loop ───────────────────────────────────────────────────────────

def fetch_league(key, cfg):
    print(f"\n  {cfg['flag']} {cfg['name']}...")
    tid = cfg["tid"]

    seasons_data = fetch(f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/seasons")
    if not seasons_data:
        return None
    sid = seasons_data["seasons"][0]["id"]

    stand_data = fetch(f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/standings/total")
    if not stand_data or not stand_data.get("standings"):
        return None

    rows = stand_data["standings"][0]["rows"]
    standings = [
        {
            "pos":    r["position"],
            "team":   r["team"]["name"],
            "teamId": r["team"]["id"],           # ← store team ID for form fetch
            "pts":    r["points"],
            "played": r["matches"],
            "gd":     r["scoresFor"] - r["scoresAgainst"],
        }
        for r in rows
    ]

    # Fetch next 2 rounds of fixtures (keep event IDs for H2H)
    fixtures_raw = []
    for page in [0, 1]:
        data = fetch(f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/{sid}/events/next/{page}")
        if data and data.get("events"):
            fixtures_raw.extend(data["events"])

    fixtures = [
        {
            "date":    fmt_date(e["startTimestamp"]),
            "home":    e["homeTeam"]["name"],
            "away":    e["awayTeam"]["name"],
            "eventId": e["id"],
        }
        for e in fixtures_raw
    ]

    max_played  = max(t["played"] for t in standings) if standings else 0
    rounds_left = max(0, cfg["rounds"] - max_played)

    # ── Pre-fetch form + injuries for teams that have stakes ─────────────────
    print(f"    Fetching form + injury data...")
    form_cache = {}   # team_name → form dict (includes injuries when available)
    for t in standings:
        labels = calc_labels(t, standings, cfg)
        if not labels:
            continue
        fd = fetch_team_form(t["teamId"])
        if fd:
            # Attach current injury data to form dict
            inj = fetch_team_injuries(t["teamId"])
            if inj:
                fd["injuries"] = inj
                print(f"      {t['team']}: 🏥 {inj['attack']} Angriff / {inj['defense']} Abwehr Ausfälle")
            form_cache[t["team"]] = fd
            streak_str = f"+{fd['streak']}" if fd["streak"] > 0 else str(fd["streak"])
            print(f"      {t['team']}: {fd['form']}  streak={streak_str}  fs={fd['formScore']}")

    # ── Stake teams (with form) ───────────────────────────────────────────────
    stake_teams = []
    for t in standings:
        labels = calc_labels(t, standings, cfg)
        if labels:
            form   = form_cache.get(t["team"])
            score  = calc_score(labels, rounds_left, form)
            gd_str = f"+{t['gd']}" if t["gd"] >= 0 else str(t["gd"])
            stake_teams.append({
                "pos": t["pos"], "team": t["team"], "pts": t["pts"],
                "played": t["played"], "gd": gd_str, "score": score,
                "labels": labels, "form": form,
            })

    # ── Stake fixtures (with form + H2H) ─────────────────────────────────────
    stand_map = {norm(t["team"]): t for t in standings}

    def find_team(name):
        n = norm(name)
        if n in stand_map:
            return stand_map[n]
        for k, v in stand_map.items():
            if n in k or k in n:
                return v
            words = [w for w in n.split() if len(w) > 3]
            if any(w in k for w in words):
                return v
        return None

    stake_fixtures = []
    for f in fixtures:
        ht = find_team(f["home"])
        at = find_team(f["away"])
        if not ht or not at:
            continue
        h_labels = calc_labels(ht, standings, cfg)
        a_labels = calc_labels(at, standings, cfg)
        if not h_labels and not a_labels:
            continue

        h_form = form_cache.get(f["home"]) or form_cache.get(ht["team"])
        a_form = form_cache.get(f["away"]) or form_cache.get(at["team"])

        home_stake = {"score": calc_score(h_labels, rounds_left, h_form), "labels": h_labels} if h_labels else None
        away_stake = {"score": calc_score(a_labels, rounds_left, a_form), "labels": a_labels} if a_labels else None

        # Fetch H2H
        h2h = fetch_h2h(f["eventId"]) if f.get("eventId") else None
        if h2h:
            print(f"      H2H {f['home']} vs {f['away']}: {h2h['homeWins']}H {h2h['draws']}X {h2h['awayWins']}A ({h2h['games']}G)")

        ms = calc_match_score(home_stake, away_stake, h2h)
        if ms < 5:
            continue
        stake_fixtures.append({
            "date": f["date"], "home": f["home"], "away": f["away"],
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
    print("\nFetching Sofascore data...")

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

if __name__ == "__main__":
    main()
