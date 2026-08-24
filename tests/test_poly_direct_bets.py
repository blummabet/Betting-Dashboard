# tests/test_poly_direct_bets.py — 24.08.2026 (Lucas): direkt aus dem „Heute"-Tab gesetzte Wetten
# haben KEIN Fixture (Tennis/E-Sport) und werden allein über den Poly-Slug abgerechnet. Hier hängt
# echtes Geld dran, also pinnen diese Tests die Abrechnungs-Mathematik fest — identisch zum
# Papier-Depot (poly_shortlist_track), damit „Papier vs. echt" vergleichbar bleibt.
import importlib
from datetime import datetime, timezone, timedelta

D = importlib.import_module("poly_direct_bets")

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _fixture(bets, home="Alcaraz", away="Sinner", league="TENNIS"):
    return [{"home": home, "away": away, "league": league, "polyBets": bets}]


def _bet(**kw):
    b = {"market": "Alcaraz", "stake": 10, "polyPrice": 0.50, "orderId": "0xabc",
         "status": "placed", "placedAt": (NOW - timedelta(hours=2)).isoformat(),
         "polyKey": "atp-alcaraz-sinner-2026-08-24", "side": "Alcaraz",
         "sport": "Tennis", "conviction": 8}
    b.update(kw)
    return b


# ── Einsammeln ───────────────────────────────────────────────────────────────
def test_sammelt_nur_platzierte_bets_mit_polykey():
    hist = _fixture([
        _bet(),
        _bet(orderId="0xskip", status="skipped"),               # nicht platziert
        _bet(orderId="0xnokey", polyKey=None),                  # kein Slug -> nicht abrechenbar
        _bet(orderId="0xnoprice", polyPrice=None),              # kein Einstieg -> nicht abrechenbar
    ])
    got = D.collect_bets(hist)
    assert len(got) == 1 and got[0]["betId"] == "0xabc"
    assert got[0]["entryPrice"] == 0.5 and got[0]["sport"] == "Tennis"


def test_bet_ohne_orderid_bekommt_stabile_id():
    b = _bet(orderId=None)
    got = D.collect_bets(_fixture([b]))
    assert got[0]["betId"].startswith("atp-alcaraz-sinner-2026-08-24|Alcaraz|")


# ── Abrechnung ───────────────────────────────────────────────────────────────
def test_gewinn_zahlt_eins_pro_aktie():
    bets = D.collect_bets(_fixture([_bet()]))                   # $10 @ 0.50 = 20 Aktien
    out = D.settle(bets, {}, {"atp-alcaraz-sinner-2026-08-24": {"winner": "Alcaraz"}}, now=NOW)
    r = out["settled"][0]
    assert r["result"] == "win" and r["pnl"] == 10.0            # 20 Aktien × $1 − $10 Einsatz
    assert out["agg"]["n"] == 1 and out["agg"]["roi"] == 1.0


def test_verlust_kostet_den_einsatz():
    bets = D.collect_bets(_fixture([_bet()]))
    out = D.settle(bets, {}, {"atp-alcaraz-sinner-2026-08-24": {"winner": "Sinner"}}, now=NOW)
    r = out["settled"][0]
    assert r["result"] == "loss" and r["pnl"] == -10.0
    assert out["agg"]["hit"] == 0.0


def test_clv_kommt_aus_dem_close_feed():
    bets = D.collect_bets(_fixture([_bet()]))
    close = {"atp-alcaraz-sinner-2026-08-24": {"prices": {"Alcaraz": 0.62, "Sinner": 0.38}}}
    out = D.settle(bets, close, {"atp-alcaraz-sinner-2026-08-24": {"winner": "Alcaraz"}}, now=NOW)
    assert out["settled"][0]["clvPP"] == 12.0                   # (0.62 − 0.50) × 100
    assert out["agg"]["clvAvg"] == 12.0


def test_ohne_close_referenz_kein_erfundener_clv():
    # Lieber CLV 0 als eine Zahl, die es nicht gibt (Poly-Shortlist-Lehre vom 07.08.).
    bets = D.collect_bets(_fixture([_bet()]))
    out = D.settle(bets, {}, {"atp-alcaraz-sinner-2026-08-24": {"winner": "Alcaraz"}}, now=NOW)
    assert out["settled"][0]["clvPP"] == 0.0
    assert out["settled"][0]["closePrice"] is None


# ── Offene Bets ──────────────────────────────────────────────────────────────
def test_ohne_aufloesung_bleibt_der_bet_offen_mit_alter():
    bets = D.collect_bets(_fixture([_bet(placedAt=(NOW - timedelta(days=4)).isoformat())]))
    out = D.settle(bets, {}, {}, now=NOW)
    assert not out["settled"] and len(out["open"]) == 1
    assert out["open"][0]["ageDays"] == 4.0                     # Guard haengt genau daran


def test_offene_bets_verfallen_nie():
    # Anders als im Papier-Depot: hier steht echtes Geld, ein unaufloesbarer Bet MUSS sichtbar bleiben.
    bets = D.collect_bets(_fixture([_bet(placedAt=(NOW - timedelta(days=90)).isoformat())]))
    out = D.settle(bets, {}, {}, now=NOW)
    assert len(out["open"]) == 1


def test_einmal_abgerechnet_bleibt_abgerechnet():
    bets = D.collect_bets(_fixture([_bet()]))
    first = D.settle(bets, {}, {"atp-alcaraz-sinner-2026-08-24": {"winner": "Alcaraz"}}, now=NOW)
    # Auflösung faellt weg (rollierendes Ledger vergisst nach 14 Tagen) -> Ergebnis darf NICHT verschwinden
    again = D.settle(bets, {}, {}, now=NOW + timedelta(days=20), prev=first)
    assert len(again["settled"]) == 1 and again["settled"][0]["result"] == "win"
    assert not again["open"]


# ── Aufschlüsselung ──────────────────────────────────────────────────────────
def test_bilanz_je_sportart():
    hist = _fixture([_bet(), _bet(orderId="0xesp", polyKey="cs2-a-b-2026-08-24",
                                 side="Team A", sport="E-Sport")])
    res = {"atp-alcaraz-sinner-2026-08-24": {"winner": "Alcaraz"},
           "cs2-a-b-2026-08-24": {"winner": "Team B"}}
    out = D.settle(D.collect_bets(hist), {}, res, now=NOW)
    assert out["bySport"]["Tennis"]["pnl"] == 10.0
    assert out["bySport"]["E-Sport"]["pnl"] == -10.0
    assert out["agg"]["n"] == 2 and out["agg"]["pnl"] == 0.0


def test_leere_bilanz_kippt_nicht_um():
    out = D.settle([], {}, {}, now=NOW)
    assert out["agg"]["n"] == 0 and out["agg"]["roi"] is None and out["agg"]["hit"] is None
