#!/usr/bin/env python3
"""test_betfair_draw_tracker.py -- Draw-Geld-Tracker (07.08.2026, Lucas).
Pre-Match-Draw-Anteil + In-Play-Zufluesse waehrend Gleichstand + Settle (finished/vanish) + Aggregat."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import betfair_draw_tracker as D

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
HOME, AWAY = "Alpha", "Beta"


def _mo(hw_vol, dr_vol, aw_vol, dr_odd=3.4):
    return {"vol": hw_vol + dr_vol + aw_vol,
            "runners": [{"name": HOME, "odd": 2.4, "vol": hw_vol},
                        {"name": "The Draw", "odd": dr_odd, "vol": dr_vol},
                        {"name": AWAY, "odd": 3.0, "vol": aw_vol}]}


def _match(mid="1", li=None, hw=1000, dr=500, aw=1000, dr_odd=3.4, ko_h=3):
    return {"matchId": mid, "home": HOME, "away": AWAY, "league": "Testliga", "country": "XX",
            "kickoff": (NOW + timedelta(hours=ko_h)).isoformat(),
            "liveInfo": li or {}, "markets": {"Match Odds": _mo(hw, dr, aw, dr_odd)}}


def _live(mid="1", t=45, gv=(0, 0), finished=False, is_ht=False, hw=1000, dr=500, aw=1000, dr_odd=3.4):
    li = {"time": t, "is_ht": is_ht, "goal_v1": gv[0], "goal_v2": gv[1], "finished": finished}
    return _match(mid, li=li, hw=hw, dr=dr, aw=aw, dr_odd=dr_odd)


def test_draw_metrics():
    dm = D.draw_metrics(_match(dr=1500, hw=1000, aw=500))   # Draw fuehrt: 1500/3000
    assert dm["drawShare"] == 0.5 and dm["drawLeader"] is True
    dm2 = D.draw_metrics(_match(dr=500, hw=1500, aw=500))   # 500/2500
    assert dm2["drawLeader"] is False and dm2["drawShare"] == 0.2


def test_prematch_schluss_und_zufluss():
    st = D.capture({"matches": [_match(dr=500)]}, {}, now=NOW)
    # zweiter Pre-Match-Lauf: +800 aufs X -> inflow akkumuliert, share/odd = Schlussstand
    st = D.capture({"matches": [_match(dr=1300)]}, st, now=NOW + timedelta(minutes=15))
    pre = st["pending"]["1"]["pre"]
    assert abs(pre["inflowEur"] - 800.0) < 1e-6
    assert pre["drawVol"] == 1300


def test_inplay_zufluss_nur_bei_gleichstand():
    st = D.capture({"matches": [_match(dr=500)]}, {}, now=NOW)                       # pre-match
    st = D.capture({"matches": [_live(t=30, gv=(0, 0), dr=500)]}, st, now=NOW + timedelta(hours=3))
    st = D.capture({"matches": [_live(t=44, gv=(0, 0), dr=2500)]}, st, now=NOW + timedelta(hours=3, minutes=15))  # +2000 bei 0:0
    st = D.capture({"matches": [_live(t=70, gv=(1, 0), dr=3000)]}, st, now=NOW + timedelta(hours=4))              # +500, aber NICHT level
    ip = st["pending"]["1"]["inplay"]
    assert abs(ip["levelDrawInflowEur"] - 2000.0) < 1e-6      # nur die 2000 bei 0:0 zaehlen
    assert abs(ip["drawInflowEur"] - 2500.0) < 1e-6           # gesamter In-Play-Zufluss
    assert ip["everLevel"] is True


def test_settle_finished_markiert_draw_came():
    st = D.capture({"matches": [_match(dr=1500, hw=1000, aw=500)]}, {}, now=NOW)     # Draw-Fuehrer
    fin = _live(t=90, gv=(1, 1), finished=True)
    st, res = D.settle({"matches": [fin]}, st, [], now=NOW + timedelta(hours=5))
    assert "1" not in st["pending"]
    assert res[0]["drawCame"] is True and res[0]["ft"] == [1, 1] and res[0]["via"] == "finished"
    assert res[0]["drawLeader"] is True


def test_settle_kein_draw():
    st = D.capture({"matches": [_match(dr=1500, hw=1000, aw=500)]}, {}, now=NOW)
    st, res = D.settle({"matches": [_live(t=90, gv=(2, 1), finished=True)]}, st, [], now=NOW + timedelta(hours=5))
    assert res[0]["drawCame"] is False


def test_vanish_settle_spaet_und_weg():
    st = D.capture({"matches": [_match(dr=1500, hw=1000, aw=500)]}, {}, now=NOW)
    seen = NOW + timedelta(hours=4)
    st = D.capture({"matches": [_live(t=88, gv=(1, 1), dr=1500)]}, st, now=seen)     # zuletzt 88', 1:1
    st, res = D.settle({"matches": []}, st, [], now=seen + timedelta(minutes=30))    # weg -> vanish
    assert res and res[0]["via"] == "vanish" and res[0]["drawCame"] is True


def test_vanish_wartet_bei_frischem_ausfall():
    st = D.capture({"matches": [_match(dr=1500, hw=1000, aw=500)]}, {}, now=NOW)
    seen = NOW + timedelta(hours=4)
    st = D.capture({"matches": [_live(t=88, gv=(1, 1), dr=1500)]}, st, now=seen)
    st, res = D.settle({"matches": []}, st, [], now=seen + timedelta(minutes=10))    # zu frisch
    assert "1" in st["pending"] and res == []


def test_aggregate_notable_und_basisrate():
    def row(share, came, odd=3.4, leader=False, level_money=0.0, inflow=0.0):
        return {"drawShare": share, "drawCame": came, "drawOdd": odd, "drawLeader": leader,
                "preInflowEur": inflow, "levelDrawInflowEur": level_money, "everLevel": level_money > 0,
                "firstLevelOdd": None, "minDrawOddInplay": None}
    results = [
        row(0.20, True), row(0.20, False), row(0.20, False),     # niedriger Anteil (nicht notable)
        row(0.45, True, leader=True), row(0.45, False, leader=True),   # hoher Anteil + Fuehrer (notable)
        row(0.35, True),                                         # notable per share
    ]
    rec = D.aggregate(results, now=NOW)
    assert rec["all"]["n"] == 6
    # notable = share>=0.33 ODER leader -> die letzten drei
    assert rec["notable"]["n"] == 3 and rec["notable"]["drawCame"] == 2
    assert rec["drawLeader"]["n"] == 2
    assert rec["byShareBand"]["share_ge_40"]["n"] == 2


def test_aggregate_inplay_level_split():
    def row(came, level_money):
        return {"drawShare": 0.5, "drawCame": came, "drawOdd": 3.0, "drawLeader": True,
                "preInflowEur": 0.0, "levelDrawInflowEur": level_money, "everLevel": True,
                "firstLevelOdd": 3.0, "minDrawOddInplay": 3.0}
    results = [row(False, 5000), row(False, 4000), row(True, 100), row(True, 200)]
    rec = D.aggregate(results, now=NOW)
    # viel In-Play-Draw-Geld bei Gleichstand -> hier kam X NIE (Trade-Out-Muster)
    assert rec["inplayLevelMoneyHigh"]["n"] == 2 and rec["inplayLevelMoneyHigh"]["drawCame"] == 0
    assert rec["inplayLevelMoneyLow"]["n"] == 2 and rec["inplayLevelMoneyLow"]["drawCame"] == 2


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f(); print("ok", f.__name__)
    print("\n%d tests passed" % len(fns))
