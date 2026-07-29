#!/usr/bin/env python3
"""test_betfair_track.py — reiner Kern von betfair_track_record (29.07.2026, Lucas)."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import betfair_track_record as T

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
HOME, AWAY = "Barcelona SC", "Emelec"   # Ecuador-Beispiel


def _mk(runners):
    return {"vol": sum(v for _, _, v in runners),
            "runners": [{"name": n, "odd": o, "vol": v} for n, o, v in runners]}


def _prematch(mid=1, ko_h=3):
    return {"matchId": mid, "home": HOME, "away": AWAY, "league": "Ecuador Serie A",
            "country": "EC", "kickoff": (NOW + timedelta(hours=ko_h)).isoformat(), "liveInfo": {},
            "markets": {
                "Match Odds": _mk([(HOME, 2.0, 8000), ("The Draw", 3.5, 1000), (AWAY, 4.0, 1000)]),
                "Over/Under 2.5 Goals": _mk([("Over 2.5 Goals", 1.9, 3000), ("Under 2.5 Goals", 2.0, 1000)]),
                "Half Time": _mk([(HOME, 2.4, 5000), ("The Draw", 2.1, 3000), (AWAY, 4.5, 2000)]),
            }}


def _live(mid=1, t=45, is_ht=True, gv=(1, 0), finished=False):
    m = _prematch(mid)
    m["liveInfo"] = {"time": t, "is_ht": is_ht, "goal_v1": gv[0], "goal_v2": gv[1], "finished": finished}
    return m


def _finished(mid=1, gv=(2, 1)):
    return _live(mid, t=90, is_ht=False, gv=gv, finished=True)


HIST = {"1": [{"mkv": {"Match Odds": 6000}}, {"mkv": {"Match Odds": 10000}}]}  # +4000 → Zufluss


def test_fav_token():
    assert T.fav_token("Match Odds", HOME, HOME, AWAY) == "H"
    assert T.fav_token("Match Odds", "The Draw", HOME, AWAY) == "D"
    assert T.fav_token("Half Time", AWAY, HOME, AWAY) == "A"
    assert T.fav_token("Over/Under 2.5 Goals", "Over 2.5 Goals", HOME, AWAY) == "OVER"
    assert T.fav_token("Both teams to Score?", "Yes", HOME, AWAY) == "YES"
    assert T.fav_token("First Half Goals 0.5", "Under 0.5 Goals", HOME, AWAY) == "UNDER"


def test_winning_token():
    assert T.winning_token("Match Odds", [2, 1], None) == "H"
    assert T.winning_token("Match Odds", [1, 1], None) == "D"
    assert T.winning_token("Match Odds", [0, 2], None) == "A"
    assert T.winning_token("Over/Under 2.5 Goals", [2, 1], None) == "OVER"   # 3 > 2.5
    assert T.winning_token("Over/Under 2.5 Goals", [1, 1], None) == "UNDER"  # 2 < 2.5
    assert T.winning_token("Both teams to Score?", [2, 1], None) == "YES"
    assert T.winning_token("Both teams to Score?", [2, 0], None) == "NO"
    assert T.winning_token("Half Time", None, [1, 0]) == "H"
    assert T.winning_token("First Half Goals 0.5", None, [0, 0]) == "UNDER"
    assert T.winning_token("First Half Goals 1.5", None, [1, 1]) == "OVER"   # 2 > 1.5
    # HT-Markt ohne HT-Stand → nicht abrechenbar
    assert T.winning_token("Half Time", [2, 1], None) is None


def test_grade():
    assert T.grade("H", "Match Odds", [2, 1], None) == (True, True)
    assert T.grade("A", "Match Odds", [2, 1], None) == (False, True)
    assert T.grade("H", "Half Time", [2, 1], None) == (False, False)   # kein HT-Stand → nicht gewertet


def test_capture_prematch_signale_mit_flags():
    st = T.capture({"matches": [_prematch()]}, HIST, {}, now=NOW)
    sig = st["pending"]["1"]["signals"]
    assert sig["Match Odds"]["fav"] == "H"
    assert sig["Match Odds"]["conc"] is True                 # 8000/10000 = 0.8 ≥ 0.65
    assert sig["Match Odds"]["inflow"] is True               # +4000 € ≥ 2000
    assert sig["Over/Under 2.5 Goals"]["fav"] == "OVER" and sig["Over/Under 2.5 Goals"]["conc"] is True
    assert sig["Over/Under 2.5 Goals"]["inflow"] is False    # kein mkv-Delta
    assert sig["Half Time"]["conc"] is False                 # 5000/10000 = 0.5 < 0.65


def test_capture_live_faengt_ht_stand_und_friert_signal():
    st = T.capture({"matches": [_prematch()]}, HIST, {}, now=NOW)
    frozen = dict(st["pending"]["1"]["signals"]["Match Odds"])
    # jetzt live nahe HT — Signale dürfen sich NICHT ändern, aber HT-Stand wird eingefangen
    st = T.capture({"matches": [_live(gv=(1, 0))]}, HIST, st, now=NOW + timedelta(hours=4))
    assert st["pending"]["1"]["htScore"] == [1, 0]
    assert st["pending"]["1"]["signals"]["Match Odds"] == frozen


def test_settle_rechnet_ab_und_entfernt_pending():
    st = T.capture({"matches": [_prematch()]}, HIST, {}, now=NOW)
    st = T.capture({"matches": [_live(gv=(1, 0))]}, HIST, st, now=NOW + timedelta(hours=4))
    st, res = T.settle({"matches": [_finished(gv=(2, 1))]}, st, [], now=NOW + timedelta(hours=6))
    assert "1" not in st["pending"]                          # settled → weg
    mkts = {r["market"]: r for r in res}
    assert mkts["Match Odds"]["win"] is True                 # 2:1 → Heim
    assert mkts["Over/Under 2.5 Goals"]["win"] is True       # 3 Tore → Over
    assert mkts["Half Time"]["win"] is True                  # HT 1:0 → Heim
    assert all(r["league"] == "Ecuador Serie A" for r in res)


def test_settle_ht_ohne_ht_stand_wird_nicht_gewertet():
    st = T.capture({"matches": [_prematch()]}, HIST, {}, now=NOW)
    # direkt finished, HT nie eingefangen → HT-Märkte fallen raus, FT-Märkte zählen
    st, res = T.settle({"matches": [_finished(gv=(2, 1))]}, st, [], now=NOW + timedelta(hours=6))
    markets = {r["market"] for r in res}
    assert "Match Odds" in markets and "Over/Under 2.5 Goals" in markets
    assert "Half Time" not in markets                        # ungraded ohne HT-Stand


def test_aggregate_trefferquote_und_roi_split():
    results = [
        {"league": "Ecuador Serie A", "market": "Half Time", "home": HOME, "away": AWAY,
         "fav": "H", "odd": 2.4, "conc": True, "inflow": True, "win": True},
        {"league": "Ecuador Serie A", "market": "Half Time", "home": "Aucas", "away": "LDU",
         "fav": "H", "odd": 3.0, "conc": True, "inflow": False, "win": False},
    ]
    rec = T.aggregate(results, now=NOW)
    lm = rec["byLeagueMarket"]["Ecuador Serie A|Half Time"]
    assert lm["n"] == 2 and lm["wins"] == 1 and lm["hitRate"] == 0.5
    # ROI: (2.4-1) - 1 = 0.4 auf 2 = 0.2
    assert abs(lm["roi"] - 0.2) < 1e-9
    # nur Konzentration: beide conc → n=2; nur Zufluss: nur der erste → n=1, 1 win
    assert lm["nConc"] == 2 and lm["nInflow"] == 1 and lm["hitRateInflow"] == 1.0
    # Team-Ebene: Barcelona SC × Half Time
    assert rec["byTeamMarket"]["Barcelona SC|Half Time"]["n"] == 1


def test_voller_flow_ecuador_ht():
    """Ende-zu-Ende: vor Anpfiff → live HT → finished → aggregiert."""
    st, res = {}, []
    st = T.capture({"matches": [_prematch()]}, HIST, st, now=NOW)
    st = T.capture({"matches": [_live(gv=(1, 0))]}, HIST, st, now=NOW + timedelta(hours=4))
    st, res = T.settle({"matches": [_finished(gv=(2, 1))]}, st, res, now=NOW + timedelta(hours=6))
    rec = T.aggregate(res, now=NOW + timedelta(hours=6))
    ht = rec["byLeagueMarket"]["Ecuador Serie A|Half Time"]
    assert ht["n"] == 1 and ht["hitRate"] == 1.0            # HT-Sieg-Signal ging auf


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f(); print("ok", f.__name__)
    print("\n%d tests passed" % len(fns))
