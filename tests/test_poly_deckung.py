#!/usr/bin/env python3
"""
06.09.2026 — ein Scanner kann nicht melden, was er nie gesehen hat.

`health/poly-global.json` und `poly_status.json` standen beide auf gruen, waehrend dem
Money-Scan 9 Poly-Maerkte fehlten (5 davon im 8h-Fenster, darunter Juventus-Milan mit
$94,6K Event-Volumen). Beide messen, ob der Lauf DURCHLIEF — nicht, ob er VOLLSTAENDIG war.

Deshalb wird gegen eine zweite, unabhaengige Quelle geprueft: `liga_poly_prices.json`.
"""
import unittest
from datetime import datetime, timedelta, timezone

import poly_deckung as D

JETZT = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def _lp(*eintraege):
    return {"prices": {str(i): e for i, e in enumerate(eintraege)}}


def _e(slug, stunden, home="H", away="A", vol=1000):
    return {"slug": slug, "homeName": home, "awayName": away, "vol": vol,
            "kickoff": (JETZT + timedelta(hours=stunden)).isoformat().replace("+00:00", "Z")}


class TestLuecken(unittest.TestCase):
    def test_bekannter_Markt_ist_keine_Luecke(self):
        self.assertEqual(D.luecken(_lp(_e("sea-a-b", 5)), {"sea-a-b"}, now=JETZT), [])

    def test_unbekannter_Markt_im_Fenster_ist_eine_Luecke(self):
        r = D.luecken(_lp(_e("sea-juv-mil", 7.1, "Juventus FC", "AC Milan", 7898)), set(), now=JETZT)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["slug"], "sea-juv-mil")
        self.assertEqual(r[0]["htk"], 7.1)

    def test_history_zaehlt_als_bekannt(self):
        """Einmal erfasst ist keine Luecke — auch wenn der Markt gerade aus dem Fenster ist."""
        self.assertEqual(D.luecken(_lp(_e("x", 5)), {"x"}, now=JETZT), [])

    def test_vergangenes_Spiel_ist_keine_Luecke(self):
        self.assertEqual(D.luecken(_lp(_e("x", -2)), set(), now=JETZT), [])

    def test_weit_draussen_ist_keine_Luecke(self):
        self.assertEqual(D.luecken(_lp(_e("x", 200)), set(), now=JETZT), [])

    def test_ohne_Anpfiff_kein_Urteil(self):
        """Fehlende Information ist keine Erlaubnis — aber auch kein Fund."""
        self.assertEqual(D.luecken(_lp({"slug": "x", "homeName": "H", "awayName": "A"}),
                                   set(), now=JETZT), [])
        self.assertEqual(D.luecken(_lp(dict(_e("x", 5), kickoff="kaputt")), set(), now=JETZT), [])

    def test_ohne_Slug_kein_Urteil(self):
        self.assertEqual(D.luecken(_lp(dict(_e("x", 5), slug=None)), set(), now=JETZT), [])

    def test_sortiert_nach_Anpfiff_Naehe(self):
        r = D.luecken(_lp(_e("spaet", 7), _e("frueh", 2), _e("mitte", 5)), set(), now=JETZT)
        self.assertEqual([x["slug"] for x in r], ["frueh", "mitte", "spaet"])

    def test_nah_filtert_das_Latch_Fenster(self):
        r = D.luecken(_lp(_e("a", 2), _e("b", 7.9), _e("c", 9), _e("d", 40)), set(), now=JETZT)
        self.assertEqual([x["slug"] for x in D.nah(r)], ["a", "b"])

    def test_leere_Eingaben(self):
        self.assertEqual(D.luecken({}, set(), now=JETZT), [])
        self.assertEqual(D.luecken(None, None, now=JETZT), [])
        self.assertEqual(D.nah(None), [])


class TestGuard(unittest.TestCase):
    NAME = "Poly-Deckung: Money-Scan gegen Liga-Fetcher"

    def _lauf(self, ctx):
        import uebersicht_integrity as UI
        return next(c for c in UI.run_checks(ctx) if c["label"] == self.NAME)

    def test_der_reale_Fall_schlaegt_an(self):
        c = self._lauf({"ligaPoly": _lp(_e("sea-juv-mil", 7.1, "Juventus FC", "AC Milan")),
                        "polyClose": {"irgendwas": {}}})
        self.assertFalse(c["ok"])
        self.assertIn("sea-juv-mil", " ".join(c["failures"]))

    def test_gedeckt_ist_gruen(self):
        c = self._lauf({"ligaPoly": _lp(_e("sea-juv-mil", 7.1)),
                        "polyClose": {"sea-juv-mil": {}}})
        self.assertTrue(c["ok"])

    def test_ohne_zweite_Quelle_kein_Urteil(self):
        """Faellt der Liga-Fetcher aus, gibt es keine Vergleichsbasis — dann meldet der Guard
        nichts, statt eine Vollstaendigkeit zu behaupten, die er nicht geprueft hat."""
        c = self._lauf({"ligaPoly": {}, "polyClose": {"x": {}}})
        self.assertTrue(c["ok"])
        self.assertEqual(c["severity"], "warn")


if __name__ == "__main__":
    unittest.main()
