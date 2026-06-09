"""
tests/test_incentive_signal.py — Tests für incentive_signal

Coverage:
  - Komponente A: Qualifikations-Math
    · must_win / can_draw / qualified / eliminated korrekt klassifiziert
    · Dead-Rubber-Detection feuert
    · Stake-Asymmetrie zwischen Teams
    · MD1/Pre-Tournament gibt None
  - Komponente B: Bracket-Asymmetrie
    · Tank-Anreiz (Sieg-Pfad gegen Stärkeren)
    · Top-Anreiz (Sieg-Pfad gegen Schwächeren)
    · Threshold (kleine Elo-Δ kein Signal)
  - Komponente C: Venue-Distanz
    · Reise-Burden Discount
    · Höhen-Penalty (Mexico City)
  - Komponente D: Rotation-Risk
    · K.O.-Phase, kurze Pause + Favorit
    · Über-Markt + Rotation
  - Profile-Switch wm2026 vs liga_default
  - Anti-Korr-Familie "incentive" in registry
  - Bracket/Venues-JSON Schema-Sanity
"""
import json
import os
import sys
import unittest
import importlib
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

# Frischer Import — damit COCOBET_PROFILE-Switches in setUp greifen
os.environ.pop("COCOBET_PROFILE", None)
from sharp_signals import incentive_signal as _is_mod
importlib.reload(_is_mod)
from sharp_signals.incentive_signal import (
    IncentiveSignal, _compute_qualification_state,
    _project_final_position, _project_r32_opponent_elo, _project_r32_venue_id,
    _haversine_km, _load_bracket, _load_venues,
)


