# -*- coding: utf-8 -*-
"""tests/test_poly_gegenseite.py — 18.09.2026

Lucas schickt zwei Karten aus demselben Spiel, wenige Minuten auseinander — $31,1K auf 3DMAX
@49c von Rang #16, $13,9K auf Liquid @50c von einer anderen bewiesenen Wallet — und schreibt:
„Ich werd solche Einsaetze nie verstehen. Beide Top Wallets."

Diese Tests halten fest, WORAN das Urteil scheitern darf: an zu wenigen Maerkten, an einem Band,
das ueber null reicht — und nicht daran, dass jemand die Gruppen so lange schneidet, bis die
Zahl passt.
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import poly_gegenseite as G  # noqa: E402


def _markt(whales, gewinner="A", resolved=True):
    return {"resolved": resolved,
            "resolvedPrices": {gewinner: 1.0, "B" if gewinner == "A" else "A": 0.0},
            "whales": whales}


def _w(wallet, side, usd=1000):
    return {"wallet": wallet, "side": side, "usd": usd}


ALLE = lambda w: True          # noqa: E731  — jede Wallet gilt als bewiesen
KEINE = lambda w: False        # noqa: E731


class TestDieEinheit(unittest.TestCase):
    def test_ein_markt_mit_beiden_seiten_ist_umkaempft(self):
        z = G.beobachtungen({"k": _markt([_w("0x1", "A"), _w("0x2", "B")])}, ALLE)
        self.assertEqual(len(z), 1)
        self.assertTrue(z[0]["umkaempft"])
        self.assertEqual(sorted(z[0]["treffer"]), [False, True])

    def test_zwei_wallets_auf_DERSELBEN_seite_sind_kein_streit(self):
        z = G.beobachtungen({"k": _markt([_w("0x1", "A"), _w("0x2", "A")])}, ALLE)
        self.assertFalse(z[0]["umkaempft"])
        self.assertEqual(z[0]["treffer"], [True, True], "zwei Wallets sind zwei Positionen")

    def test_unbewiesene_gegenseite_zaehlt_nicht(self):
        """Das Mass fuer „glaubwuerdig" wird injiziert — und es ist dasselbe, mit dem eine Wallet
        ueberhaupt in einen Push kommt. Eine beliebige Gegenwette ist kein Gegenargument."""
        z = G.beobachtungen({"k": _markt([_w("0x1", "A"), _w("0x2", "B")])},
                            lambda w: w == "0x1")
        self.assertFalse(z[0]["umkaempft"])

    def test_unaufgeloeste_maerkte_zaehlen_nicht(self):
        self.assertEqual(G.beobachtungen({"k": _markt([_w("0x1", "A")], resolved=False)}, ALLE), [])

    def test_ohne_bewiesene_wallet_kein_eintrag(self):
        self.assertEqual(G.beobachtungen({"k": _markt([_w("0x1", "A")])}, KEINE), [])


class TestDasUrteil(unittest.TestCase):
    def _welt(self, n_um, n_un, un_trefferquote):
        """Umkaempfte Maerkte sind hier immer 1 gegen 1 — und liegen damit bei exakt 50 %.

        Das ist keine Vereinfachung, sondern der Kern der Sache: sitzt auf beiden Seiten je eine
        bewiesene Wallet, gewinnt per Konstruktion eine und verliert eine. Die Frage ist nie, ob
        umkaempfte Maerkte gegen 50 % laufen — sie ist, wie weit die unumkaempften darueber
        liegen. Genau das steuert `un_trefferquote`.
        """
        close = {}
        for i in range(n_um):
            close["um%d" % i] = _markt([_w("0x1", "A"), _w("0x2", "B")], "A" if i % 2 else "B")
        for i in range(n_un):
            gew = "A" if i < round(n_un * un_trefferquote) else "B"
            close["un%d" % i] = _markt([_w("0x3", "A")], gew)
        return close

    def test_zu_wenige_umkaempfte_maerkte_sind_kein_urteil(self):
        r = G.bericht(self._welt(5, 200, 0.7), ALLE)
        self.assertEqual(r["urteil"], "zu wenig Daten", r["grund"])

    def test_der_klare_fall_heisst_umkaempft_ist_schlechter(self):
        r = G.bericht(self._welt(120, 300, 0.95), ALLE)
        self.assertEqual(r["urteil"], "umkaempft ist schlechter", r["grund"])
        self.assertLess(r["hi"], 0, "die Obergrenze muss unter null liegen")
        self.assertLess(r["diffPP"], 0)

    def test_ohne_unterschied_wird_nichts_behauptet(self):
        """Liegen die unumkaempften auch bei 50 %, gibt es nichts zu melden — dann traegt die
        Wallet-Auswahl ueberhaupt nicht, und das waere eine ganz andere Nachricht."""
        r = G.bericht(self._welt(150, 300, 0.50), ALLE)
        self.assertEqual(r["urteil"], "nicht entschieden", r["grund"])

    def test_ein_punktschaetzer_allein_entscheidet_nicht(self):
        """Die Differenz zeigt in die richtige Richtung, das Band aber ueber null. Genau die
        Konstellation, in der dieses Repo NICHT freigibt."""
        self.assertEqual(G.urteil(100, -0.03, 0.02)[0], "nicht entschieden")
        self.assertEqual(G.urteil(100, -0.17, -0.12)[0], "umkaempft ist schlechter")

    def test_leere_welt_stuerzt_nicht_ab(self):
        r = G.bericht({}, ALLE)
        self.assertEqual(r["urteil"], "zu wenig Daten")
        self.assertIsNone(r["diffPP"])


class TestGegenDenEchtenBestand(unittest.TestCase):
    """Der Befund vom 18.09., festgehalten. Bricht er weg, ist DAS die Nachricht."""

    def test_der_befund_haelt(self):
        import json
        p = BASE / "poly_gegenseite.json"
        if not p.exists():
            self.skipTest("noch kein Bericht")
        r = json.loads(p.read_text(encoding="utf-8"))
        if r["umkaempft"]["maerkte"] < G.MIN_MAERKTE:
            self.skipTest("zu duenn")
        self.assertEqual(r["urteil"], "umkaempft ist schlechter", r["grund"])
        self.assertLess(r["umkaempft"]["hitPct"], r["unumkaempft"]["hitPct"])
