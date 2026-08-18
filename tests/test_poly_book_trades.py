"""18.08.2026 (Lucas, Arkham): Orderbuch + Trades-Anreicherung fuers Poly-Terminal-Drilldown.
Reine Unit-Tests (stdlib unittest, kein Netz — get injiziert)."""
import unittest
import poly_money_broad as B


def _make_get(book, trades):
    def get(url):
        if "/book?token_id=" in url:
            return book
        if "/trades?market=" in url:
            return trades
        return None
    return get


class TestEnrichBookTrades(unittest.TestCase):
    def _oc(self):
        return [{"label": "A", "token": "tokA", "cond": "c1", "price": 0.55},
                {"label": "B", "token": "tokB", "cond": "c1", "price": 0.45}]

    def test_book_and_trades_built(self):
        book = {"bids": [{"price": "0.47", "size": "39800"}, {"price": "0.46", "size": "63100"}],
                "asks": [{"price": "0.48", "size": "7900"}, {"price": "0.49", "size": "31100"}]}
        trades = [{"proxyWallet": "0xabc", "side": "BUY", "size": "1000", "price": "0.47",
                   "timestamp": 1787000000, "outcome": "A"},
                  {"proxyWallet": "0xdef", "side": "SELL", "size": "10", "price": "0.50",
                   "timestamp": 1787000100, "outcome": "A"}]  # 10*0.5=5$ < min -> raus
        m = {"shares": {"A": 100.0, "B": 30.0}, "prices": {"A": 0.55, "B": 0.45}}
        budget = [40]
        B._enrich_book_trades(m, self._oc(), _make_get(book, trades), budget)
        self.assertEqual(budget[0], 38)                     # 2 Calls verbraucht
        bk = m.get("book"); self.assertIsNotNone(bk)
        self.assertEqual(bk["side"], "A")                   # money-fav (hoechste shares)
        self.assertAlmostEqual(bk["bid"], 0.47); self.assertAlmostEqual(bk["ask"], 0.48)
        self.assertAlmostEqual(bk["spreadC"], 1.0, places=1)
        self.assertEqual(bk["bids"][0], [0.47, 39800])      # bids nach Preis absteigend
        self.assertEqual(bk["asks"][0], [0.48, 7900])       # asks aufsteigend
        tr = m.get("trades"); self.assertEqual(len(tr), 1)  # der 5$-SELL fiel raus
        self.assertEqual(tr[0]["action"], "BUY")
        self.assertEqual(tr[0]["side"], "A")
        self.assertEqual(tr[0]["usd"], 470)

    def test_no_token_no_call(self):
        m = {"shares": {"A": 1.0}, "prices": {"A": 0.5}}
        oc = [{"label": "A", "token": None, "cond": None}]
        budget = [40]
        B._enrich_book_trades(m, oc, _make_get({}, []), budget)
        self.assertNotIn("book", m); self.assertNotIn("trades", m)
        self.assertEqual(budget[0], 40)                     # kein Token/cond -> keine Calls

    def test_budget_exhausted_silent(self):
        m = {"shares": {"A": 1.0}}
        budget = [0]
        B._enrich_book_trades(m, self._oc(), _make_get({"bids": [{"price": "0.4", "size": "1"}],
                                                        "asks": [{"price": "0.5", "size": "1"}]}, []), budget)
        self.assertNotIn("book", m)                         # Budget leer -> nichts


class TestCaptureLiveCarries(unittest.TestCase):
    def test_book_trades_durchgereicht(self):
        mkts = [{"key": "atp-a-b-2026", "totalUsd": 50000, "shares": {"A": 100}, "prices": {"A": 0.5},
                 "whales": [], "league": "ATP", "sport": "Tennis", "hoursToKickoff": 2.0,
                 "book": {"side": "A", "bid": 0.47, "ask": 0.48, "spreadC": 1.0, "bids": [[0.47, 100]], "asks": [[0.48, 50]]},
                 "trades": [{"wallet": "0xabc", "action": "BUY", "side": "A", "price": 0.47, "usd": 470, "ts": 1787000000}]}]
        out = B.capture_live(mkts, {}, min_vol=0)
        e = out["atp-a-b-2026"]
        self.assertIn("book", e); self.assertEqual(e["book"]["side"], "A")
        self.assertIn("trades", e); self.assertEqual(e["trades"][0]["usd"], 470)

    def test_ohne_book_kein_feld(self):
        mkts = [{"key": "x-2026", "totalUsd": 50000, "shares": {}, "prices": {}, "whales": [],
                 "league": "MLS", "sport": "Fußball", "hoursToKickoff": 1.0}]
        out = B.capture_live(mkts, {}, min_vol=0)
        self.assertNotIn("book", out["x-2026"])            # kein Buch -> Feld gar nicht da (JSON schlank)


if __name__ == "__main__":
    unittest.main(verbosity=2)
