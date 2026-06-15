"""
tests/test_lineup_signal.py — Unit-Tests für lineup_signal

Coverage:
  - Score-Direction für alle Markttypen (over/under/home/away/dnb/dc)
  - Top-Scorer-Status: missing / benched / starting / unknown
  - Min-Goals-Schwelle (irrelevanter Spieler triggert nichts)
  - Fuzzy Name-Matching (mit/ohne Akzente, Last-Name-Match)
  - Confidence: full bei missing, partial bei benched
  - Multiple Teams (beide Stürmer betroffen)
  - Return None bei fehlenden Daten
  - Anti-Korrelation: unique group, kein Discount
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.lineup_signal import (
    LineupSignal, _normalize_name, _player_in_list, _outcome_side_from_market
)


def _ctx(home_id="MEX", away_id="ZAF",
         home_starting=None, home_subs=None,
         away_starting=None, away_subs=None,
         home_scorer=None, away_scorer=None):
    return {
        "matchKey": f"{home_id}-{away_id}",
        "home_id":  home_id,
        "away_id":  away_id,
        "lineups": {
            f"{home_id}-{away_id}": {
                "home": {"starting": home_starting or [], "subs": home_subs or []},
                "away": {"starting": away_starting or [], "subs": away_subs or []},
                "fetchedAt": "2026-06-11T18:00:00+00:00",
            }
        },
        "squads": {
            home_id: home_scorer or {"name": "R. Jiménez", "goals": 7},
            away_id: away_scorer or {"name": "P. Tau", "goals": 5},
        },
    }


class TestNormalization(unittest.TestCase):
    def test_normalize_strips_accents(self):
        self.assertEqual(_normalize_name("Jiménez"), "jimenez")
        self.assertEqual(_normalize_name("Müller"), "muller")
        self.assertEqual(_normalize_name("Çağlar"), "caglar")

    def test_normalize_empty(self):
        self.assertEqual(_normalize_name(""), "")
        self.assertEqual(_normalize_name(None), "")


class TestPlayerInList(unittest.TestCase):
    def test_exact_substring(self):
        players = [{"name": "Raúl Jiménez"}, {"name": "Other Guy"}]
        self.assertTrue(_player_in_list("Jiménez", players))

    def test_lastname_match(self):
        """'R. Jiménez' findet 'Raúl Jiménez' über Last-Name."""
        players = [{"name": "Raúl Alves Jiménez"}]
        self.assertTrue(_player_in_list("R. Jiménez", players))

    def test_not_in_list(self):
        players = [{"name": "Anderer Spieler"}]
        self.assertFalse(_player_in_list("R. Jiménez", players))

    def test_empty_name(self):
        self.assertFalse(_player_in_list("", [{"name": "Anyone"}]))


class TestMarketSideMapping(unittest.TestCase):
    def test_over_markets(self):
        self.assertEqual(_outcome_side_from_market("Über 2.5 Tore"), "over")
        self.assertEqual(_outcome_side_from_market("Over 1.5 Tore"), "over")

    def test_under_markets(self):
        self.assertEqual(_outcome_side_from_market("Unter 2.5 Tore"), "under")
        self.assertEqual(_outcome_side_from_market("Under 3.5 Tore"), "under")

    def test_outright(self):
        self.assertEqual(_outcome_side_from_market("Heimsieg"), "home")
        self.assertEqual(_outcome_side_from_market("Auswärtssieg"), "away")
        self.assertEqual(_outcome_side_from_market("Doppelte Chance — 1X"), "home")
        self.assertEqual(_outcome_side_from_market("DNB: Heimteam"), "home")

    def test_unknown_market(self):
        self.assertEqual(_outcome_side_from_market("Über 9.5 Ecken"), "unknown")


class TestSignalEvaluation(unittest.TestCase):
    def setUp(self):
        self.sig = LineupSignal()

    def test_returns_none_when_no_lineups(self):
        ctx = {"matchKey": "MEX-ZAF", "home_id": "MEX", "away_id": "ZAF",
               "lineups": {}, "squads": {}}
        result = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNone(result)

    def test_returns_none_when_all_scorers_starting(self):
        ctx = _ctx(
            home_starting=[{"name": "Raúl Jiménez"}],
            away_starting=[{"name": "Percy Tau"}],
        )
        result = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNone(result)

    def test_home_scorer_missing_negative_over(self):
        """Heim-Top-Scorer fehlt komplett → Über = negativ."""
        ctx = _ctx(
            home_starting=[{"name": "Andere"}],
            home_subs=[{"name": "Bench Guy"}],
            away_starting=[{"name": "Percy Tau"}],
        )
        result = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)
        self.assertEqual(result.confidence, 0.80)  # missing → full conf
        self.assertIn("fehlt", result.evidence)

    def test_home_scorer_missing_positive_under(self):
        """Heim-Top-Scorer fehlt → Unter = positiv."""
        ctx = _ctx(
            home_starting=[{"name": "Andere"}],
            away_starting=[{"name": "Percy Tau"}],
        )
        result = self.sig.evaluate({"market": "Unter 2.5 Tore"}, ctx)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)

    def test_away_scorer_missing_positive_for_home_win(self):
        """Auswärts-Stürmer fehlt → Heimsieg-Pick = positiv."""
        ctx = _ctx(
            home_starting=[{"name": "Raúl Jiménez"}],
            away_starting=[{"name": "Andere"}],  # Percy Tau fehlt
        )
        result = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(result)
        self.assertGreater(result.score, 0)

    def test_home_scorer_missing_negative_for_home_win(self):
        """Heim-Stürmer fehlt → Heimsieg-Pick = negativ."""
        ctx = _ctx(
            home_starting=[{"name": "Andere"}],  # R. Jiménez fehlt
            away_starting=[{"name": "Percy Tau"}],
        )
        result = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(result)
        self.assertLess(result.score, 0)

    def test_benched_has_lower_confidence_than_missing(self):
        ctx_bench = _ctx(
            home_starting=[{"name": "Andere"}],
            home_subs=[{"name": "Raúl Jiménez"}],
            away_starting=[{"name": "Percy Tau"}],
        )
        ctx_miss = _ctx(
            home_starting=[{"name": "Andere"}],
            home_subs=[],
            away_starting=[{"name": "Percy Tau"}],
        )
        r_bench = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx_bench)
        r_miss = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx_miss)
        self.assertLess(r_bench.confidence, r_miss.confidence)
        # missing-score sollte größer (absolut) als benched-score sein
        self.assertGreater(abs(r_miss.score), abs(r_bench.score))

    def test_min_goals_threshold(self):
        """Spieler unter min_goals zählt nicht als Schlüsselspieler."""
        ctx = _ctx(
            home_starting=[{"name": "Andere"}],
            home_scorer={"name": "R. Jiménez", "goals": 1},  # < 2
            away_starting=[{"name": "Percy Tau"}],
        )
        result = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNone(result)   # kein wichtiger Spieler → kein Signal

    def test_unknown_market_returns_none(self):
        ctx = _ctx(home_starting=[{"name": "Andere"}],
                   away_starting=[{"name": "Andere"}])
        result = self.sig.evaluate({"market": "Über 9.5 Ecken"}, ctx)
        self.assertIsNone(result)

    def test_both_teams_missing_doubles_effect(self):
        """Wenn beide Stürmer fehlen, ist der Score (über) doppelt-negativ."""
        ctx = _ctx(
            home_starting=[{"name": "Andere1"}],
            away_starting=[{"name": "Andere2"}],
        )
        result = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(result)
        self.assertLess(result.score, -3.0)  # missing_score × 2 = 5.0


class TestSignalRegistry(unittest.TestCase):
    """Sanity: Signal ist in registry registriert + unique group."""

    def test_lineup_signal_in_active_signals(self):
        from sharp_signals.registry import ACTIVE_SIGNALS
        names = [s.name() for s in ACTIVE_SIGNALS]
        self.assertIn("lineup_signal", names)

    def test_lineup_signal_unique_group(self):
        from sharp_signals.registry import SIGNAL_GROUPS
        self.assertEqual(SIGNAL_GROUPS.get("lineup_signal"), "unique")

    def test_lineup_signal_in_weights(self):
        import json
        weights = json.loads((REPO / "signal_weights.json").read_text(encoding="utf-8"))
        self.assertIn("lineup_signal", weights)


class TestFullAbsenceEvaluation(unittest.TestCase):
    """Volle Ausfall-Wertung (15.06.2026): positions-bewusst, alle Schlüsselspieler.

    Spieler werden per id gematcht. starting/subs = Liste {id, name}. Fehlt ein
    key_player in beiden → 'missing'.
    """

    def _ctx_full(self, side_present_ids_home, side_present_ids_away,
                  kp_home, kp_away, home_subs_ids=(), away_subs_ids=()):
        def lst(ids):
            return [{"id": i, "name": f"p{i}"} for i in ids]
        return {
            "matchKey": "AAA-BBB", "home_id": "AAA", "away_id": "BBB",
            "lineups": {"AAA-BBB": {
                "home": {"starting": lst(side_present_ids_home), "subs": lst(home_subs_ids)},
                "away": {"starting": lst(side_present_ids_away), "subs": lst(away_subs_ids)},
                "fetchedAt": "2026-06-15T18:00:00+00:00",
            }},
            "squads": {"AAA": {"key_players": kp_home}, "BBB": {"key_players": kp_away}},
        }

    def _kp(self, pid, role, imp=0.9):
        return {"id": pid, "name": f"p{pid}", "role": role, "importance": imp}

    def test_missing_defender_pushes_over_positive(self):
        # Heim-Innenverteidiger (id 2) fehlt → mehr Gegentore → Über positiv
        kp_home = [self._kp(1, "ATT"), self._kp(2, "DEF")]
        ctx = self._ctx_full([1], [10], kp_home, [self._kp(10, "ATT")])
        sig = LineupSignal()
        r = sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0, "fehlender Verteidiger sollte Über stützen")
        self.assertEqual(r.metadata["mode"], "full")

    def test_missing_striker_pushes_over_negative(self):
        # Heim-Stürmer (id 1) fehlt → eigenes Team trifft weniger → Über negativ
        kp_home = [self._kp(1, "ATT"), self._kp(2, "DEF")]
        ctx = self._ctx_full([2], [10], kp_home, [self._kp(10, "ATT")])
        r = LineupSignal().evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0, "fehlender Stürmer sollte Über schwächen")

    def test_missing_keeper_helps_opponent_outright(self):
        # Auswärts-Keeper (id 20) fehlt → Heimsieg wahrscheinlicher → positiv
        kp_away = [self._kp(10, "ATT"), self._kp(20, "GK")]
        ctx = self._ctx_full([1], [10], [self._kp(1, "ATT")], kp_away)
        r = LineupSignal().evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_benched_weaker_than_missing(self):
        kp_home = [self._kp(1, "ATT")]
        # Variante A: Stürmer fehlt ganz
        miss = self._ctx_full([9], [10], kp_home, [self._kp(10, "ATT")])
        # Variante B: Stürmer auf Bank
        bench = self._ctx_full([9], [10], kp_home, [self._kp(10, "ATT")], home_subs_ids=[1])
        s_miss = LineupSignal().evaluate({"market": "Über 2.5 Tore"}, miss).score
        s_bench = LineupSignal().evaluate({"market": "Über 2.5 Tore"}, bench).score
        # Beide negativ (Stürmer weg), aber Bank schwächer als komplett fehlt
        self.assertLess(s_miss, s_bench)

    def test_all_starting_returns_none(self):
        kp_home = [self._kp(1, "ATT"), self._kp(2, "DEF")]
        kp_away = [self._kp(10, "ATT")]
        ctx = self._ctx_full([1, 2], [10], kp_home, kp_away)
        self.assertIsNone(LineupSignal().evaluate({"market": "Über 2.5 Tore"}, ctx))

    def test_falls_back_to_top_scorer_without_key_players(self):
        # Keine key_players → Legacy-Pfad (mode top_scorer)
        ctx = _ctx(home_starting=[{"id": 5, "name": "Andere"}],
                   home_scorer={"name": "R. Jiménez", "goals": 7},
                   away_scorer={"name": "P. Tau", "goals": 5})
        r = LineupSignal().evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertEqual(r.metadata["mode"], "top_scorer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
