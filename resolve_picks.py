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

def build_cache_index(cache_file: Path) -> dict:
    """
    Build a lookup dict: eventId → {homeGoals, awayGoals, status,
                                     yellowHome, yellowAway, redHome, redAway}
    from results-cache.json (written by fetch_results.py).
    """
    if not cache_file.exists():
        print("  ⚠️  results-cache.json not found — will use Sofascore fallback only")
        return {}
    with open(cache_file, encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    for fix in data.get("fixtures", []):
        eid = fix.get("id")
        if not eid:
            continue
        status = fix.get("status", "")
        if status == "FT":
            index[eid] = {
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
            index[eid] = {"status": "postponed", "homeGoals": None, "awayGoals": None}
    print(f"  📦 results-cache.json loaded: {len(index)} finished/cancelled fixtures")
    return index


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

    # ── Team-specific goals (e.g. "team_goals_over:1.5") ─────────────────────
    # We can't know which team's goals without more context — void for safety
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

    # Build cache index from results-cache.json (primary source, no rate limits)
    cache_index = build_cache_index(CACHE_FILE)

    # Only process unresolved entries for past matches
    pending = [
        e for e in history
        if not e.get("resolved")
        and e.get("eventId")
        and datetime.date.fromisoformat(e["dateIso"]) < today
    ]
    print(f"  Pending entries: {len(pending)}")

    resolved_count  = 0
    cache_hits      = 0
    sofascore_hits  = 0
    skipped_count   = 0

    for entry in pending:
        event_id = entry["eventId"]
        flag     = entry.get("leagueFlag", "")
        home     = entry["home"]
        away     = entry["away"]
        date_iso = entry["dateIso"]

        # ── Primary: results-cache.json ──────────────────────────────────────
        result = cache_index.get(event_id)

        if result:
            cache_hits += 1
            print(f"  📦 {flag} {home} vs {away} ({date_iso}) → cache hit")
        else:
            # ── Fallback: live Sofascore call ─────────────────────────────
            print(f"  🌐 {flag} {home} vs {away} ({date_iso}) → Sofascore fallback …")
            result = get_match_result_sofascore(event_id)
            time.sleep(0.4)
            if result:
                sofascore_hits += 1
            else:
                print(f"    → Could not fetch event {event_id}")
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
        for p in entry["picks"]:
            outcome = evaluate_pick(p["marketKey"], hg, ag, result)
            p["result"] = outcome
            if outcome == "win":    wins += 1
            elif outcome == "loss": losses += 1
            else:                   voids += 1

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
