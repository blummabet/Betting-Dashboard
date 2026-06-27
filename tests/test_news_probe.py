#!/usr/bin/env python3
"""test_news_probe.py — summarize() der News-Probe (26.06.2026): Form-Beschreibung der Roh-Response."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_news_probe as N  # noqa: E402


class TestSummarize(unittest.TestCase):
    def test_list_response(self):
        payload = {"results": 2, "errors": [], "response": [{"title": "X", "date": "2026-08-01"}, {}]}
        s = N.summarize(payload)
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["sampleItemKeys"], ["date", "title"])

    def test_empty(self):
        s = N.summarize({"results": 0, "response": []})
        self.assertEqual(s["count"], 0)
        self.assertNotIn("sampleItem", s)

    def test_non_dict(self):
        self.assertEqual(N.summarize([])["shape"], "list")


if __name__ == "__main__":
    unittest.main()
