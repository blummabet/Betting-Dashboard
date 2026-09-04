"""tests/test_uebersicht_integrity.py — 04.09.2026

Lucas: „mir waere es wichtig fehlerfrei zu sein, weil sonst ist die ganze Arbeit in Wahrheit
umsonst."

Die Betfair-, Poly- und WM-Pipelines haben je eine Guard-Batterie auf ihre eigenen Daten. Die
UEBERSICHT hatte keine — dabei ist sie die einzige Flaeche, die elf Engines zu SAETZEN verdichtet,
und genau dort entstehen die Fehler. Die drei Funde vom 04.09. waren kein Absturz, keine
Fehlrechnung, kein Datenfehler: es waren Behauptungen, die zum Schreibzeitpunkt stimmten und
danach still veralteten.

Diese Tests pruefen die Guards selbst — jeder muss den Vorfall fangen, aus dem er entstanden ist.
Ein Guard, der seinen eigenen Fall nicht faengt, ist Dekoration.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("ui_t", os.path.join(ROOT, "uebersicht_integrity.py"))
UI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(UI)


def _ok(res, label):
    return [c for c in res if c["label"] == label][0]["ok"]


class SerienRangfolge(unittest.TestCase):
    """Der Fund: „Beste Streaks" zeigte fuenfmal „Team trifft 15x · Grundrate 82 %"."""

    def _st(self, **kw):
        s = {"length": 15, "zufallPct": 3.87}
        s.update(kw)
        # eigene dicts, sonst aendert pop() alle vier auf einmal
        return {"_meta": {"sortiert": "zufallPct"}, "streaks": [dict(s) for _ in range(4)]}

    def test_gesunder_stand_faellt_nicht_auf(self):
        self.assertTrue(UI.check_serien_rangfolge({"ligaStreaks": self._st()})["ok"])

    def test_fehlendes_seltenheitsmass_wird_gemeldet(self):
        d = self._st()
        for s in d["streaks"]:
            s.pop("zufallPct")
        c = UI.check_serien_rangfolge({"ligaStreaks": d})
        self.assertFalse(c["ok"])
        self.assertIn("Laengen-Sortierung", c["failures"][0])

    def test_abweichendes_sortierkriterium_wird_gemeldet(self):
        d = self._st()
        d["_meta"]["sortiert"] = "length"
        self.assertFalse(UI.check_serien_rangfolge({"ligaStreaks": d})["ok"])

    def test_leerer_datensatz_ist_kein_fehler(self):
        self.assertTrue(UI.check_serien_rangfolge({"ligaStreaks": {"streaks": []}})["ok"])


class FreigabeGrund(unittest.TestCase):
    """Der Fund: „keine Schublade hat ihre Untergrenze ueber null" — Liga·ABWAEGEN stand
    bei ROI-UG +3,7 % und scheiterte an CLV."""

    def test_ohne_roiLb_kann_der_grund_nur_geraten_werden(self):
        f = {"regeln": {"minN": 30}, "alle": [{"schublade": "X", "n": 46, "clvLb": -2.1}]}
        c = UI.check_freigabe_grund({"freigabe": f})
        self.assertFalse(c["ok"])
        self.assertIn("roiLb", c["failures"][0])

    def test_der_reale_fall_wird_als_hinweis_benannt(self):
        f = {"regeln": {"minN": 30},
             "alle": [{"schublade": "Liga · ABWÄGEN", "n": 46, "roiLb": 0.037, "clvLb": -2.16}]}
        c = UI.check_freigabe_grund({"freigabe": f})
        self.assertTrue(c["ok"], "das ist kein Datenfehler, sondern ein Zustand")
        self.assertIn("Liga · ABWÄGEN", c["hinweis"])
        self.assertIn("CLV", c["hinweis"])

    def test_unreife_schubladen_zaehlen_nicht(self):
        f = {"regeln": {"minN": 30}, "alle": [{"schublade": "X", "n": 5}]}
        self.assertTrue(UI.check_freigabe_grund({"freigabe": f})["ok"])


class PolyKachel(unittest.TestCase):
    """Der Fund: „🎮 Poly Public n155 · 70 % · +5,0 %" — die Vorschau, die nichts sendet."""

    def test_ohne_sendet_flag_schlaegt_es_an(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz({"pulse": {"poly": {"n": 155}}})
        self.assertFalse(c["ok"])
        self.assertTrue(any("sendet" in f for f in c["failures"]))

    def test_sendet_true_waere_der_rueckfall(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 155, "sendet": True, "gesendetN": 3}}})
        self.assertFalse(c["ok"])

    def test_richtig_gekennzeichnet_ist_ok(self):
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 155, "sendet": False, "gesendetN": 3}}})
        self.assertTrue(c["ok"])

    def test_gesendetN_none_ist_erlaubt(self):
        """Kein Buch heisst unbekannt — das Feld muss da sein, der Wert darf None sein."""
        c = UI.check_poly_kachel_ist_keine_kanalbilanz(
            {"pulse": {"poly": {"n": 5, "sendet": False, "gesendetN": None}}})
        self.assertTrue(c["ok"])


