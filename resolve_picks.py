#!/usr/bin/env python3
"""
resolve_picks.py — Resolves pending picks in picks_history.json using
                   results-cache.json (written by fetch_results.py).

Falls back to live Sofascore only for entries not found in the cache.
Run daily (after matches have finished) via update-dashboard.yml.
"""

import json
import urllib.request
import urllib.error
import datetime
import time
from pathlib import Path

BASE         = Path(__file__).parent
HISTORY_FILE = BASE / "picks_history.json"
CACHE_FILE   = BASE / "results-cache.json"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":          "application/json",
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── results-cache.json lookup ─────────────────────────────────────────────────

import re as _re_norm

def _norm_name(s: str) -> str:
    """Normalize team name for fuzzy matching."""
    s = s.lower()
    # Remove common suffixes/prefixes that vary between data sources
    s = _re_norm.sub(r'\b(fc|sv|sc|ac|as|us|cd|sk|rb|bv|vv|nk|fk|cf|ss|if|kf|pfc)\b', ' ', s)
    s = _re_norm.sub(r'[^a-z0-9 ]', ' ', s)
    s = _re_norm.sub(r'\s+', ' ', s).strip()
    return s


def _make_result_entry(fix: dict) -> dict:
    """Build a result dict from a fixture entry."""
    status = fix.get("status", "")
    if status == "FT":
        return {
            "homeGoals":   fix.get("goalsHome"),
            "awayGoals":   fix.get("goalsAway"),
            "status":      "finished",
            "yellowHome":  fix.get("yellowHome"),
            "yellowAway":  fix.get("yellowAway"),
            "redHome":     fix.get("redHome"),
            "redAway":     fix.get("redAway"),
            "cornersHome": fix.get("cornersHome"),
            "cornersAway": fix.get("cornersAway"),
            "htHome":      fix.get("htHome"),
            "htAway":      fix.get("htAway"),
        }
    elif status in ("POSTP", "CANC", "WO", "AWD"):
        return {"status": "postponed", "homeGoals": None, "awayGoals": None}
    return None


def build_cache_index(cache_file: Path) -> tuple[dict, dict]:
    """
    Build two lookup dicts from results-cache.json:
      id_index:   eventId (API-Football)    → result dict
      name_index: "date|norm_home|norm_away" → result dict  (fallback)

    NOTE: picks_history uses Sofascore eventIds, while results-cache stores
    API-Football fixture IDs — they are different number spaces. The id_index
    will rarely match; the name_index is the primary resolution path.
    """
    if not cache_file.exists():
        print("  ⚠️  results-cache.json not found — will use Sofascore fallback only")
        return {}, {}
    with open(cache_file, encoding="utf-8") as f:
        data = json.load(f)
    id_index   = {}
    name_index = {}
    for fix in data.get("fixtures", []):
        status = fix.get("status", "")
        if status not in ("FT", "POSTP", "CANC", "WO", "AWD"):
            continue
        entry = _make_result_entry(fix)
        if entry is None:
            continue
        # ID-based index (API-Football IDs)
        eid = fix.get("id")
        if eid:
            id_index[eid] = entry
        # Name-based index
        date_str = (fix.get("date") or "")[:10]
        nh = _norm_name(fix.get("home", ""))
        na = _norm_name(fix.get("away", ""))
        if date_str and nh and na:
            name_index[f"{date_str}|{nh}|{na}"] = entry
    print(f"  📦 results-cache.json loaded: {len(id_index)} ID entries, {len(name_index)} name entries")
    return id_index, name_index


def lookup_cache(event_id, date_iso: str, home: str, away: str,
                 id_index: dict, name_index: dict):
    """Look up a match in the cache, trying ID first then name+date."""
    # 1) Direct ID match (rarely works — different ID spaces)
    result = id_index.get(event_id)
    if result:
        return result, "id"

    # 2) Name + date match
    nh = _norm_name(home)
    na = _norm_name(away)
    key = f"{date_iso}|{nh}|{na}"
    result = name_index.get(key)
    if result:
        return result, "name-exact"

    # 3) Fuzzy name match for the same date (handles minor name differences)
    for k, v in name_index.items():
        k_date, k_h, k_a = k.split("|", 2)
        if k_date != date_iso:
            continue
        if ((nh in k_h or k_h in nh) and nh and k_h and
                (na in k_a or k_a in na) and na and k_a):
            return v, "name-fuzzy"

    return None, None


