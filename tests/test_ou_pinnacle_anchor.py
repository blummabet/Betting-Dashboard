"""
test_ou_pinnacle_anchor.py — O/U + BTTS Pinnacle-Anker (Lucas, 14.06.2026).

Zweite Hälfte der Pinnacle-Anker-Umstellung: Tor-Märkte (Über/Unter/BTTS) laufen nicht
mehr über das Poisson-λ-Modell, sondern über die de-viggte Pinnacle-Linie als Baseline.
Sonst schlug das Modell Pinnacle und erzeugte Phantom-Edges (DEU-CUW Unter 3.5: Poisson
48 % statt Pinnacle-fair 39 %).

Getestet wird der Regressions-Tripwire wm_data_integrity.check_ou_pinnacle_anchored:
  - geankerter O/U-Pick (modelOdds == de-vig Pinnacle)        → OK
  - Poisson-Pick (modelOdds weicht ab)                        → FAIL
  - gepostetes Spiel (heute/morgen) bleibt bewusst unangerührt → OK (ausgenommen)
  - kein Pinnacle-Linien-Paar vorhanden                       → OK (Poisson-Fallback ok)
Plus die De-Vig-Mathematik selbst.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from wm_data_integrity import run_checks  # noqa: E402

# Fixes „Jetzt" → tomorrow = 2026-06-15. Spiele ≤ 15.06. gelten als gepostet (ausgenommen),
# ab 16.06. als neu gebaut (Anker Pflicht).
NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

MODEL_MARGIN = 0.96


def _devig_modelodds(o_over, o_under, side):
    """Erwartete modelOdds eines geankerten Picks = prob_to_odds(de-vig Pinnacle)."""
    io, iu = 1.0 / o_over, 1.0 / o_under
    fair = (io if side == "o" else iu) / (io + iu)
    return round((1.0 / fair) * MODEL_MARGIN, 3)


def _wm(date, market, model_odds, *, o_over=1.54, o_under=2.4,
        pair=("o35", "u35"), verdict="BET"):
    """Ein Spiel (Gruppe A, MD2, MEX-KOR) mit einem O/U-Pick + Pinnacle-Linie."""
    return {
        "groups": {"A": {"fixtures": [
            {"matchday": 2, "home": "MEX", "away": "KOR", "date": date}]}},
        "odds": {"MEX-KOR": {pair[0]: o_over, pair[1]: o_under}},
        "picks": {"A-2-MEX-KOR": [
            {"verdict": verdict, "market": market, "odds": 2.5, "modelOdds": model_odds}]},
    }


def _result(wm):
    checks = run_checks(wm, {}, {}, {}, auto_bets={"bets": []}, history={}, now=NOW)
    return next(c for c in checks if c["id"] == "ou_pinnacle_anchored")


class TestDevigMath(unittest.TestCase):
    def test_over_under_sum_to_one(self):
        io, iu = 1.0 / 1.54, 1.0 / 2.4
        fair_over = io / (io + iu)
        fair_under = iu / (io + iu)
        self.assertAlmostEqual(fair_over + fair_under, 1.0, places=9)
        # Pinnacle bepreist Curaçao gegen Deutschland klar als Über-lastig.
        self.assertGreater(fair_over, fair_under)

    def test_devig_removes_margin(self):
        # Faire Wahrscheinlichkeit muss kleiner sein als die vig-behaftete Implied-Quote.
        io = 1.0 / 1.54
        fair_over = io / (io + 1.0 / 2.4)
        self.assertLess(fair_over, io)  # de-vig zieht Marge ab


class TestOUAnchorGuard(unittest.TestCase):
    def test_anchored_future_pick_ok(self):
        mo = _devig_modelodds(1.54, 2.4, "u")          # Unter 3.5, de-viggt
        wm = _wm("2026-06-20", "Unter 3.5 Tore", mo)
        self.assertTrue(_result(wm)["ok"])

    def test_poisson_future_pick_flagged(self):
        # Poisson-Wert (2.011) weicht klar von Pinnacle-Anker (~2.456) ab → Regression.
        wm = _wm("2026-06-20", "Unter 3.5 Tore", 2.011)
        r = _result(wm)
        self.assertFalse(r["ok"])
        self.assertEqual(r["nFail"], 1)

    def test_posted_today_exempt(self):
        # Heutiges (gepostetes) Spiel mit Poisson-modelOdds → bewusst ausgenommen.
        wm = _wm("2026-06-14", "Unter 3.5 Tore", 2.011)
        self.assertTrue(_result(wm)["ok"])

    def test_posted_tomorrow_exempt(self):
        # Morgiges (gepostetes) Spiel ebenfalls ausgenommen.
        wm = _wm("2026-06-15", "Unter 3.5 Tore", 2.011)
        self.assertTrue(_result(wm)["ok"])

    def test_no_pinnacle_line_skipped(self):
        # Künftiges Spiel ohne Pinnacle-O/U-Paar → Poisson-Fallback erlaubt, nicht prüfbar.
        wm = _wm("2026-06-20", "Unter 3.5 Tore", 2.011,
                 pair=("o25", "u25"))  # liefert o35/u35 nicht
        self.assertTrue(_result(wm)["ok"])

    def test_anchored_over_pick_ok(self):
        mo = _devig_modelodds(1.54, 2.4, "o")          # Über 3.5
        wm = _wm("2026-06-20", "Über 3.5 Tore", mo)
        self.assertTrue(_result(wm)["ok"])

    def test_anchored_btts_pick_ok(self):
        mo = _devig_modelodds(1.8, 2.0, "o")           # BTTS Ja
        wm = _wm("2026-06-20", "Beide Teams treffen — Ja", mo,
                 o_over=1.8, o_under=2.0, pair=("bttsY", "bttsN"))
        self.assertTrue(_result(wm)["ok"])

    def test_poisson_btts_flagged(self):
        wm = _wm("2026-06-20", "Beide Teams treffen — Ja", 3.5,
                 o_over=1.8, o_under=2.0, pair=("bttsY", "bttsN"))
        self.assertFalse(_result(wm)["ok"])

    def test_beobachten_not_checked(self):
        # Nur BET/ABWÄGEN sind relevant; BEOBACHTEN wird nicht getrackt.
        wm = _wm("2026-06-20", "Unter 3.5 Tore", 2.011, verdict="BEOBACHTEN")
        self.assertTrue(_result(wm)["ok"])


if __name__ == "__main__":
    unittest.main()
