"""
tests/test_fetch_wm_match_results.py — Regression für den Result-Resolver.

Kern-Bug 12.06.2026: teamIds ist FLACH ({"MEX": 16}), match_fixture las es als
{"MEX": {"apiFootball": 16}} → .get() auf int crashte → JEDES Matching schlug fehl
→ FT-Ergebnisse (MEX-ZAF 2:0) wurden NIE in wm2026-data geschrieben (blieb NS).
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("fmr", REPO / "fetch_wm_match_results.py")
fmr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fmr)


def _af(home_id, away_id, home_name="Mexico", away_name="South Africa"):
    return {"teams": {"home": {"id": home_id, "name": home_name},
                      "away": {"id": away_id, "name": away_name}}}


class TestApiId(unittest.TestCase):
    def test_flat_int(self):
        self.assertEqual(fmr._api_id({"MEX": 16}, "MEX"), "16")

    def test_nested_dict(self):
        self.assertEqual(fmr._api_id({"MEX": {"apiFootball": 16}}, "MEX"), "16")

    def test_missing(self):
        self.assertEqual(fmr._api_id({}, "MEX"), "")


class TestMatchFixture(unittest.TestCase):
    def test_match_flat_teamids(self):
        # Echte Struktur: flach. Muss matchen (vorher crashte es → False/Skip).
        ti = {"MEX": 16, "ZAF": 1531}
        self.assertTrue(fmr.match_fixture(_af(16, 1531), "MEX", "ZAF", ti))

    def test_match_nested_teamids_backcompat(self):
        ti = {"MEX": {"apiFootball": 16}, "ZAF": {"apiFootball": 1531}}
        self.assertTrue(fmr.match_fixture(_af(16, 1531), "MEX", "ZAF", ti))

    def test_no_match_wrong_id(self):
        ti = {"MEX": 16, "ZAF": 1531}
        self.assertFalse(fmr.match_fixture(_af(99, 1531), "MEX", "ZAF", ti))

    def test_league_name_is_world_cup(self):
        # APIF-Liga heißt "World Cup", nicht "FIFA World Cup".
        import inspect
        src = inspect.getsource(fmr.find_wm_league_id)
        self.assertIn("name=World+Cup", src)
        self.assertNotIn("FIFA+World+Cup", src)


if __name__ == "__main__":
    unittest.main()
