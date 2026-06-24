#!/usr/bin/env python3
"""
test_reconcile_poly.py — manuelle Polymarket-Eingriffe erkennen (23.06.2026, Lucas).
Polymarket ist geoblockt → getter wird gemockt.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import reconcile_poly_positions as R   # noqa: E402


def _getter(positions, trades):
    def g(url):
        return positions if "/positions" in url else trades
    return g


class TestReconcile(unittest.TestCase):
    def _bet(self, **kw):
        b = {"betKey": "D-2-ENG-GHA|Auswärtssieg", "matchKey": "ENG-GHA", "home": "England",
             "away": "Ghana", "market": "Auswärtssieg", "status": "placed", "tokenId": "TOK1",
             "polyPrice": 0.40, "sharesEstimate": 25.0, "placedAt": "2026-06-23T08:00:00Z"}
        b.update(kw)
        return b

    def test_token_gone_prematch_closed_with_real_pnl(self):
        bet = self._bet()
        positions = []  # Wallet hält TOK1 nicht mehr
        trades = [{"asset": "TOK1", "side": "SELL", "price": 0.52, "size": 25.0,
                   "timestamp": "2026-06-23T12:00:00Z"}]
        changed = R.reconcile([bet], proxy="0xabc", finished_keys=set(),
                              now_iso="2026-06-23T18:00:00Z", getter=_getter(positions, trades))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")
        self.assertEqual(bet["sellPrice"], 0.52)
        self.assertEqual(bet["pnl"], round(25.0 * (0.52 - 0.40), 2))   # echter Sell-P&L

    def test_token_still_held_untouched(self):
        bet = self._bet()
        positions = [{"asset": "TOK1", "size": 25.0}]   # noch gehalten
        changed = R.reconcile([bet], proxy="0xabc", getter=_getter(positions, []))
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_finished_match_not_treated_as_manual(self):
        bet = self._bet()
        positions = []  # Token weg — aber Spiel fertig → Settlement, NICHT manuell
        changed = R.reconcile([bet], proxy="0xabc", finished_keys={"ENG-GHA"},
                              getter=_getter(positions, []))
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_api_error_does_nothing(self):
        bet = self._bet()
        # Positions-API FEHLER (None, nicht leere Liste) → konservativ NICHT schließen
        changed = R.reconcile([bet], proxy="0xabc", getter=lambda url: None)
        self.assertEqual(changed, [])
        self.assertEqual(bet["status"], "placed")

    def test_no_sell_trade_marks_without_pnl(self):
        bet = self._bet()
        positions = []
        changed = R.reconcile([bet], proxy="0xabc", getter=_getter(positions, []))
        self.assertEqual(len(changed), 1)
        self.assertEqual(bet["status"], "closed_manual")
        self.assertIsNone(bet["pnl"])
        self.assertEqual(bet["pnlSource"], "manual_unknown")


if __name__ == "__main__":
    unittest.main()
