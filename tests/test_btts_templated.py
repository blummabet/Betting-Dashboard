#!/usr/bin/env python3
"""
test_btts_templated.py — Templated/Platzhalter-BTTS-Linien nicht handelbar (23.06.2026, Lucas).

Vorfall: Pinnacle liefert für viele WM-Spiele eine generische Standard-BTTS-Linie (z.B. 1.91/1.80
auf 5 Spielen) statt eines echten Spiel-Sharp-Preises. De-vig davon (fair 0.4852/0.5148) ist sauber,
aber wertlos → Phantom-Edge → Auto-Trader setzte echtes Geld (CPV-SAU/PRY-AUS/JPN-SWE, real negativ).
Fix: compute_btts_edges nullt fair/edge bei templated; Tripwire-Guard prüft die Invariante.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_poly_prices as F   # noqa: E402
import wm_data_integrity as W      # noqa: E402


class TestComputeBttsEdges(unittest.TestCase):
    def test_real_line_devigs_and_edges(self):
        # echte Linie → fair_Ja + fair_Nein = 1.0, Edge berechnet
        fair, fair_no, e, e_no = F.compute_btts_edges(1.91, 1.80, 0.45, 0.55, templated=False)
        self.assertAlmostEqual(fair + fair_no, 1.0, places=3)
        self.assertIsNotNone(e)
        self.assertIsNotNone(e_no)

    def test_templated_returns_all_none(self):
        fair, fair_no, e, e_no = F.compute_btts_edges(1.91, 1.80, 0.45, 0.55, templated=True)
        self.assertEqual((fair, fair_no, e, e_no), (None, None, None, None))

    def test_missing_line_returns_none(self):
        self.assertEqual(F.compute_btts_edges(None, None, 0.45, 0.55), (None, None, None, None))


class TestBttsTemplatedGuard(unittest.TestCase):
    def _run(self, poly_all):
        res = W.run_checks({"groups": {}, "picks": {}}, {"allFixtures": poly_all}, {}, {},
                           now=datetime(2026, 6, 23, tzinfo=timezone.utc),
                           auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "btts_not_templated_traded"), None)

    def test_templated_with_edge_flagged(self):
        c = self._run([{"homeId": "PRY", "awayId": "AUS", "btts_templated": True,
                        "edge_btts": 5.0, "edge_btts_no": None}])
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])

    def test_templated_without_edge_ok(self):
        c = self._run([{"homeId": "PRY", "awayId": "AUS", "btts_templated": True,
                        "edge_btts": None, "edge_btts_no": None}])
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])

    def test_non_templated_ignored(self):
        c = self._run([{"homeId": "X", "awayId": "Y", "btts_templated": False,
                        "edge_btts": 4.0}])
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
