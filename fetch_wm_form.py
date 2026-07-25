#!/usr/bin/env python3
"""
fetch_wm_form.py — WM 2026 Team Form + H2H fetcher via API-Football.

Writes to wm2026-data.json:
  "teamIds" → { "MEX": 16, "ZAF": 45, … }   (cached, only fetched once)
  "form"    → { "MEX": { last5, avgScored, avgConceded, … } }
  "h2h"     → { "MEX-ZAF": { games, homeWins, draws, awayWins, … } }

Run:   python3 fetch_wm_form.py [--force]
Cron:  Daily via fetch-wm-data.yml (before generate_wm_picks.py)
"""

import json, os, sys, time, http.client
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE      = Path(__file__).parent
# Dataset-Modus (Single Source: cocobet_dataset): Liga → Form+H2H für liga-data.json.
# Liga-Team-id = API-Football-ID (teamIds-Identitäts-Map aus build_liga_data).
_IS_LIGA  = D.is_liga()
WM_FILE   = D.data_file()
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY  = os.environ.get("APISPORTS_KEY", "")
DELAY     = 1.5      # seconds between requests (Pro plan: 10 req/min)
FORCE     = "--force" in sys.argv

FORM_STALE_H = 24   # re-fetch form after 24 hours
H2H_STALE_H  = 168  # re-fetch H2H after 7 days (rarely changes)

# ── API-Football team name overrides ──────────────────────────────────────
APIF_NAME: dict[str, str] = {
    "ARG": "Argentina",    "AUS": "Australia",     "AUT": "Austria",
    "BEL": "Belgium",      "BIH": "Bosnia",         "BRA": "Brazil",
    "CAN": "Canada",       "CIV": "Ivory Coast",    "COD": "Congo DR",
    "COL": "Colombia",     "CPV": "Cape Verde",      "CRO": "Croatia",
    "CUW": "Curacao",      "CZE": "Czech Republic", "DZA": "Algeria",
    "ECU": "Ecuador",      "EGY": "Egypt",           "ENG": "England",
    "ESP": "Spain",        "FRA": "France",          "GER": "Germany",
    "GHA": "Ghana",        "HTI": "Haiti",           "IRN": "Iran",
    "IRQ": "Iraq",         "JOR": "Jordan",          "JPN": "Japan",
    "KOR": "South Korea",  "MAR": "Morocco",         "MEX": "Mexico",
    "NED": "Netherlands",  "NOR": "Norway",          "NZL": "New Zealand",
    "PAN": "Panama",       "POR": "Portugal",        "PRY": "Paraguay",
    "QAT": "Qatar",        "SAU": "Saudi Arabia",    "SCO": "Scotland",
    "SEN": "Senegal",      "SUI": "Switzerland",     "SWE": "Sweden",
    "TUN": "Tunisia",      "TUR": "Turkey",          "URU": "Uruguay",
    "USA": "United States","UZB": "Uzbekistan",      "ZAF": "South Africa",
}


# ── HTTP helper ───────────────────────────────────────────────────────────

def apif_get(endpoint: str, params: dict) -> list:
    """Single API-Football GET. Returns response list or []."""
    if not APIF_KEY:
        return []
    import urllib.parse
    query = urllib.parse.urlencode(params)
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", f"/{endpoint}?{query}",
                     headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        data = json.loads(raw)
        errs = data.get("errors", {})
        if errs and errs not in ({}, []):
            print(f"  ⚠️  API error /{endpoint}: {errs}")
            return []
        return data.get("response", [])
    except Exception as e:
        print(f"  ❌  Request failed /{endpoint}?{query}: {e}")
        return []


# ── Staleness check ───────────────────────────────────────────────────────

def is_stale(updated_at: str | None, hours: int) -> bool:
    if not updated_at or FORCE:
        return True
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() > hours * 3600
    except Exception:
        return True


def form_needs_refetch(existing: dict) -> bool:
    """Form-Eintrag neu holen? (28.06.2026, Lucas: Serien blieben leer.)
    Zeit-stale ODER schema-stale: fehlt das o25Seq-Feld (neu für Streaks), MUSS neu geholt werden —
    sonst überspringt der 24h-Cache einen „frischen" Eintrag und schreibt die Streak-Sequenzen nie."""
    if "wonSeq" not in (existing or {}):   # 25.07.2026: neuestes Streak-Feld → erzwingt Voll-Re-Fetch
        return True
    return is_stale((existing or {}).get("updatedAt"), FORM_STALE_H)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────
