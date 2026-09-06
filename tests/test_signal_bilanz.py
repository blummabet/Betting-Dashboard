"""Tests fuer signal_bilanz.py — 06.09.2026.

Die Regel, die hier festgehalten wird: **ein Urteil gibt es nur, wenn das ganze Intervall auf
einer Seite liegt.** Ein Signal mit n=12 und Ø CLV +3 pp bekommt „kein Urteil", nicht „gut".
Und die Richtung zaehlt: ein Signal mit negativem Score behauptet „schlechter Pick" — sein
Beitrag ist der umgekehrte Ausgang.
"""
import unittest

import signal_bilanz as B


def _rec(clv, signale, resolved=True):
    return {"clvPP": clv, "clvResolved": resolved,
            "signals": [{"name": n, "score": w} for n, w in signale]}


# 06.09.2026: seit der Schichtung nach der Zahl der UEBRIGEN Signale muessen „gefeuert" und
# „geschwiegen" dieselbe Schicht teilen — sonst gibt es zu Recht kein Urteil. Reale Picks
# tragen immer mehrere Signale; die Fixtures bilden das jetzt ab.
FUELL = ("fuell", 1.0)


def _mit(clv, name, score=1.0, resolved=True):
    """Pick, auf dem `name` gefeuert hat — plus ein Fuellsignal (Schicht 1)."""
    return _rec(clv, [FUELL, (name, score)], resolved)


def _ohne(clv, resolved=True):
    """Pick, auf dem das geprueifte Signal schwieg.

    Wichtig fuer die Schichtung: verglichen wird nach der Zahl der UEBRIGEN Signale. Ein Pick
    MIT dem Signal hat hier zwei Eintraege (Fuellsignal + Signal) -> ein uebriges. Der
    Vergleichspick muss also genau EIN Signal tragen, nicht zwei — sonst liegen die beiden in
    verschiedenen Schichten und es gibt zu Recht kein Urteil."""
    return _rec(clv, [FUELL], resolved)


def _ausgang_konstant(wert):
    return lambda r: wert


class TestBeitraege(unittest.TestCase):
    def test_richtung_wird_beruecksichtigt(self):
        """Ein Signal, das WARNT (Score < 0), traegt bei, wenn die Linie GEGEN den Pick lief."""
        recs = [_rec(-4.0, [("warner", -2.0)])]
        d = B.beitraege(recs, _ausgang_konstant(None))
        self.assertEqual(d["warner"]["clv"], [4.0])

    def test_score_null_ist_keine_beobachtung(self):
        d = B.beitraege([_rec(2.0, [("still", 0.0)])], _ausgang_konstant(None))
        self.assertNotIn("still", d)

    def test_ohne_clvResolved_keine_clv_beobachtung(self):
        """Eine 0.0 ohne clvResolved ist ein Platzhalter, keine gemessene Null."""
        d = B.beitraege([_rec(0.0, [("x", 1.0)], resolved=False)], _ausgang_konstant(None))
        self.assertEqual(d["x"]["clv"], [])

    def test_ausgang_wird_bei_warnsignal_gespiegelt(self):
        d = B.beitraege([_rec(None, [("warner", -1.0)], resolved=False)],
                        _ausgang_konstant(0.8))
        self.assertAlmostEqual(d["warner"]["ausgang"][0], 0.2)

    def test_kaputte_eingaben(self):
        self.assertEqual(B.beitraege(None, _ausgang_konstant(None)), {})
        self.assertEqual(B.beitraege([None, 5], _ausgang_konstant(None)), {})
        self.assertEqual(B.beitraege([{"signals": ["x"]}], _ausgang_konstant(None)), {})

    def test_kaputte_outcome_funktion_kippt_nichts(self):
        def boom(_r):
            raise ValueError("kaputt")
        d = B.beitraege([_rec(2.0, [("x", 1.0)])], boom)
        self.assertEqual(d["x"]["clv"], [2.0])
        self.assertEqual(d["x"]["ausgang"], [])


class TestVergleichsgruppe(unittest.TestCase):
    """06.09.2026, nach dem ersten Lauf umgestellt. Die erste Fassung mass gegen einen FESTEN
    Nullpunkt und meldete prompt fuenf Signale gleichzeitig als „schadet" (CLV) und „traegt
    bei" (Ausgang). Der Widerspruch war meiner: unsere Picks steigen im Schnitt 2,2 pp unter
    dem Schlusskurs ein — diesen Sockel erbt jedes Signal, das auf ihnen feuert. Gemessen wird
    jetzt der UNTERSCHIED zu den Picks, auf denen das Signal geschwiegen hat."""

    def test_vergleichsgruppe_wird_gebildet(self):
        recs = ([_rec(-2.0, [("a", 1.0)]) for _ in range(30)]
                + [_rec(-2.0, [("b", 1.0)]) for _ in range(30)])
        d = B.beitraege(recs, _ausgang_konstant(None))
        self.assertEqual(len(d["a"]["clv"]), 30)
        self.assertEqual(len(d["a"]["clvOhne"]), 30, "die b-Picks sind a's Vergleichsgruppe")

    def test_gleichmaessig_schlechter_sockel_ist_kein_signalbefund(self):
        """Der Kern: wenn ALLE Picks -2 pp CLV haben, hat kein einzelnes Signal daran schuld."""
        recs = ([_rec(-2.0 + (i % 5) * 0.1, [("a", 1.0)]) for i in range(40)]
                + [_rec(-2.0 + (i % 5) * 0.1, [("b", 1.0)]) for i in range(40)])
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["a"]["clvUrteil"], "kein Urteil")
        self.assertEqual(B.schaedliche(bil), [])

    def test_signal_das_wirklich_besser_ist(self):
        recs = ([_mit(+1.0 + (i % 5) * 0.1, "gut") for i in range(40)]
                + [_ohne(-3.0 + (i % 5) * 0.1) for i in range(40)])
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["gut"]["clvUrteil"], "traegt bei")
        self.assertAlmostEqual(bil["gut"]["clvDiff"], 4.0, places=1)

    def test_ohne_vergleichsgruppe_kein_urteil(self):
        """Feuert ein Signal auf ALLEN Picks, gibt es nichts zu vergleichen."""
        recs = [_rec(5.0, [("ueberall", 1.0)]) for _ in range(60)]
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["ueberall"]["clvUrteil"], "kein Urteil")
        self.assertEqual(bil["ueberall"]["nClvOhne"], 0)