def _md3_standings_asymmetric() -> dict:
    """Gruppe A nach MD2: A=6,D=4,C=1,B=0. Asymmetrische Anreize."""
    return {
        "A": [
            {"team": "TM_A", "points": 6, "played": 2, "gd": 3, "gf": 4},
            {"team": "TM_D", "points": 4, "played": 2, "gd": 1, "gf": 3},
            {"team": "TM_C", "points": 1, "played": 2, "gd": -1, "gf": 2},
            {"team": "TM_B", "points": 0, "played": 2, "gd": -3, "gf": 0},
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
#  Komponente A — Qualifikations-Math
# ──────────────────────────────────────────────────────────────────────────
class TestQualificationMath(unittest.TestCase):
    def test_qualified_team_strict(self):
        st = _md3_standings_asymmetric()
        s = _compute_qualification_state("TM_A", "A", 3, st)
        self.assertTrue(s["qualified"])
        self.assertFalse(s["must_win"])
        self.assertEqual(s["label"], "qualified")

    def test_can_draw_team(self):
        st = _md3_standings_asymmetric()
        s = _compute_qualification_state("TM_D", "A", 3, st)
        self.assertTrue(s["can_draw"])
        self.assertFalse(s["must_win"])

    def test_must_win_third_chase(self):
        # TM_C: 1pt, pos 3. Sieg → 4pts erreicht hopeful_tier=4 für Best-Third.
        st = _md3_standings_asymmetric()
        s = _compute_qualification_state("TM_C", "A", 3, st)
        self.assertTrue(s["must_win"])
        self.assertFalse(s["can_draw"])
        self.assertEqual(s["label"], "must_win")

    def test_eliminated_team(self):
        st = _md3_standings_asymmetric()
        s = _compute_qualification_state("TM_B", "A", 3, st)
        self.assertTrue(s["eliminated"])
        self.assertFalse(s["must_win"])

    def test_unknown_team_returns_unknown(self):
        st = _md3_standings_asymmetric()
        s = _compute_qualification_state("PHANTOM", "A", 3, st)
        self.assertEqual(s["label"], "unknown")

    def test_missing_group_returns_unknown(self):
        s = _compute_qualification_state("TM_A", "Z", 3, _md3_standings_asymmetric())
        self.assertEqual(s["label"], "unknown")


class TestComponentASignal(unittest.TestCase):
    def setUp(self):
        self.sig = IncentiveSignal()
        self.st  = _md3_standings_asymmetric()

    def test_md1_no_signal(self):
        ctx = {"home_id": "TM_A", "away_id": "TM_B", "group_id": "A",
               "matchday": 1, "standings": {}}
        self.assertIsNone(self.sig.evaluate({"market": "Heimsieg"}, ctx))

    def test_must_win_asymmetry_boosts_away_pick(self):
        # TM_B (eliminated) vs TM_C (must_win) → Auswärtssieg-Pick +pp
        ctx = {"home_id": "TM_B", "away_id": "TM_C", "group_id": "A",
               "matchday": 3, "standings": self.st}
        r = self.sig.evaluate({"market": "Auswärtssieg"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)

    def test_dead_rubber_under_positive(self):
        # TM_A (qualified) vs TM_D (can_draw) → Unter +pp
        ctx = {"home_id": "TM_A", "away_id": "TM_D", "group_id": "A",
               "matchday": 3, "standings": self.st}
        r = self.sig.evaluate({"market": "Unter 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertGreater(r.score, 0)
        self.assertIn("Dead Rubber", r.evidence)

    def test_dead_rubber_over_negative(self):
        ctx = {"home_id": "TM_A", "away_id": "TM_D", "group_id": "A",
               "matchday": 3, "standings": self.st}
        r = self.sig.evaluate({"market": "Über 2.5 Tore"}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)


# ──────────────────────────────────────────────────────────────────────────
#  Komponente B — Bracket-Asymmetrie
# ──────────────────────────────────────────────────────────────────────────
class TestBracketProjection(unittest.TestCase):
    """Bracket-Projektion Helpers (B-Basis)."""

    def test_project_final_pos_outcome_sensitive(self):
        # MEX 6pts vs CZE 3pts (GD-Lead bei CZE). Sieg → MEX=1; Niederlage → MEX=2.
        st = {"A": [
            {"team":"MEX","points":6,"played":2,"gd":0,"gf":4},
            {"team":"CZE","points":3,"played":2,"gd":5,"gf":6},
            {"team":"KOR","points":3,"played":2,"gd":-2,"gf":2},
            {"team":"ZAF","points":1,"played":2,"gd":-3,"gf":1},
        ]}
        self.assertEqual(_project_final_position("MEX","A",st,"MEX","CZE","W"), 1)
        self.assertEqual(_project_final_position("MEX","A",st,"MEX","CZE","L"), 2)

    def test_r32_venue_known_for_top_slots(self):
        br = _load_bracket()
        self.assertIsNotNone(br)
        # 1A → M79 in Mexico City
        self.assertEqual(_project_r32_venue_id(br, "A", 1), "mexico_city")
        # 2A → M73 in Los Angeles
        self.assertEqual(_project_r32_venue_id(br, "A", 2), "los_angeles")


class TestComponentBSignal(unittest.TestCase):
    def setUp(self):
        self.sig = IncentiveSignal()
        # Setup: MEX-CZE MD3, A=Gruppe, MEX bei Sieg 1A, Niederlage 2A
        self.st = {
            "A": [
                {"team":"MEX","points":6,"played":2,"gd":0,"gf":4},
                {"team":"CZE","points":3,"played":2,"gd":5,"gf":6},
                {"team":"KOR","points":3,"played":2,"gd":-2,"gf":2},
                {"team":"ZAF","points":1,"played":2,"gd":-3,"gf":1},
            ],
        }
        # Drittplazierte aus C/E/F/H/I — wir füllen relevante Pool-Gruppen
        for g in ("C","E","F","H","I"):
            self.st[g] = [
                {"team": f"{g}1"}, {"team": f"{g}2"}, {"team": f"{g}3"}, {"team": f"{g}4"}
            ]

    def test_tank_anreiz_strong_opponent_at_pos1(self):
        # 2B = schwach, best_third-Pool stark → bei Sieg trifft MEX auf Stärkeren
        st = {**self.st,
              "B": [{"team":"CAN","points":6,"played":2,"gd":3},
                    {"team":"BIH","points":4,"played":2,"gd":1},
                    {"team":"USA","points":3,"played":2,"gd":0},
                    {"team":"PRY","points":1,"played":2,"gd":-4}]}
        team_elo = {"MEX":1815,"CZE":1730,"BIH":1620,  # 2B schwach
                    "C3":1820,"E3":1810,"F3":1800,"H3":1790,"I3":1820}
        ctx = {"home_id":"MEX","away_id":"CZE","group_id":"A","matchday":3,
               "standings":st,"team_elo":team_elo}
        r = self.sig.evaluate({"market":"Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        cb = r.metadata["components"]["B"]
        self.assertGreater(cb["delta_elo"], 50)   # Sieg-Pfad gegen Stärkeren
        self.assertLess(r.score, 0)               # → Heimsieg-Pick gedrückt

    def test_top_anreiz_weak_opponent_at_pos1(self):
        # 2B = stark, best_third-Pool schwach → bei Sieg trifft MEX auf Schwächeren
        st = {**self.st,
              "B": [{"team":"CAN","points":6,"played":2,"gd":3},
                    {"team":"USA","points":4,"played":2,"gd":1},
                    {"team":"PRY","points":3,"played":2,"gd":0},
                    {"team":"BIH","points":1,"played":2,"gd":-4}]}
        team_elo = {"MEX":1815,"CZE":1730,"USA":1750,
                    "C3":1480,"E3":1490,"F3":1500,"H3":1520,"I3":1500}
        ctx = {"home_id":"MEX","away_id":"CZE","group_id":"A","matchday":3,
               "standings":st,"team_elo":team_elo}
        r = self.sig.evaluate({"market":"Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        cb = r.metadata["components"]["B"]
        self.assertLess(cb["delta_elo"], -50)
        self.assertGreater(r.score, 0)

    def test_no_bracket_diff_no_signal(self):
        # Gegner gleich stark bei beiden Pfaden
        st = {**self.st,
              "B": [{"team":"CAN","points":6,"played":2,"gd":3},
                    {"team":"USA","points":4,"played":2,"gd":1},
                    {"team":"PRY","points":3,"played":2,"gd":0},
                    {"team":"BIH","points":1,"played":2,"gd":-4}]}
        team_elo = {"MEX":1815,"CZE":1730,"USA":1730,
                    "C3":1730,"E3":1730,"F3":1730,"H3":1730,"I3":1730}
        ctx = {"home_id":"MEX","away_id":"CZE","group_id":"A","matchday":3,
               "standings":st,"team_elo":team_elo}
        r = self.sig.evaluate({"market":"Heimsieg"}, ctx)
        # Komponente A könnte noch feuern (TM_A ist qualified, TM_D can_draw etc.)
        # → wenn Signal kommt, Komp B-Score muss minimal sein
        if r:
            self.assertLessEqual(abs(r.metadata["components"]["B"].get("delta_elo", 0)), 50)


# ──────────────────────────────────────────────────────────────────────────
#  Komponente C — Venue-Distanz
# ──────────────────────────────────────────────────────────────────────────
class TestComponentCSignal(unittest.TestCase):
    def setUp(self):
        self.sig = IncentiveSignal()

    def test_haversine_known_distance(self):
        venues = _load_venues()
        # Mexico City → Vancouver ~4000km
        d = _haversine_km(venues["mexico_city"], venues["vancouver"])
        self.assertGreater(d, 3500)
        self.assertLess(d, 4500)

    def test_venue_close_at_win_boosts_pick(self):
        # MEX-CZE in Mexico City. Sieg → bleibt in MX (0km), Niederlage → LA (2500km).
        # → Sieg-Pfad NÄHER → Top-Anreiz → Heimsieg-Pick +pp
        st = {"A": [
            {"team":"MEX","points":6,"played":2,"gd":0,"gf":4},
            {"team":"CZE","points":3,"played":2,"gd":5,"gf":6},
            {"team":"KOR","points":3,"played":2,"gd":-2,"gf":2},
            {"team":"ZAF","points":1,"played":2,"gd":-3,"gf":1},
        ], "B": [{"team":"USA","points":4,"played":2,"gd":1},
                 {"team":"CAN","points":6,"played":2,"gd":3},
                 {"team":"PRY","points":3,"played":2},
                 {"team":"BIH","points":1,"played":2}]}
        for g in ("C","E","F","H","I"):
            st[g] = [{"team":f"{g}1"},{"team":f"{g}2"},{"team":f"{g}3"},{"team":f"{g}4"}]
        team_elo = {"MEX":1815,"CZE":1730,"USA":1750,
                    "C3":1700,"E3":1700,"F3":1700,"H3":1700,"I3":1700}
        ctx = {"home_id":"MEX","away_id":"CZE","group_id":"A","matchday":3,
               "standings":st,"team_elo":team_elo,
               "current_venue_id":"mexico_city"}
        r = self.sig.evaluate({"market":"Heimsieg"}, ctx)
        self.assertIsNotNone(r)
        cc = r.metadata["components"]["C"]
        self.assertEqual(cc["venue_W"], "mexico_city")
        self.assertEqual(cc["venue_L"], "los_angeles")
        self.assertLess(cc["delta_dist_km"], -1000)  # Sieg-Pfad >1000km näher

    def test_altitude_penalty_for_mexico_city_path(self):
        # Match in LA, MEX bei Sieg → Mexico City Höhe 2240m
        st = {"A": [
            {"team":"MEX","points":4,"played":2,"gd":2,"gf":3},
            {"team":"CZE","points":4,"played":2,"gd":1,"gf":3},
            {"team":"KOR","points":3,"played":2,"gd":0,"gf":2},
            {"team":"ZAF","points":1,"played":2,"gd":-3,"gf":1},
        ], "B": [{"team":"USA","points":4,"played":2,"gd":1},
                 {"team":"CAN","points":6,"played":2,"gd":3}]}
        for g in ("C","E","F","H","I"):
            st[g] = [{"team":f"{g}1"},{"team":f"{g}2"},{"team":f"{g}3"},{"team":f"{g}4"}]
        ctx = {"home_id":"MEX","away_id":"CZE","group_id":"A","matchday":3,
               "standings":st,"team_elo":{"MEX":1815,"CZE":1730,"USA":1750},
               "current_venue_id":"los_angeles"}
        r = self.sig.evaluate({"market":"Heimsieg"}, ctx)
        if r:
            cc = r.metadata["components"]["C"]
            self.assertGreaterEqual(cc["alt_W"], 1500)
            self.assertLess(cc["alt_L"], 1500)


# ──────────────────────────────────────────────────────────────────────────
#  Komponente D — Rotation-Risk
# ──────────────────────────────────────────────────────────────────────────
class TestComponentDSignal(unittest.TestCase):
    def setUp(self):
        self.sig = IncentiveSignal()

    def test_no_rotation_long_rest(self):
        ctx = {"home_id":"GER","away_id":"ENG","matchday":"R16",
               "current_match_date":"2026-07-04","next_match_date":"2026-07-09"}
        self.assertIsNone(self.sig.evaluate({"market":"Heimsieg","odds":1.40}, ctx))

    def test_rotation_favorite_short_rest(self):
        ctx = {"home_id":"GER","away_id":"ENG","matchday":"R16",
               "current_match_date":"2026-07-04","next_match_date":"2026-07-06"}
        r = self.sig.evaluate({"market":"Heimsieg","odds":1.40}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)

    def test_rotation_underdog_no_signal(self):
        # Auf Underdog (odds>1.65) ist Rotation nicht relevant
        ctx = {"home_id":"GER","away_id":"ENG","matchday":"R16",
               "current_match_date":"2026-07-04","next_match_date":"2026-07-06"}
        r = self.sig.evaluate({"market":"Heimsieg","odds":2.20}, ctx)
        self.assertIsNone(r)

    def test_rotation_over_market(self):
        ctx = {"home_id":"GER","away_id":"ENG","matchday":"R16",
               "current_match_date":"2026-07-04","next_match_date":"2026-07-06"}
        r = self.sig.evaluate({"market":"Über 2.5 Tore","odds":1.85}, ctx)
        self.assertIsNotNone(r)
        self.assertLess(r.score, 0)


# ──────────────────────────────────────────────────────────────────────────
#  Profile-Switch
# ──────────────────────────────────────────────────────────────────────────
class TestProfileSwitch(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COCOBET_PROFILE", None)
        # Modul neu laden für anderen Test isoliert
        importlib.reload(_is_mod)

    def test_wm2026_full_signal_pack(self):
        os.environ.pop("COCOBET_PROFILE", None)
        importlib.reload(_is_mod)
        sig = _is_mod.IncentiveSignal()
        self.assertEqual(sig._t["must_win_pp"], 2.0)
        self.assertGreater(sig._t["bracket_elo_max_pp"], 0)
        self.assertNotEqual(sig._t["rotation_pp"], 0)

    def test_liga_default_disables_bracket_and_rotation(self):
        os.environ["COCOBET_PROFILE"] = "liga_default"
        importlib.reload(_is_mod)
        sig = _is_mod.IncentiveSignal()
        self.assertEqual(sig._t["bracket_elo_max_pp"], 0.0)
        self.assertEqual(sig._t["venue_dist_max_pp"], 0.0)
        self.assertEqual(sig._t["rotation_pp"], 0.0)
        # Komponente A bleibt aktiv mit reduzierten Werten
        self.assertGreater(sig._t["must_win_pp"], 0)


# ──────────────────────────────────────────────────────────────────────────
#  Schema-Sanity: Bracket + Venues JSON
# ──────────────────────────────────────────────────────────────────────────
class TestSchemaSanity(unittest.TestCase):
    def test_bracket_has_all_phases(self):
        br = _load_bracket()
        self.assertIsNotNone(br)
        self.assertEqual(len(br["round_of_32"]), 16)
        self.assertEqual(len(br["round_of_16"]),  8)
        self.assertEqual(len(br["quarterfinals"]), 4)
        self.assertEqual(len(br["semifinals"]), 2)

    def test_bracket_venue_ids_in_venues(self):
        br = _load_bracket()
        vn = _load_venues()
        venue_ids = set(vn.keys())
        for stage in ("round_of_32","round_of_16","quarterfinals","semifinals"):
            for mk, m in br[stage].items():
                self.assertIn(m["venue_id"], venue_ids,
                              f"{stage}.{mk} venue_id '{m['venue_id']}' nicht in wm_venues.json")

    def test_bracket_winner_to_chain(self):
        br = _load_bracket()
        all_keys = set()
        for stage in ("round_of_32","round_of_16","quarterfinals","semifinals"):
            all_keys |= set(br[stage].keys())
        for stage in ("round_of_32","round_of_16","quarterfinals","semifinals"):
            for mk, m in br[stage].items():
                wt = m.get("winner_to")
                if wt and wt != "M104":   # M104 = Finale, ausserhalb
                    self.assertIn(wt, all_keys, f"{stage}.{mk} winner_to={wt} fehlt")


# ──────────────────────────────────────────────────────────────────────────
#  Registry-Integration
# ──────────────────────────────────────────────────────────────────────────
class TestRegistryIntegration(unittest.TestCase):
    def test_signal_in_active_signals(self):
        from sharp_signals.registry import ACTIVE_SIGNALS
        names = [s.name() for s in ACTIVE_SIGNALS]
        self.assertIn("incentive_signal", names)

    def test_signal_in_anti_correlation_family(self):
        from sharp_signals.registry import SIGNAL_GROUPS
        self.assertIn("incentive_signal", SIGNAL_GROUPS)
        # Eigene Familie "incentive" — orthogonal zu allen anderen
        self.assertEqual(SIGNAL_GROUPS["incentive_signal"], "incentive")


if __name__ == "__main__":
    unittest.main()
