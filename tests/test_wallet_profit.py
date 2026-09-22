#!/usr/bin/env python3
"""
tests/test_wallet_profit.py — 22.09.2026: Profit und ROI je Zeitraum, nicht nur CLV.

🔴 Lucas: „Mir ist da wirklich wichtig, dass wir den Profit und den ROI der letzten sieben und
30 Tage auch mit tracken. Du weisst ja, mit CLV bin ich jetzt nicht so der grösste Fan. Ich will
halt immer den Profit haben."

Das Loch war grösser, als es aussieht. Das Tages-Gedächtnis vom 17.09. hielt je Tag
{n, CLV-Summe, Treffer, CLV-Quadratsumme} — vier Zahlen, keine davon Geld. `fenster7` und
`fenster30` konnten deshalb nur Trefferquote und CLV sagen. Das einzige Geld-Feld an einer
Wallet war `pnl`, und das ist Polymarkets LEBENS-Bilanz über alles, auch Wahlen und Krypto.

Fehlerklasse: **ein Zeitraum, der alles ausser der Frage misst, die gestellt wurde.**

⚠️ Was die Zahl nicht ist: sie unterstellt Halten bis zur Auflösung. Wir sehen Positionen, keine
Trades. Es ist die Antwort auf „hätte sich Mitgehen gelohnt", nicht auf „was hat die Wallet
verdient" — und genau so gehört sie beschriftet.
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_money_broad as B


class TestDieRechnung(unittest.TestCase):
    """Anteile = usd/lastPrice, Einsatz = Anteile × Einstieg, der Gewinner zahlt 1,00 je Anteil."""

    def test_eine_faire_wette_verdoppelt(self):
        self.assertEqual(B.geld_aus_position(100, 0.50, 0.50, True), (100.0, 100.0))
        self.assertEqual(B.geld_aus_position(100, 0.50, 0.50, False), (-100.0, 100.0))

    def test_ein_kurzer_favorit_bringt_wenig(self):
        """95 $ bei 95¢ = 100 Anteile; Ø-Einstieg 80¢ → Einsatz 80, Gewinn 20 (ROI +25 %)."""
        self.assertEqual(B.geld_aus_position(95, 0.95, 0.80, True), (20.0, 80.0))

    def test_der_einstieg_zaehlt_nicht_der_jetzt_preis(self):
        """Die Wallet hat bei 20¢ gekauft, der Markt steht bei 80¢ — verdient wird auf 20¢."""
        gewinn, einsatz = B.geld_aus_position(80, 0.80, 0.20, True)
        self.assertEqual((gewinn, einsatz), (80.0, 20.0))
        self.assertEqual(round(gewinn / einsatz, 2), 4.0, "ROI +400 %")

    def test_ein_aussenseiter_der_verliert(self):
        self.assertEqual(B.geld_aus_position(20, 0.20, 0.20, False), (-20.0, 20.0))


class TestWoSieSchweigt(unittest.TestCase):
    """None heisst „nicht rechenbar" und nie 0 — eine Null im Nenner verdünnt jeden ROI."""

    def test_ohne_preis(self):
        self.assertEqual(B.geld_aus_position(100, None, 0.5, True), (None, None))
        self.assertEqual(B.geld_aus_position(100, 0.5, None, True), (None, None))

    def test_unsinnige_preise(self):
        for lp, en in ((0.0, 0.5), (1.0, 0.5), (0.5, 0.0), (0.5, 1.0), (-0.2, 0.5)):
            self.assertEqual(B.geld_aus_position(100, lp, en, True), (None, None), (lp, en))

    def test_ohne_groesse(self):
        self.assertEqual(B.geld_aus_position(0, 0.5, 0.5, True), (None, None))


