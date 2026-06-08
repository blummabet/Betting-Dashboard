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


if __name__ == "__main__":
    unittest.main(verbosity=2)
