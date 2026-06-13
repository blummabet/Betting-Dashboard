"""
tests/test_weather_signal.py — Tests für weather_signal

Coverage:
  - Hitze-Threshold (<30°C kein Signal)
  - Cold-team Penalty stärker als temperate
  - Hot-team kein Penalty
  - Anpfiff-Modifier (Mittag = volle Hitze, Abend gedämpft)
  - Score-Direction für over/under/home/away
  - Venue-Timezone-Offset (Dallas/Mexico City etc.)
  - Anti-Korr Context-Family
  - Registry + Config + Workflow + Pipe in fixtures
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.weather_signal import (
    WeatherSignal, TEAM_CLIMATE,
    _kickoff_modifier, _venue_offset_to_vienna, _outcome_side, _get_weather
)


def _ctx(home="MEX", away="NOR", temp=35.0,
         venue="AT&T Stadium, Dallas", kickoff="20:00"):
    """Default: Mexico vs Norwegen in Dallas, 35°C, 20:00 Wien = 13:00 Dallas (Mittag)."""
    return {
        "matchKey":     f"{home}-{away}",
        "home_id":      home,
        "away_id":      away,
        "kickoff_time": kickoff,
        "venue":        venue,
        "weather": {
            f"wm-{home.lower()}-vs-{away.lower()}-2026-06-20": {
                "tempMax":           temp,
                "forecastAvailable": True,
                "condition":         "sonnig",
            }
        },
    }


class TestTeamClimateMapping(unittest.TestCase):
    def test_cold_climate_teams(self):
        for t in ["NOR", "SWE", "SCO", "DEN"]:
            self.assertEqual(TEAM_CLIMATE.get(t), "cold")

    def test_hot_climate_teams(self):
        for t in ["MEX", "BRA", "SAU", "EGY"]:
            self.assertEqual(TEAM_CLIMATE.get(t), "hot")

    def test_temperate_teams(self):
        for t in ["ENG", "GER", "NED"]:
            self.assertEqual(TEAM_CLIMATE.get(t), "temperate")


class TestKickoffModifier(unittest.TestCase):
    def setUp(self):
        self.t = {
            "kickoff_modifier_midday":      1.00,
            "kickoff_modifier_afternoon":   0.80,
            "kickoff_modifier_evening":     0.55,
            "kickoff_modifier_night":       0.35,
        }

    def test_midday_in_dallas(self):
        """Wien 20:00 → Dallas 13:00 → Mittag (1.0)."""
        mod = _kickoff_modifier("20:00", "AT&T Stadium, Dallas", self.t)
        self.assertEqual(mod, 1.00)

    def test_evening_in_dallas(self):
        """Wien 02:00 → Dallas 19:00 → Abend (0.55)."""
        mod = _kickoff_modifier("02:00", "AT&T Stadium, Dallas", self.t)
        self.assertEqual(mod, 0.55)

    def test_no_venue_offset(self):
        """Venue unbekannt → 0h offset → Wien-Stunde direkt."""
        mod = _kickoff_modifier("13:00", "Unknown Stadium", self.t)
        self.assertEqual(mod, 1.00)   # 13:00 = Mittag


class TestVenueOffset(unittest.TestCase):
    def test_dallas_central(self):
        self.assertEqual(_venue_offset_to_vienna("AT&T Stadium, Dallas"), -7)

    def test_la_pacific(self):
        self.assertEqual(_venue_offset_to_vienna("SoFi Stadium, Los Angeles"), -9)

    def test_ny_eastern(self):
        self.assertEqual(_venue_offset_to_vienna("MetLife Stadium, New York"), -6)

    def test_mexico_city(self):
        self.assertEqual(_venue_offset_to_vienna("Estadio Azteca, Mexico City"), -7)


class TestOutcomeSide(unittest.TestCase):
    def test_over_goals(self):
        self.assertEqual(_outcome_side("Über 2.5 Tore"), "over")

    def test_under_goals(self):
        self.assertEqual(_outcome_side("Unter 2.5 Tore"), "under")

    def test_outright(self):
        self.assertEqual(_outcome_side("Heimsieg"), "home")
        self.assertEqual(_outcome_side("Auswärtssieg"), "away")

    def test_over_corners_returns_unknown(self):
        """Über 9.5 Ecken ist nicht goals-bezogen."""
        self.assertEqual(_outcome_side("Über 9.5 Ecken"), "unknown")


class TestSignalEvaluation(unittest.TestCase):
    def setUp(self):
        self.sig = WeatherSignal()

    def test_returns_none_below_heat_threshold(self):
        """28°C unter Schwelle → kein Signal."""
        ctx = _ctx(home="MEX", away="NOR", temp=28.0)
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx))

    def test_returns_none_no_weather(self):
        ctx = _ctx(home="MEX", away="NOR")
        ctx["weather"] = {}
        self.assertIsNone(self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx))

    def test_cold_vs_hot_over_negative(self):
        """Norwegen vs Mexico in 35°C Dallas Mittag, Über-Pick → negativ (Norwegen leidet)."""
        ctx = _ctx(home="MEX", away="NOR", temp=35.0,
                   venue="AT&T Stadium, Dallas", kickoff="20:00")
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)
        self.assertIn("NOR", r.evidence)
        self.assertIn("35", r.evidence)

    def test_cold_vs_hot_under_positive(self):
        ctx = _ctx(home="MEX", away="NOR", temp=35.0)
        r = self.sig.evaluate({"market": "Unter 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_home_pick_away_cold_positive(self):
        """Heimsieg-Pick wenn Auswärts cold-team → positiv (Auswärts schwächer)."""
        ctx = _ctx(home="MEX", away="NOR", temp=35.0)
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_home_pick_home_cold_negative(self):
        """Heimsieg-Pick wenn Heim cold-team → negativ."""
        ctx = _ctx(home="NOR", away="MEX", temp=35.0)
        r = self.sig.evaluate({"market": "Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_hot_vs_hot_no_signal(self):
        """Beide heat-tolerant → kein Signal."""
        ctx = _ctx(home="MEX", away="BRA", temp=35.0)
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNone(r)

    def test_evening_kickoff_lower_magnitude(self):
        """Abend-Anpfiff bei selber Hitze → schwächeres Signal als Mittag."""
        ctx_mid = _ctx(home="MEX", away="NOR", temp=35.0, kickoff="20:00")  # Dallas 13:00
        ctx_eve = _ctx(home="MEX", away="NOR", temp=35.0, kickoff="02:00")  # Dallas 19:00
        r_mid = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx_mid)
        r_eve = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx_eve)
        self.assertIsNotNone(r_mid)
        if r_eve is not None:
            # Mittag-Signal stärker (mehr negativ)
            self.assertLess(r_mid.score, r_eve.score)

    def test_unknown_market_returns_none(self):
        ctx = _ctx(home="MEX", away="NOR", temp=35.0)
        self.assertIsNone(self.sig.evaluate({"market": "Über 9.5 Ecken"}, ctx))


class TestRegistryAndConfig(unittest.TestCase):
    def test_signal_registered(self):
        from sharp_signals.registry import ACTIVE_SIGNALS, SIGNAL_GROUPS
        names = [s.name() for s in ACTIVE_SIGNALS]
        self.assertIn("weather_signal", names)
        # context-Familie (anti-korr mit Travel + Injury)
        self.assertEqual(SIGNAL_GROUPS.get("weather_signal"), "context")
        # Mindestens 13 Signale aktiv (weather_signal sollte definitiv dabei sein;
        # neue Signale dürfen nach oben ergänzen — keine harte obere Schranke)
        self.assertGreaterEqual(len(ACTIVE_SIGNALS), 13)

    def test_signal_weight_present(self):
        w = json.loads((REPO / "signal_weights.json").read_text(encoding="utf-8"))
        self.assertIn("weather_signal", w)
        # FIX 14.06.2026: Gewicht wird vom Bayesian-Loop GELERNT — es driftet von 1.0
        # weg, sobald Wetter-Spiele aufgelöst sind (z.B. nach QAT-SUI → 1.1). Daher
        # nur Präsenz + plausible Spanne prüfen, NICHT == 1.0 (sonst bricht der Test
        # jedes Mal, wenn das Lernsystem korrekt arbeitet).
        wt = w["weather_signal"]["weight"]
        self.assertIsInstance(wt, (int, float))
        self.assertTrue(0.1 <= wt <= 3.0, f"weather-Gewicht außerhalb plausibler Spanne: {wt}")

    def test_config_section_present(self):
        cfg = json.loads((REPO / "cocobet_config.json").read_text(encoding="utf-8"))
        wm = cfg["profiles"]["wm2026"]
        self.assertIn("weather_signal", wm)
        self.assertEqual(wm["weather_signal"]["heat_threshold"], 30.0)


class TestPipelineIntegration(unittest.TestCase):
    def test_state_registry_has_wm_weather(self):
        reg = json.loads((REPO / "state_files_registry.json").read_text(encoding="utf-8"))
        self.assertIn("wm_weather.json",
                      reg["categories"]["fetch_wm_data"]["files"])

    def test_workflow_has_weather_step(self):
        wf = (REPO / ".github" / "workflows" / "fetch-wm-data.yml").read_text(encoding="utf-8")
        self.assertIn("fetch_wm_weather.py", wf)

    def test_generate_picks_loads_weather(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("wm_weather.json", src)
        self.assertIn("weather_data", src)
        self.assertIn('fx["weather"]', src,
                      "Wetter muss in fixture.weather gepiped werden für Renderer-Pille")

    def test_sig_ctx_has_weather_keys(self):
        src = (REPO / "generate_wm_picks.py").read_text(encoding="utf-8")
        # Search context-block
        idx = src.find("sig_ctx = {")
        end = src.find("for p in new_picks:", idx)
        block = src[idx:end]
        for key in ['"weather"', '"venue"', '"kickoff_time"']:
            self.assertIn(key, block, f"sig_ctx fehlt {key}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
