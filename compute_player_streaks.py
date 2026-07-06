#!/usr/bin/env python3
"""compute_player_streaks.py — Spieler-Serien als quotenloses Content-Produkt (06.07.2026, Lucas).

Analog zu den Team-Serien (compute_streaks.py), aber pro SPIELER aus dem player_form_ledger
(eine Zeile je Spieler/Spiel: goals, assists, minutes, ts, fixtureId, teamId). Drei Serien-Typen:

  • goals       — Spieler trifft im N. Spiel in Folge (goals >= 1)
  • involvement — Tor ODER Assist in N Spielen in Folge (goals + assists >= 1)   [stabilerer Hook]
  • cleanSheet  — Torwart N Spiele in Folge ohne Gegentor (aus der Team-Zu-Null-Serie + GK aus Lineups)

WICHTIG (Scope-Disziplin): reines Content-Produkt (TikTok/Telegram Public), TikTok-safe (keine
Quoten/€), NICHT in Picks/Trading/Lern-Loop. Player-*Props* als Wettmarkt bleiben aus.

WICHTIG (Elimination): nur Spieler ausgeschiedener... nein — nur Spieler von Teams, die NOCH im
Turnier sind (Team hat ein `next`-Spiel). Eine Serie ohne nächstes Spiel ist wertlos.

Dataset-aware (WM/MLS/Liga) über cocobet_dataset. Reine Funktionen → testbar.

Run: python3 compute_player_streaks.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D

BASE = Path(__file__).parent

LEDGER_FILE  = D.file("player_form_ledger.json", "liga_player_form_ledger.json")
LINEUPS_FILE = D.file("wm_lineups.json", "liga_lineups.json")
STREAKS_FILE = D.file("wm_streaks.json", "liga_streaks.json")

MIN_GOALS_LEN       = 2   # ab 2 Toren in Folge interessant (Spieler-Tore sind selten)
MIN_INVOLVEMENT_LEN = 3   # Torbeteiligung häufiger → höhere Schwelle
MIN_CLEANSHEET_LEN  = 2

# code → englischer API-Football-Name (Kopie aus fetch_wm_nt_xg.py; bei Updates synchron halten).
APIF_NAME_OVERRIDE: dict[str, str] = {
    "ARG": "Argentina", "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium",
    "BIH": "Bosnia", "BRA": "Brazil", "CAN": "Canada", "CIV": "Ivory Coast",
    "COD": "Congo DR", "COL": "Colombia", "CPV": "Cape Verde", "CRO": "Croatia",
    "CUW": "Curacao", "CZE": "Czech Republic", "DZA": "Algeria", "ECU": "Ecuador",
    "EGY": "Egypt", "ENG": "England", "ESP": "Spain", "FRA": "France",
    "GER": "Germany", "GHA": "Ghana", "HTI": "Haiti", "IRN": "Iran",
    "IRQ": "Iraq", "JOR": "Jordan", "JPN": "Japan", "KOR": "South Korea",
    "MAR": "Morocco", "MEX": "Mexico", "NED": "Netherlands", "NOR": "Norway",
    "NZL": "New Zealand", "PAN": "Panama", "POR": "Portugal", "PRY": "Paraguay",
    "QAT": "Qatar", "SAU": "Saudi Arabia", "SCO": "Scotland", "SEN": "Senegal",
    "SUI": "Switzerland", "SWE": "Sweden", "TUN": "Tunisia", "TUR": "Türkiye",
    "URU": "Uruguay", "USA": "United States", "UZB": "Uzbekistan", "ZAF": "South Africa",
}


def _load(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


# ── Auflösung numerische teamId ↔ WM-Code + Torwart je Team ─────────────────────
def build_team_maps(lineups: dict) -> tuple[dict, dict]:
    """Aus wm_lineups: numerische teamId → WM-Code (via englischer Name) und teamId → aktuellster GK.
    Returns (id2code {int:code}, gk_by_id {int:{'id','name','ts'}})."""
    name2code = {v.lower(): k for k, v in APIF_NAME_OVERRIDE.items()}
    id2code: dict[int, str] = {}
    gk_by_id: dict[int, dict] = {}
    for key, fx in (lineups or {}).items():
        if not isinstance(fx, dict):
            continue
        ts = str(fx.get("kickoff") or "")
        for side in ("home", "away"):
            t = fx.get(side) or {}
            tid = t.get("team_id")
            if not isinstance(tid, int):
                continue
            code = name2code.get(str(t.get("team_name") or "").lower())
            if code and tid not in id2code:
                id2code[tid] = code
            for pl in (t.get("starting") or []):
                if pl.get("pos") == "G" and pl.get("id"):
                    prev = gk_by_id.get(tid)
                    if prev is None or ts > prev.get("ts", ""):
                        gk_by_id[tid] = {"id": pl.get("id"), "name": pl.get("name"), "ts": ts}
    return id2code, gk_by_id


def build_alive_map(streaks: list) -> dict:
    """WM-Code → {'team','flag','next'} für Teams, die NOCH ein Spiel haben (alive).
    Quelle: die Team-Serien (die tragen `next` + `flag` + Anzeigename). Team ohne next = raus."""
    alive: dict[str, dict] = {}
    for s in streaks or []:
        code = s.get("teamId")
        nx = s.get("next")
        if code and nx and code not in alive:
            alive[code] = {"team": s.get("team"), "flag": s.get("flag") or "", "next": nx}
    return alive


# ── Serien-Kern ─────────────────────────────────────────────────────────────────
def _trailing_run(flags: list[bool]) -> int:
    """Länge der jüngsten True-Serie am Ende der (chronologischen) Liste."""
    n = 0
    for f in reversed(flags):
        if f:
            n += 1
        else:
            break
    return n


def player_goal_streaks(ledger_records: list, id2code: dict, alive: dict) -> list:
    """Torserie + Torbeteiligung je Spieler. Nur Teams in `alive`. Chronologisch aus dem Ledger."""
    by_player: dict = {}
    for r in ledger_records or []:
        if (r.get("minutes") or 0) <= 0:      # nur echte Einsätze
            continue
        by_player.setdefault(r.get("playerId"), []).append(r)

    out = []
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: str(r.get("ts") or ""))
        tid = rows[-1].get("teamId")
        code = id2code.get(tid)
        if not code or code not in alive:
            continue
        goal_flags = [(r.get("goals") or 0) >= 1 for r in rows]
        inv_flags  = [((r.get("goals") or 0) + (r.get("assists") or 0)) >= 1 for r in rows]
        team = alive[code]
        base = {"playerId": pid, "name": rows[-1].get("name"), "teamCode": code,
                "team": team["team"], "flag": team["flag"], "next": team["next"]}
        g = _trailing_run(goal_flags)
        if g >= MIN_GOALS_LEN:
            out.append({**base, "type": "goals", "market": "Tor", "length": g,
                        "seq": goal_flags[-9:]})
        inv = _trailing_run(inv_flags)
        # Torbeteiligung nur zeigen, wenn sie ÜBER die reine Torserie hinausgeht (sonst redundant).
        if inv >= MIN_INVOLVEMENT_LEN and inv > g:
            out.append({**base, "type": "involvement", "market": "Torbeteiligung", "length": inv,
                        "seq": inv_flags[-9:]})
    return out


def gk_cleansheet_streaks(streaks: list, id2code: dict, gk_by_id: dict, alive: dict) -> list:
    """Zu-Null-Serien: aus den Team-cleanSheet-Serien (alive) + Torwart-Name aus den Lineups."""
    code2id = {c: i for i, c in id2code.items()}
    out = []
    for s in streaks or []:
        if s.get("type") != "cleanSheet" or (s.get("venue") or "all") != "all":
            continue   # nur die Gesamt-Serie (venue=all), sonst Dubletten aus H/A-Varianten
        code = s.get("teamId")
        if not code or code not in alive or (s.get("length") or 0) < MIN_CLEANSHEET_LEN:
            continue
        gk = gk_by_id.get(code2id.get(code))
        if not gk:
            continue
        team = alive[code]
        out.append({"playerId": gk["id"], "name": gk["name"], "teamCode": code,
                    "team": team["team"], "flag": team["flag"], "next": team["next"],
                    "type": "cleanSheet", "market": "Zu Null", "length": s.get("length"),
                    "seq": (s.get("seq") or [])[-9:]})
    return out


def compute(ledger: dict, lineups: dict, streaks: list) -> list:
    """Alle Spieler-Serien (goals/involvement/cleanSheet), heat-sortiert (längste zuerst)."""
    records = ledger.get("records") if isinstance(ledger, dict) else (ledger or [])
    id2code, gk_by_id = build_team_maps(lineups)
    alive = build_alive_map(streaks)
    res = player_goal_streaks(records, id2code, alive) + \
          gk_cleansheet_streaks(streaks, id2code, gk_by_id, alive)
    # Dedup pro (Spieler, Typ): stärkste behalten (schützt gegen doppelte Quell-Einträge)
    best: dict = {}
    for s in res:
        k = (s.get("playerId"), s.get("type"))
        if k not in best or (s.get("length") or 0) > (best[k].get("length") or 0):
            best[k] = s
    out = list(best.values())
    out.sort(key=lambda s: -(s.get("length") or 0))
    return out


def main():
    ledger  = _load(LEDGER_FILE, {"records": []})
    lineups = _load(LINEUPS_FILE, {})
    streaks = (_load(STREAKS_FILE, {}) or {}).get("streaks") or []
    players = compute(ledger, lineups, streaks)
    out = {"_meta": {"dataset": D.active_dataset(),
                     "generatedAt": datetime.now(timezone.utc).isoformat(),
                     "count": len(players)},
           "players": players}
    dst = BASE / f"{D.prefix()}player_streaks.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    by_type = {}
    for p in players:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
    print(f"✅ {len(players)} Spieler-Serien ({D.active_dataset()}): {by_type} → {dst.name}")


if __name__ == "__main__":
    main()
