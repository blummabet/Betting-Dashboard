#!/usr/bin/env python3
"""
save_picks.py — Mirror + Freeze logic.

BEFORE kick-off: picks_history.json always mirrors picks_output.json (current cards).
                 Existing entries are upserted with the latest pick logic.
AT kick-off + 5 min: entry is frozen — never overwritten again.

This ensures Results Tab stats reflect exactly what the cards showed at kick-off,
regardless of how many times the pick logic changes between now and then.

Workflow order (update-dashboard.yml):
  1. update_dashboard.py   → season-finish.html (fixture data)
  2. node generate_picks.js → picks_output.json  (canonical picks via real JS)
  3. python save_picks.py  → picks_history.json  (mirror + freeze)
"""

import json
import datetime
from pathlib import Path

BASE           = Path(__file__).parent
HISTORY_FILE   = BASE / "picks_history.json"
PICKS_OUTPUT   = BASE / "picks_output.json"
PREMATCH_FILE  = BASE / "prematch-data.json"

# Vienna is UTC+2 (CEST, May–Oct). Kick-off times in prematch-data.json are Vienna local.
VIENNA_UTC_OFFSET = datetime.timedelta(hours=2)
KICKOFF_GRACE     = datetime.timedelta(minutes=5)   # same buffer as findOdds() freeze in JS


def _kickoff_utc(date_iso: str, time_str: str):
    """Return kick-off as UTC datetime, or None on parse error."""
    try:
        d = datetime.date.fromisoformat(date_iso)
        h, m = map(int, time_str.split(':'))
        vienna_dt = datetime.datetime(d.year, d.month, d.day, h, m)
        return vienna_dt - VIENNA_UTC_OFFSET
    except Exception:
        return None


def _is_frozen(date_iso: str, time_str, now_utc: datetime.datetime) -> bool:
    """
    Returns True if the game has kicked off + 5 min → pick should not be changed.
    Falls back to date-only comparison if no kick-off time is available.
    """
    if time_str:
        ko = _kickoff_utc(date_iso, time_str)
        if ko is not None:
            return now_utc >= ko + KICKOFF_GRACE
    # Fallback: no time known → freeze once the date has passed
    try:
        return datetime.date.fromisoformat(date_iso) < now_utc.date()
    except Exception:
        return False


