#!/usr/bin/env python3
"""
tests/test_whale_erfassung.py — 22.09.2026: wir haben die guten Leute gar nicht erfasst.

🔴 Lucas: „Auf Poly treiben sich gute Leute rum und die gilt es zu erfassen … können Leute sein,
die 5K pro Wette setzen oder auch 50K."

Je Markt wurden die **Top 4** Halter mitgeschrieben. Gemessen an den 3.870 Märkten des
Close-Feeds: 3.819 tragen exakt vier — der Deckel greift praktisch überall. `_alle_holder` holt
bis zu 1.000 Halter je Ausgang; alles ab Platz 5 fiel weg, bevor irgendetwas geschrieben wurde.

Zwei Folgen, und die zweite ist die schlimmere:

  · Entdeckung: wer in einem 500K-Markt mit 5K sehr scharf unterwegs ist, existiert für uns
    nicht — die vier Plätze gehen an die Grösse.
  · Verzerrung: eine Wallet, die wir längst verfolgen, VERSCHWINDET aus den Daten, sobald sie in
    einem Markt nur Platz 5 ist. Ihr `n` ist damit nicht bloss zu klein, es ist schief — wir
    sehen sie überwiegend dort, wo sie die Grösste war. Genau dieses `n` trägt danach jede
    Trefferquote, jeden CLV und ab heute den Profit.

Fehlerklasse: **eine Stichprobe, die nach derselben Eigenschaft auswählt, die sie messen soll.**
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_money_broad as B


def _w(n, side="A", ab=1000):
    """n Halter, absteigend nach Größe."""
    return [{"wallet": "0x%02d" % i, "side": side, "usd": ab - i} for i in range(n)]


class TestDerDeckel(unittest.TestCase):
    def test_er_steht_auf_zwoelf(self):
        """Lucas' Wahl nach den gemessenen Kosten (Close-Datei 7,5 -> ~11 MB)."""
        self.assertEqual(B.WHALES_PER_MARKET, 12)

    def test_die_groessten_kommen_zuerst(self):
        r = B.whale_auswahl(_w(30))
        self.assertEqual(len(r), 12)
        self.assertEqual([x["wallet"] for x in r], ["0x%02d" % i for i in range(12)])

    def test_weniger_halter_als_der_deckel(self):
        self.assertEqual(len(B.whale_auswahl(_w(3))), 3)

    def test_unsortierte_eingabe_wird_sortiert(self):
        w = _w(20)
        w.reverse()
        self.assertEqual(B.whale_auswahl(w)[0]["usd"], 1000)

    def test_leer_wirft_nicht(self):
        self.assertEqual(B.whale_auswahl([]), [])
        self.assertEqual(B.whale_auswahl(None), [])


