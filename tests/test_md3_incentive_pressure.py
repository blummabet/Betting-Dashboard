#!/usr/bin/env python3
"""
test_md3_incentive_pressure.py — MD3 Anreiz-/Schon-Mechanik (19.06.2026, Lucas)

Anlass MEX-CZE: MEX qualifiziert+gesichert (1. via direktes Duell), CZE must-win @1 Pkt —
pressure feuerte gar nicht (Must-Win nur bei 0 Pkt + Rotation strafte nur Heim-Pick).
Fixes: Must-Win aus Quali-Mathe; qualifiziert → Gegenseite boosten; Heim-WM-Host gedämpft;
Unter-Bias NUR über lineup (bestätigtes Schonen), dort verstärkt.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.pressure_index import PressureIndexSignal   # noqa: E402
from sharp_signals.lineup_signal import LineupSignal           # noqa: E402

# MEX 6 (1.), KOR 3, CZE 1, ZAF 1 nach 2 Spielen → MEX qualifiziert+gesichert, CZE must-win
_STANDINGS = {"A": [
    {"team": "MEX", "points": 6, "gd": 3, "gf": 3, "played": 2},
    {"team": "KOR", "points": 3, "gd": 0, "gf": 2, "played": 2},
    {"team": "CZE", "points": 1, "gd": -1, "gf": 2, "played": 2},
    {"team": "ZAF", "points": 1, "gd": -2, "gf": 1, "played": 2},
]}


def _ctx(home="MEX", away="CZE"):
    return {"home_id": home, "away_id": away, "group_id": "A",
            "standings": _STANDINGS, "matchday": 3}


class TestPressureMd3(unittest.TestCase):
    def setUp(self):
        self.p = PressureIndexSignal()

    def test_away_must_win_plus_coast_fires(self):
        # CZE must-win (1 Pkt!) + MEX qualifiziert (Heim-Host gedämpft) → X2/Auswärts geboostet
        r = self.p.evaluate({"market": "Doppelte Chance — X2"}, _ctx())
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 1.0)
        self.assertIn("Must-Win", r.evidence)
        self.assertIn("gedämpft", r.evidence)   # Heim-WM-Dämpfer sichtbar

    def test_home_win_penalised_by_rotation(self):
        r = self.p.evaluate({"market": "Heimsieg"}, _ctx())
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)              # MEX-Rotation straft Heimsieg

    def test_under_not_touched_by_pressure(self):
        # Unter kommt NICHT aus pressure (sondern aus lineup-Bestätigung)
        self.assertIsNone(self.p.evaluate({"market": "Unter 2.5 Tore"}, _ctx()))

    def test_coast_boost_not_dampened_for_non_host(self):
        # Auswärts qualifiziert (kein Host) → voller Schon-Boost für Heim, kein Dämpfer
        st = {"A": [
            {"team": "CZE", "points": 6, "gd": 3, "gf": 3, "played": 2},
            {"team": "MEX", "points": 1, "gd": -1, "gf": 2, "played": 2},
            {"team": "KOR", "points": 3, "gd": 0, "gf": 2, "played": 2},
            {"team": "ZAF", "points": 1, "gd": -2, "gf": 1, "played": 2},
        ]}
        r = self.p.evaluate({"market": "Heimsieg"},
                            {"home_id": "MEX", "away_id": "CZE", "group_id": "A",
                             "standings": st, "matchday": 3})
        self.assertIsNotNone(r)
        self.assertNotIn("gedämpft", r.evidence)   # CZE auswärts qualifiziert → kein Heim-WM-Dämpfer


class TestLineupCoastAmplify(unittest.TestCase):
    def setUp(self):
        self.l = LineupSignal()

    def test_home_host_qualified_dampened(self):
        fh, fa = self.l._coast_amplify("MEX", "CZE", _ctx())
        self.assertAlmostEqual(fh, self.l._t["coast_off_amplify_home_wc"])  # Heim-Host gedämpft
        self.assertEqual(fa, 1.0)                                           # CZE nicht qualifiziert

    def test_away_qualified_full_amplify(self):
        fh, fa = self.l._coast_amplify("CZE", "MEX", _ctx())   # MEX jetzt auswärts
        self.assertEqual(fh, 1.0)
        self.assertAlmostEqual(fa, self.l._t["coast_off_amplify"])         # voll (nicht daheim)

    def test_no_amplify_outside_md3(self):
        c = _ctx(); c["matchday"] = 2
        self.assertEqual(self.l._coast_amplify("MEX", "CZE", c), (1.0, 1.0))

    def test_no_amplify_without_standings(self):
        self.assertEqual(self.l._coast_amplify("MEX", "CZE", {"matchday": 3}), (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
