#!/usr/bin/env python3
"""
test_clv_inplay_guard.py — In-Play-Schutz für den CLV (16.06.2026).

Bug (QAT-SUI): kein pre-match Closing-Snapshot → der last_known-Fallback fror
2h nach Anpfiff LIVE-Quoten ein (o25=21.0, hw=81.0 bei spätem 1:1). Daraus
pinnClose=0.0139 → clvPP=−55.11, das den Dashboard-avgCLV auf −55 zog.

Drei-Schichten-Fix:
  1. resolve_wm_results.closing_is_prematch — Lese-Seite verwirft post-Anpfiff-Snaps.
  2. fetch_wm_odds: last_known-Fallback friert nur bis +15min nach Anpfiff ein.
  3. wm_data_integrity.check_closing_prematch — macht In-Play-Lecks sichtbar.
  Bonus: check_venue_matches_schedule ignoriert reine Stadt-Label-Unterschiede.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import resolve_wm_results as R
import wm_data_integrity as I


KO = "2026-06-13T19:00:00Z"


class TestClosingIsPrematch(unittest.TestCase):
    def test_inplay_snapshot_rejected(self):
        # QAT-SUI: frozenAt 2h03 nach Anpfiff → In-Play
        snap = {"o25": 21.0, "u25": 1.01, "frozenAt": "2026-06-13T21:03:24Z"}
        self.assertFalse(R.closing_is_prematch(snap, KO))

    def test_prematch_snapshot_accepted(self):
        snap = {"o25": 1.9, "u25": 1.95, "frozenAt": "2026-06-13T17:30:00Z"}
        self.assertTrue(R.closing_is_prematch(snap, KO))

    def test_within_tolerance_accepted(self):
        # +8min nach Anpfiff (Anpfiff-Ungenauigkeit) → noch ok
        snap = {"o25": 1.9, "u25": 1.95, "frozenAt": "2026-06-13T19:08:00Z"}
        self.assertTrue(R.closing_is_prematch(snap, KO))

    def test_no_frozenat_accepted(self):
        # nicht verifizierbar → kein Regress gegenüber Altbestand
        self.assertTrue(R.closing_is_prematch({"o25": 1.9}, KO))

    def test_no_kickoff_accepted(self):
        snap = {"o25": 21.0, "frozenAt": "2026-06-13T21:03:24Z"}
        self.assertTrue(R.closing_is_prematch(snap, None))

    def test_empty_closing_false(self):
        self.assertFalse(R.closing_is_prematch({}, KO))


class TestPinnCloseNotPoisoned(unittest.TestCase):
    """Integration: verwirft build_result_lookup einen In-Play-Closing-Snapshot?"""

    def _wm(self, frozen):
        return {
            "groups": {"A": {"fixtures": [{
                "home": "QAT", "away": "SUI", "kickoff": KO,
                "result": {"status": "FT", "home_score": 1, "away_score": 1,
                           "winner": "draw"},
            }]}},
            "odds": {"QAT-SUI": {"odds_closing": {
                "o25": 21.0, "u25": 1.01, "hw": 81.0, "dr": 1.06, "aw": 11.0,
                "frozenAt": frozen,
            }}},
        }

    def test_inplay_closing_yields_no_clv(self):
        lk = R.build_result_lookup(self._wm("2026-06-13T21:03:24Z"))
        res = lk["QAT-SUI"]
        # In-Play verworfen → kein O25-Closing → CLV nicht berechenbar
        self.assertIsNone(res.get("_pinn_close_o25"))
        self.assertIsNone(R.get_pinn_close_for_market(res, "Over 2.5 Tore"))

    def test_prematch_closing_yields_clv(self):
        wm = self._wm("2026-06-13T17:00:00Z")
        wm["odds"]["QAT-SUI"]["odds_closing"].update({"o25": 1.95, "u25": 1.95})
        lk = R.build_result_lookup(wm)
        pc = R.get_pinn_close_for_market(lk["QAT-SUI"], "Over 2.5 Tore")
        self.assertIsNotNone(pc)
        self.assertTrue(0.4 < pc < 0.6)   # sane, ~0.5


class TestVenueGuardCityLabels(unittest.TestCase):
    """Reine Stadt-Label-Unterschiede (gleiches venue_id) sind KEIN Fehler."""

    def _ctx(self, fx_venue, sched_venue):
        wm = {"groups": {"A": {"fixtures": [
            {"home": "QAT", "away": "SUI", "venue": fx_venue}]}}}
        sched = {"QAT-SUI": {"venue": sched_venue}}
        return I.IntegrityCtx(wm, {}, sched, {"venues": {}})

    def test_same_stadium_different_city_ok(self):
        ctx = self._ctx("SoFi Stadium, Inglewood", "SoFi Stadium, Los Angeles")
        out = I.check_venue_matches_schedule(ctx)
        self.assertTrue(out["ok"])
        self.assertEqual(out["severity"], "warn")

    def test_levis_label_noise_ok(self):
        ctx = self._ctx("Levi's Stadium, Santa Clara",
                        "Levi's Stadium, San Francisco Bay Area")
        self.assertTrue(I.check_venue_matches_schedule(ctx)["ok"])

    def test_real_wrong_stadium_fails(self):
        # echtes falsches Stadion: verschiedene venue_id (SoFi=LA vs Akron=Guadalajara)
        ctx = self._ctx("SoFi Stadium, Inglewood", "Estadio Akron, Guadalajara")
        out = I.check_venue_matches_schedule(ctx)
        self.assertFalse(out["ok"])
        self.assertEqual(out["severity"], "warn")


if __name__ == "__main__":
    unittest.main()
