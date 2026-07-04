#!/usr/bin/env python3
"""test_notify_new_picks.py — Intraday-„Neuer Pick"-Noti (03.07.2026, Lucas).

Friert die Anti-Doppel-Send-Logik ein: der Digest ist Erst-Ankündiger, die Noti meldet nur
Nachzügler. Kein Send vor dem heutigen Digest; nur echte Deltas danach ([[pick_announce_state]])."""
import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _wm():
    return {
        "groups": {
            "A": {
                "teams": [
                    {"id": "MEX", "name": "Mexiko", "flag": "🇲🇽"},
                    {"id": "ZAF", "name": "Südafrika", "flag": "🇿🇦"},
                ],
                "fixtures": [
                    {"home": "MEX", "away": "ZAF", "matchday": 1,
                     "kickoff": "2099-01-01T20:00:00Z"},
                ],
            }
        },
        "koFixtures": [],
        "picks": {
            "A-1-MEX-ZAF": [
                {"verdict": "BET", "market": "Heimsieg", "convictionScore": 8},
                {"verdict": "NOBET", "market": "Über 2.5 Tore"},         # nie ankündigen
                {"verdict": "ABWÄGEN", "market": "Beide Teams treffen — Ja",
                 "trackingExcluded": True},                              # excluded → nie
            ]
        },
    }


class TestIterPickUnits(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state as S
        importlib.reload(S)
        self.S = S

    def test_nur_bet_und_abwaegen_ohne_excluded(self):
        units = list(self.S.iter_pick_units(_wm()))
        markets = {u["market"] for u in units}
        self.assertEqual(markets, {"Heimsieg"})   # NOBET + trackingExcluded raus

    def test_finished_spiel_raus(self):
        wm = _wm()
        wm["groups"]["A"]["fixtures"][0]["result"] = {"status": "FT"}
        self.assertEqual(list(self.S.iter_pick_units(wm)), [])


class TestNotifyFlow(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        os.environ["SKIP_TELEGRAM"] = "true"
        for m in ("cocobet_dataset", "pick_announce_state", "notify_new_picks"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import cocobet_dataset  # noqa
        importlib.reload(sys.modules["cocobet_dataset"])
        import pick_announce_state as S
        import notify_new_picks as N
        importlib.reload(S); importlib.reload(N)
        self.S, self.N = S, N
        # isolierte State-Datei + WM-Datei
        self._state = Path("/tmp/_test_announce_state.json")
        self._wmfile = Path("/tmp/_test_wm.json")
        if self._state.exists():
            self._state.unlink()
        S.STATE_FILE = self._state
        N.WM_FILE = self._wmfile
        self._write(_wm())

    def tearDown(self):
        for p in (self._state, self._wmfile):
            if p.exists():
                p.unlink()

    def _write(self, wm):
        import json
        self._wmfile.write_text(json.dumps(wm), encoding="utf-8")

    def test_vor_digest_kein_send_nur_basis(self):
        self.N.main()
        st = self.S.load()
        # Basis gesetzt, aber lastDigestDate bleibt None → es wurde nicht als „gesendet" gewertet
        self.assertEqual(len(st["announced"]), 1)
        self.assertIsNone(st["lastDigestDate"])

    def test_nach_digest_nachzuegler_wird_erkannt(self):
        import json
        # Digest simulieren: Slate markieren + lastDigestDate=heute
        st = self.S.load()
        self.S.mark(st, self.S.current_pick_ids(json.loads(self._wmfile.read_text())))
        st["lastDigestDate"] = datetime.now(timezone.utc).date().isoformat()
        self.S.save(st)
        # nichts Neues
        self.N.main()
        # Nachzügler einschleusen
        wm = _wm()
        wm["picks"]["A-1-MEX-ZAF"].append(
            {"verdict": "BET", "market": "Über 3.5 Tore", "convictionScore": 8})
        self._write(wm)
        self.N.main()
        st = self.S.load()
        self.assertIn("A-1-MEX-ZAF|Über 3.5 Tore", st["announced"])

    def test_message_ist_tiktok_safe(self):
        units = list(self.S.iter_pick_units(_wm()))
        msg = self.N.build_message(units)
        self.assertIn("Neuer Pick", msg)
        self.assertIn("Mexiko", msg)
        self.assertNotIn("€", msg)
        self.assertNotIn("@", msg)   # keine Quoten-Notation


if __name__ == "__main__":
    unittest.main()
