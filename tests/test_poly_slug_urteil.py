"""tests/test_poly_slug_urteil.py — 04.09.2026

Lucas: *„es war Over 2,5 — weiss ich, weil ich mir den Preis angesehen hab."*

Der Push „💰 $41K auf Over" auf Leeds–Brentford stand als TREFFER in unserem Buch. Das Spiel
endete 1:1, der Markt war Over 2,5, die Wette also verloren. `poly_resolutions.json` sagte
`epl-lee-bre-2026-08-30-more-markets → "Over"` — und daraus hat die Abrechnung einen Gewinn
gemacht, den es nie gab.

Ein „-more-markets"-Slug ist kein Markt, sondern ein Buendel: Over/Under auf mehreren Linien.
Bei 1:1 gewinnt Over 1,5 und verliert Over 2,5, und beide heissen im Sieger-Feld „Over". Im
Bestand liegen 3.029 solcher Buendel-Aufloesungen. Sie entscheiden nicht nur ueber das
Public-Buch, sondern ueber die Wallet-Trefferquote — und die entscheidet, wer gepusht wird.

Was hier festgenagelt wird: wo der Sieger-Name die Linie nicht traegt, wird NICHT abgerechnet.
Weder als Treffer noch als Fehlschlag.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_slug_urteil as U

LEE_BRE = "epl-lee-bre-2026-08-30-more-markets"


class DerRealeFall(unittest.TestCase):
    def test_der_push_der_falsch_als_treffer_gebucht_wurde(self):
        self.assertFalse(U.aufloesbar(LEE_BRE, "Over", "Over"))

    def test_auch_die_gegenseite_ist_nicht_entscheidbar(self):
        """Die Sperre darf nicht einseitig sein — „Under" ist genauso mehrdeutig, und ein
        faelschlich gebuchter FEHLSCHLAG waere ebenso falsch wie ein erfundener Treffer."""
        self.assertFalse(U.aufloesbar(LEE_BRE, "Under", "Under"))
        self.assertFalse(U.aufloesbar(LEE_BRE, "Under", "Over"))


class WasGenerischIst(unittest.TestCase):
    def test_alle_bedeutungslosen_labels(self):
        for n in ("Over", "under", "ÜBER", "Unter", "Yes", "no", "Ja", "NEIN"):
            self.assertTrue(U.ist_generisch(n), n)

    def test_ein_unentschieden_ist_ein_echter_ausgang(self):
        """Im Moneyline-Markt bezeichnet „Draw" genau einen Ausgang — anders als „Over"."""
        self.assertFalse(U.ist_generisch("Draw"))
        self.assertTrue(U.aufloesbar("epl-lee-bre-2026-08-30", "Draw", "Draw"))

    def test_teams_und_personen_sind_nie_generisch(self):
        for n in ("Leeds United FC", "MIBR", "Kevin Schade", "England"):
            self.assertFalse(U.ist_generisch(n), n)

    def test_leerwerte_sind_nicht_generisch_aber_auch_kein_ausgang(self):
        self.assertFalse(U.ist_generisch(None))
        self.assertFalse(U.ist_generisch(""))


class WelcheSlugsBetroffenSind(unittest.TestCase):
    def test_nur_buendel_slugs(self):
        self.assertTrue(U.ist_buendel(LEE_BRE))
        self.assertFalse(U.ist_buendel("epl-lee-bre-2026-08-30"))
        self.assertFalse(U.ist_buendel("cs2-mibr-eye-2026-09-03"))

    def test_normaler_markt_bleibt_immer_abrechenbar(self):
        """Ein Moneyline-Markt heisst nie „Over" — und wenn doch, ist er trotzdem eindeutig,
        weil hinter dem Slug nur EIN Markt liegt."""
        self.assertTrue(U.aufloesbar("epl-tot-new-2026-08-29", "Tottenham Hotspur FC",
                                     "Newcastle United FC"))
        self.assertTrue(U.aufloesbar("some-market", "Over", "Under"))

    def test_buendel_mit_echtem_ausgang_bleibt_abrechenbar(self):
        """Gesperrt wird, was mehrdeutig ist — nicht, was einen bestimmten Slug hat.
        `…-more-markets → "England"` ist eindeutig."""
        self.assertTrue(U.aufloesbar(LEE_BRE, "Kevin Schade", "Kevin Schade"))
        self.assertTrue(U.aufloesbar("wc-quali-more-markets", "England", "England"))

    def test_der_slug_wird_auch_im_zusammengesetzten_key_erkannt(self):
        """Im Ledger steht der Slug als Teil von wallet|slug|side."""
        self.assertTrue(U.ist_buendel("0xabc|" + LEE_BRE + "|Over"))

    def test_muell_kippt_nicht(self):
        self.assertTrue(U.aufloesbar(None, None))
        self.assertFalse(U.ist_buendel(None))


class WalletRanglisteBleibtSauber(unittest.TestCase):
    """Der teuerste Ort. `wins/n` je Wallet ist die Trefferquote, und die entscheidet, wer
    ueberhaupt in den Public-Kanal darf (PUB_MIN_TR / PUB_MIN_HITRATE). Ein erfundener Treffer
    macht dort eine Wallet „scharf", die es nicht ist — und die pusht dann weiter."""

    def setUp(self):
        import poly_money_broad as M
        self.M = M

    def _markt(self, key, resolved_prices):
        return {"key": key, "resolved": True, "resolvedPrices": resolved_prices}

    def _offen(self, key, side):
        return {"open": {"0xw|%s|%s" % (key, side): {
            "wallet": "0xw", "key": key, "side": side, "firstPrice": 0.5, "lastPrice": 0.5,
            "entryPrice": 0.5, "usd": 40000, "firstTs": "2026-08-30T10:00:00+00:00"}},
            "scores": {}}

    def test_ein_buendel_markt_faellt_aus_der_wallet_wertung(self):
        out = self.M.update_wallet_track(
            self._offen(LEE_BRE, "Over"),
            [self._markt(LEE_BRE, {"Over": 1.0, "Under": 0.0})])
        self.assertEqual(out["scores"], {}, "weder Treffer noch Fehlschlag — die Wette ist nicht entscheidbar")
        self.assertEqual(out["open"], {}, "und sie bleibt auch nicht ewig offen liegen")

    def test_ein_normaler_markt_wird_weiterhin_gewertet(self):
        out = self.M.update_wallet_track(
            self._offen("epl-tot-new-2026-08-29", "Newcastle United FC"),
            [self._markt("epl-tot-new-2026-08-29",
                         {"Newcastle United FC": 1.0, "Tottenham Hotspur FC": 0.0})])
        s = out["scores"]["0xw"]
        self.assertEqual((s["n"], s["wins"]), (1, 1))
