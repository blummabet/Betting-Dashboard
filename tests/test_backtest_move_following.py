#!/usr/bin/env python3
"""Tests fuer backtest_move_following.py — reine Logik + kleiner End-to-End.
25.07.2026: Fundament fuer das historische Move-/Analog-Signal (Top-5-CSVs)."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest_move_following as B


def test_devig_sums_to_one_and_orders():
    p = B.devig(2.0, 4.0, 4.0)
    assert p is not None
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] and p[0] > p[2]   # kurze Quote = hoehere Wkt


def test_devig_bad_input_is_none():
    assert B.devig(None, 3, 3) is None
    assert B.devig(0, 3, 3) is None
    assert B.devig("x", 3, 3) is None


def test_move_pick_respects_gate():
    op = (0.40, 0.30, 0.30)
    cp = (0.45, 0.28, 0.27)              # Heim +5pp
    pick = B.move_pick(op, cp, 0.02)
    assert pick is not None and pick[0] == 0 and abs(pick[1] - 0.05) < 1e-9
    assert B.move_pick(op, cp, 0.06) is None   # Gate zu hoch -> kein Bet


def test_move_pick_picks_largest_riser():
    op = (0.50, 0.25, 0.25)
    cp = (0.46, 0.24, 0.30)              # Auswaerts steigt am staerksten (+5pp)
    pick = B.move_pick(op, cp, 0.02)
    assert pick is not None and pick[0] == 2


def test_settle_win_and_loss():
    won, pnl = B.settle(0, "H", [2.5, 3.0, 3.0])
    assert won and abs(pnl - 1.5) < 1e-9
    won, pnl = B.settle(0, "A", [2.5, 3.0, 3.0])
    assert (not won) and pnl == -1.0


def test_season_and_league_mapping():
    assert B.season_of("E0_2122.csv") == "2021/22"
    assert B.season_of("E0_2223.csv") == "2022/23"
    assert B.season_of("E0.csv") == "2023/24"
    assert B.season_of("E0 (1).csv") == "2024/25"
    assert B.league_of("SP1_2223.csv") == "SP1"
    assert B.league_of("E0.csv") == "E0"


def test_move_bucket_and_odds_band():
    assert B._move_bucket(0.02) == "<3pp"
    assert B._move_bucket(0.04) == "3-5pp"
    assert B._move_bucket(0.06) == "5pp+"
    assert B._odds_band(1.8) == "fav<2.0"
    assert B._odds_band(2.9) == "mid2-3.5"
    assert B._odds_band(4.5) == "dog>3.5"


def test_evaluate_end_to_end(tmp_path):
    """Zwei Partien, beide klarer Heim-Move; eine gewonnen (H), eine verloren (A)."""
    p = tmp_path / "E0.csv"
    with open(p, "w", encoding="latin-1", newline="") as f:
        w = csv.writer(f)
        w.writerow(["FTR", "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA"])
        w.writerow(["H", "2.50", "3.40", "3.00", "2.10", "3.60", "3.80"])
        w.writerow(["A", "2.50", "3.40", "3.00", "2.10", "3.60", "3.80"])
    res = B.evaluate([str(p)], gate=0.02)
    assert res["overall"].n == 2          # beide gewettet (Heim-Move gross genug)
    assert res["overall"].win == 1        # eine H (win), eine A (loss)
    # PnL = (2.50-1) - 1 = +0.50
    assert abs(res["overall"].pnl - 0.5) < 1e-9


def test_parse_date_formats():
    assert B.parse_date("22/08/2024") is not None
    assert B.parse_date("22/08/24") is not None
    assert B.parse_date("bloedsinn") is None
    assert B.parse_date("") is None


def test_state_edge_direction():
    strong, weak = (2.0, 3.0), (1.0, 1.0)
    assert B.state_edge(0, strong, weak) > 0      # Heim stark, Heim-Move -> bestaetigt
    assert B.state_edge(2, strong, weak) < 0      # Auswaerts schwach, Auswaerts-Move -> widerspricht
    assert B.state_edge(1, strong, weak) is None  # Draw-Move: kein Zustands-Split
    assert B.state_edge(0, None, weak) is None    # fehlender Zustand


def test_rolling_state_is_leakage_free():
    """AAA spielt 4x daheim; der Zustand vor Spiel 4 darf NUR aus Spiel 1-3 stammen."""
    def row(date, hg, ag, hst, ast):
        return {"Date": date, "HomeTeam": "AAA", "AwayTeam": "BBB",
                "FTHG": str(hg), "FTAG": str(ag), "HST": str(hst), "AST": str(ast),
                "FTR": "H" if hg > ag else "A" if ag > hg else "D"}
    rows = [row("01/08/2024", 2, 0, 5, 2), row("08/08/2024", 0, 1, 3, 4),
            row("15/08/2024", 1, 1, 4, 4), row("22/08/2024", 3, 0, 7, 1)]
    out = list(B._rolling_state(rows))
    # Spiel 1: kein Team hat Historie -> beide None
    assert out[0][1] is None and out[0][2] is None
    # Spiel 4: AAA hat 3 Vorspiele -> Zustand aus GENAU diesen 3 (nicht Spiel 4 selbst)
    sH = out[3][1]
    assert sH is not None
    assert abs(sH[0] - (3 + 0 + 1) / 3) < 1e-6            # Form-Schnitt aus Spiel 1-3
    assert abs(sH[1] - ((5 + 3 + 4) / 3 - (2 + 4 + 4) / 3)) < 1e-6   # SOT-Netto aus Spiel 1-3


def test_evaluate_state_end_to_end(tmp_path):
    """Vier Duelle AAA(H) vs BBB(A); AAA klar staerker; Spiel 4 = Heim-Move + Heim-Sieg
    -> genau EIN 'bestaetigt'-Bet (Spiel 1-3 haben keinen definierten Zustand)."""
    p = tmp_path / "E0.csv"
    cols = ["Date", "HomeTeam", "AwayTeam", "FTR", "FTHG", "FTAG", "HST", "AST",
            "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA"]
    with open(p, "w", encoding="latin-1", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        # Spiel 1-3: AAA gewinnt, KEIN Move (open == close) -> werden sowieso uebersprungen
        for d in ("01/08/2024", "08/08/2024", "15/08/2024"):
            w.writerow([d, "AAA", "BBB", "H", 2, 0, 6, 2,
                        "2.00", "3.50", "4.00", "2.00", "3.50", "4.00"])
        # Spiel 4: klarer Heim-Move (open 2.60 -> close 2.10) + Heim-Sieg
        w.writerow(["22/08/2024", "AAA", "BBB", "H", 1, 0, 6, 2,
                    "2.60", "3.40", "2.80", "2.10", "3.60", "3.80"])
    st = B.evaluate_state([str(p)], gate=0.02)
    assert st["bestaetigt"].n == 1 and st["bestaetigt"].win == 1
    assert "widerspricht" not in st or st["widerspricht"].n == 0


if __name__ == "__main__":   # ohne pytest lauffaehig (Device-VM hat kein pytest)
    import tempfile
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL {name}: {e}")
    print("ALLE GRUEN" if not fails else f"{fails} FEHLER")
    sys.exit(1 if fails else 0)