class TestUrteil(unittest.TestCase):
    def test_zu_wenig_beobachtungen_kein_urteil(self):
        recs = [_rec(5.0, [("gut", 1.0)]) for _ in range(B.MIN_N - 1)]
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["gut"]["clvUrteil"], "kein Urteil")
        self.assertIsNone(bil["gut"]["clvPP"])

    def test_klar_positives_signal_traegt_bei(self):
        recs = ([_mit(4.0 + (i % 3) * 0.2, "gut") for i in range(40)]
                + [_ohne(0.0 + (i % 3) * 0.2) for i in range(40)])
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["gut"]["clvUrteil"], "traegt bei")
        self.assertIn("gut", B.tragende(bil))

    def test_klar_negatives_signal_schadet(self):
        recs = ([_mit(-4.0 - (i % 3) * 0.2, "schlecht") for i in range(40)]
                + [_ohne(0.0 + (i % 3) * 0.2) for i in range(40)])
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["schlecht"]["clvUrteil"], "schadet")
        self.assertIn("schlecht", B.schaedliche(bil))

    def test_rauschen_bekommt_kein_urteil(self):
        """Der wichtigste Test: gross gestreut um null herum ist KEIN Befund."""
        recs = ([_mit(12.0 if i % 2 else -11.0, "rauschen") for i in range(40)]
                + [_ohne(0.5 * (i % 4) - 0.7) for i in range(40)])
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["rauschen"]["clvUrteil"], "kein Urteil")
        self.assertEqual(B.schaedliche(bil), [])

    def test_signalzahl_wird_herausgerechnet(self):
        """06.09.2026, dritte Korrektur des Tages. Ohne Schichtung meldete die Bilanz 13 von 33
        Signalen als „traegt bei" und keines als schaedlich — weil Picks mit VIELEN Signalen
        besseren CLV haben (r = +0,131). Jedes Signal erbte diesen Vorteil.

        Hier feuert `mitlaeufer` ausschliesslich auf signalreichen Picks und traegt selbst
        nichts bei. Ungeschichtet saehe es glaenzend aus; geschichtet ist es das, was es ist."""
        recs = []
        for i in range(40):                      # signalreich UND guter CLV
            recs.append(_rec(2.0 + (i % 3) * 0.1,
                             [FUELL, ("a", 1.0), ("b", 1.0), ("mitlaeufer", 1.0)]))
        for i in range(40):                      # ebenso signalreich, ohne den Mitlaeufer
            recs.append(_rec(2.0 + (i % 3) * 0.1, [FUELL, ("a", 1.0), ("b", 1.0), ("c", 1.0)]))
        for i in range(40):                      # signalarm UND schlechter CLV
            recs.append(_rec(-3.0 + (i % 3) * 0.1, [FUELL, ("a", 1.0)]))
        bil = B.bilanz(recs, _ausgang_konstant(None))
        self.assertEqual(bil["mitlaeufer"]["clvUrteil"], "kein Urteil",
                         "der Mitlaeufer darf den Vorteil signalreicher Picks nicht erben")

    def test_ausgang_wird_gegen_die_vergleichsgruppe_gemessen(self):
        """Auch beim Ausgang zaehlt der Unterschied, nicht der Pegel: liegt die ganze Karte bei
        0,62, ist ein Signal mit 0,62 nicht gut, sondern durchschnittlich."""
        def aus(r):
            return 0.62
        recs = ([_rec(None, [FUELL, ("a", 1.0)], resolved=False) for _ in range(40)]
                + [_rec(None, [FUELL], resolved=False) for _ in range(40)])
        bil = B.bilanz(recs, aus)
        self.assertEqual(bil["a"]["ausgangUrteil"], "kein Urteil")

        def aus2(r):
            return 0.70 if any(s["name"] == "a" for s in r["signals"]) else 0.40
        bil2 = B.bilanz(recs, aus2)
        self.assertEqual(bil2["a"]["ausgangUrteil"], "traegt bei")


class TestBefunde(unittest.TestCase):
    def test_nur_belegte_schaeden_werden_gemeldet(self):
        recs = ([_mit(-4.0 - (i % 3) * 0.1, "schlecht") for i in range(40)]
                + [_ohne(0.0 + (i % 3) * 0.1) for i in range(40)])
        b = B.befunde(B.bilanz(recs, _ausgang_konstant(None)))
        self.assertEqual(len(b), 1)
        self.assertIn("schlecht", b[0])
        self.assertIn("abwerten", b[0])

    def test_leere_bilanz(self):
        self.assertEqual(B.befunde({}), [])
        self.assertEqual(B.befunde(None), [])


if __name__ == "__main__":
    unittest.main()
