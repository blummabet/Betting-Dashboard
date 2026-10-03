"""Wallet-CLV-Nachspiel (03.10.2026, vorangemeldet, Register `poly-wallet-clv`)."""
import json
from datetime import datetime, timedelta, timezone

import messungen
import poly_wallet_clv_follow as F

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def score(n=30, mittel=2.0, sd=1.0):
    # in sich geschlossenes Fenster: Summe und Quadratsumme derselben n Werte
    return {"n": n, "clvFenN": n, "clvFenSum": n * mittel, "clvSqSum": n * (mittel ** 2 + sd ** 2),
            "clvSumPP": n * mittel, "wins": n // 2}


def pos(w="W", key="k1", side="A", unser=0.50, ihr=0.495, alter_min=10, htk=5.0, sport="E-Sport"):
    return {"wallet": w, "key": key, "side": side, "sport": sport, "league": "L",
            "firstTs": (NOW - timedelta(minutes=alter_min)).isoformat(),
            "firstPrice": unser, "lastPrice": unser, "entryPrice": ihr, "htkFirst": htk}


def wt(*positionen, scores=None):
    return {"open": {f"{p['wallet']}|{p['key']}|{p['side']}": p for p in positionen},
            "scores": scores or {"W": score()}}


def buch(*positionen, scores=None, prev=None, res=None, close=None, now=NOW):
    return F.update_buch(prev or {}, wt(*positionen, scores=scores), close or {}, res or {},
                         {"Kampfsport"}, now=now)


def test_ug_aus_dem_geschlossenen_fenster_nicht_aus_n():
    """Gegentest zum Fehler beim ersten Ueberschlag: n (seit jeher) mit der Quadratsumme (seit
    02.09.) gemischt ergibt eine zu kleine Streuung — 120 statt 54 „belegte" Wallets."""
    s = dict(score(n=20, mittel=1.0, sd=4.0), n=400, clvSumPP=400.0)
    assert F.wallet_clv(s)["n"] == 20
    assert F.qualifiziert(s) is None, "UG = 1 - 1.645*4/sqrt(20) < 0"


def test_nehmbar_und_zu_spaet_werden_getrennt():
    b = buch(pos(key="a", unser=0.505, ihr=0.50), pos(key="b", unser=0.53, ihr=0.50))
    arms = {e["key"]: e["arm"] for e in b["open"].values()}
    assert arms == {"a": "nehmbar", "b": "zu_spaet"}
    assert b["open"]["a|A"]["walletUg"] > 0, "Qualifikation beim Einstieg eingefroren"


def test_was_nicht_passt_bleibt_draussen():
    b = buch(pos(key="alt", alter_min=200), pos(key="live", htk=0), pos(key="ohne", ihr=None),
             pos(key="ks", sport="Kampfsport"), pos(w="X", key="fremd"),
             scores={"W": score(), "X": score(mittel=0.1, sd=3.0)})
    assert b["open"] == {}
    assert b["zaehler"] == {"ohneEinstieg": 1, "gesperrt": 1, "alt": 1}


def test_je_markt_und_seite_nur_einmal():
    b = buch(pos(w="W", key="k"), pos(w="V", key="k"), scores={"W": score(), "V": score()})
    assert len(b["open"]) == 1
    b2 = F.update_buch(b, wt(pos(w="W", key="k")), {}, {}, set(), now=NOW + timedelta(minutes=15))
    assert len(b2["open"]) == 1


def test_abrechnung_zum_eigenen_preis_und_clv():
    b = buch(pos(key="k", unser=0.50, ihr=0.50))
    b = F.update_buch(b, {"open": {}, "scores": {}}, {"k": {"prices": {"A": 0.60}}},
                      {"k": {"winner": "A"}}, set(), now=NOW + timedelta(hours=6))
    z = b["settled"][0]
    assert z["result"] == "win" and z["pnl"] == 10.0 and z["clvPP"] == 10.0
    assert b["agg"]["nehmbar"]["n"] == 1 and b["agg"]["zu_spaet"]["n"] == 0


def test_messung_zaehlt_nur_nehmbar(tmp_path):
    (tmp_path / "poly_wallet_clv_follow.json").write_text(json.dumps({"settled": [
        {"arm": "nehmbar", "result": "win"}, {"arm": "zu_spaet", "result": "loss"},
        {"arm": "nehmbar", "result": "loss"}]}))
    assert messungen.zaehler_wallet_clv(str(tmp_path)) == 2
    reg = json.load(open("messungen_register.json"))
    e = next(m for m in reg["messungen"] if m["id"] == "poly-wallet-clv")
    assert e["messer"] in messungen.ZAEHLER


def test_workflow_ruft_auf_und_committet():
    src = open(".github/workflows/poly-global-scan.yml", encoding="utf-8").read()
    assert "poly_wallet_clv_follow.py" in src and "poly_wallet_clv_follow.json" in src



def test_heisse_wallet_ohne_langen_beleg_wird_auch_gefolgt():
    """03.10.2026 (Lucas: „mit der Welle mitschwimmen"): 7-Tage-CLV > +1 Punkt bei n >= 8."""
    heiss = {"clvFenN": 3, "fenster7": {"n": 10, "clv": 1.8}}
    b = buch(pos(w="H", key="h"), scores={"H": heiss})
    e = b["open"]["h|A"]
    assert e["heiss"] is True and e["belegt"] is False and e["clv7"] == 1.8


def test_abgekuehlt_faellt_raus():
    kalt = {"clvFenN": 3, "fenster7": {"n": 10, "clv": 0.4}}
    assert buch(pos(w="K", key="k"), scores={"K": kalt})["open"] == {}


def test_bilanz_getrennt_nach_auswahl():
    rows = [{"result": "win", "pnl": 10, "stake": 10, "arm": "nehmbar", "belegt": True, "heiss": False},
            {"result": "loss", "pnl": -10, "stake": 10, "arm": "nehmbar", "belegt": False, "heiss": True}]
    a = F.aggregate(rows)
    assert a["belegt_nehmbar"]["n"] == 1 and a["heiss_nehmbar"]["n"] == 1
