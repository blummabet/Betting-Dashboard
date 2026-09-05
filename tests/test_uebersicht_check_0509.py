#!/usr/bin/env python3
"""
Übersicht-Check 05.09.2026 — drei Funde, drei Guards, jeder mit Gegenbeweis.

1. „Parma · intakt · vorher 83% · 1 von 4.541" — die zweite Zahl folgt nicht aus der ersten.
2. „Brighton v Leeds · Poly · kein Markt" — bei $439.712 Poly-Geld im Markt.
3. Stake-Kachel zeigte weiter den abgesetzten Median-Faktor (×129,9 über ×42,7).
"""
import json
import unittest

import uebersicht_integrity as UI
import betfair_consensus as BC


def _lauf(name, ctx):
    return next(c for c in UI.run_checks(ctx) if c["label"] == name)


class TestSerienSeltenheit(unittest.TestCase):
    NAME = "Serien-Seltenheit folgt aus der Liga-Basis, die danebensteht"

    def _s(self, zufall, liga, laenge):
        return {"streaks": [{"team": "Parma", "type": "under25", "length": laenge,
                             "zufallPct": zufall, "ligaBasisPct": liga}]}

    def test_gesunde_Serie_geht_durch(self):
        # 0,39^9 = 0,02087 %; der echte Wert nutzt die ungerundete Rate (39,37 %) = 0,02202 %
        self.assertTrue(_lauf(self.NAME, {"ligaStreaks": self._s(0.02202, 39, 9)})["ok"])

    def test_Rundung_erzeugt_keinen_Fehlalarm(self):
        """Der erste Entwurf verglich gegen den GERUNDETEN Anzeigewert mit fester Toleranz und
        meldete prompt acht gesunde Serien. Bei p^9 wird aus 1 % Rundung ~9 % Abweichung."""
        for lb, ln in ((39, 9), (61, 15), (57, 13), (47, 8)):
            lo = ((lb - 0.49) / 100.0) ** ln * 100
            hi = ((lb + 0.49) / 100.0) ** ln * 100
            for z in (lo, hi, (lo + hi) / 2):
                self.assertTrue(_lauf(self.NAME, {"ligaStreaks": self._s(round(z, 5), lb, ln)})["ok"],
                                f"lb={lb} ln={ln} z={z}")

    def test_mit_der_falschen_Rate_gerechnet_schlaegt_an(self):
        """Der Fund selbst: 0,83^9 = 19,35 % statt 0,022 % — wer die Eigenrate nimmt, fliegt auf."""
        c = _lauf(self.NAME, {"ligaStreaks": self._s(19.35, 39, 9)})
        self.assertFalse(c["ok"])
        self.assertIn("anderen Rate", " ".join(c["failures"]))

    def test_ohne_Liga_Basis_kein_Urteil(self):
        self.assertTrue(_lauf(self.NAME, {"ligaStreaks": self._s(0.02, None, 9)})["ok"])


class TestMoneyMapLuecken(unittest.TestCase):
    NAME = "Money Map meldet ihre Luecken"

    def _ctx(self, poly_row):
        return {
            "moneyMap": {"rows": [{"home": "Brighton", "away": "Leeds",
                                   "betfair": {"eur": 263494}, "poly": poly_row}]},
            "polyClose": {"epl-bri-lee": {"prices": {
                "Brighton & Hove Albion FC": 0.475,
                "Draw (Brighton & Hove Albion FC vs. Leeds United FC)": 0.265,
                "Leeds United FC": 0.255}}},
        }

    def test_stille_Luecke_schlaegt_an(self):
        c = _lauf(self.NAME, self._ctx(None))
        self.assertFalse(c["ok"])
        self.assertIn("Brighton", " ".join(c["failures"]))

    def test_mit_Poly_ist_die_Zeile_in_Ordnung(self):
        self.assertTrue(_lauf(self.NAME, self._ctx({"usd": 439712}))["ok"])

    def test_echte_Abwesenheit_ist_kein_Fehler(self):
        """Kein Poly-Markt für die PAARUNG -> kein Fund. Der erste Entwurf suchte nur den
        Heim-Namen und meldete „Villarreal v Deportivo" wegen eines Villarreal-Spiels vom 16.08."""
        ctx = self._ctx(None)
        ctx["moneyMap"]["rows"][0].update({"home": "Villarreal", "away": "Deportivo"})
        ctx["polyClose"] = {"lal-rrc-vil-2026-08-16": {"prices": {
            "Villarreal CF": 0.5, "Rayo Vallecano": 0.5}}}
        self.assertTrue(_lauf(self.NAME, ctx)["ok"])


