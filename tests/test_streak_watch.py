#!/usr/bin/env python3
"""test_streak_watch.py — Serien-Watch (pre-match) + Serie gehalten/gerissen (post-match)
(04.07.2026, Lucas). Reine Selektoren/Auflöser, kein Send."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import telegram_streak_watch as W


def _streak(team="Frankreich", tid="FRA", stype="over25", length=12, state="intakt",
            venue="all", date="2026-07-04", opp="Paraguay", pk="KO-R16-FRA-PRY", xg=None):
    s = {"team": team, "teamId": tid, "type": stype, "market": f"{stype}", "length": length,
         "venue": venue, "continuation": {"state": state}, "flag": "🇫🇷", "xgBacked": xg}
    if date:
        s["next"] = {"oppName": opp, "date": date, "pickKey": pk, "oppRatePct": 60}
    return s


class TestWatch(unittest.TestCase):
    def test_hot_streak_heute_bewacht(self):
        out = W.build_watch([_streak()], {}, {}, "2026-07-04")
        self.assertEqual(len(out), 1)
        key, entry, msg = out[0]
        self.assertIn("Serien-Watch", msg)
        self.assertIn("Frankreich", msg)
        self.assertEqual(entry["pickKey"], "KO-R16-FRA-PRY")

    def test_spiel_nicht_heute_uebersprungen(self):
        self.assertEqual(W.build_watch([_streak(date="2026-07-09")], {}, {}, "2026-07-04"), [])

    def test_zu_kurz_uebersprungen(self):
        self.assertEqual(W.build_watch([_streak(length=9)], {}, {}, "2026-07-04"), [])   # 9 < 10 → raus

    def test_nicht_intakt_uebersprungen(self):
        self.assertEqual(W.build_watch([_streak(state="wackelt")], {}, {}, "2026-07-04"), [])

    def test_venue_variante_uebersprungen(self):
        self.assertEqual(W.build_watch([_streak(venue="H")], {}, {}, "2026-07-04"), [])

    def test_bereits_bewacht_uebersprungen(self):
        watched = {"FRA:over25:2026-07-04": {}}
        self.assertEqual(W.build_watch([_streak()], {}, watched, "2026-07-04"), [])

    def test_ecken_typ_nicht_bewacht(self):
        # Ecken/Karten nicht tor-basiert auflösbar → nicht bewachen
        self.assertEqual(W.build_watch([_streak(stype="cornersOver")], {}, {}, "2026-07-04"), [])

    def test_xg_siegel_in_nachricht(self):
        out = W.build_watch([_streak(xg=True)], {}, {}, "2026-07-04")
        self.assertIn("xG gedeckt", out[0][2])
        out2 = W.build_watch([_streak(xg=False)], {}, {}, "2026-07-04")
        self.assertIn("Glück", out2[0][2])


class TestStreakHeld(unittest.TestCase):
    def _fx(self, hs, as_, home="FRA", away="PRY"):
        return {"home": home, "away": away,
                "result": {"status": "FT", "home_score": hs, "away_score": as_}}

    def test_over25(self):
        self.assertTrue(W.streak_held("over25", "FRA", self._fx(3, 1)))
        self.assertFalse(W.streak_held("over25", "FRA", self._fx(1, 0)))

    def test_btts(self):
        self.assertTrue(W.streak_held("bttsYes", "FRA", self._fx(2, 1)))
        self.assertFalse(W.streak_held("bttsYes", "FRA", self._fx(2, 0)))

    def test_scored_cleansheet_seitenabhaengig(self):
        self.assertTrue(W.streak_held("scored", "FRA", self._fx(1, 0)))
        self.assertFalse(W.streak_held("scored", "PRY", self._fx(1, 0)))
        self.assertTrue(W.streak_held("cleanSheet", "FRA", self._fx(1, 0)))
        self.assertFalse(W.streak_held("cleanSheet", "PRY", self._fx(1, 0)))

    def test_unfertig_none(self):
        self.assertIsNone(W.streak_held("over25", "FRA", {"home": "FRA", "away": "PRY", "result": {}}))


class TestRecap(unittest.TestCase):
    def _wm(self, hs, as_):
        return {"groups": {}, "koFixtures": [
            {"home": "FRA", "away": "PRY", "round": "R16",
             "result": {"status": "FT", "home_score": hs, "away_score": as_}}]}

    def _watched(self):
        return {"FRA:over25:2026-07-04": {"teamId": "FRA", "team": "Frankreich", "type": "over25",
                "length": 15, "market": "over25", "pickKey": "KO-R16-FRA-PRY",
                "oppName": "Paraguay", "date": "2026-07-04"}}

    def test_haelt(self):
        msgs, done = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-05")
        self.assertEqual(len(msgs), 1)
        self.assertIn("hält", msgs[0])
        self.assertIn("16×", msgs[0])
        self.assertEqual(len(done), 1)

    def test_gerissen(self):
        msgs, done = W.build_recap(self._wm(1, 0), self._watched(), "2026-07-05")
        self.assertIn("gerissen", msgs[0])
        self.assertIn("15 Spielen", msgs[0])

    def test_spiel_noch_nicht_vorbei(self):
        # Spieltag == heute → noch nicht recappen
        msgs, done = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-04")
        self.assertEqual(msgs, [])
        self.assertEqual(done, [])

    def test_kein_endstand_wartet(self):
        wm = {"groups": {}, "koFixtures": [{"home": "FRA", "away": "PRY", "result": {}}]}
        msgs, done = W.build_recap(wm, self._watched(), "2026-07-05")
        self.assertEqual(msgs, [])   # kein Endstand → beim nächsten Lauf erneut


class TestSendGuard(unittest.TestCase):
    """06.07.2026 (Lucas): tg_send lieferte `not (TOKEN and CHAT_ID)` → True bei FEHLENDEM
    Token → main() setzte den Dedup-Marker ohne echten Send → Serie still verschluckt, nie
    nachgesendet. Fehlender Token in einem echten Lauf muss False sein; nur SKIP_TELEGRAM True."""

    def setUp(self):
        self._orig = (W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID)

    def tearDown(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = self._orig

    def test_fehlender_token_liefert_false(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = False, "", "123"
        self.assertFalse(W.tg_send("x"))   # echter Fehler → NICHT als bewacht markieren

    def test_fehlende_chat_id_liefert_false(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = False, "tok", ""
        self.assertFalse(W.tg_send("x"))

    def test_skip_telegram_liefert_true(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = True, "", ""
        self.assertTrue(W.tg_send("x"))    # expliziter Dry-Run → Flow fortsetzen


if __name__ == "__main__":
    unittest.main()
