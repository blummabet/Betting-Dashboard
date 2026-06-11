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

    fixtures = fetch_wc_fixtures()
    print(f"   {len(fixtures)} WC-Fixtures von API-Football erhalten")
    if not fixtures:
        print("⚠️  Keine Fixtures — API listet WC2026 (noch) nicht ODER Key/League/Season falsch.")
        return 1

    vmap = build_venue_map(fixtures, apif_to_code)
    with_venue = sum(1 for v in vmap.values() if v["venue"])
    print(f"   {len(vmap)} Fixtures gemappt, davon {with_venue} mit Venue\n")

    # Auf unsere Gruppen-Fixtures anwenden
    changed, set_kickoff, unmapped = [], 0, []
    schedule = {}
    for gdata in wm.get("groups", {}).values():
        for fx in gdata.get("fixtures", []):
            h, a = fx.get("home"), fx.get("away")
            key = frozenset((h, a))
            info = vmap.get(key)
            mk = f"{h}-{a}"
            if not info or not info["venue"]:
                unmapped.append(mk)
                continue
            old_venue = fx.get("venue")
            new_venue = info["venue"]
            if old_venue != new_venue:
                changed.append((mk, old_venue, new_venue))
            schedule[mk] = {
                "venue":   new_venue,
                "city":    info["city"],
                "kickoff": info["kickoff"],
                "fixtureId": info["fixtureId"],
            }
            if write:
                fx["venue"] = new_venue
                if not fx.get("kickoff") and info.get("kickoff"):
                    fx["kickoff"] = info["kickoff"]
                    set_kickoff += 1

    print(f"📋 {len(changed)} Venue-Korrekturen, {len(unmapped)} ungemappt:")
    for mk, old, new in changed[:30]:
        print(f"   {mk:10}  {old or '—'}  →  {new}")
    if len(changed) > 30:
        print(f"   … +{len(changed)-30} weitere")
    if unmapped:
        print(f"   ⚠️  ungemappt (Venue bleibt): {', '.join(unmapped[:12])}"
              + (" …" if len(unmapped) > 12 else ""))

    if write:
        OUT_FILE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
        WM_FILE.write_text(json.dumps(wm, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"\n✅ geschrieben: wm2026-data.json ({len(changed)} Venues, {set_kickoff} Kickoffs) "
              f"+ wm_venue_schedule.json ({len(schedule)} Spiele)")
    else:
        print("\nℹ️  DRY-RUN — nichts geschrieben. Mit  --write  anwenden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
