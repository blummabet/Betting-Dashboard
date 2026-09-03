#!/usr/bin/env python3
"""03.09.2026 — Lucas: „na dann schau dir die 2 an" (die beiden offenen Punkte aus dem
Uebersicht-Checkup).

BEFUND 1 — die Leiste mass nach anderen Regeln als das Register direkt darunter.
`agg.byConv` aggregiert den GANZEN Bestand: 500 abgerechnete Plays ueber mehrere
Engine-Versionen (`ev`: 70x 2026-09-01, 76x 2026-08-29b, 8x 2026-08-29, 346 ohne Stempel).
Die Kopfzeile warb mit „Beste Stufe Conv 7 · +2.5% ROI · n149", waehrend Ebene 1 fuer dieselbe
Stufe `4/30` zeigt und sagt: „Plays aelterer Versionen zaehlen nicht fuer eine Freigabe".
Dazu nimmt `_best_bucket` das MAXIMUM ueber ~10 Buckets und zeigte einen Punktschaetzer — ein
Maximum ueber viele Buckets ist selbst eine Auswahl.

BEFUND 2 — die Platzhalter-Nullen im CLV.
`clvPP` steht auf JEDEM Pick: angelegt mit 0.0, gefuellt erst mit einer Closing-Linie. Gemessen
an den Pick-Dateien: 122 von 264 Liga-Picks tragen clvPP==0, und davon hat KEIN EINZIGER
`clvResolved`. Der Ledger reichte das Flag nie durch, der Puls zaehlte die Nullen deshalb voll:
sie zogen den Ø CLV Richtung null (die Zahl sah BESSER aus als sie ist) und sassen im Nenner von
„schlaegt Close", wo sie per Konstruktion nie zaehlen koennen. Im Fenster: Ø −2,62pp / 13,3%
gegen die belegten Ø −3,41pp / 17,4%. Beide Zahlen falsch, je eine pro Richtung.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_dashboard_pulse as P
import freigabe as F
import poly_shortlist_track as T


def _play(ev="2026-09-01", conv=7, rendite=0.1, signals=("money",), stake=10.0):
    return {"ev": ev, "conv": conv, "stake": stake, "pnl": rendite * stake,
            "signals": list(signals), "result": "win" if rendite > 0 else "loss"}


class EngineFilterTest(unittest.TestCase):
    def test_nur_die_aktuelle_engine_zaehlt(self):
        # `settled` ist chronologisch — das Neue steht HINTEN, und aktuelle_engine liest die
        # juengsten Zeilen. Ein Fixture mit der aktuellen Version vorn waere kein Fixture,
        # sondern eine andere Datei.
        track = {"settled": [_play(ev="2026-08-29b")] * 100 + [_play(ev="2026-09-01")] * 40}
        zeilen, stempel = P._aktuelle_zeilen(track)
        self.assertEqual(stempel, "2026-09-01")
        self.assertEqual(len(zeilen), 40)

    def test_ohne_stempel_wird_nicht_gefiltert(self):
        """Wie im Register: eine alte Datei ohne Stempel soll die Leiste nicht leeren."""
        track = {"settled": [{"conv": 7, "stake": 10.0, "pnl": 1.0}] * 5}
        zeilen, stempel = P._aktuelle_zeilen(track)
        self.assertIsNone(stempel)
        self.assertEqual(len(zeilen), 5)

    def test_dieselbe_regel_wie_das_register(self):
        track = {"settled": [_play(ev="2026-08-29b")] * 100 + [_play(ev="2026-09-01")] * 40}
        self.assertEqual(P._aktuelle_zeilen(track)[1], F.aktuelle_engine(track))

    def test_settled_als_dict_wird_auch_verstanden(self):
        track = {"settled": {"a": _play(), "b": _play(ev="alt")}}
        zeilen, _ = P._aktuelle_zeilen(track)
        self.assertEqual(len(zeilen), 1)


class BucketTest(unittest.TestCase):
    def test_conv_buckets_wie_im_tracker(self):
        """Gegenprobe gegen poly_shortlist_track.aggregate — sonst driften die beiden Flaechen
        auseinander und niemand merkt es."""
        rows = [_play(conv=7)] * 25 + [_play(conv=5, rendite=-0.2)] * 10
        meins = P._bucket_renditen(rows, "conv")
        tracker = T.aggregate(rows).get("byConv") or {}
        self.assertEqual({k: len(v) for k, v in meins.items()},
                         {k: v["n"] for k, v in tracker.items()})

    def test_ein_play_zaehlt_in_mehreren_signal_buckets(self):
        rows = [_play(signals=("money", "sharp"))] * 5
        b = P._bucket_renditen(rows, "signal")
        self.assertEqual(len(b["money"]), 5)
        self.assertEqual(len(b["sharp"]), 5)

    def test_ohne_einsatz_keine_rendite(self):
        """Eine Zeile ohne stake laesst sich nicht in eine Rendite umrechnen — sie faellt raus,
        statt als 0 mitzulaufen."""
        self.assertIsNone(P._rendite({"pnl": 5.0, "stake": 0}))
        self.assertEqual(P._bucket_renditen([{"conv": 7, "pnl": 5.0, "stake": 0}], "conv"), {})


class BesteStufeTest(unittest.TestCase):
    def test_unter_der_mindeststichprobe_gibt_es_keine_beste_stufe(self):
        self.assertIsNone(P._best_bucket({"7": [0.5] * (P.STRIP_MIN_N - 1)}))

    def test_negativer_roi_gewinnt_nie(self):
        self.assertIsNone(P._best_bucket({"7": [-0.1] * 40}))

    def test_belegt_nur_wenn_die_untergrenze_ueber_null_liegt(self):
        eng = P._best_bucket({"7": [0.30, 0.32, 0.28] * 20})      # n=60, eng gestreut
        self.assertTrue(eng["belegt"])
        self.assertGreater(eng["roiUgPct"], 0)
        # Der Fall, fuer den die Untergrenze da ist: knapp positiver Schnitt, getragen von ein
        # paar Aussenseitern. 36 Verlierer, 4 Treffer zu 11.0 → Mittel +0,1, Streuung riesig.
        weit = P._best_bucket({"7": [-1.0] * 36 + [10.0] * 4})
        self.assertGreater(weit["roiPct"], 0)
        self.assertFalse(weit["belegt"])
        self.assertLess(weit["roiUgPct"], 0)

    def test_zwischen_mindeststichprobe_und_untergrenze_steht_nicht_belegt(self):
        """STRIP_MIN_N (20) liegt unter UG_MIN_N (30) — dazwischen gibt es eine Zeile, aber
        keinen Beleg. Sie verschwindet nicht, sie wird gekennzeichnet."""
        b = P._best_bucket({"7": [0.2] * 25})
        self.assertEqual(b["n"], 25)
        self.assertIsNone(b["roiUgPct"])
        self.assertFalse(b["belegt"])

    def test_der_hoechste_roi_gewinnt(self):
        b = P._best_bucket({"5": [0.05] * 40, "6": [0.20] * 40})
        self.assertEqual(b["key"], "6")


class ClvNullenTest(unittest.TestCase):
    """Der Puls darf eine Null nur zaehlen, wenn sie gemessen wurde."""

    def _fenster(self, rows):
        return [r["clvPP"] for r in rows
                if isinstance(r.get("clvPP"), (int, float)) and r.get("clvResolved")]

    def test_die_regel_steht_so_im_puls(self):
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "build_dashboard_pulse.py"), encoding="utf-8").read()
        self.assertIn('r.get("clvResolved")', quelle,
                      "Der Puls zaehlt CLV-Werte wieder ohne Beleg")

    def test_platzhalter_nullen_zaehlen_nicht(self):
        rows = [{"clvPP": 0.0}, {"clvPP": 0.0}, {"clvPP": -3.4, "clvResolved": True}]
        self.assertEqual(self._fenster(rows), [-3.4])

    def test_eine_GEMESSENE_null_zaehlt_sehr_wohl(self):
        rows = [{"clvPP": 0.0, "clvResolved": True}]
        self.assertEqual(self._fenster(rows), [0.0])

    def test_der_ledger_reicht_das_flag_durch(self):
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "build_signal_ledger.py"), encoding="utf-8").read()
        self.assertIn('"clvResolved"', quelle,
                      "Ohne das Flag im Ledger kann der Puls die Unterscheidung nie treffen")

    def test_dieselbe_regel_wie_compute_clv_summary(self):
        """Dort steht sie seit jeher: „kein Closing erfasst → zaehlt nur in die Abdeckung"."""
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "compute_clv_summary.py"), encoding="utf-8").read()
        self.assertIn('not p.get("clvResolved")', quelle,
                      "Die Referenz-Regel hat sich geaendert — dann muss der Puls nachziehen")


if __name__ == "__main__":
    unittest.main(verbosity=2)
