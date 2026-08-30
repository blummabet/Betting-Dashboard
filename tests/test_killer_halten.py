"""tests/test_killer_halten.py — 30.08.2026

Lucas: „vorhin stand da Inter und Freiburg, jetzt Man Utd, und nun grad wieder Inter und
Chelsea — das wechselt auch ohne dass ich die Seite aktualisiere."

Ursache: `inflow` ist kein Zustand, sondern ein Intervall-Delta („seit dem letzten Scan sind
>=2.000 EUR reingeflossen"). Kommt das Geld in Schueben, steht das Flag einen Lauf an und den
naechsten aus, obwohl das Geld weiter im Markt liegt. Gemessen ueber 40 Laeufe (~10 Stunden):
in mehr als der Haelfte war die Sektion leer, 15 Spiele trafen irgendwann, 6 davon (40%) waren
in GENAU EINEM Lauf sichtbar. Aus so einer Liste kann niemand blind spielen.

Deshalb wird gehalten. Diese Tests halten die drei Eigenschaften fest, auf die es dabei ankommt.
"""
import unittest
from datetime import datetime, timedelta, timezone

import killer

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
KO = (NOW + timedelta(hours=4)).isoformat().replace("+00:00", "Z")


def sig(**kw):
    d = {"fav": "H", "share": 0.74, "odd": 1.80, "entryOdd": 1.78, "pinnClose": None,
         "pinnFair": None, "conc": True, "inflow": True, "dir": "in"}
    d.update(kw)
    return d


def state(**kw):
    s = sig(**kw)
    return {"pending": {"1": {"league": "English Premier League", "home": "Arsenal",
                              "away": "Chelsea", "kickoff": KO, "signals": {"Match Odds": s}}}}


def cons():
    return {"games": [{"matchId": "1", "home": "Arsenal", "away": "Chelsea",
                       "moneySide": "home", "poly": None, "pinn": None, "verdict": "konsens"}]}


def lauf(latch, now, **sigkw):
    return killer.baue(state(**sigkw), cons(), {}, {"streaks": []}, now=now,
                       latch_state={"latch": latch})


class Halten(unittest.TestCase):
    def test_treffer_ueberlebt_den_naechsten_lauf_ohne_zufluss(self):
        # Genau der Fall aus Lucas' Beobachtung: das Geld liegt noch da, nur das Delta ist 0.
        a = lauf({}, NOW)
        self.assertEqual(len(a["stufe2"]), 1)
        b = lauf(a["_latch"], NOW + timedelta(minutes=15), inflow=False)
        self.assertEqual(len(b["stufe2"]), 1, "der Treffer darf nicht verschwinden")

    def test_haltepreis_bleibt_der_preis_von_damals(self):
        a = lauf({}, NOW)
        b = lauf(a["_latch"], NOW + timedelta(minutes=15), odd=2.40)
        z = b["stufe2"][0]
        self.assertEqual(z["haltePreis"], 1.80, "der gezeigte Preis war 1.80")
        self.assertEqual(z["odd"], 2.40, "der aktuelle Preis gehoert daneben")

    def test_aktiv_zeigt_ob_die_bedingungen_gerade_anliegen(self):
        a = lauf({}, NOW)
        self.assertTrue(a["stufe2"][0]["aktiv"])
        spaet = NOW + timedelta(minutes=killer.AKTIV_FENSTER_MIN + 10)
        b = lauf(a["_latch"], spaet, inflow=False)
        self.assertFalse(b["stufe2"][0]["aktiv"],
                         "gehalten heisst nicht: laeuft noch — das muss unterscheidbar bleiben")

    def test_anpfiff_beendet_das_halten(self):
        a = lauf({}, NOW)
        nach = NOW + timedelta(hours=5)
        b = killer.baue({"pending": {}}, cons(), {}, {"streaks": []}, now=nach,
                        latch_state={"latch": a["_latch"]})
        self.assertEqual(b["stufe1"] + b["stufe2"], [])
        self.assertEqual(len(b["_angepfiffen"]), 1, "die Zeile wandert ins Ledger, nicht ins Nichts")

    def test_verstaerker_duerfen_dazukommen_kern_bleibt(self):
        a = lauf({}, NOW)
        self.assertEqual(a["stufe2"][0]["verstaerker"], [])
        c = cons()
        c["games"][0]["pinn"] = {"home": .6, "draw": .25, "away": .15, "fav": "home"}
        c["games"][0]["poly"] = {"sharePct": 71, "vol": 40000, "odd": 1.75}
        b = killer.baue(state(), c, {}, {"streaks": []}, now=NOW + timedelta(minutes=15),
                        latch_state={"latch": a["_latch"]})
        z = (b["stufe1"] + b["stufe2"])[0]
        self.assertTrue(z["verstaerker"], "spaeter dazugekommene Deckung gehoert dazu")
        self.assertEqual(z["haltePreis"], 1.80, "der Kern-Beleg bleibt trotzdem der vom ersten Mal")


class Buch(unittest.TestCase):
    def test_gehaltene_zeile_wird_zum_haltepreis_abgerechnet(self):
        a = lauf({}, NOW)
        nach = NOW + timedelta(hours=5)
        b = killer.baue({"pending": {}}, cons(), {}, {"streaks": []}, now=nach,
                        latch_state={"latch": a["_latch"]})
        led = killer._ledger_fortschreiben(
            [], b["_angepfiffen"],
            results=[{"matchId": "1", "market": "Match Odds", "win": True, "odd": 1.35}], now=nach)
        self.assertEqual(len(led), 1)
        self.assertEqual(led[0]["status"], "abgerechnet")
        s = killer.schublade_gehalten(led)
        self.assertAlmostEqual(s["renditen"][0], 0.80, 2,
                               "1.80 war der gezeigte Preis — nicht die Schlussquote 1.35")

    def test_ohne_ergebnis_bleibt_die_zeile_offen(self):
        led = killer._ledger_fortschreiben(
            [], [{"matchId": "9", "markt": "Match Odds", "haltePreis": 2.0, "odd": 2.0}],
            results=[], now=NOW)
        self.assertEqual(led[0]["status"], "offen")
        self.assertEqual(killer.schublade_gehalten(led)["renditen"], [])

    def test_keine_doppelten_zeilen(self):
        z = [{"matchId": "9", "markt": "Match Odds", "haltePreis": 2.0, "odd": 2.0}]
        led = killer._ledger_fortschreiben([], z, results=[], now=NOW)
        led = killer._ledger_fortschreiben(led, z, results=[], now=NOW)
        self.assertEqual(len(led), 1)


if __name__ == "__main__":
    unittest.main()
