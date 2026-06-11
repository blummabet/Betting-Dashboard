#!/usr/bin/env python3
"""
fetch_wm_venues.py — echte Venues (+ Kickoff) für WC 2026 aus API-Football.

Quelle: /fixtures?league=1&season=2026
  → fixture.venue.{name, city} + fixture.date (UTC-Kickoff) + teams.home/away.id

Mappt per APIF-Team-IDs (wm2026-data["teamIds"]: our_code → apif_id) auf unsere
Gruppen-Fixtures und schreibt:
  • fx["venue"]   = "<Stadion>, <Stadt>"   (Format wie Seed; treibt travel/altitude/weather)
  • fx["kickoff"] = UTC-ISO                 (nur falls noch nicht von Polymarket gesetzt)
  • wm_venue_schedule.json                  (committetes Schedule als Single Source)

Hintergrund (11.06.2026): Der Seed-Spielplan hatte teils FALSCHE/Platzhalter-Venues
(z.B. KOR-CZE als "SoFi Stadium, Los Angeles" statt real Estadio Akron, Guadalajara).
Venue ist signal-kritisch (travel_burden / altitude / weather). API-Football listet
den WC-Spielplan inkl. Venues längst — nur der /predictions-Endpoint (eigenes Modell)
wird erst kurz vor Anpfiff je Spiel generiert. Beides nicht verwechseln.

Default = DRY-RUN (zeigt nur, was sich ändern würde). Mit --write wird geschrieben.
"""
import os
import sys
import json
import http.client
from pathlib import Path

BASE      = Path(__file__).resolve().parent
WM_FILE   = BASE / "wm2026-data.json"
OUT_FILE  = BASE / "wm_venue_schedule.json"

APIF_HOST = "v3.football.api-sports.io"
APIF_KEY  = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")
WC_LEAGUE_ID = int(os.environ.get("WC_LEAGUE_ID", "1"))   # 1 = FIFA World Cup
WC_SEASON    = int(os.environ.get("WC_SEASON", "2026"))


# ── HTTP (gleiches Muster wie fetch_wm_nt_xg.py) ───────────────────────────
def _apif_get(path: str, timeout: int = 20) -> dict | None:
    conn = None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=timeout)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            print(f"   ⚠️  HTTP {resp.status} bei {path[:80]}: {body[:200]}")
            return None
        return json.loads(body)
    except Exception as e:
        print(f"   ⚠️  Request-Fehler bei {path[:80]}: {e}")
        return None
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def fetch_wc_fixtures() -> list:
    """Alle WC-Fixtures der Saison (mit Paging)."""
    out, page = [], 1
    while True:
        data = _apif_get(f"/fixtures?league={WC_LEAGUE_ID}&season={WC_SEASON}&page={page}")
        if not data:
            break
        out.extend(data.get("response") or [])
        paging = data.get("paging") or {}
        if page >= (paging.get("total") or 1):
            break
        page += 1
    return out


def build_venue_map(fixtures: list, apif_to_code: dict) -> dict:
    """APIF-Fixtures → {frozenset({home_code, away_code}): {...}}.

    Mapping per ungeordnetem Team-Code-Paar (im Gruppen-Stadium eindeutig).
    """
    vmap = {}
    for fx in fixtures:
        f     = fx.get("fixture") or {}
        teams = fx.get("teams") or {}
        venue = f.get("venue") or {}
        h_apif = (teams.get("home") or {}).get("id")
        a_apif = (teams.get("away") or {}).get("id")
        h = apif_to_code.get(h_apif)
        a = apif_to_code.get(a_apif)
        if not h or not a:
            continue
        name = venue.get("name")
        city = venue.get("city")
        vstr = ", ".join([x for x in (name, city) if x]) or None
        vmap[frozenset((h, a))] = {
            "home":      h,
            "away":      a,
            "venue":     vstr,
            "venueName": name,
            "city":      city,
            "kickoff":   f.get("date"),       # UTC ISO
            "fixtureId": f.get("id"),
            "round":     (fx.get("league") or {}).get("round"),
        }
    return vmap


