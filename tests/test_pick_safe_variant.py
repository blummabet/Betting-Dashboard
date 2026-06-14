"""
test_pick_safe_variant.py — Guard gegen den „riskante Variante als Haupt-Pick"-Bug
(Lucas, 14.06.2026). Favoriten bekamen „AH Heim −1.5 @2.9" statt normalem Sieg, weil
die Substitutions-Map AH-Linien nicht kannte. Der Guard (wm_data_integrity.
check_pick_safe_variant) flaggt jeden BET-Pick mit riskanter Variante (AH ≤ −1.5 ODER
Quote > 3.0) der KEINE sichere Variante (saferAltFor/boldAlt) anbietet.
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from wm_data_integrity import run_checks  # noqa: E402


def _result(wm):
    checks = run_checks(wm, {}, {}, {}, auto_bets={"bets": []}, history={})
    return next(c for c in checks if c["id"] == "pick_safe_variant")


def _wm(picks):
    return {"groups": {}, "picks": picks}


class TestPickSafeVariant(unittest.TestCase):
    def test_risky_ah_bet_without_safer_flagged(self):
        wm = _wm({"G-1-BEL-EGY": [
            {"verdict": "BET", "market": "AH Heim −1.5", "odds": 2.9}]})
        self.assertFalse(_result(wm)["ok"])

    def test_risky_ah_bet_with_boldalt_ok(self):
        wm = _wm({"G-1-BEL-EGY": [
            {"verdict": "BET", "market": "AH Heim −1.5", "odds": 2.9,
             "boldAlt": {"market": "AH Heim −0.5", "odds": 1.59}}]})
        self.assertTrue(_result(wm)["ok"])

    def test_safer_variant_hero_ok(self):
        # Die sichere Variante selbst (saferAltFor gesetzt) ist nie ein Verstoß.
        wm = _wm({"G-1-BEL-EGY": [
            {"verdict": "ABWÄGEN", "market": "AH Heim −0.5", "odds": 1.59,
             "saferAltFor": "AH Heim −1.5"}]})
        self.assertTrue(_result(wm)["ok"])

    def test_high_odds_bet_without_safer_flagged(self):
        wm = _wm({"E-1-CIV-ECU": [
            {"verdict": "BET", "market": "AH Heim −0.5", "odds": 3.55}]})
        self.assertFalse(_result(wm)["ok"])

    def test_normal_win_not_flagged(self):
        # Ein normaler Sieg @2.73 ist genau die SICHERE Form (kein Handicap, Quote < 3).
        wm = _wm({"A-1-KOR-CZE": [
            {"verdict": "BET", "market": "Heimsieg", "odds": 2.73}]})
        self.assertTrue(_result(wm)["ok"])

    def test_risky_abwaegen_not_flagged(self):
        # Nur BET-Headlines sind kritisch; riskante ABWÄGEN-Longshots werden vom Renderer
        # zu „Beobachtungs-Spiel" demotet, nicht als Pick gezeigt.
        wm = _wm({"C-2-SCO-MAR": [
            {"verdict": "ABWÄGEN", "market": "AH Auswärts −2", "odds": 6.4}]})
        self.assertTrue(_result(wm)["ok"])

    def test_away_favorite_risky_bet_flagged(self):
        wm = _wm({"J-2-JOR-DZA": [
            {"verdict": "BET", "market": "AH Auswärts −1.5", "odds": 2.44}]})
        self.assertFalse(_result(wm)["ok"])


if __name__ == "__main__":
    unittest.main()
