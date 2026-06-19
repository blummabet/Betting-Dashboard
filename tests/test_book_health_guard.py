#!/usr/bin/env python3
"""
test_book_health_guard.py — Buch-Fetch-Gesundheits-Guard (19.06.2026, Lucas)

Root-Cause „seit 17.06 nichts getradet": fetch_token_book rief /books (Mehrzahl) → HTTP 400
→ JEDER Buch-Fetch scheiterte still. Der Guard check_book_fetch_healthy macht genau diesen
stillen Totalausfall sichtbar: Versuche > 0 aber 0 echte Bücher → ERROR (Transport) / WARN (dünn).
"""
import sys
import unittest
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import wm_data_integrity as W  # noqa: E402

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _run(book_health):
    with mock.patch.object(W, "_lazy",
                           side_effect=lambda f: book_health if f == "wm_book_health.json" else {}):
        res = W.run_checks({"groups": {}, "picks": {}}, {}, {}, {},
                           now=NOW, auto_bets={"bets": []}, history={})
    return next((c for c in res if c["id"] == "book_fetch_healthy"), None)


class TestBookHealthGuard(unittest.TestCase):
    def test_dead_endpoint_transport_fail_errors(self):
        c = _run({"attempts": 2, "ok": 0, "transport_fail": 2})
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "error")

    def test_healthy_when_some_books_ok(self):
        # ok > 0 → Guard meldet nichts (gibt None zurück)
        self.assertIsNone(_run({"attempts": 3, "ok": 2, "transport_fail": 1}))

    def test_never_ran_no_signal(self):
        self.assertIsNone(_run({}))
        self.assertIsNone(_run({"attempts": 0, "ok": 0, "transport_fail": 0}))

    def test_all_empty_books_warns(self):
        c = _run({"attempts": 2, "ok": 0, "transport_fail": 0, "empty_or_crossed": 2})
        self.assertIsNotNone(c)
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")


class TestBookHealthTracker(unittest.TestCase):
    def test_fetch_token_book_counts_transport_fail(self):
        import manage_wm_poly_positions as M
        M._BOOK_HEALTH.update(attempts=0, transport_fail=0, empty_or_crossed=0, ok=0)
        with mock.patch.object(M, "_http_get", return_value=None):   # = HTTP/Netz-Fehler
            self.assertIsNone(M.fetch_token_book("TOK"))
        self.assertEqual(M._BOOK_HEALTH["attempts"], 1)
        self.assertEqual(M._BOOK_HEALTH["transport_fail"], 1)
        self.assertEqual(M._BOOK_HEALTH["ok"], 0)

    def test_fetch_token_book_counts_ok(self):
        import manage_wm_poly_positions as M
        M._BOOK_HEALTH.update(attempts=0, transport_fail=0, empty_or_crossed=0, ok=0)
        book = {"bids": [{"price": 0.40, "size": 100}], "asks": [{"price": 0.43, "size": 100}]}
        with mock.patch.object(M, "_http_get", return_value=book):
            r = M.fetch_token_book("TOK")
        self.assertIsNotNone(r)
        self.assertEqual(M._BOOK_HEALTH["ok"], 1)
        self.assertEqual(M._BOOK_HEALTH["transport_fail"], 0)


if __name__ == "__main__":
    unittest.main()
