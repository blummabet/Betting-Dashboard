#!/usr/bin/env python3
"""test_fetch_liga_extra_markets.py — BTTS + alternate_totals (1.5/3.5) Anreicherung (25.07.2026).
Testet die REINEN Transforms (Merge + Extraktion); der Live-Per-Event-Call ist flag-gated."""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_odds as F


def _event_with_extras():
    return {
        "id": "evt1", "home_team": "Team A", "away_team": "Team B",
        "bookmakers": [{"key": "pinnacle", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Team A", "price": 2.0}, {"name": "Draw", "price": 3.4},
                {"name": "Team B", "price": 3.8}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 2.5, "price": 1.90},
                {"name": "Under", "point": 2.5, "price": 1.95}]},
            {"key": "alternate_totals", "outcomes": [
                {"name": "Over", "point": 1.5, "price": 1.30},
                {"name": "Under", "point": 1.5, "price": 3.40},
                {"name": "Over", "point": 3.5, "price": 2.60},
                {"name": "Under", "point": 3.5, "price": 1.50}]},
            {"key": "btts", "outcomes": [
                {"name": "Yes", "price": 1.80}, {"name": "No", "price": 1.95}]},
        ]}],
    }


class TestExtraMarkets(unittest.TestCase):
    def test_merge_bookmakers_adds_markets_no_dup(self):
        base = [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": []},
                                                {"key": "totals", "outcomes": []}]}]
        extra = [{"key": "pinnacle", "markets": [{"key": "btts", "outcomes": []},
                                                 {"key": "totals", "outcomes": []}]},  # dup totals
                 {"key": "williamhill", "markets": [{"key": "btts", "outcomes": []}]}]
        merged = F._merge_bookmakers(base, extra)
        by = {b["key"]: b for b in merged}
        pin_keys = [m["key"] for m in by["pinnacle"]["markets"]]
        self.assertEqual(pin_keys, ["h2h", "totals", "btts"])   # btts ergänzt, totals NICHT dupliziert
        self.assertIn("williamhill", by)                        # neuer Bookmaker übernommen

    def test_extract_prices_yields_all_ou_lines_and_btts(self):
        p = F.extract_prices(_event_with_extras(), "direct", "Team A", "Team B")
        # 1X2
        self.assertEqual((p["hw"], p["dr"], p["aw"]), (2.0, 3.4, 3.8))
        # O/U 1.5/2.5/3.5
        self.assertEqual((p["o15"], p["u15"]), (1.30, 3.40))
        self.assertEqual((p["o25"], p["u25"]), (1.90, 1.95))
        self.assertEqual((p["o35"], p["u35"]), (2.60, 1.50))
        # BTTS
        self.assertEqual((p["bttsY"], p["bttsN"]), (1.80, 1.95))

    def test_without_extras_unchanged_behavior(self):
        ev = _event_with_extras()
        # alternate_totals + btts entfernen → nur h2h + totals(2.5) wie im Batch
        ev["bookmakers"][0]["markets"] = [m for m in ev["bookmakers"][0]["markets"]
                                          if m["key"] in ("h2h", "totals")]
        p = F.extract_prices(ev, "direct", "Team A", "Team B")
        self.assertIn("o25", p)
        self.assertNotIn("o15", p)      # keine alternate → keine 1.5
        self.assertNotIn("bttsY", p)    # kein btts-Markt → kein BTTS

    def test_enrich_noop_without_flag(self):
        # Ohne FETCH_EXTRA_MARKETS bleibt das Event unverändert (kein Netzwerk-Call).
        self.assertFalse(F._EXTRA_MARKETS_ENABLED)   # Test-Env hat das Flag nicht
        ev = {"id": "x", "bookmakers": [{"key": "pinnacle", "markets": []}]}
        out = F._enrich_event_markets(ev, "soccer_usa_mls", {"kickoff": "2026-08-01T00:00:00Z"},
                                      "2026-07-30T00:00:00Z")
        self.assertIs(out, ev)


if __name__ == "__main__":
    unittest.main(verbosity=2)
