"""De-Vigging und der Value-Scanner — 07.09.2026.

Lucas: „wir brauchen eine Lösung, um mehr Edge zu generieren."

Der Ansatz mit der besten Evidenz für jemanden, der Pinnacle NICHT schlagen will: Pinnacle
entvigen, gegen die BESTE verfügbare Quote halten, spielen wo der Bestpreis über fair liegt.
(Buchdahl: 111.909 Quotenpaare, +2,51 % über alle Value-Wetten, +5,71 % ab Schwelle 2 %.
Kaunitz et al. 2017, peer-reviewed: 56.435 Wetten Backtest ROI 3,5 %, Echtgeld 265 Wetten 8,5 %.)

Warum es bei uns nie ging, gemessen an 264 eigenen Spielen: `soft_consensus()` schrieb den
MEDIAN von 29 Büchern. Der lag 6,2–6,7 % UNTER dem fairen Preis und in 0,3 % der Fälle darüber.
Wir haben 29 Bücher geholt und 28 weggeworfen.
"""
import unittest

import devig as D
import wert_scanner as W


class TestDeVigVerfahren(unittest.TestCase):
    def test_alle_verfahren_summieren_auf_eins(self):
        for q in ([1.25, 6.50, 13.00], [1.95, 1.98], [2.0, 3.4, 3.9], [1.10, 12.0, 26.0]):
            for v in D.VERFAHREN:
                p = D.entvigen(q, v)
                if p is None:
                    continue
                self.assertAlmostEqual(sum(p), 1.0, places=6, msg="%s %s" % (v, q))

    def test_faire_quoten_liegen_ueber_den_rohen(self):
        """Entvigen macht Quoten laenger, nie kuerzer — sonst waere die Marge negativ."""
        q = [2.0, 3.4, 3.9]
        for v in D.VERFAHREN:
            p = D.entvigen(q, v)
            if p is None:
                continue
            for i in range(3):
                self.assertGreater(1.0 / p[i], q[i] - 1e-9, "%s Ausgang %d" % (v, i))

    def test_bei_zwei_wegen_sind_alle_verfahren_praktisch_gleich(self):
        """Der Befund, der die ganze Methodendiskussion fuer Ü/U gegenstandslos macht."""
        s = D.streuung([1.95, 1.98])
        self.assertLess(max(s), 0.1, "bei n=2 duerfen die Verfahren nicht auseinanderlaufen")

    def test_bei_drei_wegen_entscheidet_das_verfahren_ueber_den_aussenseiter(self):
        """1,25/6,50/13,00: faire Aussenseiter-Quote multiplikativ 13,40 vs Shin 14,54.
        Das ist das Zwei- bis Vierfache einer typischen Value-Schwelle."""
        s = D.streuung([1.25, 6.50, 13.00])
        self.assertLess(s[0], 3.0, "beim Favoriten ist die Wahl fast egal")
        self.assertGreater(s[2], 5.0, "beim Aussenseiter ist sie es NICHT")

    def test_multiplikativ_ist_beim_aussenseiter_am_optimistischsten(self):
        """Genau deshalb erzeugt es dort Scheinvalue: es verteilt die Marge gleichmaessig,
        obwohl sie messbar auf den langen Quoten liegt (Whelan, 84.230 Spiele: ~3 % Verlust
        bei den kuerzesten, ~17 % bei den laengsten Quoten)."""
        q = [1.25, 6.50, 13.00]
        m = D.entvigen(q, "multiplikativ")[2]
        for v in ("shin", "power", "additiv", "oddsRatio"):
            self.assertLess(D.entvigen(q, v)[2], m,
                            "%s muesste dem Aussenseiter WENIGER Wahrscheinlichkeit geben" % v)

    def test_fair_waehlt_nach_marktgroesse(self):
        self.assertEqual(D.fair([1.95, 1.98]), D.entvigen([1.95, 1.98], "multiplikativ"))
        self.assertEqual(D.fair([1.25, 6.5, 13.0]), D.entvigen([1.25, 6.5, 13.0], "shin"))

    def test_muell_wird_nicht_gerechnet(self):
        for q in ([], [1.9], [0.5, 2.0], [1.9, None], ["x", "y"], [1.0, 2.0]):
            self.assertIsNone(D.fair(q), repr(q))

    def test_additiv_erfindet_keine_negative_wahrscheinlichkeit(self):
        """Bei langen Quoten wird additiv negativ. Dann lieber None als eine Zahl, die es
        nicht gibt."""
        p = D.entvigen([1.02, 40.0, 90.0], "additiv")
        self.assertTrue(p is None or all(x > 0 for x in p))

    def test_verfahren_sind_deterministisch(self):
        q = [1.25, 6.5, 13.0]
        self.assertEqual(D.entvigen(q, "shin"), D.entvigen(q, "shin"))


