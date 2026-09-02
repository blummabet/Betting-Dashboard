#!/usr/bin/env python3
"""Tests fuer poly_public_eval.py — die Abrechnung der oeffentlichen Whale-Pushs.

02.09.2026 (Lucas: „Schaffst du irgendwie die Polymarket pushes auch auszuwerten die in diesen
Channel kommen?"). Was hier festgenagelt wird, ist weniger die Rechnung als die Ehrlichkeit:
ein Push ohne Preis darf keinen ROI erfinden, ein Push ohne Aufloesung darf nicht still
verschwinden, und rueckwirkend rekonstruierte Zeilen duerfen NIE ins Vorwaerts-Buch zaehlen.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_public_eval as PE


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _e(k="0xa|m1|Home", key="m1", side="Home", price=0.50, sent=None, **kw):
    e = {"k": k, "key": key, "side": side, "pushPrice": price,
         "sentAt": (sent or NOW - timedelta(hours=2)).isoformat(), "status": "pending",
         "cat": "Fußball", "usd": 30000.0}
    e.update(kw)
    return e


class WilsonTest(unittest.TestCase):
    def test_null_ist_kein_vorteil(self):
        self.assertEqual(PE.wilson_lb(0, 0), 0.0)

    def test_untergrenze_liegt_unter_punktschaetzer(self):
        self.assertLess(PE.wilson_lb(9, 10), 0.9)

    def test_untergrenze_waechst_mit_n(self):
        self.assertLess(PE.wilson_lb(6, 10), PE.wilson_lb(60, 100))


class SettleTest(unittest.TestCase):
    def test_treffer_zahlt_gewinn_zum_pushpreis(self):
        out = PE.settle([_e(price=0.50)], {"m1": {"winner": "Home"}}, {}, now=NOW)
        self.assertEqual(out[0]["result"], "win")
        self.assertEqual(out[0]["pnl"], 10.0)          # 10/0.50 - 10

    def test_niederlage_verliert_den_einsatz(self):
        out = PE.settle([_e(price=0.50)], {"m1": {"winner": "Away"}}, {}, now=NOW)
        self.assertEqual(out[0]["result"], "loss")
        self.assertEqual(out[0]["pnl"], -10.0)

    def test_kein_preis_zaehlt_treffer_aber_kein_geld(self):
        """Der Kern: rueckwirkende Zeilen haben keinen Push-Preis. Sie duerfen die Trefferquote
        fuellen, aber niemals einen erfundenen Einstieg in den ROI tragen."""
        out = PE.settle([_e(price=None)], {"m1": {"winner": "Home"}}, {}, now=NOW)
        self.assertEqual(out[0]["result"], "win")
        self.assertIsNone(out[0]["pnl"])
        self.assertIsNone(out[0]["stake"])
        self.assertIsNone(out[0]["clvPP"])

    def test_clv_gegen_schlusskurs(self):
        close = {"m1": {"prices": {"Home": 0.60}}}
        out = PE.settle([_e(price=0.50)], {"m1": {"winner": "Home"}}, close, now=NOW)
        self.assertEqual(out[0]["clvPP"], 10.0)

    def test_ohne_schlusskurs_ist_clv_null_nicht_erfunden(self):
        out = PE.settle([_e(price=0.50)], {"m1": {"winner": "Home"}}, {}, now=NOW)
        self.assertEqual(out[0]["clvPP"], 0.0)

    def test_offen_bleibt_offen_solange_keine_aufloesung(self):
        out = PE.settle([_e()], {}, {}, now=NOW)
        self.assertEqual(out[0]["status"], "pending")

    def test_alt_und_unaufgeloest_wird_sichtbar_unaufloesbar(self):
        alt = _e(sent=NOW - timedelta(days=PE.PENDING_TTL_D + 1))
        out = PE.settle([alt], {}, {}, now=NOW)
        self.assertEqual(out[0]["status"], "unaufloesbar")
        self.assertIn("ageDays", out[0])

    def test_abgerechnet_bleibt_abgerechnet(self):
        fertig = _e(status="settled", result="win", pnl=10.0)
        out = PE.settle([fertig], {"m1": {"winner": "Away"}}, {}, now=NOW)
        self.assertEqual(out[0]["result"], "win")      # NICHT nachbewertet

    def test_muell_zeilen_fliegen_raus_ohne_absturz(self):
        out = PE.settle([None, "x", _e()], {}, {}, now=NOW)
        self.assertEqual(len(out), 1)


class BilanzTest(unittest.TestCase):
    def test_leer_liefert_keine_erfundene_quote(self):
        b = PE.bilanz([])
        self.assertEqual(b["n"], 0)
        self.assertIsNone(b["hit"])
        self.assertIsNone(b["roi"])

    def test_trefferquote_ueber_alle_roi_nur_ueber_bepreiste(self):
        rows = [
            {"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 1.0},
            {"result": "win", "stake": None, "pnl": None, "clvPP": None},   # ohne Preis
            {"result": "loss", "stake": 10.0, "pnl": -10.0, "clvPP": -1.0},
        ]
        b = PE.bilanz(rows)
        self.assertEqual((b["n"], b["wins"]), (3, 2))
        self.assertEqual(b["nOhnePreis"], 1)
        self.assertEqual(b["stake"], 20.0)             # die preislose Zeile traegt kein Geld
        self.assertEqual(b["roi"], 0.0)

    def test_untergrenze_ist_gesetzt_und_kleiner(self):
        b = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0}] * 5)
        self.assertLess(b["hitUg"], b["hit"])

    def test_clv_untergrenze_erst_ab_zwei_werten(self):
        einer = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0}])
        self.assertIsNone(einer["clvUg"])
        zwei = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0},
                          {"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0}])
        self.assertEqual(zwei["clvUg"], 3.0)           # keine Streuung → UG = Mittel

    def test_bilanz_nach_gruppiert_und_faengt_leerwerte(self):
        rows = [{"result": "win", "cat": "Fußball", "stake": 10.0, "pnl": 10.0},
                {"result": "loss", "cat": None, "stake": 10.0, "pnl": -10.0}]
        by = PE.bilanz_nach(rows, "cat")
        self.assertEqual(by["Fußball"]["n"], 1)
        self.assertEqual(by["?"]["n"], 1)


class ReportTest(unittest.TestCase):
    def test_retro_zaehlt_nie_ins_vorwaerts_buch(self):
        led = [_e(k="a", status="settled", result="win", stake=10.0, pnl=10.0),
               _e(k="b", status="settled", result="win", stake=None, pnl=None, quelle="retro")]
        r = PE.report(led, now=NOW)
        self.assertEqual(r["agg"]["n"], 1)
        self.assertEqual(r["retro"]["n"], 1)
        self.assertEqual(r["retro"]["agg"]["n"], 1)

    def test_offen_und_unaufloesbar_stehen_getrennt_im_kopf(self):
        led = [_e(k="a"), _e(k="b", status="unaufloesbar"),
               _e(k="c", status="settled", result="win", stake=10.0, pnl=10.0)]
        r = PE.report(led, now=NOW)
        self.assertEqual((r["gesamt"], r["offen"], r["unaufloesbar"]), (3, 1, 1))

    def test_leerer_ledger_kippt_nicht(self):
        r = PE.report([], now=NOW)
        self.assertEqual(r["gesamt"], 0)
        self.assertIsNone(r["startAb"])


class LedgerSchreiberTest(unittest.TestCase):
    """Der Schreiber sitzt in poly_whale_watch.py — hier nur die Preis-Wahl, die der ganzen
    Auswertung zugrunde liegt: der Leser bekommt den AKTUELLEN Kurs, nicht den alten Whale-Einstieg."""

    def test_push_preis_bevorzugt_den_aktuellen_kurs(self):
        import poly_whale_watch as W
        self.assertEqual(W._push_price({"firstPrice": 0.40, "lastPrice": 0.52}), 0.52)

    def test_push_preis_faellt_auf_ersteinstieg_zurueck(self):
        import poly_whale_watch as W
        self.assertEqual(W._push_price({"firstPrice": 0.40}), 0.40)

    def test_push_preis_verweigert_unsinn(self):
        import poly_whale_watch as W
        self.assertIsNone(W._push_price({}))
        self.assertIsNone(W._push_price({"lastPrice": "x"}))
        self.assertIsNone(W._push_price({"lastPrice": 1.0}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
