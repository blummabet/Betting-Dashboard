#!/usr/bin/env python3
"""
fetch_liga_elo.py — Club-Elo für die Top-5-Liga-Teams (26.06.2026, Lucas).

Füllt die Elo-Lücke (Liga-Teams hatten alle elo=None). Quelle: ClubElo (http://api.clubelo.com/<datum>
→ EIN CSV mit ALLEN Klubs). Schreibt team["elo"] in liga-data.json, pro Liga-Land gematcht.

WICHTIG (Lucas): Elo ist NUR Baseline/Evidenz/Kontext — NIE eine Pick-Quelle. Der aktive Pick-Pfad
ist Steam (generate_steam_picks_for_fixture → steam_engine), der keine Elo nutzt. Der alte
generate_picks_for_fixture (Elo-Edge-Pfad, der in WM-Runde 1 Phantom-Picks machte) wird für Liga
NICHT aufgerufen. Diese Datei verdrahtet Elo NICHT in die Pick-Erzeugung — sie setzt nur das Feld,
das Renderer/Evidenz/Fallback-Baseline (wenn mal keine Marktquote da ist) lesen.

Läuft im Liga-Workflow NACH build_liga_data (das elo=None setzt) und VOR den Picks. Kein API-Key
nötig (ClubElo ist offen). Namens-Matching reuse aus fetch_liga_odds (_norm_name/_names_match) +
ClubElo-spezifische Aliase. Reine Funktionen (parse/match) sind unit-getestet.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
import cocobet_dataset as D  # 29.06.2026: dataset-aware (MLS)
LIGA_FILE = D.data_file()   # 29.06.2026: liga-data.json ODER mls-data.json je COCOBET_DATASET

# Liga-Gruppe → ClubElo-Ländercode (Kandidaten je Land einschränken → weniger Fehlmatches).
GROUP_COUNTRY = {"ENG": "ENG", "ESP": "ESP", "GER": "GER", "ITA": "ITA", "FRA": "FRA"}

# ClubElo-Kurznamen → API-Football-naher Name (vor dem Matching aufgelöst). Erweiterbar bei Fehlern.
CLUBELO_ALIASES = {
    "man city": "manchester city", "man united": "manchester united", "man utd": "manchester united",
    "spurs": "tottenham", "wolves": "wolverhampton", "nott'm forest": "nottingham forest",
    "paris sg": "psg", "inter": "inter", "milan": "ac milan", "bayern": "bayern munich",
    "dortmund": "borussia dortmund", "leverkusen": "bayer leverkusen",
    "gladbach": "borussia monchengladbach", "atletico": "atletico madrid",
    "ath bilbao": "athletic club", "betis": "real betis", "sociedad": "real sociedad",
    "forest": "nottingham forest",
}


def parse_clubelo_csv(text: str) -> list[dict]:
    """ClubElo-CSV → [{club, country, elo}]. Reine Funktion (testbar)."""
    import csv
    import io
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        club, country, elo = r.get("Club"), r.get("Country"), r.get("Elo")
        if not club or elo in (None, ""):
            continue
        try:
            out.append({"club": club, "country": country, "elo": round(float(elo))})
        except ValueError:
            continue
    return out


def match_elo(teams: list[dict], rows: list[dict], country: str | None = None) -> dict:
    """{team_id: elo} per Namens-Match (optional auf ein Land beschränkt). Reine Funktion."""
    import fetch_liga_odds as O
    cands = [x for x in rows if (country is None or x.get("country") == country)]
    out = {}
    for t in teams:
        tid, tname = t.get("id"), t.get("name") or ""
        if not tid or not tname:
            continue
        best = None
        for x in cands:
            cname = CLUBELO_ALIASES.get(O._norm_name(x["club"]), x["club"])
            if O._norm_name(cname) == O._norm_name(tname):   # exakt zuerst
                best = x
                break
            if best is None and O._names_match(cname, tname):
                best = x
        if best is not None:
            out[tid] = best["elo"]
    return out


def main():
    print("=== fetch_liga_elo.py (Club-Elo) ===")
    if not LIGA_FILE.exists():
        print("  ❌  liga-data.json fehlt — erst build_liga_data.py.")
        sys.exit(1)
    import urllib.request
    url = f"http://api.clubelo.com/{os.environ.get('ELO_DATE') or date.today().isoformat()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CocoBet/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            rows = parse_clubelo_csv(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"  ⚠️  ClubElo nicht erreichbar ({e}) — Elo unverändert.")
        sys.exit(0)
    print(f"  ClubElo: {len(rows)} Klubs geladen")
    wm = json.loads(LIGA_FILE.read_text(encoding="utf-8"))
    total = matched = 0
    for gkey, gd in (wm.get("groups") or {}).items():
        teams = gd.get("teams") or []
        if not teams:
            continue
        elo_map = match_elo(teams, rows, GROUP_COUNTRY.get(gkey))
        miss = []
        for t in teams:
            total += 1
            e = elo_map.get(t.get("id"))
            if e is not None:
                t["elo"] = e
                matched += 1
            else:
                miss.append(t.get("name"))
        print(f"    {gkey}: {len(elo_map)}/{len(teams)} gematcht"
              + (f" · offen: {', '.join(m for m in miss if m)}" if miss else ""))
    LIGA_FILE.write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Elo an {matched}/{total} Teams gesetzt → liga-data.json")


if __name__ == "__main__":
    main()
