#!/usr/bin/env python3
"""Tests für validate_wm_picks.py — Cross-Market-Check + Sanity-Checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestModuleImports(unittest.TestCase):
    """Sicherstellen dass refaktorierte Imports drin sind."""

    def test_module_loads(self):
        import validate_wm_picks
        self.assertTrue(hasattr(validate_wm_picks, "validate_cross_market"))

    def test_uses_pick_constants(self):
        src = (Path(__file__).parent.parent / "validate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("from pick_constants import", src,
            "validate_wm_picks muss pick_constants importieren")
        self.assertNotIn("DIRECTION_MAP = {", src,
            "Inline DIRECTION_MAP darf nicht mehr existieren")
        self.assertNotIn("INCOMPATIBLE = {", src,
            "Inline INCOMPATIBLE darf nicht mehr existieren")

    def test_uses_is_legitimate_pick(self):
        src = (Path(__file__).parent.parent / "validate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("is_legitimate_pick", src,
            "validate_wm_picks muss is_legitimate_pick verwenden")


class TestCrossMarketValidator(unittest.TestCase):
    """E_CROSS_MARKET feuert bei BET-BET-Konflikten."""

    def setUp(self):
        from validate_wm_picks import validate_cross_market
        self.fn = validate_cross_market

    def test_no_conflict_for_orthogonal_bets(self):
        picks = [
            {"market": "Heimsieg",      "verdict": "BET"},
            {"market": "Über 2.5 Tore", "verdict": "BET"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["level"] == "error"]
        self.assertEqual(len(errors), 0,
            "Heimsieg + Über sind orthogonal — kein Error")

    def test_conflict_for_incompatible_bets(self):
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "BET"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 1,
            "Heimsieg + AH Aus = unvereinbar → Error muss feuern")

    def test_no_conflict_for_abwaegen(self):
        """ABWÄGEN-Picks lösen keine Errors aus (nur BET wird geprüft)."""
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "ABWÄGEN"},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 0)

    def test_tracking_excluded_ignored(self):
        """trackingExcluded BET-Picks werden nicht als Konflikt-Quelle gewertet."""
        picks = [
            {"market": "Heimsieg",          "verdict": "BET"},
            {"market": "AH Auswärts +0.5",  "verdict": "BET", "trackingExcluded": True},
        ]
        issues = []
        self.fn("test-mk", picks, issues)
        errors = [i for i in issues if i["code"] == "E_CROSS_MARKET"]
        self.assertEqual(len(errors), 0,
            "trackingExcluded Pick wird ignoriert — kein Konflikt-Error")


class TestHomeawaySwapFinishedSkip(unittest.TestCase):
    """E_HOMEAWAY_SWAP: abgelaufene Spiele raus + Poly-Tie als no-signal (22.06.2026)."""

    def _wm(self, *, finished, poly=(0.0, 1.0, 0.0), kickoff="2030-01-01T00:00:00Z"):
        # 1X2 Heim-Favorit (hw<aw), Poly degeneriert → würde ohne Fix fälschlich Swap melden
        result = {"status": "FT", "winner": "draw"} if finished else None
        fx = {"home": "BEL", "away": "IRN", "kickoff": kickoff, "result": result}
        return {
            "groups": {"B": {"fixtures": [fx]}},
            "odds": {"BEL-IRN": {"hw": 4.0, "aw": 5.2, "dc1X": 1.03, "dcX2": 1.03,
                                 "poly_hw": poly[0], "poly_dr": poly[1], "poly_aw": poly[2]}},
        }

    def _run(self, wm):
        import validate_wm_picks as V
        V._FIXTURE_INDEX = V._build_fixture_index(wm)
        issues = []
        V.validate_homeaway_swap(wm, issues)
        return [i for i in issues if i["code"] == "E_HOMEAWAY_SWAP"]

    def test_finished_match_no_swap_alarm(self):
        self.assertEqual(self._run(self._wm(finished=True)), [])

    def test_kickoff_passed_no_swap_alarm(self):
        self.assertEqual(
            self._run(self._wm(finished=False, kickoff="2020-01-01T00:00:00Z")), [])

    def test_poly_tie_is_no_signal(self):
        # live, aber Poly 0/0 (tie) → keine Richtung → kein Alarm (DC ist hier auch tie)
        self.assertEqual(self._run(self._wm(finished=False, poly=(0.0, 0.0, 0.0))), [])

    def test_live_genuine_swap_still_flagged(self):
        # live, 1X2 Heim-Favorit aber Poly klar Auswärts-Favorit → echter Swap, MUSS feuern
        wm = self._wm(finished=False, poly=(0.20, 0.20, 0.60))
        self.assertEqual(len(self._run(wm)), 1)

    def test_finished_ko_fixture_no_swap_alarm(self):
        # 04.07.2026 (Lucas: „E_HOMEAWAY_SWAP-Push für BRA-JPN"): fertiges KO-Spiel liegt in
        # koFixtures (nicht groups). Ohne KO im Fixture-Index fand _fx_for_key nichts → fertiges
        # Spiel wurde nicht ausgenommen → Swap-Alarm auf veraltetem Post-Match-DC-Snapshot.
        wm = {
            "groups": {},
            "koFixtures": [{"home": "BRA", "away": "JPN", "round": "R32",
                            "kickoff": "2026-06-29T17:00:00Z",
                            "result": {"status": "FT", "winner": "BRA"}}],
            # 1X2 Heim-Favorit, aber DC spiegelverkehrt (dc1X>dcX2) → würde ohne Fix feuern
            "odds": {"BRA-JPN": {"hw": 2.04, "aw": 4.5, "dc1X": 1.55, "dcX2": 1.24}},
        }
        self.assertEqual(self._run(wm), [])


class TestNegativeClvFinishedAndSteam(unittest.TestCase):
    """W_NEGATIVE_CLV: nicht auf fertigen Spielen; Steam-Wording (22.06.2026)."""

    def _wm(self, finished):
        result = {"status": "FT", "winner": "MAR"} if finished else None
        fx = {"home": "SCO", "away": "MAR", "kickoff": "2030-01-01T00:00:00Z", "result": result}
        return {"groups": {"C": {"fixtures": [fx]}}, "odds": {}}

    def _pick(self, steam):
        p = {"market": "Auswärtssieg", "odds": 1.67, "verdict": "BET",
             "edgePP": -3, "clvPP": -3.96}
        if steam:
            p.update({"source": "steam", "dataQuality": "steam",
                      "steamMovePP": 4.0, "convictionScore": 8})
        else:
            p["edgePP"] = 3        # sonst feuert E_VERDICT_NO_EDGE separat
        return p

    def _clv(self, wm, pick):
        import validate_wm_picks as V
        V._FIXTURE_INDEX = V._build_fixture_index(wm)
        issues = []
        V.validate_pick("C-2-SCO-MAR", pick, wm, issues)
        return [i for i in issues if i["code"] == "W_NEGATIVE_CLV"]

    def test_finished_steam_no_clv_warning(self):
        self.assertEqual(self._clv(self._wm(True), self._pick(steam=True)), [])

    def test_live_steam_warns_without_mispick_wording(self):
        w = self._clv(self._wm(False), self._pick(steam=True))
        self.assertEqual(len(w), 1)
        self.assertNotIn("falsch gepickt", w[0]["message"])
        self.assertIn("Close", w[0]["message"])

    def test_live_nonsteam_keeps_mispick_wording(self):
        w = self._clv(self._wm(False), self._pick(steam=False))
        self.assertEqual(len(w), 1)
        self.assertIn("falsch gepickt", w[0]["message"])


class TestLiveDataValidation(unittest.TestCase):
    """Smoketest auf echten WM-Daten — sollte sauber laufen."""

    def test_live_picks_validate_clean(self):
        import json
        from validate_wm_picks import validate_pick, validate_cross_market

        data_path = Path(__file__).parent.parent / "wm2026-data.json"
        if not data_path.exists():
            self.skipTest("wm2026-data.json fehlt")

        with open(data_path, encoding="utf-8") as f:
            wm = json.load(f)

        issues = []
        for mk, plist in wm.get("picks", {}).items():
            if not isinstance(plist, list): continue
            for p in plist:
                validate_pick(mk, p, wm, issues)
            validate_cross_market(mk, plist, issues)

        errors = [i for i in issues if i["level"] == "error"]
        # Generator sollte alle Konflikte schon abgefangen haben → 0 Errors
        self.assertEqual(len(errors), 0,
            f"Validator hat {len(errors)} Errors gefunden — Generator-Bug?")


if __name__ == "__main__":
    unittest.main()
