"""🔴 21.09.2026 (Lucas' Störungsmeldung): „Levante–Athletic Club seit 97 h ohne Ergebnis".

Das Spiel wurde am 16.09. eine halbe Stunde vor Anpfiff wegen Starkregen abgesagt. Am 20.09.
wurde die Absage erkannt und AM FIXTURE in `liga-data.json` vermerkt — und rollte mit dem
Fixture aus dem Fenster des Datensatzes. Danach meldete es niemand mehr: nicht weil es
abgerechnet worden wäre, sondern weil die Zeile weg war, über die gemeldet wurde. Gemessen am
21.09.: das Spiel ist in `liga-data.json` nicht mehr auffindbar, seine drei Picks in
`picks_history.json` stehen auf `result: null`, in `money_map_ledger.json` steht es auf
`pending`. Beides rechnet nie ab.

Fehlerklasse: eine Lücke, die sich durch Zeitablauf selbst erledigt, hinterlässt keine
Statistik.

Der zweite Teil des Falls ist der Schlüssel: dieselbe Paarung heisst bei den Quellen anders
(„Athletic Club" / „Athletic Bilbao", „Levante" / „Levante UD"). Ein exakter Namensschlüssel
hätte das Buch genau an dem Fall vorbeilaufen lassen, für den es gebaut wurde — ein toleranter
Schlüssel wiederum darf niemals die falsche Wette voiden. Beides steht hier fest.
"""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import absagen_buch as AB

GESEHEN = "2026-09-20T12:00:00+00:00"


def _levante():
    return AB.eintragen({}, "2026-09-16", "Levante", "Athletic Club", "PST", GESEHEN, liga="ESP")


class TestDerSchluessel(unittest.TestCase):
    def test_ohne_datum_gibt_es_keinen(self):
        self.assertEqual(AB.schluessel("", "A", "B"), "")

    def test_ohne_einen_namen_auch_nicht(self):
        """Ein halber Schlüssel würde später irgendetwas treffen."""
        self.assertEqual(AB.schluessel("2026-09-16", "Levante", ""), "")

    def test_ein_kaputtes_datum_ist_kein_datum(self):
        self.assertEqual(AB.schluessel("16.09.2026", "A", "B"), "")


class TestDerEchteFallLevante(unittest.TestCase):
    def test_athletic_club_und_athletic_bilbao_sind_dieselbe_paarung(self):
        self.assertIsNotNone(AB.nachschlagen(_levante(), "2026-09-16", "Levante", "Athletic Bilbao"))

    def test_levante_und_levante_ud_ebenso(self):
        self.assertIsNotNone(AB.nachschlagen(_levante(), "2026-09-16", "Levante UD", "Athletic Club"))

    def test_der_status_kommt_mit(self):
        e = AB.nachschlagen(_levante(), "2026-09-16", "Levante", "Athletic Bilbao")
        self.assertEqual(e["status"], "PST")
        self.assertEqual(e["gesehenAt"], GESEHEN)


class TestNichtGeraten(unittest.TestCase):
    def test_ein_anderer_tag_ist_ein_anderes_spiel(self):
        self.assertIsNone(AB.nachschlagen(_levante(), "2026-09-17", "Levante", "Athletic Bilbao"))

    def test_atletico_ist_nicht_athletic(self):
        self.assertIsNone(AB.nachschlagen(_levante(), "2026-09-16", "Levante", "Atletico Madrid"))

    def test_bei_zwei_passenden_wird_nichts_abgerechnet(self):
        """Manchester United und Manchester City am selben Tag gegen denselben Gegner.
        Eine falsch gevoidete Wette ist teurer als eine, die offen bleibt."""
        b = AB.eintragen({}, "2026-09-16", "Manchester United", "Chelsea", "PST", GESEHEN)
        b = AB.eintragen(b, "2026-09-16", "Manchester City", "Chelsea", "PST", GESEHEN)
        self.assertIsNone(AB.nachschlagen(b, "2026-09-16", "Manchester Utd", "Chelsea"))

    def test_aber_es_verschwindet_nicht_als_nicht_abgesagt(self):
        """Mehrdeutig ist eine eigene Auskunft — sonst sieht der Fall aus wie „findet statt"."""
        b = AB.eintragen({}, "2026-09-16", "Manchester United", "Chelsea", "PST", GESEHEN)
        b = AB.eintragen(b, "2026-09-16", "Manchester City", "Chelsea", "PST", GESEHEN)
        self.assertTrue(AB.mehrdeutig(b, "2026-09-16", "Manchester Utd", "Chelsea"))

    def test_ein_exakter_treffer_ist_nie_mehrdeutig(self):
        b = AB.eintragen({}, "2026-09-16", "Manchester United", "Chelsea", "PST", GESEHEN)
        b = AB.eintragen(b, "2026-09-16", "Manchester City", "Chelsea", "PST", GESEHEN)
        self.assertFalse(AB.mehrdeutig(b, "2026-09-16", "Manchester United", "Chelsea"))
        self.assertIsNotNone(AB.nachschlagen(b, "2026-09-16", "Manchester United", "Chelsea"))


