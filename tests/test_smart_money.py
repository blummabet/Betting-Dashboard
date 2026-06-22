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


def _ctx(home_usd=8e6, home_share=0.84, top=0.30, total=9.5e6, draw_share=0.06, away_share=0.10,
         home_cluster=0, home_net=None, hk=None):
    home = {"usd": home_usd, "share": home_share, "topHolderShare": top, "holders": 600,
            "cluster": home_cluster}
    if home_net is not None:
        home["netFlowUsd"] = home_net
    return {
        "matchKey": "FRA-IRQ",
        "smartmoney": {"FRA-IRQ": {
            "totalUsd": total, "topTraders": 12, "hoursToKickoff": hk,
            "outcomes": {
                "home": home,
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
                                          _ctx(total=50_000)))   # < min_volume (100k)

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

    def test_cluster_boost_strengthens(self):
        # gleicher Überschuss, aber ≥3 unabhängige Cluster-Wallets → stärkerer Confirm
        pick = {"market": "Heimsieg", "modelOdds": 1.667}
        base = self.s.evaluate(pick, _ctx(home_share=0.70, top=0.20, home_cluster=0))
        boosted = self.s.evaluate(pick, _ctx(home_share=0.70, top=0.20, home_cluster=4))
        self.assertIsNotNone(base)
        self.assertGreater(boosted.score, base.score)
        self.assertTrue(boosted.metadata["clustered"])
        self.assertEqual(boosted.metadata["cluster"], 4)

    def test_cluster_below_min_no_boost(self):
        pick = {"market": "Heimsieg", "modelOdds": 1.667}
        base = self.s.evaluate(pick, _ctx(home_share=0.70, top=0.20, home_cluster=0))
        two = self.s.evaluate(pick, _ctx(home_share=0.70, top=0.20, home_cluster=2))  # < min 3
        self.assertAlmostEqual(base.score, two.score)
        self.assertFalse(two.metadata["clustered"])

    def test_exit_penalty_pushes_to_warning(self):
        # Confirm-Setup, aber Wale verkaufen netto nahe Anpfiff → Score gedrückt
        pick = {"market": "Heimsieg", "modelOdds": 1.667}
        confirm = self.s.evaluate(pick, _ctx())
        exited = self.s.evaluate(pick, _ctx(home_net=-50_000, hk=3))
        self.assertIsNotNone(exited)
        self.assertLess(exited.score, confirm.score)
        self.assertTrue(exited.metadata["exitFlag"])

    def test_exit_ignored_far_from_kickoff(self):
        # gleicher Net-Abfluss, aber Anpfiff weit weg (> exit_window) → keine Strafe
        pick = {"market": "Heimsieg", "modelOdds": 1.667}
        confirm = self.s.evaluate(pick, _ctx())
        far = self.s.evaluate(pick, _ctx(home_net=-50_000, hk=72))
        self.assertAlmostEqual(confirm.score, far.score)
        self.assertFalse(far.metadata["exitFlag"])


class TestClusterMetrics(unittest.TestCase):
    """Fetcher-Berechnung der Konsens-Cluster/Net-Flow aus großen Trades."""

    def _t(self, wallet, side, action, usd, ts):
        return {"wallet": wallet, "side": side, "action": action, "usd": usd, "ts": ts}

    def test_distinct_buy_wallets_counted(self):
        import fetch_wm_poly_smartmoney as F
        trades = [
            self._t("0xa", "home", "BUY", 3000, "2026-06-22T10:00:00+00:00"),
            self._t("0xb", "home", "BUY", 4000, "2026-06-22T09:30:00+00:00"),
            self._t("0xa", "home", "BUY", 2000, "2026-06-22T09:00:00+00:00"),  # selbe Wallet → kein +
            self._t("0xc", "away", "BUY", 5000, "2026-06-22T09:45:00+00:00"),
        ]
        m = F._cluster_metrics(trades, 12)
        self.assertEqual(m["home"]["cluster"], 2)        # 0xa + 0xb, 0xa nicht doppelt
        self.assertEqual(m["away"]["cluster"], 1)
        self.assertEqual(m["home"]["buyUsd"], 9000)

    def test_netflow_buy_minus_sell(self):
        import fetch_wm_poly_smartmoney as F
        trades = [
            self._t("0xa", "home", "BUY", 6000, "2026-06-22T10:00:00+00:00"),
            self._t("0xb", "home", "SELL", 10000, "2026-06-22T09:50:00+00:00"),
        ]
        m = F._cluster_metrics(trades, 12)
        self.assertEqual(m["home"]["netFlowUsd"], -4000)
        self.assertEqual(m["home"]["cluster"], 1)        # SELL zählt nicht als Cluster-Wallet

    def test_window_excludes_old_trades(self):
        import fetch_wm_poly_smartmoney as F
        trades = [
            self._t("0xa", "home", "BUY", 3000, "2026-06-22T10:00:00+00:00"),
            self._t("0xb", "home", "BUY", 4000, "2026-06-20T10:00:00+00:00"),  # 48h älter → raus
        ]
        m = F._cluster_metrics(trades, 12)
        self.assertEqual(m["home"]["cluster"], 1)


class TestClusterGuard(unittest.TestCase):
    def _run(self, sm):
        import unittest.mock as mock
        import wm_data_integrity as W
        from datetime import datetime, timezone
        with mock.patch.object(W, "_lazy",
                               side_effect=lambda f: sm if f == "wm_poly_smartmoney.json" else {}):
            res = W.run_checks({"groups": {}, "picks": {}}, {}, {}, {},
                               now=datetime(2026, 6, 22, tzinfo=timezone.utc),
                               auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "smartmoney_cluster_sane"), None)

    def test_cluster_exceeds_holders_flagged(self):
        bad = {"matches": {"FRA-IRQ": {"totalUsd": 9e6, "outcomes": {
            "home": {"share": 0.8, "cluster": 50, "holders": 10}}}}}   # cluster > holders
        c = self._run(bad)
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])

    def test_netflow_mismatch_flagged(self):
        bad = {"matches": {"FRA-IRQ": {"totalUsd": 9e6, "outcomes": {
            "home": {"share": 0.8, "cluster": 2, "holders": 100,
                     "buyUsd": 6000, "sellUsd": 1000, "netFlowUsd": 9999}}}}}  # ≠ 5000
        c = self._run(bad)
        self.assertFalse(c["ok"])

    def test_coherent_cluster_passes(self):
        good = {"matches": {"FRA-IRQ": {"totalUsd": 9e6, "outcomes": {
            "home": {"share": 0.8, "cluster": 3, "holders": 200,
                     "buyUsd": 6000, "sellUsd": 1000, "netFlowUsd": 5000}}}}}
        c = self._run(good)
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])


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


