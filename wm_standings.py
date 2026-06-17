#!/usr/bin/env python3
"""
wm_standings.py — Gruppentabellen aus beendeten WM-Ergebnissen (17.06.2026).

Anlass (Lucas-Signal-Audit): `wm2026-data.json["standings"]` war LEER → incentive_signal
komplett tot, pressure_index halb tot (beide brauchen die Tabelle). Kein Script schrieb sie.

Baut pro Gruppe eine Tabelle im Format, das die Signale erwarten:
    standings = { "A": [ {team, played, points, gd, gf, ga, pos}, ... ], "B": [...], ... }
Sortiert nach FIFA-Tiebreaker: Punkte → Tordifferenz → erzielte Tore.

WM 2026 Format (verifiziert via FIFA/FOX/MLS): 12 Gruppen à 4, Top 2 JE Gruppe +
die 8 BESTEN Gruppendritten → Round of 32. `rank_third_placed` rankt die 12 Dritten
nach (Punkte, GD, GF) und markiert die Top 8 als qualifiziert — exakt nach Regel.

Reine Funktionen (testbar). `apply_to_wm(wm)` schreibt wm["standings"] + wm["thirdRanking"].
"""
from __future__ import annotations

FINISHED = {"FT", "AET", "PEN", "AWD", "WO"}


def build_standings(groups: dict) -> dict:
    """groups (wm['groups']) → { group_id: [team-row, …] } sortiert nach FIFA-Tiebreaker."""
    out = {}
    for gid, gdata in (groups or {}).items():
        if not isinstance(gdata, dict):
            continue
        # Alle Teams der Gruppe initialisieren (auch ohne Spiel → played 0)
        tbl = {}
        for t in (gdata.get("teams") or []):
            tid = t.get("id") if isinstance(t, dict) else t
            if tid:
                tbl[tid] = {"team": tid, "played": 0, "won": 0, "draw": 0, "lost": 0,
                            "points": 0, "gf": 0, "ga": 0, "gd": 0}
        for fx in (gdata.get("fixtures") or []):
            res = fx.get("result") or {}
            if str(res.get("status", "")).upper() not in FINISHED:
                continue
            h, a = fx.get("home"), fx.get("away")
            hs, as_ = res.get("home_score"), res.get("away_score")
            if h not in tbl or a not in tbl or hs is None or as_ is None:
                continue
            hs, as_ = int(hs), int(as_)
            for tid, gf, ga in ((h, hs, as_), (a, as_, hs)):
                r = tbl[tid]
                r["played"] += 1
                r["gf"] += gf
                r["ga"] += ga
                r["gd"] = r["gf"] - r["ga"]
                if gf > ga:
                    r["won"] += 1
                    r["points"] += 3
                elif gf == ga:
                    r["draw"] += 1
                    r["points"] += 1
                else:
                    r["lost"] += 1
        rows = sorted(tbl.values(),
                      key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
        for i, r in enumerate(rows):
            r["pos"] = i + 1
        out[gid] = rows
    return out


def rank_third_placed(standings: dict) -> list[dict]:
    """Die 12 Gruppendritten nach FIFA-Regel ranken (Punkte → GD → GF). Markiert die
    Top 8 als qualifiziert. Gibt Liste [{team, group, points, gd, gf, qualifies, rank}].
    Nur sinnvoll wenn alle/die meisten MD3-Spiele durch sind — taugt aber schon als
    Live-Projektion währenddessen."""
    thirds = []
    for gid, rows in (standings or {}).items():
        if len(rows) >= 3:
            r = rows[2]   # 3. Platz (0-indexiert)
            thirds.append({"team": r["team"], "group": gid,
                           "points": r["points"], "gd": r["gd"], "gf": r["gf"]})
    thirds.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(thirds):
        r["rank"] = i + 1
        r["qualifies"] = i < 8   # die 8 besten Dritten kommen weiter
    return thirds


def apply_to_wm(wm: dict) -> dict:
    """Schreibt wm['standings'] + wm['thirdRanking'] in-place. Gibt das Standings-Dict zurück."""
    standings = build_standings(wm.get("groups") or {})
    wm["standings"] = standings
    wm["thirdRanking"] = rank_third_placed(standings)
    return standings


def main():
    import json
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "wm2026-data.json")
    with open(path, encoding="utf-8") as f:
        wm = json.load(f)
    standings = apply_to_wm(wm)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wm, f, ensure_ascii=False, indent=2)
    n_rows = sum(len(v) for v in standings.values())
    played = sum(r["played"] for v in standings.values() for r in v)
    print(f"=== wm_standings.py ===")
    print(f"  {len(standings)} Gruppen · {n_rows} Team-Zeilen · {played // 2} Spiele verbucht")
    quali = [t for t in wm['thirdRanking'] if t['qualifies']]
    if quali:
        print(f"  Beste Dritte (Top 8 qualifiziert): "
              + ", ".join(f"{t['team']}({t['points']}P)" for t in quali[:8]))


if __name__ == "__main__":
    main()
