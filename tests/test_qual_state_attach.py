#!/usr/bin/env python3
"""
test_qual_state_attach.py — szenario-basierter MD3-Qualifikations-Status (23.06.2026, Lucas).

Der Renderer zeigte „England braucht einen Sieg für den besten Dritten" — Blödsinn, England spielt
um Platz 1. Ursache: die alte Mathe summierte die Max-Punkte ALLER anderen unabhängig (die spielen
aber gegeneinander). Fix: _md3_qual_status rechnet die 2 Rest-Spiele durch (3×3) und achtet auf
Platz 1+2, nicht nur „bester Dritter".
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G  # noqa: E402


def _row(team, points, gd, played=2):
    return {"team": team, "played": played, "points": points, "gd": gd}


def _wm(group, rows, remaining):
    fixtures = [{"home": h, "away": a, "matchday": 3, "result": None} for h, a in remaining]
    return {"standings": {group: rows}, "groups": {group: {"fixtures": fixtures}}}


class TestMd3QualStatus(unittest.TestCase):
    def test_leader_not_third_chase(self):
        # Gruppe L: ENG 4, GHA 4, CRO 3, PAN 0 — Rest: ENG-PAN, CRO-GHA
        wm = _wm("L", [_row("ENG", 4, 2), _row("GHA", 4, 1), _row("CRO", 3, -1), _row("PAN", 0, -2)],
                 [("ENG", "PAN"), ("CRO", "GHA")])
        eng = G._md3_qual_status(wm, "L", "ENG")["label"]
        self.assertIn(eng, ("qualified", "leader_can_draw"))
        self.assertNotEqual(eng, "third_chase")          # DAS war der Bug
        # PAN 0 Pkt, max 3 → kein realistischer bester Dritter → eliminated
        self.assertEqual(G._md3_qual_status(wm, "L", "PAN")["label"], "eliminated")
        self.assertEqual(G._md3_qual_status(wm, "L", "CRO")["label"], "win_secures_top2")

    def test_win_secures_not_third_chase(self):
        # Gruppe A: MEX 6, KOR 3, CZE 1, ZAF 1 — Rest: MEX-CZE, ZAF-KOR
        wm = _wm("A", [_row("MEX", 6, 3), _row("KOR", 3, 0), _row("CZE", 1, -1), _row("ZAF", 1, -2)],
                 [("MEX", "CZE"), ("ZAF", "KOR")])
        self.assertEqual(G._md3_qual_status(wm, "A", "MEX")["label"], "qualified")
        self.assertEqual(G._md3_qual_status(wm, "A", "KOR")["label"], "win_secures_top2")
        self.assertEqual(G._md3_qual_status(wm, "A", "CZE")["label"], "must_win_top2")

    def test_both_leaders_locked(self):
        # Gruppe I: FRA 6, NOR 6 → beide durch
        wm = _wm("I", [_row("FRA", 6, 5), _row("NOR", 6, 4), _row("SEN", 0, -3), _row("IRQ", 0, -6)],
                 [("FRA", "NOR"), ("SEN", "IRQ")])
        self.assertEqual(G._md3_qual_status(wm, "I", "FRA")["label"], "qualified")
        self.assertEqual(G._md3_qual_status(wm, "I", "NOR")["label"], "qualified")
        self.assertEqual(G._md3_qual_status(wm, "I", "SEN")["label"], "eliminated")

    def test_attach_writes_new_labels(self):
        wm = _wm("L", [_row("ENG", 4, 2), _row("GHA", 4, 1), _row("CRO", 3, -1), _row("PAN", 0, -2)],
                 [("ENG", "PAN"), ("CRO", "GHA")])
        G._attach_qualification_states(wm)
        fx = wm["groups"]["L"]["fixtures"][0]   # ENG-PAN
        self.assertIn("qualHome", fx)
        self.assertNotEqual(fx["qualHome"]["label"], "third_chase")  # England nie „bester Dritter"


if __name__ == "__main__":
    unittest.main()
