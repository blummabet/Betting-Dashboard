#!/usr/bin/env python3
"""
test_spread_honest_pnl.py — Ehrliche Bid/Ask-Bewertung (17.06.2026).

Geld-Bug USA-TUR „BTTS Nein": Position am MITTELPREIS bewertet (poly_btts_no = 1 − JA-Mid)
statt am realisierbaren Bid. Kauf lief über den Ask (0.43), Verkauf über den Bid (0.41) →
angezeigte +10% waren real −4%. Der Konvergenz-Verkauf flippte für einen Schein-Gewinn.

Fix:
  1. fetch_token_book — Live-Bid/Ask, ORDER-UNABHÄNGIG (max-Bid/min-Ask).
  2. check_position bewertet am Bid; Profit-Sell-Veto wenn Bid ≤ Entry oder Spread zu breit.
  3. 8% Profit-Schwelle auf REALEM Gewinn.
  4. Integritäts-Guard check_profit_sell_real.
"""
import sys
import unittest
import unittest.mock as mock
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

# Spieltermin IMMER in der Zukunft (relativ zu jetzt) — sonst kippt der Test in den
# In-Play-Modus, sobald die Wanduhr über ein fixes Datum läuft (Profit-Sells sind dann aus).
_FUTURE_MATCH = (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")

import manage_wm_poly_positions as M
import wm_data_integrity as I


class TestFetchTokenBook(unittest.TestCase):
    """Order-Unabhängigkeit: best bid = max, best ask = min — egal wie Poly sortiert."""

    def _book(self, bids, asks):
        data = {"bids": [{"price": str(p), "size": "100"} for p in bids],
                "asks": [{"price": str(p), "size": "100"} for p in asks]}
        with mock.patch.object(M, "_http_get", return_value=data):
            return M.fetch_token_book("TOK")

    def test_bids_ascending_asks_descending(self):
        # Poly liefert manchmal bids aufsteigend, asks absteigend → [0] wäre falsch
        b = self._book(bids=[0.38, 0.39, 0.41], asks=[0.46, 0.44, 0.43])
        self.assertEqual(b["bid"], 0.41)   # max der bids
        self.assertEqual(b["ask"], 0.43)   # min der asks
        self.assertAlmostEqual(b["spreadPP"], 2.0, places=1)

    def test_bids_descending_asks_ascending(self):
        b = self._book(bids=[0.41, 0.39, 0.38], asks=[0.43, 0.44, 0.46])
        self.assertEqual(b["bid"], 0.41)
        self.assertEqual(b["ask"], 0.43)

    def test_crossed_book_returns_none(self):
        # bid >= ask (degeneriert/gekreuzt) → None → kein Sell
        self.assertIsNone(self._book(bids=[0.50], asks=[0.48]))

    def test_empty_book_none(self):
        self.assertIsNone(self._book(bids=[], asks=[0.43]))


class TestHonestValuation(unittest.TestCase):
    def _pos(self, **kw):
        base = {"market": "Beide Teams treffen — Nein", "tokenId": "X",
                "pinnFair": 0.452, "sharesEstimate": 13, "placedAt": "",
                "matchDate": _FUTURE_MATCH, "homeId": "USA", "awayId": "TUR"}
        base.update(kw)
        return base

    def _check(self, pos, book):
        with mock.patch.object(M, "fetch_token_book", return_value=book):
            return M.check_position(dict(pos))

    def test_usatur_phantom_now_honest_loss(self):
        # DER Bug: Entry am Ask 0.43, Bid jetzt 0.41 → real −4.7%, KEIN Profit-Sell
        r = self._check(self._pos(entryPrice=0.43),
                        {"bid": 0.41, "ask": 0.43, "mid": 0.42, "spreadPP": 2.0, "liqUSD": 500})
        self.assertEqual(r["currentPrice"], 0.41)   # Bid, nicht Mid 0.42
        self.assertLess(r["pnlPct"], 0)
        self.assertFalse(r["sellSignal"])
        self.assertEqual(r["priceSource"], "live_bid")

    def test_real_profit_sells_at_8pct(self):
        # Entry 0.40, Bid 0.45 → +12.5% ≥ 8% → echter Profit-Sell
        r = self._check(self._pos(entryPrice=0.40),
                        {"bid": 0.45, "ask": 0.47, "mid": 0.46, "spreadPP": 2.0, "liqUSD": 500})
        self.assertTrue(r["sellSignal"])
        self.assertIn("Profit", r["sellReason"])

    def test_below_8pct_no_sell(self):
        # Entry 0.40, Bid 0.42 → +5% < 8% und Konvergenz greift (fair 0.452, gap 3.2pp>1.5) nicht
        r = self._check(self._pos(entryPrice=0.40, pinnFair=0.60),
                        {"bid": 0.42, "ask": 0.44, "mid": 0.43, "spreadPP": 2.0, "liqUSD": 500})
        self.assertFalse(r["sellSignal"])

    def test_profit_sell_vetoed_on_wide_spread(self):
        # +10% am Bid, aber Spread 18pp > 15pp Cap → Profit-Sell geblockt
        r = self._check(self._pos(entryPrice=0.40),
                        {"bid": 0.44, "ask": 0.62, "mid": 0.53, "spreadPP": 18.0, "liqUSD": 500})
        self.assertFalse(r["sellSignal"])
        self.assertIn("Spread", r.get("sellVetoed", ""))

    def test_cache_fallback_when_book_down(self):
        # Buch nicht erreichbar → Cache-Mid-Fallback, markiert
        with mock.patch.object(M, "fetch_token_book", return_value=None), \
             mock.patch.object(M, "_token_price_from_cache", return_value=0.40):
            r = M.check_position(self._pos(entryPrice=0.40))
        self.assertEqual(r["priceSource"], "cache_mid_fallback")
        self.assertEqual(r["currentPrice"], 0.40)


class TestProfitSellRealGuard(unittest.TestCase):
    def _ctx(self, bets):
        return I.IntegrityCtx({"groups": {}}, {}, {}, {"venues": {}}, auto_bets={"bets": bets})

    def test_flags_phantom_profit_sell(self):
        bets = [{"home": "USA", "away": "TUR", "market": "BTTS Nein", "status": "sold",
                 "sellReason": "Profit +10%", "sellPrice": 0.40, "polyPrice": 0.44}]
        out = I.check_profit_sell_real(self._ctx(bets))
        self.assertFalse(out["ok"])

    def test_real_profit_sell_ok(self):
        bets = [{"home": "USA", "away": "TUR", "market": "BTTS Nein", "status": "sold",
                 "sellReason": "Profit +8%", "sellPrice": 0.45, "polyPrice": 0.40}]
        self.assertTrue(I.check_profit_sell_real(self._ctx(bets))["ok"])


if __name__ == "__main__":
    unittest.main()
