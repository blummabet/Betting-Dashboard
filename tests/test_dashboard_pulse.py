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


# 03.09.2026 (Lucas-Checkup): `_best_bucket` bekommt keine fertigen Aggregate mehr, sondern die
# RENDITEN je Play — nur so laesst sich eine Untergrenze rechnen. Ein Maximum ueber ~10 Buckets
# ist selbst eine Auswahl; ohne Schranke stand in der Kopfzeile die gluecklichste Stufe.
# Die Aussage der beiden Tests bleibt, die Eingabe ist eine andere.
def test_best_bucket_haelt_schwelle_und_waehlt_hoechsten_roi():
    ok, knapp_drunter = bp.STRIP_MIN_N + 2, bp.STRIP_MIN_N - 1
    buckets = {"7": [0.05] * ok, "8": [0.107] * ok, "9": [0.20] * ok,
               "10": [0.9] * knapp_drunter}   # unter der Schwelle -> ignoriert trotz 90% ROI
    out = bp._best_bucket(buckets)
    assert out["key"] == "9" and out["roiPct"] == 20.0 and out["n"] == ok


def test_best_bucket_none_wenn_alles_negativ_oder_zu_klein():
    assert bp._best_bucket({"7": [-0.05] * (bp.STRIP_MIN_N + 2),
                            "10": [0.5] * (bp.STRIP_MIN_N - 1)}) is None
    assert bp._best_bucket({}) is None


def test_best_bucket_sagt_ob_das_ergebnis_traegt():
    """Neu am 03.09.: die Leiste stand ueber dem Register und behauptete mehr als es."""
    eng = bp._best_bucket({"7": [0.30, 0.32, 0.28] * 20})
    assert eng["belegt"] is True and eng["roiUgPct"] > 0
    duenn = bp._best_bucket({"7": [0.2] * (bp.STRIP_MIN_N + 2)})   # < UG_MIN_N
    assert duenn["belegt"] is False and duenn["roiUgPct"] is None


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


# ── NOBET-Bilanz (23.08.2026, Lucas): waren die Abstufungen richtig? Schatten-Win + CLV je Grund ──
def test_nobet_bucket_mapping():
    assert bp._nobet_bucket("Conviction 3/10 < 4 — zu dünn") == "Conviction zu dünn"
    assert bp._nobet_bucket("Edge weg — Linie gegen den Pick gelaufen (2.6→3.2)") == "Linie weggelaufen"
    assert bp._nobet_bucket("Engine-Netto -0.2pp negativ — Modell gegen den Pick") == "Engine gegen den Pick"
    assert bp._nobet_bucket("Quote zu kurz geworden (1.6→1.4) — kein Value mehr") == "Quote zu kurz geworden"
    assert bp._nobet_bucket("Kein Value mehr — Move ausgelaufen / Konsens konvergiert") == "Value ausgelaufen"
    assert bp._nobet_bucket(None) == "Sonstige"


def test_nobet_scoreboard_aggregates_shadow_and_clv(monkeypatch):
    fake = {"picks": {"K1": [
        {"verdict": "NOBET", "shadowResult": "WIN",  "nobetReason": "Conviction 3/10 < 4 — zu dünn", "clvPP": -5.0},
        {"verdict": "NOBET", "shadowResult": "LOSS", "nobetReason": "Conviction 2/10 < 4 — zu dünn", "clvPP": -3.0},
        {"verdict": "BET",   "shadowResult": "WIN",  "clvPP": 9.0},    # kein NOBET → ignoriert
        {"verdict": "NOBET", "shadowResult": None,   "clvPP": 2.0},    # kein shadow → ignoriert
    ]}}
    monkeypatch.setattr(bp, "_load", lambda name: fake if name == "liga-data.json" else {})
    b = bp._nobet_scoreboard(["liga-data.json"])
    assert b["n"] == 2 and b["wins"] == 1 and b["winPct"] == 50
    assert b["clvAvg"] == -4.0
    assert len(b["rows"]) == 1
    assert b["rows"][0]["reason"] == "Conviction zu dünn" and b["rows"][0]["n"] == 2 and b["rows"][0]["clvAvg"] == -4.0


def test_nobet_scoreboard_leer_ist_none(monkeypatch):
    monkeypatch.setattr(bp, "_load", lambda name: {})
    assert bp._nobet_scoreboard(["x.json"]) is None
