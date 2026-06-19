#!/usr/bin/env python3
"""
test_post_only_retry.py — Post-Only/503-Retry (19.06.2026, Lucas)

Polymarkets CLOB geht zeitweise in „post-only mode" (nur Maker-Orders) → Market-Order wird
mit retry_after_seconds abgelehnt. place_order_with_retry probiert EINMAL nach dem Backoff
erneut (gecappt), fängt so kurze Fenster im selben Lauf ab. Andere Fehler werden NICHT geretryt.
"""
import sys
import unittest
import unittest.mock as mock
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import auto_wm_poly_trigger as T  # noqa: E402

_POST_ONLY = {"status": "failed", "error":
              "PolyApiException[status_code=503, error_message={'code': 'post_only_mode', "
              "'retry_after_seconds': 100}]"}
_OK = {"status": "placed", "orderId": "0xabc"}
_CREDS = {"status": "failed", "error": "invalid api credentials"}


class TestPostOnlyRetry(unittest.TestCase):
    def setUp(self):
        self._sleep = mock.patch.object(T.time, "sleep").start()
        T.POST_ONLY_RETRY_MAX_S = 120
        self.addCleanup(mock.patch.stopall)

    def test_transient_then_success_retries_once(self):
        place = mock.Mock(side_effect=[_POST_ONLY, _OK])
        r = T.place_order_with_retry(place, "TOK", 5.5, "pk", 0.31)
        self.assertEqual(r["status"], "placed")
        self.assertEqual(place.call_count, 2)        # genau ein Retry
        self.assertTrue(self._sleep.called)
        self.assertLessEqual(self._sleep.call_args[0][0], 120)   # gecappt

    def test_transient_twice_gives_up(self):
        place = mock.Mock(side_effect=[_POST_ONLY, _POST_ONLY])
        r = T.place_order_with_retry(place, "TOK", 5.5, "pk", 0.31)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(place.call_count, 2)        # nicht endlos

    def test_non_transient_not_retried(self):
        place = mock.Mock(side_effect=[_CREDS])
        r = T.place_order_with_retry(place, "TOK", 5.5, "pk", 0.31)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(place.call_count, 1)        # KEIN Retry bei Creds-Fehler
        self.assertFalse(self._sleep.called)

    def test_immediate_success_no_retry_no_sleep(self):
        place = mock.Mock(side_effect=[_OK])
        r = T.place_order_with_retry(place, "TOK", 5.5, "pk", 0.31)
        self.assertEqual(r["status"], "placed")
        self.assertEqual(place.call_count, 1)
        self.assertFalse(self._sleep.called)

    def test_retry_after_parsed_and_capped(self):
        T.POST_ONLY_RETRY_MAX_S = 30   # niedriger Cap
        place = mock.Mock(side_effect=[_POST_ONLY, _OK])
        T.place_order_with_retry(place, "TOK", 5.5, "pk", 0.31)
        self.assertEqual(self._sleep.call_args[0][0], 30)   # 100+5 → auf 30 gecappt


if __name__ == "__main__":
    unittest.main()