#  STEP 1 — Resolve API-Football team IDs
#  Cached in wm["teamIds"]. Only fetches unknown teams.
# ─────────────────────────────────────────────────────────────────────────

def resolve_team_ids(wm: dict) -> dict:
    wm.setdefault("teamIds", {})
    existing = wm["teamIds"]

    all_ids: set[str] = set()
    for gdata in wm.get("groups", {}).values():
        for t in gdata.get("teams", []):
            all_ids.add(t["id"])

    # B3 Fix 05.06.2026: Alternative Namen für API-Football-Resolution.
    # 4 Teams (BIH, CPV, TUR, USA) wurden nicht aufgelöst weil API-Football
    # andere Schreibweisen verwendet. Liste mehrere Kandidaten und nimm
    # ersten erfolgreichen Match.
    ALT_NAMES = {
        "BIH": ["Bosnia & Herzegovina", "Bosnia and Herzegovina", "Bosnia", "Bosnia-Herzegovina"],
        "CPV": ["Cape Verde Islands", "Cabo Verde", "Cape Verde"],
        "TUR": ["Turkey", "Türkiye", "Turkiye"],
        "USA": ["USA", "United States", "United States of America"],
    }

    new_found = 0
    for tid in sorted(all_ids):
        if tid in existing and not FORCE:
            continue
        # Probiere alle Namens-Varianten — erste die etwas liefert gewinnt
        candidates = ALT_NAMES.get(tid, [APIF_NAME.get(tid, tid)])
        match_team = None
        used_name  = None
        for name in candidates:
            print(f"  🔍 {tid} ({name})…", end=" ", flush=True)
            resp = apif_get("teams", {"name": name})
            time.sleep(DELAY)
            # FIX 11.06.2026: Fuzzy-Fallback. /teams?name= ist EXAKT-Match — wenn
            # API-Football eine andere Schreibweise nutzt (z.B. "Bosnia &
            # Herzegovina" mit Ampersand), liefert name= 0 Treffer. /teams?search=
            # macht Teilstring-Suche und fängt diese Fälle. War der Grund warum
            # BIH als einziges der 48 Teams keine Form-Daten hatte.
            if not resp:
                resp = apif_get("teams", {"search": name})
                time.sleep(DELAY)
            if not resp:
                print("0 Treffer")
                continue
            # Try exact match first, then any
            name_low = name.lower()
            for r in resp:
                t = r.get("team", {})
                if name_low in t.get("name", "").lower():
                    match_team = t
                    used_name  = name
                    break
            if not match_team:
                match_team = resp[0].get("team", {}) if resp else None
                used_name  = name
            if match_team:
                break

        if match_team and match_team.get("id"):
            existing[tid] = match_team["id"]
            print(f"→ {match_team['id']} ({match_team.get('name')}) [via '{used_name}']")
            new_found += 1
        else:
            print(f"  ❌ {tid} nicht aufgelöst (alle {len(candidates)} Namens-Varianten leer)")

    print(f"  [TeamIDs] {new_found} neu, {len(existing)} total cached.")
    return wm


# ─────────────────────────────────────────────────────────────────────────
#  STEP 2 — Fetch team form (last 15 finished matches)
# ─────────────────────────────────────────────────────────────────────────

