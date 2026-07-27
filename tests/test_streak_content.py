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


class TestStreakCardTiming(unittest.TestCase):
    """04.07.2026 (Lucas: „Card kommt immer nach dem Spiel"): forward-looking bevorzugen +
    _next_fixtures muss KO-Spiele kennen (sonst kein nächstes Spiel in der K.-o.-Phase)."""

    def test_next_fixtures_kennt_ko(self):
        import compute_streaks as C
        wm = {
            "groups": {"A": {"teams": [{"id": "FRA", "name": "Frankreich"},
                                       {"id": "PRY", "name": "Paraguay"}], "fixtures": []}},
            "koFixtures": [{"home": "FRA", "away": "PRY", "round": "R16",
                            "date": "2099-01-01", "kickoff": "2099-01-01T20:00:00Z"}],
        }
        nf = C._next_fixtures(wm)
        self.assertIn("FRA", nf)
        self.assertEqual(nf["FRA"]["oppName"], "Paraguay")
        self.assertEqual(nf["FRA"]["pickKey"], "KO-R16-FRA-PRY")

    def test_forward_looking_bevorzugt(self):
        # zwei intakt-Meilenstein-Serien: eine mit nächstem Spiel, eine ohne (ausgeschieden).
        # Die forward-looking gewinnt, auch wenn die andere „heißer" (länger) ist.
        eliminated = _s("Eliminated", "99", "over25", 12)         # kein next
        upcoming = _s("Upcoming", "42", "over25", 6, opp="Gegner")
        upcoming["next"]["date"] = "2099-01-01"
        chosen = G.pick_streak_for_card([eliminated, upcoming], set())
        self.assertEqual(chosen[0]["team"], "Upcoming")

    def test_evergreen_fallback(self):
        # keine forward-looking Serie → Evergreen-Fallback greift (ausgeschiedenes Team postet)
        eliminated = _s("Eliminated", "99", "over25", 12)
        chosen = G.pick_streak_for_card([eliminated], set())
        self.assertIsNotNone(chosen)


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
                   _s("Bayern", "50", "bttsYes", 6, opp="Dortmund")]
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
        streaks = [_s("Arsenal", "42", "over25", 8, opp="City"),
                   _s("Arsenal", "42", "bttsYes", 6, opp="City")]
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


class TestStreaksDigestDedup(unittest.TestCase):
    """27.07.2026 (Lucas: „immer die selben" + „WM obwohl vorbei"): Frische-Guard + Woche-über-
    Woche-Dedup im Serien-Digest."""
    def _s(self, tid, typ, length, venue="all"):
        return {"teamId": tid, "type": typ, "length": length, "venue": venue}

    def test_key_ist_venue_aware(self):
        self.assertNotEqual(TS._skey(self._s("A", "over25", 5, "all")),
                            TS._skey(self._s("A", "over25", 5, "home")))

    def test_novel_nichts_gewachsen_ist_leer(self):
        streaks = [self._s("A", "over25", 12), self._s("B", "scored", 8)]
        state = {TS._skey(x): x["length"] for x in streaks}
        self.assertEqual(TS._novel(streaks, state, TS._skey), [])

    def test_novel_nur_gewachsene(self):
        base = [self._s("A", "over25", 12), self._s("B", "scored", 8)]
        state = {TS._skey(x): x["length"] for x in base}
        grown = [self._s("A", "over25", 13), self._s("B", "scored", 8)]
        nov = TS._novel(grown, state, TS._skey)
        self.assertEqual([x["teamId"] for x in nov], ["A"])

    def test_novel_neue_serie_kommt_durch(self):
        self.assertEqual(len(TS._novel([self._s("C", "cleanSheet", 6)], {}, TS._skey)), 1)

    def test_stale_days_erkennt_eingefrorenes_meta(self):
        import json, tempfile
        from datetime import datetime, timezone, timedelta
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            json.dump({"_meta": {"generatedAt": old}, "streaks": []}, f)
            path = f.name
        self.assertIsNotNone(TS._stale_days(path))
        self.assertGreater(TS._stale_days(path), 9)


if __name__ == "__main__":
    unittest.main()
