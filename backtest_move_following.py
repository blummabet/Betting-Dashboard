#!/usr/bin/env python3
"""
backtest_move_following.py — Fundament-Backtest: traegt "dem Pinnacle-Move folgen"?
(25.07.2026, Lucas: historisches Move-/Analog-Signal fuer die Top-5-Ligen)

Nutzt die football-data.co.uk-CSVs (D1/E0/F1/I1/SP1 x 4 Saisons), die als EINZIGE
Quelle historische Pinnacle-CLOSING-Odds tragen (PSCH/PSCD/PSCA). Fuer die MLS ist das
unmoeglich (keine hist. Quoten) — deshalb ist DIESER ROI/CLV-Backtest ueberhaupt baubar,
den liga_backtest.py bisher liegen laesst ("ohne Quoten/ROI").

REGEL: de-vigge Pinnacle Opening (PSH/PSD/PSA) -> Closing (PSCH/PSCD/PSCA), setze auf die
Seite mit der groessten Wahrscheinlichkeits-ZUNAHME (wohin das Geld zog), Einsatz zur
OPENING-Quote, Abrechnung gegen FTR. Misst ROI / Trefferquote / CLV, gebucketet nach
Move-Groesse + Quotenband, je Liga/Saison. Plus ehrlicher Out-of-Sample-Split.

WICHTIG — idealisierter Einstieg: wir setzen zur OPENING-Quote NACHDEM der Move Richtung
gezeigt hat. Live bekommt man die Opening-Quote so nicht mehr -> der ROI ist eine
OBERGRENZE, nicht die live erzielbare Rendite. Ehrlich so labeln.

REIN LESEND. Kein Pipeline-Output, kein Live-Eingriff, nur stdlib. Aufruf:
    python3 backtest_move_following.py
"""
from __future__ import annotations

import csv
import datetime
import glob
import os
from collections import defaultdict, deque

# ── Saison-Zuordnung der Dateinamen (football-data.co.uk) ────────────────────
# X_2122.csv = 2021/22, X_2223.csv = 2022/23, X.csv = 2023/24, "X (1).csv" = 2024/25.
LEAGUES = ("D1", "E0", "F1", "I1", "SP1")
LEAGUE_NAME = {"D1": "Bundesliga", "E0": "Premier League", "F1": "Ligue 1",
               "I1": "Serie A", "SP1": "La Liga"}

GATE_DEFAULT = 0.02           # Mindest-Move (Close-Open pp) damit ueberhaupt gewettet wird
MOVE_EDGES = (0.03, 0.05)     # Bucket-Grenzen: <3pp / 3-5pp / 5pp+
ODDS_BANDS = ((0.0, 2.0, "fav<2.0"), (2.0, 3.5, "mid2-3.5"), (3.5, 1e9, "dog>3.5"))
OOS_TRAIN_SEASONS = ("2021/22", "2022/23", "2023/24")
OOS_TEST_SEASON = "2024/25"
GATE_CANDIDATES = (0.02, 0.03, 0.05)


def season_of(fname: str) -> str:
    b = os.path.basename(fname)
    if "_2122" in b:
        return "2021/22"
    if "_2223" in b:
        return "2022/23"
    if "(1)" in b:
        return "2024/25"
    return "2023/24"


def league_of(fname: str) -> str:
    b = os.path.basename(fname)
    for lg in ("SP1", "D1", "E0", "F1", "I1"):   # SP1 vor D1/E0 wegen Praefix-Eindeutigkeit
        if b.startswith(lg):
            return lg
    return "?"


def discover_files(base: str = ".") -> list:
    """Alle Top-5-CSVs, dedupliziert nach (Liga, Saison) — je Kombi genau eine Datei."""
    found = {}
    for lg in LEAGUES:
        for f in glob.glob(os.path.join(base, f"{lg}*.csv")):
            key = (league_of(f), season_of(f))
            found.setdefault(key, f)   # erste gewinnt; Kombis sind ohnehin eindeutig
    return sorted(found.values())


