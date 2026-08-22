# tests/test_dashboard_pulse.py — 07.08.2026 (Lucas): der Übersicht-Puls trägt jetzt drei Flächen.
# Cards (CLV/Treffer aus den Ledgern, bestehend) + Betfair-Signal-Bilanz (Treffer/ROI, kein CLV)
# + Poly „Heute wetten"-Paper-Trade (Treffer/ROI/CLV/offen). Die zwei neuen Verdichter testbar.
import importlib
bp = importlib.import_module("build_dashboard_pulse")


def test_betfair_pulse_aus_global():
    rec = {"global": {"n": 744, "wins": 382, "hitRate": 0.5134, "roi": -0.0211}}
    out = bp._betfair_pulse(rec)
    assert out == {"n": 744, "hitPct": 51.3, "roiPct": -2.1}


def test_betfair_pulse_leer_ist_none():
    assert bp._betfair_pulse({}) is None
    assert bp._betfair_pulse({"global": {"n": 0}}) is None


def test_poly_pulse_aus_agg_public():
    # 12.08.2026 (Lucas): der Puls zeigt die HART GEGATETEN Public-Kandidaten (agg.public),
    # openN zaehlt nur offene Plays mit public=True.
    track = {"agg": {"public": {"n": 40, "hit": 0.75, "roi": 0.026, "clvAvg": 0.03}},
             "open": {"a": {"public": True}, "b": {"public": True}, "c": {"public": False}}}
    out = bp._poly_pulse(track)
    assert out == {"n": 40, "hitPct": 75.0, "roiPct": 2.6, "clvAvg": 0.03, "openN": 2}


def test_poly_pulse_leer_ist_none():
    assert bp._poly_pulse({}) is None
    assert bp._poly_pulse({"agg": {"public": {"n": 0}}}) is None


def test_best_bucket_haelt_schwelle_und_waehlt_hoechsten_roi():
    buckets = {"7": {"n": 17, "roi": 0.05}, "8": {"n": 11, "roi": 0.107}, "9": {"n": 15, "roi": 0.20},
               "10": {"n": 2, "roi": 0.9}}   # n<8 -> ignoriert trotz 90% ROI
    out = bp._best_bucket(buckets)
    assert out == {"key": "9", "roiPct": 20.0, "n": 15}


def test_best_bucket_none_wenn_alles_negativ_oder_zu_klein():
    assert bp._best_bucket({"7": {"n": 17, "roi": -0.05}, "10": {"n": 2, "roi": 0.5}}) is None
    assert bp._best_bucket({}) is None


# 22.08.2026 (Lucas): Signal-Bilanz — pro-Signal Win% dafür/dagegen + Edge.
def _rec(res, sigs):
    return {"result": res, "resolvedAt": "2026-08-22T00:00:00Z", "clvPP": 0.0,
            "signals": [{"name": n, "score": s} for n, s in sigs]}

def test_signal_scoreboard_edge_und_seiten():
    recs = [
        _rec("WIN",  [("form_trend", 3.0), ("h2h_pattern", -2.0)]),
        _rec("WIN",  [("form_trend", 2.0), ("h2h_pattern", -1.0)]),
        _rec("LOSS", [("form_trend", -2.0), ("h2h_pattern", 1.5)]),
    ]
    b = bp._signal_scoreboard(recs)
    assert b["n"] == 3
    rows = {r["name"]: r for r in b["rows"]}
    ft = rows["form_trend"]
    assert ft["fire"] == 3 and ft["supp"] == 2 and ft["opp"] == 1
    assert ft["suppWinPct"] == 100 and ft["oppWinPct"] == 0 and ft["edge"] == 100

def test_signal_scoreboard_leer_ist_none():
    assert bp._signal_scoreboard([]) is None
    assert bp._signal_scoreboard([{"result": "VOID", "signals": []}]) is None
