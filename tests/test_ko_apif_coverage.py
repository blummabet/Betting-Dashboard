#!/usr/bin/env python3
"""test_ko_apif_coverage.py — check_ko_apif_coverage (06.07.2026, Lucas: „nicht wieder KO-Bugs
einzeln finden"). Safety-Net gegen die KO-Datenpfad-Bug-Klasse: anstehendes KO-Spiel ohne
apif-Prognose wird geflaggt; mit Prognose grün; weit entfernte KO-Spiele werden NICHT geflaggt."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402


def _ctx(ko):
    wm = {"_meta": {"profile": "wm2026"}, "groups": {}, "odds": {}, "koFixtures": ko}
    return W.IntegrityCtx(wm, {}, {}, {})


def _in(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _ko(kickoff):
    return [{"round": "QF", "home": "FRA", "away": "MAR", "bothResolved": True,
             "result": None, "kickoff": kickoff}]


class TestKoApifCoverage(unittest.TestCase):
    def _run(self, ko, apif):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "wm_apif_predictions.json").write_text(json.dumps(apif), encoding="utf-8")
            with patch.object(W, "_BASE", Path(d)):
                return W.check_ko_apif_coverage(_ctx(ko))

    def test_flags_missing_upcoming(self):
        res = self._run(_ko(_in(10)), {})   # apif leer, Spiel in 10h
        self.assertFalse(res["ok"])
        self.assertIn("FRA-MAR", res["failures"][0])

    def test_ok_when_present(self):
        res = self._run(_ko(_in(10)), {"FRA-MAR": {"advice": "x"}})
        self.assertTrue(res["ok"])

    def test_skip_far_future(self):
        res = self._run(_ko(_in(24 * 10)), {})   # 10 Tage weg → apif holt es erst später → kein Flag
        self.assertTrue(res["ok"])

    def test_skip_finished(self):
        ko = _ko(_in(-5)); ko[0]["result"] = {"status": "FT"}
        res = self._run(ko, {})
        self.assertTrue(res["ok"])


if __name__ == "__main__":
    unittest.main()
