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

    def test_zwei_gleiche_werte_ergeben_KEINE_untergrenze(self):
        """Dieser Test stand hier vorher andersherum — und war der Fehler.

        Er behauptete „keine Streuung → UG = Mittel" und nagelte damit genau die Krankheit
        fest, die freigabe.untergrenze am 03.09. behandelt hat: zwei oder drei aehnliche Werte
        haben eine Streuung nahe null, die Schranke faellt auf den Punktschaetzer zusammen, und
        heraus kommt ein Mittelwert mit dem Etikett „UG". Im gespeicherten Record stand deshalb
        clvUg: -0.65 aus n=3. Eine Untergrenze aus drei Werten ist keine Untergrenze.
        """
        einer = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0}])
        self.assertIsNone(einer["clvUg"])
        zwei = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0}] * 2)
        self.assertIsNone(zwei["clvUg"], "n=2 traegt keine Schranke, egal wie eng die Werte liegen")
        viele = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0, "clvPP": 3.0}] * 40)
        self.assertEqual(viele["clvUg"], 3.0)          # ab n=30 gibt es eine Zahl


class RuecknahmeUndKorrekturTest(unittest.TestCase):
    """04.09.2026 — Lucas hat einen Push nachgeschlagen, den unser Buch falsch hatte.

    „💰 $41K auf Over" auf Leeds–Brentford, Endstand 1:1, Markt Over 2,5 → verloren. Im Buch
    stand ein Treffer, weil poly_resolutions.json fuer den Buendel-Slug pauschal „Over" meldet.

    Zwei Regeln werden hier festgehalten, und die zweite ist die heiklere:
      1. Ein Ergebnis auf untragfaehiger Basis wird ZURUECKGENOMMEN — auch nachtraeglich.
      2. Eine Korrektur von Hand darf NUR eintragen, wo die Maschine nichts weiss. Sonst waere
         das Buch nicht mehr vorwaerts-gerichtet, sondern nachtraeglich zurechtgelegt.
    """

    LEE = "epl-lee-bre-2026-08-30-more-markets"

    def _gebucht(self, **kw):
        d = {"k": "0xw|" + self.LEE + "|Over", "key": self.LEE, "side": "Over",
             "sentAt": (NOW - timedelta(days=5)).isoformat(), "status": "settled",
             "result": "win", "winner": "Over", "stake": 10.0, "pnl": 9.0, "cat": "Fußball"}
        d.update(kw)
        return d

    def test_ein_treffer_auf_untragfaehiger_basis_wird_zurueckgenommen(self):
        out = PE.settle([self._gebucht()], {}, {}, now=NOW)[0]
        self.assertEqual(out["status"], "unaufloesbar")
        self.assertIsNone(out.get("result"))
        self.assertIsNone(out.get("pnl"), "auch das Geld faellt weg, nicht nur das Etikett")
        self.assertEqual(out["zurueckgenommen"]["war"], "win")

    def test_die_ruecknahme_passiert_nur_einmal(self):
        """Sonst nimmt der naechste Lauf die Korrektur wieder zurueck und `war` protokolliert
        am Ende die Korrektur statt des Fehlers."""
        e = self._gebucht()
        for _ in range(3):
            e = PE.settle([e], {}, {}, now=NOW)[0]
        self.assertEqual(e["zurueckgenommen"]["war"], "win")

    def test_ein_sauber_abgerechnetes_ergebnis_bleibt_unangetastet(self):
        e = {"key": "cs2-mibr-eye-2026-09-03", "side": "MIBR", "status": "settled",
             "result": "win", "winner": "MIBR", "stake": 10.0, "pnl": 3.61}
        out = PE.settle([e], {}, {}, now=NOW)[0]
        self.assertEqual(out["result"], "win")
        self.assertNotIn("zurueckgenommen", out)

    def test_ein_buendel_push_wird_gar_nicht_erst_abgerechnet(self):
        offen = {"key": self.LEE, "side": "Over", "status": "pending",
                 "sentAt": (NOW - timedelta(hours=2)).isoformat(), "pushPrice": 0.52}
        out = PE.settle([offen], {self.LEE: {"winner": "Over"}}, {}, now=NOW)[0]
        self.assertEqual(out["status"], "pending", "kein erfundener Treffer")
        self.assertIn("Buendel", out.get("nichtAufloesbarGrund", ""))

    # ── Die Korrektur und ihre Grenzen ──────────────────────────────────────
    KORR = {"result": "loss", "quelle": "Lucas, 04.09.2026", "warum": "Markt war Over 2,5, 1:1"}

    def test_ein_nachgeprueftes_ergebnis_kommt_ins_buch(self):
        """Den bekannten Verlust wegzulassen waere die schlechtere Wahl: ohne ihn stuende das
        Buch bei 12:1 statt 12:2 — Weglassen schoent."""
        e = self._gebucht()
        out = PE.settle([e], {}, {}, now=NOW, korrekturen={e["k"]: self.KORR})[0]
        self.assertEqual(out["status"], "settled")
        self.assertEqual(out["result"], "loss")
        self.assertEqual(out["korrigiert"]["quelle"], "Lucas, 04.09.2026")

    def test_eine_korrektur_kann_ein_maschinelles_ergebnis_NIE_ueberschreiben(self):
        """Die wichtigste Grenze. Sonst waere das hier eine Hintertuer, um nachtraeglich
        Treffer einzutragen — genau das, was ueberall sonst verboten ist."""
        sauber = {"key": "cs2-mibr-eye-2026-09-03", "k": "x", "side": "MIBR",
                  "status": "settled", "result": "win", "winner": "MIBR"}
        out = PE.settle([sauber], {}, {}, now=NOW,
                        korrekturen={"x": {"result": "loss", "quelle": "wer", "warum": "warum"}})[0]
        self.assertEqual(out["result"], "win")
        self.assertNotIn("korrigiert", out)

    def test_ohne_herkunft_keine_korrektur(self):
        e = self._gebucht()
        for unvollstaendig in ({"result": "loss"},
                               {"result": "loss", "quelle": "Lucas"},
                               {"result": "loss", "warum": "weil"}):
            out = PE.settle([e], {}, {}, now=NOW, korrekturen={e["k"]: unvollstaendig})[0]
            self.assertEqual(out["status"], "unaufloesbar", unvollstaendig)

    def test_unsinniges_ergebnis_wird_nicht_uebernommen(self):
        e = self._gebucht()
        out = PE.settle([e], {}, {}, now=NOW,
                        korrekturen={e["k"]: {"result": "vielleicht", "quelle": "x", "warum": "y"}})[0]
        self.assertEqual(out["status"], "unaufloesbar")

    def test_mit_nachgetragenem_preis_zaehlt_die_korrektur_auch_geld(self):
        e = self._gebucht()
        k = dict(self.KORR, preis=0.52)
        out = PE.settle([e], {}, {}, now=NOW, korrekturen={e["k"]: k})[0]
        self.assertEqual(out["pnl"], -10.0)
        self.assertEqual(out["stake"], 10.0)

    def test_korrekturen_stehen_getrennt_im_report(self):
        e = self._gebucht(quelle=None)
        led = PE.settle([e], {}, {}, now=NOW, korrekturen={e["k"]: self.KORR})
        rep = PE.report(led, now=NOW)
        self.assertEqual(rep["korrigiert"], 1)
        self.assertEqual(rep["zurueckgenommen"], 1)


