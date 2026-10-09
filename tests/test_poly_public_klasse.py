"""🔴 09.10.2026 (Lucas, Public-Karte „1WIN v Aurora Gaming · $31.7K auf Aurora Gaming · 17 % des
Marktvolumens": „sieht nicht so nach Riesen-Einsatz aus"). Wallet …ac3b, bewiesen 163/288, Rang 25.

Public-Buch (55 abgerechnet): Top-10 ODER >= $50K  n=44 ROI +34,0 %; Rang 11-60 UND < $50K
n=11 ROI -51,3 %. Ab jetzt public nur noch Top-10 oder ab $50K; die aussortierte Gruppe wird
im Trades-Buch markiert und weiter gemessen (Register poly-public-klasse).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import poly_whale_watch as W  # noqa: E402


def _scores(n=30):
    # Rang ueber den Sport-P&L — je groesser, desto weiter vorn.
    return {"0x%02d" % i: {"n": 50, "wins": 35, "clvSumPP": 10.0, "pnl": 1e6 - i * 1000,
                           "usd": 500000} for i in range(1, n + 1)}


def _rang(sc, w):
    return W._sharp_rank_map(sc).get(w)


def test_der_aurora_fall_bleibt_draussen():
    sc = _scores()
    w = next(k for k in sc if _rang(sc, k) == 25)
    assert not W._pub_klasse_ok(sc, {"wallet": w, "usd": 31725})


def test_top_10_darf_auch_klein():
    sc = _scores()
    w = next(k for k in sc if _rang(sc, k) == 7)
    assert W._pub_klasse_ok(sc, {"wallet": w, "usd": 25000})


def test_ab_50k_darf_auch_rang_25():
    sc = _scores()
    w = next(k for k in sc if _rang(sc, k) == 25)
    assert W._pub_klasse_ok(sc, {"wallet": w, "usd": 50000})


def test_ohne_rang_entscheidet_die_groesse_unbekannt_ist_nicht_gross():
    assert W._pub_klasse_ok({}, {"wallet": "0xneu", "usd": 120000})
    assert not W._pub_klasse_ok({}, {"wallet": "0xneu", "usd": 40000})
    assert not W._pub_klasse_ok({}, {"wallet": "0xneu", "usd": None})


def test_die_schwelle_steht_zuletzt_und_markiert_das_trades_buch():
    src = Path(W.__file__).read_text(encoding="utf-8")
    i_klasse = src.index("_klasse_raus = [c for c in pub_cand")
    i_send = src.index("for pkey, pos, restock in pub_cand[:MAX_ALERTS]:")
    i_gegen = src.index("_conflicting_top_wallet(c[1], broad, scores, bewiesen_zaehlt")
    assert i_gegen < i_klasse < i_send
    assert 'feld="publicKlasseGesperrt"' in src


def test_markierung_im_trades_buch(tmp_path, monkeypatch):
    f = tmp_path / "trades.json"
    f.write_text(json.dumps([{"k": "a"}, {"k": "b", "public": True}]), encoding="utf-8")
    monkeypatch.setattr(W, "TRADES_LEDGER_FILE", f)
    W._markiere_public(["a"], feld="publicKlasseGesperrt")
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d[0].get("publicKlasseGesperrt") is True and "public" not in d[0]
    assert "publicKlasseGesperrt" not in d[1]


def test_register_und_zaehler():
    import messungen as M
    reg = json.loads((Path(W.__file__).parent / "messungen_register.json").read_text(encoding="utf-8"))
    e = [x for x in reg["messungen"] if x["id"] == "poly-public-klasse"][0]
    assert e["messer"] in M.ZAEHLER and e["mindestN"] == 30
