"""De-Vig: Power ist seit 04.10.2026 scharf (fetch_wm_poly_prices.DEVIG_METHODE).

Messung (Poly-Schlusskurs als Schiedsrichter, 68 Spiele / 339 Ausgaenge seit 14.09.): Power liegt
belegt naeher, in O/U hob proportional die Aussenseiter-Seite um ~1,1pp — Edge, die es nicht gab.
Die Tests fallen am alten Code (proportional scharf, kein fairProp_*, kein Schalter)."""
import importlib
import inspect

import fetch_wm_poly_prices as F
from odds_plausibility import devig_power


def test_power_ist_standard_und_schalter_fuehrt_zurueck(monkeypatch):
    assert F.DEVIG_METHODE == "power"
    monkeypatch.setenv("DEVIG_METHODE", "proportional")
    try:
        assert importlib.reload(F).DEVIG_METHODE == "proportional"
    finally:
        monkeypatch.delenv("DEVIG_METHODE")
        importlib.reload(F)


def test_edge_rechnet_mit_der_scharfen_methode_fuer_1x2_und_ou():
    src = inspect.getsource(F.main)
    assert '_fair = _fairp if DEVIG_METHODE == "power" else _fairq' in src
    assert 'fair_o25, fair_u25 = fairPow_o25, fairPow_u25' in src


def test_gegenprobe_proportional_wird_mitgeschrieben():
    src = inspect.getsource(F.main)
    for feld in ("fairProp_hw", "fairProp_dr", "fairProp_aw", "fairProp_o25", "fairProp_u25", '"devig"'):
        assert feld in src, feld


def test_power_nimmt_dem_aussenseiter_die_scheinbare_edge():
    # O/U 1,40 / 3,00: proportional gibt der Aussenseiter-Seite mehr als power
    imp = [1 / 1.40, 1 / 3.00]
    prop = imp[1] / sum(imp)
    pw = devig_power([1.40, 3.00])[1]
    assert pw < prop and abs(sum(devig_power([1.40, 3.00])) - 1) < 1e-3
