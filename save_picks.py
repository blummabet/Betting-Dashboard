#!/usr/bin/env python3
"""
save_picks.py — Reads matches_today.json, generates picks using simplified
                scoring logic, and appends new entries to picks_history.json.

Run after update_dashboard.py. Skips matches already recorded for today.
"""

import json
import datetime
from pathlib import Path

BASE = Path(__file__).parent
MATCHES_FILE  = BASE / "matches_today.json"
HISTORY_FILE  = BASE / "picks_history.json"


# ── Simplified pick scoring (mirrors JS getBettingPicks logic) ────────────────

def pick_market_key(market: str) -> str:
    """Map German market label to a short key for stats grouping."""
    m = market.lower()
    if "heimsieg" in m:       return "homeWin"
    if "auswärtssieg" in m:   return "awayWin"
    if "unentschieden" in m:  return "draw"
    if "über 3.5" in m:       return "over35"
    if "unter 3.5" in m:      return "under35"
    if "über 2.5" in m:       return "over25"
    if "unter 2.5" in m:      return "under25"
    if "beide" in m:           return "btts"
    if "keine" in m:           return "noBtts"
    if "über 9.5" in m:       return "over95corners"
    if "unter 9.5" in m:      return "under95corners"
    return "other"


def generate_picks(match: dict) -> list[dict]:
    """
    Simplified Python equivalent of JS getBettingPicks().
    Returns list of {market, marketKey, conf, sc, icon} sorted by sc desc.
    """
    picks = []

    home_stake = match.get("homeStake") or {}
    away_stake = match.get("awayStake") or {}
    home_form  = match.get("homeForm")  or {}
    away_form  = match.get("awayForm")  or {}
    h2h        = match.get("h2h")       or {}
    rl         = match.get("roundsLeft", 99)

    hs = home_stake.get("score", 0) or 0   # 1–10 stake score
    as_ = away_stake.get("score", 0) or 0
    hfs = home_form.get("formScore", 0) or 0
    afs = away_form.get("formScore", 0) or 0
    hwr = home_form.get("homeWinRate") or 0
    awr = away_form.get("awayWinRate") or 0

    h_colors = [lb.get("c","") for lb in (home_stake.get("labels") or [])]
    a_colors = [lb.get("c","") for lb in (away_stake.get("labels") or [])]

    home_needs_win = rl <= 6 and ("red" in h_colors or "gold" in h_colors)
    away_needs_win = rl <= 6 and ("red" in a_colors or "gold" in a_colors)
    both_need_win  = home_needs_win and away_needs_win
    urgency_high   = rl <= 3

    # ── 1X2 picks ────────────────────────────────────────────────────────────
    # Heimsieg
    sc_h = 0.50
    sc_h += min(0.20, hs / 50)
    sc_h += min(0.10, hfs / 100) if hfs else 0
    sc_h += min(0.10, hwr * 0.25)
    if home_needs_win and not away_needs_win:
        sc_h += 0.20 if urgency_high else 0.11
    if both_need_win:
        sc_h += 0.10 if urgency_high else 0.06
    if h2h.get("games", 0) >= 3:
        n = h2h["games"]
        sc_h += min(0.08, (h2h.get("homeWins", 0) / n) * 0.15)
    picks.append({"market": "Heimsieg", "marketKey": "homeWin", "icon": "🏠", "sc": round(min(0.95, sc_h), 3)})

    # Auswärtssieg
    sc_a = 0.38
    sc_a += min(0.18, as_ / 55)
    sc_a += min(0.10, afs / 100) if afs else 0
    sc_a += min(0.10, awr * 0.25)
    if away_needs_win and not home_needs_win:
        sc_a += 0.20 if urgency_high else 0.11
    if both_need_win:
        sc_a += 0.10 if urgency_high else 0.06
    if h2h.get("games", 0) >= 3:
        n = h2h["games"]
        sc_a += min(0.08, (h2h.get("awayWins", 0) / n) * 0.15)
    picks.append({"market": "Auswärtssieg", "marketKey": "awayWin", "icon": "✈️", "sc": round(min(0.90, sc_a), 3)})

    # ── Goals picks ──────────────────────────────────────────────────────────
    avg_goals_h = home_form.get("avgGoals", 2.5) or 2.5
    avg_goals_a = away_form.get("avgGoals", 2.5) or 2.5
    avg_total   = (avg_goals_h + avg_goals_a) / 2

    # Über 2.5
    sc_o25 = 0.50 + min(0.25, (avg_total - 2.5) * 0.15)
    if both_need_win: sc_o25 += 0.18 if urgency_high else 0.10
    picks.append({"market": "Über 2.5 Tore", "marketKey": "over25", "icon": "⚽", "sc": round(min(0.90, sc_o25), 3)})

    # Unter 2.5
    sc_u25 = 0.50 - min(0.20, (avg_total - 2.5) * 0.12)
    if both_need_win: sc_u25 = max(0.05, sc_u25 - 0.15)
    picks.append({"market": "Unter 2.5 Tore", "marketKey": "under25", "icon": "🔒", "sc": round(max(0.05, sc_u25), 3)})

    # Beide treffen
    h_scored = home_form.get("avgScored", 1.3) or 1.3
    a_scored = away_form.get("avgScored", 1.0) or 1.0
    sc_btts = 0.45 + min(0.20, (h_scored + a_scored - 2.0) * 0.10)
    if both_need_win: sc_btts += 0.12 if urgency_high else 0.07
    picks.append({"market": "Beide Teams treffen", "marketKey": "btts", "icon": "🎯", "sc": round(min(0.85, sc_btts), 3)})

    # Sort by sc descending, keep top 3
    picks.sort(key=lambda p: -p["sc"])
    top = picks[:3]

    # Assign confidence
    for p in top:
        if p["sc"] >= 0.70:   p["conf"] = "high"
        elif p["sc"] >= 0.58: p["conf"] = "medium"
        else:                  p["conf"] = "low"

    return top


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today_iso = datetime.date.today().isoformat()
    print(f"📝  Save picks — {today_iso}")

    if not MATCHES_FILE.exists():
        print("  ⚠️  matches_today.json not found — run update_dashboard.py first")
        return

    with open(MATCHES_FILE, encoding="utf-8") as f:
        matches = json.load(f)

    # Load existing history
    history = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)

    # Build set of already-saved match IDs for today
    saved_ids = {
        e["id"] for e in history
        if e.get("dateIso") == today_iso
    }

    added = 0
    for match in matches:
        mid = f"{today_iso}-{match['league']}-{match['home']}-{match['away']}"
        mid = mid.replace(" ", "_").replace("/", "-")

        if mid in saved_ids:
            continue  # Already saved today

        picks = generate_picks(match)
        if not picks:
            continue

        entry = {
            "id":          mid,
            "date":        match["date"],
            "dateIso":     today_iso,
            "league":      match["league"],
            "leagueName":  match["leagueName"],
            "leagueFlag":  match["leagueFlag"],
            "home":        match["home"],
            "away":        match["away"],
            "eventId":     match.get("eventId"),
            "matchScore":  match.get("matchScore"),
            "picks":       [
                {
                    "market":    p["market"],
                    "marketKey": p["marketKey"],
                    "icon":      p["icon"],
                    "conf":      p["conf"],
                    "sc":        p["sc"],
                    "odds":      None,   # Will be filled by resolve_picks.py
                    "result":    None,   # null = pending
                }
                for p in picks
            ],
            "finalScore":  None,
            "resolved":    False,
            "savedAt":     datetime.datetime.utcnow().isoformat() + "Z",
        }
        history.append(entry)
        added += 1
        print(f"  + {match['leagueFlag']} {match['home']} vs {match['away']}  →  {', '.join(p['market'] for p in picks)}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {added} neue Einträge gespeichert  (total: {len(history)})")
    print(f"   Datei: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
