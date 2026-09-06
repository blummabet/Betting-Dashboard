"""Tests fuer signal_stille.py — 06.09.2026.

Regel: Stille ist eine Aussage, aber nur ueber genug Material. Und ein Signal mit Score 0
hat nicht gefeuert — es war nur anwesend.
"""
import unittest

import signal_stille as S

REG = ["form_trend", "polymarket_sharp", "steam_lag", "altitude_signal"]


def _rec(*paare):
    return {"signals": [{"name": n, "score": w} for n, w in paare]}


def _viele(n, *paare):
    return [_rec(*paare) for _ in range(n)]


class TestFeuerungen(unittest.TestCase):
    def test_zaehlt_nur_echte_feuerungen(self):
        f = S.feuerungen(_viele(3, ("form_trend", 1.2), ("steam_lag", 0.0)))
        self.assertEqual(f.get("form_trend"), 3)
        self.assertIsNone(f.get("steam_lag"), "Score 0 ist keine Feuerung")

    def test_negativer_score_ist_eine_feuerung(self):
        """Ein Signal, das WARNT, hat gesprochen."""
        f = S.feuerungen(_viele(2, ("form_trend", -1.4)))
        self.assertEqual(f.get("form_trend"), 2)

    def test_bool_ist_keine_zahl(self):
        self.assertEqual(S.feuerungen(_viele(2, ("form_trend", True))), {})

    def test_kaputte_eingaben(self):
        self.assertEqual(S.feuerungen(None), {})
        self.assertEqual(S.feuerungen([None, 3, "x"]), {})
        self.assertEqual(S.feuerungen([{"signals": ["nix"]}]), {})


class TestStumme(unittest.TestCase):
    def test_zu_wenig_material_kein_urteil(self):
        self.assertIsNone(S.stumme(_viele(S.MIN_RECORDS - 1, ("form_trend", 1.0)), REG))

    def test_findet_die_schweiger(self):
        st = S.stumme(_viele(S.MIN_RECORDS, ("form_trend", 1.0)), REG)
        self.assertEqual(st, ["altitude_signal", "polymarket_sharp", "steam_lag"])

    def test_alle_sprechen(self):
        recs = _viele(S.MIN_RECORDS, *[(n, 1.0) for n in REG])
        self.assertEqual(S.stumme(recs, REG), [])

    def test_ein_einziges_feuern_reicht(self):
        """Das ist der Punkt: 1 von 318 waere schon ein Lebenszeichen gewesen."""
        recs = _viele(S.MIN_RECORDS, ("form_trend", 1.0))
        recs[0]["signals"].append({"name": "polymarket_sharp", "score": 0.8})
        self.assertNotIn("polymarket_sharp", S.stumme(recs, REG))

    def test_leere_registry(self):
        self.assertEqual(S.stumme(_viele(S.MIN_RECORDS, ("form_trend", 1.0)), []), [])


class TestAbgeschaltetUndStumm(unittest.TestCase):
    """Die Stille hat zwei Ursachen, und nur eine davon ist ein Fehler."""

    def test_trennt_die_beiden_ursachen(self):
        g = S.abgeschaltet_und_stumm(
            ["altitude_signal", "polymarket_sharp", "steam_lag"],
            {"altitude_signal", "steam_lag"})
        self.assertEqual(g["abgeschaltet"], ["altitude_signal", "steam_lag"])
        self.assertEqual(g["stumm_trotz_an"], ["polymarket_sharp"])

    def test_ohne_abschaltliste_ist_alles_verdaechtig(self):
        g = S.abgeschaltet_und_stumm(["a", "b"], None)
        self.assertEqual(g["abgeschaltet"], [])
        self.assertEqual(g["stumm_trotz_an"], ["a", "b"])

    def test_leere_stille(self):
        g = S.abgeschaltet_und_stumm(None, {"x"})
        self.assertEqual(g, {"abgeschaltet": [], "stumm_trotz_an": []})


class TestProfilKonfiguration(unittest.TestCase):
    def test_die_reparierten_signale_sind_in_der_liga_an(self):
        """06.09.2026: `smart_money` und `polymarket_sharp` waren abgeschaltet UND defekt.
        Nach der Reparatur (verifiziert: 4 bzw. 6 Feuerungen auf dem echten Bestand) muessen
        sie an sein — sonst laufen 3,04 Mio. USD Poly-Geld weiter an den Picks vorbei."""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "cocobet_config.json"
        if not p.exists():
            self.skipTest("cocobet_config.json fehlt")
        aus = set(((json.loads(p.read_text(encoding="utf-8")).get("profiles") or {})
                   .get("liga_default") or {}).get("disabled_signals") or [])
        for name in ("smart_money", "polymarket_sharp", "pressure_index"):
            self.assertNotIn(name, aus, f"{name} ist in liga_default wieder abgeschaltet")


class TestBefunde(unittest.TestCase):
    def test_kein_urteil_meldet_nichts(self):
        self.assertEqual(S.befunde(None, []), [])
        self.assertEqual(S.befunde([], _viele(80, ("form_trend", 1.0))), [])

    def test_eine_zeile_je_schweiger(self):
        recs = _viele(S.MIN_RECORDS, ("form_trend", 1.0))
        b = S.befunde(S.stumme(recs, REG), recs)
        self.assertEqual(len(b), 3)
        self.assertTrue(all(str(S.MIN_RECORDS) in z for z in b),
                        "die Zeile muss sagen, auf wie vielen Picks sie beruht")


if __name__ == "__main__":
    unittest.main()