class TestWertScanner(unittest.TestCase):
    def _row(self, faktor=1.06, buecher=29):
        r = {"hw": 2.00, "dr": 3.40, "aw": 3.90, "o25": 1.90, "u25": 1.95}
        for f in list(r):
            r["best_" + f] = round(r[f] * faktor, 3)
            r["bestBook_" + f] = "unibet"
            r["nBooks_" + f] = buecher
        return r

    def test_ein_klarer_bestpreis_wird_gefunden(self):
        f = W.funde(self._row(1.08))
        self.assertTrue(f)
        self.assertTrue(all(x["edgePct"] > 100 * W.SCHWELLE for x in f))
        self.assertTrue(all(x["buch"] == "unibet" for x in f))

    def test_ein_bestpreis_auf_pinnacle_niveau_ergibt_nichts(self):
        """Der Normalfall. Findet der Scanner hier etwas, rechnet er falsch."""
        self.assertEqual(W.funde(self._row(1.00)), [])

    def test_unter_der_schwelle_wird_nichts_gemeldet(self):
        self.assertEqual(W.funde(self._row(1.01)), [])

    def test_zu_wenige_buecher_zaehlen_nicht(self):
        """Aus einem einzigen Buch ist „das Maximum" derselbe Preis mit besserem Namen —
        und ein Ausreisser-Buch wuerde Scheinvalue erzeugen."""
        self.assertEqual(W.funde(self._row(1.08, buecher=2)), [])

    def test_fehlende_buecherzahl_ist_keine_erlaubnis(self):
        r = {k: v for k, v in self._row(1.08).items() if not k.startswith("nBooks_")}
        self.assertEqual(W.funde(r), [])

    def test_longshots_bleiben_draussen(self):
        """Dort ist die De-Vig am unsichersten (Streuung bis 12 %) — genau da darf der
        Scanner nicht am lautesten sein."""
        r = {"hw": 1.13, "dr": 11.0, "aw": 40.0}
        for f in ("hw", "dr", "aw"):
            r["best_" + f] = round(r[f] * 1.10, 3)
            r["bestBook_" + f] = "x"
            r["nBooks_" + f] = 29
        self.assertTrue(all(x["bestQuote"] <= W.MAX_QUOTE for x in W.funde(r)))

    def test_jeder_fund_traegt_seine_streuung_und_sein_robust(self):
        for f in W.funde(self._row(1.08)):
            self.assertIn("streuungPct", f)
            self.assertIn("robust", f)
            self.assertIsInstance(f["robust"], bool)

    def test_robust_faellt_wenn_der_fund_nur_an_einem_verfahren_haengt(self):
        """Der Kern der Ehrlichkeit hier: ein Flag, das nur unter multiplikativem De-Vigging
        steht, ist ein Artefakt der Rechenvorschrift und kein Pick."""
        r = {"hw": 1.25, "dr": 6.50, "aw": 13.00}
        # Bestpreis knapp ueber der multiplikativ-fairen Aussenseiterquote (13,40), aber unter
        # der Shin-fairen (14,54) -> darf nicht als robust gelten.
        r["best_aw"], r["bestBook_aw"], r["nBooks_aw"] = 13.60, "x", 29
        f = [x for x in W.funde(r, schwelle=-1.0) if x["seite"] == "Auswärts"]
        self.assertTrue(f)
        self.assertFalse(f[0]["robust"])

    def test_ein_leerer_bestand_meldet_die_rollout_luecke_statt_null_funde(self):
        d = W.baue()
        self.assertIn("spieleMitBestpreis", d)
        self.assertIn("spieleGeprueft", d)
        self.assertGreaterEqual(d["spieleGeprueft"], 0)

    def test_abgeschlossene_spiele_stehen_nicht_mehr_drin(self):
        daten = {"odds": {"1-2": self._row(1.08)},
                 "groups": {"g": {"name": "L", "fixtures": [
                     {"home": "1", "away": "2", "homeName": "A", "awayName": "B",
                      "result": {"status": "FT", "home_score": 1, "away_score": 0}}]}}}
        self.assertEqual(W.scan(daten), [])


