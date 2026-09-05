#!/usr/bin/env python3
"""
Die n-korrigierte Auffaelligkeit — und die Krankheit, die sie ersetzt.

04.09.2026. Der Kern: `max/median` waechst mit der Stichprobengroesse und sortiert damit
nach Sammeldauer statt nach Auffaelligkeit. Diese Tests halten fest, dass die neue Zahl
das NICHT tut, dass ein Plateau kein Befund ist, und dass „zu duenn" niemals als
harmlose Zahl herauskommt.
"""
import math
import random
import statistics
import unittest

import stake_seltenheit as S
from stake_analyse import auffaellig, kleine_liga_gross, _ueber_norm


def _pareto(n, alpha=1.5, xm=2000.0, seed=7):
    r = random.Random(seed)
    return [xm / (r.random() ** (1.0 / alpha)) for _ in range(n)]


class TestSchwanz(unittest.TestCase):
    def test_zu_duenn_gibt_None_statt_einer_Zahl(self):
        """Unter TAIL_MIN_N gibt es kein Urteil. Nicht 1.0, nicht 0 — None.
        Fehlende Information ist keine Erlaubnis."""
        for n in (0, 1, 15, S.TAIL_MIN_N - 1):
            self.assertIsNone(S.schwanz(_pareto(n)), "n=%d haette kein Urteil geben duerfen" % n)

    def test_ab_der_Grenze_gibt_es_Fits(self):
        fits = S.schwanz(_pareto(S.TAIL_MIN_N))
        self.assertTrue(fits)
        self.assertGreaterEqual(len(fits), 1)
        for f in fits:
            self.assertGreater(f["alpha"], 0)
            self.assertGreater(f["xK"], 0)

    def test_entartet_gibt_None(self):
        """Alle Werte gleich -> kein Schwanz, keine Streuung, kein Urteil."""
        self.assertIsNone(S.schwanz([2000.0] * 200))

    def test_nicht_numerisches_und_Nullen_fliegen_raus(self):
        self.assertIsNone(S.schwanz([None, "x", 0, -5] * 30))

    def test_bool_gilt_nicht_als_Betrag(self):
        self.assertIsNone(S.schwanz([True] * 100))


