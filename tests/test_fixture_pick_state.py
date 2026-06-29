#!/usr/bin/env python3
"""test_fixture_pick_state.py — Pick-Immutability/Freeze-Ladder (28.06.2026, Lucas:
KO-Pick ZAF-CAN kippte spät pre-match Auswärtssieg→Unter). Rollendes Posted-Fenster."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G  # noqa: E402

TODAY = "2026-06-28"
NOW = datetime(2026, 6, 28, 18, 0, tzinfo=timezone.utc)          # vor dem 19:00Z-Anpfiff
CUTOVER = datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)       # statischer Launch-Cutover


def _fx(date, kickoff):
    return {"date": date, "kickoff": kickoff}


class TestPickState(unittest.TestCase):
    def test_today_with_pick_is_locked_refresh(self):
        # DER FIX: heutiges Spiel + existierender Pick → refresh (Markt-Lock), NICHT rebuild
        fx = _fx(TODAY, "2026-06-28T19:00:00Z")
        self.assertEqual(G.fixture_pick_state(fx, True, TODAY, NOW, CUTOVER), "refresh")

    def test_today_without_pick_rebuilds(self):
        # noch kein Pick → erstmalig bauen
        fx = _fx(TODAY, "2026-06-28T19:00:00Z")
        self.assertEqual(G.fixture_pick_state(fx, False, TODAY, NOW, CUTOVER), "rebuild")

    def test_tomorrow_with_pick_locked(self):
        fx = _fx("2026-06-29", "2026-06-29T19:00:00Z")
        self.assertEqual(G.fixture_pick_state(fx, True, TODAY, NOW, CUTOVER), "refresh")

    def test_kickoff_passed_frozen(self):
        fx = _fx(TODAY, "2026-06-28T17:00:00Z")   # vor NOW (18:00) → angepfiffen
        self.assertEqual(G.fixture_pick_state(fx, True, TODAY, NOW, CUTOVER), "kickoff_passed")

    def test_future_game_still_follows_steam(self):
        # 5 Tage hin, außerhalb Posted-Fenster → darf weiter dem Steam folgen (rebuild)
        fx = _fx("2026-07-03", "2026-07-03T19:00:00Z")
        self.assertEqual(G.fixture_pick_state(fx, True, TODAY, NOW, CUTOVER), "rebuild")

    def test_past_untouched(self):
        fx = _fx("2026-06-20", "2026-06-20T19:00:00Z")
        self.assertEqual(G.fixture_pick_state(fx, True, TODAY, NOW, CUTOVER), "past")


if __name__ == "__main__":
    unittest.main()
