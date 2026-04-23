#!/usr/bin/env python3
"""
save_picks.py — Reads fixture data from season-finish.html and saves
                top picks per match to picks_history.json.

Uses the real embedded fixture data (pressure, form, H2H, stake labels)
to generate picks that closely match the JS dashboard cards.

Odds enrichment: prematch-data.json is loaded to apply the same AH substitution
logic as the browser — when hw < 1.35 (home strong favourite), the result pick
is replaced with the best AH line from ah_home_lines (or standard ah_h fallback).
"""

import json
import re
import datetime
from pathlib import Path

BASE            = Path(__file__).parent
HTML_FILE       = BASE / "season-finish.html"
HISTORY_FILE    = BASE / "picks_history.json"
PREMATCH_FILE   = BASE / "prematch-data.json"


# ── Prematch odds lookup (from prematch-data.json) ────────────────────────────

def _norm(s: str) -> str:
    """Normalize team name for fuzzy matching (same approach as JS norm())."""
    import unicodedata
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # strip diacritics
    s = re.sub(r"\b(fc|sv|sc|ac|ss|rc|sk|tsv|rb|vfb|bsc|vfl|as|us|cd|cf)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def load_prematch_odds() -> dict:
    """
    Returns a dict keyed by (norm_home, norm_away) → odds dict from prematch-data.json.
    Includes hw, aw, ah_h, ah_h_point, ah_a, ah_a_point, ah_home_lines, ah_away_lines.
    """
    if not PREMATCH_FILE.exists():
        return {}
    try:
        with open(PREMATCH_FILE, encoding="utf-8") as f:
            data = json.load(f)
        lookup = {}
        for fx in data.get("fixtures", []):
            o = fx.get("odds") or {}
            if not o:
                continue
            h = _norm(fx.get("homeTeamName", ""))
            a = _norm(fx.get("awayTeamName", ""))
            if h and a:
                lookup[(h, a)] = o
        return lookup
    except Exception:
        return {}

def find_prematch_odds(lookup: dict, home: str, away: str) -> dict | None:
    """Fuzzy-match home/away team names against prematch lookup."""
    hn, an = _norm(home), _norm(away)
    # Exact match first
    if (hn, an) in lookup:
        return lookup[(hn, an)]
    # Partial match: one name contains the other
    for (lh, la), odds in lookup.items():
        hm = lh == hn or lh in hn or hn in lh
        am = la == an or la in an or an in la
        if hm and am:
            return odds
    return None

def pick_best_line(lines: list, target: float = 1.62) -> dict | None:
    """Mirror of JS _pickBestLine — returns {pt, price} closest to target odds."""
    if not lines:
        return None
    return min(lines, key=lambda l: abs(l.get("price", 99) - target))


# ── Parse fixture data from season-finish.html ────────────────────────────────

def extract_fixtures_from_html(html: str) -> list[dict]:
    """
    Parse all league fixture blocks from the embedded data object in the HTML.
    Returns flat list of fixture dicts with added _league/_leagueName/_leagueFlag/_roundsLeft.
    """
    league_block_pattern = re.compile(
        r'([A-Z][A-Z0-9]*):\{name:"([^"]+)",flag:"([^"]+)",roundsLeft:(\d+)',
    )
    all_fixtures = []

    for league_match in league_block_pattern.finditer(html):
        pos        = league_match.start()
        league_code = league_match.group(1)
        league_name = league_match.group(2)
        league_flag = league_match.group(3)
        rounds_left = int(league_match.group(4))

        # Find the first fixtures:[ after this league header (within 6000 chars)
        fx_pos = html.find("fixtures:[", pos)
        if fx_pos == -1 or fx_pos > pos + 6000:
            continue

        # Extract the JSON array with matched bracket counting
        bracket_start = fx_pos + len("fixtures:")
        depth = 0
        i = bracket_start
        while i < len(html):
            if html[i] == "[":   depth += 1
            elif html[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1

        fixtures_str = html[bracket_start:i + 1]
        try:
            fixtures = json.loads(fixtures_str)
        except json.JSONDecodeError:
            continue

        for fx in fixtures:
            fx["_league"]     = league_code
            fx["_leagueName"] = league_name
            fx["_leagueFlag"] = league_flag
            fx["_roundsLeft"] = rounds_left
        all_fixtures.extend(fixtures)

    return all_fixtures


# ── Pick generation logic ─────────────────────────────────────────────────────

def get_colors(stake: dict | None) -> list[str]:
    """Extract label colors from a stake object."""
    if not stake:
        return []
    return [lb.get("c", "") for lb in (stake.get("labels") or [])]


def score_result(fx: dict) -> tuple[str, str, float]:
    """
    Returns (market_key, market_label, score) for the best result pick.
    Mirrors the JS PICK 1 logic using available fixture data.
    """
    rl          = fx.get("_roundsLeft", 99)
    h_stake     = fx.get("homeStake") or {}
    a_stake     = fx.get("awayStake") or {}
    h_form      = fx.get("homeForm")  or {}
    a_form      = fx.get("awayForm")  or {}
    h2h         = fx.get("h2h")       or {}

    h_colors    = get_colors(h_stake)
    a_colors    = get_colors(a_stake)

    pressure_rl    = rl <= 6
    home_needs_win = pressure_rl and any(c in h_colors for c in ("red", "gold", "blue", "orange", "purple"))
    away_needs_win = pressure_rl and any(c in h_colors for c in ("red", "gold", "blue", "orange", "purple"))
    away_needs_win = pressure_rl and any(c in a_colors for c in ("red", "gold", "blue", "orange", "purple"))
    urgency_high   = rl <= 3

    h_pr = h_stake.get("pressureRatio", 0) or 0
    a_pr = a_stake.get("pressureRatio", 0) or 0
    h_mw = h_stake.get("mustWin", False)
    a_mw = a_stake.get("mustWin", False)

    # Form-based scores
    h_fs   = h_form.get("formScore", 0.5) or 0.5
    a_fs   = a_form.get("formScore", 0.5) or 0.5
    h_hwr  = h_form.get("homeWinRate") or 0
    a_awr  = a_form.get("awayWinRate") or 0

    h2h_n   = h2h.get("games", 0)
    h2h_hw  = h2h.get("homeWins", 0) / h2h_n if h2h_n >= 3 else 0.5
    h2h_aw  = h2h.get("awayWins", 0) / h2h_n if h2h_n >= 3 else 0.3

    # Heimsieg score
    sc_h = 0.52
    sc_h += min(0.18, h_fs * 0.25)
    sc_h += min(0.08, h_hwr * 0.20)
    sc_h += min(0.06, h2h_hw * 0.10)
    if h_mw and not a_mw:
        sc_h += 0.20 if urgency_high else 0.12
    elif h_mw and a_mw:
        sc_h += 0.08 if urgency_high else 0.05
    if a_mw and not h_mw:
        sc_h = max(0, sc_h - 0.08)  # Away needs win hurts home win case
    # H2H dominance by home side
    sc_h += min(0.06, (h2h_hw - 0.4) * 0.15) if h2h_n >= 5 else 0
    sc_h = min(0.95, sc_h)

    # Auswärtssieg score
    sc_a = 0.36
    sc_a += min(0.18, a_fs * 0.22)
    sc_a += min(0.08, a_awr * 0.20)
    sc_a += min(0.06, h2h_aw * 0.10)
    if a_mw and not h_mw:
        sc_a += 0.20 if urgency_high else 0.12
    elif a_mw and h_mw:
        sc_a += 0.08 if urgency_high else 0.05
    if h_mw and not a_mw:
        sc_a = max(0, sc_a - 0.06)
    sc_a += min(0.06, (h2h_aw - 0.3) * 0.15) if h2h_n >= 5 else 0
    sc_a = min(0.90, sc_a)

    # Draw score (high H2H draw rate, both mid-table)
    h2h_dr  = h2h.get("draws", 0) / h2h_n if h2h_n >= 3 else 0
    sc_d    = 0.25 + min(0.20, h2h_dr * 0.60)
    if not h_mw and not a_mw:
        sc_d += 0.06
    sc_d = min(0.70, sc_d)

    # Pick best result
    if sc_h >= sc_a and sc_h >= sc_d:
        return ("homeWin",  "🏠 Heimsieg",       sc_h)
    elif sc_a >= sc_h and sc_a >= sc_d:
        return ("awayWin",  "✈️ Auswärtssieg",   sc_a)
    else:
        return ("draw",     "🤝 Unentschieden",  sc_d)


def score_goals(fx: dict) -> tuple[str, str, float]:
    """
    Returns (market_key, market_label, score) for the best goals pick.
    """
    h_form   = fx.get("homeForm")  or {}
    a_form   = fx.get("awayForm")  or {}
    h2h      = fx.get("h2h")       or {}
    rl       = fx.get("_roundsLeft", 99)
    h_stake  = fx.get("homeStake") or {}
    a_stake  = fx.get("awayStake") or {}

    h_gpg   = h_form.get("goalsPerGame", 1.3) or 1.3
    a_gpg   = a_form.get("goalsPerGame", 1.0) or 1.0
    h2h_avg = h2h.get("avgGoals") or (h_gpg + a_gpg)
    # Expected goals: blend of form and H2H
    exp_g   = (h_gpg + a_gpg) * 0.7 + h2h_avg * 0.3

    h_mw    = h_stake.get("mustWin", False)
    a_mw    = a_stake.get("mustWin", False)
    both_mw = h_mw and a_mw
    any_mw  = h_mw or a_mw
    pressure_rl = rl <= 6
    _pb     = (0.28 if rl <= 1 else 0.22 if rl <= 2 else 0.16 if rl <= 3
               else 0.11 if rl <= 4 else 0.08 if rl <= 5 else 0.06 if rl <= 6 else 0)

    # Over 2.5
    sc_o25  = (0.78 if exp_g > 3.2 else 0.66 if exp_g > 2.8 else
               0.52 if exp_g > 2.5 else 0.30 if exp_g > 2.2 else 0.10)
    if exp_g < 2.5:
        sc_o25 = None  # Hard gate
    else:
        if both_mw and pressure_rl:   sc_o25 = min(0.90, sc_o25 + _pb * 0.70)
        elif any_mw and pressure_rl:  sc_o25 = min(0.88, sc_o25 + _pb * 0.45)

    # Under 2.5
    sc_u25  = (0.85 if exp_g < 1.7 else 0.72 if exp_g < 2.0 else
               0.57 if exp_g < 2.3 else 0.34 if exp_g < 2.6 else 0.12)
    if any_mw and pressure_rl:
        sc_u25 = max(0, sc_u25 - _pb * 0.65)

    # BTTS
    h_att   = h_form.get("avgScored", h_gpg) or h_gpg
    a_att   = a_form.get("avgScored", a_gpg) or a_gpg
    h_def   = h_form.get("concededPerGame", 1.2) or 1.2
    a_def   = a_form.get("concededPerGame", 1.2) or 1.2
    sc_btts = 0.14
    sc_btts += min(0.22, max(0, (h_att - 0.95) * 0.38))
    sc_btts += min(0.20, max(0, (a_att - 0.80) * 0.44))
    sc_btts += min(0.14, max(0, (h_def - 0.80) * 0.30))
    sc_btts += min(0.12, max(0, (a_def - 0.80) * 0.30))
    if both_mw and pressure_rl:   sc_btts = min(0.90, sc_btts + _pb * 1.30)
    elif any_mw and pressure_rl:  sc_btts = min(0.86, sc_btts + _pb * 0.80)

    # Pick best goals market
    candidates = [
        ("btts",    "🎯 Beide Teams treffen", sc_btts),
        ("under25", "🔒 Unter 2.5 Tore",     sc_u25),
    ]
    if sc_o25 is not None:
        candidates.append(("over25", "⚽ Über 2.5 Tore", sc_o25))
    candidates.sort(key=lambda x: -x[2])
    return candidates[0]


def score_cards(fx: dict) -> tuple[str, str, float] | None:
    """
    Returns cards pick if pressure signals are strong enough, else None.
    Mirrors JS cards pick logic (cardsHigh / cardsVeryHigh).
    """
    rl       = fx.get("_roundsLeft", 99)
    h_stake  = fx.get("homeStake") or {}
    a_stake  = fx.get("awayStake") or {}
    h_colors = get_colors(h_stake)
    a_colors = get_colors(a_stake)

    h_pr    = h_stake.get("pressureRatio", 0) or 0
    a_pr    = a_stake.get("pressureRatio", 0) or 0
    h_red   = "red" in h_colors
    a_red   = "red" in a_colors
    h_gold  = "gold" in h_colors
    a_gold  = "gold" in a_colors

    both_red        = h_red and a_red
    any_red         = h_red or a_red
    any_gold        = h_gold or a_gold
    red_vs_gold     = any_red and any_gold and not both_red
    urgency_high    = rl <= 3

    _pb = (0.28 if rl <= 1 else 0.22 if rl <= 2 else 0.16 if rl <= 3
           else 0.11 if rl <= 4 else 0.08 if rl <= 5 else 0.06 if rl <= 6 else 0)

    # Classify card pressure (mirrors JS cardsVeryHigh / cardsHigh)
    cards_very_high = both_red and rl <= 6
    cards_high      = (any_red and rl <= 6) or red_vs_gold or (both_red and rl <= 8)

    if cards_very_high:
        sc       = min(0.96, 0.90 + _pb * 0.30)
        market   = "Über 4.5 Karten"
        mkt_key  = "cards45"
    elif cards_high:
        sc       = min(0.88, 0.66 + _pb * 0.50)
        market   = "Über 4.5 Karten" if urgency_high else "Über 3.5 Karten"
        mkt_key  = "cards45" if urgency_high else "cards35"
    elif any_red and rl <= 6 and (h_pr >= 0.5 or a_pr >= 0.5):
        sc       = min(0.60, 0.35 + _pb * 0.30)
        market   = "Über 3.5 Karten"
        mkt_key  = "cards35"
    else:
        return None  # Not enough signal

    if sc < 0.45:  # Below medium threshold — skip
        return None

    icon = "🟨"
    label = f"{icon} {market}"
    return (mkt_key, label, sc)


def generate_picks(fx: dict, pm_odds: dict | None = None) -> list[dict]:
    """
    Generate top picks for a fixture, mirroring JS getBettingPicks() category logic:
    1 result pick + 1 goals pick + optional cards pick (specialist).

    pm_odds: odds dict from prematch-data.json — used for AH substitution (hw < 1.35).
    """
    result_key, result_label, result_sc   = score_result(fx)
    goals_key,  goals_label,  goals_sc    = score_goals(fx)
    cards_pick = score_cards(fx)

    picks = []

    # Confidence thresholds (mirror dashboard)
    def conf(sc, h=0.68, m=0.48):
        return "high" if sc >= h else "medium" if sc >= m else "low"

    # ── AH substitution (mirrors JS logic: hw/aw < 1.35 → show AH pick) ───────
    # Also override score_result if odds clearly indicate a different direction
    # (e.g. aw=1.10 but score_result picked homeWin from fixture data signals)
    result_odds = None
    if pm_odds:
        hw = pm_odds.get("hw")
        aw = pm_odds.get("aw")
        # Correct direction if odds strongly disagree with fixture-data result pick
        if hw and aw:
            if hw < 1.35 and result_key != "homeWin":
                result_key, result_label, result_sc = "homeWin", "🏠 Heimsieg", result_sc
            elif aw < 1.35 and result_key != "awayWin":
                result_key, result_label, result_sc = "awayWin", "✈️ Auswärtssieg", result_sc
        # Home favourite → AH Heim
        if result_key == "homeWin" and hw and hw < 1.35:
            ah_lines = pm_odds.get("ah_home_lines") or []
            best     = pick_best_line(ah_lines, 1.62) if ah_lines else None
            ah_odds  = best["price"] if best else pm_odds.get("ah_h")
            ah_pt    = best["pt"]    if best else pm_odds.get("ah_h_point")
            if ah_odds and 1.35 <= ah_odds <= 2.05:
                pt_str       = f" {'+' if ah_pt >= 0 else ''}{ah_pt}" if ah_pt is not None else ""
                result_key   = f"ah_home:{ah_pt}" if ah_pt is not None else "ah_home"
                result_label = f"🏠 AH Heim{pt_str}"
                result_odds  = round(ah_odds, 2)
        # Away favourite → AH Ausw.
        elif result_key == "awayWin" and aw and aw < 1.35:
            ah_lines = pm_odds.get("ah_away_lines") or []
            best     = pick_best_line(ah_lines, 1.62) if ah_lines else None
            ah_odds  = best["price"] if best else pm_odds.get("ah_a")
            ah_pt    = best["pt"]    if best else pm_odds.get("ah_a_point")
            if ah_odds and 1.35 <= ah_odds <= 2.05:
                pt_str       = f" {'+' if ah_pt >= 0 else ''}{ah_pt}" if ah_pt is not None else ""
                result_key   = f"ah_away:{ah_pt}" if ah_pt is not None else "ah_away"
                result_label = f"✈️ AH Ausw.{pt_str}"
                result_odds  = round(ah_odds, 2)

    picks.append({
        "market":    result_label,
        "marketKey": result_key,
        "icon":      result_label.split()[0],
        "conf":      conf(result_sc, h=0.72, m=0.58),
        "sc":        round(result_sc, 3),
        "odds":      result_odds,
        "result":    None,
    })

    picks.append({
        "market":    goals_label,
        "marketKey": goals_key,
        "icon":      goals_label.split()[0],
        "conf":      conf(goals_sc, h=0.66, m=0.46),
        "sc":        round(goals_sc, 3),
        "odds":      None,
        "result":    None,
    })

    if cards_pick:
        ck, cl, cs = cards_pick
        picks.append({
            "market":    cl,
            "marketKey": ck,
            "icon":      "🟨",
            "conf":      conf(cs, h=0.70, m=0.48),
            "sc":        round(cs, 3),
            "odds":      None,
            "result":    None,
        })

    return picks


# ── Main ──────────────────────────────────────────────────────────────────────

def fixture_date_iso(date_str: str, fallback: str) -> str:
    try:
        d = datetime.datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return d.strftime("%Y-%m-%d")
    except Exception:
        return fallback


def main():
    today_iso = datetime.date.today().isoformat()
    print(f"📝  Save picks — {today_iso}")

    if not HTML_FILE.exists():
        print(f"  ❌  {HTML_FILE.name} not found")
        return

    with open(HTML_FILE, encoding="utf-8") as f:
        html = f.read()

    fixtures = extract_fixtures_from_html(html)
    print(f"  📦 {len(fixtures)} fixtures extracted from HTML")

    # Load prematch odds for AH substitution
    pm_lookup = load_prematch_odds()
    print(f"  📊 {len(pm_lookup)} prematch odds entries loaded")

    # Load existing history
    history = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
    saved_ids = {e["id"] for e in history}

    # Build fx lookup by normalised home+away for re-apply step below
    fx_by_key: dict[tuple, dict] = {}
    added = 0
    for fx in fixtures:
        date_iso = fixture_date_iso(fx.get("date", ""), today_iso)
        league   = fx.get("_league", "UNK")
        home     = fx.get("home", "?")
        away     = fx.get("away", "?")

        mid = f"{date_iso}-{league}-{home}-{away}".replace(" ", "_").replace("/", "-")

        # Store for re-apply step regardless of whether already saved
        key = (_norm(home), _norm(away))
        fx_by_key[key] = fx

        if mid in saved_ids:
            continue

        pm_odds = find_prematch_odds(pm_lookup, home, away)
        picks = generate_picks(fx, pm_odds)
        if not picks:
            continue

        entry = {
            "id":          mid,
            "date":        fx.get("date", ""),
            "dateIso":     date_iso,
            "league":      league,
            "leagueName":  fx.get("_leagueName", ""),
            "leagueFlag":  fx.get("_leagueFlag", ""),
            "home":        home,
            "away":        away,
            "eventId":     fx.get("eventId"),
            "matchScore":  fx.get("matchScore"),
            "picks":       picks,
            "finalScore":  None,
            "resolved":    False,
            "savedAt":     datetime.datetime.utcnow().isoformat() + "Z",
        }
        history.append(entry)
        added += 1
        pick_labels = ", ".join(p["market"] for p in picks)
        print(f"  + {fx.get('_leagueFlag','')} {home} vs {away} ({fx.get('date','')}) → {pick_labels}")

    # ── Re-apply prematch odds for unresolved upcoming/today entries ─────────
    # When save_picks runs days before the match, prematch-data.json may not yet
    # have AH lines. This block re-runs generate_picks() with fresh odds so AH
    # substitution is applied as soon as the data arrives.
    today_dt = datetime.date.fromisoformat(today_iso)
    refreshed = 0
    if pm_lookup:
        for e in history:
            if e.get("resolved"):
                continue
            try:
                e_date = datetime.date.fromisoformat(e["dateIso"])
            except Exception:
                continue
            # Refresh today, future AND yesterday (unresolved overnight matches)
            # Anything older than 2 days is left alone.
            if e_date < today_dt - datetime.timedelta(days=2):
                continue
            # Skip if result pick already has AH + odds (fully enriched)
            result_pick = next(
                (p for p in e["picks"]
                 if p.get("marketKey", "").startswith("ah_")
                 or p.get("marketKey") in ("homeWin", "awayWin", "draw")),
                None
            )
            if result_pick and result_pick.get("marketKey", "").startswith("ah_") \
                    and result_pick.get("odds") is not None:
                continue  # Already has AH odds — nothing to update
            # Try to find prematch odds for this entry
            home, away = e.get("home", ""), e.get("away", "")
            pm_odds = find_prematch_odds(pm_lookup, home, away)
            if not pm_odds:
                continue
            # Find matching fixture from HTML (needed for full generate_picks)
            hn, an = _norm(home), _norm(away)
            fx = fx_by_key.get((hn, an))
            if fx is None:
                # Fuzzy search
                for (fh, fa), candidate in fx_by_key.items():
                    if (fh in hn or hn in fh) and (fa in an or an in fa):
                        fx = candidate
                        break
            if fx is None:
                continue
            new_picks = generate_picks(fx, pm_odds)
            if not new_picks:
                continue
            # Preserve isTopCard flags from existing picks (same order assumed)
            for i, np in enumerate(new_picks):
                if i < len(e["picks"]):
                    np["isTopCard"] = e["picks"][i].get("isTopCard", False)
            e["picks"] = new_picks
            refreshed += 1
            new_labels = ", ".join(p["market"] for p in new_picks)
            flag = e.get("leagueFlag", "")
            print(f"  🔄 {flag} {home} vs {away} ({e['dateIso']}) → {new_labels}")

    if refreshed:
        print(f"\n♻️   {refreshed} Einträge mit frischen Prematch-Odds aktualisiert")

    # ── Mark top picks (isTopCard) for today's fixtures ──────────────────────
    # Mirrors JS buildTopCardsHtml() ranking: sc*10 + conf bonus + match score bonus.
    # Top 7 picks (rank ≥ 12, max 2 per match) get isTopCard=True.
    # Runs every time — resets and recomputes so reruns stay idempotent.
    today_entries = [e for e in history if e.get("dateIso") == today_iso]
    if today_entries:
        # Clear existing flags for today (idempotent reruns)
        for e in today_entries:
            for p in e["picks"]:
                p["isTopCard"] = False

        # Build ranked candidates: (rank, entry_id, pick_idx)
        candidates = []
        for e in today_entries:
            ms = e.get("matchScore") or 0
            for idx, p in enumerate(e["picks"]):
                sc   = p.get("sc") or 0
                conf = p.get("conf", "low")
                rank = sc * 10
                rank += 4 if conf == "high" else 1 if conf == "medium" else 0
                rank += (ms - 6) * 2
                candidates.append((rank, e["id"], idx))

        # Sort descending, take up to 7 (max 2 per match, min rank 12)
        candidates.sort(key=lambda x: -x[0])
        match_counts: dict[str, int] = {}
        top_count = 0
        for rank, eid, pidx in candidates:
            if rank < 12 or top_count >= 7:
                break
            if match_counts.get(eid, 0) >= 2:
                continue
            # Find entry by id and mark pick
            for e in today_entries:
                if e["id"] == eid:
                    e["picks"][pidx]["isTopCard"] = True
                    match_counts[eid] = match_counts.get(eid, 0) + 1
                    top_count += 1
                    break

        top_labels = [
            f"{e.get('leagueFlag','')} {e['home']} vs {e['away']} → {p['market']}"
            for e in today_entries for p in e["picks"] if p.get("isTopCard")
        ]
        print(f"\n🃏  Top Picks ({top_count}):")
        for lbl in top_labels:
            print(f"   ⭐ {lbl}")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {added} neue Einträge gespeichert  (total: {len(history)})")
    print(f"   Datei: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
