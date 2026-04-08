#!/usr/bin/env python3
"""
resolve_picks.py — Fetches final scores from Sofascore for completed matches
                   and marks picks in picks_history.json as win / loss / void.

Run daily (after matches have finished).
"""

import json
import urllib.request
import urllib.error
import datetime
import time
from pathlib import Path

BASE         = Path(__file__).parent
HISTORY_FILE = BASE / "picks_history.json"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":          "application/json",
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Sofascore fetch ───────────────────────────────────────────────────────────

def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    ⚠️  Fetch failed: {url} — {e}")
        return None


def get_match_result(event_id: int) -> dict | None:
    """
    Returns {homeGoals, awayGoals, status} for a Sofascore event.
    status: 'finished' | 'inprogress' | 'notstarted' | 'postponed' | 'cancelled'
    """
    data = fetch(f"https://api.sofascore.com/api/v1/event/{event_id}")
    if not data or "event" not in data:
        return None
    ev  = data["event"]
    st  = ev.get("status", {}).get("type", "notstarted")
    hg  = (ev.get("homeScore") or {}).get("current")
    ag  = (ev.get("awayScore") or {}).get("current")
    if st == "finished" and hg is not None and ag is not None:
        return {"homeGoals": int(hg), "awayGoals": int(ag), "status": "finished"}
    return {"status": st, "homeGoals": None, "awayGoals": None}


# ── Win/loss determination ────────────────────────────────────────────────────

def evaluate_pick(market_key: str, home_goals: int, away_goals: int) -> str:
    """Returns 'win', 'loss', or 'void'."""
    total = home_goals + away_goals
    rules = {
        "homeWin":        home_goals > away_goals,
        "awayWin":        away_goals > home_goals,
        "draw":           home_goals == away_goals,
        "over25":         total > 2,
        "under25":        total < 3,
        "over35":         total > 3,
        "under35":        total < 4,
        "btts":           home_goals > 0 and away_goals > 0,
        "noBtts":         home_goals == 0 or away_goals == 0,
    }
    if market_key not in rules:
        return "void"
    return "win" if rules[market_key] else "loss"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.date.today()
    print(f"🔍  Resolve picks — {today.isoformat()}")

    if not HISTORY_FILE.exists():
        print("  ℹ️  picks_history.json not found — nothing to resolve yet")
        return

    with open(HISTORY_FILE, encoding="utf-8") as f:
        history = json.load(f)

    pending = [e for e in history if not e.get("resolved") and e.get("eventId")]
    print(f"  Pending entries: {len(pending)}")

    resolved_count = 0
    skipped_count  = 0

    for entry in pending:
        match_date = datetime.date.fromisoformat(entry["dateIso"])

        # Only try to resolve if the match was scheduled for yesterday or earlier
        # (gives time for the result to appear on Sofascore)
        if match_date >= today:
            skipped_count += 1
            continue

        event_id = entry["eventId"]
        print(f"\n  Checking {entry['leagueFlag']} {entry['home']} vs {entry['away']} ({entry['dateIso']}) …")

        result = get_match_result(event_id)
        time.sleep(0.4)  # be polite to Sofascore

        if result is None:
            print(f"    → Could not fetch event {event_id}")
            continue

        status = result["status"]
        if status in ("postponed", "cancelled"):
            # Mark all picks as void
            for p in entry["picks"]:
                p["result"] = "void"
            entry["finalScore"] = status.upper()
            entry["resolved"]   = True
            resolved_count += 1
            print(f"    → {status.upper()} — all picks void")
            continue

        if status != "finished":
            print(f"    → Status: {status} — skipping")
            continue

        hg = result["homeGoals"]
        ag = result["awayGoals"]
        entry["finalScore"] = f"{hg}:{ag}"
        entry["resolved"]   = True

        wins = losses = voids = 0
        for p in entry["picks"]:
            outcome = evaluate_pick(p["marketKey"], hg, ag)
            p["result"] = outcome
            if outcome == "win":   wins += 1
            elif outcome == "loss": losses += 1
            else:                  voids += 1

        result_icon = "✅" if wins > 0 else "❌"
        print(f"    → {hg}:{ag}  {result_icon}  wins={wins} losses={losses} voids={voids}")
        resolved_count += 1

    # Save back
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    total       = len(history)
    total_picks = sum(len(e["picks"]) for e in history)
    won_picks   = sum(1 for e in history for p in e["picks"] if p.get("result") == "win")
    lost_picks  = sum(1 for e in history for p in e["picks"] if p.get("result") == "loss")
    wr = round(won_picks / (won_picks + lost_picks) * 100, 1) if (won_picks + lost_picks) > 0 else None

    print(f"\n✅  Resolved {resolved_count} matches  (skipped {skipped_count} future)")
    print(f"   Total history: {total} matches · {total_picks} picks")
    if wr is not None:
        print(f"   Overall win rate: {won_picks}W / {lost_picks}L = {wr}%")
    print(f"   Datei: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
