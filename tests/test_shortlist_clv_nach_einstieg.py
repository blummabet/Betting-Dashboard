"""29.09.2026 (Lucas: „mach 1") — der CLV von „Heute spielenswert" mass Preise von VOR der Wette.

Auf 1.317 abgerechneten Plays: 43 % CLV exakt 0,00, 117 Live-Plays gegen den Vor-Anpfiff-Preis
gemessen, und die Plays mit angeblich −15 pp CLV gewannen +5,2 %. Ursache:
`close_ref = lastPrice or entry` — eine Referenz ohne Zeitbedingung, „nicht gemessen" als 0,0.
Nach dem Fix trennt der CLV auf echten Daten: >+1 pp ROI +16,6 %, <−1 pp ROI −7,7 %.
"""
import copy
from datetime import datetime, timedelta, timezone

import poly_shortlist_track as T
import poly_data_integrity as PI
import stoerungsmeldung as SM

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
KEY = "atp-a-b-2026-09-20"


def _iso(dt):
    return dt.isoformat()


def _emit(price=0.60, htk=2.0):
    return {"plays": [{"key": KEY, "side": "A", "price": price, "verdict": "BET", "conv": 6,
                       "league": "TENNIS", "cat": "Tennis", "htk": htk, "signals": ["money"]}]}


def _close(price, cap, htk=0.5):
    return {KEY: {"prices": {"A": price, "B": round(1 - price, 3)}, "capturedAt": _iso(cap),
                  "hoursToKickoff": htk, "league": "TENNIS"}}


RES = {KEY: {"winner": "A", "ts": "2026-09-20T18:00:00+00:00"}}


def _lauf(close, pfade, emit_htk=2.0, close_zwischen=None):
    """Einstieg bei T0, ein Zwischenlauf, dann Abrechnung."""
    tr = T.update_track({}, _emit(htk=emit_htk), close_zwischen or {}, {}, now=T0, pfade=pfade)
    tr = T.update_track(tr, {"plays": []}, close, {}, now=T0 + timedelta(hours=1, minutes=40), pfade=pfade)
    tr = T.update_track(tr, {"plays": []}, close, RES, now=T0 + timedelta(hours=6), pfade=pfade)
    assert tr["settled"], "nicht abgerechnet"
    return tr["settled"][-1], tr


def test_schluss_nach_einstieg_wird_gemessen():
    row, _ = _lauf(_close(0.65, T0 + timedelta(hours=1, minutes=30)), {})
    assert row["clvPP"] == 5.0 and row["closeQuelle"] == "close"
    assert row["closeRefTs"] > row["firstTs"]


def test_schluss_vor_einstieg_ist_kein_clv():
    """Gegentest: der alte Code rechnete hier (0.55-0.60)*100 = −5 aus einem Preis von vor der Wette."""
    row, _ = _lauf(_close(0.55, T0 - timedelta(minutes=10)), {})
    assert row["clvPP"] is None
    assert row["clvGrund"] == "schluss_vor_einstieg"


def test_ohne_schluss_ist_clv_none_nicht_null():
    """Gegentest: der alte Code schrieb 0,0 (lastPrice = Einstieg)."""
    row, _ = _lauf({}, {})
    assert row["clvPP"] is None and row["closePrice"] is None
    assert row["clvGrund"] == "kein_schluss_nach_einstieg"


def test_live_einstieg_hat_keinen_clv():
    row, _ = _lauf(_close(0.70, T0 + timedelta(hours=1)), {}, emit_htk=-0.3)
    assert row["clvPP"] is None and row["clvGrund"] == "live_eingestiegen"


def test_preispfad_springt_ein_wenn_freeze_vor_einstieg_lag():
    pfade = {KEY: {"points": [
        {"ts": _iso(T0 - timedelta(minutes=30)), "htk": 2.5, "p": {"A": 0.50}},
        {"ts": _iso(T0 + timedelta(minutes=50)), "htk": 1.2, "p": {"A": 0.63}},
        {"ts": _iso(T0 + timedelta(hours=3)), "htk": -1.0, "p": {"A": 0.95}},   # nach Anpfiff: zaehlt nicht
    ]}}
    row, _ = _lauf(_close(0.55, T0 - timedelta(minutes=10)), pfade)
    assert row["closeQuelle"] == "pfad" and row["clvPP"] == 3.0


def test_der_spaetere_vor_anpfiff_punkt_gewinnt():
    e = {"side": "A", "firstTs": _iso(T0), "htkAtEntry": 3.0}
    close = {"prices": {"A": 0.62}, "capturedAt": _iso(T0 + timedelta(hours=2)), "hoursToKickoff": 0.8}
    pfad = {"points": [{"ts": _iso(T0 + timedelta(hours=2, minutes=30)), "htk": 0.3, "p": {"A": 0.64}}]}
    assert T.schluss_referenz(e, close, pfad)[0] == 0.64
    assert T.schluss_referenz(e, close, None)[0] == 0.62


def test_altzeilen_werden_einmal_nachgetragen_und_bleiben_stehen():
    alt = {"key": KEY, "side": "A", "entryPrice": 0.6, "result": "win", "pnl": 6.6, "stake": 10,
           "clvPP": 0.0, "closePrice": 0.6, "firstTs": _iso(T0), "htkAtEntry": -0.5}
    tr = T.update_track({"settled": [dict(alt)]}, {"plays": []}, {}, {}, now=T0 + timedelta(days=1), pfade={})
    r = tr["settled"][0]
    assert r["clvPP"] is None and r["clvPPalt"] == 0.0 and r["clvGrund"] == "live_eingestiegen"
    assert tr["clvNachgetragen"] == 1
    tr2 = T.update_track(copy.deepcopy(tr), {"plays": []}, {}, {}, now=T0 + timedelta(days=2), pfade={})
    assert tr2["clvNachgetragen"] == 0 and tr2["settled"][0] == r


def test_durchschnitt_zaehlt_nur_gemessene():
    rows = [{"result": "win", "pnl": 5, "stake": 10, "clvPP": 2.0},
            {"result": "loss", "pnl": -10, "stake": 10, "clvPP": None}]
    a = T._agg_one(rows)
    assert a["clvAvg"] == 2.0 and a["clvN"] == 1          # alt: (2+0)/2 = 1.0


def test_guard_faellt_auf_altem_muster_und_ist_eingestuft():
    schlecht = {"settled": [{"key": KEY, "side": "A", "result": "win", "clvPP": 0.0,
                             "firstTs": _iso(T0)}]}
    assert not PI.check_shortlist_clv_nach_einstieg(PI.PolyCtx(shortlist=schlecht))["ok"]
    vor = {"settled": [{"key": KEY, "side": "A", "result": "win", "clvPP": 1.0, "closeQuelle": "close",
                        "firstTs": _iso(T0), "closeRefTs": _iso(T0 - timedelta(minutes=5))}]}
    assert not PI.check_shortlist_clv_nach_einstieg(PI.PolyCtx(shortlist=vor))["ok"]
    row, tr = _lauf(_close(0.65, T0 + timedelta(hours=1, minutes=30)), {})
    assert PI.check_shortlist_clv_nach_einstieg(PI.PolyCtx(shortlist=tr))["ok"]
    assert "check_shortlist_clv_nach_einstieg" in [f.__name__ for f in PI.POLY_CHECKS]
    assert "shortlist_clv_nach_einstieg" in SM.GEPRUEFT_KEIN_GELD
