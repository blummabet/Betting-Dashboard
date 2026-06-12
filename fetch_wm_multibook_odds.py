#!/usr/bin/env python3
"""
fetch_wm_multibook_odds.py — Soft-Book-KONSENS aus API-Football für public_static_bias.

Quelle: /odds?league=1&season=2026  (Ultra-Plan: 14 Bookmaker pro Spiel).
Bisher lieferte fetch_wm_odds nur EINEN Soft-Book (williamhill) als public_* —
verrauscht, deshalb feuerte public_static_bias kaum. Hier: robuster Median-Konsens
ALLER Soft-Books (ohne Pinnacle) → bessere "Public"-Schätzung + füllt fehlende
Fixtures. Schreibt public_hw/dr/aw + public_o25/u25 + public_bttsY/N + public_bookmaker
in wm2026-data["odds"][matchKey]. Pinnacle (hw/dr/aw via TheOddsAPI) bleibt unberührt.

Mappt /odds-Fixtures per fixture_id → matchKey über /fixtures (+ teamIds).
Default DRY-RUN; --write schreibt. Läuft VOR generate_wm_picks.
"""
import os
import sys
import json
import http.client
import statistics
from pathlib import Path

BASE      = Path(__file__).resolve().parent
WM_FILE   = BASE / "wm2026-data.json"
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY  = os.environ.get("APISPORTS_KEY", "9f36726c1bdc9957b4a49f89277b80db")
WC_LEAGUE_ID = int(os.environ.get("WC_LEAGUE_ID", "1"))
WC_SEASON    = int(os.environ.get("WC_SEASON", "2026"))

# Pinnacle = unser Sharp-Anker → NICHT in den Public-Konsens aufnehmen.
SHARP_BOOK = "pinnacle"


def _apif_get(path: str, timeout: int = 20) -> dict | None:
    conn = None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=timeout)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            print(f"   ⚠️  HTTP {resp.status} bei {path[:80]}: {body[:160]}")
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


def _paged(path_base: str) -> list:
    out, page = [], 1
    while True:
        data = _apif_get(f"{path_base}&page={page}")
        if not data:
            break
        out.extend(data.get("response") or [])
        paging = data.get("paging") or {}
        if page >= (paging.get("total") or 1):
            break
        page += 1
    return out


def build_fixture_map(apif_to_code: dict) -> dict:
    """fixture_id → 'HOME-AWAY' (unsere Codes).

    FIX 12.06.2026: NICHT _paged() benutzen — API-Football lehnt `&page` bei
    /fixtures ab ('The Page field do not exist.' → 0 Ergebnisse). /fixtures liefert
    ohnehin alle Spiele in EINER Response (paging.total=1). Vorher: _paged hängte
    &page=1 an → /fixtures gab 0 → fmap leer → JEDE /odds-Zeile übersprungen → 0
    Konsens-Writes → public_* blieb beim alten Einzel-Book (williamhill). /odds
    paginiert dagegen normal, deshalb fällt es nur hier auf."""
    data = _apif_get(f"/fixtures?league={WC_LEAGUE_ID}&season={WC_SEASON}")
    fixtures = (data or {}).get("response") or []
    fmap = {}
    for fx in fixtures:
        fid = (fx.get("fixture") or {}).get("id")
        teams = fx.get("teams") or {}
        h = apif_to_code.get((teams.get("home") or {}).get("id"))
        a = apif_to_code.get((teams.get("away") or {}).get("id"))
        if fid and h and a:
            fmap[fid] = f"{h}-{a}"
    return fmap


def _median(vals: list) -> float | None:
    vals = [float(v) for v in vals if v and float(v) > 1.0]
    return round(statistics.median(vals), 3) if vals else None


def consensus_for_fixture(bookmakers: list) -> dict:
    """Median-Konsens (Dezimalquote) über alle Soft-Books (ohne Pinnacle)."""
    acc = {k: [] for k in ("hw", "dr", "aw", "o25", "u25", "bttsY", "bttsN")}
    n_books = 0
    for bk in bookmakers:
        name = (bk.get("name") or "").lower()
        if SHARP_BOOK in name:
            continue
        used = False
        for bet in (bk.get("bets") or []):
            bname = (bet.get("name") or "").lower()
            vals = {str(v.get("value")).lower(): v.get("odd") for v in (bet.get("values") or [])}
            if bname == "match winner":
                if "home" in vals: acc["hw"].append(vals["home"]); used = True
                if "draw" in vals: acc["dr"].append(vals["draw"])
                if "away" in vals: acc["aw"].append(vals["away"])
            elif bname == "goals over/under":
                if "over 2.5" in vals:  acc["o25"].append(vals["over 2.5"])
                if "under 2.5" in vals: acc["u25"].append(vals["under 2.5"])
            elif bname == "both teams score":
                if "yes" in vals: acc["bttsY"].append(vals["yes"])
                if "no" in vals:  acc["bttsN"].append(vals["no"])
        if used:
            n_books += 1
    out = {k: _median(v) for k, v in acc.items()}
    out["n_books"] = n_books
    return out


def main() -> int:
    write = "--write" in sys.argv[1:]
    print(f"=== fetch_wm_multibook_odds.py === ({'WRITE' if write else 'DRY-RUN'})\n")

    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    team_ids = wm.get("teamIds") or {}
    apif_to_code = {int(v): k for k, v in team_ids.items() if v is not None}
    apif_to_code.setdefault(1113, "BIH")
    odds_ref = wm.setdefault("odds", {})

    fmap = build_fixture_map(apif_to_code)
    print(f"   {len(fmap)} Fixtures gemappt")

    rows = _paged(f"/odds?league={WC_LEAGUE_ID}&season={WC_SEASON}")
    print(f"   {len(rows)} Odds-Einträge von API-Football\n")
    if not rows:
        print("⚠️  Keine Odds — API listet WC2026 (noch) nicht ODER Key/League/Season falsch.")
        return 1

    updated, samples = 0, []
    for row in rows:
        fid = (row.get("fixture") or {}).get("id")
        mk = fmap.get(fid)
        if not mk:
            continue
        con = consensus_for_fixture(row.get("bookmakers") or [])
        if not con.get("hw") or con["n_books"] < 2:
            continue   # zu wenig Soft-Books → kein verlässlicher Konsens
        entry = odds_ref.setdefault(mk, {})
        before = entry.get("public_hw")
        new_pub = {
            "public_hw": con["hw"], "public_dr": con["dr"], "public_aw": con["aw"],
            "public_o25": con["o25"], "public_u25": con["u25"],
            "public_bttsY": con["bttsY"], "public_bttsN": con["bttsN"],
            "public_bookmaker": f"Konsens ({con['n_books']} Books)",
            "public_ou_bookmaker": f"Konsens ({con['n_books']} Books)",
        }
        if write:
            entry.update({k: v for k, v in new_pub.items() if v is not None})
        updated += 1
        if len(samples) < 8:
            samples.append(f"{mk}: pub hw/dr/aw={con['hw']}/{con['dr']}/{con['aw']} "
                           f"(war {before}) · {con['n_books']} Books")

    print(f"📊 {updated} Fixtures mit Soft-Book-Konsens:")
    for s in samples:
        print(f"   {s}")

    if write:
        WM_FILE.write_text(json.dumps(wm, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"\n✅ wm2026-data.json: public_* (Konsens) für {updated} Fixtures geschrieben")
    else:
        print("\nℹ️  DRY-RUN — mit --write anwenden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