# ── Sofascore fallback ────────────────────────────────────────────────────────

def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    ⚠️  Fetch failed: {url} — {e}")
        return None


def get_match_result_sofascore(event_id: int) -> dict | None:
    """Live Sofascore fallback for fixtures not in results-cache."""
    data = fetch(f"https://api.sofascore.com/api/v1/event/{event_id}")
    if not data or "event" not in data:
        return None
    ev = data["event"]
    st = ev.get("status", {}).get("type", "notstarted")
    hg = (ev.get("homeScore") or {}).get("current")
    ag = (ev.get("awayScore") or {}).get("current")
    if st == "finished" and hg is not None and ag is not None:
        return {"homeGoals": int(hg), "awayGoals": int(ag), "status": "finished"}
    return {"status": st, "homeGoals": None, "awayGoals": None}


# ── Win/loss determination ────────────────────────────────────────────────────

def evaluate_pick(market_key: str, home_goals: int, away_goals: int,
                  result: dict | None = None) -> str:
    """Returns 'win', 'loss', or 'void'.

    result is the full cache entry (may contain yellowHome/Away, redHome/Away).
    Cards markets need result data — if unavailable they return 'void'.
    """
    total = home_goals + away_goals
    rules = {
        "homeWin":  home_goals > away_goals,
        "awayWin":  away_goals > home_goals,
        "draw":     home_goals == away_goals,
        "over25":   total > 2,
        "under25":  total < 3,
        "over35":   total > 3,
        "under35":  total < 4,
        "btts":     home_goals > 0 and away_goals > 0,
        "noBtts":   home_goals == 0 or away_goals == 0,
    }
    if market_key in rules:
        return "win" if rules[market_key] else "loss"

    # ── Asian Handicap — market_key encodes direction + point: "ah_home:-2.25"
    # pt < 0: favourite gives goals (e.g. -2.25 means home gives 2.25 to away)
    # AH whole-ball: push on exact margin → void
    # AH quarter-ball (.25/.75): half win → win, half loss → loss
    if market_key.startswith("ah_home:") or market_key.startswith("ah_away:"):
        import re as _re
        m = _re.search(r':([-+]?\d+\.?\d*)', market_key)
        if not m:
            return "void"
        pt = float(m.group(1))
        is_home = market_key.startswith("ah_home")
        margin = home_goals - away_goals if is_home else away_goals - home_goals
        adjusted = margin + pt  # e.g. margin=3, pt=-2.25 → adjusted=0.75 → win
        if abs(adjusted) < 0.01:
            return "void"           # push (whole-ball exact cover)
        elif abs(adjusted - 0.25) < 0.01:
            return "win"            # quarter-ball: half win → win
        elif abs(adjusted + 0.25) < 0.01:
            return "loss"           # quarter-ball: half loss → loss
        return "win" if adjusted > 0 else "loss"

    # ── Cards markets ─────────────────────────────────────────────────────────
    if market_key in ("cards35", "cards45"):
        if not result:
            return "void"
        yh = result.get("yellowHome")
        ya = result.get("yellowAway")
        rh = result.get("redHome")  or 0
        ra = result.get("redAway")  or 0
        if yh is None or ya is None:
            return "void"
        total_cards = yh + ya + rh + ra
        threshold = 3.5 if market_key == "cards35" else 4.5
        return "win" if total_cards > threshold else "loss"

    # ── Double Chance ─────────────────────────────────────────────────────────
    if market_key == "dc1X":   # Home win OR draw
        return "win" if home_goals >= away_goals else "loss"
    if market_key == "dcX2":   # Draw OR away win
        return "win" if away_goals >= home_goals else "loss"
    if market_key == "dc12":   # Home win OR away win (no draw)
        return "void" if home_goals == away_goals else "win"

    # ── Corners markets ───────────────────────────────────────────────────────
    if market_key.startswith("corners_over:") or market_key.startswith("corners_under:"):
        if not result:
            return "void"
        ch = result.get("cornersHome")
        ca = result.get("cornersAway")
        if ch is None or ca is None:
            return "void"
        total_corners = ch + ca
        import re as _re2
        mt = _re2.search(r':([\d.]+)', market_key)
        if not mt:
            return "void"
        threshold = float(mt.group(1))
        if market_key.startswith("corners_over:"):
            if abs(total_corners - threshold) < 0.01:
                return "void"   # push (whole-number)
            return "win" if total_corners > threshold else "loss"
        else:
            if abs(total_corners - threshold) < 0.01:
                return "void"
            return "win" if total_corners < threshold else "loss"

    # ── Half-time markets ─────────────────────────────────────────────────────
    if market_key in ("ht_over05", "ht_over15", "ht_btts", "ht_noBtts"):
        if not result:
            return "void"
        hth = result.get("htHome")
        hta = result.get("htAway")
        if hth is None or hta is None:
            return "void"
        ht_total = hth + hta
        if market_key == "ht_over05":
            return "win" if ht_total > 0 else "loss"
        if market_key == "ht_over15":
            return "win" if ht_total > 1 else "loss"
        if market_key == "ht_btts":
            return "win" if hth > 0 and hta > 0 else "loss"
        if market_key == "ht_noBtts":
            return "win" if hth == 0 or hta == 0 else "loss"

    # ── Team-specific goals ───────────────────────────────────────────────────
    # New format: team_goals_home_over:1.5 / team_goals_away_over:1.5
    # Legacy format: team_goals_over:1.5 (can't resolve without home/away context → void)
    import re as _re3
    _tg = _re3.search(r':([\d.]+)', market_key)
    if _tg:
        _thr = float(_tg.group(1))
        if market_key.startswith("team_goals_home_over:"):
            return "win" if home_goals > _thr else "loss"
        if market_key.startswith("team_goals_home_under:"):
            return "win" if home_goals < _thr else ("void" if home_goals == _thr else "loss")
        if market_key.startswith("team_goals_away_over:"):
            return "win" if away_goals > _thr else "loss"
        if market_key.startswith("team_goals_away_under:"):
            return "win" if away_goals < _thr else ("void" if away_goals == _thr else "loss")
    # Legacy: no home/away context encoded
    if market_key.startswith("team_goals_over:") or market_key.startswith("team_goals_under:"):
        return "void"

    return "void"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.date.today()
    print(f"🔍  Resolve picks — {today.isoformat()}")

    if not HISTORY_FILE.exists():
        print("  ℹ️  picks_history.json not found — nothing to resolve yet")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        history = json.load(f)

    # ── Cleanup: mark entries as resolved if they already have all results ───────
    # Handles legacy entries where results were written but resolved flag was missed.
    auto_resolved = 0
    for e in history:
        if e.get("resolved"):
            continue
        if e.get("finalScore") and e.get("picks") and all(p.get("result") for p in e["picks"]):
            e["resolved"] = True
            auto_resolved += 1
    if auto_resolved:
        print(f"  🔧 Auto-fixed {auto_resolved} entries with results but resolved=False")

    # Build cache indexes from results-cache.json (primary source, no rate limits)
    id_index, name_index = build_cache_index(CACHE_FILE)

    # Only process unresolved entries for past matches
    pending = [
        e for e in history
        if not e.get("resolved")
        and datetime.date.fromisoformat(e["dateIso"]) < today
    ]
    print(f"  Pending entries: {len(pending)}")

    resolved_count  = 0
    cache_hits      = 0
    sofascore_hits  = 0
    skipped_count   = 0

    for entry in pending:
        event_id = entry.get("eventId")
        flag     = entry.get("leagueFlag", "")
        home     = entry["home"]
        away     = entry["away"]
        date_iso = entry["dateIso"]

        # ── Primary: results-cache.json (ID + name fallback) ─────────────────
        result, match_method = lookup_cache(event_id, date_iso, home, away,
                                            id_index, name_index)

        if result:
            cache_hits += 1
            print(f"  📦 {flag} {home} vs {away} ({date_iso}) → cache ({match_method})")
        elif event_id:
            # ── Fallback: live Sofascore call (only when we have an eventId) ─
            print(f"  🌐 {flag} {home} vs {away} ({date_iso}) → Sofascore fallback …")
            result = get_match_result_sofascore(event_id)
            time.sleep(0.4)
            if result:
                sofascore_hits += 1
            else:
                print(f"    → Could not fetch event {event_id}")
                skipped_count += 1
                continue
        else:
            print(f"  ⚠️  {flag} {home} vs {away} ({date_iso}) → no eventId + not in cache")
            skipped_count += 1
            continue

        status = result["status"]

        if status in ("postponed", "cancelled"):
            for p in entry["picks"]:
                p["result"] = "void"
            entry["finalScore"] = status.upper()
            entry["resolved"]   = True
            resolved_count += 1
            print(f"    → {status.upper()} — all picks void")
            continue

        if status != "finished":
            print(f"    → Status: {status} — skipping")
            skipped_count += 1
            continue

        hg = result["homeGoals"]
        ag = result["awayGoals"]

        if hg is None or ag is None:
            print(f"    → No score data — skipping")
            skipped_count += 1
            continue

        entry["finalScore"] = f"{hg}:{ag}"
        entry["resolved"]   = True

        # Store card totals if available (for dashboard display)
        if result.get("yellowHome") is not None:
            total_c = (result.get("yellowHome") or 0) + (result.get("yellowAway") or 0) + \
                      (result.get("redHome") or 0) + (result.get("redAway") or 0)
            entry["totalCards"] = total_c
        elif "totalCards" in entry:
            pass  # Keep existing value

        wins = losses = voids = 0

        # ── CLV: map marketKey → relevant closing odds field ──────────────
        # Priority: true closing odds (captured at kickoff) > bet odds (at pick save time)
        MARKET_TO_CLOSING_FIELD = {
            "homeWin":  "hw",   "awayWin":  "aw",   "draw":    "dr",
            "btts":     "bttsY", "noBtts":  "bttsN",
            "over25":   "o25",  "under25":  "u25",
            "over35":   "o35",  "under35":  "u35",
            "dc1X":     "dc1X_bkr", "dcX2": "dcX2_bkr",
        }
        closing = entry.get("odds_closing") or entry.get("odds_bet") or {}

        for p in entry["picks"]:
            outcome = evaluate_pick(p["marketKey"], hg, ag, result)
            p["result"] = outcome
            if outcome == "win":    wins += 1
            elif outcome == "loss": losses += 1
            else:                   voids += 1

            # CLV = how much better/worse were our pick odds vs. market closing line
            # Formula: (pick_odds / closing_odds - 1) * 100  [positive = value found]
            if "clv" not in p:   # only compute once (don't overwrite on re-runs)
                pick_odds    = p.get("odds")
                closing_key  = MARKET_TO_CLOSING_FIELD.get(p.get("marketKey", ""))
                closing_odds = closing.get(closing_key) if closing_key else None
                if pick_odds and closing_odds and pick_odds > 1 and closing_odds > 1:
                    p["clv"] = round((pick_odds / closing_odds - 1) * 100, 1)
                else:
                    p["clv"] = None

        # Log card stats if any cards picks were resolved
        card_info = ""
        if result.get("yellowHome") is not None:
            total_c = entry.get("totalCards", 0)
            card_info = f" | 🟨 {total_c} Karten"

        icon = "✅" if wins > 0 else "❌"
        print(f"    → {hg}:{ag}  {icon}  wins={wins} losses={losses} voids={voids}{card_info}")
        resolved_count += 1

    # Save back
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    total       = len(history)
    total_picks = sum(len(e["picks"]) for e in history)
    won_picks   = sum(1 for e in history for p in e["picks"] if p.get("result") == "win")
    lost_picks  = sum(1 for e in history for p in e["picks"] if p.get("result") == "loss")
    wr = round(won_picks / (won_picks + lost_picks) * 100, 1) if (won_picks + lost_picks) > 0 else None

    print(f"\n✅  Resolved {resolved_count} matches  "
          f"(cache:{cache_hits} / sofascore:{sofascore_hits} / skipped:{skipped_count})")
    print(f"   Total history: {total} matches · {total_picks} picks")
    if wr is not None:
        print(f"   Overall win rate: {won_picks}W / {lost_picks}L = {wr}%")
    print(f"   Datei: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
