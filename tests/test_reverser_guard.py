#!/usr/bin/env python3
"""
test_reverser_guard.py — Frische-Modell + Reverser-Guard (18.06.2026, Lucas).

Der „Move seit Eröffnung" wird in seinen LETZTEN Bewegungs-Abschnitt (latest leg) aufgeteilt
— fenster-frei (kein fixes 24h), weil bei 30-Min-Snaps der frische Move auch 5 Tage vor
Anpfiff passieren kann. Drei Zustände: confirm / drift / reverse. Ein Reverser stuft den
Pick zurück und leitet die sichere Gegen-Linie ab (läuft durch die Signal-Engine).
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import generate_wm_picks as G  # noqa: E402
from wm_data_integrity import run_checks  # noqa: E402

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def _snap(hw, ts, dr=3.4, aw=3.6):
    return {"bk": "pinnacle", "ts": ts.isoformat(), "hw": hw, "dr": dr, "aw": aw}


def _result(checks, cid):
    return next((c for c in checks if c["id"] == cid), None)


class TestFreshnessModel(unittest.TestCase):
    def test_reverse_latest_leg_overrides_old_move(self):
        # Linie läuft 5 Tage FÜR uns (2.20→2.00), dreht dann vor 2 Tagen, fällt (2.00→2.30).
        # Ein fixes 24h-Fenster hätte den Reverser verschluckt — die latest-leg-Logik nicht.
        hist = [_snap(2.20, NOW - timedelta(days=6)), _snap(2.10, NOW - timedelta(days=4)),
                _snap(2.00, NOW - timedelta(days=2)), _snap(2.15, NOW - timedelta(days=1)),
                _snap(2.30, NOW - timedelta(hours=2))]
        a = G.analyze_recent_move(hist, "Heimsieg")
        self.assertEqual(a["state"], "reverse")
        self.assertLess(a["movePP"], -G.REVERSER_THRESHOLD_PP)
        self.assertGreater(a["legHours"], 24)  # dreht seit ~2 Tagen, nicht nur 24h

    def test_confirm_when_money_keeps_running_for_pick(self):
        hist = [_snap(2.40, NOW - timedelta(days=5)), _snap(2.20, NOW - timedelta(days=3)),
                _snap(2.05, NOW - timedelta(days=1)), _snap(1.95, NOW - timedelta(hours=2))]
        a = G.analyze_recent_move(hist, "Heimsieg")
        self.assertEqual(a["state"], "confirm")
        self.assertGreaterEqual(a["movePP"], G.CONFIRM_THRESHOLD_PP)

    def test_drift_when_recent_leg_is_flat(self):
        # Großer alter Move, aber die jüngsten Snaps sind quasi unbewegt → ruht.
        hist = [_snap(2.60, NOW - timedelta(days=8)), _snap(2.05, NOW - timedelta(days=5)),
                _snap(2.04, NOW - timedelta(days=1)), _snap(2.05, NOW - timedelta(hours=1))]
        a = G.analyze_recent_move(hist, "Heimsieg")
        self.assertEqual(a["state"], "drift")

    def test_unmappable_market_returns_none(self):
        hist = [_snap(2.1, NOW - timedelta(days=1)), _snap(2.0, NOW)]
        self.assertIsNone(G.analyze_recent_move(hist, "Über 2.5 Tore"))  # kein Tor-Key in Snaps

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(G.analyze_recent_move([_snap(2.0, NOW)], "Heimsieg"))

    def test_lastmoveh_distinguishes_fresh_vs_old_reversal(self):
        # Frischer Reverser: Gegen-Move passiert gerade eben.
        fresh = [_snap(2.00, NOW - timedelta(days=4)), _snap(1.95, NOW - timedelta(days=2)),
                 _snap(2.20, NOW - timedelta(hours=2))]
        a = G.analyze_recent_move(fresh, "Heimsieg")
        self.assertEqual(a["state"], "reverse")
        self.assertLessEqual(a["lastMoveH"], G.STALE_AFTER_H)   # frisch
        # Alter Reverser: Gegen-Move vor 7 Tagen, seither flach.
        old = [_snap(2.00, NOW - timedelta(days=14)), _snap(2.25, NOW - timedelta(days=7)),
               _snap(2.25, NOW - timedelta(days=1)), _snap(2.25, NOW - timedelta(hours=2))]
        b = G.analyze_recent_move(old, "Heimsieg")
        self.assertEqual(b["state"], "reverse")
        self.assertGreater(b["lastMoveH"], G.STALE_AFTER_H)     # alt


class TestReverserCounter(unittest.TestCase):
    def test_heimsieg_counter_is_dc_x2(self):
        snap = {"dcX2": 1.55, "hw": 2.30, "dr": 3.4, "aw": 3.6}
        ctr = G._derive_reverser_counter({"market": "Heimsieg"}, snap, -6.5)
        self.assertIsNotNone(ctr)
        self.assertEqual(ctr["market"], "Doppelte Chance — X2")
        self.assertTrue(ctr["reverserCounter"])
        self.assertEqual(ctr["counterOf"], "Heimsieg")
        self.assertEqual(ctr["verdict"], "ABWÄGEN")  # nie Auto-BET, reift via Conviction

    def test_counter_below_floor_is_dropped(self):
        snap = {"dcX2": 1.20}  # < 1.35 Floor → zu kurz, kein Mehrwert
        self.assertIsNone(G._derive_reverser_counter({"market": "Heimsieg"}, snap, -6.5))

    def test_over_counter_is_safe_under(self):
        snap = {"u35": 1.40}
        ctr = G._derive_reverser_counter({"market": "Über 2.5 Tore"}, snap, -5.0)
        self.assertEqual(ctr["market"], "Unter 3.5 Tore")

    def test_unmappable_market_no_counter(self):
        self.assertIsNone(G._derive_reverser_counter({"market": "BTTS Ja"}, {}, -5.0))


class TestReverserGuard(unittest.TestCase):
    def _run(self, picks):
        wm = {"groups": {}, "picks": picks}
        return run_checks(wm, {}, {}, {}, now=NOW,
                          auto_bets={"bets": []}, history={})

    def test_reverser_still_bet_flagged(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "BET",
             "reverser": True, "reverserPP": -6.1}]}
        c = _result(self._run(picks), "reverser_demoted")
        self.assertFalse(c["ok"])

    def test_reverser_demoted_ok(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "ABWÄGEN",
             "reverser": True, "reverserPP": -6.1}]}
        c = _result(self._run(picks), "reverser_demoted")
        self.assertTrue(c["ok"])

    def test_non_reverser_bet_ok(self):
        picks = {"A-1-AAA-BBB": [
            {"market": "Heimsieg", "source": "steam", "verdict": "BET",
             "freshnessState": "confirm"}]}
        c = _result(self._run(picks), "reverser_demoted")
        self.assertTrue(c["ok"])


if __name__ == "__main__":
    unittest.main()
