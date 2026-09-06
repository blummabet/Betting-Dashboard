"""betfair_coherence darf keinen Misfit als Markt-Kante verkaufen — 06.09.2026.

Gemessen ueber die 119 Betfair-Matches mit Ueber/Unter-Leiter:

    r(RMSE des Poisson-Fits, groesste gemeldete "Kante") = **+0,985**

Die "Kante" dieses Signals war zu 97 % der eigene Misfit. `rmse` senkte bis heute nur die
`confidence` und blockte nie den `score` — in Bundesliga 2, Segunda oder Thai League 2 (RMSE
6-14 pp) haette das Signal Abweichungen von 12-29 pp als Markt-Inkohaerenz gemeldet.
Bug-Klasse 5: eine Metrik, die sich selbst beurteilt.

Die Schranke kommt aus der Messung, nicht aus dem Gefuehl: bei RMSE <= 0,02 hat KEINES der 84
verbleibenden Spiele eine Kante >= 4 pp. Wo wir die Leiter beschreiben koennen, stimmen wir
mit ihr ueberein — die Betfair-Tormarkt-Leiter ist auf unserer Aufloesung arbitragefrei.

Folge: das Signal feuert fast nie. Das ist das Ergebnis, nicht der Fehler.
"""
import json
import unittest
from pathlib import Path

import sharp_signals.betfair_coherence as BC

BASE = Path(__file__).resolve().parents[1]


def _leiter(lam_wie_poisson=True, stoerung=0.0):
    """Baut eine Ue/U-Leiter: entweder sauber poissonverteilt oder absichtlich verbogen."""
    rungs = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        p = BC._pois_over(line, 2.6)
        if stoerung and line == 2.5:
            p = min(0.99, max(0.01, p + stoerung))
        rungs[line] = p
    return rungs


class TestFitSchranke(unittest.TestCase):
    def test_schranke_existiert_und_ist_scharf(self):
        self.assertTrue(hasattr(BC, "MAX_RMSE"))
        self.assertLessEqual(BC.MAX_RMSE, 0.03,
                             "ueber 0,03 kommen laut Messung Misfit-'Kanten' durch")

    def test_sauberer_fit_kommt_durch(self):
        fit = BC._fit_lambda(_leiter())
        self.assertIsNotNone(fit)
        self.assertLessEqual(fit[2], BC.MAX_RMSE)

    def test_verbogene_leiter_wird_zum_schlechten_fit(self):
        """Eine Leiter, die kein Poisson beschreibt, muss sich am RMSE zeigen — genau daran
        haengt jetzt die Entscheidung."""
        fit = BC._fit_lambda(_leiter(stoerung=0.25))
        self.assertIsNotNone(fit)
        self.assertGreater(fit[2], BC.MAX_RMSE)


class TestGegenDieEchtenBetfairDaten(unittest.TestCase):
    def _leitern(self):
        p = BASE / "betfair_prices.json"
        if not p.exists():
            self.skipTest("betfair_prices.json nicht vorhanden")
        out = []
        for m in (json.loads(p.read_text(encoding="utf-8")).get("matches") or []):
            r = BC._ou_rungs(m.get("markets") or {})
            if len(r) < BC.MIN_RUNGS:
                continue
            f = BC._fit_lambda(r)
            if f:
                out.append((r, f))
        if not out:
            self.skipTest("keine Leitern im Snapshot")
        return out

    def test_gute_fits_finden_keine_grossen_kanten(self):
        """Der Kern des Befunds: wo das Modell passt, ist der Markt kohaerent. Kippt dieser
        Test, hat sich entweder der Markt geaendert oder unser Fit — beides ist ein Befund."""
        for rungs, (lam, _sse, rmse) in self._leitern():
            if rmse > BC.MAX_RMSE:
                continue
            groesste = max(abs(BC._pois_over(l, lam) - p) for l, p in rungs.items())
            self.assertLess(
                groesste, BC.MIN_EDGE + 0.02,
                f"Gut gefittete Leiter (RMSE {rmse:.4f}) meldet {groesste:.4f} Abweichung — "
                "das waere eine echte Inkohaerenz und gehoert angesehen.")

    def test_schlechte_fits_werden_ueberhaupt_aussortiert(self):
        """Haelt fest, dass die Schranke im echten Bestand etwas tut. Waere sie wirkungslos,
        koennte man sie versehentlich entfernen, ohne dass ein Test rot wird."""
        alle = self._leitern()
        raus = [1 for _r, (_l, _s, rmse) in alle if rmse > BC.MAX_RMSE]
        self.assertGreater(len(raus), 0,
                           "Kein einziger Fit faellt durch — Schranke pruefen statt vertrauen.")


if __name__ == "__main__":
    unittest.main()
