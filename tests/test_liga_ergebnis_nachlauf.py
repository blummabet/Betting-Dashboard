#!/usr/bin/env python3
"""test_liga_ergebnis_nachlauf.py — Ergebnisse muessen ankommen (20.09.2026).

Vorfall: Toulouse–Le Havre, 19.09., fuenf Tore, `Under 2.5 Tore` verloren. Am naechsten
Mittag stand die Wette noch als `placed` im Buch, weil in liga-data.json
`"result": null` steht — der Resolver kann nichts abrechnen, wozu kein Ergebnis da ist.
Ergebnisse schrieb bis hierher nur der Tagesbau (3 Crons/Tag, am 20.09. beide ausgefallen).

Die teure Haelfte: eine Zeile, die nicht abgerechnet werden kann, faellt aus der Rechnung
und nicht negativ auf. Das Buch zeigte einen Verlust, es waren zwei.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_ergebnisse as E  # noqa: E402

JETZT = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


def _fx(**kw):
    f = {"home": "96", "away": "111", "homeName": "Toulouse", "awayName": "Le Havre",
         "fid": 1552772, "kickoff": "2026-09-19T18:45:00Z", "result": None}
    f.update(kw)
    return f


def _groups(*fxs, liga="FRA"):
    return {liga: {"fixtures": list(fxs)}}


class TestOffeneFixtures(unittest.TestCase):
    def test_der_echte_vorfall_wird_gefunden(self):
        offen = E.offene_fixtures(_groups(_fx()), JETZT)
        self.assertEqual(list(offen), ["FRA"])
        self.assertEqual(offen["FRA"][0]["awayName"], "Le Havre")

    def test_ein_spiel_mit_ergebnis_ist_erledigt(self):
        fx = _fx(result={"status": "FT", "home_score": 3, "away_score": 2})
        self.assertEqual(E.offene_fixtures(_groups(fx), JETZT), {})

    def test_ein_laufendes_spiel_ist_kein_befund(self):
        """Innerhalb des Nachlaufs ist ein fehlendes Ergebnis normal — wer hier meldet,
        meldet jeden Abend."""
        fx = _fx(kickoff=(JETZT - timedelta(hours=1)).isoformat())
        self.assertEqual(E.offene_fixtures(_groups(fx), JETZT), {})

    def test_ein_kommendes_spiel_erst_recht_nicht(self):
        fx = _fx(kickoff=(JETZT + timedelta(hours=8)).isoformat())
        self.assertEqual(E.offene_fixtures(_groups(fx), JETZT), {})

    def test_uralt_wird_nicht_still_nachgetragen(self):
        """Ein Spiel, das seit Wochen ohne Ergebnis dasteht, ist ein anderer Befund als ein
        verpasster Tagesbau. Dafuer ist der Guard da, nicht ein stiller Nachtrag."""
        fx = _fx(kickoff="2026-06-01T18:45:00Z")
        self.assertEqual(E.offene_fixtures(_groups(fx), JETZT), {})

    def test_ohne_anpfiff_wird_gezaehlt_statt_geraten(self):
        fx = _fx(kickoff=None)
        self.assertEqual(E.offene_fixtures(_groups(fx), JETZT), {})
        self.assertEqual(E.ohne_anpfiff(_groups(fx)), 1)

    def test_mehrere_ligen_werden_getrennt(self):
        g = _groups(_fx())
        g.update(_groups(_fx(homeName="Venezia", awayName="Lazio", fid=1), liga="ITA"))
        self.assertEqual(sorted(E.offene_fixtures(g, JETZT)), ["FRA", "ITA"])


class TestErgebnisAusApi(unittest.TestCase):
    def _item(self, kurz="FT", h=3, a=2):
        return {"fixture": {"id": 1552772, "status": {"short": kurz}},
                "goals": {"home": h, "away": a}}

    def test_fertiges_spiel(self):
        self.assertEqual(E.ergebnis_aus_api(self._item()),
                         {"status": "FT", "home_score": 3, "away_score": 2})

    def test_verlaengerung_und_elfmeter_zaehlen_als_fertig(self):
        for kurz in ("AET", "PEN"):
            self.assertIsNotNone(E.ergebnis_aus_api(self._item(kurz)), kurz)

    def test_laufendes_oder_abgesagtes_spiel_gibt_nichts(self):
        for kurz in ("1H", "HT", "2H", "NS", "PST", "CANC", ""):
            self.assertIsNone(E.ergebnis_aus_api(self._item(kurz)), kurz)

    def test_fehlende_tore_werden_nicht_zu_null_zu_null(self):
        """Fehlende Information darf nicht als harmloser Default rendern — ein 0:0 waere
        hier eine erfundene Abrechnung."""
        self.assertIsNone(E.ergebnis_aus_api(self._item(h=None)))
        self.assertIsNone(E.ergebnis_aus_api(self._item(a=None)))


class TestEintragen(unittest.TestCase):
    def test_traegt_ein(self):
        fx = _fx()
        self.assertTrue(E.eintragen(fx, {"status": "FT", "home_score": 3, "away_score": 2}))
        self.assertEqual(fx["result"]["home_score"], 3)

    def test_ueberschreibt_kein_vorhandenes_ergebnis(self):
        fx = _fx(result={"status": "FT", "home_score": 1, "away_score": 1})
        self.assertFalse(E.eintragen(fx, {"status": "FT", "home_score": 9, "away_score": 9}))
        self.assertEqual(fx["result"]["home_score"], 1)

    def test_vorhandene_stats_bleiben_erhalten(self):
        """xG schreibt ein anderer Produzent. Wer sie hier ueberbuegelt, loescht sie."""
        fx = _fx(result={"stats": {"xgTotal": 3.4, "xgSource": "api"}})
        self.assertTrue(E.eintragen(fx, {"status": "FT", "home_score": 3, "away_score": 2}))
        self.assertEqual(fx["result"]["stats"]["xgTotal"], 3.4)
        self.assertEqual(fx["result"]["home_score"], 3)


class TestWorkflow(unittest.TestCase):
    def test_der_nachlauf_laeuft_vor_dem_resolver(self):
        """Nachtragen NACH dem Abrechnen haette den Vorfall um einen ganzen Lauf verpasst."""
        y = (REPO / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertIn("fetch_liga_ergebnisse.py", y)
        self.assertLess(y.index("fetch_liga_ergebnisse.py"), y.index("resolve_wm_results.py"))
        # manage-liga-poly staged ueber eine `for f in ...`-Liste, nicht ueber `git add <datei>`
        self.assertIn("liga_ergebnis_nachlauf.json", y.split("Status speichern", 1)[1])

    def test_er_haengt_auch_am_odds_refresh(self):
        """Der Odds-Refresh ist der Workflow, der am 19.09. 17 frische Ergebnisse wieder
        herausgeworfen hat — er traegt sie jetzt im selben Lauf nach."""
        y = (REPO / ".github/workflows/fetch-liga-odds-dense.yml").read_text(encoding="utf-8")
        self.assertIn("fetch_liga_ergebnisse.py", y)
        self.assertIn("APISPORTS_KEY", y)
        self.assertIn("git add liga_ergebnis_nachlauf.json", y)


if __name__ == "__main__":
    unittest.main()
