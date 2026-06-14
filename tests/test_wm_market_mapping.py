"""
test_wm_market_mapping.py — Guard gegen den "kein Markt"-Bug vom 14.06.2026.

Bug: WM_MARKET_TO_PRICE_KEY (polymarket-tab.js) hatte 'Over 3.5 Tore' aber NICHT
'Under 3.5 Tore' (und kein 'Under 1.5 Tore'). Folge: Deutschland-Curaçao "Under 3.5"
zeigte "kein Markt", obwohl poly_u35 in den Daten war → Pick nicht manuell wettbar.

Tiefe: stiller Bug, blockiert eine reale Geld-Wette. → Regressions-Guard (feedback_guard_on_every_bug).

Invariante: JEDE Tor-Linie + BTTS, die die Pick-Engine ausgeben kann, MUSS im Frontend
auf ein Poly-Preisfeld gemappt sein — sonst ist der Pick auf Polymarket nicht handelbar.
"""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
JS = BASE / "polymarket-tab.js"

# Tor-/BTTS-Märkte, die generate_wm_picks emittieren kann, → erwartetes Poly-Feld.
EXPECTED = {
    "Over 1.5 Tore":       "poly_o15",
    "Under 1.5 Tore":      "poly_u15",
    "Over 2.5 Tore":       "poly_o25",
    "Under 2.5 Tore":      "poly_u25",
    "Over 3.5 Tore":       "poly_o35",
    "Under 3.5 Tore":      "poly_u35",
    "Beide Teams treffen": "poly_btts",
}


def _extract_map() -> dict:
    src = JS.read_text(encoding="utf-8")
    m = re.search(r"WM_MARKET_TO_PRICE_KEY\s*=\s*\{(.*?)\}", src, re.DOTALL)
    assert m, "WM_MARKET_TO_PRICE_KEY nicht in polymarket-tab.js gefunden"
    body = m.group(1)
    out = {}
    for km, vm in re.findall(r"'([^']+)'\s*:\s*'([^']+)'", body):
        out[km] = vm
    return out


class TestWmMarketMapping(unittest.TestCase):
    def test_all_goal_and_btts_markets_mapped(self):
        mp = _extract_map()
        missing = [k for k in EXPECTED if k not in mp]
        self.assertEqual(missing, [], f"Nicht gemappte Märkte (→ 'kein Markt' im UI): {missing}")

    def test_mappings_point_to_correct_poly_field(self):
        mp = _extract_map()
        wrong = {k: mp[k] for k, v in EXPECTED.items() if k in mp and mp[k] != v}
        self.assertEqual(wrong, {}, f"Falsches Poly-Feld gemappt: {wrong}")

    def test_over_under_lines_are_symmetric(self):
        # Wenn eine Over-Linie gemappt ist, MUSS auch die Under-Linie da sein (und umgekehrt).
        mp = _extract_map()
        for line in ("1.5", "2.5", "3.5"):
            over, under = f"Over {line} Tore", f"Under {line} Tore"
            self.assertEqual(
                over in mp, under in mp,
                f"Asymmetrie bei {line}: Over={over in mp} Under={under in mp} "
                f"— genau dieser Bug ließ 'Under 3.5' als 'kein Markt' erscheinen",
            )


if __name__ == "__main__":
    unittest.main()
