#!/usr/bin/env python3
"""
test_qual_state_attach.py — MD3-Qualifikations-Status korrekt pro Fixture (23.06.2026, Lucas).

Der Renderer zeigte „schon Achtelfinale/bereits sicher" anhand der Tabellen-POSITION → Teams mit
2–3 Punkten auf Platz 2 galten fälschlich als sicher (Iran, Uruguay, Korea, Elfenbeinküste).
Fix: generate_wm_picks._attach_qualification_states hängt den mathematisch korrekten Status
(incentive_signal._compute_qualification_state) ans Fixture; der Renderer zeigt ihn nur noch an.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.incentive_signal import _compute_qualification_state  # noqa: E402
import generate_wm_picks as G  # noqa: E402


def _row(team, played, points, gd):
    return {"team": team, "played": played, "points": points, "gd": gd}


class TestQualMathRealCases(unittest.TestCase):
    """Echte Schlussrunden-Tabellen — die Karten-Fehler dürfen nicht mehr passieren."""

    def test_iran_2pts_not_qualified(self):
        # Gruppe G: EGY 4, IRN 2, BEL 2, NZL 1 — Iran (Platz 2) ist NICHT sicher
        st = {"G": [_row("EGY", 2, 4, 2), _row("IRN", 2, 2, 0),
                    _row("BEL", 2, 2, 0), _row("NZL", 2, 1, -2)]}
        s = _compute_qualification_state("IRN", "G", 3, st)
        self.assertFalse(s["qualified"], "Iran mit 2 Pkt darf nicht 'qualified' sein")

    def test_korea_3pts_pos2_not_qualified(self):
        # Gruppe A: MEX 6, KOR 3, CZE 1, ZAF 1 — Korea (Platz 2) noch schlagbar
        st = {"A": [_row("MEX", 2, 6, 3), _row("KOR", 2, 3, 0),
                    _row("CZE", 2, 1, -1), _row("ZAF", 2, 1, -2)]}
        s = _compute_qualification_state("KOR", "A", 3, st)
        self.assertFalse(s["qualified"], "Korea mit 3 Pkt darf nicht 'bereits sicher' sein")

    def test_both_6pts_locked_qualified(self):
        # Gruppe I: FRA 6, NOR 6 — beide mathematisch durch
        st = {"I": [_row("FRA", 2, 6, 5), _row("NOR", 2, 6, 4),
                    _row("SEN", 2, 0, -3), _row("IRQ", 2, 0, -6)]}
        self.assertTrue(_compute_qualification_state("FRA", "I", 3, st)["qualified"])
        self.assertTrue(_compute_qualification_state("NOR", "I", 3, st)["qualified"])


class TestAttachToFixtures(unittest.TestCase):
    def test_attach_sets_qual_fields_on_md3(self):
        wm = {
            "standings": {"G": [_row("EGY", 2, 4, 2), _row("IRN", 2, 2, 0),
                                _row("BEL", 2, 2, 0), _row("NZL", 2, 1, -2)]},
            "groups": {"G": {"fixtures": [
                {"matchday": 3, "home": "EGY", "away": "IRN"},
                {"matchday": 2, "home": "BEL", "away": "NZL"},  # nicht MD3 → kein Attach
            ]}},
        }
        G._attach_qualification_states(wm)
        md3 = wm["groups"]["G"]["fixtures"][0]
        self.assertIn("qualHome", md3)
        self.assertIn("qualAway", md3)
        self.assertFalse(md3["qualAway"]["qualified"])   # Iran nicht sicher
        self.assertNotIn("qualHome", wm["groups"]["G"]["fixtures"][1])  # MD2 unberührt

    def test_no_standings_no_crash(self):
        wm = {"groups": {"G": {"fixtures": [{"matchday": 3, "home": "A", "away": "B"}]}}}
        G._attach_qualification_states(wm)   # darf nicht crashen
        self.assertNotIn("qualHome", wm["groups"]["G"]["fixtures"][0])


if __name__ == "__main__":
    unittest.main()