def devig(h, d, a):
    """De-viggte 1X2-Wahrscheinlichkeiten (H, D, A) oder None bei kaputten Quoten."""
    try:
        ih, idr, ia = 1.0 / float(h), 1.0 / float(d), 1.0 / float(a)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = ih + idr + ia
    if s <= 0:
        return None
    return (ih / s, idr / s, ia / s)


def move_pick(open_p, close_p, gate: float):
    """Index (0=H,1=D,2=A) der Seite mit groesster Wkt-Zunahme Open->Close, wenn >= gate.
    None, wenn kein Move das Gate erreicht."""
    if not open_p or not close_p:
        return None
    moves = [close_p[i] - open_p[i] for i in range(3)]
    i = max(range(3), key=lambda k: moves[k])
    return (i, moves[i]) if moves[i] >= gate else None


def settle(idx: int, ftr: str, open_odds):
    """(won, pnl) fuer 1 Einheit Einsatz zur Opening-Quote der Seite idx gegen FTR."""
    won = (ftr == "H" and idx == 0) or (ftr == "D" and idx == 1) or (ftr == "A" and idx == 2)
    return won, (float(open_odds[idx]) - 1.0) if won else -1.0


def _move_bucket(mv: float) -> str:
    if mv < MOVE_EDGES[0]:
        return f"<{int(MOVE_EDGES[0]*100)}pp"
    if mv < MOVE_EDGES[1]:
        return f"{int(MOVE_EDGES[0]*100)}-{int(MOVE_EDGES[1]*100)}pp"
    return f"{int(MOVE_EDGES[1]*100)}pp+"


def _odds_band(o: float) -> str:
    for lo, hi, lbl in ODDS_BANDS:
        if lo <= o < hi:
            return lbl
    return "?"


class Acc:
    __slots__ = ("n", "win", "pnl", "clv")

    def __init__(self):
        self.n = self.win = 0
        self.pnl = self.clv = 0.0

    def add(self, won: bool, pnl: float, clv: float):
        self.n += 1
        self.win += 1 if won else 0
        self.pnl += pnl
        self.clv += clv

    def roi(self):
        return (self.pnl / self.n * 100) if self.n else 0.0

    def hit(self):
        return (self.win / self.n * 100) if self.n else 0.0

    def avg_clv(self):
        return (self.clv / self.n * 100) if self.n else 0.0


def iter_bets(files, gate: float):
    """Yield (league, season, move, idx, won, pnl, open_odds[idx]) je gewetteter Partie."""
    for f in files:
        lg, se = league_of(f), season_of(f)
        try:
            rows = list(csv.DictReader(open(f, encoding="latin-1")))
        except OSError:
            continue
        for r in rows:
            op = devig(r.get("PSH"), r.get("PSD"), r.get("PSA"))
            cp = devig(r.get("PSCH"), r.get("PSCD"), r.get("PSCA"))
            ftr = r.get("FTR")
            if ftr not in ("H", "D", "A"):
                continue
            try:
                oo = [float(r["PSH"]), float(r["PSD"]), float(r["PSA"])]
            except (TypeError, ValueError, KeyError):
                continue
            pick = move_pick(op, cp, gate)
            if not pick:
                continue
            idx, mv = pick
            won, pnl = settle(idx, ftr, oo)
            yield (lg, se, mv, idx, won, pnl, oo[idx])


def evaluate(files, gate: float = GATE_DEFAULT) -> dict:
    overall = Acc()
    by_size, by_band, by_league = defaultdict(Acc), defaultdict(Acc), defaultdict(Acc)
    for lg, se, mv, idx, won, pnl, o in iter_bets(files, gate):
        clv = mv   # Close-Open der gewetteten Seite = realisierter CLV-Proxy
        overall.add(won, pnl, clv)
        by_size[_move_bucket(mv)].add(won, pnl, clv)
        by_band[_odds_band(o)].add(won, pnl, clv)
        by_league[lg].add(won, pnl, clv)
    return {"overall": overall, "by_size": by_size, "by_band": by_band, "by_league": by_league}


