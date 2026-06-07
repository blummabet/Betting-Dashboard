#!/usr/bin/env python3
"""
test_steam_lag_stale_bug.py — Regression-Test für Stale-Snapshot-Bug.

Bug 07.06.2026 (Wiederauftreten von Task #152):
  Wenn ein Match unter MIN_EDGE_PP (1.5pp) fällt, aber compute_signals() es
  noch zurückgibt mit gültigem bestEdgeKey:
    - signal_keys_market enthält (matchKey, bestEdgeKey)
    - Main-Loop skippt wegen `bestEdge < MIN_EDGE_PP and not steamLag`
    - Stale-Pass skippt fälschlich wegen "schon im Main aktualisiert"
    - Resultat: OPEN-Signal bleibt forever stale (Tage ohne Snapshot)

Fix: Tracke `snapshotted_in_main` set nur dann, wenn ein Snapshot wirklich
geschrieben wurde. Stale-Pass nutzt diesen Set statt der ungefilterten
signal_keys_market.

MEX-ZAF aw war konkret das Match das aufgefallen ist (07.06.2026,
letzter Snapshot 04.06., 64h stale).
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestStaleSignalGetsUpdate(unittest.TestCase):
    """OPEN-Signal mit Edge < MIN_EDGE_PP MUSS Stale-Snapshot kriegen."""

    @classmethod
    def setUpClass(cls):
        import steam_lag_monitor as mod
        cls.mod = mod

    def _make_fx(self, key="MEX-ZAF", best_edge=0.9, best_key="aw"):
        return {
            "key": key,
            "homeId": "MEX",
            "awayId": "ZAF",
            "homeName": "Mexiko",
            "awayName": "Südafrika",
            "matchDate": "2026-06-11",
            "bestEdge": best_edge,
            "bestEdgeKey": best_key,
            f"edge_{best_key}": best_edge,
            f"poly_{best_key}": 0.105,
            f"fair_{best_key}": 0.1137,
            "steamLag": False,
            "vol": 0,
            "pinnSteamMove": None,
            "edgeTrend": "stable",
        }

    def _existing_open(self, mod, key="MEX-ZAF", market="aw"):
        """Simuliere OPEN-Signal das vor 3 Tagen entry'd wurde mit edge=2.2."""
        return {
            "id": f"{key}_{market}_20260604",
            "matchKey": key,
            "market": market,
            "marketLabel": "Auswärtssieg",
            "homeId": "MEX", "awayId": "ZAF",
            "home": "Mexiko", "away": "Südafrika",
            "homeFlag": "🇲🇽", "awayFlag": "🇿🇦",
            "matchDate": "2026-06-11",
            "signalTs": "2026-06-04T16:01:00Z",
            "entryEdgePp": 2.2,
            "entryPolyPrice": 0.105,
            "entryPinnFair": 0.1137,
            "entryVol": 0,
            "steamLagAtSignal": False,
            "pinnMoveAtSignal": None,
            "edgeTrendAtSignal": "stable",
            "highConfidence": False,
            "entryTier": "track",
            "snapshots": [
                {"ts": "2026-06-04T16:01:00Z", "edgePp": 2.2,
                 "polyPrice": 0.105, "pinnFair": 0.1137, "steamLag": False}
            ],
            "currentEdgePp": 2.2,
            "currentPolyPrice": 0.105,
            "edgeVelocityPPH": 0.0,
            "convergencePct": 0.0,
            "convergenceTs": None,
            "convergenceHours": None,
            "status": "OPEN",
            "outcome": None,
        }

    def test_open_signal_below_min_edge_gets_stale_snapshot(self):
        """REGRESSION: Edge 0.9pp < MIN_EDGE_PP, fx existiert in signals mit
        bestEdgeKey='aw'. Vorher: NIE Update. Jetzt: Stale-Pass updated.

        Konkret das MEX-ZAF-aw Szenario vom 07.06.2026.
        """
        mod = self.mod
        # Existierender OPEN-Eintrag (Entry war bei 2.2pp, jetzt nur noch 0.9pp)
        log = {"signals": [self._existing_open(mod, key="MEX-ZAF", market="aw")]}

        # compute_signals() returnt fx weiterhin mit bestEdgeKey='aw' — Edge ist
        # zwar gesunken, aber compute_signals filtert nicht.
        signals = [self._make_fx(key="MEX-ZAF", best_edge=0.9, best_key="aw")]

        # Patch POLY_FILE: Stale-Pass liest allFixtures aus dieser Datei.
        import json, tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            poly_file = Path(td) / "poly.json"
            poly_file.write_text(json.dumps({
                "allFixtures": [
                    {"key": "MEX-ZAF", "edge_aw": 0.9,
                     "poly_aw": 0.105, "fair_aw": 0.1137,
                     "steamLag": False}
                ]
            }))
            with patch.object(mod, "POLY_FILE", poly_file):
                now_ts = "2026-06-07T12:00:00Z"
                updated = mod.update_log(log, signals, team_info={}, now_ts=now_ts)

        entry = updated["signals"][0]
        snaps = entry["snapshots"]
        # MUSS jetzt 2 Snapshots haben — der zweite vom Stale-Pass
        self.assertGreaterEqual(len(snaps), 2,
            f"Stale-Pass hätte einen Snapshot anhängen müssen — hatte {len(snaps)} Snapshots")
        last = snaps[-1]
        self.assertEqual(last["ts"], now_ts,
            "Letzter Snapshot muss aktuellen Timestamp haben")
        self.assertEqual(last["edgePp"], 0.9,
            "Letzter Snapshot muss aktuellen Edge (0.9pp) haben")
        # currentEdgePp im Entry muss auch aktualisiert sein
        self.assertEqual(entry["currentEdgePp"], 0.9,
            "currentEdgePp muss auf 0.9 aktualisiert sein")

    def test_open_signal_above_min_edge_gets_main_snapshot_not_double(self):
        """Wenn Edge >= MIN_EDGE_PP: Main-Loop snapshottet. Stale-Pass darf
        NICHT doppelt snapshotten."""
        mod = self.mod
        log = {"signals": [self._existing_open(mod, key="MEX-ZAF", market="aw")]}
        # Diesmal mit edge=2.5pp, sollte vom Main-Loop verarbeitet werden
        signals = [self._make_fx(key="MEX-ZAF", best_edge=2.5, best_key="aw")]

        import json, tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            poly_file = Path(td) / "poly.json"
            poly_file.write_text(json.dumps({
                "allFixtures": [
                    {"key": "MEX-ZAF", "edge_aw": 2.5,
                     "poly_aw": 0.105, "fair_aw": 0.1137, "steamLag": False}
                ]
            }))
            with patch.object(mod, "POLY_FILE", poly_file):
                updated = mod.update_log(log, signals, {}, "2026-06-07T12:00:00Z")

        entry = updated["signals"][0]
        # Genau 1 neuer Snapshot vom Main-Loop, kein zweiter vom Stale-Pass
        self.assertEqual(len(entry["snapshots"]), 2,
            f"Erwarte exakt 2 Snapshots (1 alt + 1 main-loop) — hatte {len(entry['snapshots'])}")


if __name__ == "__main__":
    unittest.main()