def main():
    now_utc   = datetime.datetime.utcnow()
    today_iso = now_utc.date().isoformat()
    print(f"📝  Save picks (Mirror+Freeze) — {today_iso}  UTC {now_utc.strftime('%H:%M')}")

    if not PICKS_OUTPUT.exists():
        print("  ❌  picks_output.json not found — run 'node generate_picks.js' first")
        return

    with open(PICKS_OUTPUT, encoding="utf-8") as f:
        generated = json.load(f)
    print(f"  📦 {len(generated)} fixtures from picks_output.json")

    # ── Load kick-off times + odds snapshots from prematch-data.json ─────────
    # Key: "HomeTeamName|AwayTeamName"  →  {date, time, odds_open, odds_closing, hw/dr/aw}
    kickoff_map: dict[str, dict] = {}
    if PREMATCH_FILE.exists():
        try:
            with open(PREMATCH_FILE, encoding="utf-8") as f:
                pm = json.load(f)
            for fx in pm.get("fixtures", []):
                key = f"{fx.get('homeTeamName', '')}|{fx.get('awayTeamName', '')}"
                kickoff_map[key] = {
                    "date":         fx.get("date", ""),
                    "time":         fx.get("time"),
                    "odds_open":    fx.get("odds_open"),
                    "odds_closing": fx.get("odds_closing"),
                    "hw": fx.get("hw"), "dr": fx.get("dr"), "aw": fx.get("aw"),
                    "bttsY": fx.get("bttsY"), "o25": fx.get("o25"),
                    "dc1X_bkr": fx.get("dc1X_bkr"), "dcX2_bkr": fx.get("dcX2_bkr"),
                }
            print(f"  🕐 {len(kickoff_map)} kick-off times + odds snapshots loaded from prematch-data.json")
        except Exception as e:
            print(f"  ⚠️  Could not load prematch-data.json: {e}")

    # ── Load existing history ────────────────────────────────────────────────
    history: list[dict] = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)

    history_by_id: dict[str, int] = {e["id"]: i for i, e in enumerate(history)}

    # ── Build fresh-picks lookup ─────────────────────────────────────────────
    fresh_by_id: dict[str, dict] = {}
    for fx in generated:
        date_iso = fx.get("dateIso", "")
        mid = (
            f"{date_iso}-{fx.get('league', 'UNK')}-{fx.get('home', '')}-{fx.get('away', '')}"
            .replace(" ", "_").replace("/", "-")
        )
        fresh_by_id[mid] = fx

    def _get_kickoff_info(fx_or_entry: dict) -> tuple[str, object]:
        """Look up (date_iso, time_str) from prematch-data, fall back to entry fields."""
        home = fx_or_entry.get("home", "") or fx_or_entry.get("homeTeamName", "")
        away = fx_or_entry.get("away", "") or fx_or_entry.get("awayTeamName", "")
        pm   = kickoff_map.get(f"{home}|{away}", {})
        date_iso = pm.get("date") or fx_or_entry.get("dateIso", "")
        time_str = pm.get("time")   # None if not found → fallback to date-only check
        return date_iso, time_str

    def _get_odds_snapshots(fx_or_entry: dict) -> dict:
        """Return odds_open and odds_bet snapshots from prematch-data for CLV tracking."""
        home = fx_or_entry.get("home", "") or fx_or_entry.get("homeTeamName", "")
        away = fx_or_entry.get("away", "") or fx_or_entry.get("awayTeamName", "")
        pm   = kickoff_map.get(f"{home}|{away}", {})
        return {
            "odds_open":    pm.get("odds_open"),   # first snapshot ever (set once)
            "odds_bet":     {                       # current odds at pick-save time
                k: pm.get(k) for k in ("hw", "dr", "aw", "bttsY", "o25", "dc1X_bkr", "dcX2_bkr")
                if pm.get(k) is not None
            } or None,
        }

    def _build_pick_entries(picks: list, old_picks: list | None = None) -> list:
        """Convert picks_output picks to history format, preserving isTopCard flags."""
        result = []
        for i, p in enumerate(picks):
            old = old_picks[i] if old_picks and i < len(old_picks) else {}
            result.append({
                "market":    p.get("market",    ""),
                "marketKey": p.get("marketKey", ""),
                "icon":      p.get("icon",      ""),
                "conf":      p.get("conf",      "medium"),
                "sc":        p.get("sc",        0),
                "odds":      p.get("odds"),
                "result":    None,
                "isTopCard": old.get("isTopCard", False),
            })
        return result

    added    = 0
    updated  = 0
    frozen_c = 0
    skipped  = 0

    # ── Process all fresh picks ──────────────────────────────────────────────
    for mid, fx in fresh_by_id.items():
        picks = fx.get("picks", [])
        if not picks:
            skipped += 1
            continue

        date_iso, time_str = _get_kickoff_info(fx)
        frozen = _is_frozen(date_iso, time_str, now_utc)

        if mid in history_by_id:
            e = history[history_by_id[mid]]

            # Already resolved (result known) → skip entirely
            if e.get("resolved"):
                frozen_c += 1
                continue

            # Just kicked off → capture closing odds snapshot (once), then freeze
            if frozen:
                if not e.get("odds_closing"):
                    # First time we see this entry as frozen → save closing line
                    pm_info = kickoff_map.get(f"{e.get('home','')}|{e.get('away','')}", {})
                    closing = pm_info.get("odds_closing") or {
                        k: pm_info.get(k)
                        for k in ("hw", "dr", "aw", "bttsY", "o25", "dc1X_bkr", "dcX2_bkr")
                        if pm_info.get(k) is not None
                    } or None
                    if closing:
                        e["odds_closing"] = closing
                frozen_c += 1
                continue

            # Pre-kick-off → mirror current picks
            old_keys = [p.get("marketKey", "") for p in e.get("picks", [])]
            new_keys = [p.get("marketKey", "") for p in picks]
            old_odds = [p.get("odds")           for p in e.get("picks", [])]
            new_odds = [p.get("odds")           for p in picks]

            if old_keys == new_keys and old_odds == new_odds:
                continue  # no meaningful change

            e["picks"]     = _build_pick_entries(picks, e.get("picks"))
            e["matchScore"] = fx.get("matchScore")
            e["savedAt"]   = now_utc.isoformat() + "Z"
            updated += 1
            flag = fx.get("leagueFlag", "")
            labels = ", ".join(p["market"] for p in e["picks"])
            print(f"  🔄 {flag} {fx.get('home')} vs {fx.get('away')} ({date_iso}) → {labels}")

        else:
            # New entry — only add if game hasn't kicked off yet
            if frozen:
                frozen_c += 1
                continue

            odds_snaps = _get_odds_snapshots(fx)
            entry = {
                "id":         mid,
                "date":       fx.get("date", ""),
                "dateIso":    date_iso,
                "league":     fx.get("league", "UNK"),
                "leagueName": fx.get("leagueName", ""),
                "leagueFlag": fx.get("leagueFlag", ""),
                "home":       fx.get("home", ""),
                "away":       fx.get("away", ""),
                "eventId":    fx.get("eventId"),
                "matchScore": fx.get("matchScore"),
                "picks":      _build_pick_entries(picks),
                "odds_open":  odds_snaps["odds_open"],   # opening line snapshot
                "odds_bet":   odds_snaps["odds_bet"],    # odds at time of pick (for CLV)
                "finalScore": None,
                "resolved":   False,
                "savedAt":    now_utc.isoformat() + "Z",
            }
            history.append(entry)
            history_by_id[mid] = len(history) - 1
            added += 1
            flag   = fx.get("leagueFlag", "")
            labels = ", ".join(p["market"] for p in entry["picks"])
            print(f"  + {flag} {fx.get('home')} vs {fx.get('away')} ({date_iso}) → {labels}")

    # ── Mark top picks (isTopCard) for today's entries ────────────────────────
    # Mirrors JS buildTopCardsHtml(): sc*10 + conf bonus + matchScore bonus.
    # Top 7 picks (rank ≥ 12, max 2 per match) get isTopCard=True.
    today_entries = [e for e in history if e.get("dateIso") == today_iso]
    if today_entries:
        for e in today_entries:
            for p in e["picks"]:
                p["isTopCard"] = False

        candidates = []
        for e in today_entries:
            ms = e.get("matchScore") or 0
            if ms < 10:
                continue
            for idx, p in enumerate(e["picks"]):
                sc   = p.get("sc") or 0
                conf = p.get("conf", "low")
                rank = sc * 10
                rank += 4 if conf == "high" else 1 if conf == "medium" else 0
                rank += (ms - 6) * 2
                candidates.append((rank, e["id"], idx))

        candidates.sort(key=lambda x: -x[0])
        match_counts: dict[str, int] = {}
        top_count = 0
        for rank, eid, pidx in candidates:
            if rank < 12 or top_count >= 7:
                break
            if match_counts.get(eid, 0) >= 2:
                continue
            for e in today_entries:
                if e["id"] == eid:
                    e["picks"][pidx]["isTopCard"] = True
                    match_counts[eid] = match_counts.get(eid, 0) + 1
                    top_count += 1
                    break

        top_labels = [
            f"{e.get('leagueFlag', '')} {e['home']} vs {e['away']} → {p['market']}"
            for e in today_entries for p in e["picks"] if p.get("isTopCard")
        ]
        print(f"\n🃏  Top Picks ({top_count}):")
        for lbl in top_labels:
            print(f"   ⭐ {lbl}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\n✅  +{added} neu  🔄{updated} gespiegelt  🔒{frozen_c} eingefroren  (total: {len(history)})")
    print(f"   Datei: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