def best_gate(train_files, candidates=GATE_CANDIDATES, min_bets: int = 100):
    """Waehlt das Gate mit hoechstem ROI auf den Trainings-Saisons (min_bets als Guard)."""
    best, best_roi = candidates[0], -1e9
    for g in candidates:
        acc = evaluate(train_files, g)["overall"]
        if acc.n >= min_bets and acc.roi() > best_roi:
            best, best_roi = g, acc.roi()
    return best, best_roi


# ── Schritt 2: leakage-freies Zustands-Feature (25.07.2026) ──────────────────
# Rollende xG-Proxy (Schuesse aufs Tor netto, letzte 5) + Form-5, NUR aus Spielen VOR
# der Partie. Testet die POC-These: rettet Zustands-Bestaetigung die schwachen sub-5pp-Moves?
FORM_W = 0.15            # Gewicht Form-Differenz relativ zur SOT-Netto-Differenz
STATE_MIN_GAMES = 3      # darunter Zustand undefiniert (Saison-Anfang)


def parse_date(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def _rolling_state(rows):
    """Generator je Partie (Datums-Reihenfolge): (row, stateHome, stateWeg) mit dem
    Zustand VOR dem Spiel (leakage-free). state = (form_avg, sot_net) oder None (zu jung).
    Aktualisiert NACH dem Yield mit den Post-Match-Statistiken (dann erlaubt)."""
    form = defaultdict(lambda: deque(maxlen=5))
    sotf = defaultdict(lambda: deque(maxlen=5))
    sota = defaultdict(lambda: deque(maxlen=5))
    dated = [(parse_date(r.get("Date", "")), r) for r in rows]
    dated = [(d, r) for d, r in dated if d is not None]
    dated.sort(key=lambda x: x[0])

    def strength(t):
        if len(sotf[t]) < STATE_MIN_GAMES:
            return None
        f = sum(form[t]) / len(form[t])
        net = sum(sotf[t]) / len(sotf[t]) - sum(sota[t]) / len(sota[t])
        return (f, net)

    for _, r in dated:
        H, A = r.get("HomeTeam"), r.get("AwayTeam")
        yield r, strength(H), strength(A)
        try:                                   # Update NACH dem Spiel (Post-Match erlaubt)
            hg, ag = int(r["FTHG"]), int(r["FTAG"])
            form[H].append(3 if hg > ag else 1 if hg == ag else 0)
            form[A].append(3 if ag > hg else 1 if hg == ag else 0)
            sotf[H].append(float(r["HST"])); sota[H].append(float(r["AST"]))
            sotf[A].append(float(r["AST"])); sota[A].append(float(r["HST"]))
        except (KeyError, ValueError, TypeError):
            pass


def state_edge(moved_idx, s_home, s_away):
    """Zustands-Vorteil der GEWETTETEN Seite (nur H/A). None bei Draw-Move oder fehlendem
    Zustand. >0 = Team-Daten stuetzen den Move, <0 = Daten widersprechen ihm."""
    if moved_idx not in (0, 2) or not s_home or not s_away:
        return None
    moved, opp = (s_home, s_away) if moved_idx == 0 else (s_away, s_home)
    return (moved[1] - opp[1]) + FORM_W * (moved[0] - opp[0])


def evaluate_state(files, gate: float = GATE_DEFAULT) -> dict:
    """Buckets nach Zustand (bestaetigt/widerspricht), gesamt + je Move-Zone. Leakage-free."""
    buckets = defaultdict(Acc)
    for f in files:
        try:
            rows = list(csv.DictReader(open(f, encoding="latin-1")))
        except OSError:
            continue
        for r, sH, sA in _rolling_state(rows):
            op = devig(r.get("PSH"), r.get("PSD"), r.get("PSA"))
            cp = devig(r.get("PSCH"), r.get("PSCD"), r.get("PSCA"))
            ftr = r.get("FTR")
            if ftr not in ("H", "D", "A"):
                continue
            try:
                oo = [float(r["PSH"]), float(r["PSD"]), float(r["PSA"])]
            except (TypeError, ValueError, KeyError):
                continue
            pick = move_pick(op, cp, gate)
            if not pick:
                continue
            idx, mv = pick
            edge = state_edge(idx, sH, sA)
            if edge is None:               # Draw-Move oder Zustand unbekannt -> raus
                continue
            won, pnl = settle(idx, ftr, oo)
            state = "bestaetigt" if edge > 0 else "widerspricht"
            buckets[state].add(won, pnl, mv)
            buckets[f"{state} | {_move_bucket(mv)}"].add(won, pnl, mv)
    return buckets


def _line(label, acc: Acc):
    return f"  {label:24} n={acc.n:4}  hit={acc.hit():4.1f}%  ROI={acc.roi():+6.2f}%  CLV={acc.avg_clv():+.2f}pp"


def main():
    files = discover_files(os.path.dirname(os.path.abspath(__file__)))
    if not files:
        print("Keine Top-5-CSVs gefunden.")
        return
    print(f"Dateien: {len(files)} (Liga x Saison, dedupliziert)\n")

    res = evaluate(files, GATE_DEFAULT)
    o = res["overall"]
    print(f"=== IN-SAMPLE (alle Saisons, Gate>={int(GATE_DEFAULT*100)}pp) ===")
    print(_line("BASIS", o))
    print("\n nach Move-Groesse:")
    for k in sorted(res["by_size"], key=lambda x: (len(x), x)):
        print(_line(k, res["by_size"][k]))
    print("\n nach Quote der Move-Seite:")
    for k in sorted(res["by_band"]):
        print(_line(k, res["by_band"][k]))
    print("\n je Liga:")
    for k in sorted(res["by_league"]):
        print(_line(f"{k} {LEAGUE_NAME.get(k,'')}"[:16], res["by_league"][k]))

    # ── Out-of-Sample: Gate auf 3 alten Saisons waehlen, auf 24/25 testen ──
    train = [f for f in files if season_of(f) in OOS_TRAIN_SEASONS]
    test = [f for f in files if season_of(f) == OOS_TEST_SEASON]
    g, tr_roi = best_gate(train)
    te = evaluate(test, g)["overall"]
    print(f"\n=== OUT-OF-SAMPLE ===")
    print(f" Train {OOS_TRAIN_SEASONS}: bestes Gate = {int(g*100)}pp (Train-ROI {tr_roi:+.2f}%)")
    print(_line(f"Test {OOS_TEST_SEASON}", te))

    # ── Schritt 2: Zustands-Bestaetigung (leakage-free) ──
    zones = (f"<{int(MOVE_EDGES[0]*100)}pp",
             f"{int(MOVE_EDGES[0]*100)}-{int(MOVE_EDGES[1]*100)}pp",
             f"{int(MOVE_EDGES[1]*100)}pp+")

    def show_state(title, fset):
        st = evaluate_state(fset, GATE_DEFAULT)
        print(f"\n {title}")
        for s in ("bestaetigt", "widerspricht"):
            if s in st:
                print(_line(s.upper(), st[s]))
        for zone in zones:
            for s in ("bestaetigt", "widerspricht"):
                key = f"{s} | {zone}"
                if key in st:
                    print(_line(key, st[key]))

    print(f"\n=== SCHRITT 2: ZUSTANDS-BESTAETIGUNG (These: rettet sub-5pp?) ===")
    show_state("in-sample (alle Saisons):", files)
    show_state("out-of-sample (nur 24/25):", test)

    print("\n(ROI = idealisierter Opening-Einstieg = OBERGRENZE, nicht live erzielbar.)")


if __name__ == "__main__":
    main()
