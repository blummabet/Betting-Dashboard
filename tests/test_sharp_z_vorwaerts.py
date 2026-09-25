"""25.09.2026 — Vorwaertsmessung z=1,282 vs 1,645 (sharp_z_vorwaerts.py).

Jede Sperre steht gegen eine bekannte Selbsttaeuschung: Kohorten einfrieren (sonst misst man,
wer spaeter gut aussah), nur Tage NACH der Anmeldung (sonst Rueckschau), Signatur (sonst
verschiebt man die Grenze), und kein Urteil vor dem Ziel (sonst hoert man auf, wenn es passt).
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sharp_z_vorwaerts as V

T0 = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
# 60 % aus 60: Wilson-UG bei 1,645 < 0,5, bei 1,282 > 0,5 -> Band.
BAND = {"n": 60, "wins": 36, "clvSumPP": 0.0}
STRENG = {"n": 100, "wins": 70, "clvSumPP": 0.0}
NICHTS = {"n": 20, "wins": 8, "clvSumPP": 0.0}


def _tag(n, gewinn, einsatz):
    return [n, 0.0, n // 2, 0.0, gewinn, einsatz, n]


class TestKohorten(unittest.TestCase):
    def test_zuordnung(self):
        k = V.kohorten({"a": BAND, "b": STRENG, "c": NICHTS})
        self.assertEqual(k, {"streng": ["b"], "band": ["a"]})

    def test_anmeldung_wird_nie_ueberschrieben(self):
        reg = V.anmelden({}, {"a": BAND}, now=T0)
        reg2 = V.anmelden(reg, {"a": STRENG, "x": BAND}, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(reg2["anmeldung"], reg["anmeldung"])


class TestMessung(unittest.TestCase):
    def _reg(self):
        return V.anmelden({}, {"a": BAND, "b": STRENG, "c": NICHTS}, now=T0)

    def test_nur_tage_nach_der_anmeldung(self):
        a = dict(BAND, tage={"2026-09-24": _tag(10, 50, 100),     # davor
                             "2026-09-25": _tag(10, 50, 100),     # Anmeldetag: zaehlt nicht
                             "2026-09-26": _tag(4, 10, 40)},
                 tageNachtrag={"2026-09-27": [5, 999, 1]})         # rekonstruiert: zaehlt nie
        st = V.messen(self._reg(), {"a": a, "b": STRENG, "c": NICHTS}, heute="2026-09-27")
        self.assertEqual(st["band"]["n"], 4)
        self.assertEqual(st["band"]["nGeld"], 4)
        self.assertAlmostEqual(st["band"]["roi"], 0.25)

    def test_aufsteiger_bleibt_in_seiner_kohorte(self):
        """c war bei der Anmeldung nichts — spaeter scharf, zaehlt trotzdem zur Basis."""
        c = dict(STRENG, tage={"2026-09-26": _tag(3, 3, 3)})
        st = V.messen(self._reg(), {"a": BAND, "b": STRENG, "c": c}, heute="2026-09-27")
        self.assertEqual(st["basis"]["n"], 3)
        self.assertEqual(st["streng"]["n"], 0)

    def test_signaturbruch_misst_nichts(self):
        reg = self._reg()
        reg["anmeldung"]["signatur"] = "etwas anderes"
        self.assertEqual(V.messen(reg, {"a": BAND})["status"], "ungueltig")

    def test_kein_urteil_vor_dem_ziel(self):
        a = dict(BAND, tage={"2026-09-26": _tag(V.ZIEL_N - 1, 100, 100)})
        st = V.messen(self._reg(), {"a": a, "b": STRENG, "c": NICHTS}, heute="2026-09-27")
        self.assertEqual(st["status"], "sammelt")

    def test_urteil_nach_kriterium(self):
        tag = "2026-09-26"
        a = dict(BAND, tage={tag: _tag(V.ZIEL_N, 10, 100)})       # +10 %
        b = dict(STRENG, tage={tag: _tag(50, 12, 100)})           # +12 %
        c = dict(NICHTS, tage={tag: _tag(50, -5, 100)})           # -5 %
        st = V.messen(self._reg(), {"a": a, "b": b, "c": c}, heute="2026-09-27")
        self.assertEqual(st["status"], "locker")
        b2 = dict(STRENG, tage={tag: _tag(50, 20, 100)})          # +20 % -> Band 10pp dahinter
        st = V.messen(self._reg(), {"a": a, "b": b2, "c": c}, heute="2026-09-27")
        self.assertEqual(st["status"], "streng")


class TestMessungenZaehler(unittest.TestCase):
    def test_zaehler(self):
        import json, tempfile, os
        import messungen as M
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(M.zaehler_sharp_z(d), 0)
            with open(os.path.join(d, "sharp_z_vorwaerts.json"), "w") as f:
                json.dump({"stand": {"status": "sammelt", "band": {"nGeld": 17}}}, f)
            self.assertEqual(M.zaehler_sharp_z(d), 17)
            with open(os.path.join(d, "sharp_z_vorwaerts.json"), "w") as f:
                json.dump({"stand": {"status": "ungueltig"}}, f)
            self.assertIsNone(M.zaehler_sharp_z(d))


if __name__ == "__main__":
    unittest.main()
