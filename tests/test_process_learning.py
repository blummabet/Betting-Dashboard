"""
test_process_learning.py — Post-Match-Prozess-Lernen (14.06.2026)

Deckt die Kette ab: echte Match-xG → „verdient/Pech"-Verdict → prozess-gewichtetes
Bayesian-Lernen. Kern-Use-Case (Lucas, QAT-SUI): Over 2.5 ging als LOSS, aber die
Schweiz war xG-dominant (Tore verdient) → das System soll die Signale milder
bestrafen als bei einem echten Fehl-Read.
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestProcessVerdict(unittest.TestCase):
    """resolve_wm_results.process_verdict — xG vs Ergebnis."""

    def setUp(self):
        import resolve_wm_results
        self.pv = resolve_wm_results.process_verdict
        # QAT(home) 0.6 : SUI(away) 2.4 → Σ3.0, endete real 1:1
        self.stats = {"xgTotal": 3.0, "homeXg": 0.6, "awayXg": 2.4}

    def test_over_lost_but_deserved_is_unlucky(self):
        self.assertEqual(self.pv("Über 2.5 Tore", "LOSS", self.stats)["processVerdict"], "UNLUCKY")

    def test_over_lost_and_deserved_loss(self):
        # 3.0 < 3.5 → Over 3.5 hat es per xG NICHT verdient
        self.assertEqual(self.pv("Über 3.5 Tore", "LOSS", self.stats)["processVerdict"], "DESERVED_LOSS")

    def test_over_won_justified(self):
        self.assertEqual(self.pv("Über 1.5 Tore", "WIN", self.stats)["processVerdict"], "JUSTIFIED")

    def test_double_chance_home_won_but_lucky(self):
        # 1X (Heim/Remis) gewann (1:1), aber Heim war xG-dominiert → glücklich
        self.assertEqual(self.pv("Doppelte Chance — 1X", "WIN", self.stats)["processVerdict"], "LUCKY")

    def test_btts_lost_but_both_deserved_is_unlucky(self):
        # FIX 14.06.2026: BTTS prozess-bewertbar. AUS-TUR 0:2 — Türkei (away) xG 1.8,
        # Australien (home) 0.9 → beide ≥0.8, BTTS-Ja verlor (TUR traf nicht) → UNLUCKY.
        s = {"xgTotal": 2.7, "homeXg": 0.9, "awayXg": 1.8}
        self.assertEqual(self.pv("Beide Teams treffen — Ja", "LOSS", s)["processVerdict"], "UNLUCKY")

    def test_btts_lost_one_side_dead_is_deserved(self):
        s = {"xgTotal": 1.4, "homeXg": 1.2, "awayXg": 0.2}   # away tot (<0.8)
        self.assertEqual(self.pv("Beide Teams treffen — Ja", "LOSS", s)["processVerdict"], "DESERVED_LOSS")

    def test_btts_no_won_both_dead_is_justified(self):
        s = {"xgTotal": 0.8, "homeXg": 0.5, "awayXg": 0.3}
        self.assertEqual(self.pv("Beide Teams treffen — Nein", "WIN", s)["processVerdict"], "JUSTIFIED")

    def test_no_stats_returns_empty(self):
        self.assertEqual(self.pv("Über 2.5 Tore", "LOSS", None), {})

    def test_pending_returns_empty(self):
        self.assertEqual(self.pv("Über 2.5 Tore", "PENDING", self.stats), {})

    def test_mls_field_convention_xghome_graded(self):
        # 27.07.2026 (Lucas: „lernt MLS wirklich?"): Liga/MLS schreibt xgHome/xgAway statt
        # homeXg/awayXg. Der Grader muss beide Konventionen gleich bewerten — sonst bleibt der
        # MLS-Ledger leer und die Gewichte lernen nichts.
        wm  = {"xgTotal": 3.0, "homeXg": 2.4, "awayXg": 0.6}
        mls = {"xgTotal": 3.0, "xgHome": 2.4, "xgAway": 0.6}
        self.assertEqual(self.pv("Heimsieg", "WIN", mls).get("processVerdict"),
                         self.pv("Heimsieg", "WIN", wm).get("processVerdict"))
        self.assertEqual(self.pv("Heimsieg", "WIN", mls).get("processVerdict"), "JUSTIFIED")
        # DC X2 (Auswärts/Remis) bei klarer Heim-xG → Glück
        self.assertEqual(self.pv("Doppelte Chance — X2", "WIN", mls).get("processVerdict"), "LUCKY")


class TestOutcomeScore(unittest.TestCase):
    """update_signal_weights._process_outcome_score — prozess-justiert + Binär-Fallback."""

    def setUp(self):
        import update_signal_weights
        self.f = update_signal_weights._process_outcome_score

    def test_process_scores(self):
        self.assertEqual(self.f({"processVerdict": "JUSTIFIED"}), 1.0)
        self.assertEqual(self.f({"processVerdict": "DESERVED_LOSS"}), 0.0)
        self.assertGreater(self.f({"processVerdict": "UNLUCKY"}), 0.0)   # Loss, aber Teilgutschrift
        self.assertLess(self.f({"processVerdict": "LUCKY"}), 1.0)        # Win, aber Teilabzug

    def test_binary_fallback_identical_to_old(self):
        # Ohne processVerdict exakt altes Verhalten: WIN=1, LOSS=0, Void=None
        self.assertEqual(self.f({"result": "WIN"}), 1.0)
        self.assertEqual(self.f({"result": "LOSS"}), 0.0)
        self.assertIsNone(self.f({"result": "VOID"}))


class TestProcessWeightedLearningSofterPenalty(unittest.TestCase):
    """Ein verlorener-aber-verdienter Pick bestraft ein Signal MILDER als ein
    verlorener-und-verdient-verlorener (gleiche Signal-Richtung)."""

    def test_unlucky_loss_softer_than_deserved_loss(self):
        import update_signal_weights as U
        sig = [{"name": "form_trend", "score": 1.0}]   # score>0 = „guter Pick"
        unlucky = [{"result": "LOSS", "processVerdict": "UNLUCKY", "signals": sig}] * 5
        deserved = [{"result": "LOSS", "processVerdict": "DESERVED_LOSS", "signals": sig}] * 5
        # Gutschrift summieren wie der Updater
        cu = sum(U._process_outcome_score(p) for p in unlucky)
        cd = sum(U._process_outcome_score(p) for p in deserved)
        self.assertGreater(cu, cd, "UNLUCKY-Loss muss mehr Gutschrift geben als DESERVED_LOSS")


class TestLedgerCarriesVerdict(unittest.TestCase):
    """build_signal_ledger.collect_observations hängt processVerdict an, wenn Match-
    Stats vorhanden sind."""

    def test_verdict_attached_from_stats(self):
        import build_signal_ledger as B
        wm = {
            "groups": {"B": {"fixtures": [{
                "matchday": 1, "home": "CAN", "away": "BIH",
                "result": {"status": "FT", "home_score": 1, "away_score": 1,
                           "stats": {"xgTotal": 3.0, "homeXg": 0.6, "awayXg": 2.4}},
            }]}},
            "picks": {"B-1-CAN-BIH": [{
                "market": "Über 2.5 Tore", "result": "LOSS",
                "signals": [{"name": "xg_strength", "score": 1.2}],
            }]},
        }
        recs = B.collect_observations(wm)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].get("processVerdict"), "UNLUCKY")


if __name__ == "__main__":
    unittest.main()
