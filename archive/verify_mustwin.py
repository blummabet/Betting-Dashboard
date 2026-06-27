#!/usr/bin/env python3
"""
Überprüfe die 7 MustWin-Flaggen in den letzten 5 Runden.
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict
from backtest_v4 import (
    LeagueTable, TeamStats, calc_pressure_and_motiv, LEAGUE_CFGS
)

csv_path = Path("E0.csv")
df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines="skip")

if "Date" in df.columns:
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)

league_cfg = LEAGUE_CFGS["ENG"]
total_rounds = league_cfg["rounds"]
games_per_round = 10

# Letzten 5 Runden
last_n_rounds = 5
cutoff_idx = len(df) - (last_n_rounds * games_per_round)

team_stats = defaultdict(TeamStats)
table = LeagueTable()

# Baue Tabelle bis cutoff
for game_idx in range(cutoff_idx):
    row = df.iloc[game_idx]
    home = str(row["HomeTeam"]).strip()
    away = str(row["AwayTeam"]).strip()
    hg = int(row["FTHG"])
    ag = int(row["FTAG"])

    team_stats[home].record_home(hg, ag)
    team_stats[away].record_away(ag, hg)
    table.update(home, away, hg, ag)

print("MustWin-Analyse (letzten 5 Runden)\n")

mustwin_matches = []

for game_idx in range(cutoff_idx, len(df)):
    row = df.iloc[game_idx]
    home = str(row["HomeTeam"]).strip()
    away = str(row["AwayTeam"]).strip()
    hg = int(row["FTHG"])
    ag = int(row["FTAG"])
    date_str = str(row.get("Date", "?"))[:10]

    snap = table.snapshot()
    h_rounds_left = max(0, total_rounds - team_stats[home].games_played())
    a_rounds_left = max(0, total_rounds - team_stats[away].games_played())

    h_pr = calc_pressure_and_motiv(home, snap, table, league_cfg, h_rounds_left)
    a_pr = calc_pressure_and_motiv(away, snap, table, league_cfg, a_rounds_left)

    h_ratio, h_mw, h_cd, h_motiv = h_pr
    a_ratio, a_mw, a_cd, a_motiv = a_pr

    if h_mw or a_mw:
        mustwin_matches.append({
            "date": date_str,
            "home": home,
            "away": away,
            "result": f"{hg}-{ag}",
            "h_pos": table.team_pos(snap, home),
            "a_pos": table.team_pos(snap, away),
            "h_rl": h_rounds_left,
            "a_rl": a_rounds_left,
            "h_mw": h_mw,
            "a_mw": a_mw,
            "h_ratio": h_ratio,
            "a_ratio": a_ratio,
            "h_motiv": h_motiv,
            "a_motiv": a_motiv,
        })

    team_stats[home].record_home(hg, ag)
    team_stats[away].record_away(ag, hg)
    table.update(home, away, hg, ag)

print(f"Total MustWin-Spiele: {len(mustwin_matches)}\n")
print("="*120)

for i, m in enumerate(mustwin_matches, 1):
    print(f"\n{i}. {m['date']} | {m['home']:15s} ({m['h_pos']:2d}) vs {m['away']:15s} ({m['a_pos']:2d})")
    print(f"   Ergebnis: {m['result']}")
    print(f"   Home: RL={m['h_rl']:2d}, Ratio={m['h_ratio']:.3f}, mustWin={m['h_mw']}, motiv={m['h_motiv']}")
    print(f"   Away: RL={m['a_rl']:2d}, Ratio={m['a_ratio']:.3f}, mustWin={m['a_mw']}, motiv={m['a_motiv']}")

print("\n" + "="*120)
print("\nVALIDIERUNG:")
print("MustWin sollte setzen wenn:")
print("  - pressure_ratio > 0.30 UND motiv='full'")
print("\nTeams mit Druck in dieser Phase:")
print("  - Arsenal (Titelkampf, Platz 2)")
print("  - Liverpool (Titelkampf, Platz 3)")
print("  - Man City (Titelkampf, Platz 2-3)")
print("  - Tottenham (Champions League, Platz 5)")
print("  - Aston Villa (Champions League, Platz 4)")
print("  - Luton, Burnley, Sheffield United (Abstiegskampf)")