class TestDasTagesGedaechtnis(unittest.TestCase):
    NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    def _s(self, n=10):
        return {"n": n, "clvSumPP": 0.0, "wins": 0, "usd": 0}

    def test_geld_landet_im_tag(self):
        s = B._wallet_zeit(self._s(), 1.0, True, self.NOW, gewinn=100.0, einsatz=50.0)
        tag = s["tage"]["2026-09-22"]
        self.assertEqual(len(tag), 7)
        self.assertEqual((tag[4], tag[5], tag[6]), (100.0, 50.0, 1))

    def test_zwei_auflösungen_am_selben_tag_summieren_sich(self):
        s = B._wallet_zeit(self._s(), 1.0, True, self.NOW, gewinn=100.0, einsatz=50.0)
        s = B._wallet_zeit(s, -1.0, False, self.NOW, gewinn=-30.0, einsatz=30.0)
        tag = s["tage"]["2026-09-22"]
        self.assertEqual((tag[0], tag[4], tag[5], tag[6]), (2, 70.0, 80.0, 2))

    def test_eine_auflösung_ohne_geld_zaehlt_nur_bei_n(self):
        """⭐ Der Riegel gegen den erfundenen Nenner: ohne Preis darf die Zeile die Anzahl
        erhöhen, aber nicht so tun, als wäre 0 $ auf 0 $ gesetzt worden."""
        s = B._wallet_zeit(self._s(), 1.0, True, self.NOW, gewinn=100.0, einsatz=50.0)
        s = B._wallet_zeit(s, 1.0, True, self.NOW, gewinn=None, einsatz=None)
        tag = s["tage"]["2026-09-22"]
        self.assertEqual(tag[0], 2, "beide zählen bei n")
        self.assertEqual((tag[4], tag[5], tag[6]), (100.0, 50.0, 1), "nur eine bei Geld")

    def test_alte_vier_stellige_tage_bleiben_lesbar(self):
        s = self._s()
        s["tage"] = {"2026-09-20": [3, 1.5, 2, 4.0]}
        s = B._wallet_zeit(s, 1.0, True, self.NOW, gewinn=10.0, einsatz=5.0)
        self.assertEqual(s["tage"]["2026-09-20"], [3, 1.5, 2, 4.0], "der Altbestand bleibt")
        self.assertEqual(len(s["tage"]["2026-09-22"]), 7)


class TestDerZeitraum(unittest.TestCase):
    def _tage(self, **d):
        return {"tage": d, "n": 10}

    def test_profit_und_roi_ueber_sieben_tage(self):
        s = self._tage(**{"2026-09-20": [2, 1.0, 1, 2.0, 50.0, 100.0, 2],
                          "2026-09-21": [1, 0.5, 1, 0.5, 25.0, 50.0, 1]})
        b = B.zeitraum_bilanz(s, "2026-09-22", 7)
        self.assertEqual(b["gewinn"], 75.0)
        self.assertEqual(b["einsatz"], 150.0)
        self.assertEqual(b["roi"], 0.5)
        self.assertEqual(b["nGeld"], 3)

    def test_ausserhalb_des_fensters_zaehlt_nichts(self):
        s = self._tage(**{"2026-08-01": [2, 1.0, 1, 2.0, 999.0, 10.0, 2],
                          "2026-09-21": [1, 0.5, 1, 0.5, 25.0, 50.0, 1]})
        b = B.zeitraum_bilanz(s, "2026-09-22", 7)
        self.assertEqual(b["gewinn"], 25.0)
        self.assertEqual(b["nGeld"], 1)

    def test_ein_fenster_ganz_ohne_geld_sagt_None_statt_null(self):
        """⭐ Der Unterschied, um den es geht: „nicht gemessen" ist nicht „nichts verdient"."""
        b = B.zeitraum_bilanz(self._tage(**{"2026-09-21": [3, 1.5, 2, 4.0]}), "2026-09-22", 7)
        self.assertEqual(b["n"], 3)
        self.assertIsNone(b["gewinn"])
        self.assertIsNone(b["roi"])
        self.assertEqual(b["nGeld"], 0)

    def test_nGeld_nennt_die_abdeckung(self):
        """Ein ROI aus 1 von 30 Auflösungen darf nicht aussehen wie einer aus 30."""
        s = self._tage(**{"2026-09-20": [29, 1.0, 20, 2.0],
                          "2026-09-21": [1, 0.5, 1, 0.5, 25.0, 50.0, 1]})
        b = B.zeitraum_bilanz(s, "2026-09-22", 7)
        self.assertEqual((b["n"], b["nGeld"]), (30, 1))

    def test_nGeld_zaehlt_nicht_einfach_die_auflösungen(self):
        """⭐ Ein Tag kann drei Auflösungen haben und nur bei einer einen Preis — dann ist
        `nGeld` 1, nicht 3. Ohne diesen Fall überlebt `nGeld = n` jede Mutation, weil beide
        Zahlen in den einfachen Beispielen zufällig gleich sind."""
        s = self._tage(**{"2026-09-21": [3, 1.5, 2, 4.0, 25.0, 50.0, 1]})
        b = B.zeitraum_bilanz(s, "2026-09-22", 7)
        self.assertEqual((b["n"], b["nGeld"]), (3, 1))

    def test_ein_einsatz_von_null_gibt_keinen_roi(self):
        s = self._tage(**{"2026-09-21": [1, 0.5, 1, 0.5, 0.0, 0.0, 1]})
        self.assertIsNone(B.zeitraum_bilanz(s, "2026-09-22", 7)["roi"])


