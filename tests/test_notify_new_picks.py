#!/usr/bin/env python3
"""test_notify_new_picks.py — Intraday-„Neuer Pick"-Noti (03.07.2026, Lucas).

Friert die Anti-Doppel-Send-Logik ein: der Digest ist Erst-Ankündiger, die Noti meldet nur
Nachzügler. Kein Send vor dem heutigen Digest; nur echte Deltas danach ([[pick_announce_state]])."""
import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _wm():
    return {
        "groups": {
            "A": {
                "teams": [
                    {"id": "MEX", "name": "Mexiko", "flag": "🇲🇽"},
                    {"id": "ZAF", "name": "Südafrika", "flag": "🇿🇦"},
                ],
                "fixtures": [
                    {"home": "MEX", "away": "ZAF", "matchday": 1,
                     "kickoff": "2099-01-01T20:00:00Z"},
                ],
            }
        },
        "koFixtures": [],
        "picks": {
            "A-1-MEX-ZAF": [
                {"verdict": "BET", "market": "Heimsieg", "convictionScore": 8},
                {"verdict": "NOBET", "market": "Über 2.5 Tore"},         # nie ankündigen
                {"verdict": "ABWÄGEN", "market": "Beide Teams treffen — Ja",
                 "trackingExcluded": True},                              # excluded → nie
            ]
        },
    }


