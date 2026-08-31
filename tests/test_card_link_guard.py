"""
test_card_link_guard.py — 31.08.2026

Der Terminal-Kartenlink stand fünf Tage auf „0 verlinkt" und sah dabei aus wie ein ruhiger Tag
ohne Top-5-Spiele. Dieser Guard ist die Antwort darauf: 0 von 0 ist ein ruhiger Tag, 0 von N ist
ein Bruch. Die Datei wird über `_lazy` gelesen — der Test schiebt sie unter, damit er nicht von
der echten Datei im Repo abhängt (sonst kippt er, sobald der Bot schreibt,
[[feedback_tests_no_live_data_thresholds]]).
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import wm_data_integrity as WDI  # noqa: E402

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
FNAME = "betfair_card_link.json"


class TestCardLinkGuard(unittest.TestCase):
    def _run(self, datei, unlesbar=False):
        echt_lazy, echt_failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: (datei if name == FNAME else echt_lazy(name))
        if unlesbar:
            WDI._LAZY_FAILED.add(FNAME)
        else:
            WDI._LAZY_FAILED.discard(FNAME)
        try:
            checks = WDI.run_checks({"groups": {}}, {}, {}, {}, now=NOW)
        finally:
            WDI._lazy = echt_lazy
            WDI._LAZY_FAILED.clear()
            WDI._LAZY_FAILED.update(echt_failed)
        return next(c for c in checks if c["id"] == "card_link_alive")

    def test_kandidaten_ohne_link_ist_ein_fehler(self):
        c = self._run({"nGames": 12, "nCandidates": 12, "nLinked": 0})
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "error")

    def test_ruhiger_tag_ist_kein_fehler(self):
        """Keine Cards an diesem Tag → 0 verlinkt ist die Wahrheit, kein Bruch."""
        c = self._run({"nGames": 12, "nCandidates": 0, "nLinked": 0})
        self.assertTrue(c["ok"])

    def test_verlinkt_ist_gruen(self):
        c = self._run({"nGames": 12, "nCandidates": 12, "nLinked": 4})
        self.assertTrue(c["ok"])

    def test_unlesbare_datei_meldet_unbekannt_statt_gruen(self):
        c = self._run({}, unlesbar=True)
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")

    def test_alte_datei_ohne_kandidatenzahl_meldet_unbekannt(self):
        """Vor dem 31.08. stand nCandidates nicht in der Datei — dann ist die Aussage offen."""
        c = self._run({"nGames": 12, "nLinked": 0})
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")


class TestLiveScanGuard(unittest.TestCase):
    """31.08.2026 — sechs Tage Live-Scan bei 8-29% Abdeckung, ohne dass etwas rot wurde.

    Geprüft wird die Gesundheits-Datei, nicht die Daten: `poly_money_broad_live.json` steht auch
    dann still, wenn kein Spiel läuft. `health/poly-live-scan.json` schreibt run_health bei
    JEDEM Lauf — sie beantwortet „ist der Job gestartet", und nur das ist hier die Frage.
    """
    FNAME = "health/poly-live-scan.json"

    def _run(self, datei, unlesbar=False):
        echt_lazy, echt_failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: (datei if name == self.FNAME else echt_lazy(name))
        if unlesbar:
            WDI._LAZY_FAILED.add(self.FNAME)
        else:
            WDI._LAZY_FAILED.discard(self.FNAME)
        try:
            checks = WDI.run_checks({"groups": {}}, {}, {}, {}, now=NOW)
        finally:
            WDI._lazy = echt_lazy
            WDI._LAZY_FAILED.clear()
            WDI._LAZY_FAILED.update(echt_failed)
        return next(c for c in checks if c["id"] == "live_scan_laeuft")

    def _vor(self, minuten):
        return {"updatedAt": (NOW - timedelta(minutes=minuten)).isoformat()}

    def test_frischer_lauf_ist_gruen(self):
        self.assertTrue(self._run(self._vor(12))["ok"])

    def test_eine_verpasste_runde_alarmiert_noch_nicht(self):
        """15-Min-Takt: ein, zwei ausgefallene Läufe sind Rauschen, keine Störung."""
        self.assertTrue(self._run(self._vor(45))["ok"])

    def test_stundenlanges_schweigen_ist_ein_fehler(self):
        c = self._run(self._vor(6 * 60))
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "error")
        self.assertIn("6.0h", c["failures"][0])

    def test_unlesbare_datei_meldet_unbekannt_statt_gruen(self):
        c = self._run({}, unlesbar=True)
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")

    def test_kaputter_zeitstempel_meldet_unbekannt(self):
        c = self._run({"updatedAt": "gestern irgendwann"})
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")