class TestBestpreisErfassung(unittest.TestCase):
    """Die Erfassung selbst — ohne sie ist der Scanner ein leeres Versprechen."""

    def _bk(self, key, hw, dr, aw):
        return {"key": key, "markets": [{"key": "h2h", "outcomes": [
            {"name": "Heim", "price": hw}, {"name": "Draw", "price": dr},
            {"name": "Gast", "price": aw}]}]}

    def test_das_maximum_wird_erfasst_und_das_buch_dazu(self):
        import fetch_liga_odds as F
        pub, books, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("unibet_eu", 2.15, 3.30, 3.95),
             self._bk("williamhill", 2.02, 3.60, 4.10)], "Heim", "Gast")
        self.assertEqual(pub["best_hw"], 2.15)
        self.assertEqual(pub["bestBook_hw"], "unibet_eu")
        self.assertEqual(pub["best_aw"], 4.10)
        self.assertEqual(pub["bestBook_aw"], "williamhill")
        self.assertEqual(pub["nBooks_hw"], 3)

    def test_der_median_bleibt_unveraendert_daneben_stehen(self):
        """Er faehrt alle bestehenden Vergleiche weiter — der Bestpreis kommt DAZU,
        er ersetzt nichts."""
        import fetch_liga_odds as F
        pub, _, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80), self._bk("unibet_eu", 2.15, 3.30, 3.95),
             self._bk("bwin", 2.02, 3.60, 4.10)], "Heim", "Gast")
        self.assertEqual(pub["public_hw"], 2.05)

    def test_das_sharp_buch_faellt_nicht_in_den_soft_konsens(self):
        import fetch_liga_odds as F
        pub, books, _, _ = F.soft_consensus(
            [self._bk("pinnacle", 9.99, 9.99, 9.99), self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("unibet_eu", 2.15, 3.30, 3.95)], "Heim", "Gast")
        self.assertNotIn("pinnacle", books)
        self.assertEqual(pub["best_hw"], 2.15, "Pinnacle darf den Bestpreis nicht stellen")

    def test_ein_einziges_buch_liefert_keinen_bestpreis(self):
        import fetch_liga_odds as F
        pub, _, _, _ = F.soft_consensus([self._bk("bet365", 2.05, 3.50, 3.80)], "Heim", "Gast")
        self.assertNotIn("best_hw", pub)
        self.assertIn("public_hw", pub)

    def test_die_bestpreis_linie_darf_unter_100_prozent_summieren(self):
        """🔴 Der Fehler, der beim Bauen sofort auftrat: `plausible_1x2` verwirft alles unter
        Overround 1,00 als „Arbitrage-Geschenk = Fehler". Fuer EIN Buch stimmt das. Fuer eine
        Best-of-29-Linie ist es der Normal- und Zweckfall — die Spur waere nie geschrieben
        worden. Zwei Regeln statt einer aufgeweichten."""
        from odds_plausibility import plausible_1x2, plausible_best_1x2
        self.assertFalse(plausible_1x2(2.15, 3.60, 4.10))
        self.assertTrue(plausible_best_1x2(2.15, 3.60, 4.10))
        # nach unten bleibt eine Grenze
        self.assertFalse(plausible_best_1x2(3.0, 4.0, 5.0))
        # und die alte Regel ist unveraendert scharf
        self.assertFalse(plausible_1x2(1.04, 1.01, 1.04))
        self.assertFalse(plausible_best_1x2(1.04, 1.01, 1.04))

    def test_die_drei_spuren_bleiben_getrennt(self):
        """🔴 Zweiter Fehler beim Bauen: der Pinnacle-Rueckgriff suchte `bk != "public"` und
        haette die neue best-Spur als „letzten Pinnacle" gelesen — echte Pinnacle-Bewegungen
        waeren im Aenderungs-Vergleich verschwunden."""
        import fetch_liga_odds as F
        h = {}
        pr = {"hw": 2.0, "dr": 3.4, "aw": 3.9,
              "public_hw": 2.05, "public_dr": 3.5, "public_aw": 3.95,
              "best_hw": 2.15, "best_dr": 3.6, "best_aw": 4.10, "bestBook_hw": "unibet"}
        F.append_snapshot(h, "k", pr, "2026-09-07T08:00:00+00:00")
        self.assertEqual([s["bk"] for s in h["k"]], ["pinnacle", "public", "best"])
        self.assertEqual(F.append_snapshot(h, "k", pr, "2026-09-07T09:00:00+00:00"), 0)
        pr2 = dict(pr, hw=2.10)
        self.assertEqual(F.append_snapshot(h, "k", pr2, "2026-09-07T10:00:00+00:00"), 1)
        self.assertEqual(h["k"][-1]["bk"], "pinnacle")


