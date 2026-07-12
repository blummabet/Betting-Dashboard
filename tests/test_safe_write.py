#!/usr/bin/env python3
"""
test_safe_write.py — Zentraler Wipe-Schutz (12.07.2026, Lucas).

Bug-Klasse: Ein leeres/fehlgeschlagenes API-Ergebnis überschreibt bestehende Daten.
Real passiert: abgelaufener API-Key → build_liga_data schrieb mls-data.json leer →
Liga-Cards kaputt. Audit fand dieselbe Klasse in 11 weiteren Skripten.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from safe_write import preserve_nonempty, write_json_guarded


class TestPreserveNonempty(unittest.TestCase):
    def test_empty_new_keeps_old(self):
        merged, kept = preserve_nonempty({"a": {"x": 1}}, {"a": {}})
        self.assertEqual(merged["a"], {"x": 1})
        self.assertEqual(kept, ["a"])

    def test_missing_key_in_new_is_kept(self):
        merged, kept = preserve_nonempty({"a": [1, 2], "b": [3]}, {"a": [1, 2, 3]})
        self.assertEqual(merged["b"], [3])
        self.assertIn("b", kept)
        self.assertEqual(merged["a"], [1, 2, 3])   # gute Daten werden ersetzt

    def test_populated_new_replaces(self):
        merged, kept = preserve_nonempty({"a": {"x": 1}}, {"a": {"y": 2}})
        self.assertEqual(merged["a"], {"y": 2})
        self.assertEqual(kept, [])

    def test_first_run_no_old(self):
        merged, kept = preserve_nonempty({}, {"a": {"x": 1}})
        self.assertEqual(merged, {"a": {"x": 1}})
        self.assertEqual(kept, [])

    def test_empty_new_and_empty_old_ok(self):
        merged, kept = preserve_nonempty({"a": {}}, {"a": {}})
        self.assertEqual(merged["a"], {})   # nichts zu retten → kein False-Positive
        self.assertEqual(kept, [])


class TestWriteJsonGuarded(unittest.TestCase):
    def test_refuses_drastic_shrink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text(json.dumps({str(i): i for i in range(100)}))
            with self.assertRaises(SystemExit):
                write_json_guarded(p, {"1": 1})        # 100 → 1 Einträge
            # Datei UNVERÄNDERT — das ist der Punkt
            self.assertEqual(len(json.loads(p.read_text())), 100)

    def test_allows_normal_growth(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text(json.dumps({"a": 1}))
            write_json_guarded(p, {"a": 1, "b": 2})
            self.assertEqual(len(json.loads(p.read_text())), 2)

    def test_allows_mild_shrink(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text(json.dumps({str(i): i for i in range(10)}))
            write_json_guarded(p, {str(i): i for i in range(8)})   # 10 → 8 (≥50%)
            self.assertEqual(len(json.loads(p.read_text())), 8)

    def test_first_write_ok(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "neu.json"
            write_json_guarded(p, {"a": 1})
            self.assertTrue(p.exists())

    def test_force_bypasses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text(json.dumps({str(i): i for i in range(100)}))
            write_json_guarded(p, {}, force=True)
            self.assertEqual(json.loads(p.read_text()), {})

    def test_custom_count_fn(self):
        # stats_cache-Muster: {liga: {team: {...}}} → Teams zählen, nicht Ligen
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "stats.json"
            p.write_text(json.dumps({"PL": {str(i): {} for i in range(20)}}))
            cnt = lambda x: sum(len(v) for v in x.values() if isinstance(v, dict))
            with self.assertRaises(SystemExit):
                write_json_guarded(p, {"PL": {}}, count=cnt)   # 20 Teams → 0
            self.assertEqual(len(json.loads(p.read_text())["PL"]), 20)


if __name__ == "__main__":
    unittest.main()
