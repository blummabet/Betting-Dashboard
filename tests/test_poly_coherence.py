"""19.07.2026 — Poly-interne Kohärenz: Polymarket gegen sich selbst.

Der Detektor sucht Widersprüche in Polys EIGENEN Preisen — ohne Pinnacle-Anker. Die Tests halten
die drei Härtegrade auseinander und, genauso wichtig, die Fälle, in denen NICHTS gemeldet werden
darf: ein Fehlalarm hier schickt echtes Geld in einen Scheinarb.
"""
import pytest

import poly_coherence as C


def _match(**over):
    e = {"title": "A vs B", "vol": 50_000,
         "hw": 0.40, "dr": 0.30, "aw": 0.30,
         "poly_o15": 0.70, "poly_o25": 0.45, "poly_o35": 0.22,
         "poly_u15": 0.30, "poly_u25": 0.55, "poly_u35": 0.78,
         "poly_btts": 0.52, "poly_btts_no": 0.48}
    e.update(over)
    return {"prices": {"K": e}}


def _typen(rep):
    return {b["typ"] for b in rep["findings"]}


class TestArb:
    def test_underround_ou_paar_ist_arb(self):
        # o25+u25 = 0.44+0.50 = 0.94 → beide kaufen zahlt 1.0, kostet 0.94
        rep = C.analyze(_match(poly_o25=0.44, poly_u25=0.50))
        arb = [b for b in rep["findings"] if b["typ"] == "underround" and "2.5" in b["markt"]]
        assert arb, "klarer O/U-Underround nicht erkannt"
        assert arb[0]["edgePP"] == pytest.approx(6.0, abs=0.1)

    def test_btts_underround(self):
        rep = C.analyze(_match(poly_btts=0.45, poly_btts_no=0.50))
        assert any(b["markt"] == "BTTS" and b["typ"] == "underround" for b in rep["findings"])

    def test_1x2_underround(self):
        rep = C.analyze(_match(hw=0.30, dr=0.30, aw=0.30))   # Summe 0.90
        assert rep["arbCount"] >= 1

    def test_knapper_underround_zaehlt_nicht(self):
        """0.99 ist nach Spread+Gebühr+Slippage kein Gewinn — nicht als Arb melden."""
        rep = C.analyze(_match(poly_o25=0.49, poly_u25=0.50))   # Summe 0.99
        assert not any(b["typ"] == "underround" and "2.5" in b["markt"] for b in rep["findings"])


class TestLeiterInversion:
    def test_ueber35_teurer_als_ueber25_ist_widerspruch(self):
        rep = C.analyze(_match(poly_o25=0.30, poly_o35=0.45))   # mehr Tore teurer = unmöglich
        inv = [b for b in rep["findings"] if b["typ"] == "ladder_inversion"]
        assert inv, "Leiter-Inversion nicht erkannt"

    def test_saubere_leiter_meldet_nichts(self):
        rep = C.analyze(_match())   # 0.70 > 0.45 > 0.22, monoton fallend
        assert "ladder_inversion" not in _typen(rep)

    def test_winzige_inversion_ist_rundung(self):
        """Zeitversatz zwischen zwei Snapshots → minimale Inversion. Kein echter Widerspruch."""
        rep = C.analyze(_match(poly_o25=0.44, poly_o35=0.45))   # nur 1pp, < LADDER_TOL(1.5pp)
        assert "ladder_inversion" not in _typen(rep)


class TestSpreadWarnung:
    def test_fetter_spread_wird_als_warnung_markiert(self):
        rep = C.analyze(_match(poly_btts=0.56, poly_btts_no=0.55))   # Summe 1.11
        assert any(b["typ"] == "overround" and b["markt"] == "BTTS" for b in rep["findings"])

    def test_normaler_overround_ist_kein_alarm(self):
        """~1.02-1.04 ist der normale Poly-Aufschlag, kein handlungsrelevanter Befund."""
        rep = C.analyze(_match(poly_o25=0.46, poly_u25=0.56))   # 1.02
        assert not any(b["typ"] == "overround" and "2.5" in b["markt"] for b in rep["findings"])


class TestDuenneMaerkteRaus:
    def test_niedriges_volumen_wird_ignoriert(self):
        """Ein 'Arb' auf einem $200-Markt ist ein veralteter Preis, kein Geschenk —
        das ist der teuerste denkbare Fehlalarm."""
        rep = C.analyze(_match(vol=200, poly_o25=0.40, poly_u25=0.45))
        assert rep["findings"] == []

    def test_fehlende_felder_kein_absturz(self):
        rep = C.analyze({"prices": {"K": {"title": "X", "vol": 50_000, "hw": 0.5}}})
        assert isinstance(rep["findings"], list)


class TestRangfolge:
    def test_arb_steht_vor_warnung(self):
        rep = C.analyze(_match(poly_o25=0.44, poly_u25=0.50,      # Arb
                               poly_btts=0.56, poly_btts_no=0.55))  # Warnung
        assert rep["findings"][0]["typ"] == "underround", "härtester Befund muss oben stehen"

    def test_leere_preise(self):
        rep = C.analyze({"prices": {}})
        assert rep["arbCount"] == 0 and rep["findings"] == []
