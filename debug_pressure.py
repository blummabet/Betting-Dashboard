#!/usr/bin/env python3
"""
DEBUG: Warum werden Burnley und Luton mit motiv=none gekennzeichnet?
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

team_stats = defaultdict(TeamStats)
table = LeagueTable()

# Baue Tabelle bis zu einem bestimmten Punkt
target_date = "2024-05-11"

for game_idx, (_, row) in enumerate(df.iterrows()):
    date_str = str(row.get("Date", "?"))[:10]
    if date_str > target_date:
        break

    home = str(row["HomeTeam"]).strip()
    away = str(row["AwayTeam"]).strip()
    hg = int(row["FTHG"])
    ag = int(row["FTAG"])

    team_stats[home].record_home(hg, ag)
    team_stats[away].record_away(ag, hg)
    table.update(home, away, hg, ag)

print(f"Tabellenstand vor 11.05.2024:")
snap = table.snapshot()
for i in range(15, 20):
    r = snap[i]
    print(f"{r['pos']:2d}. {r['team']:20s} {r['pts']:2d} Pkte | "
          f"W:{r['w']} D:{r['d']} L:{r['l']} | "
          f"GF:{r['gf']} GA:{r['ga']} GD:{r['gd']:+d}")

print("\n" + "="*80)
print("ANALYSE: BURNLEY")
print("="*80)

burnley_pos = table.team_pos(snap, "Burnley")
burnley_pts = table.team_pts(snap, "Burnley")
burnley_games = team_stats["Burnley"].games_played()
burnley_rl = max(0, total_rounds - burnley_games)

print(f"\nBurnley Status vor 11.05:")
print(f"  Position: {burnley_pos}")
print(f"  Punkte: {burnley_pts}")
print(f"  Spiele: {burnley_games}")
print(f"  Runden übrig: {burnley_rl}")

h_pr = calc_pressure_and_motiv("Burnley", snap, table, league_cfg, burnley_rl)
print(f"\nPressure-Ergebnis:")
print(f"  ratio: {h_pr[0]}")
print(f"  mustWin: {h_pr[1]}")
print(f"  canDraw: {h_pr[2]}")
print(f"  motiv: {h_pr[3]}")

# Debug die Berechnung
rel_start = 18
safe_pos = 17
danger_pos = 14
max_gain = burnley_rl * 3

print(f"\nDebug-Zwischenschritte:")
print(f"  rel_start={rel_start}, safe_pos={safe_pos}, danger_pos={danger_pos}")
print(f"  max_gain = {burnley_rl} * 3 = {max_gain}")
print(f"  Burnley ist auf Platz {burnley_pos} (Abstiegszone ab {rel_start})")

if burnley_pos >= rel_start:
    print(f"  → Burnley ist in direkter Abstiegszone!")
    pts_safe = table.get_pts(snap, safe_pos)
    gap = pts_safe - burnley_pts
    print(f"  → Punkte auf Platz {safe_pos} (sicher): {pts_safe}")
    print(f"  → Gap: {pts_safe} - {burnley_pts} = {gap}")
    print(f"  → max_gain: {max_gain}")
    if gap > max_gain:
        print(f"  → {gap} > {max_gain}? JA! → motiv=none (mathematisch abgestiegen)")
    else:
        print(f"  → {gap} > {max_gain}? NEIN")

print("\n" + "="*80)
print("ANALYSE: LUTON")
print("="*80)

luton_pos = table.team_pos(snap, "Luton")
luton_pts = table.team_pts(snap, "Luton")
luton_games = team_stats["Luton"].games_played()
luton_rl = max(0, total_rounds - luton_games)

print(f"\nLuton Status vor 11.05:")
print(f"  Position: {luton_pos}")
print(f"  Punkte: {luton_pts}")
print(f"  Spiele: {luton_games}")
print(f"  Runden übrig: {luton_rl}")

l_pr = calc_pressure_and_motiv("Luton", snap, table, league_cfg, luton_rl)
print(f"\nPressure-Ergebnis:")
print(f"  ratio: {l_pr[0]}")
print(f"  mustWin: {l_pr[1]}")
print(f"  canDraw: {l_pr[2]}")
print(f"  motiv: {l_pr[3]}")

if luton_pos >= rel_start:
    print(f"  → Luton ist in direkter Abstiegszone!")
    pts_safe = table.get_pts(snap, safe_pos)
    gap = pts_safe - luton_pts
    print(f"  → Punkte auf Platz {safe_pos} (sicher): {pts_safe}")
    print(f"  → Gap: {pts_safe} - {luton_pts} = {gap}")
    print(f"  → max_gain: {luton_rl * 3}")
    if gap > luton_rl * 3:
        print(f"  → {gap} > {luton_rl * 3}? JA! → motiv=none")
    else:
        print(f"  → {gap} > {luton_rl * 3}? NEIN")

print("\n" + "="*80)
print("ANALYSE: SHEFFIELD UNITED")
print("="*80)

su_pos = table.team_pos(snap, "Sheffield United")
su_pts = table.team_pts(snap, "Sheffield United")
su_games = team_stats["Sheffield United"].games_played()
su_rl = max(0, total_rounds - su_games)

print(f"\nSheffield United Status vor 11.05:")
print(f"  Position: {su_pos}")
print(f"  Punkte: {su_pts}")
print(f"  Spiele: {su_games}")
print(f"  Runden übrig: {su_rl}")

su_pr = calc_pressure_and_motiv("Sheffield United", snap, table, league_cfg, su_rl)
print(f"\nPressure-Ergebnis:")
print(f"  ratio: {su_pr[0]}")
print(f"  mustWin: {su_pr[1]}")
print(f"  canDraw: {su_pr[2]}")
print(f"  motiv: {su_pr[3]}")

if su_pos >= rel_start:
    print(f"  → Sheffield United ist in direkter Abstiegszone!")
    pts_safe = table.get_pts(snap, safe_pos)
    gap = pts_safe - su_pts
    print(f"  → Punkte auf Platz {safe_pos} (sicher): {pts_safe}")
    print(f"  → Gap: {pts_safe} - {su_pts} = {gap}")
    print(f"  → max_gain: {su_rl * 3}")
    print(f"  → {gap} > {su_rl * 3}? {gap > su_rl * 3}")
