#!/usr/bin/env python3
"""test_streak_content.py — Serien-Content (29.06.2026, Lucas): TikTok-Card-Auswahl (gegated/dedup)
+ Telegram-Wochendigest. Reine Selektoren, kein Render/Send."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate_daily_tiktok as G
import telegram_streaks as TS
import tiktok_card_templates as TC


def _s(team, tid, stype, length, state="intakt", venue="all", confirm=False, opp=None):
    d = {"team": team, "teamId": tid, "type": stype, "market": f"{stype}-Markt",
         "length": length, "venue": venue, "continuation": {"state": state}}
    if confirm:
        d["signalInfo"] = {"state": "confirm", "count": 3}
    if opp:
        d["next"] = {"oppName": opp}
    return d


class TestTiktokStreakPick(unittest.TestCase):
    def test_hot_milestone_picked(self):
        chosen = G.pick_streak_for_card([_s("Arsenal", "42", "over25", 6)], set())
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen[0]["team"], "Arsenal")
        self.assertEqual(chosen[1], "streak:42:over25:6")

    def test_below_milestone_skipped(self):
        self.assertIsNone(G.pick_streak_for_card([_s("Arsenal", "42", "over25", 4)], set()))

    def test_not_intakt_skipped(self):
        self.assertIsNone(G.pick_streak_for_card([_s("Arsenal", "42", "over25", 8, state="wackelt")], set()))

    def test_venue_variant_skipped(self):
        self.assertIsNone(G.pick_streak_for_card([_s("Arsenal", "42", "over25", 8, venue="H")], set()))

    def test_already_posted_milestone_skipped(self):
        posted = {"streak:42:over25:6"}
        # Länge 6 → Meilenstein 6 schon gepostet → None
        self.assertIsNone(G.pick_streak_for_card([_s("Arsenal", "42", "over25", 6)], posted))
        # Länge 8 → neuer Meilenstein 8 → wieder posten
        self.assertIsNotNone(G.pick_streak_for_card([_s("Arsenal", "42", "over25", 8)], posted))

    def test_hottest_chosen(self):
        cands = [_s("A", "1", "over25", 6), _s("B", "2", "over25", 8, confirm=True)]
        chosen = G.pick_streak_for_card(cands, set())
        self.assertEqual(chosen[0]["team"], "B")   # länger + Signal → mehr Heat


class TestTelegramDigest(unittest.TestCase):
    def test_digest_lists_hot_streaks(self):
        streaks = [_s("Arsenal", "42", "over25", 7, opp="City"),
                   _s("Bayern", "50", "bttsYes", 6)]
        msg = TS.build_streaks_digest(streaks)
        self.assertIn("Serien der Woche", msg)
        self.assertIn("Arsenal", msg)
        self.assertIn("Bayern", msg)
        self.assertIn("City", msg)              # nächster Gegner
        self.assertIn("keine Wettempfehlung", msg)

    def test_none_when_no_hot(self):
        self.assertIsNone(TS.build_streaks_digest([_s("X", "9", "over25", 3)]))   # zu kurz
        self.assertIsNone(TS.build_streaks_digest([_s("X", "9", "over25", 8, state="wackelt")]))

    def test_distinct_teams(self):
        streaks = [_s("Arsenal", "42", "over25", 8), _s("Arsenal", "42", "bttsYes", 6)]
        msg = TS.build_streaks_digest(streaks)
        self.assertEqual(msg.count("Arsenal"), 1)   # je Team nur die stärkste


class TestStreakCardCrest(unittest.TestCase):
    """Logo-Logik (30.06.2026, Lucas „mit Team-Logos arbeiten"): Vereine numerisch → API-Logo,
    WM-Code → Flagge, sonst Initialen."""
    def test_numeric_id_uses_logo(self):
        html = TC.streak_card("Arsenal", "42", "Über 2,5", 8, [True] * 8, "intakt", True, "City", "23.08.")
        self.assertIn("media.api-sports.io/football/teams/42.png", html)

    def test_wm_code_uses_flag(self):
        html = TC.streak_card("Frankreich", "FRA", "Über 2,5", 6, [True] * 6, "intakt", False, flag="🇫🇷")
        self.assertIn("🇫🇷", html)
        self.assertNotIn("api-sports", html)

    def test_no_id_uses_initials(self):
        html = TC.streak_card("Unbekannt", None, "Über 2,5", 7, [True] * 7, "intakt", False)
        self.assertIn(">UNB<", html)


class TestKoMatchContexts(unittest.TestCase):
    """29.06.2026 (Lucas „keine Review/Preview in KO-Phase"): Preview/Review-Iterator muss koFixtures
    mitnehmen (Spiele liegen dort, nicht in groups) — sonst feuert der Killer-Stat-Fallback."""
    WM = {"groups": {"A": {"teams": [{"id": "GER", "name": "DE", "flag": "x"},
                                     {"id": "PRY", "name": "PY", "flag": "y"}],
                           "fixtures": [{"home": "GER", "away": "PRY", "matchday": 1, "date": "2026-06-20"}]}},
          "koFixtures": [{"home": "GER", "away": "PRY", "round": "R32", "roundLabel": "Sechzehntelfinale",
                          "date": "2026-06-29", "result": {"status": "FT", "home_score": 2, "away_score": 0}}]}

    def test_iterator_includes_ko(self):
        ctx = list(G._iter_match_contexts(self.WM))
        ko = [c for c in ctx if c[3].startswith("KO-")]
        self.assertEqual(len(ko), 1)
        self.assertEqual(ko[0][3], "KO-R32-GER-PRY")     # pkey wie generate_wm_picks
        self.assertIn("Sechzehntelfinale", ko[0][2])     # Runden-Label statt Gruppe

    def test_ko_global_team_lookup(self):
        # KO-Fixture hat nur IDs → Iterator liefert globale Team-Union zum Auflösen
        ko = next(c for c in G._iter_match_contexts(self.WM) if c[3].startswith("KO-"))
        teams = ko[1]
        self.assertEqual(teams["GER"]["name"], "DE")

    def test_ko_open_pairing_skipped(self):
        wm = {"groups": {}, "koFixtures": [{"home": "GER", "away": None, "round": "R32"}]}
        self.assertEqual([c for c in G._iter_match_contexts(wm) if c[3].startswith("KO-")], [])


if __name__ == "__main__":
    unittest.main()
