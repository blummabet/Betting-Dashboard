"""streak_momentum muss feuern können, sonst ist es nicht messbar — 06.09.2026.

Lucas: „mir kann keiner sagen, dass eine Mannschaft mit einer Serie keine Auswirkung hat.
Das ist für mich unvorstellbar."

Er hatte in dem Punkt recht, der zählt: **wir haben es nie gemessen.** Nachgerechnet über alle
Liga-Picks:

    Ergebnis-Märkte (1X2/DC, 156 von 274 Picks)
      Fälle mit qualifizierter Serie      58
      Median-Score                     0,052
      höchster Score über alle 58      0,214
      Feuer-Schwelle                   0,250
      davon über der Schwelle              0     ← kein einziger

    Über/Unter: Median 0,101, Maximum 0,279 — gerade so über der Schwelle.

Ergebnis: 8 Feuerungen in 318 Picks, praktisch zufällig. Das Signal war nicht vorsichtig, es
war stumm — die Multiplikatorenkette (0,15 × Länge × Rate × Persistenz 0,4–0,5 × xG 0,35 ×
Gegner) löscht sich selbst aus.

Der Zustand war der schlechteste denkbare: **weder helfen noch widerlegt werden können.** Ohne
Beobachtungen urteilt die Bilanz nie, also bleibt das Gewicht ewig 1,0. „Serien wirken nicht"
war nie gemessen; es war nie gefragt.

Die Tests halten fest, dass das Signal sprechen KANN — und dass es dabei leise bleibt.
"""
import json
import unittest
from pathlib import Path

import sharp_signals.streak_momentum as SM

BASE = Path(__file__).resolve().parents[1]


class TestSchwelle(unittest.TestCase):
    def test_die_schwelle_ist_erreichbar(self):
        """Der Kern: die Schwelle muss unter dem liegen, was real vorkommt. Sonst ist das
        Signal per Konstruktion stumm, und niemand merkt es — es sieht aus wie eines, das
        gerade nichts zu sagen hat."""
        self.assertLess(SM.DEFAULTS["min_fire_abs"], 0.214,
                        "über dem höchsten real gemessenen Score der Ergebnis-Märkte — "
                        "dann feuert es dort nie")

    def test_der_deckel_bleibt_klein(self):
        """Feuern ja, Picks drehen nein. Andere Signale liefern 1–3 pp; die Serien-Scores
        liegen bei 0,05–0,28 und sollen es auch bleiben, solange nichts gemessen ist."""
        self.assertLessEqual(SM.DEFAULTS["max_pp"], 2.5)

    def test_daempfung_bleibt_bestehen(self):
        """Die Persistenz-Multiplikatoren stammen aus einem Backtest (Tor-/BTTS-Serien
        mean-reverten: btts −15 %, over25 −11 %, noBtts −26 %; nur Ecken-Über persistiert
        +4 %). Die Schwelle zu senken heisst NICHT, diese Messung zu verwerfen."""
        p = SM.DEFAULTS["market_persistence"]
        self.assertLessEqual(p["bttsYes"], 0.5)
        self.assertLessEqual(p["over25"], 0.5)
        self.assertGreaterEqual(p["cornersOver"], 0.9,
                                "die einzige Serie, die im Backtest persistierte")


class TestGegenDieEchtenDaten(unittest.TestCase):
    def _welt(self):
        for f in ("liga-data.json", "liga_streaks.json"):
            if not (BASE / f).exists():
                self.skipTest(f"{f} fehlt")
        d = json.loads((BASE / "liga-data.json").read_text(encoding="utf-8"))
        idx = {}
        for s in (json.loads((BASE / "liga_streaks.json").read_text(encoding="utf-8"))
                  .get("streaks") or []):
            idx.setdefault(str(s.get("teamId")), []).append(s)
        fix = {}
        for gk, g in (d.get("groups") or {}).items():
            for fx in g.get("fixtures") or []:
                if fx.get("home") and fx.get("away"):
                    fix[f"{gk}-{fx.get('matchday')}-{fx['home']}-{fx['away']}"] = (fx["home"], fx["away"])
        return d, idx, fix

    def test_es_feuert_auf_dem_echten_bestand(self):
        """Kein erfundenes Fixture: gegen die Dateien, die die Pipeline schreibt. Wäre das
        Signal weiter stumm, stünde hier 0 — genau der Zustand, der monatelang unbemerkt war."""
        d, idx, fix = self._welt()
        if not idx:
            self.skipTest("keine Serien im Bestand")
        sig = SM.StreakMomentumSignal()
        n = feuer = 0
        for mk, picks in (d.get("picks") or {}).items():
            if mk not in fix:
                continue
            h, a = fix[mk]
            ctx = {"streaks": idx, "home_id": h, "away_id": a}
            for p in picks or []:
                n += 1
                if sig.evaluate(p, ctx):
                    feuer += 1
        if n < 50:
            self.skipTest("zu wenige Picks im Bestand")
        self.assertGreater(feuer, 0, "streak_momentum feuert auf keinem einzigen echten Pick")
        self.assertGreater(feuer / n, 0.05,
                           f"nur {feuer} von {n} — zu selten, um je gemessen zu werden")

    def test_die_scores_bleiben_klein_genug_um_nichts_zu_drehen(self):
        d, idx, fix = self._welt()
        if not idx:
            self.skipTest("keine Serien im Bestand")
        sig = SM.StreakMomentumSignal()
        scores = []
        for mk, picks in (d.get("picks") or {}).items():
            if mk not in fix:
                continue
            h, a = fix[mk]
            ctx = {"streaks": idx, "home_id": h, "away_id": a}
            for p in picks or []:
                r = sig.evaluate(p, ctx)
                if r:
                    scores.append(abs(r.score))
        if not scores:
            self.skipTest("keine Feuerungen")
        self.assertLess(max(scores), 1.0,
                        "ein beobachtendes Signal darf keinen Pick drehen können")


if __name__ == "__main__":
    unittest.main()
