#!/usr/bin/env python3
"""test_poly_derived_market_filter.py — Kind-/Spezialmärkte NICHT als Moneyline verarbeiten
(01.07.2026, Lucas: „Poly-Odds die's nie gab", z.B. Argentinien-Sieg @1.45 aus einem
…-second-half-result-Markt). Der GAMMA_URL-Fix (closed=false) holt jetzt auch die Kind-Events pro
Spiel rein; die Allowlist-Regex muss sie zuverlässig aussortieren."""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), REPO / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

CHILD = [
    "fifwc-aus-egy-2026-07-03-first-to-score",
    "fifwc-arg-cvi-2026-07-03-second-half-result",
    "fifwc-bel-sen-2026-07-01-first-to-score",
    "fifwc-esp-aut-2026-07-02-first-half-result",
    "fifwc-esp-aut-2026-07-02-more-markets",
]
MONEYLINE = [
    "fifwc-esp-aut-2026-07-02",
    "fifwc-ecu-kor-2026-06-20",
    "fifwc-aus-egy-2026-07-03",
]


class TestDerivedSlugRegex(unittest.TestCase):
    def _check(self, rx):
        for s in CHILD:
            self.assertIsNotNone(rx.search(s), f"Kind-Markt sollte gefiltert werden: {s}")
        for s in MONEYLINE:
            self.assertIsNone(rx.search(s), f"Moneyline sollte bleiben: {s}")

    def test_prices_fetcher(self):
        self._check(_load("fetch_wm_poly_prices.py")._DERIVED_SLUG_RE)

    def test_steam_lag_monitor(self):
        self._check(_load("steam_lag_monitor.py")._DERIVED_SLUG_RE)


if __name__ == "__main__":
    unittest.main()
