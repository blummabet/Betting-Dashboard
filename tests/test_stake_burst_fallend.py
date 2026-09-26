"""26.09.2026 — FC Vion Zlate Moravce-Vrable v FC Petrzalka: 11 Tickets, $20.015, 190 Sekunden,
Draw No Bet Petrzalka, Quote 1,85 → 1,75 → 1,70. Das Beinahe-Buch fuehrte den Fall mit
`quoten_uneinheitlich` — die Regel verlangte die gleiche Quote und warf den Fall weg, in dem das
Geld den Preis bewegt hat."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stake_burst_push as S

T0 = datetime(2026, 9, 26, 16, 23, 27, tzinfo=timezone.utc)


def _w(i, sek, usd, q):
    return {"id": "b%d" % i, "ts": (T0 + timedelta(seconds=sek)).isoformat(), "einsatzUsd": usd,
            "quote": q, "auswahlId": "petrzalka", "kat": "Fußball", "event": "A - B", "phase": "live",
            "markt": "Draw No Bet", "auswahl": "FC Petrzalka 1898", "liga": "2. Liga"}


FALL = [_w(0, 0, 1997, 1.85), _w(1, 2, 1996, 1.85), _w(2, 17, 1996, 1.85), _w(3, 120, 2122, 1.75),
        _w(4, 147, 1332, 1.75), _w(5, 147, 1934, 1.75), _w(6, 151, 2000, 1.75), _w(7, 164, 2100, 1.75),
        _w(8, 181, 1347, 1.70), _w(9, 184, 1979, 1.70)]
NOW = T0 + timedelta(minutes=6)


class TestQuotenArt(unittest.TestCase):
    def test_arten(self):
        self.assertEqual(S.quoten_art([1.85, 1.85]), "gleich")
        self.assertEqual(S.quoten_art([1.85, 1.75, 1.75, 1.70]), "fallend")
        self.assertEqual(S.quoten_art([1.70, 1.85]), "steigend")
        self.assertEqual(S.quoten_art([1.85, 1.70, 1.80]), "gemischt")


class TestDerFallWirdGefunden(unittest.TestCase):
    def test_fallende_quote_ist_ein_burst(self):
        bs = S.bursts(FALL, now=NOW, gesperrt=[])
        self.assertEqual(len(bs), 1)
        self.assertEqual(bs[0]["quotenArt"], "fallend")

    def test_gemischte_quote_bleibt_draussen(self):
        gem = [dict(x, quote=q) for x, q in zip(FALL, [1.85, 1.70, 1.85, 1.70, 1.85, 1.70, 1.85, 1.70, 1.85, 1.70])]
        verw = []
        self.assertEqual(S.bursts(gem, now=NOW, gesperrt=[], verworfen=verw), [])
        self.assertIn("quoten_uneinheitlich", verw[0]["gruende"])

    def test_der_boden_gilt_fuer_die_letzte_quote(self):
        tief = [dict(x, quote=q) for x, q in zip(FALL, [1.5] * 3 + [1.4] * 5 + [1.3] * 2)]
        self.assertEqual(S.bursts(tief, now=NOW, gesperrt=[]), [])

    def test_karte_zeigt_den_verlauf_und_die_eigene_bilanz(self):
        b = S.bursts(FALL, now=NOW, gesperrt=[])[0]
        k = S.build_burst_card(b, bilanz=S.buch_bilanz([], "fallend"))
        self.assertIn("@1.85 → @1.70", k)
        self.assertIn("noch kein gesendeter Burst", k)
        self.assertNotIn("+45,9", k, "die getippte Rueckrechnung vom 12.09. ist raus")

    def test_buchzeile_stempelt_die_art(self):
        b = S.bursts(FALL, now=NOW, gesperrt=[])[0]
        self.assertEqual(S.buch_zeile(b, "x")["quotenArt"], "fallend")


class TestBuchBilanz(unittest.TestCase):
    def test_alte_zeilen_zaehlen_als_gleich(self):
        led = [{"rendite": 0.1}] * 12 + [{"rendite": 0.5, "quotenArt": "fallend"}]
        self.assertEqual(S.buch_bilanz(led, "gleich")["n"], 12)
        self.assertEqual(S.buch_bilanz(led, "fallend")["n"], 1)
        self.assertIsNone(S.buch_bilanz(led, "fallend")["ug"])


if __name__ == "__main__":
    unittest.main()
