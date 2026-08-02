#!/usr/bin/env python3
"""test_streak_watch.py — Serien-Watch (pre-match) + Serie gehalten/gerissen (post-match)
(04.07.2026, Lucas). Reine Selektoren/Auflöser, kein Send.

02.08.2026 (Lucas: „Spiele waren heute Nacht"): der Watch gated jetzt auf den ECHTEN Anpfiff
(WATCH_LEAD_MIN..WATCH_HORIZON_H) statt auf `date == today`. Tests bekommen ein `kickoff` +
ein festes `now` gespritzt."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import telegram_streak_watch as W

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)   # fixer Prüfzeitpunkt


def _ko(hours):
    return (NOW + timedelta(hours=hours)).isoformat()


def _streak(team="Frankreich", tid="FRA", stype="over25", length=12, state="intakt",
            venue="all", date="2026-07-04", opp="Paraguay", pk="KO-R16-FRA-PRY", xg=None,
            ko_h=6):
    """ko_h = Stunden bis Anpfiff (relativ zu NOW); None → gar kein kickoff-Feld."""
    s = {"team": team, "teamId": tid, "type": stype, "market": f"{stype}", "length": length,
         "venue": venue, "continuation": {"state": state}, "flag": "🇫🇷", "xgBacked": xg}
    if date:
        nx = {"oppName": opp, "date": date, "pickKey": pk, "oppRatePct": 60}
        if ko_h is not None:
            nx["kickoff"] = _ko(ko_h)
        s["next"] = nx
    return s


class TestWatch(unittest.TestCase):
    def _watch(self, streaks, watched=None):
        return W.build_watch(streaks, {}, watched or {}, "2026-07-04", now=NOW)

    def test_anpfiff_bevorstehend_bewacht(self):
        out = self._watch([_streak(ko_h=6)])
        self.assertEqual(len(out), 1)
        key, entry, msg = out[0]
        self.assertIn("Serien-Watch", msg)
        self.assertIn("Frankreich", msg)
        self.assertEqual(entry["pickKey"], "KO-R16-FRA-PRY")
        self.assertIn("kickoff", entry)   # Anpfiff wird mitgeschrieben

    def test_anpfiff_vorbei_nicht_bewacht(self):
        # DER „heute Nacht"-Bug: Spiel lief schon (Anpfiff -3 h), Datum aber == heute → früher gefeuert.
        self.assertEqual(self._watch([_streak(ko_h=-3)]), [])

    def test_anpfiff_zu_knapp_nicht_bewacht(self):
        # < WATCH_LEAD_MIN (30 min) → nicht mehr spielbar
        self.assertEqual(self._watch([_streak(ko_h=0.25)]), [])   # +15 min

    def test_anpfiff_zu_weit_weg_nicht_bewacht(self):
        # > WATCH_HORIZON_H (18 h) → erst näher am Spiel
        self.assertEqual(self._watch([_streak(ko_h=30)]), [])

    def test_ohne_kickoff_nicht_bewacht(self):
        # kein Zeitstempel → lieber still als falsch
        self.assertEqual(self._watch([_streak(ko_h=None)]), [])

    def test_spaetes_us_spiel_naechster_utc_tag_trotzdem_bewacht(self):
        # Anpfiff in 8 h, aber UTC-Datum bereits MORGEN → der alte date==today-Filter hätte es
        # verschluckt; jetzt zählt der Zeitpunkt → wird bewacht.
        out = self._watch([_streak(date="2026-07-05", ko_h=8, pk="KO-R16-FRA-XXX")])
        self.assertEqual(len(out), 1)

    def test_zu_kurz_uebersprungen(self):
        self.assertEqual(self._watch([_streak(length=9)]), [])   # 9 < 10 → raus

    def test_nicht_intakt_uebersprungen(self):
        self.assertEqual(self._watch([_streak(state="wackelt")]), [])

    def test_venue_variante_uebersprungen(self):
        self.assertEqual(self._watch([_streak(venue="H")]), [])

    def test_bereits_bewacht_uebersprungen(self):
        watched = {"FRA:over25:2026-07-04": {}}
        self.assertEqual(self._watch([_streak()], watched), [])

    def test_ecken_typ_nicht_bewacht(self):
        self.assertEqual(self._watch([_streak(stype="cornersOver")]), [])

    def test_xg_siegel_in_nachricht(self):
        self.assertIn("xG gedeckt", self._watch([_streak(xg=True)])[0][2])
        self.assertIn("Glück", self._watch([_streak(xg=False)])[0][2])


class TestParseKo(unittest.TestCase):
    def test_iso_offset(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00+00:00").hour, 0)

    def test_zulu(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00Z").minute, 30)

    def test_naiv_als_utc(self):
        self.assertEqual(W._parse_ko("2026-08-02T00:30:00").tzinfo, timezone.utc)

    def test_leer_und_muell(self):
        self.assertIsNone(W._parse_ko(""))
        self.assertIsNone(W._parse_ko(None))
        self.assertIsNone(W._parse_ko("morgen"))


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
        msgs, done = W.build_recap(self._wm(3, 1), self._watched(), "2026-07-04")
        self.assertEqual(msgs, [])
        self.assertEqual(done, [])

    def test_kein_endstand_wartet(self):
        wm = {"groups": {}, "koFixtures": [{"home": "FRA", "away": "PRY", "result": {}}]}
        msgs, done = W.build_recap(wm, self._watched(), "2026-07-05")
        self.assertEqual(msgs, [])


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
        self.assertFalse(W.tg_send("x"))

    def test_fehlende_chat_id_liefert_false(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = False, "tok", ""
        self.assertFalse(W.tg_send("x"))

    def test_skip_telegram_liefert_true(self):
        W.SKIP_TELEGRAM, W.TOKEN, W.CHAT_ID = True, "", ""
        self.assertTrue(W.tg_send("x"))


if __name__ == "__main__":
    unittest.main()
