#!/usr/bin/env python3
"""
tests/test_verlauf_nachtragen.py — 21.09.2026.

🔴 `wallet_abgleich.entbuchen` kann eine Zeile nur entlasten, wenn der Wallet-Verlauf ihren
Zeitpunkt abdeckt. `*_poly_verlauf.json` gibt es seit dem 21.09. nachmittags; die zwei Zeilen,
um die es geht, sind von derselben Nacht. Fehlerklasse: **eine Gegenprobe, deren Beweismittel
juenger ist als das, was sie beweisen soll.**

Die Staende liegen in der Git-Historie von `*_poly_balance.json`. Getestet wird hier der reine
Kern — Rekonstruktion aus Git ist I/O und gehoert dem Workflow.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verlauf_nachtragen as VN
import wallet_abgleich as WA


def _p(ts, usdc, pos=0.0):
    return {"ts": ts, "usdc": usdc, "positions": pos, "total": usdc + pos}


class TestEinStandWirdEinPunkt(unittest.TestCase):
    def test_der_normalfall(self):
        p = VN.punkt({"usdc": 178.2312, "positions": 0.0, "total": 178.2312,
                      "updatedAt": "2026-09-21T02:53:54+00:00"})
        self.assertEqual(p["ts"], "2026-09-21T02:53:54+00:00")
        self.assertEqual(p["usdc"], 178.2312)

    def test_ohne_zeitstempel_ist_er_wertlos(self):
        """Der Abgleich sucht Bewegungen in der ZEIT."""
        self.assertIsNone(VN.punkt({"usdc": 178.23}))

    def test_ohne_usdc_ebenfalls(self):
        self.assertIsNone(VN.punkt({"updatedAt": "2026-09-21T02:53:54+00:00"}))
        self.assertIsNone(VN.punkt({"updatedAt": "x", "usdc": "178"}))

    def test_kein_dict_wirft_nicht(self):
        for x in (None, [], "x", 3):
            self.assertIsNone(VN.punkt(x))


class TestZusammenfuehren(unittest.TestCase):
    def test_der_nachtrag_kommt_vorne_dran(self):
        alt = [_p("2026-09-21T16:20:00+00:00", 195.4)]
        nach = [_p("2026-09-21T02:53:00+00:00", 178.2),
                _p("2026-09-21T04:39:00+00:00", 178.2)]
        r = VN.zusammenfuehren(alt, nach)
        self.assertEqual([x["ts"][:16] for x in r],
                         ["2026-09-21T02:53", "2026-09-21T16:20"])
        self.assertEqual(r[0]["bisTs"][:16], "2026-09-21T04:39")

    def test_eine_ruhephase_schrumpft_auf_ihren_ANFANG(self):
        """🔴 Die wichtigste Zeile hier. Im ersten Anlauf behielt ich das ENDE der Ruhephase —
        damit wanderte der Kauf, der sie eroeffnet, um Stunden nach hinten, und `entbuchen`
        erklaerte die dazugehoerige Wette fuer unbelegt. Der Nachtrag haette das Gegenteil
        dessen bewiesen, wofuer es ihn gibt.

        Behalten wird der erste Stand; `bisTs` sagt, bis wann er galt."""
        nach = [_p("2026-09-21T01:00:00+00:00", 178.2),
                _p("2026-09-21T02:00:00+00:00", 178.2),
                _p("2026-09-21T03:00:00+00:00", 178.2)]
        r = VN.zusammenfuehren([], nach)
        self.assertEqual([x["ts"][:13] for x in r], ["2026-09-21T01"])
        self.assertEqual(r[-1]["bisTs"][:13], "2026-09-21T03")

    def test_und_der_verlauf_reicht_trotzdem_bis_zum_ende(self):
        """Die Kehrseite: wer nur `ts` liest, erklaert den halben Tag fuer nicht abgedeckt."""
        r = VN.zusammenfuehren([], [_p("2026-09-21T01:00:00+00:00", 178.2),
                                    _p("2026-09-21T03:00:00+00:00", 178.2)])
        self.assertEqual(WA.ende(r).isoformat()[:13], "2026-09-21T03")

    def test_der_produzent_gewinnt_bei_gleichem_zeitstempel(self):
        """Der bestehende Verlauf kommt aus dem Lauf selbst, der Nachtrag ist Rekonstruktion."""
        alt = [_p("2026-09-21T02:00:00+00:00", 99.0)]
        nach = [_p("2026-09-21T02:00:00+00:00", 178.2)]
        self.assertEqual(VN.zusammenfuehren(alt, nach)[0]["usdc"], 99.0)

    def test_zweimal_nachtragen_aendert_nichts(self):
        alt = [_p("2026-09-21T16:20:00+00:00", 195.4)]
        nach = [_p("2026-09-21T02:53:00+00:00", 178.2)]
        einmal = VN.zusammenfuehren(alt, nach)
        self.assertEqual(VN.zusammenfuehren(einmal, nach), einmal)

    def test_die_kappung_wirft_das_aelteste_weg(self):
        nach = [_p("2026-09-21T%02d:00:00+00:00" % h, 100.0 + h) for h in range(10)]
        r = VN.zusammenfuehren([], nach, keep=3)
        self.assertEqual([x["usdc"] for x in r], [107.0, 108.0, 109.0])

    def test_leere_eingaben_werfen_nicht(self):
        self.assertEqual(VN.zusammenfuehren(None, None), [])
        self.assertEqual(VN.zusammenfuehren([], [{"kein": "ts"}]), [])


class TestUndDannGreiftDerAbgleich(unittest.TestCase):
    """⭐ Der eigentliche Zweck, in einem Stueck: erst mit dem Nachtrag laesst sich die
    Toluca-Zeile ueberhaupt beurteilen."""

    NACHT = [_p("2026-09-20T21:53:00+00:00", 178.2312),
             _p("2026-09-21T02:53:00+00:00", 178.2312),
             _p("2026-09-21T04:39:00+00:00", 178.2312)]
    HEUTE = [_p("2026-09-21T16:20:00+00:00", 195.4329)]
    ZEILE = {"betKey": "toluca", "stake": 5.0, "placedAt": "2026-09-21T01:04:00+00:00",
             "status": "lost", "result": "LOSS", "pnl": -5.0}

    def test_ohne_nachtrag_ist_sie_nicht_pruefbar(self):
        bets = [dict(self.ZEILE)]
        self.assertEqual(WA.entbuchen(bets, self.HEUTE), [],
                         "unbeobachtet ist nicht widerlegt")
        self.assertEqual(bets[0]["pnl"], -5.0)

    def test_mit_nachtrag_faellt_sie_aus_der_bilanz(self):
        bets = [dict(self.ZEILE)]
        verlauf = VN.zusammenfuehren(self.HEUTE, self.NACHT)
        self.assertEqual(len(WA.entbuchen(bets, verlauf)), 1)
        self.assertEqual(bets[0]["pnl"], 0.0)

    def test_und_ein_echter_kauf_in_derselben_nacht_bleibt_stehen(self):
        """Die Gegenprobe: der Nachtrag darf nicht ALLES entlasten."""
        nacht = [_p("2026-09-20T21:53:00+00:00", 178.2312),
                 _p("2026-09-21T01:15:00+00:00", 173.1612),   # -5,07: ein echter Kauf
                 _p("2026-09-21T04:39:00+00:00", 173.1612)]
        bets = [dict(self.ZEILE)]
        verlauf = VN.zusammenfuehren(self.HEUTE, nacht)
        self.assertEqual(WA.entbuchen(bets, verlauf), [])
        self.assertEqual(bets[0]["pnl"], -5.0)


if __name__ == "__main__":
    unittest.main()
