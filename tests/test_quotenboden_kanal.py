#!/usr/bin/env python3
"""
tests/test_quotenboden_kanal.py — 22.09.2026: der Quotenboden gilt fuer BEIDE Kanaele.

🔴 Lucas, zu einer Karte im Trades-Kanal:

    🎮 E-Sport · Fuego v T1 Academy
    T1 Academy @ 95¢        ← @1,05
    $51.6K · 76 % des Marktes

„die Quote ist halt wertlos … was soll ich da wetten? Das macht null Sinn … Bitte das auch
anpassen, damit nur die durchkommen, die zumindest 1,3 haben."

Die Regel gab es — sie hing nur am falschen Kanal. Der oeffentliche Trichter prueft die
Mindestquote seit dem 22.08., das Dominanz-Band seit dem 11.09.; der TRADES-Trichter nie. Dort
stand nur `_pub_ok`, und das laesst alles zwischen 3 und 97 Cent durch.

Fehlerklasse: **eine Regel, die fuer eine Teilmenge gilt, obwohl die Frage fuer alle dieselbe
ist.**

⚠️ Und die ehrliche Halbzeile dazu, damit sie niemand spaeter falsch zitiert: das ist eine
BRAUCHBARKEITS-Regel, keine Rendite-Regel. Ueber 500 abgerechnete Zeilen des
Whale-Follow-Tracks liegt der ROI UNTER 1,35 bei +2,9 % und darueber bei −4,8 %. Der Boden
kommt, weil eine Karte @1,05 nichts ist, dem man folgen kann — nicht weil sie Geld kostet.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_whale_watch as W


def _pos(first, last=None, league="ESPORTS", sport="esports"):
    p = {"firstPrice": first, "league": league, "sport": sport}
    if last is not None:
        p["lastPrice"] = last
    return p


class TestDerEchteFall(unittest.TestCase):
    """T1 Academy @ 95¢ = @1,053."""

    def test_die_karte_kommt_nicht_mehr_durch(self):
        self.assertFalse(W._quote_ok(_pos(0.95)))

    def test_und_sie_kam_vorher_durch_das_alte_tor(self):
        """⭐ Die Gegenprobe: `_pub_ok` — das einzige Tor, das im Trades-Trichter stand — haelt
        sie fuer in Ordnung. Ohne diesen Nachweis waere nicht belegt, dass genau hier die
        Luecke war."""
        self.assertTrue(W._pub_ok(_pos(0.95)))


class TestDerTrichterWendetIhnAuchAn(unittest.TestCase):
    """⭐ 🔴 Im ersten Anlauf fehlte genau dieser Test: `_quote_ok` war dreifach geprueft, aber
    die Mutation „Filter im Trades-Trichter wieder raus" blieb gruen — die Regel war getestet,
    ihre Anwendung nicht.
    Fehlerklasse: eine Regel, die geprueft ist, und eine Anwendung, die es nicht ist."""

    def _cand(self, *preise):
        return [("k%d" % i, _pos(p), False) for i, p in enumerate(preise)]

    def test_die_T1_karte_wird_zurueckgehalten(self):
        ok, raus = W.mit_quote(self._cand(0.95))
        self.assertEqual(ok, [])
        self.assertEqual(raus, 1)

    def test_die_brauchbaren_bleiben(self):
        ok, raus = W.mit_quote(self._cand(0.95, 0.50, 0.20))
        self.assertEqual([c[1]["firstPrice"] for c in ok], [0.50, 0.20])
        self.assertEqual(raus, 1)

    def test_ohne_kandidaten_wirft_es_nicht(self):
        self.assertEqual(W.mit_quote([]), ([], 0))
        self.assertEqual(W.mit_quote(None), ([], 0))

    def test_die_zahl_der_zurueckgehaltenen_stimmt(self):
        """Sie wird gedruckt — eine Regel, deren Preis niemand sieht, verschwindet still."""
        _ok, raus = W.mit_quote(self._cand(0.95, 0.90, 0.99, 0.40))
        self.assertEqual(raus, 3)


class TestEineZahlFuerEineFrage(unittest.TestCase):
    def test_alle_drei_boeden_sind_derselbe(self):
        """Trades, Public und das Dominanz-Band beantworten dieselbe Frage — drei Konstanten
        waeren drei Orte, an denen sie auseinanderlaufen koennen."""
        self.assertEqual(W.PUB_MIN_ODDS, W.MIN_QUOTE)
        self.assertEqual(W.DOM_MIN_QUOTE, W.MIN_QUOTE)

    def test_die_zahl_ist_die_des_projekts(self):
        """1,35 — dieselbe, die Lucas am 11.09. fuer das Band genannt hat und die in
        pick-engine.js und stake-radar.js schon der Boden ist."""
        self.assertEqual(W.MIN_QUOTE, 1.35)

    def test_der_oeffentliche_trichter_benutzt_denselben_kern(self):
        for preis in (0.95, 0.80, 0.735, 0.74, 0.20):
            self.assertEqual(W._pub_min_odds_ok(_pos(preis)), W._quote_ok(_pos(preis)), preis)


class TestWoDerBodenLiegt(unittest.TestCase):
    def test_knapp_darueber_bleibt_drin(self):
        self.assertTrue(W._quote_ok(_pos(1 / 1.36)))

    def test_knapp_darunter_faellt_raus(self):
        self.assertFalse(W._quote_ok(_pos(1 / 1.34)))

    def test_ein_aussenseiter_bleibt_immer_drin(self):
        """Hohe Quote heisst niedriger Preis — der Boden darf nur nach oben schneiden."""
        self.assertTrue(W._quote_ok(_pos(0.05)))

    def test_auch_der_jetzt_preis_muss_tragen(self):
        """Einstieg gut, Markt inzwischen durchgelaufen: ein Leser kauft zum Jetzt-Preis."""
        self.assertTrue(W._quote_ok(_pos(0.50, last=0.60)))
        self.assertFalse(W._quote_ok(_pos(0.50, last=0.95)))

    def test_ohne_preis_keine_karte(self):
        """Eine Empfehlung, deren Quote niemand kennt, kann man weder befolgen noch nachpruefen."""
        self.assertFalse(W._quote_ok({"league": "ESPORTS"}))
        self.assertFalse(W._quote_ok(_pos("keine Zahl")))


class TestDerBodenIstUmstellbar(unittest.TestCase):
    def test_ein_anderer_wert_wirkt(self):
        self.assertTrue(W._quote_ok(_pos(0.95), min_quote=1.02))
        self.assertFalse(W._quote_ok(_pos(0.50), min_quote=2.50))


class TestWasErKostet(unittest.TestCase):
    """Der Preis der Regel gehoert gemessen, nicht geschaetzt — sonst ist sie eine Meinung."""

    def _ledger(self, name):
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def test_im_public_buch_kostet_er_nichts(self):
        """Von 44 Pushs mit Preis liegt die niedrigste Quote bei @1,36 — der Anstieg von 1,30
        auf 1,35 nimmt dort keine einzige Zeile."""
        q = [1 / float(x["pushPrice"]) for x in self._ledger("poly_whale_public_ledger.json")
             if isinstance(x.get("pushPrice"), (int, float)) and 0 < x["pushPrice"] < 1]
        if not q:
            self.skipTest("kein Public-Buch")
        self.assertEqual([x for x in q if x < 1.35], [])

    def test_im_trades_buch_kostet_er_etwas_und_das_steht_hier(self):
        """Im Trades-Buch liegen Zeilen darunter. Die Zahl steht im Test, damit ein spaeterer
        Leser sieht, was die Regel weggenommen hat — und nicht glaubt, sie sei gratis."""
        q = [1 / float(x["pushPrice"]) for x in self._ledger("poly_whale_trades_ledger.json")
             if isinstance(x.get("pushPrice"), (int, float)) and 0 < x["pushPrice"] < 1]
        if not q:
            self.skipTest("kein Trades-Buch")
        unter = [x for x in q if x < 1.35]
        self.assertGreater(len(unter), 0,
                           "keine einzige Zeile darunter — dann war die Regel folgenlos, "
                           "und dieser Test hat seinen Anlass verloren")


if __name__ == "__main__":
    unittest.main()
