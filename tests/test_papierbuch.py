#!/usr/bin/env python3
"""test_papierbuch.py — Auto-Trading aus, Messung an (20.09.2026).

Lucas: „ich bin dafuer wir stellen das Auto trading mal ab und schreiben es nur im Cockpit
mit ala paper trading."

Der Anlass ist ein Messproblem, nicht Vorsicht: der Fussball-Trader hat nach Monaten sechs
abgerechnete Zeilen, das 95-%-Band seiner 27 verkauften Trades reicht von -4,2 % bis
+9,6 %. Bis hierher endete ein deaktivierter Lauf mit `return` nach der Kandidatenliste —
„aus" hiess „wir erfahren nichts".
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import paper_settle as P  # noqa: E402
import manage_wm_poly_positions as M  # noqa: E402


def _papier(**kw):
    b = {"betKey": "96-111-Under 2.5 Tore", "home": "Toulouse", "away": "Le Havre",
         "homeId": "96", "awayId": "111", "market": "Under 2.5 Tore",
         "stake": 5.5, "polyPrice": 0.45, "status": "papier", "papier": True,
         "source": "papier"}
    b.update(kw)
    return b


class TestVerkaufsPL(unittest.TestCase):
    """20.09.2026 (Lucas: „ich hab den noch nie gruen gesehen als Position"). Nachgerechnet
    schlossen 14 von 27 verkauften WM-Trades gruen, zusammen +3,98 $ — nur stand das
    nirgends: bei `sold` wurde `sellPrice` geschrieben, aber nie `pnl`."""

    def test_gewinn_wird_gerechnet(self):
        # 5,50 $ zu 0,275 = 20 Shares; Verkauf zu 0,55 = 11,00 $ → +5,50
        self.assertEqual(M.verkaufs_pl({"polyPrice": 0.275, "sellPrice": 0.55, "stake": 5.5}), 5.5)

    def test_verlust_wird_gerechnet(self):
        self.assertEqual(M.verkaufs_pl({"polyPrice": 0.5, "sellPrice": 0.25, "stake": 5.5}), -2.75)

    def test_ohne_verkaufspreis_wird_nichts_erfunden(self):
        self.assertIsNone(M.verkaufs_pl({"polyPrice": 0.5, "sellPrice": None, "stake": 5.5}))
        self.assertIsNone(M.verkaufs_pl({"polyPrice": 0, "sellPrice": 0.5, "stake": 5.5}))
        self.assertIsNone(M.verkaufs_pl({"polyPrice": "x", "sellPrice": 0.5, "stake": 5.5}))

    def test_ein_einstieg_von_null_wird_nicht_geraten(self):
        """Ein Einstieg von 0 ist keine Wette, sondern eine kaputte Zeile. Wer hier einen
        Ersatzpreis einsetzt, erfindet einen P/L — fehlende Information darf nicht als
        harmloser Default rendern."""
        self.assertIsNone(M.verkaufs_pl({"polyPrice": 0, "entryAsk": 0,
                                         "sellPrice": 0.5, "stake": 5.5}))
        self.assertIsNone(M.verkaufs_pl({"polyPrice": -0.2, "sellPrice": 0.5, "stake": 5.5}))
        self.assertIsNone(M.verkaufs_pl({"polyPrice": 0.5, "sellPrice": 0.6, "stake": 0}))

    def test_nachbuchen_ist_idempotent(self):
        d = {"bets": [{"status": "sold", "polyPrice": 0.5, "sellPrice": 0.6, "stake": 5.5}]}
        self.assertEqual(M.verkaeufe_nachbuchen(d), 1)
        self.assertEqual(M.verkaeufe_nachbuchen(d), 0)
        self.assertEqual(d["bets"][0]["pnlSource"], "sell")

    def test_ein_vorhandener_pl_wird_nicht_ueberschrieben(self):
        """`closed_manual` traegt den ECHTEN P/L aus dem Wallet-Trade. Wer den mit einer
        Schaetzung aus `sellPrice` ueberbuegelt, faelscht die Bilanz."""
        d = {"bets": [{"status": "sold", "polyPrice": 0.5, "sellPrice": 0.6,
                       "stake": 5.5, "pnl": 9.99}]}
        self.assertEqual(M.verkaeufe_nachbuchen(d), 0)
        self.assertEqual(d["bets"][0]["pnl"], 9.99)

    def test_offene_wetten_bekommen_keinen_pl(self):
        d = {"bets": [{"status": "placed", "polyPrice": 0.5, "sellPrice": 0.6, "stake": 5.5}]}
        self.assertEqual(M.verkaeufe_nachbuchen(d), 0)

    def test_gegen_den_echten_bestand(self):
        """Die Zahl aus der Untersuchung muss reproduzierbar sein, sonst ist sie eine
        Behauptung: 27 verkaufte WM-Trades, zusammen rund +4 $."""
        d = json.loads((REPO / "wm_auto_bets_placed.json").read_text(encoding="utf-8"))
        n = M.verkaeufe_nachbuchen(d)
        pl = sum(b["pnl"] for b in d["bets"] if b.get("pnlSource") == "sell")
        self.assertGreaterEqual(n + sum(1 for b in d["bets"]
                                        if b.get("pnlSource") == "sell"), 20)
        self.assertGreater(pl, 0.0, "die verkauften Trades waren in Summe NICHT negativ")


class TestPapierAbrechnung(unittest.TestCase):
    def _fns(self, ergebnis="WIN"):
        return (lambda bet, res: ergebnis), (lambda bet, r: 6.72 if r == "WIN" else -5.5)

    def test_eine_papierzeile_wird_abgerechnet(self):
        bets = [_papier()]
        det, pnl = self._fns("WIN")
        neu, pending = P.abrechnen(bets, {"96-111": {"x": 1}}, det, pnl)
        self.assertEqual((neu, pending), (1, 0))
        self.assertEqual(bets[0]["result"], "WIN")
        self.assertEqual(bets[0]["pnl"], 6.72)
        self.assertIn("resolvedAt", bets[0])

    def test_ohne_spielergebnis_bleibt_sie_offen(self):
        bets = [_papier()]
        det, pnl = self._fns()
        self.assertEqual(P.abrechnen(bets, {}, det, pnl), (0, 1))
        self.assertNotIn("result", bets[0])

    def test_abrechnen_ist_idempotent(self):
        bets = [_papier()]
        det, pnl = self._fns("LOSS")
        P.abrechnen(bets, {"96-111": {"x": 1}}, det, pnl)
        erst = bets[0]["resolvedAt"]
        self.assertEqual(P.abrechnen(bets, {"96-111": {"x": 1}}, det, pnl), (0, 0))
        self.assertEqual(bets[0]["resolvedAt"], erst)

    def test_keine_auswahl_nach_ausgang(self):
        """Jede Zeile mit Ergebnis wird gebucht — auch die verlorenen. Wer nur die
        abrechnet, die zufaellig ein Ergebnis bekommen haben, misst den Filter."""
        bets = [_papier(betKey="a"), _papier(betKey="b", homeId="1", awayId="2")]
        det, pnl = self._fns("LOSS")
        neu, pending = P.abrechnen(bets, {"96-111": {"x": 1}, "1-2": {"x": 1}}, det, pnl)
        self.assertEqual((neu, pending), (2, 0))
        self.assertTrue(all(b["result"] == "LOSS" for b in bets))


class TestBilanz(unittest.TestCase):
    def test_zahlen_stimmen(self):
        bets = [_papier(result="WIN", pnl=6.72), _papier(result="LOSS", pnl=-5.5), _papier()]
        b = P.bilanz(bets)
        self.assertEqual((b["n"], b["abgerechnet"], b["offen"], b["gewonnen"]), (3, 2, 1, 1))
        self.assertEqual(b["einsatz"], 11.0)
        self.assertEqual(b["pl"], 1.22)

    def test_je_markt_getrennt(self):
        """Die offene Frage ist genau diese: 7 von 7 Liga-Wetten waren `Under 2.5 Tore`.
        Eine Gesamtzahl beantwortet sie nicht."""
        bets = [_papier(result="WIN", pnl=6.72),
                _papier(market="Over 2.5 Tore", result="LOSS", pnl=-5.5)]
        b = P.bilanz(bets)
        self.assertEqual(sorted(b["jeMarkt"]), ["Over 2.5 Tore", "Under 2.5 Tore"])
        self.assertEqual(b["jeMarkt"]["Under 2.5 Tore"]["gewonnen"], 1)

    def test_kleine_stichprobe_bekommt_kein_urteil(self):
        """Ein Punktschaetzer entscheidet nichts. Bei n unter 100 heisst es 'nicht belegt',
        egal wie schoen die Rendite aussieht."""
        b = P.bilanz([_papier(result="WIN", pnl=99.0)])
        self.assertEqual(b["urteil"], "nicht belegt")
        b2 = P.bilanz([_papier(result="WIN", pnl=1.0) for _ in range(100)])
        self.assertEqual(b2["urteil"], "messbar")

    def test_leeres_buch_stuerzt_nicht(self):
        b = P.bilanz([])
        self.assertEqual(b["abgerechnet"], 0)
        self.assertIsNone(b["roiPct"])


class TestTriggerUndWorkflows(unittest.TestCase):
    def test_der_deaktivierte_lauf_steigt_nicht_mehr_aus(self):
        """Vor diesem Commit stand hier ein `return` — 'aus' hiess 'wir erfahren nichts'."""
        q = (REPO / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        self.assertNotIn("DEAKTIVIERT — {len(candidates)} Bet(s) würden platziert", q)
        self.assertIn("papier = not is_enabled", q)

    def test_papier_platziert_keine_order(self):
        q = (REPO / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        i = q.index("if papier:")
        j = q.index("place_order_with_retry(", i)
        # zwischen dem Papier-Zweig und dem Order-Aufruf muss ein else stehen
        self.assertIn("else:", q[i:j])
        self.assertIn('"status": "papier"', q[i:j])

    def test_papier_landet_nicht_im_echten_wettbuch(self):
        """Positions-Manager, Resolver, Bilanz und Wallet-Abgleich lesen alle das echte
        Buch. Eine Papier-Zeile, die dort als offene Position durchrutscht, waere
        schlimmer als gar kein Papierbuch."""
        q = (REPO / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        self.assertIn("PAPIER_FILE", q)
        block = q[q.index("if papier:", q.index("# 5. Ergebnisse speichern")):]
        self.assertIn("save_json(PAPIER_FILE", block)
        self.assertLess(block.index("return"), block.find("save_json(PLACED_FILE")
                        if "save_json(PLACED_FILE" in block else len(block))

    def test_dedup_kennt_auch_das_papierbuch(self):
        """Sonst schriebe jeder Lauf dieselbe Papier-Wette erneut — alle 30 Minuten eine."""
        q = (REPO / "auto_wm_poly_trigger.py").read_text(encoding="utf-8")
        self.assertIn("placed_keys |= {b[\"betKey\"] for b in papier_bets", q)

    def test_liga_trigger_steht_auf_papier(self):
        y = (REPO / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertIn("LIGA_AUTO_TRIGGER_ENABLED || 'false'", y)

    def test_auto_sell_bleibt_an(self):
        """Wer den Verkauf mit abschaltet, nimmt genau den Mechanismus weg, dessen Ausfall
        Toulouse–Le Havre ins Spiel laufen liess. Es liegen noch echte Positionen."""
        y = (REPO / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertIn("LIGA_AUTO_SELL_ENABLED || 'true'", y)

    def test_das_papierbuch_wird_ueberall_abgerechnet_und_committet(self):
        for ds in ("liga", "mls", "wm"):
            y = (REPO / (".github/workflows/manage-%s-poly.yml" % ds)).read_text(encoding="utf-8")
            self.assertIn("paper_settle.py", y, ds)
        for ds in ("liga", "mls"):
            y = (REPO / (".github/workflows/manage-%s-poly.yml" % ds)).read_text(encoding="utf-8")
            self.assertIn("%s_paper_bets.json" % ds, y.split("Status speichern")[-1], ds)
        reg = (REPO / "state_files_registry.json").read_text(encoding="utf-8")
        self.assertIn("wm_paper_bets.json", reg)


if __name__ == "__main__":
    unittest.main()
