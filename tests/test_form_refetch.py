#!/usr/bin/env python3
"""test_form_refetch.py — form_needs_refetch: Schema-stale (fehlt o25Seq) erzwingt Re-Fetch
(28.06.2026, Lucas: Serien blieben leer, weil der 24h-Cache den o25Seq-losen Eintrag übersprang)."""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_wm_form as F  # noqa: E402

NOW = datetime.now(timezone.utc).isoformat()
OLD = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


class TestRefetch(unittest.TestCase):
    def test_missing_seq_forces_refetch_even_if_fresh(self):
        # frisch, aber ohne Streak-Felder → trotzdem neu holen (der eigentliche Bug)
        self.assertTrue(F.form_needs_refetch({"updatedAt": NOW, "over25Rate": 0.5}))

    def test_missing_venueseq_forces_refetch(self):
        # alter Eintrag MIT o25Seq, aber OHNE venueSeq (Heim/Auswärts-Split) → neu holen
        self.assertTrue(F.form_needs_refetch({"updatedAt": NOW, "o25Seq": [True, False]}))

    def test_missing_wonseq_forces_refetch(self):
        # o25Seq + venueSeq vorhanden, aber OHNE wonSeq (Sieg-/Ungeschlagen-Serien) → neu holen
        self.assertTrue(F.form_needs_refetch({"updatedAt": NOW, "o25Seq": [True, False],
                                              "venueSeq": ["H", "A"]}))

    def test_full_schema_and_fresh_skips(self):
        self.assertFalse(F.form_needs_refetch({"updatedAt": NOW, "o25Seq": [True, False],
                                               "venueSeq": ["H", "A"], "wonSeq": [True, False]}))

    def test_full_schema_but_old_refetches(self):
        self.assertTrue(F.form_needs_refetch({"updatedAt": OLD, "o25Seq": [True], "venueSeq": ["H"],
                                              "wonSeq": [True]}))

    def test_empty_refetches(self):
        self.assertTrue(F.form_needs_refetch({}))


if __name__ == "__main__":
    unittest.main()
