#!/usr/bin/env python3
"""
05.09.2026 — „ich war so 180 vorne und jetzt haben wir dort Minus, ich check's nicht."

Die Delle war echt (03.09.: +191 -> 05.09.: +60, zwei Tage, -2,0 Standardabweichungen).
Beim Nachrechnen kam ich aber auf **549 bespielbare Plays und -118 $**, waehrend die Datei
**512 und +60 $** sagte — und ich habe daraus voreilig „drei verschiedene Zahlen fuer denselben
Topf" gemacht.

Falsch war meine Rechnung. `cat` wird erst seit dem 24.08. gestempelt und stand in **207 von
563** Zeilen auf null; ich hatte nach dem rohen Feld gefiltert und damit 37 % der Zeilen
ungeprueft als bespielbar durchgewinkt — gesperrte Sportarten eingeschlossen. Die maßgebliche
Regel ist `_row_cat()`: Stempel, sonst aus der Liga abgeleitet.

Zwei Konsequenzen, beide hier festgehalten:
  1. Das Feld wird beim Schreiben nachgetragen, statt sich auf die Disziplin jedes Lesers zu
     verlassen (dieselbe Loesung wie `ledger_mischen()` fuer die Stake-Sportarten am 04.09.).
  2. Niemand darf die Zeilen nach dem rohen `cat` filtern.
"""
import re
import unittest
from pathlib import Path

import poly_shortlist_track as T

BASE = Path(__file__).resolve().parent.parent


class TestRowCat(unittest.TestCase):
    def test_gestempelte_Kategorie_gewinnt(self):
        self.assertEqual(T._row_cat({"cat": "Tennis", "league": "EPL"}), "Tennis")

    def test_ohne_Stempel_aus_der_Liga(self):
        self.assertEqual(T._row_cat({"league": "NBA"}), "US-Sport")
        self.assertEqual(T._row_cat({"cat": None, "league": "UFC 300"}), "Kampfsport")
        self.assertEqual(T._row_cat({"league": "LOL-LCK"}), "E-Sport")

    def test_die_Falle_selbst(self):
        """Eine gesperrte Sportart ohne Stempel: nach rohem `cat` sieht sie bespielbar aus."""
        r = {"cat": None, "league": "NBA", "pnl": -10.0, "result": "loss"}
        self.assertIsNone(r.get("cat"))
        self.assertNotIn(r.get("cat"), {"US-Sport", "Kampfsport"})   # so entstand mein Fehler
        self.assertIn(T._row_cat(r), {"US-Sport", "Kampfsport"})     # so ist es richtig


class TestNachtragen(unittest.TestCase):
    def _prev(self):
        return {"open": {"a|X": {"key": "a", "side": "X", "league": "NBA"}},
                "settled": [{"key": "b", "side": "Y", "league": "UFC", "cat": None,
                             "pnl": -10.0, "stake": 10.0, "result": "loss"},
                            {"key": "c", "side": "Z", "league": "EPL", "cat": "Fußball",
                             "pnl": 8.0, "stake": 10.0, "result": "win"}],
                "blockedCats": ["US-Sport", "Kampfsport"]}

    def test_fehlende_Kategorien_werden_nachgetragen(self):
        out = T.update_track(self._prev(), {"plays": []}, {}, {})
        self.assertEqual(out["katNachgetragen"], 2)
        self.assertEqual(out["open"]["a|X"]["cat"], "US-Sport")
        self.assertEqual(out["settled"][0]["cat"], "Kampfsport")

    def test_bestehende_Stempel_bleiben(self):
        out = T.update_track(self._prev(), {"plays": []}, {}, {})
        self.assertEqual(out["settled"][1]["cat"], "Fußball")

    def test_danach_traegt_jede_Zeile_ihre_Sportart(self):
        out = T.update_track(self._prev(), {"plays": []}, {}, {})
        self.assertEqual([r for r in out["settled"] if not r.get("cat")], [])
        self.assertEqual([r for r in out["open"].values() if not r.get("cat")], [])

    def test_die_gesperrte_Zeile_zaehlt_danach_als_gesperrt(self):
        """Der eigentliche Schaden: ohne Nachtrag landet ein UFC-Verlust im bespielbaren Topf."""
        out = T.update_track(self._prev(), {"plays": []}, {}, {})
        self.assertEqual(out["agg"]["bettable"]["n"], 1)
        self.assertEqual(out["agg"]["blocked"]["n"], 1)
        self.assertEqual(out["agg"]["bettable"]["pnl"], 8.0)


class TestNiemandLiestRohesCat(unittest.TestCase):
    def test_kein_Modul_filtert_nach_dem_rohen_Feld(self):
        """`x.get("cat") in/not in blocked` ist der Fehler. Wer filtert, nimmt `_row_cat`."""
        muster = re.compile(r"""\.get\(\s*["']cat["']\s*\)\s*(?:not\s+)?in\b""")
        fehler = []
        for p in sorted(BASE.glob("*.py")):
            for i, z in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if z.lstrip().startswith("#"):
                    continue
                if muster.search(z):
                    fehler.append(f"{p.name}:{i}")
        self.assertEqual(fehler, [], "nach rohem cat gefiltert: " + ", ".join(fehler))

    def test_das_Muster_wuerde_erkannt(self):
        """Gegenbeweis: der Waechter faengt seinen eigenen Fall."""
        muster = re.compile(r"""\.get\(\s*["']cat["']\s*\)\s*(?:not\s+)?in\b""")
        self.assertTrue(muster.search('x = [r for r in s if r.get("cat") not in blocked]'))
        self.assertTrue(muster.search("if r.get('cat') in bl:"))
        self.assertFalse(muster.search('c = _row_cat(r)'))


if __name__ == "__main__":
    unittest.main()
