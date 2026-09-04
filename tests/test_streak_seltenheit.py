"""tests/test_streak_seltenheit.py — 04.09.2026

Lucas: „wir haben ja die Serien … sind die wirklich optimal dargestellt, oder kann man da was
verbessern, um diese Serien schlauer und wichtiger zu machen?"

Gemessen ueber 733 aktive Serien kamen drei Sachen heraus:

1. LAENGE IST KEIN MASSSTAB. Die Liga-Grundraten liegen weit auseinander —
   „Team trifft" 81 %, „Ungeschlagen" 69 %, „Sieg-Serie" 47 %, „Zu null" 28 %. Eine 5er-Serie
   ist im einen Markt in fast jedem vierten Fall reiner Zufall, im anderen praktisch nie.
   Das Board sortierte trotzdem nach Laenge: 17 der Top-25 waren „Team trifft", waehrend
   Barcelonas 8er-Siegesserie gar nicht vorkam.

2. DIE GRUENE PLAKETTE URTEILTE UEBER SICH SELBST. Fuellt eine Serie das 15-Spiele-Fenster,
   war die „Eigentendenz" die Serie selbst — 100 %. 457 von 733 Serien hatten keine
   unabhaengige Basis, 345 davon standen trotzdem als „intakt" da, und ALLE 25 der Top-25.

3. GLEICH LANGE SIEG- UND UNGESCHLAGEN-SERIEN SIND DIESELBEN SPIELE. Bei 8 von 14 Teams war
   die Ungeschlagen-Serie exakt so lang wie die Siegesserie (Bayern 7/7, Freiburg 7/7 …).
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("cs_t", os.path.join(ROOT, "compute_streaks.py"))
CS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CS)


class LigaGrundraten(unittest.TestCase):
    def test_rate_kommt_aus_allen_teams_nicht_aus_den_serien(self):
        form = {"a": {"scoredRate": 0.9}, "b": {"scoredRate": 0.7}, "c": {"scoredRate": 0.8}}
        self.assertAlmostEqual(CS.liga_grundraten(form, {})["scored"], 0.8, places=3)

    def test_gegenrichtung_wird_gedreht(self):
        """Unter 2,5 nutzt dasselbe Feld wie Ueber 2,5 — die Rate muss gespiegelt werden."""
        g = CS.liga_grundraten({"a": {"over25Rate": 0.7}}, {})
        self.assertAlmostEqual(g["over25"], 0.7, places=3)
        self.assertAlmostEqual(g["under25"], 0.3, places=3)

    def test_ohne_daten_gibt_es_keine_erfundene_rate(self):
        self.assertNotIn("scored", CS.liga_grundraten({}, {}))
        self.assertNotIn("cards", CS.liga_grundraten({"a": {"scoredRate": 0.8}}, {}))

    def test_raten_werden_von_0_und_1_weggeklemmt(self):
        """p=1 wuerde jede Serie als voellig normal erklaeren, p=0 jede als Wunder."""
        g = CS.liga_grundraten({"a": {"scoredRate": 1.0}, "b": {"cleanSheetRate": 0.0}}, {})
        self.assertLess(g["scored"], 1.0)
        self.assertGreater(g["cleanSheet"], 0.0)


class Seltenheit(unittest.TestCase):
    def test_der_reale_vergleich(self):
        """Der ganze Punkt: 15x „Team trifft" ist harmloser als 4x „Zu null"."""
        trifft = CS.zufall_pct(0.81, 15)
        zunull = CS.zufall_pct(0.28, 4)
        self.assertGreater(trifft, zunull, "die lange Serie ist die wahrscheinlichere")
        self.assertGreater(trifft / zunull, 5, "und zwar deutlich")

    def test_laenger_ist_seltener_innerhalb_desselben_marktes(self):
        self.assertLess(CS.zufall_pct(0.5, 8), CS.zufall_pct(0.5, 5))

    def test_ohne_grundrate_keine_zahl(self):
        self.assertIsNone(CS.zufall_pct(None, 8))
        self.assertIsNone(CS.zufall_pct(0.5, 0))


class Impliziert(unittest.TestCase):
    def _s(self, typ, laenge, tid="1", venue="all"):
        return {"teamId": tid, "venue": venue, "type": typ, "length": laenge, "market": typ}

    def test_gleich_lange_ungeschlagen_serie_ist_dieselbe_nachricht(self):
        """Bayern 7/7, Freiburg 7/7, Arsenal 3/3 — zwei Eintraege, dieselben Spiele."""
        st = CS.markiere_impliziert([self._s("win", 7), self._s("unbeaten", 7)])
        ub = [s for s in st if s["type"] == "unbeaten"][0]
        self.assertEqual(ub["impliziertVon"], "win")

    def test_laengere_ungeschlagen_serie_bleibt_eigenstaendig(self):
        """Inter: Sieg 4x, ungeschlagen 15x — die elf Remis sind eine echte Zusatzaussage."""
        st = CS.markiere_impliziert([self._s("win", 4), self._s("unbeaten", 15)])
        self.assertNotIn("impliziertVon", [s for s in st if s["type"] == "unbeaten"][0])

    def test_zu_null_impliziert_beide_treffen_nein(self):
        st = CS.markiere_impliziert([self._s("cleanSheet", 4), self._s("bttsNo", 4)])
        self.assertEqual([s for s in st if s["type"] == "bttsNo"][0]["impliziertVon"], "cleanSheet")

    def test_die_striktere_serie_wird_nie_markiert(self):
        st = CS.markiere_impliziert([self._s("win", 5), self._s("unbeaten", 5)])
        self.assertNotIn("impliziertVon", [s for s in st if s["type"] == "win"][0])

    def test_verschiedene_teams_beeinflussen_sich_nicht(self):
        st = CS.markiere_impliziert([self._s("win", 5, tid="1"), self._s("unbeaten", 5, tid="2")])
        self.assertTrue(all("impliziertVon" not in s for s in st))

    def test_heim_und_auswaerts_werden_getrennt_betrachtet(self):
        st = CS.markiere_impliziert([self._s("win", 5, venue="H"), self._s("unbeaten", 5, venue="A")])
        self.assertTrue(all("impliziertVon" not in s for s in st))
