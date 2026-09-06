"""Tests fuer preis_deckung.py — 06.09.2026.

Festgehalten wird die REGEL: zu wenig Material heisst kein Urteil, eine vollstaendig blinde
Marktfamilie ist ein Befund, und der Altbestand darf den Fix nicht ueberdecken.
"""
import unittest
from datetime import datetime, timedelta, timezone

import preis_deckung as D

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _rec(markt, preis_signal=True, tage=1, score=2.0):
    sig = [{"name": "form_trend", "score": 1.2}]
    if preis_signal:
        sig.append({"name": "betfair_money", "score": score})
    return {"market": markt, "signals": sig,
            "resolvedAt": (NOW - timedelta(days=tage)).isoformat().replace("+00:00", "Z")}


class TestFamilie(unittest.TestCase):
    def test_zuordnung(self):
        self.assertEqual(D.familie("Beide Teams treffen — Ja"), "BTTS")
        self.assertEqual(D.familie("Über 2.5 Tore"), "Ü/U")
        self.assertEqual(D.familie("Unter 3.5 Tore"), "Ü/U")
        self.assertEqual(D.familie("Unter 6.5 Ecken"), "Ecken")
        self.assertEqual(D.familie("Heimsieg"), "1X2/DC/AH")
        self.assertEqual(D.familie("Doppelte Chance — X2"), "1X2/DC/AH")

    def test_ecken_gehen_nicht_als_unter_durch(self):
        """'Unter 6.5 Ecken' enthaelt 'unter' — die Reihenfolge der Pruefungen entscheidet."""
        self.assertNotEqual(D.familie("Unter 6.5 Ecken"), "Ü/U")


class TestHatPreisSignal(unittest.TestCase):
    def test_erkennt_preis_signal(self):
        self.assertTrue(D.hat_preis_signal(_rec("Heimsieg")))

    def test_nur_staerke_ist_blind(self):
        self.assertFalse(D.hat_preis_signal(_rec("Heimsieg", preis_signal=False)))

    def test_bool_zaehlt_nicht_als_zahl(self):
        r = {"signals": [{"name": "betfair_money", "score": True}]}
        self.assertFalse(D.hat_preis_signal(r))

    def test_kaputte_eingaben(self):
        self.assertFalse(D.hat_preis_signal(None))
        self.assertFalse(D.hat_preis_signal({}))
        self.assertFalse(D.hat_preis_signal({"signals": ["nix"]}))


class TestDeckung(unittest.TestCase):
    def test_zu_wenig_material_kein_urteil(self):
        recs = [_rec("Heimsieg") for _ in range(D.MIN_N - 1)]
        self.assertIsNone(D.deckung(recs, now=NOW))

    def test_altbestand_zaehlt_nicht_mit(self):
        """Alles vor dem Fix ist blind und wuerde die Messung monatelang vergiften."""
        alt = [_rec("Über 2.5 Tore", preis_signal=False, tage=200) for _ in range(300)]
        neu = [_rec("Über 2.5 Tore", preis_signal=True, tage=2) for _ in range(D.MIN_N)]
        d = D.deckung(alt + neu, now=NOW)
        self.assertEqual(d["n"], D.MIN_N)
        self.assertEqual(d["blind"], 0)

    def test_blindquote_und_familien(self):
        recs = ([_rec("Heimsieg") for _ in range(20)]
                + [_rec("Beide Teams treffen — Ja", preis_signal=False) for _ in range(10)])
        d = D.deckung(recs, now=NOW)
        self.assertEqual(d["n"], 30)
        self.assertEqual(d["blind"], 10)
        self.assertAlmostEqual(d["blindPct"], 33.3, places=1)
        self.assertEqual(d["proFamilie"]["BTTS"]["blindPct"], 100.0)
        self.assertEqual(d["proFamilie"]["1X2/DC/AH"]["blindPct"], 0.0)

    def test_ohne_zeitstempel_faellt_raus(self):
        recs = [dict(_rec("Heimsieg"), resolvedAt=None) for _ in range(40)]
        self.assertIsNone(D.deckung(recs, now=NOW))


class TestBefunde(unittest.TestCase):
    def test_kein_urteil_meldet_nichts(self):
        self.assertEqual(D.befunde(None), [])

    def test_gesunde_deckung_meldet_nichts(self):
        recs = [_rec("Heimsieg") for _ in range(40)]
        self.assertEqual(D.befunde(D.deckung(recs, now=NOW)), [])

    def test_vollstaendig_blinde_familie_wird_gemeldet(self):
        recs = ([_rec("Heimsieg") for _ in range(30)]
                + [_rec("Beide Teams treffen — Ja", preis_signal=False) for _ in range(10)])
        b = D.befunde(D.deckung(recs, now=NOW))
        self.assertTrue(any("BTTS" in x for x in b), b)

    def test_kleine_familie_wird_nicht_gemeldet(self):
        """3 blinde BTTS-Picks sind kein Strukturbefund."""
        recs = ([_rec("Heimsieg") for _ in range(40)]
                + [_rec("Beide Teams treffen — Ja", preis_signal=False) for _ in range(3)])
        b = D.befunde(D.deckung(recs, now=NOW))
        self.assertFalse(any("BTTS" in x for x in b), b)


if __name__ == "__main__":
    unittest.main()
