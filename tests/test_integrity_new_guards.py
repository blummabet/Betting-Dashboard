"""
test_integrity_new_guards.py — Guards für die Fehlerquellen vom 13./14.06.2026
(Auto-Bet-Kickoff, Resolved-Status-Propagation, AH-Leiter, Match-Stats, Soft-Book-
History). Daten werden injiziert (kein Disk-Lazy-Load), damit der Test deterministisch ist.
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from wm_data_integrity import run_checks  # noqa: E402

NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _result(checks, cid):
    return next((c for c in checks if c["id"] == cid), None)


class TestNewIntegrityGuards(unittest.TestCase):
    def _run(self, wm, auto_bets=None, history=None):
        return run_checks(wm, {}, {}, {}, now=NOW,
                          auto_bets={"bets": auto_bets or []},
                          history=history if history is not None else {})

    def test_autobet_without_kickoff_fails(self):
        wm = {"groups": {}}   # kein Fixture → keine Kickoff-Auflösung
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "autobet_kickoff")
        self.assertFalse(c["ok"])

    def test_autobet_with_kickoff_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-20T19:00:00Z"}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "autobet_kickoff")
        self.assertTrue(c["ok"])

    def test_finished_game_with_placed_bet_flagged(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-13T19:00:00Z",
             "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "placed"}]
        c = _result(self._run(wm, bets), "resolved_status_propagated")
        self.assertFalse(c["ok"])

    def test_finished_game_resolved_bet_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "kickoff": "2026-06-13T19:00:00Z",
             "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        bets = [{"homeId": "QAT", "awayId": "SUI", "market": "Over 2.5 Tore", "status": "lost"}]
        c = _result(self._run(wm, bets), "resolved_status_propagated")
        self.assertTrue(c["ok"])

    def test_finished_without_stats_flagged(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "result": {"status": "FT", "home_score": 1, "away_score": 1}}]}}}
        c = _result(self._run(wm), "finished_has_stats")
        self.assertFalse(c["ok"])

    def test_finished_with_stats_ok(self):
        wm = {"groups": {"B": {"fixtures": [
            {"home": "QAT", "away": "SUI", "result": {"status": "FT", "home_score": 1, "away_score": 1,
             "stats": {"xgTotal": 3.0, "homeXg": 0.6, "awayXg": 2.4}}}]}}}
        c = _result(self._run(wm), "finished_has_stats")
        self.assertTrue(c["ok"])

    def test_soft_book_history_all_pinnacle_flagged(self):
        wm = {"groups": {}}
        # 24 Snapshots, alle nur Pinnacle → lead_lag kann nie feuern
        hist = {"QAT-SUI": [{"ts": "x", "bk": "pinnacle"} for _ in range(24)]}
        c = _result(self._run(wm, history=hist), "soft_book_history")
        self.assertFalse(c["ok"])

    def test_soft_book_history_with_public_ok(self):
        wm = {"groups": {}}
        hist = {"QAT-SUI": [{"ts": "x", "bk": "pinnacle"} for _ in range(20)]
                + [{"ts": "x", "bk": "public"} for _ in range(4)]}
        c = _result(self._run(wm, history=hist), "soft_book_history")
        self.assertTrue(c["ok"])

    # ── Tor-Anker-Quelle (15.06.2026): warnt bei Soft-Fallback ──────────────
    def _wm_with_anchor(self, src):
        return {
            "groups": {"H": {"fixtures": [
                {"home": "ESP", "away": "CPV", "matchday": 1, "date": "2026-06-20"}]}},
            "odds": {"ESP-CPV": {"o25": 1.31, "u25": 3.6, "o25_src": src}},
            "picks": {"H-1-ESP-CPV": [
                {"market": "Über 2.5 Tore", "verdict": "BET", "modelOdds": 1.31}]},
        }

    def test_soft_sourced_anchor_flagged(self):
        c = _result(self._run(self._wm_with_anchor("williamhill")), "ou_anchor_source")
        self.assertFalse(c["ok"], "Soft-Book als Tor-Anker muss als Warnung auftauchen")

    def test_pinnacle_anchor_ok(self):
        c = _result(self._run(self._wm_with_anchor("pinnacle")), "ou_anchor_source")
        self.assertTrue(c["ok"])

    def test_untagged_anchor_not_checkable_ok(self):
        # Alte Daten ohne *_src-Tag → nicht prüfbar → kein false-positive
        wm = self._wm_with_anchor("pinnacle")
        del wm["odds"]["ESP-CPV"]["o25_src"]
        c = _result(self._run(wm), "ou_anchor_source")
        self.assertTrue(c["ok"])

    # ── AH-Edge-Sanity (Mirror-Phantom-Detektor, 15.06.2026) ────────────────
    def _run_poly(self, poly):
        return run_checks({"groups": {}}, poly, {}, {}, now=NOW,
                          auto_bets={"bets": []}, history={})

    def test_ah_phantom_edge_flagged(self):
        poly = {"allFixtures": [{"homeId": "ENG", "awayId": "PAN",
                "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.0235,
                              "fair": 0.5257, "edge": 50.2}]}]}
        c = _result(self._run_poly(poly), "ah_edge_sane")
        self.assertFalse(c["ok"])

    def test_ah_small_edge_ok(self):
        poly = {"allFixtures": [{"homeId": "URU", "awayId": "CPV",
                "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.365,
                              "fair": 0.4071, "edge": 4.2}]}]}
        c = _result(self._run_poly(poly), "ah_edge_sane")
        self.assertTrue(c["ok"])

    def test_ah_settled_market_not_flagged(self):
        # Spiel gelaufen → Poly-Preis springt auf 0/1, riesiger Schein-Edge.
        # Das ist ein Resolution-Artefakt, KEIN Mirror-Bug → Guard ignoriert es.
        poly = {"allFixtures": [
            {"homeId": "AUS", "awayId": "TUR",   # poly 1.0 (settled)
             "ah_edges": [{"side": "home", "line": -1.5, "poly": 1.0,
                           "fair": 0.0728, "edge": -92.7}]},
            {"homeId": "BEL", "awayId": "EGY",   # poly ~0 (settled)
             "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.005,
                           "fair": 0.3462, "edge": 34.1}]}]}
        c = _result(self._run_poly(poly), "ah_edge_sane")
        self.assertTrue(c["ok"], "Settled-Markt (poly 0/1) ist kein Phantom")

    # ── BTTS-Edge-Sanity (15.06.2026, BTTS-Auto-Trade verdrahtet) ───────────
    def test_btts_phantom_edge_flagged(self):
        poly = {"allFixtures": [{"homeId": "ESP", "awayId": "CPV",
                "poly_btts": 0.40, "fair_btts": 0.85, "edge_btts": 45.0}]}
        c = _result(self._run_poly(poly), "btts_edge_sane")
        self.assertFalse(c["ok"])

    def test_btts_small_edge_ok(self):
        poly = {"allFixtures": [{"homeId": "ESP", "awayId": "CPV",
                "poly_btts": 0.55, "fair_btts": 0.59, "edge_btts": 4.0,
                "poly_btts_no": 0.45, "fair_btts_no": 0.41, "edge_btts_no": -4.0}]}
        c = _result(self._run_poly(poly), "btts_edge_sane")
        self.assertTrue(c["ok"])

    def test_btts_settled_market_not_flagged(self):
        poly = {"allFixtures": [{"homeId": "GER", "awayId": "CUW",
                "poly_btts": 1.0, "fair_btts": 0.30, "edge_btts": -70.0}]}
        c = _result(self._run_poly(poly), "btts_edge_sane")
        self.assertTrue(c["ok"], "Settled BTTS-Markt (poly 0/1) ist kein Phantom")

    # ── AH/BTTS-Position-Bewertbarkeit (16.06.2026, Geld-Bug) ───────────────
    def _run_poly_ab(self, poly, bets):
        return run_checks({"groups": {}}, poly, {}, {}, now=NOW,
                          auto_bets={"bets": bets}, history={})

    def test_ah_position_token_in_cache_ok(self):
        poly = {"allFixtures": [{"homeId": "USA", "awayId": "AUS",
                "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.345,
                              "tokens": ["AHTOK", "AHNO"]}]}]}
        bets = [{"homeId": "USA", "awayId": "AUS", "market": "AH Heim -1.5",
                 "status": "placed", "tokenId": "AHTOK"}]
        c = _result(self._run_poly_ab(poly, bets), "ah_btts_position_priced")
        self.assertTrue(c["ok"])

    def test_ah_position_token_missing_flagged(self):
        poly = {"allFixtures": [{"homeId": "USA", "awayId": "AUS",
                "ah_edges": [{"side": "home", "line": -1.5, "poly": 0.345,
                              "tokens": ["AHTOK", "AHNO"]}]}]}
        bets = [{"homeId": "USA", "awayId": "AUS", "market": "AH Heim -1.5",
                 "status": "placed", "tokenId": "FALSCHER_TOKEN"}]
        c = _result(self._run_poly_ab(poly, bets), "ah_btts_position_priced")
        self.assertFalse(c["ok"])

    # ── Home/Away-Konsistenz (16.06.2026: war toter Guard, Poly=Wahrscheinlichkeit) ──
    def _run_ha(self, odds, prices):
        return run_checks({"groups": {}, "odds": odds}, {"prices": prices}, {}, {}, now=NOW,
                          auto_bets={"bets": []}, history={})

    def test_homeaway_swap_flagged_poly_probabilities(self):
        # Pinnacle: Heim-Fav (hw<aw). Poly (Wahrscheinlichkeit): Ausw-Fav (phw<paw) → Konflikt
        odds   = {"CPV-SAU": {"hw": 2.40, "aw": 2.63}}
        prices = {"CPV-SAU": {"hw": 0.345, "aw": 0.395}}
        c = _result(self._run_ha(odds, prices), "homeaway_consistent")
        self.assertFalse(c["ok"], "Poly als Wahrscheinlichkeit muss verglichen werden (nicht >1.0-gefiltert)")

    def test_homeaway_consistent_ok_when_agree(self):
        odds   = {"ENG-PAN": {"hw": 1.40, "aw": 7.0}}     # Heim klar Fav
        prices = {"ENG-PAN": {"hw": 0.72, "aw": 0.10}}    # Poly auch Heim Fav
        c = _result(self._run_ha(odds, prices), "homeaway_consistent")
        self.assertTrue(c["ok"])

    def test_homeaway_skips_coinflip(self):
        # |hw-aw| ≤ 0.15 → kein aussagekräftiger Favorit → nicht flaggen
        odds   = {"AAA-BBB": {"hw": 2.55, "aw": 2.50}}
        prices = {"AAA-BBB": {"hw": 0.40, "aw": 0.42}}
        c = _result(self._run_ha(odds, prices), "homeaway_consistent")
        self.assertTrue(c["ok"])

    # ── Odds-Freshness (16.06.2026: 13h alte Pinnacle-Odds, kein Guard fing es) ──
    def _run_fresh(self, updated_at):
        wm = {"groups": {}, "odds": {"ENG-PAN": {"hw": 1.4, "aw": 7.0, "updatedAt": updated_at}}}
        return run_checks(wm, {}, {}, {}, now=NOW, auto_bets={"bets": []}, history={})

    def test_stale_odds_flagged(self):
        # NOW = 2026-06-14 12:00; Odds von vor 13h → > 6h Warnschwelle
        c = _result(self._run_fresh("2026-06-13T23:00:00Z"), "odds_freshness")
        self.assertFalse(c["ok"])

    def test_fresh_odds_ok(self):
        c = _result(self._run_fresh("2026-06-14T09:00:00Z"), "odds_freshness")  # 3h alt
        self.assertTrue(c["ok"])


class TestSignalCoverageGuard(unittest.TestCase):
    """Coverage-Guard (21.06.2026, Lucas-Sorge: 'finden die Guards stille Fehler?').
    Schlägt an, wenn ein zuletzt zuverlässig feuerndes Signal heute slatewide 0 zeigt.
    History wird via _lazy-Monkeypatch injiziert (deterministisch, kein Disk)."""

    def setUp(self):
        import wm_data_integrity as W
        self.W = W
        self._orig = W._lazy
        self.ctx = type("C", (), {})()

    def tearDown(self):
        self.W._lazy = self._orig

    def _patch(self, hist):
        orig = self._orig
        self.W._lazy = lambda f: hist if "signal_history" in f else orig(f)

    def _day(self, **per):
        return {"date": "d", "perSignal": dict(per)}

    def test_silent_signal_flagged(self):
        # form_trend feuert 4 Tage zuverlässig, heute 0 → Verdacht
        self._patch([
            self._day(form_trend=140, xg_strength=120),
            self._day(form_trend=145, xg_strength=125),
            self._day(form_trend=150, xg_strength=130),
            self._day(form_trend=148, xg_strength=128),
            self._day(form_trend=0,   xg_strength=129),   # heute
        ])
        c = self.W.check_signal_coverage(self.ctx)
        self.assertFalse(c["ok"])
        self.assertTrue(any("form_trend" in f for f in c["failures"]))
        self.assertEqual(c["severity"], "warn")

    def test_intermittent_signal_not_flagged(self):
        # Wetter hat einen Off-Tag im Fenster → intermittierend → kein Fehlalarm
        self._patch([
            self._day(weather_signal=30),
            self._day(weather_signal=0),
            self._day(weather_signal=35),
            self._day(weather_signal=33),
            self._day(weather_signal=0),   # heute auch 0, aber Baseline nicht durchgehend
        ])
        c = self.W.check_signal_coverage(self.ctx)
        self.assertTrue(c["ok"])

    def test_always_zero_signal_not_flagged(self):
        # injury feuert nie (API leer) → war nie aktiv → kein Fehlalarm
        self._patch([self._day(injury=0) for _ in range(5)])
        c = self.W.check_signal_coverage(self.ctx)
        self.assertTrue(c["ok"])

    def test_too_little_history_ok(self):
        self._patch([self._day(form_trend=100), self._day(form_trend=0)])
        c = self.W.check_signal_coverage(self.ctx)
        self.assertTrue(c["ok"])


class TestTradeClvCoverageGuard(unittest.TestCase):
    """Mess-Schicht-Guard (21.06.2026, Lucas): CLV/Closing muss erfasst sein, sonst ist
    die Trade-Auswertung teilblind. History via _lazy-Monkeypatch injiziert."""

    def setUp(self):
        import wm_data_integrity as W
        self.W = W
        self._orig = W._lazy
        self.ctx = type("C", (), {})()

    def tearDown(self):
        self.W._lazy = self._orig

    def _patch(self, pm):
        orig = self._orig
        res = {"summary": {"postmortem": pm}}
        self.W._lazy = lambda f: res if "wm_results" in f else orig(f)

    def test_low_clv_coverage_flagged(self):
        self._patch({"closedN": 15, "clvCoverage": "4/15",
                     "heldToClose": {"n": 0}})
        c = self.W.check_trade_clv_coverage(self.ctx)
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")
        self.assertTrue(any("CLV nur bei" in f for f in c["failures"]))
        self.assertTrue(any("polyClose" in f for f in c["failures"]))

    def test_good_coverage_ok(self):
        self._patch({"closedN": 12, "clvCoverage": "10/12",
                     "heldToClose": {"n": 8}})
        c = self.W.check_trade_clv_coverage(self.ctx)
        self.assertTrue(c["ok"])

    def test_too_few_closed_ok(self):
        self._patch({"closedN": 3, "clvCoverage": "0/3", "heldToClose": {"n": 0}})
        c = self.W.check_trade_clv_coverage(self.ctx)
        self.assertTrue(c["ok"])


class TestStreaksGuardAndMlsCtx(unittest.TestCase):
    """29.06.2026: Streaks-Frische-Guard + is_liga gilt auch für mls_default."""

    def _streaks_check(self, streaks):
        checks = run_checks({"groups": {}}, {}, {}, {}, now=NOW, history={}, streaks=streaks)
        return _result(checks, "streaks_fresh")

    def test_streaks_missing_flagged(self):
        self.assertFalse(self._streaks_check({})["ok"])

    def test_streaks_old_schema_flagged(self):
        # Serien ohne ratePct = Alt-Schema → WARN (genau Lucas' Bug).
        old = {"_meta": {"generatedAt": NOW.isoformat()},
               "streaks": [{"team": "X", "type": "over25", "length": 5}]}
        self.assertFalse(self._streaks_check(old)["ok"])

    def test_streaks_current_schema_ok(self):
        fresh = {"_meta": {"generatedAt": NOW.isoformat()},
                 "streaks": [{"team": "X", "type": "over25", "length": 5, "ratePct": 72}]}
        self.assertTrue(self._streaks_check(fresh)["ok"])

    def test_mls_profile_counts_as_club_mode(self):
        from wm_data_integrity import IntegrityCtx
        ctx_mls = IntegrityCtx({"_meta": {"profile": "mls_default"}, "groups": {}}, {}, {}, {})
        ctx_wm = IntegrityCtx({"_meta": {"profile": "wm2026"}, "groups": {}}, {}, {}, {})
        self.assertTrue(ctx_mls.is_liga)    # MLS → WM-spezifische Guards passen
        self.assertFalse(ctx_wm.is_liga)


if __name__ == "__main__":
    unittest.main()
