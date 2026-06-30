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


class TestFillKoOpponents(unittest.TestCase):
    """29.06.2026 (Lucas: GER-PRY ohne Card): offene KO-Gegner-Slots aus echten API-Paarungen füllen."""

    def _af_round(self, hid, aid, rnd):
        return {"league": {"round": rnd}, "teams": {"home": {"id": hid}, "away": {"id": aid}}}

    def test_fills_best_third_opponent(self):
        wm = {"koFixtures": [{"round": "R32", "home": "GER", "away": None,
                              "homeResolved": True, "awayResolved": False, "bothResolved": False}]}
        api = [self._af_round(10, 20, "Round of 32")]
        n = fmr.fill_ko_opponents_from_api(wm, api, {"GER": 10, "PRY": 20})
        self.assertEqual(n, 1)
        self.assertEqual(wm["koFixtures"][0]["away"], "PRY")
        self.assertTrue(wm["koFixtures"][0]["bothResolved"])

    def test_ignores_group_stage_pairing(self):
        wm = {"koFixtures": [{"round": "R32", "home": "GER", "away": None}]}
        api = [self._af_round(10, 99, "Group Stage - 3")]
        self.assertEqual(fmr.fill_ko_opponents_from_api(wm, api, {"GER": 10, "X": 99}), 0)
        self.assertIsNone(wm["koFixtures"][0]["away"])

    def test_complete_or_both_open_skipped(self):
        wm = {"koFixtures": [
            {"round": "R32", "home": "GER", "away": "PRY"},   # komplett
            {"round": "R32", "home": None, "away": None},      # beide offen
        ]}
        api = [self._af_round(10, 20, "Round of 32")]
        self.assertEqual(fmr.fill_ko_opponents_from_api(wm, api, {"GER": 10, "PRY": 20}), 0)


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
