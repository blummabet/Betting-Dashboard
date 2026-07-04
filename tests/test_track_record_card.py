#!/usr/bin/env python3
"""test_track_record_card.py — Track-Record-KPIs (04.07.2026, Lucas: „0% ist wertlos hoch 10").

Der Resolver schreibt result als WIN/LOSS/VOID (Großschrift), compute_kpis filterte aber auf
"won"/"lost"/"push" → 0 Treffer gezählt → Karte zeigte 0% Genauigkeit trotz 83 Treffern.
Dieser Test friert die Ergebnis-Normalisierung + Runden-Aufschlüsselung ein, damit der
Silent-Bug nicht zurückkommt ([[feedback_guard_on_every_bug]])."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import generate_track_record_card as T


class TestResultNormalisierung(unittest.TestCase):
    def test_grossschrift_resolver_werte(self):
        self.assertEqual(T._norm_result("WIN"), "won")
        self.assertEqual(T._norm_result("LOSS"), "lost")
        self.assertEqual(T._norm_result("VOID"), "push")

    def test_alt_kleinschrift_bleibt_gueltig(self):
        self.assertEqual(T._norm_result("won"), "won")
        self.assertEqual(T._norm_result("lost"), "lost")
        self.assertEqual(T._norm_result("push"), "push")

    def test_leer_und_unbekannt(self):
        self.assertIsNone(T._norm_result(None))
        self.assertIsNone(T._norm_result(""))
        self.assertIsNone(T._norm_result("pending"))


def _wm_fixture():
    """Mini-WM mit Gruppe (WIN/LOSS gemischt) + KO-Runde (fast alles WIN)."""
    return {
        "groups": {
            "A": {
                "fixtures": [
                    {"home": "MEX", "away": "ZAF", "date": "2026-06-11", "time": "18:00"},
                    {"home": "KOR", "away": "CZE", "date": "2026-06-12", "time": "18:00"},
                ]
            }
        },
        "koFixtures": [
            {"home": "ARG", "away": "EGY", "round": "R32",
             "kickoff": "2026-07-01T20:00:00Z", "date": "2026-07-01"},
            {"home": "BRA", "away": "NOR", "round": "R32",
             "kickoff": "2026-07-02T20:00:00Z", "date": "2026-07-02"},
        ],
        "picks": {
            "A-1-MEX-ZAF": [{"verdict": "BET", "result": "WIN", "odds": 1.8, "clvPP": 2.0}],
            "A-1-KOR-CZE": [{"verdict": "BET", "result": "LOSS", "odds": 2.1, "clvPP": -1.0}],
            "KO-R32-ARG-EGY": [{"verdict": "BET", "result": "WIN", "odds": 1.6, "clvPP": 1.5}],
            "KO-R32-BRA-NOR": [{"verdict": "BET", "result": "WIN", "odds": 1.7, "clvPP": 0.5}],
        },
    }


class TestComputeKpis(unittest.TestCase):
    def setUp(self):
        self.k = T.compute_kpis(_wm_fixture())

    def test_hit_rate_nicht_null(self):
        # 3 WIN / 1 LOSS → 75 %  (früher fälschlich 0 %)
        self.assertEqual(self.k["won"], 3)
        self.assertEqual(self.k["lost"], 1)
        self.assertEqual(self.k["hit_rate"], 75)

    def test_runden_aufschluesselung(self):
        rs = self.k["round_stats"]
        self.assertEqual(rs["Gruppenphase"]["won"], 1)
        self.assertEqual(rs["Gruppenphase"]["lost"], 1)
        self.assertEqual(rs["Sechzehntelfinale"]["won"], 2)
        self.assertEqual(rs["Sechzehntelfinale"]["hit_rate"], 100)

    def test_equity_verlauf_nicht_flach(self):
        # chronologisch: WIN, LOSS (Gruppe) → +1, 0 ; dann KO WIN, WIN → +1, +2
        self.assertEqual(self.k["equity"], [1, 0, 1, 2])

    def test_recent_form(self):
        self.assertEqual(self.k["recent_won"], 3)
        self.assertEqual(len(self.k["recent"]), 4)


class TestTemplateRendert(unittest.TestCase):
    def test_html_enthaelt_bilanz_und_runde(self):
        from tiktok_card_templates import track_record_card
        k = T.compute_kpis(_wm_fixture())
        html = track_record_card(
            roi_pct=0, hit_rate_pct=k["hit_rate"], total_picks=k["total"],
            resolved_picks=k["resolved"], won=k["won"], lost=k["lost"], push=k["push"],
            pnl_eur=0, avg_clv_pp=None, equity_curve_points=k["equity"],
            round_stats=k["round_stats"], highlight_round=k["highlight_round"],
            recent=k["recent"], recent_won=k["recent_won"],
        )
        self.assertIn("3 richtig", html)      # Bilanz im Hero
        self.assertIn("Sechzehntelfinale", html)  # Runden-Zeile
        self.assertNotIn("Vorhersage-Wert", html)  # CLV-Jargon raus
        self.assertNotIn("€", html)                # TikTok-safe


if __name__ == "__main__":
    unittest.main()