class TestDasBuchFuehrtSich(unittest.TestCase):
    def test_der_erste_zeitpunkt_bleibt_stehen(self):
        """Wann die Absage zuerst bekannt war, IST die Auskunft — jeder Lauf würde sie sonst
        nach vorn schieben und „seit wann hängt das" unbeantwortbar machen."""
        b = _levante()
        b = AB.eintragen(b, "2026-09-16", "Levante", "Athletic Club", "PST", "2026-09-21T06:00:00+00:00")
        self.assertEqual(list(b.values())[0]["gesehenAt"], GESEHEN)

    def test_ohne_status_wird_nichts_eingetragen(self):
        self.assertEqual(AB.eintragen({}, "2026-09-16", "A", "B", "", GESEHEN), {})

    def test_das_uebergebene_buch_bleibt_unveraendert(self):
        b = {}
        AB.eintragen(b, "2026-09-16", "A", "B", "PST", GESEHEN)
        self.assertEqual(b, {})

    def test_alte_eintraege_fallen_raus(self):
        b = AB.eintragen({}, "2026-01-01", "A", "B", "PST", GESEHEN)
        self.assertEqual(AB.aufraeumen(b, dt.date(2026, 9, 21)), {})

    def test_frische_bleiben(self):
        self.assertEqual(len(AB.aufraeumen(_levante(), dt.date(2026, 9, 21))), 1)

    def test_ein_eintrag_ohne_lesbares_datum_wird_nicht_weggeworfen(self):
        """Ihn zu entfernen wäre eine Entscheidung auf Basis einer Information, die fehlt."""
        b = {"x": {"datum": None, "heim": "A", "gast": "B", "status": "PST"}}
        self.assertEqual(len(AB.aufraeumen(b, dt.date(2026, 9, 21))), 1)


class TestDerWaechter(unittest.TestCase):
    """Ein Buch, das niemand liest, ist dasselbe Schweigen mit mehr Dateien."""

    def _ctx(self, tmp, buch, hist):
        import wm_data_integrity as W
        (tmp / "liga_absagen.json").write_text(json.dumps(buch), encoding="utf-8")
        (tmp / "picks_history.json").write_text(json.dumps(hist), encoding="utf-8")
        W._LAZY_CACHE = {} if hasattr(W, "_LAZY_CACHE") else None
        return W

    def test_eine_bekannte_absage_die_offen_steht_ist_ein_fehler(self):
        import wm_data_integrity as W
        from unittest import mock
        buch = _levante()
        hist = [{"id": "x", "dateIso": "2026-09-16", "home": "Levante",
                 "away": "Athletic Club", "resolved": False, "picks": [{"result": None}]}]
        def fake(n):
            return buch if n == "liga_absagen.json" else (hist if n == "picks_history.json" else None)
        with mock.patch.object(W, "_lazy", side_effect=fake):
            c = W.check_absagen_werden_abgerechnet(None)
        self.assertFalse(c["ok"])
        self.assertIn("Levante", c["failures"][0])

    def test_abgerechnet_ist_still(self):
        import wm_data_integrity as W
        from unittest import mock
        buch = _levante()
        hist = [{"id": "x", "dateIso": "2026-09-16", "home": "Levante",
                 "away": "Athletic Club", "resolved": True, "picks": [{"result": "void"}]}]
        def fake(n):
            return buch if n == "liga_absagen.json" else (hist if n == "picks_history.json" else None)
        with mock.patch.object(W, "_lazy", side_effect=fake):
            self.assertTrue(W.check_absagen_werden_abgerechnet(None)["ok"])

    def test_ohne_buch_behauptet_er_nichts(self):
        import wm_data_integrity as W
        from unittest import mock
        with mock.patch.object(W, "_lazy", side_effect=lambda n: None):
            c = W.check_absagen_werden_abgerechnet(None)
        self.assertTrue(c["ok"])
        self.assertIn("keine Aussage", c["note"])

    def test_er_ist_registriert(self):
        import wm_data_integrity as W
        self.assertIn("check_absagen_werden_abgerechnet",
                      [f.__name__ for f in W.INTEGRITY_CHECKS])


