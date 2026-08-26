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


# ── Atomares Schreiben (25.08.2026, Audit-Befund 01) ─────────────────────────────────────────
# Vorher: open(path,"w") + json.dump. Zwischen Oeffnen und letztem Byte ist die Datei kaputt.
# Wird der Runner in dem Fenster abgeraeumt, faellt im naechsten Lauf jede Bankroll-Grenze aus,
# weil der Loader still den Default liefert. temp+replace macht das Ersetzen zu EINEM Schritt.
import json as _json
import pytest as _pytest


def test_schreibt_und_hinterlaesst_keine_tmp(tmp_path):
    from safe_write import write_json_atomic
    p = tmp_path / "bets.json"
    write_json_atomic(p, {"bets": [1, 2, 3]})
    assert _json.loads(p.read_text()) == {"bets": [1, 2, 3]}
    assert not (tmp_path / "bets.json.tmp").exists()


def test_ersetzt_bestehende_datei(tmp_path):
    from safe_write import write_json_atomic
    p = tmp_path / "bets.json"
    write_json_atomic(p, {"bets": [1]})
    write_json_atomic(p, {"bets": [1, 2]})
    assert _json.loads(p.read_text())["bets"] == [1, 2]


def test_darf_schrumpfen(tmp_path):
    # Unterschied zu write_json_guarded: ein Ledger darf beim Prunen kleiner werden.
    from safe_write import write_json_atomic
    p = tmp_path / "ledger.json"
    write_json_atomic(p, list(range(100)))
    write_json_atomic(p, [1])
    assert _json.loads(p.read_text()) == [1]


def test_abbruch_mitten_im_schreiben_laesst_den_alten_stand_stehen(tmp_path, monkeypatch):
    """Der eigentliche Punkt: geht das Schreiben schief, ist die ALTE Datei noch da und lesbar."""
    import safe_write
    p = tmp_path / "bets.json"
    safe_write.write_json_atomic(p, {"bets": ["alt1", "alt2"]})

    def kracht(*a, **kw):
        raise OSError("Runner abgeraeumt")

    monkeypatch.setattr(safe_write.json, "dump", kracht)
    with _pytest.raises(OSError):
        safe_write.write_json_atomic(p, {"bets": ["neu"]})

    assert _json.loads(p.read_text())["bets"] == ["alt1", "alt2"], "alter Stand muss unversehrt sein"


def test_kompakt_ohne_indent(tmp_path):
    from safe_write import write_json_atomic
    p = tmp_path / "gross.json"
    write_json_atomic(p, {"a": 1, "b": 2}, indent=None)
    assert p.read_text() == '{"a":1,"b":2}'

