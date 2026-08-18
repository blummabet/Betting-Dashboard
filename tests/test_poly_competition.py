"""18.08.2026 (Lucas): zentrale Slug->Wettbewerb-Ableitung + Resolver-byCompetition-Buckets."""
import json, os, tempfile, unittest
from pathlib import Path
import poly_competition as PC


class TestPolyCompetition(unittest.TestCase):
    def test_label_and_key_from_slug(self):
        self.assertEqual(PC.label_of("mls-orl-rsl-2026-08-17"), "MLS")
        self.assertEqual(PC.label_of("epl-ful-che-2026-08-24"), "Premier League")
        self.assertEqual(PC.label_of("lal-rma-fcb-2026-09-01"), "La Liga")
        self.assertEqual(PC.key_of("sea-int-mil-2026-09-01"), "seriea")
        self.assertEqual(PC.key_of("fifwc-ger-civ-2026-06-12"), "wc")

    def test_dataset_fallback_when_no_slug(self):
        self.assertEqual(PC.label_of(None, "mls"), "MLS")
        self.assertEqual(PC.key_of(None, "liga"), "liga_mix")
        self.assertEqual(PC.label_of("", "wm"), "WM 2026")

    def test_unknown_is_neutral_not_wm(self):
        self.assertEqual(PC.label_of("weird-a-b"), "Fussball")
        self.assertIsNone(PC.poly_path("weird-a-b"))

    def test_poly_url(self):
        self.assertEqual(PC.poly_url("mls-orl-rsl-2026-08-17"),
                         "https://polymarket.com/sports/mls/mls-orl-rsl-2026-08-17")
        self.assertEqual(PC.poly_url("weird-a-b"), "https://polymarket.com/event/weird-a-b")


class TestResolverByCompetition(unittest.TestCase):
    def _run(self, bets):
        import resolve_wm_results as R
        tmp = Path(tempfile.mkdtemp()) / "results.json"
        old = R.RESULTS_FILE
        R.RESULTS_FILE = tmp
        try:
            R._write_results(bets, "2026-08-18T00:00:00Z")
            return json.loads(tmp.read_text(encoding="utf-8"))
        finally:
            R.RESULTS_FILE = old

    def test_bucketed_by_competition_from_slug(self):
        bets = [
            {"slug": "epl-ful-che-2026-08-24", "market": "Heimsieg", "stake": 10,
             "result": "WIN", "pnl": 8.0, "clvPP": 2.0},
            {"slug": "epl-ars-tot-2026-08-25", "market": "Auswärtssieg", "stake": 10,
             "result": "LOSS", "pnl": -10.0, "clvPP": -1.0},
            {"slug": "mls-orl-rsl-2026-08-17", "market": "Unentschieden", "stake": 5,
             "result": "WIN", "pnl": 12.0, "clvPP": 3.0},
        ]
        out = self._run(bets)
        byc = out["summary"]["postmortem"]["byCompetition"]
        self.assertIn("epl", byc)
        self.assertIn("mls", byc)
        self.assertEqual(byc["epl"]["label"], "Premier League")
        self.assertEqual(byc["epl"]["n"], 2)
        self.assertAlmostEqual(byc["epl"]["pnl"], -2.0, places=2)
        self.assertAlmostEqual(byc["epl"]["staked"], 20.0, places=2)
        self.assertAlmostEqual(byc["epl"]["roi"], -10.0, places=1)   # -2/20*100
        self.assertAlmostEqual(byc["epl"]["avgClv"], 0.5, places=2)  # (2-1)/2
        self.assertEqual(byc["mls"]["n"], 1)
        self.assertAlmostEqual(byc["mls"]["roi"], 240.0, places=1)   # 12/5*100
        # jeder Bet wird gestempelt
        self.assertTrue(all("competition" in b for b in out["bets"]))

    def test_prefers_stamped_competition_field_over_slug(self):
        bets = [{"competition": "laliga", "competitionLabel": "La Liga",
                 "slug": "", "market": "Heimsieg", "stake": 10,
                 "result": "WIN", "pnl": 5.0, "clvPP": 1.0}]
        out = self._run(bets)
        self.assertIn("laliga", out["summary"]["postmortem"]["byCompetition"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