class TestSeltenheit(unittest.TestCase):
    def test_groesster_Wert_ist_IM_MITTEL_einmal_erwartbar(self):
        """Das Maximum JEDER Stichprobe ist per Konstruktion rund einmal erwartbar.
        Genau deshalb ist `max/median` kein Urteil — und `erwartetN` eines.

        Ueber EINE Stichprobe sagt das nichts: der erste Entwurf dieses Tests pruefte einen
        einzigen Seed und schlug fehl, weil die Nullverteilung breit ist. Genau dieser
        Fehlschlag hat `zufallPct` erzwungen. Gemessen wird deshalb der Median ueber viele."""
        werte = [S.seltenheit(max(w), S.schwanz(w))["erwartetN"]
                 for w in (_pareto(200, seed=i) for i in range(120))]
        self.assertGreater(statistics.median(werte), 0.6)
        self.assertLess(statistics.median(werte), 1.8)

    def test_Nullverteilung_wird_eingehalten(self):
        """Der Fund, der die feste Schwelle gekippt hat: in einer Stichprobe, in der NICHTS
        auffaellig ist, liegt das Maximum in ~25 % der Faelle bei „2x ueber Erwartung".
        `zufallPct` muss das auf hoechstens ~10 % druecken — sonst meldet die Kachel
        reihenweise Ligen, in denen nichts passiert ist."""
        for n in (60, 200, 500):
            treffer = 0
            for i in range(200):
                w = _pareto(n, seed=i * 31 + n)
                sel = S.seltenheit(max(w), S.schwanz(w))
                if sel and sel["zufallPct"] is not None and sel["zufallPct"] <= 0.10:
                    treffer += 1
            self.assertLessEqual(treffer / 200.0, 0.18,
                                 "n=%d: zu viele Fehlalarme (%d/200)" % (n, treffer))

    def test_zufallPct_ist_n_frei(self):
        """Dasselbe Vielfache darf in einer grossen Liga NICHT dasselbe Urteil geben wie in
        einer kleinen — die Nullverteilung waechst mit n. Ohne das waere die Schwelle wieder
        eine Rangliste der Sammeldauer."""
        self.assertEqual(S.zufall_pct(8.0, 100), 0.01)
        self.assertEqual(S.zufall_pct(8.0, 600), 0.10)

    def test_Eichung_passt_zu_den_Konstanten(self):
        """`NULL` wurde fuer genau diese Schwanzausschnitte simuliert. Wer sie aendert, ohne
        neu zu simulieren, laesst `zufallPct` auf eine Eichung zeigen, die es nicht mehr gibt —
        und das waere still, weil weiterhin Zahlen herauskaemen."""
        self.assertEqual(S.TAIL_ANTEILE, (0.05, 0.08, 0.10, 0.15, 0.20))
        self.assertEqual(S.TAIL_MIN_K, 5)
        self.assertEqual(S.TAIL_MIN_N, 40)
        self.assertEqual(min(S.NULL), S.TAIL_MIN_N)

    def test_waechst_NICHT_mit_der_Stichprobengroesse(self):
        """Der eigentliche Fund vom 04.09.: max/median steigt mit n (r=+0,68), die
        n-korrigierte Zahl darf das nicht tun."""
        klein, gross = _pareto(60, seed=3), _pareto(600, seed=3)
        v_klein = max(klein) / sorted(klein)[len(klein) // 2]
        v_gross = max(gross) / sorted(gross)[len(gross) // 2]
        self.assertGreater(v_gross, v_klein * 1.5, "Voraussetzung: x Median steigt mit n")
        u_klein = S.seltenheit(max(klein), S.schwanz(klein))["ueberErwartung"]
        u_gross = S.seltenheit(max(gross), S.schwanz(gross))["ueberErwartung"]
        # beide um 1 herum, keine Groessenordnung dazwischen
        self.assertLess(max(u_klein, u_gross) / max(min(u_klein, u_gross), 1e-9), 4.0)

    def test_ein_echter_Ausreisser_wird_erkannt(self):
        werte = _pareto(200, seed=11)
        sel = S.seltenheit(max(werte) * 50, S.schwanz(werte))
        self.assertGreater(sel["ueberErwartung"], 5.0)

    def test_Plateau_erzeugt_keinen_Scheinbefund(self):
        """Caribbean Premier League, 04.09.: neun Werte dicht beieinander, darueber eine
        einzelne groessere. Ein einzelner Hill-Fit sass im Plateau, schaetzte alpha riesig
        und meldete 22,1x. Der konservativste Fit meldet 1,2x. Geklemmte Varianz ist kein
        Befund — dieselbe Krankheit wie „UG +74 % aus drei Plays"."""
        werte = [2000.0 + i for i in range(60)] + [9300.0] * 9 + [15580.0]
        fits = S.schwanz(werte)
        self.assertTrue(fits)
        sel = S.seltenheit(15580.0, fits)
        einzeln = max(S.seltenheit(15580.0, f)["ueberErwartung"] for f in fits)
        self.assertGreater(einzeln, 5.0, "Voraussetzung: ein einzelner Fit uebertreibt hier")
        self.assertLess(sel["ueberErwartung"], einzeln / 2,
                        "der konservativste Fit muss den Scheinbefund kappen")

    def test_kSpanne_zeigt_die_Wackeligkeit(self):
        werte = [2000.0 + i for i in range(60)] + [9300.0] * 9 + [15580.0]
        sel = S.seltenheit(15580.0, S.schwanz(werte))
        self.assertEqual(sel["ueberErwartung"], sel["kSpanne"][0])
        self.assertGreater(sel["kSpanne"][1], sel["kSpanne"][0])

    def test_ohne_Fits_kein_Urteil(self):
        self.assertIsNone(S.seltenheit(5000.0, None))
        self.assertIsNone(S.seltenheit(5000.0, []))

    def test_Betrag_ungueltig_gibt_None(self):
        fits = S.schwanz(_pareto(200))
        for b in (None, 0, -1, "viel", True):
            self.assertIsNone(S.seltenheit(b, fits), "Betrag %r haette None geben muessen" % (b,))

    def test_p_nie_ueber_eins(self):
        fits = S.schwanz(_pareto(200))
        for f in fits:
            self.assertLessEqual(S.p_schwanz(1.0, f), 1.0)

    def test_monoton(self):
        """Mehr Geld darf nie weniger ueberraschend sein."""
        fits = S.schwanz(_pareto(300, seed=5))
        vorher = None
        for b in (3000, 10000, 30000, 100000, 500000):
            u = S.seltenheit(b, fits)["ueberErwartung"]
            if vorher is not None:
                self.assertGreaterEqual(u, vorher)
            vorher = u


class TestAuffaellig(unittest.TestCase):
    def _norm(self, n=300, seed=9):
        werte = _pareto(n, seed=seed)
        return {"Testliga": {"basis": "gelernt", "n": n,
                             "median": sorted(werte)[n // 2],
                             "schwanz": S.schwanz(werte)}}, werte

    def test_drei_unterscheidbare_Zustaende(self):
        norm, werte = self._norm()
        a = auffaellig({"liga": "Testliga", "einsatzUsd": max(werte) * 30}, norm)
        self.assertEqual(a["basis"], "n-korrigiert")
        self.assertIsNotNone(a["ueberErwartung"])

        duenn = {"Testliga": {"basis": "gelernt", "n": 20, "median": 2000.0, "schwanz": None}}
        b = auffaellig({"liga": "Testliga", "einsatzUsd": 90000.0}, duenn)
        self.assertEqual(b["basis"], "nur median")
        self.assertIsNone(b["ueberErwartung"])
        self.assertIsNotNone(b["faktor"])

        c = auffaellig({"liga": "Unbekannt", "einsatzUsd": 90000.0}, norm)
        self.assertEqual(c["basis"], "keine Norm")
        self.assertIsNone(c["ueberErwartung"])
        self.assertIsNone(c["faktor"])

    def test_gemessen_unauffaellig_schlaegt_grossen_Medianfaktor(self):
        """Der Kern der Umstellung: eine Wette mit riesigem x Median, die gemessen
        erwartbar ist, darf NICHT als auffaellig durchgehen. Vorher tat sie genau das —
        und stand dann auch noch oben."""
        norm, werte = self._norm(n=560, seed=4)
        gross = max(werte)
        a = auffaellig({"liga": "Testliga", "einsatzUsd": gross}, norm)
        self.assertGreater(a["faktor"], 20, "Voraussetzung: der alte Faktor sieht spektakulaer aus")
        self.assertEqual(a["zufallPct"], 1.0)
        self.assertFalse(_ueber_norm(a))

    def test_Rangliste_stellt_gemessene_Urteile_nach_vorn(self):
        norm, werte = self._norm(n=300, seed=6)
        duenne = dict(norm)
        duenne["Duennliga"] = {"basis": "gelernt", "n": 20, "median": 1000.0, "schwanz": None}
        wetten = [
            {"id": "a", "liga": "Duennliga", "einsatzUsd": 500000.0, "quote": 2.0},   # x500 Median
            {"id": "b", "liga": "Testliga", "einsatzUsd": max(werte) * 40, "quote": 2.0},
        ]
        out = kleine_liga_gross(wetten, duenne)
        self.assertEqual(out[0]["id"], "b", "gemessenes Urteil muss vor dem Median-Faktor stehen")
        self.assertIsNotNone(out[0]["zufallPct"])
        self.assertIsNone(out[1]["zufallPct"])

    def test_grund_behauptet_nichts_was_die_Zahl_widerlegt(self):
        norm, werte = self._norm()
        wetten = [{"id": "a", "liga": "Testliga", "einsatzUsd": max(werte) * 40, "quote": 2.0}]
        r = kleine_liga_gross(wetten, norm)[0]
        self.assertIn("über Erwartung", r["grund"])
        self.assertIn("%", r["grund"], "der Grund muss die Seltenheit nennen, nicht nur das Vielfache")
        self.assertNotIn("Median der Liga", r["grund"])

    def test_duenner_grund_sagt_dass_er_schwaecher_ist(self):
        duenn = {"L": {"basis": "gelernt", "n": 20, "median": 1000.0, "schwanz": None}}
        r = kleine_liga_gross([{"id": "a", "liga": "L", "einsatzUsd": 50000.0, "quote": 2.0}], duenn)[0]
        self.assertIn("zu dünn", r["grund"])


if __name__ == "__main__":
    unittest.main()
