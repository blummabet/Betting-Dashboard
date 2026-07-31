#!/usr/bin/env python3
"""test_poly_whale_watch.py — Polymarket Whale-Watch (26.07.2026).
Sichert Sport-Mapping, Track-Record-Schwelle, Auswahl (Größe/Frische/Dedup/Aufstocken)
und den Telegram-sicheren Nachrichtenbau. Kein Modul-Level-Env (Audit-konform)."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import poly_whale_watch as P

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
def _ts(dt): return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def _pos(usd, league="TENNIS", side="Blockx", price=0.60, ageDays=0, wallet="0xabc123def456"):
    return {"wallet": wallet, "key": f"k-{side}", "side": side, "league": league,
            "firstPrice": price, "firstTs": _ts(NOW - timedelta(days=ageDays)), "usd": usd}


class TestSport(unittest.TestCase):
    def test_map(self):
        self.assertEqual(P._sport("ESPORTS")[0], "🎮")
        self.assertEqual(P._sport("TENNIS")[0], "🎾")
        self.assertEqual(P._sport("MLB")[0], "⚾")
        self.assertEqual(P._sport("soccer_mls")[0], "⚽")
        self.assertEqual(P._sport("SOMETHINGELSE"), ("🎯", "Somethingelse"))


class TestTrackRecord(unittest.TestCase):
    def test_too_thin_returns_none(self):
        self.assertIsNone(P.track_record({"0xa": {"n": 2, "wins": 2}}, "0xa"))

    def test_shows_hitrate(self):
        tr = P.track_record({"0xa": {"n": 5, "wins": 3}}, "0xa")
        self.assertIn("3/5", tr); self.assertIn("60%", tr)

    def test_unknown_wallet(self):
        self.assertIsNone(P.track_record({}, "0xzz"))


class TestSelect(unittest.TestCase):
    # Gestaffelt: ohne Record Schwelle $25k, mit Record (n≥3) $5k.
    def _tracked(self, wallet="0xREC"):
        return {"scores": {wallet: {"n": 5, "wins": 3}}}

    def test_untracked_below_25k_skipped(self):
        track = {"open": {"a": _pos(20000)}}          # groß, aber ohne Record < $25k
        self.assertEqual(P.select(track, {}, NOW), [])

    def test_untracked_big_included(self):
        track = {"open": {"a": _pos(30000)}}
        got = P.select(track, {}, NOW)
        self.assertEqual(len(got), 1); self.assertFalse(got[0][2])

    def test_tracked_wallet_lower_threshold(self):
        # dieselbe $6k-Position: mit Record gemeldet, ohne Record verworfen
        pos = _pos(6000, wallet="0xREC")
        tracked = {"open": {"a": pos}}; tracked.update(self._tracked())
        self.assertEqual(len(P.select(tracked, {}, NOW)), 1)
        self.assertEqual(P.select({"open": {"a": _pos(6000, wallet="0xNOREC")}}, {}, NOW), [])

    def test_bad_record_no_free_pass(self):
        # 0/4 (schlechter Record) bekommt NICHT die niedrige Schwelle → $6k verworfen
        track = {"open": {"a": _pos(6000, wallet="0xBAD")},
                 "scores": {"0xBAD": {"n": 4, "wins": 0}}}
        self.assertEqual(P.select(track, {}, NOW), [])
        # aber groß genug (≥$25k) kommt es trotzdem durch (reines Größen-Signal)
        big = {"open": {"a": _pos(30000, wallet="0xBAD")},
               "scores": {"0xBAD": {"n": 4, "wins": 0}}}
        self.assertEqual(len(P.select(big, {}, NOW)), 1)

    def test_stale_unseen_skipped(self):
        track = {"open": {"a": _pos(30000, ageDays=5)}}   # groß genug, aber 5 Tage alt
        self.assertEqual(P.select(track, {}, NOW), [])

    def test_already_seen_skipped(self):
        track = {"open": {"a": _pos(30000)}}
        seen = {"a": {"usd": 30000}}
        self.assertEqual(P.select(track, seen, NOW), [])

    def test_restock_realerts(self):
        track = {"open": {"a": _pos(45000)}}           # von 27000 → 45000 (≥ +50%)
        seen = {"a": {"usd": 27000}}
        got = P.select(track, seen, NOW)
        self.assertEqual(len(got), 1); self.assertTrue(got[0][2])

    def test_small_topup_not_realerted(self):
        track = {"open": {"a": _pos(30000)}}           # von 27000 → 30000 (< +50%)
        seen = {"a": {"usd": 27000}}
        self.assertEqual(P.select(track, seen, NOW), [])

    def test_sorted_by_size(self):
        track = {"open": {"a": _pos(30000, side="A"), "b": _pos(50000, side="B")}}
        got = P.select(track, {}, NOW)
        self.assertEqual(got[0][1]["side"], "B")   # größte zuerst


class TestBuildCard(unittest.TestCase):
    def test_core_fields_and_safe_tags(self):
        import re
        card = P.build_card(_pos(24000, league="MLB", side="Cleveland Guardians", price=0.46),
                            {}, restock=False)
        self.assertIn("Cleveland Guardians", card)
        self.assertIn("46¢", card)
        self.assertIn("⚾", card)
        self.assertIn("im Aufbau", card)          # neutral statt abschreckend
        bad = set(re.findall(r"</?([a-zA-Z0-9-]+)", card)) - {"b", "i", "a"}
        self.assertFalse(bad, f"verbotene Tags: {bad}")

    def test_wallet_is_clickable_profile_link(self):
        card = P.build_card(_pos(9000, wallet="0xabcdef1234567890abcd"), {}, False)
        self.assertIn('href="https://polymarket.com/profile/0xabcdef1234567890abcd"', card)
        self.assertIn("0xabcd…abcd", card)   # Kurz-ID bleibt als Linktext

    def test_track_record_line(self):
        card = P.build_card(_pos(9000, wallet="0xa"), {"0xa": {"n": 9, "wins": 6}}, False)
        self.assertIn("6/9 richtig", card); self.assertIn("67%", card)

    def test_weak_record_shown_neutral(self):
        # schwache 1/3-Bilanz NICHT als abschreckende Zahl — neutral „im Aufbau"
        card = P.build_card(_pos(30000, wallet="0xw"), {"0xw": {"n": 3, "wins": 1}}, False)
        self.assertIn("im Aufbau", card)
        self.assertNotIn("33%", card)
        self.assertNotIn("1/3", card)

    def test_good_record_highlighted(self):
        card = P.build_card(_pos(9000, wallet="0xg"), {"0xg": {"n": 6, "wins": 4}}, False)
        self.assertIn("bewiesene Wallet", card); self.assertIn("4/6 richtig", card)

    def test_contrarian_hint_under_45c(self):
        self.assertIn("Außenseiter", P.build_card(_pos(9000, price=0.40), {}, False))
        self.assertNotIn("Außenseiter", P.build_card(_pos(9000, price=0.60), {}, False))

    def test_restock_header(self):
        self.assertIn("stockt auf", P.build_card(_pos(9000), {}, restock=True))


if __name__ == "__main__":
    unittest.main()


class TestPublicWhale(unittest.TestCase):
    """31.07.2026 (Lucas) — öffentlicher Whale-Watch: kuratiert (riesig ab $100K / bewährt ab $25K),
    nur Sport + sinnvoller Preis, Wallet-Qualität annotiert."""

    def test_pub_quality_filter(self):
        self.assertTrue(P._pub_ok(_pos(50000, league="TENNIS", price=0.60)))
        self.assertFalse(P._pub_ok(_pos(50000, league="Greater Manchester", price=0.60)))  # Politik → 🎯
        self.assertFalse(P._pub_ok(_pos(50000, league="TENNIS", price=1.00)))              # quasi-settled
        self.assertFalse(P._pub_ok(_pos(50000, league="TENNIS", price=0.01)))              # Dust

    def test_public_bands(self):
        track = {
            "open": {
                "k1": _pos(30000, side="A", wallet="0xSHARP"),   # bewährt, $30K ≥ 25K → PASS
                "k2": _pos(30000, side="B", wallet="0xUNK"),     # unbekannt, $30K < 100K → SKIP
                "k3": _pos(120000, side="C", wallet="0xUNK2"),   # riesig, $120K ≥ 100K → PASS
            },
            "scores": {"0xSHARP": {"n": 6, "wins": 4, "clvSumPP": 12}},
        }
        cand = P.select(track, {}, NOW, P.PUB_MIN_USD_UNTRACKED, P.PUB_MIN_USD_TRACKED,
                        P.PUB_MIN_TR, P.PUB_MIN_HITRATE)
        keys = {c[0] for c in cand}
        self.assertIn("k1", keys)
        self.assertNotIn("k2", keys)
        self.assertIn("k3", keys)

    def test_public_card_proven(self):
        broad = {"k-Flamengo": {"shares": {"Flamengo": 100, "Palmeiras": 50}}}
        pos = _pos(150000, league="soccer_brasileirao", side="Flamengo", price=0.62, wallet="0xS")
        scores = {"0xS": {"n": 20, "wins": 14, "clvSumPP": 64}}   # 70%, Ø CLV +3.2pp
        msg = P.build_public_card(pos, scores, False, broad)
        self.assertIn("Polymarket Whale", msg)
        self.assertIn("Flamengo v Palmeiras", msg)      # Paarung aus broad
        self.assertIn("$150K", msg)
        self.assertIn("62¢", msg)
        self.assertIn("bewiesen scharf", msg)
        self.assertIn("14/20 richtig (70%, +3.2pp CLV)", msg)

    def test_public_card_pnl_when_present(self):
        pos = _pos(150000, league="TENNIS", side="Sinner", price=0.55, wallet="0xP")
        scores = {"0xP": {"n": 12, "wins": 8, "clvSumPP": 24, "pnl": 120000}}
        msg = P.build_public_card(pos, scores, False, {})
        self.assertIn("+$120", msg)   # Lifetime-P&L, sobald der Runner sie zieht
        self.assertIn("lifetime", msg)

    def test_public_card_unproven_neutral(self):
        pos = _pos(120000, league="NBA", side="Celtics", price=0.58, wallet="0xNEW")
        msg = P.build_public_card(pos, {}, False, {})
        self.assertIn("Track-Record noch im Aufbau", msg)
        self.assertNotIn("bewiesen scharf", msg)
