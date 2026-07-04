#!/usr/bin/env python3
"""
fetch_wm_match_results.py — WM 2026 Spielergebnisse via API-Football

Holt abgeschlossene WM-Spielergebnisse und schreibt sie in wm2026-data.json:

  fixture.result = {
    "home_score": 2,
    "away_score": 1,
    "winner":     "MEX",      # oder "ZAF" oder "draw"
    "status":     "FT",       # FT | AET | PEN | LIVE | NS (Not Started)
    "statusShort": "FT",
    "elapsed":    90,
    "resolvedAt": "2026-06-12T..."
  }

Wird aufgerufen von: fetch-wm-data.yml (täglich)
Benötigt: APISPORTS_KEY
"""

import json
import os
import sys
import http.client
import ssl
from datetime import datetime, timezone
from pathlib import Path

BASE    = Path(__file__).parent
WM_FILE = BASE / "wm2026-data.json"

APISPORTS_KEY = os.environ.get("APISPORTS_KEY", "")
API_HOST      = "v3.football.api-sports.io"

# FIFA WM 2026 League ID bei API-Football
# Wird als Fallback gesucht wenn nicht gesetzt (typisch: 1 = WM)
WM_LEAGUE_ID  = int(os.environ.get("WM_LEAGUE_ID", "1"))
WM_SEASON     = 2026

# Spielstatus die als "abgeschlossen" gelten
FINISHED_STATUSES = {"FT", "AET", "PEN"}
LIVE_STATUSES     = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}


def api_get(path: str) -> dict | None:
    """API-Football GET Request."""
    if not APISPORTS_KEY:
        return None
    try:
        ctx  = ssl.create_default_context()
        conn = http.client.HTTPSConnection(API_HOST, timeout=20, context=ctx)
        conn.request("GET", path, headers={
            "x-apisports-key": APISPORTS_KEY,
            "User-Agent":      "CocoBet/1.0",
        })
        resp = conn.getresponse()
        raw  = resp.read().decode()
        conn.close()
        if resp.status == 200:
            return json.loads(raw)
        print(f"  ⚠️  API-Football {resp.status}: {raw[:200]}")
        return None
    except Exception as e:
        print(f"  ❌  API-Football Fehler: {e}")
        return None


def find_wm_league_id() -> int | None:
    """Sucht die WM 2026 League-ID bei API-Football."""
    # API-Football-Liga heißt exakt "World Cup" (NICHT "FIFA World Cup"!), id=1.
    data = api_get(f"/leagues?name=World+Cup&season={WM_SEASON}")
    if not data:
        return None
    leagues = data.get("response", [])
    if leagues:
        lid = leagues[0]["league"]["id"]
        print(f"  Gefunden: WM League-ID = {lid}")
        return lid
    return None


def fetch_all_fixtures(league_id: int) -> list:
    """Holt alle WM-Fixtures (inkl. Ergebnisse) von API-Football."""
    data = api_get(f"/fixtures?league={league_id}&season={WM_SEASON}")
    if not data:
        return []
    return data.get("response", [])


def _ninety_min_score(api_match: dict, orientation: str) -> tuple:
    """Settlement-Score = 90 Minuten (reguläre Zeit + Nachspielzeit), NICHT inkl. Verlängerung
    (03.07.2026, Lucas: ARG-CPV 1:1 nach 90 → Verlängerung 3:2 → „Unter 2.5/3.5" fälschlich verloren).
    score.fulltime = 90-Min-Stand; goals enthält bei AET/PEN die Verlängerungstore. orientation
    'swapped' dreht Heim/Auswärts. Gibt (home, away) zurück."""
    goals = api_match.get("goals") or {}
    ft = (api_match.get("score") or {}).get("fulltime") or {}
    h = ft.get("home") if ft.get("home") is not None else goals.get("home")
    a = ft.get("away") if ft.get("away") is not None else goals.get("away")
    return (a, h) if orientation == "swapped" else (h, a)


