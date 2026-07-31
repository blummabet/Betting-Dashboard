"""31.07.2026 (Lucas) — echte Lebenszeit-P&L je Wallet (user-pnl-api) in den Wallet-Track ziehen.
Grund: die „schärfste Wallets"-Rangliste stand nach CLV-Timing kopf — ein −800K-Wallet auf #1, weil
CLV nur die wenigen getrackten Wetten misst. Jetzt: nach TATSÄCHLICHEM Gewinn ranken."""
import poly_money_broad as B


class TestLifetimePnl:
    def test_last_point_is_pnl(self):
        data = [{"t": 1, "p": 100.0}, {"t": 2, "p": -800728.7}]
        assert B._lifetime_pnl(data) == -800728.7

    def test_empty_or_bad(self):
        assert B._lifetime_pnl([]) is None
        assert B._lifetime_pnl(None) is None
        assert B._lifetime_pnl("nope") is None
        assert B._lifetime_pnl([{"t": 1}]) is None   # kein p


class TestEnrichWalletPnl:
    def _get(self, pnl_by_wallet):
        def get(url):
            for w, series in pnl_by_wallet.items():
                if w in url:
                    return series
            return None
        return get

    def test_sets_pnl_and_respects_min_n(self):
        scores = {
            "0xAAA": {"n": 30, "clvSumPP": 90, "wins": 21, "usd": 8000},
            "0xBBB": {"n": 3,  "clvSumPP": 30, "wins": 3,  "usd": 9000},   # n<5 → nicht abgefragt
        }
        get = self._get({
            "0xAAA": [{"t": 1, "p": 12000.0}],
            "0xBBB": [{"t": 1, "p": 99999.0}],
        })
        n = B.enrich_wallet_pnl(scores, get, [60], min_n=5)
        assert n == 1
        assert scores["0xAAA"]["pnl"] == 12000.0
        assert "pnl" not in scores["0xBBB"]

    def test_budget_caps_calls(self):
        scores = {f"0x{i:02d}": {"n": 20} for i in range(10)}
        get = self._get({f"0x{i:02d}": [{"t": 1, "p": float(i)}] for i in range(10)})
        budget = [3]
        n = B.enrich_wallet_pnl(scores, get, budget, min_n=5)
        assert n == 3 and budget[0] == 0
        assert sum(1 for s in scores.values() if "pnl" in s) == 3

    def test_prefers_wallets_with_more_history(self):
        scores = {"0xLOW": {"n": 6}, "0xHIGH": {"n": 40}}
        get = self._get({"0xLOW": [{"t": 1, "p": 1.0}], "0xHIGH": [{"t": 1, "p": 2.0}]})
        B.enrich_wallet_pnl(scores, get, [1], min_n=5)   # nur 1 Call → das Wallet mit mehr n
        assert "pnl" in scores["0xHIGH"] and "pnl" not in scores["0xLOW"]