class TestDieLebenssumme(unittest.TestCase):
    """Getrennt von `pnl` — das ist Polymarkets Lebensbilanz über ALLES, auch Wahlen und Krypto."""

    def test_gewinn_und_pnl_sind_zwei_verschiedene_felder(self):
        import re
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "poly_money_broad.py"), encoding="utf-8").read()
        self.assertIn('s["gewinn"]', quelle)
        self.assertIn('s["einsatz"]', quelle)
        self.assertNotIn('s["pnl"] = round((s.get("gewinn")', quelle)
        del re


if __name__ == "__main__":
    unittest.main()


# ── Der ganze Lauf: bucht `update_wallet_track` das Geld wirklich? ────────────────────────
class TestDerLaufBuchtEsAuch(unittest.TestCase):
    """⭐ Eine Rechnung, die niemand aufruft, ist keine Messung. Genau diese Lücke hat in dieser
    Woche schon zweimal eine Mutation überlebt."""

    from datetime import timedelta
    T0 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    def _up(self, price, usd=5000, wallet="0xW"):
        return {"key": "mlb-a-b", "league": "MLB", "resolved": False, "hoursToKickoff": 2.0,
                "prices": {"A": price, "B": round(1 - price, 4)},
                "whales": [{"wallet": wallet, "side": "A", "usd": usd}]}

    def _resolved(self, winner="A"):
        return {"key": "mlb-a-b", "resolved": True,
                "resolvedPrices": {winner: 1.0, ("B" if winner == "A" else "A"): 0.0}}

    def _lauf(self, winner="A", preis=0.40, usd=5000, vor_n=0):
        t = B.update_wallet_track({}, [self._up(preis, usd)], now=self.T0)
        if vor_n:
            # als haette die Wallet schon eine Historie — erst ab WALLET_FENSTER_AB_N legt der
            # Produzent ueberhaupt ein Tages-Gedaechtnis an
            t.setdefault("scores", {}).setdefault("0xW", {"n": 0, "clvSumPP": 0.0,
                                                         "wins": 0, "usd": 0})["n"] = vor_n
        return B.update_wallet_track(t, [self._resolved(winner)],
                                     now=self.T0 + self.timedelta(hours=3))

    def test_ein_treffer_wird_als_gewinn_gebucht(self):
        """5.000 $ bei 40¢ = 12.500 Anteile, Einsatz 5.000 → Gewinn +7.500."""
        s = self._lauf("A")["scores"]["0xW"]
        self.assertEqual(s["gewinn"], 7500.0)
        self.assertEqual(s["einsatz"], 5000.0)
        self.assertEqual(s["nGeld"], 1)

    def test_ein_fehlschlag_ebenfalls(self):
        s = self._lauf("B")["scores"]["0xW"]
        self.assertEqual(s["gewinn"], -5000.0)
        self.assertEqual(s["einsatz"], 5000.0)

    def test_duenne_wallets_bekommen_kein_tages_gedaechtnis(self):
        """Bewusst so: das Gedaechtnis beginnt erst ab `WALLET_FENSTER_AB_N` Aufloesungen —
        2.573 Wallets mit n<8 wuerden die Datei sonst verdreifachen (gemessen 17.09.). Die
        LEBENS-Summe laeuft trotzdem ab der ersten Zeile mit, nur die Zeitfenster nicht."""
        s = self._lauf("A")["scores"]["0xW"]
        self.assertEqual(s["gewinn"], 7500.0)
        self.assertIsNone(s.get("fenster7"))

    def test_die_zeitfenster_tragen_es_weiter(self):
        s = self._lauf("A", vor_n=B.WALLET_FENSTER_AB_N)["scores"]["0xW"]
        for f in ("fenster7", "fenster30"):
            self.assertIsNotNone(s.get(f), f)
            self.assertEqual(s[f]["gewinn"], 7500.0, f)
            self.assertEqual(s[f]["roi"], 1.5, f)
            self.assertEqual(s[f]["nGeld"], 1, f)

    def test_es_bleibt_getrennt_von_polymarkets_lebensbilanz(self):
        """`pnl` ist Polymarkets Zahl über alles — sie darf von unserer nicht überschrieben
        werden, sonst misst das Dashboard zwei verschiedene Dinge unter einem Namen."""
        s = self._lauf("A")["scores"]["0xW"]
        self.assertNotIn("pnl", s)


