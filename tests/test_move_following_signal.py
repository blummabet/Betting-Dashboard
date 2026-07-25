#!/usr/bin/env python3
"""Tests fuer sharp_signals/move_following.py (25.07.2026).
Konstruiert Pick/Context wie im Live-Pfad (odds_history + xg_stats + form)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sharp_signals.move_following import MoveFollowingSignal

SIG = MoveFollowingSignal()


def _hist(open_odds, now_odds):
    """Zwei Pinnacle-Snaps (hw,dr,aw) -> odds_history."""
    return [
        {"bk": "pinnacle", "ts": "2026-08-01T08:00:00Z",
         "hw": open_odds[0], "dr": open_odds[1], "aw": open_odds[2]},
        {"bk": "pinnacle", "ts": "2026-08-03T12:00:00Z",
         "hw": now_odds[0], "dr": now_odds[1], "aw": now_odds[2]},
    ]


def _team(net_for, net_ag, last5):
    return net_for, net_ag, last5


def _ctx(open_odds, now_odds, home=None, away=None):
    c = {"home_id": "H", "away_id": "A", "odds_history": _hist(open_odds, now_odds),
         "xg_stats": {}, "form": {}}
    if home:
        c["xg_stats"]["H"] = {"xgSimForAvg": home[0], "xgSimAgainstAvg": home[1], "games": 6}
        c["form"]["H"] = {"last5": home[2], "avgScored": home[0], "avgConceded": home[1], "games": 6}
    if away:
        c["xg_stats"]["A"] = {"xgSimForAvg": away[0], "xgSimAgainstAvg": away[1], "games": 6}
        c["form"]["A"] = {"last5": away[2], "avgScored": away[0], "avgConceded": away[1], "games": 6}
    return c


PICK_HOME = {"market": "Heimsieg"}

# Move-Groessen (berechnet aus den Snaps): gross ~+9.7pp, mittel ~+4pp, schwach ~+2.4pp
OPEN = [2.50, 3.50, 3.20]
NOW_STRONG = [2.10, 3.60, 3.80]
NOW_MID = [2.15, 3.50, 3.30]
NOW_WEAK = [2.30, 3.50, 3.30]

STRONG_HOME, WEAK_AWAY = (1.7, 1.0, ["W", "W", "D", "W", "L"]), (1.0, 1.6, ["L", "L", "D", "L", "W"])


def test_strong_move_positive_ignores_state():
    # starker Move + WIDERSPRECHENDER Zustand -> trotzdem positiv (Zustand egal)
    r = SIG.evaluate(PICK_HOME, _ctx(OPEN, NOW_STRONG, home=WEAK_AWAY, away=STRONG_HOME))
    assert r is not None and r.score > 0 and r.metadata["bucket"] == "strong"
    assert r.metadata["move_pp"] >= 5.0


def test_mid_move_positive():
    r = SIG.evaluate(PICK_HOME, _ctx(OPEN, NOW_MID))
    assert r is not None and r.score > 0 and r.metadata["bucket"] == "mid"
    assert 3.0 <= r.metadata["move_pp"] < 5.0


def test_weak_move_confirm_positive():
    r = SIG.evaluate(PICK_HOME, _ctx(OPEN, NOW_WEAK, home=STRONG_HOME, away=WEAK_AWAY))
    assert r is not None and r.score > 0 and r.metadata["bucket"] == "weak_confirm"
    assert 2.0 <= r.metadata["move_pp"] < 3.0


def test_weak_move_contradict_negative():
    r = SIG.evaluate(PICK_HOME, _ctx(OPEN, NOW_WEAK, home=WEAK_AWAY, away=STRONG_HOME))
    assert r is not None and r.score < 0 and r.metadata["bucket"] == "weak_contradict"


def test_weak_move_unknown_state_none():
    # schwacher Move ohne xG/Form -> nicht bewertbar
    assert SIG.evaluate(PICK_HOME, _ctx(OPEN, NOW_WEAK)) is None


def test_no_move_returns_none():
    assert SIG.evaluate(PICK_HOME, _ctx(OPEN, OPEN, home=STRONG_HOME, away=WEAK_AWAY)) is None


def test_irrelevant_market_none():
    assert SIG.evaluate({"market": "Beide treffen — Ja"}, _ctx(OPEN, NOW_STRONG)) is None


def test_too_few_snaps_none():
    c = _ctx(OPEN, NOW_STRONG)
    c["odds_history"] = c["odds_history"][:1]
    assert SIG.evaluate(PICK_HOME, c) is None


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    print("ALLE GRUEN" if not fails else f"{fails} FEHLER")
    sys.exit(1 if fails else 0)
