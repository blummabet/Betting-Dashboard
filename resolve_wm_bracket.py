#!/usr/bin/env python3
"""
resolve_wm_bracket.py — KO-Bracket → echte Paarungen (25.06.2026, Lucas: „sobald beide Teams
feststehen kann er schon eine Card generieren").

Liest wm_bracket.json (Raster R32→Halbfinale, group_position / best_third / Sieger-Refs) und löst
die Seiten INKREMENTELL gegen die aktuellen Tabellen auf:

  - group_position: sobald die Gruppe KOMPLETT ist (alle 6 Spiele beendet) → standings[group][pos-1]
  - best_third:     braucht alle 12 Gruppen fertig + offizielle FIFA-Zuordnungstabelle → bis dahin TBD
  - "W74" (Sieger): braucht KO-Ergebnis von Spiel 74 → bis dahin TBD

Schreibt wm['koFixtures'] = [ {matchKey, round, roundLabel, matchNo, home, away, homeRef, awayRef,
homeResolved, awayResolved, bothResolved, kickoff, date, venue, venueId, winnerTo, result}, ... ].
Beide Teams aufgelöst (bothResolved) = Card kann generiert werden (zweistufig: erst Vorschau, dann
Pick sobald Quoten da). Reine Funktionen (testbar); `apply_to_wm(wm)` schreibt in-place + idempotent.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

FINISHED = {"FT", "AET", "PEN", "AWD", "WO"}

# Bracket-Sektion → (Runden-Code, deutsches Label). 48er-WM: erste KO-Runde = Sechzehntelfinale.
ROUND_MAP = {
    "round_of_32":   ("R32", "Sechzehntelfinale"),
    "round_of_16":   ("R16", "Achtelfinale"),
    "quarterfinals": ("QF",  "Viertelfinale"),
    "semifinals":    ("SF",  "Halbfinale"),
    "final":         ("F",   "Finale"),
    "third_place":   ("3RD", "Spiel um Platz 3"),
}
ROUND_ORDER = ["R32", "R16", "QF", "SF", "3RD", "F"]


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _group_complete(groups: dict, gid: str) -> bool:
    """Gruppe positionell fixiert = alle ihre Spiele beendet."""
    gd = (groups or {}).get(gid) or {}
    fxs = gd.get("fixtures") or []
    if not fxs:
        return False
    return all(str((fx.get("result") or {}).get("status", "")).upper() in FINISHED for fx in fxs)


def _kickoff_utc(date_str: str, local_hhmm: str, venue_id: str, venues: dict) -> str | None:
    """date (YYYY-MM-DD) + lokale HH:MM + Venue-TZ → ISO-UTC mit Z. Ohne TZ/Datum → None."""
    if not (date_str and local_hhmm):
        return None
    v = (venues or {}).get(venue_id) or {}
    off = v.get("tz_offset_h_utc")
    if off is None:
        return None
    try:
        local = datetime.strptime(f"{date_str} {local_hhmm}", "%Y-%m-%d %H:%M")
    except Exception:
        return None
    utc = local - timedelta(hours=float(off))
    return utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_side(side, groups: dict, standings: dict, ko_winners: dict) -> tuple:
    """Eine Bracket-Seite auflösen. Gibt (team_id_or_None, human_ref_label) zurück."""
    # Sieger-Referenz: "W74"
    if isinstance(side, str):
        if side.startswith("W"):
            mno = side[1:]
            return ko_winners.get(mno), f"Sieger Spiel {mno}"
        return None, str(side)

    if not isinstance(side, dict):
        return None, "TBD"

    typ = side.get("type")
    if typ == "group_position":
        g = side.get("group")
        pos = int(side.get("position", 0))
        if pos == 1:
            ref = f"Sieger Gruppe {g}"
        else:
            ref = f"{pos}. Gruppe {g}"
        if g and pos and _group_complete(groups, g):
            rows = (standings or {}).get(g) or []
            if len(rows) >= pos:
                return rows[pos - 1].get("team"), ref
        return None, ref

    if typ == "best_third":
        froms = side.get("from_groups") or []
        ref = f"Bester Dritter ({'/'.join(froms)})" if froms else "Bester Dritter"
        # TODO offizielle FIFA-Zuordnungstabelle (welcher Dritte in welchen Slot) — braucht alle 12
        # Gruppen fertig. Bis dahin bewusst TBD statt zu raten (mehrere Slots passen sonst).
        return None, ref

    return None, "TBD"


def build_ko_fixtures(bracket: dict, groups: dict, standings: dict,
                      venues: dict, ko_winners: dict | None = None) -> list[dict]:
    """Bracket-Raster → Liste aufgelöster (oder TBD-) KO-Fixtures, chronologisch."""
    ko_winners = ko_winners or {}
    out = []
    for section, matches in (bracket or {}).items():
        if section.startswith("_") or not isinstance(matches, dict):
            continue
        rcode, rlabel = ROUND_MAP.get(section, (section.upper(), section))
        for mkey, m in matches.items():
            if not isinstance(m, dict):
                continue
            home, home_ref = _resolve_side(m.get("side_a"), groups, standings, ko_winners)
            away, away_ref = _resolve_side(m.get("side_b"), groups, standings, ko_winners)
            vid = m.get("venue_id")
            venue_name = ((venues or {}).get(vid) or {}).get("city") or vid
            out.append({
                "matchKey":     f"{rcode}-{mkey}",
                "round":        rcode,
                "roundLabel":   rlabel,
                "matchNo":      m.get("matchNo"),
                "home":         home,
                "away":         away,
                "homeRef":      home_ref,
                "awayRef":      away_ref,
                "homeResolved": home is not None,
                "awayResolved": away is not None,
                "bothResolved": home is not None and away is not None,
                "kickoff":      _kickoff_utc(m.get("date"), m.get("kickoff_local"), vid, venues),
                "date":         m.get("date"),
                "venue":        venue_name,
                "venueId":      vid,
                "winnerTo":     m.get("winner_to"),
                "result":       None,
            })
    out.sort(key=lambda f: (ROUND_ORDER.index(f["round"]) if f["round"] in ROUND_ORDER else 99,
                            f.get("matchNo") or 0))
    return out


def apply_to_wm(wm: dict, bracket: dict | None = None, venues: dict | None = None) -> list[dict]:
    """Schreibt wm['koFixtures'] in-place. Standings müssen vorher gebaut sein (wm_standings)."""
    base = os.path.dirname(os.path.abspath(__file__))
    if bracket is None:
        bracket = _load_json(os.path.join(base, "wm_bracket.json"))
    if venues is None:
        try:
            _vraw = _load_json(os.path.join(base, "wm_venues.json"))
            # Venues liegen verschachtelt unter "venues"; Fallback auf Top-Level
            venues = _vraw.get("venues") if isinstance(_vraw, dict) and "venues" in _vraw else _vraw
        except Exception:
            venues = {}
    # Sieger bereits gespielter KO-Spiele (für W-Refs) aus evtl. vorhandenen koFixtures-Ergebnissen
    ko_winners = {}
    for f in (wm.get("koFixtures") or []):
        res = f.get("result") or {}
        w = res.get("winner")
        if w and f.get("matchNo") is not None:
            ko_winners[str(f["matchNo"])] = w
    ko = build_ko_fixtures(bracket, wm.get("groups") or {}, wm.get("standings") or {},
                           venues, ko_winners)
    # API-aufgelöste Gegner + Ergebnisse ERHALTEN (29.06.2026, Lucas: GER-PRY/FRA-Cards verschwanden,
    # weil apply_to_wm koFixtures komplett neu baute → die fetch_wm_match_results-Gegnerfüllung
    # (Best-Dritter aus echten API-Paarungen) + geschriebene Endstände wurden überbügelt). Nur Slots
    # füllen, die der Bracket-Build selbst NICHT auflösen konnte (None) — bracket bleibt autoritativ.
    _prev = {f["matchKey"]: f for f in (wm.get("koFixtures") or []) if f.get("matchKey")}
    for f in ko:
        old = _prev.get(f.get("matchKey"))
        if not old:
            continue
        if f.get("home") is None and old.get("home"):
            f["home"] = old["home"]
        if f.get("away") is None and old.get("away"):
            f["away"] = old["away"]
        if old.get("result") and not f.get("result"):
            f["result"] = old["result"]
        f["homeResolved"] = f.get("home") is not None
        f["awayResolved"] = f.get("away") is not None
        f["bothResolved"] = f["homeResolved"] and f["awayResolved"]
    wm["koFixtures"] = ko
    return ko


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "wm2026-data.json")
    wm = _load_json(path)
    # Standings sicherstellen (idempotent)
    try:
        import wm_standings
        wm_standings.apply_to_wm(wm)
    except Exception as e:
        print(f"  ⚠️  wm_standings nicht ausgeführt: {e}")
    ko = apply_to_wm(wm)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)
    resolved = sum(1 for f in ko if f["bothResolved"])
    print("=== resolve_wm_bracket.py ===")
    print(f"  {len(ko)} KO-Slots · {resolved} mit beiden Teams fix · {len(ko) - resolved} TBD")
    for f in ko:
        if f["bothResolved"]:
            print(f"  {f['matchKey']:9} {f['home']} vs {f['away']}  ({f['roundLabel']}, {f['date']})")


if __name__ == "__main__":
    main()