class StakeKategorien(unittest.TestCase):
    """Der Fund: „Chicago Cubs – Milwaukee Brewers" trotz US-Sport-Sperre in einer Kachel."""

    def test_zeile_ohne_kategorie_wird_gemeldet(self):
        c = UI.check_stake_kategorien({"stake": {"wetten": [{"kat": "Fußball"}, {}]}})
        self.assertFalse(c["ok"])

    def test_vollstaendig_gestempelt_ist_ok(self):
        self.assertTrue(UI.check_stake_kategorien(
            {"stake": {"wetten": [{"kat": "Fußball"}, {"kat": "US-Sport"}]}})["ok"])


class BetfairUrteil(unittest.TestCase):
    """Der Fund: die Fade-Schwelle stand an vier Stellen, die vierte bei -0,05 statt -0,10."""

    def test_fehlendes_urteil_im_artefakt_schlaegt_an(self):
        c = UI.check_betfair_urteil({"bfTrack": {"global": {"n": 100, "roiUg": -0.02}}})
        self.assertFalse(c["ok"])

    def test_bucket_mit_untergrenze_aber_ohne_urteil_faellt_auf(self):
        c = UI.check_betfair_urteil({"bfTrack": {
            "global": {"urteil": "neutral"},
            "byLeagueMarket": {"A|Match Odds": {"roiUg": -0.4}}}})
        self.assertFalse(c["ok"])

    def test_vollstaendig_ist_ok(self):
        c = UI.check_betfair_urteil({"bfTrack": {
            "global": {"urteil": "neutral"},
            "byLeagueMarket": {"A|Match Odds": {"roiUg": -0.4, "urteil": "verliert"}}}})
        self.assertTrue(c["ok"])


class Robustheit(unittest.TestCase):
    def test_die_batterie_laeuft_auf_leerem_kontext_durch(self):
        res = UI.run_checks({})
        self.assertEqual(len(res), len(UI.UEBERSICHT_CHECKS))
        self.assertTrue(all("ok" in c for c in res))

    def test_ein_abstuerzender_guard_kippt_die_batterie_nicht(self):
        def kaputt(ctx):
            raise ValueError("absichtlich")
        alt = list(UI.UEBERSICHT_CHECKS)
        try:
            UI.UEBERSICHT_CHECKS.append(kaputt)
            res = UI.run_checks({})
            letzter = res[-1]
            self.assertFalse(letzter["ok"])
            self.assertIn("gecrasht", letzter["failures"][0])
        finally:
            UI.UEBERSICHT_CHECKS[:] = alt

    def test_jeder_guard_traegt_seinen_vorfall_im_docstring(self):
        """Ein Guard ohne Vorfall ist eine Meinung — im Rest des Repos steht ueberall, WARUM."""
        for fn in UI.UEBERSICHT_CHECKS:
            self.assertTrue((fn.__doc__ or "").strip(), fn.__name__)
            self.assertIn("2026", fn.__doc__, fn.__name__ + ": kein Datum/Vorfall genannt")
