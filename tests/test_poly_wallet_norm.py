#!/usr/bin/env python3
"""
„Gross" heisst relativ, nicht absolut.

05.09.2026 (Lucas): „250.000 ist fuer mich ein Vermoegen, fuer den wahrscheinlich ein normaler
Bet." Die Schwelle war ein fester Dollar-Betrag — 9 Wallets haben ein MEDIAN-Ticket ueber
$50.000, bei denen loeste per Konstruktion jede zweite Position aus. Diese Tests halten fest,
dass die Groesse jetzt gegen das eigene Ticket bzw. den Markt gemessen wird, und dass
„unbekannt" nicht als „normal" durchgeht.
"""
import unittest
from datetime import datetime, timezone

import poly_wallet_norm as N
import poly_whale_watch as W


def _state(wallet, betraege, key_praefix="m"):
    pos = [(wallet, 1_780_000_000_000.0 + i, b, "%s%d|%s" % (key_praefix, i, wallet))
           for i, b in enumerate(betraege)]
    return N.nachtragen({}, pos, jetzt=datetime(2026, 9, 5, tzinfo=timezone.utc))


class TestNorm(unittest.TestCase):
    def test_dedup_ueber_posKey(self):
        """Dieselbe Position steht in zwei Artefakten. Sie darf die Norm nicht zweimal beschweren."""
        pos = [("0xa", 1_788_000_000_000.0, 5000.0, "k|0xa")] * 5
        st = N.nachtragen({}, pos, jetzt=datetime(2026, 9, 5, tzinfo=timezone.utc))
        self.assertEqual(len(st["samples"]["0xa"]), 1)
        self.assertEqual(st["zugangLetzterLauf"], 1)

    def test_unter_MIN_N_keine_Zahl(self):
        """Ueber ein Konto mit vier Positionen ist nichts bekannt — und das muss anders
        aussehen als ein gemessenes „normal"."""
        norm = N.norm_bauen(_state("0xa", [1000, 2000, 3000, 4000]))
        e = norm["0xa"]
        self.assertEqual(e["basis"], "zu duenn")
        self.assertIsNone(e["median"])
        self.assertIsNone(N.ticket_vergleich(999999, e))

    def test_ab_MIN_N_gibt_es_ein_Vielfaches(self):
        norm = N.norm_bauen(_state("0xa", [100, 200, 300, 400, 500, 600, 700, 800]))
        tv = N.ticket_vergleich(900, norm["0xa"])
        self.assertEqual(tv["basis"], "gelernt")
        self.assertAlmostEqual(tv["faktor"], 900 / 450.0, places=2)

    def test_schwanz_erst_ab_40(self):
        klein = N.norm_bauen(_state("0xa", list(range(1000, 1000 + 20 * 100, 100))))
        gross = N.norm_bauen(_state("0xb", list(range(1000, 1000 + 60 * 100, 100))))
        self.assertIsNone(klein["0xa"]["schwanz"])
        self.assertIsNotNone(gross["0xb"]["schwanz"])

    def test_ungueltige_Eingaben(self):
        norm = N.norm_bauen(_state("0xa", [100] * 10))
        for u in (None, 0, -5, "viel", True):
            self.assertIsNone(N.ticket_vergleich(u, norm["0xa"]))

    def test_alte_Positionen_fallen_raus(self):
        alt = [("0xa", 1_600_000_000_000.0, 5000.0, "alt|0xa")]
        st = N.nachtragen({}, alt, jetzt=datetime(2026, 9, 5, tzinfo=timezone.utc))
        self.assertNotIn("0xa", st["samples"])

    def test_ts_aus_key(self):
        """Der Markt-Key traegt das Datum. Ohne Datum gilt der Fallback, nicht „heute" —
        sonst blieben alte Positionen ewig frisch."""
        ms = N._ts_aus_key("fl1-hac-asm-2026-08-23", 0.0)
        self.assertEqual(datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat(),
                         "2026-08-23")
        self.assertEqual(N._ts_aus_key("ohne-datum", 42.0), 42.0)
        self.assertEqual(N._ts_aus_key("bad-2026-13-45", 42.0), 42.0)


class TestKarte(unittest.TestCase):
    def setUp(self):
        W._WNORM_CACHE = {"0xgross": {"basis": "gelernt", "n": 12, "median": 200000.0},
                          "0xklein": {"basis": "gelernt", "n": 12, "median": 2000.0}}

    def tearDown(self):
        W._WNORM_CACHE = None

    def _pos(self, wallet, usd, key="k1"):
        return {"wallet": wallet, "usd": usd, "key": key, "side": "A", "league": "SOCCER"}

    def test_Dauerlaeufer_ist_nicht_mehr_gross(self):
        """Der Fall aus der Meldung: $250.900 sind fuer dieses Konto das 1,4-fache seines
        Median-Tickets. Die alte absolute Schwelle sagte trotzdem „gross"."""
        pos = self._pos("0xgross", 250900)
        self.assertGreaterEqual(pos["usd"], W.MIN_USD_UNTRACKED, "Voraussetzung: alte Schwelle greift")
        self.assertFalse(W._ist_gross(pos, {}))
        zeilen = " ".join(W._groessen_zeilen(pos, {}))
        self.assertIn("Normalgröße", zeilen)

    def test_kleines_Konto_das_ploetzlich_schiebt_ist_gross(self):
        """Das ist der Fall, den die absolute Schwelle VERSCHLUCKT hat: 20x das eigene
        Ticket, aber unter $50.000."""
        pos = self._pos("0xklein", 40000)
        self.assertLess(pos["usd"], W.MIN_USD_UNTRACKED)
        self.assertTrue(W._ist_gross(pos, {}))
        self.assertIn("übliche Ticket", " ".join(W._groessen_zeilen(pos, {})))

    def test_unbekanntes_Konto_behauptet_keine_Normalgroesse(self):
        pos = self._pos("0xneu", 250900)
        self.assertEqual(W._groessen_zeilen(pos, {}), [])
        # ohne jede relative Information faellt es auf die absolute Schwelle zurueck
        self.assertTrue(W._ist_gross(pos, {}))

    def test_Marktanteil_nur_wenn_der_Nenner_traegt(self):
        broad = {"k1": {"totalUsd": 400000}, "k2": {"totalUsd": 1000}, "k3": {}}
        self.assertAlmostEqual(W.markt_anteil(self._pos("0xneu", 100000, "k1"), broad), 0.25)
        # Einsatz groesser als das gesamte Marktvolumen -> der Nenner widerspricht dem Zaehler
        self.assertIsNone(W.markt_anteil(self._pos("0xneu", 100000, "k2"), broad))
        self.assertIsNone(W.markt_anteil(self._pos("0xneu", 100000, "k3"), broad))
        self.assertIsNone(W.markt_anteil(self._pos("0xneu", 100000, "fehlt"), broad))

    def test_Marktanteil_traegt_wenn_das_Konto_unbekannt_ist(self):
        broad = {"k1": {"totalUsd": 100000}}
        pos = self._pos("0xneu", 40000, "k1")     # 40 % des Markts, aber unter $50.000
        self.assertLess(pos["usd"], W.MIN_USD_UNTRACKED)
        self.assertTrue(W._ist_gross(pos, broad))

    def test_Ueberschrift_behauptet_kein_Gross_mehr_wenn_es_keins_ist(self):
        karte = W.build_card(self._pos("0xgross", 250900), {}, False, {})
        self.assertIn("Whale-Einstieg", karte)
        self.assertNotIn("Großer", karte)


if __name__ == "__main__":
    unittest.main()