def _parse_results(fixtures: list, team_api_id: int) -> dict | None:
    """Parse API-Football fixture list into form stats from team's perspective."""
    rows = []
    for fx in fixtures:
        ht  = fx.get("teams", {}).get("home", {})
        at  = fx.get("teams", {}).get("away", {})
        sc  = fx.get("score", {}).get("fulltime", {})
        gls = fx.get("goals", {})

        hg = sc.get("home") if sc.get("home") is not None else gls.get("home")
        ag = sc.get("away") if sc.get("away") is not None else gls.get("away")
        if hg is None or ag is None:
            continue

        is_home  = ht.get("id") == team_api_id
        scored   = hg if is_home else ag
        conceded = ag if is_home else hg
        total    = hg + ag

        if   scored > conceded: result = "W"
        elif scored < conceded: result = "L"
        else:                   result = "D"

        rows.append({
            "r": result, "scored": scored, "conceded": conceded,
            "total": total, "o25": total > 2, "btts": scored > 0 and conceded > 0,
            "h": bool(is_home), "sc": scored > 0, "cs": conceded == 0,
        })

    if not rows:
        return None

    n  = len(rows)
    n5 = min(5, n)

    return {
        "last5":         [r["r"] for r in rows[:n5]],
        "last10":        [r["r"] for r in rows[:10]],
        "avgScored":     round(sum(r["scored"]   for r in rows) / n, 3),
        "avgConceded":   round(sum(r["conceded"] for r in rows) / n, 3),
        "avgGoals":      round(sum(r["total"]    for r in rows) / n, 3),
        "over25Rate":    round(sum(r["o25"]       for r in rows) / n, 3),
        "bttsRate":      round(sum(r["btts"]      for r in rows) / n, 3),
        "scoredRate":    round(sum(r["sc"]        for r in rows) / n, 3),
        "cleanSheetRate": round(sum(r["cs"]       for r in rows) / n, 3),
        # 25.07.2026 (Lucas: „5 Siege in Folge sollten die 1X2 beeinflussen"): Ergebnis-Raten +
        # -Sequenzen. Ergebnis (r["r"]) lag schon vor, wurde nur nie zu Sieg-/Ungeschlagen-Serien.
        "winRate":       round(sum(1 for r in rows if r["r"] == "W") / n, 3),
        "unbeatenRate":  round(sum(1 for r in rows if r["r"] != "L") / n, 3),
        # Pro-Spiel-Sequenzen (most-recent-first) für compute_streaks.py (28.06.2026, Lucas: Serien).
        # Roh-Daten lagen schon in rows, wurden bisher zu Raten verdichtet + verworfen.
        # venueSeq ('H'/'A') parallel → Heim/Auswärts-Split (adamchoi-Stil). sc/cs = trifft/zu null.
        "o25Seq":        [bool(r["o25"])  for r in rows[:15]],
        "bttsSeq":       [bool(r["btts"]) for r in rows[:15]],
        "scoredSeq":     [bool(r["sc"])   for r in rows[:15]],
        "csSeq":         [bool(r["cs"])   for r in rows[:15]],
        "wonSeq":        [r["r"] == "W"   for r in rows[:15]],   # 25.07.2026: Sieg-Serie (1X2)
        "unbeatenSeq":   [r["r"] != "L"   for r in rows[:15]],   #             Ungeschlagen-Serie
        "venueSeq":      ["H" if r["h"] else "A" for r in rows[:15]],
        "games":         n,
        "updatedAt":     now_iso(),
    }


def fetch_team_form(wm: dict) -> dict:
    wm.setdefault("form", {})
    team_ids = wm.get("teamIds", {})

    all_tids: set[str] = set()
    for gdata in wm.get("groups", {}).values():
        for t in gdata.get("teams", []):
            all_tids.add(t["id"])

    updated = 0
    for tid in sorted(all_tids):
        existing = wm["form"].get(tid, {})
        if not form_needs_refetch(existing):
            continue

        api_id = team_ids.get(tid)
        if not api_id:
            print(f"  ⚠️  Keine API-ID für {tid} — Form übersprungen")
            continue

        print(f"  📊 Form {tid} (ID {api_id})…", end=" ", flush=True)
        resp = apif_get("fixtures", {"team": api_id, "last": 15, "status": "FT"})
        time.sleep(DELAY)

        form = _parse_results(resp, api_id)
        if form:
            wm["form"][tid] = form
            last5 = " ".join(form["last5"])
            print(f"{last5} | Ø {form['avgScored']:.2f}:{form['avgConceded']:.2f}")
            updated += 1
        else:
            print("keine Daten")

    print(f"  [Form] {updated} Teams aktualisiert.")
    return wm


# ─────────────────────────────────────────────────────────────────────────
#  STEP 3 — Fetch H2H per fixture pair
#  Key = "HOME-AWAY" e.g. "MEX-ZAF" from home team's perspective.
# ─────────────────────────────────────────────────────────────────────────

