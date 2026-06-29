#!/usr/bin/env python3
"""Tests für generate_wm_picks.py — Konstanten + Imports + Smoketest."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestModuleImports(unittest.TestCase):
    """Sicherstellen dass das Modul mit allen Imports lädt."""

    def test_module_loads_without_error(self):
        import generate_wm_picks
        self.assertTrue(hasattr(generate_wm_picks, "EDGE_BET_1X2"))

    def test_no_inline_direction_map(self):
        """Keine Inline-Richtungs-Map — Richtungs-/Inkompatibilitäts-Logik gehört in die geteilten
        Helfer (pick_helpers / sharp_signals.base.market_side). (26.06.2026: der pick_constants-
        Import lag NUR im entfernten toten Elo-Pfad; Anti-Inline-Regression bleibt.)"""
        src = (Path(__file__).parent.parent / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertNotIn("DIRECTION_MAP = {", src,
            "Inline DIRECTION_MAP darf nicht existieren — geteilte Helfer verwenden")

    def test_uses_cocobet_config(self):
        """Magic Numbers müssen aus Config kommen."""
        src = (Path(__file__).parent.parent / "generate_wm_picks.py").read_text(encoding="utf-8")
        self.assertIn("from cocobet_config import", src,
            "generate_wm_picks muss cocobet_config importieren")


class TestEdgeConstantsValues(unittest.TestCase):
    """Konstanten-Werte müssen mit dem WM-Profile übereinstimmen."""

    @classmethod
    def setUpClass(cls):
        import generate_wm_picks
        cls.g = generate_wm_picks

    def test_edge_thresholds_match_wm_profile(self):
        # Aus cocobet_config.json profiles.wm2026.edge
        self.assertEqual(self.g.EDGE_MIN_1X2, 5)
        self.assertEqual(self.g.EDGE_BET_1X2, 8)
        self.assertEqual(self.g.EDGE_BET_OU, 6)
        self.assertEqual(self.g.EDGE_OU_BET_MAX, 10)
        self.assertEqual(self.g.EDGE_AH_BET_MAX, 12)
        self.assertEqual(self.g.EDGE_MAX_SANE, 18)

    def test_odds_caps_match_wm_profile(self):
        self.assertEqual(self.g.ODDS_BET_MAX, 4.5)
        self.assertEqual(self.g.ODDS_BET_MAX_OU, 3.0)
        self.assertEqual(self.g.ODDS_BET_MAX_DNB, 4.0)
        self.assertEqual(self.g.ODDS_MAX, 6.5)

    def test_underdog_thresholds_match_wm_profile(self):
        self.assertEqual(self.g.UNDERDOG_ELO_SOFT, 100)
        self.assertEqual(self.g.UNDERDOG_ELO_HARD, 200)

    def test_natural_constants_unchanged(self):
        """INTL_AVG_GOALS und DRAW_BASE bleiben hartkodiert (Naturkonstanten)."""
        self.assertEqual(self.g.INTL_AVG_GOALS, 1.25)
        self.assertEqual(self.g.DRAW_BASE, 0.24)
        self.assertEqual(self.g.HOME_BONUS_PP, 0.03)


class TestProfileSwitching(unittest.TestCase):
    """Profile-Wechsel muss Konstanten anpassen."""

    def setUp(self):
        import os
        self._original_env = os.environ.get("COCOBET_PROFILE")
        os.environ["COCOBET_PROFILE"] = "liga_default"
        # Force re-load der Module
        import cocobet_config
        cocobet_config.reload_config()
        # generate_wm_picks neu laden mit Liga-Profile
        import importlib, generate_wm_picks
        importlib.reload(generate_wm_picks)
        self.g = generate_wm_picks

    def tearDown(self):
        import os
        if self._original_env is None:
            os.environ.pop("COCOBET_PROFILE", None)
        else:
            os.environ["COCOBET_PROFILE"] = self._original_env
        import cocobet_config, importlib, generate_wm_picks
        cocobet_config.reload_config()
        importlib.reload(generate_wm_picks)

    def test_liga_profile_has_different_threshold(self):
        # Liga: bet_threshold_1x2 = 6 (statt WM 8)
        self.assertEqual(self.g.EDGE_BET_1X2, 6,
            "Profile-Switch zu liga_default muss EDGE_BET_1X2 auf 6 setzen")


class TestRegressionPicksUnchanged(unittest.TestCase):
    """Goldstandard-Test: regenerierte Picks identisch mit Pre-Refactor-Snapshot.

    Falls dieser Test fehlschlägt → mein Refactor hat sich auf den Output ausgewirkt.
    Snapshot liegt in tests/snapshots/picks_pre_refactor.json.
    """

    def test_picks_match_snapshot(self):
        # OBSOLET seit 14.06.2026: der Pick-Motor wurde komplett auf Steam-Following
        # (Pinnacle-Move-Trigger) umgestellt — der Pre-Refactor-Snapshot (Poisson/Elo-
        # Edge) ist kein gültiges Goldbild mehr. Regressionsabdeckung läuft jetzt über
        # tests/test_steam_engine.py + die Integritäts-Batterie. Exakt-Match gegen
        # Live-Odds war ohnehin driftanfällig.
        self.skipTest("Pick-Motor auf Steam-Following umgestellt (14.06.2026) — "
                      "Pre-Refactor-Snapshot obsolet; Abdeckung via test_steam_engine + Guards")
        import json
        snap_path = Path(__file__).parent / "snapshots" / "picks_pre_refactor.json"
        data_path = Path(__file__).parent.parent / "wm2026-data.json"
        if not snap_path.exists():
            self.skipTest(f"Snapshot fehlt: {snap_path}")
        if not data_path.exists():
            self.skipTest("wm2026-data.json fehlt — Smoketest nicht möglich")

        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        with open(data_path, encoding="utf-8") as f:
            d = json.load(f)

        keys = ['market', 'verdict', 'edgePP', 'odds', 'modelOdds', 'conf',
                'saferAltFor', 'downgradedReason', 'trackingExcluded',
                'dataQuality', 'edgeMin', 'storyVerdict']

        actual = {}
        for pk in sorted(d.get("picks", {}).keys()):
            plist = d["picks"][pk]
            if not isinstance(plist, list): continue
            actual[pk] = [{k: p.get(k) for k in keys} for p in plist]

        diffs = []
        for mk in sorted(set(snap) | set(actual)):
            if snap.get(mk) != actual.get(mk):
                diffs.append(mk)

        self.assertEqual(len(diffs), 0,
            f"Regression: {len(diffs)} Matches anders als Snapshot: {diffs[:5]}")


class TestFixturePickState(unittest.TestCase):
    """fixture_pick_state(): Freeze/Refresh/Rebuild-Entscheidung (Fix 15.06.2026).

    Kernpunkt: NUR die Anpfiff-Zeit gegen den Cutover entscheidet, ob ein heutiges
    Spiel veröffentlicht (refresh) oder frei (rebuild) ist — kein `fx_date == today`.
    """

    @classmethod
    def setUpClass(cls):
        from datetime import datetime, timezone
        import generate_wm_picks as g
        cls.g = g
        cls.dt = datetime
        cls.tz = timezone
        # "Jetzt" = 15.06.2026 12:00Z, Cutover = 15.06.2026 00:00Z, today = 15.06.
        cls.now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        cls.cutover = datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)
        cls.today = "2026-06-15"

    def _state(self, date, kickoff, has_pick):
        return self.g.fixture_pick_state(
            {"date": date, "kickoff": kickoff}, has_pick,
            self.today, self.now, self.cutover,
        )

    def test_past_fixture_untouched(self):
        self.assertEqual(self._state("2026-06-14", "2026-06-14T20:00:00Z", True), "past")

    def test_kicked_off_today_is_frozen(self):
        # Anpfiff 10:00Z < now 12:00Z → läuft/vorbei
        self.assertEqual(self._state("2026-06-15", "2026-06-15T10:00:00Z", True), "kickoff_passed")

    def test_today_published_pre_cutover_with_pick_refreshes(self):
        # Anpfiff genau am Cutover (≤), noch nicht angepfiffen wäre nötig — hier vor now
        # liegt es aber: published + kickoff_passed → kickoff_passed gewinnt (Reihenfolge).
        # Reiner Refresh-Fall: kickoff ≤ cutover ABER > now ist unmöglich (cutover ≤ now),
        # daher Refresh greift praktisch nur solange now ≤ cutover. Test über frühes now:
        early_now = self.dt(2026, 6, 14, 23, 0, tzinfo=self.tz.utc)
        state = self.g.fixture_pick_state(
            {"date": "2026-06-15", "kickoff": "2026-06-14T23:30:00Z"},
            True, "2026-06-14", early_now, self.cutover,
        )
        self.assertEqual(state, "refresh")

    def test_today_post_cutover_rebuilds_even_with_pick(self):
        # 28.06.2026 (Lucas, ersetzt die 15.06-Regel): heutiges Spiel + Pick existiert → 'refresh'
        # (Markt-Lock). Ein (quasi) gepostete Pick darf pre-match NICHT mehr das Marktziel wechseln
        # (KO ZAF-CAN kippte Auswärtssieg→Unter spät pre-match → unehrlicher Track-Record).
        # fx_date<=tomorrow = Immutability-Fenster. (Vorher absichtlich 'rebuild' = Ursache des Bugs.)
        self.assertEqual(self._state("2026-06-15", "2026-06-15T19:00:00Z", True), "refresh")

    def test_future_fixture_rebuilds(self):
        self.assertEqual(self._state("2026-06-16", "2026-06-16T18:00:00Z", False), "rebuild")

    def test_missing_kickoff_today_with_pick_locked(self):
        # 28.06.2026: heute + Pick existiert → Posted-Fenster greift (refresh), auch ohne kickoff.
        # (Ohne Pick bliebe es 'rebuild' — s. test_post_cutover_without_pick_rebuilds.)
        self.assertEqual(self._state("2026-06-15", None, True), "refresh")

    def test_missing_kickoff_future_without_pick_rebuilds(self):
        # Künftiges Spiel ohne Pick + ohne kickoff → rebuild (nicht versehentlich freezen)
        self.assertEqual(self._state("2026-06-20", None, False), "rebuild")

    def test_post_cutover_without_pick_rebuilds(self):
        self.assertEqual(self._state("2026-06-15", "2026-06-15T19:00:00Z", False), "rebuild")


if __name__ == "__main__":
    unittest.main()