class TestWerVerfolgtWirdBleibtDrin(unittest.TestCase):
    """⭐ Der eigentliche Fix. Der Deckel allein behebt nur die Entdeckung, nicht die Verzerrung."""

    def test_eine_verfolgte_wallet_auf_platz_20_kommt_mit(self):
        r = B.whale_auswahl(_w(30), bekannt={"0x20"})
        self.assertEqual(len(r), 13)
        self.assertIn("0x20", [x["wallet"] for x in r])

    def test_ohne_sie_faellt_dieselbe_wallet_raus(self):
        """Die Gegenprobe — sonst wäre nicht belegt, dass die Regel etwas tut."""
        self.assertNotIn("0x20", [x["wallet"] for x in B.whale_auswahl(_w(30))])

    def test_sie_wird_nicht_doppelt_aufgenommen(self):
        r = B.whale_auswahl(_w(30), bekannt={"0x03"})     # steht schon in den Top 12
        self.assertEqual(len(r), 12)

    def test_ein_doppelter_eintrag_wird_nur_einmal_genommen(self):
        """🔴 Beim Mutationstest aufgefallen: `drin` war unbelegt. Der Fall, in dem es zaehlt,
        ist eine Liste mit derselben (Wallet, Seite) zweimal — heute liefert `_market_money`
        das nicht, aber eine Dedup-Regel, die nie geprueft wird, ist keine."""
        # zwei Faelle: eine Dopplung UNTERHALB des Deckels …
        w = _w(30) + [{"wallet": "0x20", "side": "A", "usd": 3},
                      {"wallet": "0x20", "side": "A", "usd": 2}]
        r = B.whale_auswahl(w, bekannt={"0x20"})
        self.assertEqual(sum(1 for x in r if x["wallet"] == "0x20" and x["side"] == "A"), 1)
        # … und eine, die den Eintrag aus den Top 12 nochmal nennt. Nur dieser zweite Fall
        # prueft die Startmenge von `drin` — der erste kaeme auch ohne sie durch.
        w2 = _w(30) + [{"wallet": "0x03", "side": "A", "usd": 1}]
        r2 = B.whale_auswahl(w2, bekannt={"0x03"})
        self.assertEqual(len(r2), 12)
        self.assertEqual(sum(1 for x in r2 if x["wallet"] == "0x03"), 1)

    def test_dieselbe_wallet_auf_zwei_seiten_zaehlt_zweimal(self):
        """Ein Halter auf Over UND Under sind zwei Positionen — die Zuordnung läuft über
        (Wallet, Seite), nicht über die Wallet allein."""
        w = _w(30) + [{"wallet": "0x20", "side": "B", "usd": 5}]
        r = B.whale_auswahl(w, bekannt={"0x20"})
        self.assertEqual(sorted(x["side"] for x in r if x["wallet"] == "0x20"), ["A", "B"])

    def test_die_gross_schreibung_der_adresse_stoert_nicht(self):
        w = _w(12) + [{"wallet": "0xAbCdEf", "side": "A", "usd": 1}]
        r = B.whale_auswahl(w, bekannt={"0xabcdef"})
        self.assertIn("0xAbCdEf", [x["wallet"] for x in r])

    def test_die_harte_obergrenze_haelt(self):
        """Sonst könnte ein Markt mit 500 verfolgten Wallets die Datei sprengen."""
        r = B.whale_auswahl(_w(200), bekannt={"0x%02d" % i for i in range(200)})
        self.assertEqual(len(r), B.WHALES_HART)


class TestWenWirVerfolgen(unittest.TestCase):
    def test_ab_vier_aufloesungen(self):
        t = {"scores": {"0xa": {"n": 4}, "0xb": {"n": 3}, "0xc": {"n": 40}}}
        self.assertEqual(B.bekannte_wallets(t), {"0xa", "0xc"})

    def test_die_schwelle_ist_niedrig_und_das_mit_absicht(self):
        """Eine Wallet, die gerade erst Historie aufbaut, ist genau die, deren nächste Zeilen
        wir brauchen."""
        self.assertLessEqual(B.BEKANNT_AB_N, 4)

    def test_kaputter_track_wirft_nicht(self):
        for t in (None, {}, {"scores": None}, {"scores": {"0xa": "kein dict"}}):
            self.assertEqual(B.bekannte_wallets(t), set())

    def test_adressen_werden_kleingeschrieben(self):
        self.assertEqual(B.bekannte_wallets({"scores": {"0xAB": {"n": 9}}}), {"0xab"})


class TestDerProduzentBenutztEsAuch(unittest.TestCase):
    """Eine Auswahl, die niemand aufruft, ändert nichts — dieselbe Lücke hat diese Woche schon
    zweimal eine Mutation überlebt."""

    def test_market_money_ruft_die_auswahl(self):
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "poly_money_broad.py"), encoding="utf-8").read()
        kern = quelle.split("def _market_money")[1].split("\ndef ")[0]
        self.assertIn("whale_auswahl(whales, BEKANNTE_WALLETS)", kern)
        self.assertNotIn("whales[:WHALES_PER_MARKET]", kern,
                         "der alte, blosse Groessen-Schnitt darf nicht danebenstehen")

    def test_main_fuellt_die_bekannten_vor_dem_scan(self):
        """`_market_money` entscheidet WÄHREND des Fetchs — wer erst danach lädt, kommt zu spät."""
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "poly_money_broad.py"), encoding="utf-8").read()
        mainblock = quelle.split("\ndef main() -> int:")[1]
        vor_scan = mainblock.split("fetch_markets(")[0]
        self.assertIn("BEKANNTE_WALLETS = bekannte_wallets(", vor_scan)


if __name__ == "__main__":
    unittest.main()
