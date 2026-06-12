"""
tests/test_lineup_alerts.py — Tests für Telegram-Alert in fetch_wm_lineups.py

Coverage:
  - _classify_scorer: missing / benched / starting / unknown
  - Min-Goals-Schwelle (Spieler mit zu wenig Toren wird ignoriert)
  - _emit_lineup_alerts: Sendet beide Teams wenn betroffen, respektiert Dedup
  - Dedup: gleicher (match+team+status) wird nicht doppelt gesendet
  - SKIP_TELEGRAM Schutz im Test (kein realer Send)
  - Workflow-Datei wm-lineup-watcher.yml existiert + ruft fetch_wm_lineups auf
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("SKIP_TELEGRAM", "true")


class TestClassifyScorer(unittest.TestCase):
    def setUp(self):
        for m in list(sys.modules):
            if m.startswith("fetch_wm_lineups"):
                del sys.modules[m]
        import fetch_wm_lineups
        self.mod = fetch_wm_lineups
        self.mod.CFG = {**self.mod.DEFAULT_CFG}

    def test_starting_when_in_starting_xi(self):
        team_lineup = {"starting": [{"name": "Raúl Jiménez"}], "subs": []}
        scorer = {"name": "R. Jiménez", "goals": 7}
        self.assertEqual(self.mod._classify_scorer(scorer, team_lineup), "starting")

    def test_benched_when_in_subs(self):
        team_lineup = {"starting": [{"name": "Other"}], "subs": [{"name": "Raúl Jiménez"}]}
        scorer = {"name": "R. Jiménez", "goals": 7}
        self.assertEqual(self.mod._classify_scorer(scorer, team_lineup), "benched")

    def test_missing_when_in_neither(self):
        team_lineup = {"starting": [{"name": "Other"}], "subs": [{"name": "AnotherOne"}]}
        scorer = {"name": "R. Jiménez", "goals": 7}
        self.assertEqual(self.mod._classify_scorer(scorer, team_lineup), "missing")

    def test_unknown_when_below_min_goals(self):
        team_lineup = {"starting": [{"name": "Other"}], "subs": []}
        scorer = {"name": "Backup", "goals": 1}    # < min_goals=2
        self.assertEqual(self.mod._classify_scorer(scorer, team_lineup), "unknown")

    def test_unknown_when_scorer_empty(self):
        self.assertEqual(self.mod._classify_scorer({}, {"starting": [], "subs": []}),
                         "unknown")
        self.assertEqual(self.mod._classify_scorer(None, {"starting": [], "subs": []}),
                         "unknown")


class TestEmitAlerts(unittest.TestCase):
    def setUp(self):
        for m in list(sys.modules):
            if m.startswith("fetch_wm_lineups"):
                del sys.modules[m]
        import fetch_wm_lineups
        self.mod = fetch_wm_lineups
        self.mod.CFG = {**self.mod.DEFAULT_CFG}
        self.mod.SKIP_TELEGRAM = True  # keine reale Telegram-API

    def _entry(self, home_starting=None, home_subs=None,
               away_starting=None, away_subs=None, kickoff=None):
        # Kickoff standardmäßig in der ZUKUNFT (T+1h) — Lineup-Alerts sind pre-match;
        # ab Anpfiff unterdrückt der ko-Guard (FIX 12.06.2026). Fixes Datum würde
        # mit fortschreitender realer Zeit fälschlich "post-kickoff" werden.
        ko = kickoff or (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        return {
            "fixture_id": 99,
            "kickoff": ko,
            "home": {"starting": home_starting or [], "subs": home_subs or []},
            "away": {"starting": away_starting or [], "subs": away_subs or []},
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
        }

    def _meta(self):
        return {"home_id": "MEX", "away_id": "ZAF",
                "home_name": "Mexico", "away_name": "South Africa"}

    def test_no_alerts_when_all_starting(self):
        entry = self._entry(home_starting=[{"name": "Raúl Jiménez"}],
                            away_starting=[{"name": "Percy Tau"}])
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        dedup = {}
        sent = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads, self._meta(), dedup)
        self.assertEqual(sent, 0)

    def test_no_alert_after_kickoff(self):
        # FIX 12.06.2026: nach Anpfiff KEIN Lineup-Alert (war: bis 24h danach).
        past_ko = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        entry = self._entry(home_starting=[{"name": "Other"}],
                            away_starting=[{"name": "Percy Tau"}],
                            kickoff=past_ko)
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        sent = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads, self._meta(), {})
        self.assertEqual(sent, 0)

    def test_alert_when_home_missing(self):
        entry = self._entry(home_starting=[{"name": "Other"}],
                            away_starting=[{"name": "Percy Tau"}])
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        dedup = {}
        with patch.object(self.mod, "_send_telegram", return_value=True) as ts:
            sent = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads,
                                                self._meta(), dedup)
        self.assertEqual(sent, 1)
        self.assertEqual(ts.call_count, 1)
        msg = ts.call_args[0][0]
        self.assertIn("R. Jiménez", msg)
        self.assertIn("FEHLT", msg)

    def test_alert_when_both_teams_affected(self):
        entry = self._entry(home_starting=[{"name": "Other1"}],
                            away_starting=[{"name": "Other2"}],
                            away_subs=[{"name": "Percy Tau"}])  # Tau auf Bench
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        dedup = {}
        with patch.object(self.mod, "_send_telegram", return_value=True):
            sent = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads,
                                                self._meta(), dedup)
        self.assertEqual(sent, 2)  # Heim missing + Auswärts benched

    def test_dedup_prevents_double_send(self):
        entry = self._entry(home_starting=[{"name": "Other"}],
                            away_starting=[{"name": "Percy Tau"}])
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        dedup = {}
        with patch.object(self.mod, "_send_telegram", return_value=True):
            sent1 = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads,
                                                 self._meta(), dedup)
            sent2 = self.mod._emit_lineup_alerts("MEX-ZAF", entry, squads,
                                                 self._meta(), dedup)
        self.assertEqual(sent1, 1)
        self.assertEqual(sent2, 0)   # gleicher Alert nicht erneut

    def test_status_flip_triggers_new_alert(self):
        """Wenn Spieler von missing → benched wechselt (Spät-Sub eingewechselt
        bevor Anpfiff, theoretischer Edge-Case): zweiter Alert erlaubt."""
        squads = {"MEX": {"name": "R. Jiménez", "goals": 7},
                  "ZAF": {"name": "P. Tau", "goals": 5}}
        dedup = {}
        entry_missing = self._entry(home_starting=[{"name": "Other"}],
                                    away_starting=[{"name": "Percy Tau"}])
        entry_benched = self._entry(home_starting=[{"name": "Other"}],
                                    home_subs=[{"name": "Raúl Jiménez"}],
                                    away_starting=[{"name": "Percy Tau"}])
        with patch.object(self.mod, "_send_telegram", return_value=True):
            s1 = self.mod._emit_lineup_alerts("MEX-ZAF", entry_missing, squads,
                                              self._meta(), dedup)
            s2 = self.mod._emit_lineup_alerts("MEX-ZAF", entry_benched, squads,
                                              self._meta(), dedup)
        self.assertEqual(s1, 1)
        self.assertEqual(s2, 1)   # Status-Flip → neuer Alert


class TestSkipTelegramGuard(unittest.TestCase):
    """SKIP_TELEGRAM und fehlende ENV-Variablen blockieren Send."""

    def setUp(self):
        for m in list(sys.modules):
            if m.startswith("fetch_wm_lineups"):
                del sys.modules[m]
        import fetch_wm_lineups
        self.mod = fetch_wm_lineups

    def test_skip_telegram_returns_false(self):
        self.mod.SKIP_TELEGRAM = True
        self.assertFalse(self.mod._send_telegram("test"))

    def test_missing_token_returns_false(self):
        self.mod.SKIP_TELEGRAM = False
        self.mod.TELEGRAM_TOKEN = ""
        self.mod.TELEGRAM_TRADES_CHAT_ID = "x"
        self.assertFalse(self.mod._send_telegram("test"))

    def test_missing_chat_returns_false(self):
        self.mod.SKIP_TELEGRAM = False
        self.mod.TELEGRAM_TOKEN = "x"
        self.mod.TELEGRAM_TRADES_CHAT_ID = ""
        self.assertFalse(self.mod._send_telegram("test"))


class TestStateRegistry(unittest.TestCase):
    def test_alert_dedup_registered(self):
        reg = json.loads((REPO / "state_files_registry.json").read_text(encoding="utf-8"))
        files = reg["categories"]["fetch_wm_data"]["files"]
        self.assertIn("wm_lineup_alerts.json", files)


class TestWatcherWorkflowExists(unittest.TestCase):
    """Sanity: wm-lineup-watcher.yml existiert + ruft fetch_wm_lineups auf."""

    def test_workflow_file_exists(self):
        wf = REPO / ".github" / "workflows" / "wm-lineup-watcher.yml"
        self.assertTrue(wf.exists())

    def test_workflow_runs_lineup_fetcher(self):
        wf = REPO / ".github" / "workflows" / "wm-lineup-watcher.yml"
        src = wf.read_text(encoding="utf-8")
        self.assertIn("fetch_wm_lineups.py", src)
        self.assertIn("TELEGRAM_TRADES_CHAT_ID", src)
        # Public-Channel-Schutz: niemals TELEGRAM_CHAT_ID
        self.assertNotIn("TELEGRAM_CHAT_ID:", src.replace("TELEGRAM_TRADES_CHAT_ID:", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
