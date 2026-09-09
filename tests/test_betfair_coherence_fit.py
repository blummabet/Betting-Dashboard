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

    # 🔴 09.09.2026 — HIER STAND EIN GUARD, DER DIE DATEN MASS STATT DEN CODE.
    #
    # Er verlangte, dass im LIVE-Snapshot mindestens ein Fit an der Schranke scheitert. Die
    # Absicht war richtig (eine Schranke, die nie greift, koennte man versehentlich loeschen),
    # die Umsetzung nicht: am 09.09. hatte der Snapshot 49 Leitern, die schlechteste mit RMSE
    # 0,0154 — alle unter der Schranke von 0,02. Der Test wurde rot, weil die DATEN gut waren.
    #
    # Ein Guard, der bei gutem Marktzustand anschlaegt, erzieht dazu, ihn zu ignorieren — und
    # dann faengt er auch den echten Fall nicht mehr. Genau dieselbe Klasse wie „eine Kennzahl
    # urteilt ueber sich selbst", nur eine Ebene hoeher: hier urteilt ein TEST ueber Daten,
    # ueber die er gar nichts behaupten wollte.
    #
    # Was an seine Stelle tritt, sind zwei Saetze, die beide vom Marktzustand UNABHAENGIG sind:
    #   1. Die Schranke wird im Entscheidungspfad wirklich angewandt (mit einer konstruierten
    #      Leiter geprueft, nicht mit einer gefundenen).
    #   2. Sie ist an DIESEN Daten kalibriert: sie liegt in derselben Groessenordnung wie die
    #      real vorkommenden Fits. Eine Schranke bei 0,5 waere formal vorhanden und praktisch
    #      tot — und genau das sollte der alte Test verhindern.
    def test_die_schranke_greift_im_entscheidungspfad(self):
        """Geprueft mit einer KONSTRUIERTEN Leiter — unabhaengig davon, wie der Markt heute
        aussieht. Die verbogene Leiter darf kein Urteil erzeugen, die saubere schon."""
        schlecht = BC._fit_lambda(_leiter(stoerung=0.25))
        self.assertGreater(schlecht[2], BC.MAX_RMSE, "Vorbedingung: der Fit ist schlecht")
        gut = BC._fit_lambda(_leiter())
        self.assertLessEqual(gut[2], BC.MAX_RMSE, "Vorbedingung: der Fit ist gut")
        # Und der Code liest die Schranke auch: die Zeile, die aussortiert, muss existieren.
        quelle = (BASE / "sharp_signals" / "betfair_coherence.py").read_text(encoding="utf-8")
        self.assertIn("rmse > MAX_RMSE", quelle,
                      "die Schranke steht in der Konstanten, aber nichts sortiert danach aus")

    def test_die_schranke_ist_an_diesen_daten_kalibriert(self):
        """Die Absicht des alten Guards, ohne seine Abhaengigkeit vom Tagesbestand: die Schranke
        muss in der Groessenordnung der real vorkommenden Fits liegen. Bei MAX_RMSE = 0,5 waere
        sie formal da und praktisch tot — DAS soll auffallen, nicht ein guter Markttag."""
        alle = self._leitern()
        schlechteste = max(rmse for _r, (_l, _s, rmse) in alle)
        self.assertGreater(
            schlechteste * 10, BC.MAX_RMSE,
            f"schlechtester realer Fit {schlechteste:.4f}, Schranke {BC.MAX_RMSE} — die "
            "Schranke liegt so weit ueber allem, was vorkommt, dass sie nie greifen kann")
        # Die Gegenrichtung gehoert dazu: eine Schranke UNTER allen realen Fits wuerde jede
        # Leiter aussortieren und das Signal still abschalten.
        beste = min(rmse for _r, (_l, _s, rmse) in alle)
        self.assertGreater(BC.MAX_RMSE, beste,
                           f"bester realer Fit {beste:.4f} liegt ueber der Schranke — dann "
                           "kommt gar nichts mehr durch und das Signal ist tot")

    def test_wie_viele_leitern_die_schranke_heute_nimmt(self):
        """Kein Urteil, nur ein Protokoll: der Anteil steht im Testlauf, damit eine Verschiebung
        auffaellt, ohne dass ein guter Markttag den Lauf rot macht."""
        alle = self._leitern()
        raus = len([1 for _r, (_l, _s, rmse) in alle if rmse > BC.MAX_RMSE])
        print(f"\n[coherence] {len(alle)} Leitern im Snapshot, {raus} ueber MAX_RMSE "
              f"({BC.MAX_RMSE}) — schlechtester Fit "
              f"{max(rmse for _r, (_l, _s, rmse) in alle):.4f}")
        self.assertGreaterEqual(raus, 0)


if __name__ == "__main__":
    unittest.main()