def _winner_from_tiebreak(api_match: dict, home_id: str, away_id: str, orientation: str) -> str:
    """Sieger bei Gleichstand nach regulärer Zeit/Verlängerung (30.06.2026, Lucas: „Kanada vs draw").
    KO-Spiele entscheidet das Elfmeterschießen → reiner Tor-Vergleich liefert fälschlich „draw".
    Reihenfolge: Elfmeter-Score → API-Sieger-Flag → „draw" (nur echtes Gruppen-Remis). Orientation
    „swapped" dreht Heim/Auswärts wie beim Score-Mapping."""
    pen = (api_match.get("score") or {}).get("penalty") or {}
    ph, pa = pen.get("home"), pen.get("away")
    tm = api_match.get("teams") or {}
    if orientation == "swapped":
        ph, pa = pa, ph
        th, ta = tm.get("away") or {}, tm.get("home") or {}
    else:
        th, ta = tm.get("home") or {}, tm.get("away") or {}
    if ph is not None and pa is not None and ph != pa:
        return home_id if ph > pa else away_id      # Elfmeterschießen
    if th.get("winner") is True:
        return home_id                               # API-Sieger-Flag (AET/PEN)
    if ta.get("winner") is True:
        return away_id
    return "draw"                                    # echtes Remis (nur Gruppenphase)


def _num(v):
    """Tolerantes Zahlen-Parsing (entfernt %, behandelt None/Strings)."""
    try:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.replace("%", "").strip()
        return float(v)
    except Exception:
        return None


def fetch_match_stats(api_match: dict) -> dict | None:
    """Echte Match-Statistiken eines BEENDETEN Spiels — Basis fürs Prozess-Lernen
    (14.06.2026). Holt /fixtures/statistics + /fixtures/players und liefert pro
    Heim/Auswärts: xG (API, sonst xGsim 0.118·inside + 0.10·on), Schüsse, SOT,
    Inside-Box, Key-Passes (Großchancen-Proxy). So kann das System „verdient vs Pech"
    bewerten statt nur aus dem Endstand zu lernen (QAT-SUI 1:1: Schweiz xG-dominant)."""
    fid = (api_match.get("fixture") or {}).get("id")
    teams = api_match.get("teams") or {}
    home_tid = (teams.get("home") or {}).get("id")
    away_tid = (teams.get("away") or {}).get("id")
    if not (fid and home_tid and away_tid):
        return None
    data = api_get(f"/fixtures/statistics?fixture={fid}")
    if not data or not data.get("response"):
        return None
    per: dict = {}
    for ts in data["response"]:
        tid = (ts.get("team") or {}).get("id")
        if not tid:
            continue
        m, xg = {}, None
        for s in (ts.get("statistics") or []):
            key = (s.get("type") or "").lower().strip()
            m[key] = s.get("value")
            if "expected goals" in key or key == "xg":
                xg = _num(s.get("value"))
        inside = _num(m.get("shots insidebox")) or 0.0
        on     = _num(m.get("shots on goal")) or 0.0
        total  = _num(m.get("total shots")) or 0.0
        per[tid] = {"xg": xg, "xgsim": round(0.118 * inside + 0.10 * on, 3),
                    "sot": on, "shots": total, "inside": inside}
    if home_tid not in per or away_tid not in per:
        return None
    # Key-Passes (Großchancen-Proxy) aus /fixtures/players
    kp: dict = {}
    pdata = api_get(f"/fixtures/players?fixture={fid}")
    if pdata and pdata.get("response"):
        for tb in pdata["response"]:
            tid = (tb.get("team") or {}).get("id")
            if not tid:
                continue
            s = 0.0
            for p in (tb.get("players") or []):
                k = (((p.get("statistics") or [{}])[0] or {}).get("passes") or {}).get("key")
                if k is not None:
                    s += _num(k) or 0.0
            kp[tid] = s
    h, a = per[home_tid], per[away_tid]
    h_xg = h["xg"] if h["xg"] is not None else h["xgsim"]
    a_xg = a["xg"] if a["xg"] is not None else a["xgsim"]
    xg_source = "api" if (h["xg"] is not None and a["xg"] is not None) else "sim"
    return {
        "homeXg": round(h_xg, 2), "awayXg": round(a_xg, 2),
        "xgTotal": round(h_xg + a_xg, 2), "xgSource": xg_source,
        "homeSot": h["sot"], "awaySot": a["sot"],
        "homeShots": h["shots"], "awayShots": a["shots"],
        "homeInside": h["inside"], "awayInside": a["inside"],
        "homeKeyPasses": kp.get(home_tid), "awayKeyPasses": kp.get(away_tid),
    }