class TestStakeKachel(unittest.TestCase):
    NAME = "Stake-Auffaelligkeiten tragen ihr gemessenes Urteil"

    def test_gemessene_Zeile_ohne_zufallPct_schlaegt_an(self):
        c = _lauf(self.NAME, {"stakeAus": {"auffaellige": [
            {"event": "X", "ueberErwartung": 4.9, "zufallPct": None, "faktor": 129.9}]}})
        self.assertFalse(c["ok"])

    def test_vollstaendige_Zeile_geht_durch(self):
        self.assertTrue(_lauf(self.NAME, {"stakeAus": {"auffaellige": [
            {"event": "X", "ueberErwartung": 4.9, "zufallPct": 0.10, "faktor": 129.9}]}})["ok"])

    def test_nur_median_Zeile_geht_durch(self):
        self.assertTrue(_lauf(self.NAME, {"stakeAus": {"auffaellige": [
            {"event": "X", "ueberErwartung": None, "zufallPct": None, "faktor": 56.2}]}})["ok"])


class TestNamensbruecke(unittest.TestCase):
    KEYS = ["Brighton & Hove Albion FC",
            "Draw (Brighton & Hove Albion FC vs. Leeds United FC)",
            "Leeds United FC"]

    def test_Draw_mit_Klammerzusatz_ist_kein_Team(self):
        """Der Kern: Polymarket schreibt den dritten 1X2-Ausgang als „Draw (A vs. B)".
        Die exakte Mengenpruefung hielt ihn fuer einen Teamnamen — in 543 von 565 Maerkten."""
        self.assertTrue(BC._ist_nicht_team(self.KEYS[1]))
        self.assertTrue(BC._ist_nicht_team("The Draw (X vs. Y)"))
        self.assertTrue(BC._ist_nicht_team("Draw"))
        self.assertFalse(BC._ist_nicht_team("Brighton & Hove Albion FC"))
        self.assertFalse(BC._ist_nicht_team("Drawsko Pomorskie FC"), "kein blindes Praefix-Match")

    def test_Abkuerzung_matcht_wieder(self):
        pe = {"prices": {k: 0.3 for k in self.KEYS}, "key": "epl-bri-lee"}
        r = BC._best_poly_entry({"home": "Brighton", "away": "Leeds"}, [pe])
        self.assertIsNotNone(r, "der Rueckfall vom 12.08. muss greifen")
        self.assertEqual(r[1], "Brighton & Hove Albion FC")
        self.assertEqual(r[2], "Leeds United FC")

    def test_Rangliste_und_Annahme_sind_getrennt(self):
        """`bsc` war Bestenliste UND Schwelle in einer Variable (Start 0.99). Damit galt die
        strenge Direkt-Schwelle auch fuer den Rueckfall — er konnte nie zum Zug kommen."""
        self.assertEqual(BC.RUECKFALL_MIN_SUMME, 0.60)
        pe = {"prices": {k: 0.3 for k in self.KEYS}, "key": "epl-bri-lee"}
        summe = BC._name_score("Brighton", self.KEYS[0]) + BC._name_score("Leeds", self.KEYS[2])
        self.assertLess(summe, 0.99, "Voraussetzung: unter der alten Direkt-Schwelle")
        self.assertGreater(summe, BC.RUECKFALL_MIN_SUMME)
        self.assertIsNotNone(BC._best_poly_entry({"home": "Brighton", "away": "Leeds"}, [pe]))

    def test_kein_Falschpaar_bei_nur_einem_Treffer(self):
        """Schutz: die abgeleitete Seite muss mindestens ein Token teilen."""
        pe = {"prices": {"Leeds United FC": 0.5, "Sheffield Wednesday FC": 0.5}, "key": "x"}
        self.assertIsNone(BC._best_poly_entry({"home": "Brighton", "away": "Leeds"}, [pe]))

    def test_direkte_Treffer_bleiben_streng(self):
        pe = {"prices": {"Manchester City FC": 0.7, "Coventry City FC": 0.3}, "key": "y"}
        self.assertIsNone(BC._best_poly_entry({"home": "Nottingham", "away": "Coventry"}, [pe]),
                          "eine Seite passt gar nicht — dann gibt es kein Paar")


if __name__ == "__main__":
    unittest.main()
