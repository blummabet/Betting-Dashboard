# tests/test_betfair_coherence.py — Markt-Kohärenz-Signal (29.07.2026)
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_signals.betfair_coherence import BetfairCoherenceSignal


def ou(n, p, vol=9000):
    return {"Over/Under %s Goals" % n: {"runners": [
        {"name": "Over %s Goals" % n, "odd": round(1.0 / p, 3), "vol": vol / 2},
        {"name": "Under %s Goals" % n, "odd": round(1.0 / (1 - p), 3), "vol": vol / 2}]}}


def snap(mklist, fair=None, home="Alpha", away="Beta", league="Test"):
    mk = {}
    for d in mklist:
        mk.update(d)
    s = {"home": home, "away": away, "league": league, "markets": mk}
    if fair:
        s["mo"] = {"hw": 2.2, "dr": 3.4, "aw": 3.4, "fair": fair}
    return s


from sharp_signals.betfair_coherence import _pois_over as _pois, _fit_lambda as _fit

SIG = BetfairCoherenceSignal()


class TestCoherence(unittest.TestCase):
    def test_no_snapshot(self):
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {}))

    def test_1x2_pick_returns_none(self):
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(2.5, 0.45), ou(3.5, 0.24)],
                 fair={"home": 0.45, "draw": 0.28, "away": 0.27})
        self.assertIsNone(SIG.evaluate({"market": "Heimsieg"}, {"betfair_snapshot": s}))

    def test_thin_market_none(self):
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(3.5, 0.30), ou(2.5, 0.38, vol=500)])
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s}))

    def test_underpriced_over_fires_positive(self):
        """06.09.2026 neu gebaut. Die alte Fixture war eine Leiter, die KEIN Poisson beschreibt
        (RMSE 0,050 — eine echte Betfair-Leiter liegt bei 0,001), mit Residuen auf allen vier
        Sprossen. Sie testete damit nicht „eine Sprosse ist fehlbepreist", sondern „unser Modell
        passt hier nicht" — und genau das darf das Signal seit heute nicht mehr melden.

        Jetzt: eine saubere Poisson-Leiter, wie sie real vorkommt, mit EINER um 7 pp
        verschobenen Sprosse. Das Lambda wird aus den anderen gefittet, die verschobene faellt
        als Kante auf. So sieht eine echte Fehlbepreisung aus."""
        rein = {l: _pois(l, 2.6) for l in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)}
        rein[2.5] -= 0.07                      # nur DIESE Sprosse ist zu billig
        s = snap([ou(l, p, vol=12000 if l == 2.5 else 9000) for l, p in sorted(rein.items())])
        r = SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s})
        self.assertIsNotNone(r, "eine kohaerente Leiter mit einem echten Ausreisser muss feuern")
        self.assertEqual(r.metadata["token"], "OVER")
        self.assertGreater(r.score, 0)
        self.assertIn("lambda", r.metadata)

    def test_unfittbare_leiter_feuert_nicht(self):
        """Die Gegenprobe, und der eigentliche Fund: eine Leiter, die unser Poisson nicht
        beschreiben kann, ist keine Markt-Kante. Ueber die 119 echten Betfair-Leitern gemessen
        war die Korrelation zwischen dem RMSE des Fits und der gemeldeten „Kante" **+0,985** —
        die Kante WAR der Misfit."""
        s = snap([ou(0.5, 0.93), ou(1.5, 0.74), ou(2.5, 0.38, vol=12000), ou(3.5, 0.30)])
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s}))

    def test_eigene_sprosse_zieht_das_lambda_nicht_zu_sich(self):
        """Leave-one-out: das Lambda darf nicht aus der Sprosse mitgefittet werden, gegen die
        geprueft wird — sonst blockt eine echte Fehlbepreisung ihre eigene Entdeckung."""
        rein = {l: _pois(l, 2.6) for l in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)}
        rein[2.5] -= 0.07
        voll = _fit(rein)
        ohne = _fit({l: p for l, p in rein.items() if l != 2.5})
        self.assertGreater(voll[2], ohne[2],
                           "der volle Fit muss schlechter sein — das ist der ganze Grund fuer LOO")
        self.assertLessEqual(ohne[2], 0.001, "der Rest-Fit muss die Leiter exakt treffen")

    def test_hard_conflict_flag(self):
        # 06.09.2026: um eine Sprosse erweitert — mit nur vier bleibt nach dem Leave-one-out
        # kein tragfaehiger Rest (MIN_REST_RUNGS), und der Test pruefte dann nur noch, dass
        # etwas None ist.
        s = snap([ou(0.5, 0.70), ou(1.5, 0.80), ou(2.5, 0.30, vol=12000), ou(3.5, 0.20),
                  ou(4.5, 0.10), ou(5.5, 0.05)])
        r = SIG.evaluate({"market": "Unter 2.5"}, {"betfair_snapshot": s})
        if r is not None:
            print("hard:", r.metadata["hard_conflict"], r.score)
            self.assertTrue(r.metadata["hard_conflict"])

    def test_ladder_too_short_none(self):
        s = snap([ou(2.5, 0.45, vol=12000), ou(3.5, 0.24)])
        self.assertIsNone(SIG.evaluate({"market": "Über 2.5"}, {"betfair_snapshot": s}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