def _api_id(team_ids: dict, code: str) -> str:
    """apiFootball-Team-ID aus teamIds robust lesen. FIX 12.06.2026: Struktur ist
    FLACH ({"MEX": 16}), match_fixture las sie aber als {"MEX": {"apiFootball": 16}}
    → .get('apiFootball') auf einem int crashte → JEDES Fixture-Matching schlug fehl
    → Ergebnisse wurden NIE geschrieben (MEX-ZAF blieb NS trotz FT in der API).
    Beide Strukturen werden jetzt unterstützt."""
    v = team_ids.get(code)
    if isinstance(v, dict):
        v = v.get("apiFootball")
    return str(v) if v not in (None, "") else ""


def match_fixture(api_fixture: dict, home_id: str, away_id: str,
                  team_ids: dict) -> str | None:
    """Orientierungs-AGNOSTISCH (FIX 25.06.2026, Lucas: MD3 nicht aufgelöst). Match per Team-PAAR,
    nicht per Heim/Auswärts-Reihenfolge — API-Football ordnet bei WM-Spielen (oft neutraler Platz)
    Heim/Auswärts teils anders zu als unser Seed → strikter Reihenfolge-Match schlug fehl → kein
    Ergebnis. Gibt zurück: 'direct' (api_home == unser_home), 'swapped' (vertauscht) oder None.
    Der Aufrufer mappt die Scores entsprechend per Team-ID (sonst falscher Endstand!)."""
    api_home_id = str(api_fixture["teams"]["home"]["id"])
    api_away_id = str(api_fixture["teams"]["away"]["id"])

    our_home_api = _api_id(team_ids, home_id)
    our_away_api = _api_id(team_ids, away_id)

    if our_home_api and our_away_api:
        if {api_home_id, api_away_id} != {str(our_home_api), str(our_away_api)}:
            return None
        return "direct" if api_home_id == str(our_home_api) else "swapped"

    # Fallback: Namensvergleich (auch orientierungs-agnostisch)
    from fetch_wm_odds import TEAM_NAMES  # type: ignore
    def nm(api_name: str, our_id: str) -> bool:
        api_l = api_name.lower()
        return any(n.lower() in api_l or api_l in n.lower()
                   for n in TEAM_NAMES.get(our_id, [our_id]))

    ah, aa = api_fixture["teams"]["home"]["name"], api_fixture["teams"]["away"]["name"]
    if nm(ah, home_id) and nm(aa, away_id):
        return "direct"
    if nm(ah, away_id) and nm(aa, home_id):
        return "swapped"
    return None


_KO_ROUND_HINT = {"R32": "32", "R16": "16", "QF": "quarter", "SF": "semi", "F": "final"}


