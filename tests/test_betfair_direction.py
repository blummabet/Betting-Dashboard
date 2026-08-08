#!/usr/bin/env python3
"""test_betfair_direction.py -- Richtungs-Signal aus der Quotenbewegung (08.08.2026, Lucas).
Quote kuerzer = gebackt ('in'), Quote driftet = gelayt ('out'), sonst 'flat'."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import betfair_direction as D


def _prices(over_odd, under_odd, mid="1"):
    return {"matches": [{"matchId": mid, "markets": {"Over/Under 2.5 Goals": {"runners": [
        {"name": "Over 2.5 Goals", "odd": over_odd, "vol": 1200},
        {"name": "Under 2.5 Goals", "odd": under_odd, "vol": 600}]}}}]}


def test_classify():
    assert D.classify(1.40, 1.50) == "in"     # -6.7% -> kuerzer -> Back
    assert D.classify(1.60, 1.50) == "out"    # +6.7% -> laenger -> Lay/Drift
    assert D.classify(1.51, 1.50) == "flat"   # < 3% -> Rauschen
    assert D.classify(None, 1.50) == "flat"
    assert D.classify(1.4, 0) == "flat"


def test_erster_lauf_alles_flat():
    d = D.annotate(_prices(1.40, 3.50), {})
    assert d["1"]["Over/Under 2.5 Goals"]["Over 2.5 Goals"]["dir"] == "flat"
    assert d["1"]["Over/Under 2.5 Goals"]["Over 2.5 Goals"]["prev"] is None


def test_over_wird_gebackt():
    prev = D.annotate(_prices(1.50, 3.20), {})
    d = D.annotate(_prices(1.40, 3.50), prev)           # Over 1.50->1.40 kuerzer, Under driftet
    over = d["1"]["Over/Under 2.5 Goals"]["Over 2.5 Goals"]
    under = d["1"]["Over/Under 2.5 Goals"]["Under 2.5 Goals"]
    assert over["dir"] == "in" and over["prev"] == 1.50
    assert under["dir"] == "out"


def test_volumen_favorit_driftet_trotz_geld():
    # Blinder Fleck: Over hat mehr Volumen (Favorit), aber die Quote DRIFTET -> kein echter Back-Rueckhalt
    prev = D.annotate(_prices(1.40, 3.50), {})
    d = D.annotate(_prices(1.55, 3.10), prev)           # Over 1.40->1.55 laenger
    assert d["1"]["Over/Under 2.5 Goals"]["Over 2.5 Goals"]["dir"] == "out"


def test_look_join():
    d = D.annotate(_prices(1.40, 3.50), {})
    assert D.look(d, "1", "Over/Under 2.5 Goals", "Over 2.5 Goals")["odd"] == 1.40
    assert D.look(d, "1", "Over/Under 2.5 Goals", "Nope") is None
    assert D.look(d, "999", "x", "y") is None


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f(); print("ok", f.__name__)
    print("\n%d tests passed" % len(fns))