if __name__ == "__main__":
    unittest.main()


class TestNurSpielbareBuecher(unittest.TestCase):
    """07.09.2026, Lucas: „mit den Quoten dann quasi von Softbookies oder wie?"

    Die Frage hat einen Fehler in meinem eigenen Bau aufgedeckt, bevor etwas live war. Der Feed
    holt `regions=eu,uk,us` — im Bestand stehen Konsense aus bis zu 46 Büchern. Das Maximum über
    ALLE wäre systematisch bei US-Buchmachern gelandet (DraftKings, FanDuel …), bei denen man
    aus Österreich kein Konto eröffnen kann.

    Das Board hätte dann korrekt gerechnete Value-Funde gezeigt, auf die man nicht handeln kann.
    Eine richtige Zahl, die nichts nützt, ist in diesem System der teurere Fehler.
    """

    def _bk(self, key, hw, dr, aw):
        return {"key": key, "markets": [{"key": "h2h", "outcomes": [
            {"name": "Heim", "price": hw}, {"name": "Draw", "price": dr},
            {"name": "Gast", "price": aw}]}]}

    def test_ein_us_buch_stellt_nie_den_bestpreis(self):
        import fetch_liga_odds as F
        pub, _, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("unibet_eu", 2.15, 3.30, 3.95),
             self._bk("draftkings", 2.60, 3.90, 4.60)], "Heim", "Gast")
        self.assertEqual(pub["bestBook_hw"], "unibet_eu")
        self.assertEqual(pub["best_hw"], 2.15)

    def test_der_median_bleibt_ueber_ALLE_buecher(self):
        """Er beschreibt den Markt, er ist nicht der Preis, den man nimmt. Ihn mitzufiltern
        wuerde die Marktbeschreibung verzerren."""
        import fetch_liga_odds as F
        pub, books, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("unibet_eu", 2.15, 3.30, 3.95),
             self._bk("draftkings", 2.60, 3.90, 4.60),
             self._bk("fanduel", 2.55, 3.85, 4.50)], "Heim", "Gast")
        self.assertIn("draftkings", books)
        self.assertEqual(pub["public_hw"], 2.35)

    def test_nBooks_zaehlt_nur_die_spielbaren(self):
        """Sonst behauptet die Zahl eine Auswahl, die es nicht gab — und die Mindestzahl im
        Scanner waere wirkungslos."""
        import fetch_liga_odds as F
        pub, _, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("unibet_eu", 2.15, 3.30, 3.95),
             self._bk("draftkings", 2.60, 3.90, 4.60),
             self._bk("fanduel", 2.55, 3.85, 4.50)], "Heim", "Gast")
        self.assertEqual(pub["nBooks_hw"], 2)

    def test_nur_ein_spielbares_buch_liefert_keinen_bestpreis(self):
        import fetch_liga_odds as F
        pub, _, _, _ = F.soft_consensus(
            [self._bk("bet365", 2.05, 3.50, 3.80),
             self._bk("draftkings", 2.60, 3.90, 4.60),
             self._bk("fanduel", 2.55, 3.85, 4.50)], "Heim", "Gast")
        self.assertNotIn("best_hw", pub, "aus EINEM Buch ist das Maximum keine Auswahl")

    def test_die_liste_kennt_die_gaengigen_faelle(self):
        import buecher as B
        for ja in ("bet365", "unibet_eu", "bwin", "interwetten", "betano", "BET365", " bwin "):
            self.assertTrue(B.spielbar(ja), ja)
        for nein in ("draftkings", "fanduel", "betmgm", "caesars", "bovada", "", None):
            self.assertFalse(B.spielbar(nein), repr(nein))

    def test_pinnacle_steht_nicht_in_der_spielbar_liste(self):
        """Pinnacle ist der MASSSTAB, nicht der Ort, an dem gespielt wird. Stuende es drin,
        wuerde der Scanner Pinnacle gegen sich selbst halten — Edge per Konstruktion null,
        aber die Zeile saehe aus wie ein Fund."""
        import buecher as B
        self.assertFalse(B.spielbar("pinnacle"))
