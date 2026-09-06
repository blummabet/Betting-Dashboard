#!/usr/bin/env python3
"""
06.09.2026 — „Serie A sind alle Spiele da. Blödsinn zu sagen 2 solche Spiele seien nicht
verfügbar." Lucas hatte recht, ich lag falsch: ich hatte aus „nicht in unseren Artefakten"
auf „gibt es bei Polymarket nicht" geschlossen. Genau davor warnt unsere eigene Regel —
*leeres eigenes File = unser Fetcher-Bug, nicht die Quelle.*

Drei Ursachen, drei Fixes:
  1. `Rennes` gegen Polys `Stade Rennais FC 1901` teilt NULL Tokens. Der Rueckfall verlangt
     mindestens eines und verweigerte zu Recht — ein niedrigerer Schwellwert waere die falsche
     Antwort gewesen, die richtige ist ein Alias.
  2. `sea-juv-mil` ($94,6K) und `sea-bol-sas` ($50,0K) fehlten im Money-Scan, liegen aber mit
     Slug und Preisen in `liga_poly_prices.json`. Wir holten die Daten, der Konsens fragte sie nie.
  3. `sharePct` kam AUSSCHLIESSLICH aus `shares` — und die traegt nur der close-Pool (~3h).
     Alles weiter draussen bekam `sharePct=None`, `killer.py` las „unbekannt", das Board zeigte ❔.
     `money_map_row()` faellt seit dem 12.08. auf den Preis zurueck, `match_poly` nie: daher
     „Money Map: Konsens 3/3" neben „Punktestand: POLY ❔" fuer dasselbe Spiel.
"""
import unittest

import betfair_consensus as BC


class TestAlias(unittest.TestCase):
    def test_Rennes_trifft_Stade_Rennais(self):
        self.assertIn("rennes", BC._norm("Stade Rennais FC 1901"))
        self.assertGreaterEqual(BC._name_score("Rennes", "Stade Rennais FC 1901"), 0.49)

    def test_der_reale_Fall(self):
        pe = {"key": "fl1-ang-ren", "prices": {
            "Angers SCO": 0.235,
            "Draw (Angers SCO vs. Stade Rennais FC 1901)": 0.245,
            "Stade Rennais FC 1901": 0.515}}
        r = BC._best_poly_entry({"home": "Angers", "away": "Rennes"}, [pe])
        self.assertIsNotNone(r)
        self.assertEqual(r[2], "Stade Rennais FC 1901")

    def test_Alias_paart_nicht_wahllos(self):
        """Die Bruecke bleibt eng: ein Alias darf keine fremden Vereine verbinden."""
        pe = {"key": "x", "prices": {"Stade Brestois 29": 0.5, "Stade de Reims": 0.5}}
        self.assertIsNone(BC._best_poly_entry({"home": "Angers", "away": "Rennes"}, [pe]))


class TestShareAusPreis(unittest.TestCase):
    MIT_GELD = {"key": "a", "src": "close",
                "prices": {"H": 0.6, "Draw (H vs. A)": 0.25, "A": 0.15},
                "shares": {"H": 900.0, "Draw (H vs. A)": 50.0, "A": 50.0}, "totalUsd": 1000}
    NUR_PREIS = {"key": "b", "src": "liga",
                 "prices": {"H": 0.455, "Draw (H vs. A)": 0.285, "A": 0.255}, "totalUsd": 7898}

    def test_Geld_bleibt_Geld(self):
        mp = BC.match_poly({"home": "H", "away": "A"}, {"side": "home"}, [self.MIT_GELD])
        self.assertEqual(mp["sharePct"], 90)
        self.assertEqual(mp["shareSrc"], "geld")

    def test_ohne_Shares_kommt_der_Preis(self):
        """Vorher: None -> „unbekannt" -> ❔, obwohl Markt und Preis vorlagen."""
        mp = BC.match_poly({"home": "H", "away": "A"}, {"side": "home"}, [self.NUR_PREIS])
        self.assertEqual(mp["sharePct"], 46)
        self.assertEqual(mp["shareSrc"], "preis")

    def test_die_beiden_sind_unterscheidbar(self):
        """Preis-Anteil ist nicht Geld-Anteil — wer das gleichsetzt, verkauft eine
        Wahrscheinlichkeit als Geldfluss."""
        a = BC.match_poly({"home": "H", "away": "A"}, {"side": "home"}, [self.MIT_GELD])
        b = BC.match_poly({"home": "H", "away": "A"}, {"side": "home"}, [self.NUR_PREIS])
        self.assertNotEqual(a["shareSrc"], b["shareSrc"])

    def test_ohne_Markt_bleibt_es_None(self):
        self.assertIsNone(BC.match_poly({"home": "X", "away": "Y"}, {"side": "home"}, []))

    def test_kaputter_Preis_erfindet_nichts(self):
        pe = {"key": "c", "src": "liga", "prices": {"H": 0, "Draw (H vs. A)": 0, "A": 0}}
        mp = BC.match_poly({"home": "H", "away": "A"}, {"side": "home"}, [pe])
        self.assertIsNone(mp["sharePct"])
        self.assertIsNone(mp["shareSrc"])


class TestPickPolyKette(unittest.TestCase):
    def test_liga_ist_die_letzte_Quelle(self):
        """Reihenfolge: live > close > upcoming > liga. Der Preis aus dem Liga-Fetcher
        darf echtes Geld nie verdraengen."""
        close = [{"key": "close", "src": "close", "prices": {"H": 0.6, "A": 0.4},
                  "shares": {"H": 90.0, "A": 10.0}, "totalUsd": 100}]
        liga = [{"key": "liga", "src": "liga", "prices": {"H": 0.5, "A": 0.5}, "totalUsd": 1}]
        m = {"home": "H", "away": "A"}
        self.assertEqual(BC.pick_poly(m, {"side": "home"}, False, close, [], [], liga)["key"], "close")
        self.assertEqual(BC.pick_poly(m, {"side": "home"}, False, [], [], [], liga)["key"], "liga")

    def test_ohne_liga_Pool_unveraendert(self):
        """Der neue Parameter ist optional — alte Aufrufer bleiben gueltig."""
        close = [{"key": "close", "src": "close", "prices": {"H": 0.6, "A": 0.4}}]
        self.assertEqual(BC.pick_poly({"home": "H", "away": "A"}, {"side": "home"},
                                      False, close, [], [])["key"], "close")


if __name__ == "__main__":
    unittest.main()
