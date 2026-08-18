"""18.08.2026 (Lucas): Auto-Bet-Push leitet den Wettbewerb aus dem Slug ab (nicht mehr hart WM)."""
import unittest
import telegram_trades as T


class TestCompetitionFromSlug(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(T._competition("fifwc-ger-civ-2026-06-12")[0], "WM 2026")
        self.assertEqual(T._competition("mls-orl-rsl-2026-08-17")[0], "MLS")
        self.assertEqual(T._competition("epl-ful-che-2026-08-24")[0], "Premier League")
        self.assertEqual(T._competition("lal-rma-fcb-2026-09-01")[0], "La Liga")
        self.assertEqual(T._competition("sea-int-mil-2026-09-01")[0], "Serie A")
        self.assertEqual(T._competition("fl1-psg-om-2026-09-01")[0], "Ligue 1")
        self.assertEqual(T._competition("bun-bvb-fcb-2026-09-01")[0], "Bundesliga")

    def test_unknown_slug_falls_back_neutral_not_wm(self):
        label, path = T._competition("weirdleague-a-b-2026-01-01")
        self.assertEqual(label, "Fussball")
        self.assertIsNone(path)
        self.assertEqual(T._competition("")[0], "Fussball")
        self.assertEqual(T._competition(None)[0], "Fussball")

    def test_poly_url_per_competition(self):
        self.assertEqual(T._poly_url("mls-orl-rsl-2026-08-17"),
                         "https://polymarket.com/sports/mls/mls-orl-rsl-2026-08-17")
        self.assertEqual(T._poly_url("fifwc-ger-civ-2026-06-12"),
                         "https://polymarket.com/sports/fifa-world-cup/fifwc-ger-civ-2026-06-12")
        # unbekannt -> generischer /event/-Link statt falschem /sports/fifa-world-cup/
        self.assertEqual(T._poly_url("weird-a-b"), "https://polymarket.com/event/weird-a-b")
        self.assertIsNone(T._poly_url(""))

    def test_message_has_no_wm_hardcode_for_mls(self):
        # Kanal nicht konfiguriert -> send gibt False, aber Formatierung laeuft; wir pruefen via _competition
        label, _ = T._competition("mls-nyr-chi-2026-08-22")
        self.assertNotIn("WM", label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
