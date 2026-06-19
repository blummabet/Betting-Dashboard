#!/usr/bin/env python3
"""
test_smart_money.py — Polymarket Smart-Money-Signal (19.06.2026, Lucas)

Geldverteilung relativ zur SCHARFEN Pinnacle-Fair (nicht 50/50), big-wallet-gewichtet, NIEDRIG
gedeckelt. Misst ÜBERSCHUSS gegen die Fair × Konzentration → kein redundantes Volumen-Signal.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.smart_money import SmartMoneySignal  # noqa: E402
from sharp_signals.registry import ACTIVE_SIGNALS       # noqa: E402


def _ctx(home_usd=8e6, home_share=0.84, top=0.30, total=9.5e6, draw_share=0.06, away_share=0.10):
    return {
        "matchKey": "FRA-IRQ",
        "smartmoney": {"FRA-IRQ": {
            "totalUsd": total, "topTraders": 12,
            "outcomes": {
                "home": {"usd": home_usd, "share": home_share, "topHolderShare": top, "holders": 600},
                "draw": {"usd": 6e5, "share": draw_share, "topHolderShare": 0.2, "holders": 90},
                "away": {"usd": 9e5, "share": away_share, "topHolderShare": 0.15, "holders": 120},
            }}}}


class TestSmartMoney(unittest.TestCase):
    def setUp(self):
        self.s = SmartMoneySignal()

    def test_smart_money_excess_confirms(self):
        # Heim-Pick, Fair 60% (modelOdds 1.67), aber 84% des Geldes + Big-Wallets → + (Confirm)
        r = self.s.evaluate({"market": "Heimsieg", "modelOdds": 1.667}, _ctx())
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertLessEqual(r.score, self.s._t["max_signal_pp"])   # niedrig gedeckelt
        self.assertEqual(r.metadata["topTraders"], 12)

    def test_capped_low(self):
        # Extremer Überschuss → trotzdem auf max_signal_pp gedeckelt
        r = self.s.evaluate({"market": "Heimsieg", "modelOdds": 5.0}, _ctx(home_share=0.95, top=0.9))
        self.assertLessEqual(r.score, self.s._t["max_signal_pp"] + 1e-9)

    def test_thin_market_no_signal(self):
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg", "modelOdds": 1.667},
                                          _ctx(total=100_000)))   # < min_volume

    def test_retail_only_no_signal(self):
        # hohes Volumen, aber Konzentration unter min_top_share → reines Retail → None
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg", "modelOdds": 1.667},
                                          _ctx(top=0.03)))

    def test_no_modelodds_no_signal(self):
        # ohne scharfe Baseline kein „Überschuss" berechenbar
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg"}, _ctx()))

    def test_unmappable_market_none(self):
        self.assertIsNone(self.s.evaluate({"market": "Über 2.5 Tore", "modelOdds": 1.8}, _ctx()))

    def test_no_data_none(self):
        self.assertIsNone(self.s.evaluate({"market": "Heimsieg", "modelOdds": 1.667},
                                          {"matchKey": "X", "smartmoney": {}}))

    def test_registered(self):
        self.assertTrue(any(s.name() == "smart_money" for s in ACTIVE_SIGNALS))


class TestSmartMoneyGuard(unittest.TestCase):
    def test_incoherent_shares_flagged(self):
        import unittest.mock as mock
        import wm_data_integrity as W
        from datetime import datetime, timezone
        bad = {"matches": {"FRA-IRQ": {"totalUsd": 9e6, "outcomes": {
            "home": {"share": 0.84}, "away": {"share": 0.50}}}}}   # summiert 1.34
        with mock.patch.object(W, "_lazy",
                               side_effect=lambda f: bad if f == "wm_poly_smartmoney.json" else {}):
            res = W.run_checks({"groups": {}, "picks": {}}, {}, {}, {},
                               now=datetime(2026, 6, 19, tzinfo=timezone.utc),
                               auto_bets={"bets": []}, history={})
        c = next((x for x in res if x["id"] == "smartmoney_sane"), None)
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])


if __name__ == "__main__":
    unittest.main()
