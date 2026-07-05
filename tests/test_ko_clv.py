#!/usr/bin/env python3
"""test_ko_clv.py — KO-CLV-Erfassung (04.07.2026, Lucas/Fable-Audit: „KO-CLV tot, 0/16 positiv").

build_result_lookup iterierte nur groups → K.-o.-Spiele (koFixtures) fehlten im Lookup →
resolve_steam_clv setzte clvPP nie → das performende R32-Segment lief auf totem CLV-Sensor.
Dieser Test friert die KO-Abdeckung ein + prüft die Liga-Neutralität (keine koFixtures → No-Op)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestKoInResultLookup(unittest.TestCase):
    def _wm(self):
        # KO-Spiel mit Ergebnis + Closing-1X2-Odds (pre-match), plus ein Gruppen-Spiel.
        closing = {"hw": 1.8, "dr": 3.6, "aw": 4.5}
        return {
            "groups": {"A": {"fixtures": [
                {"home": "MEX", "away": "ZAF", "kickoff": "2026-06-11T18:00:00Z",
                 "result": {"status": "FT", "home_score": 2, "away_score": 0}}]}},
            "koFixtures": [
                {"home": "BRA", "away": "JPN", "round": "R32", "kickoff": "2026-06-29T17:00:00Z",
                 "result": {"status": "FT", "home_score": 2, "away_score": 1}}],
            "odds": {
                "MEX-ZAF": {"odds_closing": closing},
                "BRA-JPN": {"odds_closing": closing},
            },
        }

    def test_ko_fixture_im_lookup(self):
        import resolve_wm_results as R
        lk = R.build_result_lookup(self._wm())
        self.assertIn("BRA-JPN", lk)          # war vorher NIE drin
        self.assertIn("MEX-ZAF", lk)          # Gruppe weiter da
        self.assertIsNotNone(lk["BRA-JPN"].get("_pinn_close_hw"))   # Closing devigged

    def test_ko_steam_pick_bekommt_clv(self):
        import resolve_wm_results as R, resolve_steam_clv as C
        wm = self._wm()
        wm["picks"] = {"KO-R32-BRA-JPN": [
            {"source": "steam", "market": "Heimsieg", "odds": 2.10, "entryOdd": 2.10,
             "result": "WIN"}]}
        n = C.resolve(wm)
        self.assertGreaterEqual(n, 1)
        clv = wm["picks"]["KO-R32-BRA-JPN"][0].get("clvPP")
        self.assertIsInstance(clv, (int, float))
        self.assertNotEqual(clv, 0)           # echter CLV statt totem 0

    def test_liga_ohne_ko_kein_crash(self):
        # Liga/MLS haben keine koFixtures → synthetische leere Gruppe → No-Op, kein Fehler
        import resolve_wm_results as R
        liga = {"groups": {}, "odds": {}}   # kein koFixtures-Key
        self.assertEqual(R.build_result_lookup(liga), {})


if __name__ == "__main__":
    unittest.main()
