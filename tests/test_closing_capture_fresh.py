#!/usr/bin/env python3
"""test_closing_capture_fresh.py — check_closing_capture_fresh (07.07.2026, Lucas: „Guard der im
Status zeigt, ob wir die Odds nah am Anpfiff holen"). Kürzlich angepfiffenes Spiel mit zu früh
eingefrorenem Closing → WARN; nah am Anpfiff → grün; >48h alt → ignoriert (historisch)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(kickoff):
    wm = {"_meta": {"profile": "wm2026"}, "groups": {},
          "koFixtures": [{"home": "AAA", "away": "BBB", "kickoff": kickoff}]}
    return W.IntegrityCtx(wm, {}, {}, {})


def _iso(dt):
    return dt.isoformat()


class TestClosingCaptureFresh(unittest.TestCase):
    def _run(self, kickoff, frozen_at):
        with patch.object(W, "_lazy", lambda *_a, **_k: {"AAA-BBB": {"frozenAt": frozen_at}}):
            return W.check_closing_capture_fresh(_ctx(kickoff))

    def test_stale_recent_flagged(self):
        now = datetime.now(timezone.utc)
        ko = now - timedelta(hours=2)              # vor 2h angepfiffen (kürzlich)
        fz = ko - timedelta(minutes=180)           # Closing 3h VOR Anpfiff = veraltet
        res = self._run(_iso(ko), _iso(fz))
        self.assertFalse(res["ok"])
        self.assertIn("AAA-BBB", res["failures"][0])

    def test_fresh_recent_ok(self):
        now = datetime.now(timezone.utc)
        ko = now - timedelta(hours=2)
        fz = ko - timedelta(minutes=12)            # ≤45min → frisch
        res = self._run(_iso(ko), _iso(fz))
        self.assertTrue(res["ok"])

    def test_old_game_ignored(self):
        now = datetime.now(timezone.utc)
        ko = now - timedelta(hours=72)             # >48h → historisch, nicht flaggen
        fz = ko - timedelta(minutes=300)
        res = self._run(_iso(ko), _iso(fz))
        self.assertTrue(res["ok"])

    def test_upcoming_ignored(self):
        now = datetime.now(timezone.utc)
        ko = now + timedelta(hours=3)              # noch nicht angepfiffen
        fz = now - timedelta(minutes=10)
        res = self._run(_iso(ko), _iso(fz))
        self.assertTrue(res["ok"])


if __name__ == "__main__":
    unittest.main()