class TestDerResolverRechnetSieAb(unittest.TestCase):
    """Der eigentliche Beweis: nicht dass das Buch existiert, sondern dass die Zeile zugeht."""

    def _lauf(self, hist, buch):
        import os
        import tempfile
        from unittest import mock
        import resolve_picks as R
        tmp = Path(tempfile.mkdtemp())
        (tmp / "picks_history.json").write_text(json.dumps(hist), encoding="utf-8")
        (tmp / "liga_absagen.json").write_text(json.dumps(buch), encoding="utf-8")
        (tmp / "results-cache.json").write_text('{"fixtures": []}', encoding="utf-8")
        alt_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            with mock.patch.object(R, "HISTORY_FILE", tmp / "picks_history.json"), \
                 mock.patch.object(R, "CACHE_FILE", tmp / "results-cache.json"), \
                 mock.patch.object(R, "get_match_result_sofascore", return_value=None):
                R.main()
            return json.loads((tmp / "picks_history.json").read_text(encoding="utf-8"))
        finally:
            os.chdir(alt_cwd)

    def _zeile(self, **kw):
        z = {"id": "2026-09-16-ESP-Levante-Athletic_Club", "dateIso": "2026-09-16",
             "date": "16.09.2026", "league": "ESP", "home": "Levante",
             "away": "Athletic Club", "eventId": 1570389, "resolved": False,
             "picks": [{"market": "Über 2.5 Tore", "result": None},
                       {"market": "Doppelte Chance: X2", "result": None}]}
        z.update(kw)
        return z

    def test_der_echte_fall_geht_zu(self):
        raus = self._lauf([self._zeile()], _levante())
        e = raus[0]
        self.assertTrue(e["resolved"], "die Zeile haengt seit fuenf Tagen und muss zugehen")
        self.assertEqual([p["result"] for p in e["picks"]], ["void", "void"])
        self.assertEqual(e["finalScore"], "PST")
        self.assertEqual(e["absage"]["gesehenAt"], GESEHEN)

    def test_ohne_absage_bleibt_sie_offen(self):
        """Kein Buch-Treffer heisst weiter warten — nicht „void“."""
        raus = self._lauf([self._zeile()], {})
        self.assertFalse(raus[0]["resolved"])
        self.assertEqual([p["result"] for p in raus[0]["picks"]], [None, None])

    def test_eine_mehrdeutige_absage_rechnet_nicht_ab(self):
        b = AB.eintragen({}, "2026-09-16", "Levante UD", "Athletic Club", "PST", GESEHEN)
        b = AB.eintragen(b, "2026-09-16", "Levante FC", "Athletic Bilbao", "CANC", GESEHEN)
        raus = self._lauf([self._zeile(home="Levante", away="Athletic")], b)
        self.assertFalse(raus[0]["resolved"], "bei zwei passenden Absagen wird nicht geraten")


if __name__ == "__main__":
    unittest.main()