def _parse_h2h(fixtures: list, home_api_id: int) -> dict | None:
    """Parse H2H results from home_api_id's perspective (our fixture's home team)."""
    rows = []
    for fx in fixtures:
        ht  = fx.get("teams", {}).get("home", {})
        at  = fx.get("teams", {}).get("away", {})
        sc  = fx.get("score", {}).get("fulltime", {})
        gls = fx.get("goals", {})

        hg = sc.get("home") if sc.get("home") is not None else gls.get("home")
        ag = sc.get("away") if sc.get("away") is not None else gls.get("away")
        if hg is None or ag is None:
            continue

        # Re-orient: scored = our home team's goals
        if ht.get("id") == home_api_id:
            our, their = hg, ag
        elif at.get("id") == home_api_id:
            our, their = ag, hg
        else:
            continue

        total = our + their
        rows.append({
            "w": our > their, "d": our == their, "l": our < their,
            "total": total, "o25": total > 2, "btts": our > 0 and their > 0,
        })

    if not rows:
        return None

    n = len(rows)
    return {
        "games":      n,
        "homeWins":   sum(r["w"] for r in rows),
        "draws":      sum(r["d"] for r in rows),
        "awayWins":   sum(r["l"] for r in rows),
        "avgGoals":   round(sum(r["total"] for r in rows) / n, 3),
        "over25Rate": round(sum(r["o25"]   for r in rows) / n, 3),
        "bttsRate":   round(sum(r["btts"]  for r in rows) / n, 3),
        "updatedAt":  now_iso(),
    }


def fetch_h2h(wm: dict) -> dict:
    wm.setdefault("h2h", {})
    team_ids = wm.get("teamIds", {})

    # Collect unique fixture pairs. (25.06.2026, Lucas) Liga hat ~1000+ Fixtures (ganze Saison) →
    # H2H nur für ANSTEHENDE Spiele holen + deckeln, sonst sprengt es die API-Quota. WM: alle.
    if _IS_LIGA:
        from datetime import date as _date
        _today = _date.today().isoformat()
        _dated = []
        for gdata in wm.get("groups", {}).values():
            for fx in gdata.get("fixtures", []):
                if (fx.get("date") or "") >= _today:
                    _dated.append((fx.get("date") or "", fx["home"], fx["away"]))
        _dated.sort()
        pairs = [(h, a) for _d, h, a in _dated[:60]]   # nächste ~60 Begegnungen
    else:
        pairs = set()
        for gdata in wm.get("groups", {}).values():
            for fx in gdata.get("fixtures", []):
                pairs.add((fx["home"], fx["away"]))

    updated = 0
    for home, away in sorted(pairs):
        key      = f"{home}-{away}"
        existing = wm["h2h"].get(key, {})
        if not is_stale(existing.get("updatedAt"), H2H_STALE_H):
            continue

        home_id = team_ids.get(home)
        away_id = team_ids.get(away)
        if not home_id or not away_id:
            print(f"  ⚠️  H2H {key}: fehlende IDs ({home}={home_id}, {away}={away_id})")
            continue

        print(f"  🤝 H2H {key}…", end=" ", flush=True)
        resp = apif_get("fixtures/headtohead", {
            "h2h":    f"{home_id}-{away_id}",
            "last":   10,
            "status": "FT",
        })
        time.sleep(DELAY)

        h2h = _parse_h2h(resp, home_id)
        if h2h:
            wm["h2h"][key] = h2h
            print(f"H{h2h['homeWins']} X{h2h['draws']} A{h2h['awayWins']} ({h2h['games']} Sp.)")
            updated += 1
        else:
            # WIPE-SCHUTZ (12.07.2026, Wipe-Audit): Bei Quota/Ausfall liefert die API nichts →
            # der {"games": 0}-Stub hätte ein BEFÜLLTES H2H überschrieben UND updatedAt neu
            # gesetzt → die Frische-Prüfung hätte tagelang nicht erneut geholt (doppelt schädlich).
            _prev = (wm["h2h"] or {}).get(key) or {}
            if _prev.get("games"):
                print("keine H2H-Daten — bestehenden H2H-Stand BEHALTEN (kein Stub-Overwrite)")
            else:
                wm["h2h"][key] = {"games": 0, "updatedAt": now_iso()}
                print("keine H2H-Daten")

    print(f"  [H2H] {updated} Paarungen aktualisiert.")
    return wm


# ── MAIN ──────────────────────────────────────────────────────────────────

def main():
    if not APIF_KEY:
        print("⚠️  APISPORTS_KEY nicht gesetzt — fetch übersprungen.")
        return

    print("=== fetch_wm_form.py ===")
    print(f"Force: {FORCE}\n")

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    wm = resolve_team_ids(wm)
    print()
    wm = fetch_team_form(wm)
    print()
    wm = fetch_h2h(wm)

    wm.setdefault("_meta", {})["formUpdatedAt"] = now_iso()

    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print("\n✅ wm2026-data.json gespeichert.")


if __name__ == "__main__":
    main()
