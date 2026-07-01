#!/usr/bin/env python3
"""test_generate_wm_ai_preview.py — Vorschau nur für anstehende Spiele (01.07.2026, Lucas: „heute keine
Previews, nur Reviews"). Ohne untere Zeitgrenze verarbeitete der Generator alle längst gespielten
Gruppenspiele zuerst → die anstehenden KO-Spiele (ans Ende gehängt) bekamen nie eine Vorschau."""
import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("gap", REPO / "generate_wm_ai_preview.py")
gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gap)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


class TestFixtureIsUpcoming(unittest.TestCase):
    def test_future_kickoff_upcoming(self):
        fx = {"kickoff": "2026-07-02T19:00:00Z", "date": "2026-07-02"}
        self.assertTrue(gap._fixture_is_upcoming(fx, NOW))

    def test_past_kickoff_not_upcoming(self):
        fx = {"kickoff": "2026-06-27T19:00:00Z", "date": "2026-06-27"}
        self.assertFalse(gap._fixture_is_upcoming(fx, NOW))

    def test_date_fallback_without_kickoff(self):
        self.assertFalse(gap._fixture_is_upcoming({"date": "2026-06-20"}, NOW))   # vergangen
        self.assertTrue(gap._fixture_is_upcoming({"date": "2026-07-05"}, NOW))    # anstehend

    def test_unparseable_not_filtered(self):
        # kaputte/fehlende Zeit → lieber drin lassen als fälschlich rauswerfen
        self.assertTrue(gap._fixture_is_upcoming({"kickoff": "kaputt"}, NOW))
        self.assertTrue(gap._fixture_is_upcoming({}, NOW))


if __name__ == "__main__":
    unittest.main()
