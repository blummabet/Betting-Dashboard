#!/usr/bin/env python3
"""02.09.2026 — Lucas: „Haben diese Tik Tok irgendwie die wir generieren auch da ein Speicher
Problem / Und die Event Seiten, kann man die vergangenen die aelter wie eine Woche sind loeschen?"

Ja beim einen, nein beim anderen — und der Unterschied ist der Punkt dieser Tests.

  · TikTok: 145 MB im Arbeitsbaum, alles in git, KEINE Aufraeum-Logik, ~2,2 MB/Tag Zuwachs.
  · Event-SEITEN: 120 Stueck, zusammen 2,9 MB. Die zu loeschen braechte nichts und kostet genau
    den SEO-Bestand, den Lucas behalten will. Teuer ist `matches/data` (1.373 JSONs, 65 MB) —
    und davon haben 832 weder eine Seite noch einen Index-Eintrag.

Diese Tests nageln fest, dass die Regel nur wegwirft, was nachweislich niemand anfasst. Ein
Loeschskript, das im Zweifel zuschlaegt, ist gefaehrlicher als ein volles Repo.
"""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import archiv_aufraeumen as A

HEUTE = date(2026, 9, 2)


class _Baum(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "matches", "data"))
        for o in A.KARTEN_ORDNER:
            os.makedirs(os.path.join(self.tmp, o))

    def _karte(self, ordner, name):
        p = os.path.join(self.tmp, ordner, name)
        open(p, "w").write("x")
        return p

    def _daten(self, slug):
        open(os.path.join(self.tmp, "matches", "data", slug + ".json"), "w").write("{}")

    def _seite(self, slug):
        open(os.path.join(self.tmp, "matches", slug + ".html"), "w").write("<html>")

    def _index(self, name, slugs):
        json.dump({"slugs": slugs}, open(os.path.join(self.tmp, "matches", name), "w"))


class KartenTest(_Baum):
    def test_alte_karten_fliegen_raus(self):
        self._karte("daily-tiktok", "2026-06-02_story_hook.png")
        self.assertEqual(A.alte_karten(HEUTE, self.tmp), ["daily-tiktok/2026-06-02_story_hook.png"])

    def test_frische_karten_bleiben(self):
        self._karte("liga_daily-tiktok", "2026-09-02_moneymap_36006990.png")
        self._karte("liga_daily-tiktok", "2026-08-25_review_1_2.png")   # 8 Tage — im Fenster
        self.assertEqual(A.alte_karten(HEUTE, self.tmp), [])

    def test_kompaktes_datumsformat_wird_erkannt(self):
        """`track_record_20260901_1427.png` — ohne Bindestriche."""
        self._karte("mls_daily-tiktok", "track_record_20260718_1427.png")
        self.assertEqual(len(A.alte_karten(HEUTE, self.tmp)), 1)

    def test_ohne_datum_wird_NICHTS_geloescht(self):
        """Ein unlesbarer Name ist kein Beleg fuers Alter. Im Zweifel bleibt die Datei."""
        self._karte("daily-tiktok", "irgendwas.png")
        self._karte("daily-tiktok", "README.md")
        self.assertEqual(A.alte_karten(HEUTE, self.tmp), [])

    def test_unsinniges_datum_kippt_nicht(self):
        self._karte("daily-tiktok", "2026-13-45_kaputt.png")
        self.assertEqual(A.alte_karten(HEUTE, self.tmp), [])

    def test_fehlender_ordner_ist_kein_fehler(self):
        import shutil
        shutil.rmtree(os.path.join(self.tmp, "daily-tiktok"))
        self.assertEqual(A.alte_karten(HEUTE, self.tmp), [])


class MatchDatenTest(_Baum):
    def test_verwaiste_alte_daten_fliegen_raus(self):
        self._daten("aberdeen-vs-kilmarnock-2026-08-01")
        self._index("wm-index.json", [])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp),
                         [os.path.join("matches", "data", "aberdeen-vs-kilmarnock-2026-08-01.json")])

    def test_daten_mit_event_seite_bleiben(self):
        """Der SEO-Bestand: existiert die Seite, bleibt ihre Datei — egal wie alt."""
        self._daten("alaves-vs-rayo-2026-05-23")
        self._seite("alaves-vs-rayo-2026-05-23")
        self._index("wm-index.json", [])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp), [])

    def test_daten_im_index_bleiben(self):
        self._daten("ipswich-vs-liverpool-2026-08-01")
        self._index("liga-index.json", ["ipswich-vs-liverpool-2026-08-01"])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp), [])

    def test_jeder_index_zaehlt_nicht_nur_einer(self):
        self._daten("x-vs-y-2026-08-01")
        self._index("wm-index.json", [])
        self._index("mls-index.json", ["x-vs-y-2026-08-01"])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp), [])

    def test_frische_daten_bleiben_auch_ohne_index(self):
        """Die Sicherung gegen einen Generator-Aussetzer: faellt ein Index einmal leer aus,
        verschwinden nicht sofort die Daten von gestern."""
        self._daten("heute-vs-morgen-2026-08-30")   # 3 Tage alt
        self._index("wm-index.json", [])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp), [])

    def test_daten_ohne_datum_im_slug_bleiben(self):
        self._daten("irgendein-spiel-ohne-datum")
        self._index("wm-index.json", [])
        self.assertEqual(A.verwaiste_matchdaten(HEUTE, self.tmp), [])

    def test_kaputter_index_stoppt_das_loeschen_ganz(self):
        """Lieber nichts loeschen als anhand einer halben Liste entscheiden."""
        self._daten("x-vs-y-2026-08-01")
        open(os.path.join(self.tmp, "matches", "wm-index.json"), "w").write("{kaputt")
        with self.assertRaises(Exception):
            A.verwaiste_matchdaten(HEUTE, self.tmp)


class EchterBestandTest(unittest.TestCase):
    """Gegenprobe am echten Repo: die Regel darf keine Event-Seite und nichts aus einem Index treffen."""

    def test_keine_datei_mit_seite_oder_index_wird_angefasst(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        raus = set(A.verwaiste_matchdaten(HEUTE, repo))
        if not raus:
            self.skipTest("nichts zu loeschen im aktuellen Bestand")
        seiten = {f[:-5] for f in os.listdir(os.path.join(repo, "matches")) if f.endswith(".html")}
        idx = A._index_slugs(repo)
        for p in raus:
            slug = os.path.basename(p)[:-5]
            self.assertNotIn(slug, seiten, f"{slug} hat eine Event-Seite")
            self.assertNotIn(slug, idx, f"{slug} steht in einem Index")

    def test_event_seiten_selbst_stehen_nie_auf_der_liste(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        raus = A.alte_karten(HEUTE, repo) + A.verwaiste_matchdaten(HEUTE, repo)
        self.assertFalse([p for p in raus if p.endswith(".html") and p.startswith("matches/")],
                         "Die Regel wuerde eine Event-Seite loeschen — das ist der SEO-Bestand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
