#!/usr/bin/env python3
"""test_poly_offene_wache.py — die Wache ueber offene Poly-Positionen (20.09.2026).

Vorfall: Toulouse–Le Havre, Anpfiff 19.09. 18:45 UTC, `Under 2.5 Tore`, 5,50 $. Der
Positions-Manager lief um 17:06 UTC, also im eigenen 2-h-Hard-Close-Fenster, verkaufte
nicht und schrieb nichts darueber ins Buch. Die Wette steht bis heute als `placed` da.

Jeder Test hier haengt an einer Bedingung, die man mutieren kann: nimmt man die Stufe
`drin` heraus, nimmt man die Dedup-Kette heraus, oder laesst man `matchDate` als Anpfiff
durchgehen, faellt genau einer.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import poly_offene_wache as W  # noqa: E402

JETZT = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)


def _bet(**kw):
    b = {"betKey": "96-111-Under 2.5 Tore", "home": "Toulouse", "away": "Le Havre",
         "market": "Under 2.5 Tore", "status": "placed", "stake": 5.5, "entryAsk": 0.45,
         "kickoff": "2026-09-19T18:45:00Z", "matchDate": "2026-09-19"}
    b.update(kw)
    return b


class TestStufe(unittest.TestCase):
    def test_der_echte_vorfall_45_minuten_vor_anpfiff_ist_spaet(self):
        self.assertEqual(W.stufe(_bet(), JETZT), "spaet")

    def test_nach_anpfiff_ist_drin(self):
        self.assertEqual(W.stufe(_bet(), JETZT + timedelta(hours=2)), "drin")

    def test_weit_vor_anpfiff_schweigt_die_wache(self):
        self.assertEqual(W.stufe(_bet(), JETZT - timedelta(hours=6)), "")

    def test_nur_offene_wetten(self):
        for st in ("sold", "lost", "won", "closed_manual", "sell_signaled"):
            self.assertEqual(W.stufe(_bet(status=st), JETZT), "", st)

    def test_reines_datum_gilt_nicht_als_anpfiff(self):
        """`matchDate` ist oft nur ein Datum (00:00 UTC). Wer das als Anpfiff nimmt, haelt
        JEDES Abendspiel ab Mitternacht fuer angepfiffen — genau der QAT-SUI-Fehler vom
        13.06. Ohne `kickoff` urteilt die Wache lieber gar nicht."""
        b = _bet()
        b.pop("kickoff")
        self.assertIsNone(W.anpfiff(b))
        self.assertEqual(W.stufe(b, JETZT), "")

    def test_matchdate_mit_uhrzeit_reicht_als_anpfiff(self):
        b = _bet()
        b.pop("kickoff")
        b["matchDate"] = "2026-09-19T18:45:00Z"
        self.assertEqual(W.stufe(b, JETZT), "spaet")

    def test_unlesbarer_anpfiff_wird_nicht_zu_jetzt(self):
        self.assertIsNone(W.anpfiff(_bet(kickoff="demnaechst")))


class TestZeilen(unittest.TestCase):
    def test_der_blinde_fleck_wird_gezaehlt_nicht_verschwiegen(self):
        """Das Shortlist-Buch traegt keinen Anpfiff. Diese Zeilen duerfen nicht als
        'alles in Ordnung' rendern — fehlende Information ist kein harmloser Default."""
        buch = {"bets": [{"betKey": "x", "status": "placed"},
                         {"betKey": "y", "status": "sold"}]}
        self.assertEqual(W.ohne_anpfiff(buch), 1)
        self.assertEqual(W.zeilen_aus_buch(buch, "Shortlist", "s.json", JETZT), [])

    def test_zeile_nennt_dass_kein_versuch_im_buch_steht(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)[0]
        self.assertEqual(z["stufe"], "spaet")
        self.assertIn("kein Verkaufsversuch", z["versuch"])

    def test_zeile_nennt_den_gescheiterten_versuch(self):
        z = W.zeilen_aus_buch({"bets": [_bet(sellVersuche=3,
                                             sellVersuchGrund="Order abgelehnt",
                                             sellVersuchAm="2026-09-19T17:06:00+00:00")]},
                              "Liga", "liga.json", JETZT)[0]
        self.assertIn("3 Versuche", z["versuch"])
        self.assertIn("Order abgelehnt", z["versuch"])


class TestDedup(unittest.TestCase):
    def test_dieselbe_lage_kommt_nicht_zweimal_hintereinander(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)
        neu1, seen = W.neue_zeilen(z, {}, JETZT)
        self.assertEqual(len(neu1), 1)
        neu2, seen = W.neue_zeilen(z, seen, JETZT + timedelta(hours=1))
        self.assertEqual(neu2, [])

    def test_nach_der_wiederholungsfrist_meldet_sie_sich_wieder(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)
        _, seen = W.neue_zeilen(z, {}, JETZT)
        neu, _ = W.neue_zeilen(z, seen, JETZT + timedelta(hours=7))
        self.assertEqual(len(neu), 1)

    def test_der_stufenwechsel_kommt_sofort(self):
        """spaet -> drin ist der Moment, in dem aus einer Warnung ein Schaden wird. Ein
        Dedup, der nur auf betKey laeuft, verschluckt genau diese Nachricht."""
        spaet = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)
        _, seen = W.neue_zeilen(spaet, {}, JETZT)
        spaeter = JETZT + timedelta(hours=1)
        drin = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", spaeter)
        self.assertEqual(drin[0]["stufe"], "drin")
        neu, _ = W.neue_zeilen(drin, seen, spaeter)
        self.assertEqual(len(neu), 1)

    def test_der_dedup_stand_waechst_nicht_endlos(self):
        alt = {"tot|drin": (JETZT - timedelta(hours=100)).isoformat()}
        _, seen = W.neue_zeilen([], alt, JETZT)
        self.assertEqual(seen, {})

    def test_unlesbarer_zeitstempel_blockiert_nicht_fuer_immer(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)
        neu, _ = W.neue_zeilen(z, {"96-111-Under 2.5 Tore|spaet": "kaputt"}, JETZT)
        self.assertEqual(len(neu), 1)


class TestKarte(unittest.TestCase):
    def test_im_spiel_ist_optisch_nicht_zu_uebersehen(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json",
                              JETZT + timedelta(hours=2))[0]
        k = W.karte(z)
        self.assertTrue(k.startswith("🚨🚨"))
        self.assertIn("LIEF INS SPIEL", k)
        self.assertIn("Toulouse v Le Havre", k)

    def test_spaet_ist_eine_warnung_kein_alarm(self):
        z = W.zeilen_aus_buch({"bets": [_bet()]}, "Liga", "liga.json", JETZT)[0]
        k = W.karte(z)
        self.assertTrue(k.startswith("⚠️"))
        self.assertIn("Anpfiff in 0.8 h", k)

    def test_html_aus_dem_buch_wird_entschaerft(self):
        z = W.zeilen_aus_buch({"bets": [_bet(home="<b>A", away="B")]}, "Liga", "l.json", JETZT)[0]
        self.assertNotIn("<b>A", W.karte(z))
        self.assertIn("&lt;b&gt;A", W.karte(z))


class TestWorkflow(unittest.TestCase):
    def test_die_wache_haengt_am_15_minuten_takt_nicht_am_poly_workflow(self):
        """Der Takt ist der halbe Fix: manage-liga-poly.yml behauptet 25 Laeufe am Tag und
        liefert vier bis fuenf. Ein Waechter dort haette dieselbe Luecke wie das Bewachte."""
        bf = (REPO / ".github/workflows/betfair.yml").read_text(encoding="utf-8")
        self.assertIn("poly_offene_wache.py", bf)
        self.assertIn("*/15 * * * *", bf)
        self.assertIn("git add poly_offene_wache_seen.json", bf)
        poly = (REPO / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertNotIn("poly_offene_wache.py", poly)


if __name__ == "__main__":
    unittest.main()
