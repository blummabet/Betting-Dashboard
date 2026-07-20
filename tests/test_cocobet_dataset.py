#!/usr/bin/env python3
"""test_cocobet_dataset.py — Single-Source-Dataset-Auflösung (26.06.2026 Konsolidierung)."""
import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


def _reload(dataset=None, profile=None, season=None):
    for k, v in (("COCOBET_DATASET", dataset), ("COCOBET_PROFILE", profile), ("LIGA_SEASON", season)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import cocobet_dataset as D
    return importlib.reload(D)


class TestDataset(unittest.TestCase):
    def tearDown(self):
        _reload(None, None, None)   # Env sauber zurücksetzen

    def test_wm_default(self):
        D = _reload(None)
        self.assertFalse(D.is_liga())
        self.assertEqual(D.active_dataset(), "wm")
        self.assertEqual(D.data_file().name, "wm2026-data.json")
        self.assertEqual(D.prefix(), "")
        self.assertEqual(D.active_profile(), "wm2026")

    def test_liga(self):
        D = _reload("liga")
        self.assertTrue(D.is_liga())
        self.assertEqual(D.data_file().name, "liga-data.json")
        self.assertEqual(D.prefix(), "liga_")
        self.assertEqual(D.active_profile(), "liga_default")
        self.assertEqual(D.file("signal_weights.json", "liga_signal_weights.json").name,
                         "liga_signal_weights.json")

    def test_leagues_single_source(self):
        D = _reload("liga")
        self.assertEqual(D.leagues(), {"ENG": 39, "ESP": 140, "GER": 78, "ITA": 135, "FRA": 61})

    def test_mls_dataset(self):
        # 29.06.2026 (Lucas): MLS als 3. Datensatz. Name aus liga-Schema abgeleitet (liga→mls).
        D = _reload("mls")
        self.assertTrue(D.is_liga())                       # non-WM → Klub-Pfade greifen
        self.assertEqual(D.active_dataset(), "mls")
        self.assertEqual(D.data_file().name, "mls-data.json")
        self.assertEqual(D.prefix(), "mls_")
        self.assertEqual(D.active_profile(), "mls_default")
        self.assertEqual(D.leagues(), {"MLS": 253})
        self.assertEqual(D.file("wm_streaks.json", "liga_streaks.json").name, "mls_streaks.json")

    def test_mls_profile_env_override(self):
        D = _reload("mls", "custom_profile")
        self.assertEqual(D.active_profile(), "custom_profile")

    def test_current_season(self):
        D = _reload(None)
        self.assertEqual(D.current_season(datetime(2026, 7, 1, tzinfo=timezone.utc)), 2026)
        self.assertEqual(D.current_season(datetime(2026, 3, 1, tzinfo=timezone.utc)), 2025)

    def test_season_env_override(self):
        D = _reload("liga", None, "2024")
        self.assertEqual(D.season(), 2024)


class TestTournamentOver(unittest.TestCase):
    """20.07.2026 WM-Winterisierung — beendetes Turnier von laufendem unterscheiden, damit die
    Konsumenten (Odds-Fetcher, Status-Guards) nicht ewig alarmieren, wenn TheOddsAPI die WM dropt."""

    def setUp(self):
        self.D = _reload(None)
        self.NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    def _fx(self, ko, status):
        return {"kickoff": ko, "result": {"status": status}}

    def test_alle_aufgeloest_und_vergangen_ist_vorbei(self):
        data = {"groups": {"A": {"fixtures": [
            self._fx("2026-06-11T18:00:00Z", "FT"), self._fx("2026-07-19T18:00:00Z", "FT")]}},
            "koFixtures": [self._fx("2026-07-15T18:00:00Z", "AET")]}
        self.assertTrue(self.D.tournament_is_over(data, now=self.NOW))

    def test_ein_offenes_spiel_ist_nicht_vorbei(self):
        data = {"groups": {"A": {"fixtures": [
            self._fx("2026-07-19T18:00:00Z", "FT"),
            self._fx("2026-07-22T18:00:00Z", None)]}}}   # noch nicht gespielt
        self.assertFalse(self.D.tournament_is_over(data, now=self.NOW))

    def test_ko_in_kofixtures_wird_mitgezaehlt(self):
        # KO liegt NICHT in groups (Memory 'KO-Datenpfad') — ein offenes KO-Spiel = nicht vorbei.
        data = {"groups": {"A": {"fixtures": [self._fx("2026-07-01T18:00:00Z", "FT")]}},
                "koFixtures": [self._fx("2026-07-25T18:00:00Z", None)]}
        self.assertFalse(self.D.tournament_is_over(data, now=self.NOW))

    def test_alle_aufgeloest_aber_zukunft_ist_nicht_vorbei(self):
        # theoretisch: alle 'FT', aber spätester Anpfiff in der Zukunft → Schutz gegen False-Positive.
        data = {"groups": {"A": {"fixtures": [self._fx("2026-07-25T18:00:00Z", "FT")]}}}
        self.assertFalse(self.D.tournament_is_over(data, now=self.NOW))

    def test_leerer_datensatz_ist_nicht_vorbei(self):
        self.assertFalse(self.D.tournament_is_over({}, now=self.NOW))
        self.assertFalse(self.D.tournament_is_over({"groups": {}}, now=self.NOW))

    def test_laufende_liga_ist_nie_vorbei(self):
        # Universell: eine Liga mit kommenden Spielen → immer False (nur beendetes Turnier True).
        data = {"groups": {"ENG": {"fixtures": [
            self._fx("2026-07-18T18:00:00Z", "FT"),
            self._fx("2026-07-27T18:00:00Z", None)]}}}
        self.assertFalse(self.D.tournament_is_over(data, now=self.NOW))

    def test_nur_datum_ohne_zeit(self):
        data = {"groups": {"A": {"fixtures": [{"date": "2026-07-19", "result": {"status": "FT"}}]}}}
        self.assertTrue(self.D.tournament_is_over(data, now=self.NOW))


if __name__ == "__main__":
    unittest.main()
