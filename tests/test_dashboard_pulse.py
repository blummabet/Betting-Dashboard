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


def test_poly_pulse_aus_agg_all():
    track = {"agg": {"all": {"n": 45, "hit": 0.6222, "roi": 0.0615, "clvAvg": 0.11}},
             "open": {"a": 1, "b": 2}}
    out = bp._poly_pulse(track)
    assert out == {"n": 45, "hitPct": 62.2, "roiPct": 6.2, "clvAvg": 0.11, "openN": 2}


def test_poly_pulse_leer_ist_none():
    assert bp._poly_pulse({}) is None
    assert bp._poly_pulse({"agg": {"all": {"n": 0}}}) is None


def test_best_bucket_haelt_schwelle_und_waehlt_hoechsten_roi():
    buckets = {"7": {"n": 17, "roi": 0.05}, "8": {"n": 11, "roi": 0.107}, "9": {"n": 15, "roi": 0.20},
               "10": {"n": 2, "roi": 0.9}}   # n<8 -> ignoriert trotz 90% ROI
    out = bp._best_bucket(buckets)
    assert out == {"key": "9", "roiPct": 20.0, "n": 15}


def test_best_bucket_none_wenn_alles_negativ_oder_zu_klein():
    assert bp._best_bucket({"7": {"n": 17, "roi": -0.05}, "10": {"n": 2, "roi": 0.5}}) is None
    assert bp._best_bucket({}) is None
