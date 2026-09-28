"""Die Pinnacle-O/U-Leiter haengt am selben Key wie der Anker — 27.09.2026 (Terminal-Check).

Denmark v Wales hatte einen Pinnacle-Anker (ueber den globalen Pool, soccer_uefa_nations_league),
aber keine Totals: die wurden nur fuer die Handliste geholt. Der Terminal versprach „erscheinen
nach dem naechsten Betfair-Lauf" — sie waeren nie erschienen.
"""
import pathlib
import betfair_consensus as BC

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _match(m, pool, max_h=None):
    for e in pool:
        if e["home"] == m["home"]:
            return e
    return None


def test_entdeckter_key_mit_pinnacle_bekommt_totals():
    pool = [{"home": "Denmark", "key": "soccer_uefa_nations_league", "pinn": [0.6, 0.25, 0.15]}]
    ks = BC.totals_keys(["soccer_spain_segunda_division"], [{"home": "Denmark"}], pool, _match)
    assert ks == ["soccer_spain_segunda_division", "soccer_uefa_nations_league"]


def test_gegenbeweis_ohne_pinnacle_kein_totals_call():
    pool = [{"home": "Austria", "key": "soccer_uefa_nations_league", "pinn": None}]
    assert BC.totals_keys([], [{"home": "Austria"}], pool, _match) == []


def test_kein_key_doppelt():
    pool = [{"home": "A", "key": "k1", "pinn": [1]}, {"home": "B", "key": "k1", "pinn": [1]}]
    assert BC.totals_keys(["k1"], [{"home": "A"}, {"home": "B"}], pool, _match) == ["k1"]


def test_main_holt_totals_ueber_den_anker_key():
    src = (ROOT / "betfair_consensus.py").read_text(encoding="utf-8")
    main = src[src.index("def main():"):]
    assert main.index("_global_pool = [") < main.index("totals_keys("), "Totals erst nach dem Pool"
    assert '_tk = k or (ev or {}).get("key")' in main, "tev muss den Anker-Key nutzen"
    assert "for k in need:\n        if (_time.monotonic() - _t0) > ODDS_GESAMT_S" not in main