# ── Und auf der Karte? ────────────────────────────────────────────────────────────────────
class TestDieKarteZeigtDenProfit(unittest.TestCase):
    """Lucas sieht die Wallets zuerst auf der Push-Karte. Eine Zahl, die nur im Artefakt steht,
    beantwortet seine Frage nicht."""

    def setUp(self):
        import poly_whale_watch
        self.W = poly_whale_watch

    def test_beide_zeitraeume_stehen_drauf(self):
        self.assertEqual(self.W.FENSTER_TAGE_ALLE, (7, 30))

    def test_die_geld_zeile_nennt_profit_und_roi(self):
        t = self.W._geld_zeile({"gewinn": 7500, "einsatz": 5000, "roi": 1.5, "n": 9, "nGeld": 9})
        self.assertIn("Profit", t)
        self.assertIn("+$7.5K", t)
        self.assertIn("ROI +150.0 %", t)

    def test_ein_verlust_steht_als_verlust_da(self):
        t = self.W._geld_zeile({"gewinn": -320.5, "einsatz": 5000, "roi": -0.064,
                                "n": 30, "nGeld": 30})
        self.assertIn("−$320", t)
        self.assertIn("-6.4 %", t)

    def test_eine_luecke_wird_genannt(self):
        """⭐ Ein ROI aus 12 von 30 Auflösungen darf nicht aussehen wie einer aus 30."""
        t = self.W._geld_zeile({"gewinn": -320.5, "einsatz": 5000, "roi": -0.064,
                                "n": 30, "nGeld": 12})
        self.assertIn("aus 12 von 30", t)

    def test_nicht_gemessen_ist_nicht_null(self):
        for f in ({"n": 9, "nGeld": 0}, {}, None):
            self.assertIn("noch nicht gemessen", self.W._geld_zeile(f))
            self.assertNotIn("$0", self.W._geld_zeile(f))

    def test_die_lebensbilanz_sagt_jetzt_was_sie_ist(self):
        """`pnl` ist Polymarkets Zahl über ALLES — ohne den Zusatz liest sie sich wie Sport."""
        quelle = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "poly_whale_watch.py"), encoding="utf-8").read()
        self.assertIn("auch Wahlen/Krypto", quelle)
