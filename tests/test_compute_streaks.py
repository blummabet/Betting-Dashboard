#!/usr/bin/env python3
"""test_compute_streaks.py — Serien-Erkennung + Continuation (28.06.2026)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import compute_streaks as S  # noqa: E402


def _wm(form):
    return {"groups": {"ENG": {"name": "Premier League",
                               "teams": [{"id": "42", "name": "Arsenal"}, {"id": "50", "name": "City"}]}},
            "form": form}


class TestStreaks(unittest.TestCase):
    def test_lead_run(self):
        self.assertEqual(S._lead_run([True, True, True, False, True], True), 3)
        self.assertEqual(S._lead_run([False, True, True], True), 0)   # jüngstes passt nicht
        self.assertEqual(S._lead_run([False, False, False], False), 3)

    def test_over_streak_detected_with_continuation(self):
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "bttsSeq": [False, True, False],
                         "over25Rate": 0.75, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = [s for s in out["streaks"] if s["type"] == "over25"]
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0]["length"], 4)
        self.assertEqual(over[0]["team"], "Arsenal")
        self.assertEqual(over[0]["league"], "ENG")
        self.assertEqual(over[0]["continuation"]["state"], "intakt")   # 75% stützt
        # under25 darf NICHT erscheinen (jüngstes Spiel war Über)
        self.assertEqual([s for s in out["streaks"] if s["type"] == "under25"], [])

    def test_short_streak_filtered(self):
        wm = _wm({"42": {"o25Seq": [True, True, False], "over25Rate": 0.6, "bttsRate": 0.5}})
        self.assertEqual(S.build_streaks(wm)["streaks"], [])   # nur 2 < MIN_LEN

    def test_btts_no_streak_wobbles_against_baseline(self):
        # 3× kein BTTS in Folge, aber Grundrate BTTS 70% → Serie läuft gegen die Rate → wackelt
        wm = _wm({"50": {"o25Seq": [True, False], "bttsSeq": [False, False, False],
                         "over25Rate": 0.5, "bttsRate": 0.7}})
        out = S.build_streaks(wm)
        bn = [s for s in out["streaks"] if s["type"] == "bttsNo"]
        self.assertEqual(len(bn), 1)
        self.assertEqual(bn[0]["continuation"]["state"], "wackelt")

    def test_corner_streak_from_cornersform(self):
        wm = _wm({})
        wm["cornersForm"] = {"42": {"cornerLine": 9.5, "overLineRate": 0.7,
                                    "cornerOverSeq": [True, True, True, True, False]}}
        out = S.build_streaks(wm)
        co = [s for s in out["streaks"] if s["type"] == "cornersOver"]
        self.assertEqual(len(co), 1)
        self.assertEqual(co[0]["length"], 4)
        self.assertEqual(co[0]["team"], "Arsenal")
        self.assertIn("9,5 Ecken", co[0]["market"])
        self.assertEqual(co[0]["continuation"]["state"], "intakt")   # 70% stützt
        self.assertEqual([s for s in out["streaks"] if s["type"] == "cornersUnder"], [])

    def test_venue_split_home_streak(self):
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "venueSeq": ["H", "A", "H", "H"],
                         "over25Rate": 0.7, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = {s["venue"]: s["length"] for s in out["streaks"] if s["type"] == "over25"}
        self.assertEqual(over.get("all"), 4)
        self.assertEqual(over.get("H"), 3)        # Heimspiele (Index 0,2,3) alle Über
        self.assertNotIn("A", over)               # nur 1 Auswärts → < MIN_LEN

    def test_scored_and_cleansheet_markets(self):
        wm = _wm({"42": {"scoredSeq": [True, True, True], "scoredRate": 0.9,
                         "csSeq": [True, True, True], "cleanSheetRate": 0.5}})
        out = S.build_streaks(wm)
        self.assertTrue(any(s["type"] == "scored" and s["market"] == "Team trifft" for s in out["streaks"]))
        self.assertTrue(any(s["type"] == "cleanSheet" for s in out["streaks"]))

    def test_card_streak_from_cornersform(self):
        wm = _wm({})
        wm["cornersForm"] = {"42": {"cardLine": 3.5, "cardOverRate": 0.6,
                                    "cardOverSeq": [True, True, True]}}
        out = S.build_streaks(wm)
        cards = [s for s in out["streaks"] if s["type"] == "cards"]
        self.assertEqual(len(cards), 1)
        self.assertIn("3,5 Karten", cards[0]["market"])

    def test_next_fixture_with_opponent_rate(self):
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=3)).isoformat()
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.7, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.66}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "date": fut,
                                            "kickoff": fut + "T15:00:00Z"}]
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["next"]["oppName"], "City")
        self.assertEqual(over["next"]["atHome"], True)
        self.assertEqual(over["next"]["oppRatePct"], 66)

    def test_matchup_downgrades_status_when_opponent_hurts(self):
        # Eigentendenz stark (80% → allein „intakt"), aber nächster Gegner geht kaum über (20%)
        # → kombiniert 0.6*0.8 + 0.4*0.2 = 0.56 → „neutral" (lebendiger Status, 29.06.2026).
        from datetime import date, timedelta
        fut = (date.today() + timedelta(days=2)).isoformat()
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "over25Rate": 0.8, "bttsRate": 0.4},
                  "50": {"over25Rate": 0.20}})
        wm["groups"]["ENG"]["fixtures"] = [{"home": "42", "away": "50", "date": fut,
                                            "kickoff": fut + "T15:00:00Z"}]
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25" and s["venue"] == "all")
        self.assertEqual(over["ratePct"], 80)                 # Eigentendenz unverändert
        self.assertEqual(over["oppSupportPct"], 20)           # Gegner stützt nur 20%
        self.assertEqual(over["matchupPct"], 56)              # kombiniert
        self.assertEqual(over["continuation"]["state"], "neutral")   # von intakt → offen gedämpft

    def test_matchup_only_own_when_no_opponent(self):
        # Ohne nächstes Spiel bleibt der Status reine Eigentendenz (Fallback).
        wm = _wm({"42": {"o25Seq": [True, True, True, True], "over25Rate": 0.8, "bttsRate": 0.4}})
        out = S.build_streaks(wm)
        over = next(s for s in out["streaks"] if s["type"] == "over25")
        self.assertEqual(over["continuation"]["state"], "intakt")
        self.assertNotIn("oppSupportPct", over)

    def test_sorted_by_length_desc(self):
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.6, "bttsRate": 0.5},
                  "50": {"o25Seq": [True] * 6, "over25Rate": 0.8, "bttsRate": 0.5}})
        out = S.build_streaks(wm)
        self.assertEqual(out["streaks"][0]["length"], 6)
        self.assertTrue(out["streaks"][0]["strong"])


if __name__ == "__main__":
    unittest.main()