def main() -> int:
    write = "--write" in sys.argv[1:]
    print("=== fetch_wm_venues.py ===")
    print(f"   Quelle: /fixtures?league={WC_LEAGUE_ID}&season={WC_SEASON}  "
          f"({'WRITE' if write else 'DRY-RUN'})\n")

    if not WM_FILE.exists():
        print("❌ wm2026-data.json fehlt"); return 1
    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))

    team_ids = wm.get("teamIds") or {}
    if not team_ids:
        print("❌ wm2026-data.json hat kein teamIds (our_code → apif_id) — Mapping unmöglich")
        return 1
    apif_to_code = {int(v): k for k, v in team_ids.items() if v is not None}
    apif_to_code.setdefault(1113, "BIH")  # Bosnia & Herzegovina (falls in teamIds noch nicht)
    print(f"   {len(apif_to_code)} Team-IDs gemappt (apif_id → code)")

    # ── 1) Committete Schedule deterministisch anwenden (KEIN API nötig) ─────
    # Bulletproof: wm_venue_schedule.json ist fixe, korrekte Daten. Wird IMMER
    # zuerst angewendet — so landet der Venue/Kickoff-Fix auch wenn der API-Call
    # im CI fehlschlägt (vorher: `return 1` ohne zu schreiben → Venues blieben falsch).
    schedule = {}
    if OUT_FILE.exists():
        try:
            schedule = json.loads(OUT_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            schedule = {}
    pre_changed, pre_ko = _apply_to_fixtures(wm, schedule, write)
    if schedule:
        print(f"   📁 Schedule angewendet: {len(pre_changed)} Venue-Korrekturen, {pre_ko} Kickoffs "
              f"(aus committeter wm_venue_schedule.json)")

    # ── 2) API-Refresh (best effort) — hält Schedule + Fixtures aktuell ──────
    fixtures = fetch_wc_fixtures()
    if fixtures:
        vmap = build_venue_map(fixtures, apif_to_code)
        mk_to_info = {f"{v['home']}-{v['away']}": v for v in vmap.values() if v.get("venue")}
        api_changed, api_ko = _apply_to_fixtures(wm, mk_to_info, write)
        schedule = {mk: {"venue": v["venue"], "city": v["city"],
                         "kickoff": v["kickoff"], "fixtureId": v["fixtureId"]}
                    for mk, v in mk_to_info.items()}
        print(f"   🌐 API-Refresh: {len(fixtures)} Fixtures, {len(api_changed)} weitere Venue-Korrekturen")
        for mk, old, new in api_changed[:15]:
            print(f"      {mk:10} {old or '—'} → {new}")
    else:
        print("   ⚠️  API lieferte keine Fixtures — committete Schedule bleibt maßgeblich (Venues korrekt).")

    if write:
        if schedule:
            OUT_FILE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
        WM_FILE.write_text(json.dumps(wm, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"\n✅ geschrieben: wm2026-data.json + wm_venue_schedule.json ({len(schedule)} Spiele)")
    else:
        print("\nℹ️  DRY-RUN — nichts geschrieben. Mit  --write  anwenden.")
    return 0


def _apply_to_fixtures(wm: dict, mk_to_info: dict, write: bool):
    """Setzt venue + kickoff je Gruppen-Fixture aus {matchKey: {venue,city,kickoff}}.
    Returns (changed_list, n_kickoffs_set)."""
    changed, ko_set = [], 0
    for gdata in (wm.get("groups") or {}).values():
        for fx in (gdata.get("fixtures") or []):
            mk = f"{fx.get('home')}-{fx.get('away')}"
            info = mk_to_info.get(mk)
            if not info or not info.get("venue"):
                continue
            if fx.get("venue") != info["venue"]:
                changed.append((mk, fx.get("venue"), info["venue"]))
            if write:
                fx["venue"] = info["venue"]
                if info.get("kickoff"):
                    if fx.get("kickoff") != info["kickoff"]:
                        ko_set += 1
                    fx["kickoff"] = info["kickoff"]
    return changed, ko_set


if __name__ == "__main__":
    sys.exit(main())
