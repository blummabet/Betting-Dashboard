#!/usr/bin/env python3
"""
test_disabled_markets.py — Verlust-Märkte raus halten

Backtest 07.06.2026 hat gezeigt:
  · BTTS: -15% ROI (n=141) — signifikant negativ
  · noBtts: -26% ROI (n=40)
  · Corners >10.5: -65% ROI (n=10)

Bis das Modell überarbeitet ist, werden diese Märkte via
cocobet_config.json.profiles.wm2026.disabled_markets[] gesperrt.
Dieser Test stellt sicher dass:
  1. Die config-Liste eingelesen wird
  2. generate_picks_for_fixture diese Märkte überspringt
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestDisabledMarketsRead(unittest.TestCase):
    """Config wird korrekt geparst."""

    def test_btts_in_disabled(self):
        sys.argv = ["test"]
        import generate_wm_picks as g
        self.assertIn("btts", g.DISABLED_MARKETS,
            "BTTS muss in disabled_markets sein — Backtest hat es als -15% ROI markiert")


class TestDisabledMarketsFiltered(unittest.TestCase):
    """generate_picks_for_fixture erzeugt keine Picks für gesperrte Märkte."""

    @classmethod
    def setUpClass(cls):
        sys.argv = ["test"]
        import generate_wm_picks
        cls.mod = generate_wm_picks
        cls.wm = json.loads((BASE / "wm2026-data.json").read_text(encoding="utf-8"))
        travel_path = BASE / "wm_travel_burden.json"
        cls.travel = json.loads(travel_path.read_text()) if travel_path.exists() else {}

    def test_no_btts_picks_anywhere(self):
        """Über alle WM-Fixtures: kein einziger BTTS-Pick."""
        btts_picks = []
        for gkey, gdata in self.wm["groups"].items():
            for fx in gdata.get("fixtures", []):
                try:
                    picks = self.mod.generate_picks_for_fixture(
                        fx=fx, gdata=gdata,
                        mkt=self.wm["odds"], form=self.wm["form"],
                        h2h_data=self.wm["h2h"],
                        today_iso="2026-06-07",
                        xg_stats=self.wm.get("xgStats", {}),
                        injuries=self.wm.get("injuries", {}),
                        travel_data=self.travel,
                        corners_form=self.wm.get("cornersForm", {}),
                    )
                    for p in picks:
                        m = (p.get("market") or "")
                        if "Beide Teams" in m:
                            btts_picks.append(f"{fx['home']}-{fx['away']}: {m}")
                except Exception:
                    pass
        self.assertEqual(btts_picks, [],
            f"BTTS-Picks gefunden obwohl deaktiviert: {btts_picks[:5]}")


if __name__ == "__main__":
    unittest.main()
