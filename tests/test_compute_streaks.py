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

    def test_sorted_by_length_desc(self):
        wm = _wm({"42": {"o25Seq": [True, True, True], "over25Rate": 0.6, "bttsRate": 0.5},
                  "50": {"o25Seq": [True] * 6, "over25Rate": 0.8, "bttsRate": 0.5}})
        out = S.build_streaks(wm)
        self.assertEqual(out["streaks"][0]["length"], 6)
        self.assertTrue(out["streaks"][0]["strong"])


if __name__ == "__main__":
    unittest.main()