def fill_ko_opponents_from_api(wm: dict, api_fixtures: list, team_ids: dict) -> int:
    """Füllt offene KO-Gegner-Slots (eine Seite None, z.B. „Bester Dritter") aus den ECHTEN
    Paarungen von API-Football — umgeht die FIFA-Best-Dritter-Zuordnung, der Quell-Bracket ist
    maßgeblich. 29.06.2026 (Lucas: GER-PRY hatte keine Card, weil der Gegner-Slot nie zugewiesen
    wurde). Reiner Transformer (testbar). Returns Anzahl gefüllter Slots."""
    if not api_fixtures:
        return 0
    api_to_code = {}
    for code, aid in (team_ids or {}).items():
        try:
            api_to_code[int(aid)] = code
        except Exception:
            pass
    filled = 0
    for fx in (wm.get("koFixtures") or []):
        h, a = fx.get("home"), fx.get("away")
        if (h and a) or not (h or a):
            continue   # komplett ODER beide offen → nichts zu tun
        known = h or a
        known_api = (team_ids or {}).get(known)
        if known_api is None:
            continue
        hint = _KO_ROUND_HINT.get(fx.get("round"), "")
        for af in api_fixtures:
            rnd = str((af.get("league") or {}).get("round") or "").lower()
            if hint and hint not in rnd:
                continue   # nur dieselbe KO-Runde
            teams = af.get("teams") or {}
            ah = (teams.get("home") or {}).get("id")
            aa = (teams.get("away") or {}).get("id")
            if int(known_api) not in (ah or -1, aa or -1):
                continue
            opp_api = aa if ah == int(known_api) else ah
            opp_code = api_to_code.get(opp_api)
            if not opp_code:
                continue
            if h:
                fx["away"], fx["awayResolved"] = opp_code, True
            else:
                fx["home"], fx["homeResolved"] = opp_code, True
            fx["bothResolved"] = bool(fx.get("home") and fx.get("away"))
            filled += 1
            break
    return filled


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"⚽  fetch_wm_match_results.py — WM 2026 Ergebnisse")
    print(f"    Zeit: {now_iso[:19]} UTC")

    if not APISPORTS_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen")
        sys.exit(0)

    if not WM_FILE.exists():
        print("  ❌  wm2026-data.json nicht gefunden")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    groups   = wm.get("groups", {})
    team_ids = wm.get("teamIds", {})  # FLACH: {"MEX": 16, ...} (siehe _api_id)

    # WM League-ID + API-Fixtures ZUERST — wir brauchen sie, um offene KO-Gegner zu füllen.
    league_id = WM_LEAGUE_ID or find_wm_league_id()
    if not league_id:
        print("  ❌  WM League-ID konnte nicht bestimmt werden")
        sys.exit(1)

    print(f"\n  Lade API-Football Fixtures für League {league_id} / Saison {WM_SEASON}…")
    api_fixtures = fetch_all_fixtures(league_id)
    if not api_fixtures:
        print("  ⚠️  Keine Fixtures von API-Football — WM möglicherweise noch nicht gelistet")
        sys.exit(0)
    print(f"  → {len(api_fixtures)} Fixtures von API-Football")

    # Offene KO-Gegner-Slots (Best-Dritter etc.) aus den echten API-Paarungen füllen (29.06.2026,
    # Lucas: GER-PRY ohne Card, weil Gegner nie zugewiesen). Erst danach hat das KO-Fixture beide
    # Teams → kommt in all_fixtures + kriegt Ergebnis + wird bepickt/resolved.
    _kf = fill_ko_opponents_from_api(wm, api_fixtures, team_ids)
    if _kf:
        print(f"  🔗 {_kf} offene KO-Gegner aus API-Football zugewiesen")

    # Alle Fixtures sammeln (Gruppen + jetzt-vollständige KO-Fixtures).
    all_fixtures: list[dict] = []
    for gkey, gdata in groups.items():
        for fx in gdata.get("fixtures", []):
            all_fixtures.append({"gkey": gkey, **fx})
    # KO-Fixtures (28.06.2026): liegen in wm["koFixtures"], NICHT in groups → sonst nie aufgelöst.
    for fx in (wm.get("koFixtures") or []):
        if fx.get("home") and fx.get("away"):
            all_fixtures.append({"gkey": None, "_ko": True, **fx})

    print(f"  Fixtures gesamt: {len(all_fixtures)}")

    # Map: date+teams → API result
    updated = 0
    skipped = 0

    for our_fx in all_fixtures:
        home_id = our_fx["home"]
        away_id = our_fx["away"]
        gkey    = our_fx["gkey"]

        # Passendes API-Fixture suchen (orientierungs-agnostisch)
        api_match = None
        orientation = None
        for af in api_fixtures:
            try:
                o = match_fixture(af, home_id, away_id, team_ids)
                if o:
                    api_match, orientation = af, o
                    break
            except Exception:
                continue

        if not api_match:
            skipped += 1
            continue

        status_obj = api_match.get("fixture", {}).get("status", {})
        status_short = status_obj.get("short", "NS")
        status_long  = status_obj.get("long",  "Not Started")
        elapsed      = status_obj.get("elapsed")

        # 03.07.2026 (Lucas: ARG-CPV 1:1 nach 90, in der Verlängerung 3:2 → „Unter 2.5/3.5" fälschlich
        # verloren; ERSTES AET-Spiel der WM, daher bisher unbemerkt): UNSERE Märkte (1X2/DC/DNB/AH/
        # Über-Unter/BTTS) settlen auf 90 MINUTEN (reguläre Zeit + Nachspielzeit). Verlängerung + Elf-
        # meter zählen NUR für den Aufstieg (winner), NIE fürs Pick-Settlement. Deshalb: Settlement-Score
        # = score.fulltime (90 Min). `goals` enthält bei AET/PEN die Verlängerungstore → nur für Anzeige.
        goals = api_match.get("goals", {})
        home_score, away_score = _ninety_min_score(api_match, orientation)   # Settlement = 90 Min
        # bei 'swapped' liefert API Heim/Auswärts vertauscht → sonst falscher Stand (25.06.2026).
        if orientation == "swapped":
            agg_home, agg_away = goals.get("away"), goals.get("home")
        else:
            agg_home, agg_away = goals.get("home"), goals.get("away")

        # Winner bestimmen. 30.06.2026 (Lucas: „Kanada vs draw" in R16): KO-Spiele können nach
        # regulärer Zeit/Verlängerung remis stehen → dann entscheidet das Elfmeterschießen. Der reine
        # Tor-Vergleich liefert dann „draw", was fälschlich als Sieger in die nächste Runde wandert.
        # Reihenfolge: Tore → bei Gleichstand Elfmeter-Score → API-Sieger-Flag → echtes Remis (Gruppe).
        winner = None
        if status_short in FINISHED_STATUSES and home_score is not None and away_score is not None:
            if home_score > away_score:
                winner = home_id
            elif away_score > home_score:
                winner = away_id
            else:
                winner = _winner_from_tiebreak(api_match, home_id, away_id, orientation)

        # FIX 13.06.2026: Scores NUR persistieren wenn das Spiel beendet ist.
        # Vorher wurde ein Live-Zwischenstand (z.B. USA-PRY 1H 2:0) ins result
        # geschrieben → Dashboard rendert ihn als „Endstand 2:0", obwohl das Spiel
        # 4:1 endete. result.home_score ist damit IMMER ein echter Endstand;
        # Live-Status (1H/HT/…) + elapsed werden weiter gezeigt, aber ohne Score.
        _finished = status_short in FINISHED_STATUSES
        result_entry = {
            "status":      status_short,
            "statusLong":  status_long,
            "home_score":  home_score if _finished else None,   # 90-Min-Stand = Settlement-Basis
            "away_score":  away_score if _finished else None,
        }
        # Verlängerungs-/Gesamtstand (inkl. Verlängerung) nur zur Anzeige — settlet NICHTS. Bei AET/PEN
        # IMMER speichern (auch wenn == 90-Min), damit der Guard check_ko_settlement_ninety_min eine
        # verlässliche ET-Referenz hat (sonst blind bei einem Revert des _ninety_min_score-Fix).
        if _finished and status_short in ("AET", "PEN") and agg_home is not None:
            result_entry["aggregateScore"] = {"home": agg_home, "away": agg_away}
        if winner is not None:
            result_entry["winner"] = winner
        if elapsed is not None:
            result_entry["elapsed"] = elapsed
        if status_short in FINISHED_STATUSES:
            result_entry["resolvedAt"] = now_iso

        # ── Venue-Sync 09.06.2026 ──────────────────────────────────────
        # API-Football liefert venue.name + venue.city im /fixtures-Response.
        # Vorher: wir ignorierten das. Resultat: "Empower Field, Denver" und
        # "Camping World Stadium, Orlando" als Phantom-Venues aus alter Daten-
        # quelle in wm2026-data.json. Jetzt: API-Football als Source-of-Truth.
        api_venue = api_match.get("fixture", {}).get("venue", {}) or {}
        venue_name = api_venue.get("name")
        venue_city = api_venue.get("city")
        venue_str = None
        if venue_name and venue_city:
            venue_str = f"{venue_name}, {venue_city}"
        elif venue_name:
            venue_str = venue_name
        elif venue_city:
            venue_str = venue_city

        # In wm2026-data.json schreiben — KO ins koFixtures-Array, sonst in die Gruppe.
        _target = (wm.get("koFixtures") or []) if our_fx.get("_ko") else wm["groups"][gkey]["fixtures"]
        for fx in _target:
            if fx.get("home") == home_id and fx.get("away") == away_id:
                # Stale-Downgrade-Schutz (12.06.2026): ein bereits FINALES Ergebnis
                # NICHT mit einem NS/Scheduled-Re-Fetch plätten. API-Football (und
                # auch ESPN) liefern WC2026-Spiele teils noch als "Not Started",
                # obwohl sie längst final sind → sonst würde ein gesetztes 2:0
                # bei jedem Lauf auf null zurückgesetzt.
                _old = fx.get("result") or {}
                _old_final = (_old.get("status") in FINISHED_STATUSES
                              and _old.get("home_score") is not None)
                _new_final = (status_short in FINISHED_STATUSES
                              and home_score is not None)
                if _old_final and not _new_final:
                    print(f"  🛡️  {home_id} vs {away_id}: behalte finales "
                          f"{_old.get('home_score')}:{_old.get('away_score')} "
                          f"(API liefert {status_short})")
                    break
                # Post-Match-Stats (xG/Schüsse/Key-Passes) für Prozess-Lernen —
                # idempotent: schon erfasste Stats nicht neu holen (spart API-Calls).
                if _finished:
                    if _old.get("stats"):
                        result_entry["stats"] = _old["stats"]
                    else:
                        _st = fetch_match_stats(api_match)
                        if _st:
                            result_entry["stats"] = _st
                            print(f"     📊 Match-Stats: xG {_st['homeXg']}:{_st['awayXg']} "
                                  f"(Σ{_st['xgTotal']}, {_st['xgSource']})")
                fx["result"] = result_entry
                if venue_str:
                    # Nur überschreiben wenn API-Quelle einen vernünftigen Wert liefert
                    old_venue = fx.get("venue", "")
                    if fx.get("venue") != venue_str:
                        fx["venue"] = venue_str
                        if old_venue:
                            print(f"     📍 Venue-Update: {old_venue!r} → {venue_str!r}")
                break

        score_str = f"{home_score}:{away_score}" if home_score is not None else "—"
        print(f"  ✅  {home_id} vs {away_id}: {score_str} [{status_short}]")
        updated += 1

    # Sieger/Verlierer sofort in den Bracket propagieren (01.07.2026, Audit-Fix): ohne das füllte sich
    # der nächste Runden-Gegner (bzw. der Halbfinal-Verlierer für Platz 3) erst beim nächsten
    # generate_wm_picks/fetch_wm_odds-Lauf → kurzes Card/Quoten-Loch nach jedem KO-Ergebnis. apply_to_wm
    # nutzt die frisch geschriebenen koFixtures-Ergebnisse + erhält bereits gefüllte Gegner.
    try:
        import resolve_wm_bracket
        resolve_wm_bracket.apply_to_wm(wm)
    except Exception as e:
        print(f"  ⚠️  Bracket-Propagation übersprungen: {e}")

    # Schreiben
    wm["_meta"]["resultsUpdatedAt"] = now_iso
    with open(WM_FILE, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {updated} Fixtures aktualisiert, {skipped} nicht gemappt")
    print(f"   Gespeichert: {WM_FILE}")


if __name__ == "__main__":
    main()
