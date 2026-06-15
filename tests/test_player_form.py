#!/usr/bin/env python3
"""
test_player_form.py — Per-Spieler-Form-Loop (15.06.2026, liga-tauglich).

Schützt: positions-abhängige Form, ±15%-Deckel + Schrumpfung nach Spielanzahl,
Ledger-Dedup, und die Einspeisung ins lineup_signal (schwache Form → kleinerer Score).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import player_form as pf
from sharp_signals.lineup_signal import LineupSignal


class TestFormFactor(unittest.TestCase):
    def setUp(self):
        self.cfg = pf.load_config()

    def test_capped_at_15pct(self):
        base = {"role": "ATT", "rating": 7.4, "goals": 18, "assists": 6, "minutes": 2600}
        # extrem schwach über viele Spiele → darf nicht unter 0.85 (Deckel)
        recs = [{"minutes": 90, "rating": 4.0, "goals": 0, "assists": 0, "keyPasses": 0}] * 6
        f, _ = pf.compute_form_factor(recs, base, "ATT", self.cfg)
        self.assertGreaterEqual(f, 0.85)
        self.assertLessEqual(f, 1.15)

    def test_small_sample_shrinks_toward_neutral(self):
        base = {"role": "ATT", "rating": 7.0}
        one = [{"minutes": 90, "rating": 5.0, "goals": 0, "assists": 0, "keyPasses": 0}]
        many = one * 5
        f1, _ = pf.compute_form_factor(one, base, "ATT", self.cfg)
        f5, _ = pf.compute_form_factor(many, base, "ATT", self.cfg)
        # 1 Spiel muss näher an 1.0 liegen als 5 Spiele (Schrumpfung)
        self.assertLess(abs(1 - f1), abs(1 - f5))

    def test_striker_goalless_downgraded_even_with_ok_rating(self):
        # Kern-Szenario (Lucas): ordentliches Rating, aber torlos → Stürmer abgewertet
        base = {"role": "ATT", "rating": 7.0, "goals": 16, "assists": 4, "minutes": 2400}
        recs = [{"minutes": 90, "rating": 7.0, "goals": 0, "assists": 0, "keyPasses": 0}] * 3
        f, _ = pf.compute_form_factor(recs, base, "ATT", self.cfg)
        self.assertLess(f, 1.0, "torloser Stürmer trotz OK-Rating muss < 1.0 sein")

    def test_defender_judged_by_rating_not_goals(self):
        base = {"role": "DEF", "rating": 7.0}
        # Verteidiger ohne Tore, aber gutes Rating → NICHT abgewertet
        recs = [{"minutes": 90, "rating": 7.6, "goals": 0, "assists": 0, "keyPasses": 0}] * 3
        f, _ = pf.compute_form_factor(recs, base, "DEF", self.cfg)
        self.assertGreater(f, 1.0, "starker Verteidiger darf nicht für 0 Tore abgewertet werden")

    def test_no_records_neutral(self):
        f, _ = pf.compute_form_factor([], {"role": "ATT"}, "ATT", self.cfg)
        self.assertEqual(f, 1.0)


class TestLedger(unittest.TestCase):
    def test_append_dedup(self):
        ledger = {"records": []}
        rows = [{"playerId": 1, "fixtureId": 100, "minutes": 90},
                {"playerId": 2, "fixtureId": 100, "minutes": 80}]
        self.assertEqual(pf.append_records(ledger, rows), 2)
        # gleiche (player, fixture) nicht doppelt
        self.assertEqual(pf.append_records(ledger, rows), 0)
        self.assertEqual(len(ledger["records"]), 2)

    def test_rows_from_fixture_players_skips_zero_minutes(self):
        resp = [{"team": {"id": 5}, "players": [
            {"player": {"id": 1, "name": "A"}, "statistics": [{"games": {"minutes": 90, "rating": "7.0"},
             "goals": {"total": 1, "assists": 0}, "passes": {"key": 2}}]},
            {"player": {"id": 2, "name": "B"}, "statistics": [{"games": {"minutes": 0, "rating": None}}]},
        ]}]
        rows = pf.rows_from_fixture_players(999, resp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["playerId"], 1)

    def test_build_form_table_uses_baselines(self):
        ledger = {"records": [
            {"playerId": 7, "fixtureId": 1, "minutes": 90, "rating": 8.0, "goals": 2, "assists": 0, "keyPasses": 3, "ts": "2026-06-12T00:00:00Z"},
            {"playerId": 7, "fixtureId": 2, "minutes": 90, "rating": 7.8, "goals": 1, "assists": 1, "keyPasses": 2, "ts": "2026-06-15T00:00:00Z"},
        ]}
        baselines = {"7": {"role": "ATT", "rating": 7.0, "goals": 10, "assists": 5, "minutes": 2500}}
        table = pf.build_form_table(ledger, baselines)
        self.assertIn("7", table)
        self.assertGreater(table["7"]["form_factor"], 1.0)   # über Baseline → Aufwertung


class TestLineupIntegration(unittest.TestCase):
    def _ctx(self, form=None):
        c = {"matchKey": "A-B", "home_id": "A", "away_id": "B",
             "lineups": {"A-B": {"home": {"starting": [{"id": 99}], "subs": []},
                                 "away": {"starting": [{"id": 10}], "subs": []}}},
             "squads": {"A": {"key_players": [{"id": 1, "name": "S", "role": "ATT", "importance": 0.9}]},
                        "B": {"key_players": [{"id": 10, "name": "x", "role": "ATT", "importance": 0.9}]}}}
        if form is not None:
            c["player_form"] = form
        return c

    def test_weak_form_reduces_impact(self):
        sig = LineupSignal()
        base = sig.evaluate({"market": "Über 2.5 Tore"}, self._ctx())
        weak = sig.evaluate({"market": "Über 2.5 Tore"}, self._ctx({"1": {"form_factor": 0.85}}))
        self.assertLess(abs(weak.score), abs(base.score))

    def test_accepts_full_file_shape(self):
        # context kann das ganze player_form.json ({"players": {...}}) ODER nur das Mapping sein
        sig = LineupSignal()
        r = sig.evaluate({"market": "Über 2.5 Tore"},
                         self._ctx({"players": {"1": {"form_factor": 0.85}}}))
        self.assertIsNotNone(r)


class TestReturnerBoost(unittest.TestCase):
    """Rückkehrer-Boost (15.06.2026): präsenter Schlüsselspieler der zuletzt fehlte → Aufwertung."""

    def test_zero_minute_star_detected_via_teammate(self):
        # Star (id 1) hat KEINE Ledger-Zeile, Mitspieler (id 2) spielte 2 Team-Spiele →
        # games_missed des Stars muss via Mitspieler/Team-Fixtures = 2 sein.
        ledger = {"records": [
            {"playerId": 2, "teamId": 500, "fixtureId": 1, "minutes": 90, "rating": 7.0,
             "goals": 0, "assists": 0, "keyPasses": 1, "ts": "2026-06-10T00:00:00Z"},
            {"playerId": 2, "teamId": 500, "fixtureId": 2, "minutes": 90, "rating": 7.1,
             "goals": 0, "assists": 0, "keyPasses": 1, "ts": "2026-06-13T00:00:00Z"},
        ]}
        table = pf.build_form_table(ledger, {"1": {"role": "ATT"}, "2": {"role": "MID"}},
                                    squad_players={"ESP": [1, 2]})
        self.assertEqual(table["1"]["games_missed"], 2)
        self.assertEqual(table["1"]["recent_minutes"], 0.0)

    def _ctx_present(self, table):
        return {"matchKey": "ESP-X", "home_id": "ESP", "away_id": "X",
                "lineups": {"ESP-X": {"home": {"starting": [{"id": 1}, {"id": 2}], "subs": []},
                                      "away": {"starting": [{"id": 9}], "subs": []}}},
                "squads": {"ESP": {"key_players": [
                                {"id": 1, "name": "Star", "role": "ATT", "importance": 0.9},
                                {"id": 2, "name": "Mid", "role": "MID", "importance": 0.7}]},
                           "X": {"key_players": [{"id": 9, "name": "y", "role": "ATT", "importance": 0.8}]}},
                "player_form": table}

    def test_returning_star_boosts_over(self):
        sig = LineupSignal()
        table = {"1": {"form_factor": 1.0, "games_missed": 2}}
        r = sig.evaluate({"market": "Über 2.5 Tore"}, self._ctx_present(table))
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0, "präsenter Rückkehr-Stürmer sollte Über stützen")
        self.assertIn("zurück", r.evidence)

    def test_present_but_no_missed_games_no_boost(self):
        # Schlüsselspieler präsent, hat aber nichts verpasst (games_missed 0) → kein Boost
        sig = LineupSignal()
        table = {"1": {"form_factor": 1.0, "games_missed": 0}}
        r = sig.evaluate({"market": "Über 2.5 Tore"}, self._ctx_present(table))
        self.assertIsNone(r)   # alle starten, keiner fehlt, kein Rückkehrer → kein Signal

    def test_low_importance_returner_no_boost(self):
        # Randspieler (importance < return_min_importance) → kein Boost trotz games_missed
        sig = LineupSignal()
        ctx = self._ctx_present({"1": {"form_factor": 1.0, "games_missed": 2}})
        ctx["squads"]["ESP"]["key_players"][0]["importance"] = 0.4
        r = sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