class TestIterPickUnits(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state as S
        importlib.reload(S)
        self.S = S

    def test_nur_bet_und_abwaegen_ohne_excluded(self):
        units = list(self.S.iter_pick_units(_wm()))
        markets = {u["market"] for u in units}
        self.assertEqual(markets, {"Heimsieg"})   # NOBET + trackingExcluded raus

    def test_finished_spiel_raus(self):
        wm = _wm()
        wm["groups"]["A"]["fixtures"][0]["result"] = {"status": "FT"}
        self.assertEqual(list(self.S.iter_pick_units(wm)), [])


class TestNotifyFlow(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        os.environ["SKIP_TELEGRAM"] = "true"
        for m in ("cocobet_dataset", "pick_announce_state", "notify_new_picks"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
        import cocobet_dataset  # noqa
        importlib.reload(sys.modules["cocobet_dataset"])
        import pick_announce_state as S
        import notify_new_picks as N
        importlib.reload(S); importlib.reload(N)
        self.S, self.N = S, N
        # isolierte State-Datei + WM-Datei
        self._state = Path("/tmp/_test_announce_state.json")
        self._wmfile = Path("/tmp/_test_wm.json")
        if self._state.exists():
            self._state.unlink()
        S.STATE_FILE = self._state
        N.WM_FILE = self._wmfile
        self._write(_wm())

    def tearDown(self):
        for p in (self._state, self._wmfile):
            if p.exists():
                p.unlink()

    def _write(self, wm):
        import json
        self._wmfile.write_text(json.dumps(wm), encoding="utf-8")

    def test_vor_digest_kein_send_nur_basis(self):
        self.N.main()
        st = self.S.load()
        # Basis gesetzt, aber lastDigestDate bleibt None → es wurde nicht als „gesendet" gewertet
        self.assertEqual(len(st["announced"]), 1)
        self.assertIsNone(st["lastDigestDate"])

    def test_nach_digest_nachzuegler_wird_erkannt(self):
        import json
        # Digest simulieren: Slate markieren + lastDigestDate=heute
        st = self.S.load()
        self.S.mark(st, self.S.current_pick_ids(json.loads(self._wmfile.read_text())))
        st["lastDigestDate"] = datetime.now(timezone.utc).date().isoformat()
        self.S.save(st)
        # nichts Neues
        self.N.main()
        # Nachzügler einschleusen
        wm = _wm()
        wm["picks"]["A-1-MEX-ZAF"].append(
            {"verdict": "BET", "market": "Über 3.5 Tore", "convictionScore": 8})
        self._write(wm)
        self.N.main()
        st = self.S.load()
        self.assertIn("A-1-MEX-ZAF|Über 3.5 Tore", st["announced"])

    def test_spaeteres_spiel_wird_vermerkt_aber_NICHT_gesendet(self):
        """⭐ 14.09.2026: der Fall „AS Roma – Inter · 18:00", fuenf Tage im Voraus im
        Public-Channel. Er muss als bekannt vermerkt werden (sonst bietet ihn jeder Lauf erneut
        an), darf aber nicht rausgehen — die Morning-Card kuendigt ihn an seinem Spieltag an.
        Das Fixture dieser Datei steht auf 2099, liegt also sicher nicht im heutigen Slate."""
        import json
        st = self.S.load()
        self.S.mark(st, self.S.current_pick_ids(json.loads(self._wmfile.read_text())))
        st["lastDigestDate"] = datetime.now(timezone.utc).date().isoformat()
        self.S.save(st)
        wm = _wm()
        wm["picks"]["A-1-MEX-ZAF"].append(
            {"verdict": "BET", "market": "Über 3.5 Tore", "convictionScore": 8})
        self._write(wm)
        self.N.main()
        st = self.S.load()
        pid = "A-1-MEX-ZAF|Über 3.5 Tore"
        self.assertIn(pid, st["announced"], "muss als bekannt vermerkt sein")
        self.assertNotIn(pid, st.get("gesendet") or {},
                         "ein Spiel in ferner Zukunft darf nicht als gesendet gebucht werden")

    def test_message_ist_tiktok_safe(self):
        units = list(self.S.iter_pick_units(_wm()))
        msg = self.N.build_message(units)
        self.assertIn("Neuer Pick", msg)
        self.assertIn("Mexiko", msg)
        self.assertNotIn("€", msg)
        self.assertNotIn("@", msg)   # keine Quoten-Notation


if __name__ == "__main__":
    unittest.main()


# ── 10.09.2026: der img-Bug, gegen den es seit dem 25.07. tg_safe gibt ───────────────────
def test_klub_logo_wird_nie_als_img_tag_gesendet():
    """🔴 `homeFlag` ist bei liga/mls ein komplettes <img src="…">-Tag (fuers Dashboard).
    Telegram erlaubt im HTML-Modus kein <img> und antwortet mit HTTP 400 — die Nachricht
    scheitert LAUTLOS. `telegram_wm`, `detect_wm_sharp_moves` und `telegram_streak_watch`
    benutzen `safe_flag` seit dem 25.07.; dieser Sender nie. Der Cards-Public-Push hat damit
    fuer die Klub-Datensaetze vermutlich nie zugestellt."""
    import notify_new_picks as N
    u = [{"id": "x", "homeFlag": '<img src="https://media.api-sports.io/football/teams/35.png">',
          "homeName": "Bournemouth", "awayName": "Brentford", "market": "Über 2.5 Tore",
          "verdict": "ABWÄGEN", "convictionScore": 5}]
    t = N.build_message(u)
    assert "<img" not in t, "ein <img>-Tag laesst Telegram die ganze Nachricht ablehnen"
    assert "⚽" in t, "statt des Logos steht das neutrale Fallback-Emoji"


def test_echte_laenderflagge_bleibt_stehen():
    """Die WM-Flaggen sind echte Emoji und duerfen nicht zu ⚽ werden."""
    import notify_new_picks as N
    u = [{"id": "x", "homeFlag": "🇪🇸", "homeName": "Spanien", "awayName": "Italien",
          "market": "Heimsieg", "verdict": "BET", "convictionScore": 8}]
    assert "🇪🇸" in N.build_message(u)


class NurHeutigeSpieleUndNieOhneDatum(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „aber sorry die Spiele sind doch nicht heute").

    In einer Public-Nachricht standen nebeneinander:

        ⚽ Inter – Udinese · 20:45      (heute)
        ⚽ AS Roma – Inter · 18:00      (19.09., fünf Tage später)

    Beide unter „🆕 2 neue Picks" und über „Kam nach dem Morgen-Update rein". Eine nackte
    Uhrzeit liest sich als heute Abend — im öffentlichen Kanal.

    Zwei Ursachen, beide hier festgehalten: die Zeitzeile kannte kein Datum, und die Auswahl
    kein „heute" — obwohl der Zweck dieser Noti laut ihrer eigenen Beschreibung genau die
    Nachzügler für HEUTE sind.
    """

    JETZT = datetime(2026, 9, 14, 17, 27, tzinfo=timezone.utc)

    def setUp(self):
        os.environ["COCOBET_DATASET"] = "liga"
        import notify_new_picks
        importlib.reload(notify_new_picks)
        self.N = notify_new_picks

    def _u(self, ident, ko):
        return {"id": ident, "kickoff": ko}

    def test_spiel_von_heute_kommt_durch(self):
        u = [self._u("a", "2026-09-14T18:45:00Z")]
        self.assertEqual([x["id"] for x in self.N.heutiger_slate(u, self.JETZT)], ["a"])

    def test_spiel_in_fuenf_tagen_faellt_raus(self):
        u = [self._u("b", "2026-09-19T16:00:00Z")]
        self.assertEqual(self.N.heutiger_slate(u, self.JETZT), [])

    def test_nachtspiel_gehoert_noch_zu_heute(self):
        """00:30 UTC am Folgetag ist der heutige Abend — dasselbe Fenster wie die Morning-Card."""
        u = [self._u("c", "2026-09-15T00:30:00Z")]
        self.assertEqual([x["id"] for x in self.N.heutiger_slate(u, self.JETZT)], ["c"])

    def test_ohne_anpfiff_wird_nicht_geraten(self):
        self.assertEqual(self.N.heutiger_slate([self._u("x", None)], self.JETZT), [])

    def test_heutiges_spiel_zeigt_nur_die_uhrzeit(self):
        t = self.N._kickoff_wien(self._u("a", "2026-09-14T18:45:00Z"), self.JETZT)
        self.assertEqual(t.strip(), "· 20:45")

    def test_spaeteres_spiel_traegt_sein_datum(self):
        """⭐ Der eigentliche Fund: „18:00" ohne Datum war die Irreführung."""
        t = self.N._kickoff_wien(self._u("b", "2026-09-19T16:00:00Z"), self.JETZT)
        self.assertIn("19.09.", t)
        self.assertIn("Sa", t)

    def test_unlesbarer_anpfiff_erfindet_nichts(self):
        self.assertEqual(self.N._kickoff_wien({"kickoff": "kaputt"}, self.JETZT), "")