class GeldUrteilTest(unittest.TestCase):
    """04.09.2026 — dieselbe Lehre, die heute stake_analyse.py umgebaut hat, hier festgenagelt:

        EINE TREFFERQUOTE OHNE DIE PREISE IST KEINE ZAHL.

    Das Buch gab bisher hit/hitUg aus und daneben einen ROI ohne Schranke. Der Retro-Block
    zeigte 91% Treffer auf n=11, waehrend bei ALLEN elf der Einstiegspreis fehlte — daraus ist
    keine Rendite berechenbar, und die Trefferquote sagt darueber nichts.
    """

    def _wins(self, n, pnl=10.0):
        return [{"result": "win", "stake": 10.0, "pnl": pnl, "clvPP": 1.0}] * n

    def test_belegt_haengt_an_der_rendite_nicht_an_der_trefferquote(self):
        """40 Favoritensiege zu 0,93: makellose Quote, und trotzdem Geld verloren."""
        rows = [{"result": "win", "stake": 10.0, "pnl": 0.75}] * 36 + \
               [{"result": "loss", "stake": 10.0, "pnl": -10.0}] * 4
        b = PE.bilanz(rows)
        self.assertEqual(b["hit"], 0.9)
        self.assertGreater(b["hitUg"], 0.5, "die Trefferquote sieht glaenzend aus")
        self.assertLess(b["roi"], 0, "und trotzdem ist Geld weg")
        self.assertFalse(b["belegt"], "belegt darf NIE aus der Trefferquote kommen")

    def test_belegt_wird_gesetzt_wenn_die_rendite_untergrenze_ueber_null_liegt(self):
        b = PE.bilanz(self._wins(40))
        self.assertIsNotNone(b["roiUg"])
        self.assertGreater(b["roiUg"], 0)
        self.assertTrue(b["belegt"])

    def test_kleine_stichprobe_bekommt_keine_rendite_untergrenze(self):
        """Der reale Stand am 04.09.: drei Pushs, alle getroffen, ROI +58%. Das ist ein
        Punktschaetzer, kein Beleg — und muss auch so dastehen."""
        b = PE.bilanz(self._wins(3, pnl=5.84))
        self.assertGreater(b["roi"], 0.5)
        self.assertIsNone(b["roiUg"], "unter n=30 gibt es keine Schranke")
        self.assertFalse(b["belegt"])

    def test_ohne_preis_gibt_es_kein_geldurteil(self):
        rows = [{"result": "win", "stake": None, "pnl": None}] * 10 + \
               [{"result": "loss", "stake": None, "pnl": None}]
        b = PE.bilanz(rows)
        self.assertEqual(b["hit"], round(10 / 11, 4))
        self.assertEqual(b["nOhnePreis"], 11)
        self.assertFalse(b["geldurteil"], "bei keiner Zeile ist ein Einstieg bekannt")
        self.assertIsNone(b["roi"])
        self.assertIsNone(b["roiUg"])
        self.assertFalse(b["belegt"])

    def test_geldurteil_sobald_wenigstens_eine_zeile_einen_preis_hat(self):
        b = PE.bilanz([{"result": "win", "stake": 10.0, "pnl": 10.0},
                       {"result": "win", "stake": None, "pnl": None}])
        self.assertTrue(b["geldurteil"])
        self.assertEqual(b["nOhnePreis"], 1)

    def test_leere_bilanz_ist_nicht_belegt(self):
        b = PE.bilanz([])
        self.assertFalse(b["belegt"])
        self.assertFalse(b["geldurteil"])
        self.assertIsNone(b["roiUg"])

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