class TestCardOnlyTradeIsolation(unittest.TestCase):
    """Zwei-Flächen-Invariante: smart_money darf NIE in den Trade-Pfad lecken (Zirkel)."""

    def _run(self, picks):
        import wm_data_integrity as W
        from datetime import datetime, timezone
        res = W.run_checks({"groups": {}, "picks": picks}, {}, {}, {},
                           now=datetime(2026, 6, 20, tzinfo=timezone.utc),
                           auto_bets={"bets": []}, history={})
        return next((x for x in res if x["id"] == "card_only_not_in_trade"), None)

    def _pick(self, trade_adj):
        # smart_money +1.5 + form_trend −2.0 → combined −0.5; Trade-Feld MUSS −2.0 sein
        return {"market": "Heimsieg",
                "signals": [{"name": "smart_money", "score": 1.5},
                            {"name": "form_trend", "score": -2.0}],
                "signalAdjustmentPP": -0.5,
                "signalAdjustmentPP_trade": trade_adj}

    def test_correct_exclusion_passes(self):
        c = self._run({"C-2-BRA-HTI": [self._pick(-2.0)]})   # smart_money sauber abgezogen
        self.assertIsNotNone(c)
        self.assertTrue(c["ok"])

    def test_leak_into_trade_flagged(self):
        c = self._run({"C-2-BRA-HTI": [self._pick(-0.5)]})    # smart_money NICHT abgezogen
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])


if __name__ == "__main__":
    unittest.main()
