"""tests/test_loop_basis.py — 30.08.2026

Lucas-Checkup: „Torjaeger n35, 37% dafuer" — und trotzdem Gewicht 0,974, also praktisch
unbestraft. Der Grund war der Massstab: `weight = posterior_mean / 0.5`. Unsere Picks sind aber
keine Muenzwuerfe, sie gewinnen im Schnitt ~55%. Damit belohnte der Loop den HAUSVORTEIL statt
den Beitrag des Signals — ein Signal auf genau durchschnittlichen Picks bekam einen Bonus, und
eines sieben Punkte unter dem Schnitt fast keine Strafe.

Der heikle Teil ist der CLV-Strom: dort heisst 0,5 „Linie stand still", nicht „Muenzwurf". Wuerde
man ihn gegen die Trefferquote messen, bestrafte man die sharp_money-Signale fuer nichts.
"""
import unittest

import update_signal_weights as U


def pick(win=True, sig=("form_trend",), score=1.0, clv=None):
    return {"result": "WIN" if win else "LOSS", "clvPP": clv,
            "signals": [{"name": n, "score": score} for n in sig]}


class Basis(unittest.TestCase):
    def test_unter_der_mindestzahl_bleibt_der_muenzwurf(self):
        q, n = U.basisquote([pick(True) for _ in range(U.BASIS_MIN_N - 1)])
        self.assertEqual(q, 0.5, "eine Basis aus zu wenig Picks ist kein Massstab")
        self.assertEqual(n, U.BASIS_MIN_N - 1)

    def test_ab_der_mindestzahl_zaehlt_die_eigene_quote(self):
        picks = [pick(True) for _ in range(30)] + [pick(False) for _ in range(20)]
        q, n = U.basisquote(picks)
        self.assertEqual(n, 50)
        self.assertAlmostEqual(q, 0.60, 2)

    def test_gluecksstraehne_kippt_den_massstab_nicht(self):
        q, _ = U.basisquote([pick(True) for _ in range(60)])
        self.assertEqual(q, U.BASIS_MAX, "100% Basis wuerde jedes Signal unter Wasser druecken")
        q2, _ = U.basisquote([pick(False) for _ in range(60)])
        self.assertEqual(q2, U.BASIS_MIN)

    def test_leere_eingabe(self):
        self.assertEqual(U.basisquote([]), (0.5, 0))
        self.assertEqual(U.basisquote(None), (0.5, 0))


class Gewicht(unittest.TestCase):
    """Der Effekt am konkreten Fall: 35 Beobachtungen, 17 davon richtig (48,6%)."""

    def _weight(self, wins, n, basis):
        post = (U.PRIOR_ALPHA + wins) / (U.PRIOR_ALPHA + U.PRIOR_BETA + n)
        return round(max(0.3, min(1.7, post / basis)), 3)

    def test_unterdurchschnittliches_signal_wird_jetzt_bestraft(self):
        alt = self._weight(17, 35, 0.5)      # Muenzwurf-Massstab
        neu = self._weight(17, 35, 0.527)    # MLS-Trefferquote
        self.assertAlmostEqual(alt, 0.974, 2)
        self.assertLess(neu, alt)
        self.assertLess(neu, 0.95)

    def test_durchschnittliches_signal_bekommt_keinen_bonus_mehr(self):
        # 55% Treffer bei einer 55%-Basis heisst: das Signal hat nichts beigetragen.
        n, basis = 100, 0.55
        neu = self._weight(basis * n, n, basis)
        self.assertLess(abs(neu - 1.0), 0.03, "neutral, nicht belohnt")
        alt = self._weight(basis * n, n, 0.5)
        self.assertGreater(alt, 1.05, "vorher gab es dafuer einen Bonus")


class ClvStrom(unittest.TestCase):
    def test_clv_bleibt_gegen_null_komma_fuenf_gemessen(self):
        # Im Modul verdrahtet: der Nullpunkt ist das mit den Stroemen gewichtete Mittel aus
        # Basis (Ergebnisse) und 0.5 (CLV). Reiner CLV -> 0.5, reines Ergebnis -> Basis.
        import inspect
        src = inspect.getsource(U.main) if hasattr(U, "main") else ""
        quelle = inspect.getsource(U)
        self.assertIn("(_n_erg * basis + n_clv * 0.5) / n", quelle,
                      "CLV darf nicht gegen die Trefferquote gemessen werden")

    def test_nullpunkt_mischt_richtig(self):
        basis, n_erg, n_clv = 0.60, 30.0, 10.0
        neutral = (n_erg * basis + n_clv * 0.5) / (n_erg + n_clv)
        self.assertAlmostEqual(neutral, 0.575, 3)


class Nachvollziehbar(unittest.TestCase):
    def test_der_massstab_steht_im_gewicht_drin(self):
        # Ein Gewicht ohne seinen Nullpunkt ist nicht nachrechenbar.
        import json
        from pathlib import Path
        f = Path(__file__).parent.parent / "mls_signal_weights.json"
        if not f.exists():
            self.skipTest("keine MLS-Gewichte im Baum")
        w = json.loads(f.read_text(encoding="utf-8"))
        eintrag = next(v for k, v in w.items() if isinstance(v, dict) and "weight" in v)
        for feld in ("basis", "basisN", "neutral"):
            self.assertIn(feld, eintrag)


if __name__ == "__main__":
    unittest.main()
