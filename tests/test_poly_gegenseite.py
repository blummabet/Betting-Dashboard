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


class TestDieGegenprobeEinigkeit(unittest.TestCase):
    """18.09.2026 (Lucas: „was ist, wenn zwei Top Wallets auf dieselbe Seite gehen? Haben wir das
    extra bedacht oder extra erwaehnt im Push?").

    Nein — auf der Karte stand dazu kein Wort, waehrend der Streitfall seit August einen Marker
    hat. Wenn Widerspruch etwas kostet, gehoert die Frage dazu, ob Zustimmung etwas bringt. Und
    sie wird mit DERSELBEN Strenge beantwortet: dort muss die Obergrenze unter null liegen, hier
    die Untergrenze darueber.
    """

    def _welt(self, n_einig, n_allein, einig_quote, allein_quote):
        close = {}
        for i in range(n_einig):
            gew = "A" if i < round(n_einig * einig_quote) else "B"
            close["e%d" % i] = _markt([_w("0x1", "A"), _w("0x2", "A")], gew)
        for i in range(n_allein):
            gew = "A" if i < round(n_allein * allein_quote) else "B"
            close["a%d" % i] = _markt([_w("0x3", "A")], gew)
        return close

    def test_der_klare_fall_heisst_einigkeit_traegt(self):
        r = G.bericht(self._welt(80, 300, 0.95, 0.55), ALLE)["einigkeit"]
        self.assertEqual(r["urteil"], "Einigkeit traegt", r["grund"])
        self.assertGreater(r["lo"], 0, "die Untergrenze muss ueber null liegen")

    def test_ohne_unterschied_wird_nichts_behauptet(self):
        r = G.bericht(self._welt(80, 300, 0.60, 0.60), ALLE)["einigkeit"]
        self.assertEqual(r["urteil"], "nicht entschieden", r["grund"])

    def test_einigkeit_die_SCHLECHTER_ist_wird_nicht_zum_beleg(self):
        """Die Richtung muss stimmen. Ein Band unter null ist kein Beleg, auch kein negativer."""
        r = G.bericht(self._welt(80, 300, 0.30, 0.70), ALLE)["einigkeit"]
        self.assertEqual(r["urteil"], "nicht entschieden", r["grund"])

    def test_zu_wenige_einige_maerkte_sind_kein_urteil(self):
        r = G.bericht(self._welt(5, 300, 0.95, 0.55), ALLE)["einigkeit"]
        self.assertEqual(r["urteil"], "zu wenig Daten", r["grund"])

    def test_umkaempfte_maerkte_zaehlen_hier_nicht_mit(self):
        """Sonst wandert der Streitfall in die Gegenprobe und verwaessert beide Aussagen."""
        welt = self._welt(40, 200, 0.95, 0.55)
        for i in range(60):
            welt["u%d" % i] = _markt([_w("0x1", "A"), _w("0x2", "A"), _w("0x9", "B")], "B")
        r = G.bericht(welt, ALLE)
        self.assertEqual(r["einigkeit"]["einig"]["maerkte"], 40)
        self.assertEqual(r["umkaempft"]["maerkte"], 60)
        # Und sie duerfen auch nicht in den VERGLEICHSARM rutschen: „eine Wallet allein" waere
        # sonst zur Haelfte aus Maerkten gebaut, in denen zwei sich widersprechen — die Zahl,
        # gegen die Einigkeit gemessen wird, waere dann eine andere als ihr Name sagt.
        self.assertEqual(r["einigkeit"]["allein"]["maerkte"], 200)
        self.assertEqual(r["einigkeit"]["einig"]["maerkte"] + r["einigkeit"]["allein"]["maerkte"],
                         r["unumkaempft"]["maerkte"])

    def test_die_schranke_ist_spiegelbildlich(self):
        self.assertEqual(G.einigkeit_urteil(100, 0.18, 0.07)[0], "Einigkeit traegt")
        self.assertEqual(G.einigkeit_urteil(100, 0.18, -0.02)[0], "nicht entschieden")
