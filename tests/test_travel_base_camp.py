#!/usr/bin/env python3
"""
test_travel_base_camp.py — Base-Camp-Travel-Modell + Carry-over (15.06.2026, Lucas)

Schützt drei Dinge:
  · Befund 1: jeder Spieltag (auch MD1) hat eine Reise-Last (Base Camp → Stadion).
  · Befund 2: Carry-over — Rest-Müdigkeit aus dem vorigen Trip wird mitgeschleppt.
  · Befund 3: travel_factor mappt die echten Labels (critical/significant/moderate),
    nicht die toten high/medium-Zweige.
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestBaseCampData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bc = json.loads((REPO / "wm_base_camps.json").read_text(encoding="utf-8"))["camps"]
        wm = json.loads((REPO / "wm2026-data.json").read_text(encoding="utf-8"))
        cls.teams = {t["id"] for g in wm["groups"].values() for t in g.get("teams", [])}

    def test_all_48_teams_have_base_camp(self):
        missing = self.teams - set(self.bc)
        self.assertEqual(missing, set(), f"Base Camp fehlt für: {sorted(missing)}")

    def test_coords_plausible(self):
        for tid, c in self.bc.items():
            self.assertTrue(-90 <= c["lat"] <= 90, f"{tid} lat out of range")
            self.assertTrue(-180 <= c["lon"] <= 180, f"{tid} lon out of range")
            self.assertIn(c["country"], ("USA", "Mexiko", "Kanada"), f"{tid} country")


class TestTravelFactorLabels(unittest.TestCase):
    """Befund 3: Label-Mapping. travel_factor(team, matchday, travel_data)."""

    @classmethod
    def setUpClass(cls):
        import generate_wm_picks as g
        cls.g = g   # über das Modul aufrufen → keine Methoden-Bindung

    def tf(self, *a):
        return self.g.travel_factor(*a)

    def _td(self, burden, km=1000, eff=None, rest=4, alt=0):
        return {"X": {"legs": [{
            "matchday_to": 2, "burden": burden, "km": km,
            "effective_km": eff if eff is not None else km,
            "rest_days": rest, "alt_shift": alt, "same_venue": False,
        }]}}

    def test_critical_maps_85(self):
        f, _ = self.tf("X", 2, self._td("critical"))
        self.assertAlmostEqual(f, 0.85, places=2)

    def test_significant_maps_90(self):
        # Vorher fiel 'significant' in den km-Fallback (toter high-Zweig). Jetzt 0.90.
        f, _ = self.tf("X", 2, self._td("significant"))
        self.assertAlmostEqual(f, 0.90, places=2)

    def test_moderate_maps_95(self):
        f, _ = self.tf("X", 2, self._td("moderate"))
        self.assertAlmostEqual(f, 0.95, places=2)

    def test_low_and_none_no_discount(self):
        self.assertAlmostEqual(self.tf("X", 2, self._td("low"))[0], 1.0, places=2)
        self.assertAlmostEqual(self.tf("X", 2, self._td("none"))[0], 1.0, places=2)

    def test_unknown_label_uses_effective_km_fallback(self):
        # Carry-over: hohe effektive Last trotz kleiner Eigen-km → Fallback greift via eff
        f, _ = self.tf("X", 2, self._td("???", km=200, eff=3200, rest=2))
        self.assertAlmostEqual(f, 0.85, places=2)

    def test_no_leg_for_matchday_neutral(self):
        td = {"X": {"legs": [{"matchday_to": 3, "burden": "critical"}]}}
        self.assertEqual(self.tf("X", 2, td), (1.0, ""))


class TestComputeModel(unittest.TestCase):
    """Output-Invarianten des regenerierten wm_travel_burden.json."""

    @classmethod
    def setUpClass(cls):
        p = REPO / "wm_travel_burden.json"
        if not p.exists():
            raise unittest.SkipTest("wm_travel_burden.json fehlt — compute_wm_travel_burden.py laufen lassen")
        cls.d = json.loads(p.read_text(encoding="utf-8"))

    def test_every_team_has_md1_leg(self):
        # Befund 1: MD1 darf nicht mehr ohne Reise-Last sein
        for tid, r in self.d.items():
            md1 = [l for l in r["legs"] if l.get("matchday_to") == 1 and "error" not in l]
            self.assertTrue(md1, f"{tid} hat kein MD1-Leg")

    def test_carry_over_present_and_nonneg(self):
        # Befund 2: carry_km existiert, ist nie negativ, MD1 hat carry 0
        for tid, r in self.d.items():
            for l in r["legs"]:
                if "error" in l:
                    continue
                self.assertGreaterEqual(l.get("carry_km", 0), 0, f"{tid} negativ carry")
                self.assertGreaterEqual(l.get("effective_km", 0), l.get("km", 0),
                                        f"{tid} eff < km")
                if l["matchday_to"] == 1:
                    self.assertEqual(l.get("carry_km", 0), 0, f"{tid} MD1 carry≠0")

    def test_score_spread_not_saturated(self):
        scores = [r["burden_score"] for r in self.d.values()]
        # Re-kalibrierung: nicht alles bei 10 kleben
        self.assertLess(max(scores), 11)
        self.assertGreater(len(set(scores)), 4, "Score differenziert zu wenig")


if __name__ == "__main__":
    unittest.main()
