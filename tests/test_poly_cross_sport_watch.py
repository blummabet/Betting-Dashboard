#!/usr/bin/env python3
"""test_poly_cross_sport_watch.py — Cross-Sport-Edge-Alert (28.07.2026, Lucas).
Kernregel: NUR konvergierende Lücken (Poly läuft zur scharfen Pinnacle → echt) werden gemeldet,
rohe/„neue"/stehende Lücken NICHT. Plus Dedup (erneut nur bei weiterer Konvergenz)."""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import poly_cross_sport_watch as X

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _edge(**kw):
    d = {"id": "soccer_mls|a-b|hw", "sport": "soccer_mls", "event": "A vs B", "market": "1X2",
         "outcome": "Heim", "polyPP": 50.0, "pinnPP": 40.0, "gapPP": 10.0, "vol": 105744,
         "richtung": "Poly zu hoch → faden", "convergePP": 2.5}
    d.update(kw)
    return d


def _data(*edges):
    return {"discrepancies": list(edges)}


def test_konvergierende_edge_wird_gewaehlt():
    out = X.select(_data(_edge()), {}, NOW)
    assert len(out) == 1 and out[0]["id"] == "soccer_mls|a-b|hw"


def test_neue_luecke_ohne_konvergenz_wird_nicht_gemeldet():
    # convergePP None = erst einmal gesehen → nicht bewertbar → NICHT alerten.
    out = X.select(_data(_edge(id="x1", convergePP=None)), {}, NOW)
    assert out == []


def test_stehende_oder_wachsende_luecke_raus():
    out = X.select(_data(_edge(id="x2", convergePP=0.2),      # steht (unter MIN_CONVERGE)
                         _edge(id="x3", convergePP=-3.0)), {}, NOW)  # wächst (Artefakt)
    assert out == []


def test_zu_kleine_luecke_und_zu_wenig_volumen_raus():
    out = X.select(_data(_edge(id="x4", gapPP=4.0),           # Lücke < MIN_GAP
                         _edge(id="x5", vol=5000)), {}, NOW)   # Vol < MIN_VOL
    assert out == []


def test_negative_luecke_zaehlt_ueber_betrag():
    # gap -9 (Poly zu niedrig → backen) ist genauso eine Lücke; Betrag zählt.
    out = X.select(_data(_edge(id="x6", gapPP=-9.0, convergePP=2.0)), {}, NOW)
    assert len(out) == 1


def test_dedup_kein_zweiter_alert_ohne_weitere_konvergenz():
    seen = {"soccer_mls|a-b|hw": {"convergePP": 2.5}}
    out = X.select(_data(_edge(convergePP=2.6)), seen, NOW)   # nur +0.1 → unter RECONVERGE
    assert out == []


def test_dedup_erneuter_alert_bei_weiterer_konvergenz():
    seen = {"soccer_mls|a-b|hw": {"convergePP": 0.0}}
    out = X.select(_data(_edge(convergePP=2.5)), seen, NOW)   # +2.5 ≥ RECONVERGE → wieder melden
    assert len(out) == 1


def test_build_card_zeigt_kernfakten():
    card = X.build_card(_edge())
    for frag in ("Cross-Sport-Edge", "A vs B", "Heim", "Poly", "Pinnacle", "+10.0pp",
                 "schließt sich", "Volumen"):
        assert frag in card, frag


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"\n{len(fns)} tests passed")
