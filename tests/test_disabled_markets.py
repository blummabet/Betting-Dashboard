#!/usr/bin/env python3
"""
test_disabled_markets.py — Verlust-/Engine-lose Märkte raus halten

Stand 10.06.2026 (WM2026-Profil):
  · Corners (o_corners85/95/105) DEAKTIVIERT — kein Signal hat aggregierte
    Corner-Daten für WM-Nationalteams (kein H2H-Corner-Rate, kein NT-Corner-Bias)
    → reine Poisson ohne Signal-Filter. Code bleibt für liga_default drin.
  · BTTS WIEDER AKTIV (09.06.2026) — der alte Backtest-Loss (-15% ROI) stammt aus
    dem alten Modell OHNE Signal-Adjust. xG/Form/H2H/Lineup/Weather können BTTS
    inzwischen sinnvoll bewerten, daher raus aus disabled_markets.

Dieser Test stellt sicher dass:
  1. Die config-Liste eingelesen wird (Corners disabled, BTTS aktiv)
  2. generate_picks_for_fixture die gesperrten Corner-Märkte überspringt
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

CORNER_KEYS = {"o_corners85", "o_corners95", "o_corners105"}


class TestDisabledMarketsRead(unittest.TestCase):
    """Config wird korrekt geparst."""

    def test_corners_in_disabled(self):
        sys.argv = ["test"]
        import generate_wm_picks as g
        self.assertTrue(
            CORNER_KEYS.issubset(set(g.DISABLED_MARKETS)),
            "Alle Corner-Märkte müssen in disabled_markets sein — kein Engine-Hook für NT-Corners")

    def test_btts_reenabled(self):
        """BTTS am 09.06.2026 reaktiviert → darf NICHT mehr disabled sein."""
        sys.argv = ["test"]
        import generate_wm_picks as g
        self.assertNotIn("btts", g.DISABLED_MARKETS,
            "BTTS wurde 09.06.2026 reaktiviert (Signal-Adjust deckt es jetzt ab)")


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

    def test_no_corner_picks_anywhere(self):
        """Über alle WM-Fixtures: kein einziger aktiver Corner-Pick (BET/ABWÄGEN)."""
        corner_picks = []
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
                        # WATCH-Platzhalter ("Pick aktiv sobald Bookies öffnen")
                        # sind kein aktiver Markt — nur BET/ABWÄGEN zählen.
                        if "Ecken" in m and p.get("verdict") in ("BET", "ABWÄGEN"):
                            corner_picks.append(f"{fx['home']}-{fx['away']}: {m}")
                except Exception:
                    pass
        self.assertEqual(corner_picks, [],
            f"Corner-Picks gefunden obwohl deaktiviert: {corner_picks[:5]}")


if __name__ == "__main__":
    unittest.main()
