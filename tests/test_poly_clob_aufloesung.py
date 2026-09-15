#!/usr/bin/env python3
"""
tests/test_poly_clob_aufloesung.py — 15.09.2026: der CLOB als zweite Auflösungs-Quelle.

Anlass ist ein echter Fall: $5 auf lol-big1-koia-2026-09-14|BIG standen nach dem Spielende
weiter auf `placed`, weil KEIN Pfad Polymarket je nach diesem Markt gefragt hat. Jede Schranke
hier wird provoziert — zu jeder gehoert ein Fall, in dem Raten teurer gewesen waere als Warten.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import poly_clob_aufloesung as CA


def _markt(closed=True, tokens=None):
    return {"market_slug": "x", "closed": closed, "tokens": tokens or []}


def _tok(outcome, price=0.0, winner=None):
    t = {"outcome": outcome, "price": price}
    if winner is not None:
        t["winner"] = winner
    return t


class SiegerAusMarkt(unittest.TestCase):
    def test_echter_big_markt_wird_korrekt_gelesen(self):
        # Wortlaut der CLOB-Antwort vom 15.09.2026 fuer die Wette, die den Fix ausgeloest hat.
        payload = {"market_slug": "lol-big1-koia-2026-09-14", "closed": True,
                   "accepting_orders": False,
                   "tokens": [_tok("BIG", 0, False),
                              _tok("Movistar KOI Fenix", 1, True)]}
        sieger, grund = CA.sieger_aus_markt(payload)
        self.assertEqual(sieger, "Movistar KOI Fenix")
        self.assertEqual(grund, "")

    def test_offener_markt_hat_keinen_sieger_trotz_winner_flag(self):
        # PROVOKATION: ein Preis bei 0.99 und ein gesetztes Flag reichen NICHT. Ohne `closed`
        # waere das eine Abrechnung mitten im laufenden Spiel.
        p = _markt(closed=False, tokens=[_tok("A", 0.99, True), _tok("B", 0.01, False)])
        sieger, grund = CA.sieger_aus_markt(p)
        self.assertIsNone(sieger)
        self.assertEqual(grund, "Markt noch offen")

    def test_zwei_gewinner_flags_ergeben_keine_aufloesung(self):
        # PROVOKATION: waehlte die Funktion einfach den ersten, entschiede die Reihenfolge der
        # API-Antwort ueber Gewinn und Verlust.
        p = _markt(tokens=[_tok("A", 1, True), _tok("B", 1, True)])
        sieger, grund = CA.sieger_aus_markt(p)
        self.assertIsNone(sieger)
        self.assertEqual(grund, "mehrere Gewinner-Flags")

    def test_ohne_flag_entscheidet_der_settlement_preis(self):
        p = _markt(tokens=[_tok("A", 1.0), _tok("B", 0.0)])
        self.assertEqual(CA.sieger_aus_markt(p)[0], "A")

    def test_ohne_flag_und_ohne_eindeutigen_preis_keine_aufloesung(self):
        # PROVOKATION: 0.5/0.5 ist kein Ergebnis, sondern ein haengender Markt.
        p = _markt(tokens=[_tok("A", 0.5), _tok("B", 0.5)])
        sieger, grund = CA.sieger_aus_markt(p)
        self.assertIsNone(sieger)
        self.assertEqual(grund, "nicht eindeutig aufgeloest")

    def test_zwei_preise_nahe_eins_ergeben_keine_aufloesung(self):
        p = _markt(tokens=[_tok("A", 1.0), _tok("B", 0.995)])
        self.assertIsNone(CA.sieger_aus_markt(p)[0])

    def test_toleranz_greift_knapp_unter_eins(self):
        self.assertEqual(CA.sieger_aus_markt(_markt(tokens=[_tok("A", 0.985), _tok("B", 0.0)]))[0], "A")
        self.assertIsNone(CA.sieger_aus_markt(_markt(tokens=[_tok("A", 0.97), _tok("B", 0.0)]))[0])

    def test_gewinner_ohne_namen_wird_nicht_erfunden(self):
        p = _markt(tokens=[_tok("   ", 1, True), _tok("B", 0, False)])
        sieger, grund = CA.sieger_aus_markt(p)
        self.assertIsNone(sieger)
        self.assertEqual(grund, "Gewinner ohne Namen")

    def test_muell_antworten_werfen_nicht(self):
        for p in (None, [], "nein", {}, _markt(tokens=[]), {"closed": True}):
            sieger, grund = CA.sieger_aus_markt(p)
            self.assertIsNone(sieger)
            self.assertTrue(grund)


class OffeneKandidaten(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def _schreib(self, name, obj):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_track_und_wettdatei_werden_zusammengefuehrt(self):
        self._schreib("poly_shortlist_track.json", {"open": {
            "k1|A": {"key": "k1", "side": "A", "cond": "0xabc", "firstTs": "2026-09-14T10:00:00+00:00"},
        }})
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [
            {"key": "k1", "side": "A", "stake": 5, "status": "placed",
             "placedAt": "2026-09-14T18:00:00+00:00"},
        ]})
        k = CA.offene_kandidaten(self.dir)
        self.assertEqual(len(k), 1)
        # Die `cond` kommt aus dem Track, die Geld-Eigenschaft aus der Wett-Datei — genau die
        # Verbindung, die vorher niemand hergestellt hat.
        self.assertEqual(k[0]["cond"], "0xabc")
        self.assertTrue(k[0]["echt"])

    def test_wette_ohne_track_eintrag_faellt_nicht_durch(self):
        # PROVOKATION: genau so verschwand der Fall bisher — wer nur das Close-File (bzw. hier
        # nur den Track) liest, sieht eine Position mit Geld darauf gar nicht.
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [
            {"key": "einsam", "side": "A", "cond": "0xdd", "status": "placed"}]})
        k = CA.offene_kandidaten(self.dir)
        self.assertEqual([e["key"] for e in k], ["einsam"])
        self.assertTrue(k[0]["echt"])

    def test_abgerechnete_wetten_sind_keine_kandidaten(self):
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [
            {"key": "fertig", "status": "lost", "result": "LOSS"},
            {"key": "verkauft", "soldAt": "2026-09-01T00:00:00+00:00"},
            {"key": "offen", "status": "placed"}]})
        self.assertEqual([e["key"] for e in CA.offene_kandidaten(self.dir)], ["offen"])

    def test_echtes_geld_steht_vor_papier(self):
        self._schreib("poly_shortlist_track.json", {"open": {
            "alt|A": {"key": "alt", "side": "A", "cond": "0x1", "firstTs": "2026-01-01T00:00:00+00:00"},
            "neu|B": {"key": "neu", "side": "B", "cond": "0x2", "firstTs": "2026-09-14T00:00:00+00:00"},
        }})
        self._schreib("shortlist_auto_bets_placed.json", {"bets": [
            {"key": "neu", "status": "placed", "placedAt": "2026-09-14T00:00:00+00:00"}]})
        # PROVOKATION: sortierte man nur nach Alter, bekaeme der uralte Papier-Play das
        # Call-Budget und die Position mit echtem Geld ginge leer aus.
        self.assertEqual([e["key"] for e in CA.offene_kandidaten(self.dir)], ["neu", "alt"])

    def test_kaputte_datei_wirft_nicht(self):
        with open(os.path.join(self.dir, "poly_shortlist_track.json"), "w") as f:
            f.write("{kaputt")
        self.assertEqual(CA.offene_kandidaten(self.dir), [])


class Nachschlagen(unittest.TestCase):
    def _get(self, antworten, log):
        def get(url):
            log.append(url)
            return antworten.get(url)
        return get

    def test_bekannte_aufloesung_kostet_keinen_call(self):
        log = []
        neu, prob = CA.nachschlagen([{"key": "k", "cond": "0x1", "seite": "A"}],
                                    self._get({}, log), schon={"k": {"winner": "A"}})
        self.assertEqual(neu, {})
        self.assertEqual(log, [])

    def test_ohne_condition_id_wird_nicht_geraten(self):
        log = []
        neu, prob = CA.nachschlagen([{"key": "k", "cond": None, "seite": "A", "echt": True}],
                                    self._get({}, log))
        self.assertEqual(neu, {})
        self.assertEqual(log, [])
        self.assertEqual(prob[0]["grund"], "keine conditionId")
        self.assertTrue(prob[0]["echt"])

    def test_treffer_wird_als_aufloesung_geschrieben(self):
        url = CA.CLOB_MARKT.format(cond="0x1")
        log = []
        neu, prob = CA.nachschlagen(
            [{"key": "k", "cond": "0x1", "seite": "BIG"}],
            self._get({url: _markt(tokens=[_tok("KOI", 1, True), _tok("BIG", 0, False)])}, log))
        self.assertEqual(neu["k"]["winner"], "KOI")
        self.assertEqual(neu["k"]["quelle"], "clob")
        self.assertTrue(neu["k"]["ts"])
        self.assertEqual(prob, [])

    def test_call_budget_wird_eingehalten(self):
        log = []
        kand = [{"key": f"k{i}", "cond": f"0x{i}", "seite": "A"} for i in range(5)]
        neu, prob = CA.nachschlagen(kand, self._get({}, log), cap=2)
        self.assertEqual(len(log), 2)
        self.assertEqual(sum(1 for p in prob if p["grund"] == "Call-Budget erschoepft"), 3)

    def test_abrufsfehler_stoppt_den_lauf_nicht(self):
        def get(url):
            if url.endswith("0x1"):
                raise RuntimeError("Netz weg")
            return _markt(tokens=[_tok("A", 1, True)])
        neu, prob = CA.nachschlagen([{"key": "k1", "cond": "0x1", "seite": "A"},
                                     {"key": "k2", "cond": "0x2", "seite": "A"}], get)
        self.assertEqual(list(neu), ["k2"])
        self.assertIn("Abruf fehlgeschlagen", prob[0]["grund"])

    def test_derselbe_key_wird_nur_einmal_abgefragt(self):
        url = CA.CLOB_MARKT.format(cond="0x1")
        log = []
        get = self._get({url: _markt(tokens=[_tok("A", 1, True)])}, log)
        neu, prob = CA.nachschlagen([{"key": "k", "cond": "0x1", "seite": "A"},
                                     {"key": "k", "cond": "0x1", "seite": "A"}], get)
        self.assertEqual(len(log), 1)

    def test_buendel_ohne_festgenagelten_markt_bleibt_offen(self):
        # PROVOKATION: bei einem `-more-markets`-Slug bezeichnet „Over" ohne conditionId nicht
        # zwingend dieselbe Linie wie beim Erfassen. Lieber offen als geraten.
        url = CA.CLOB_MARKT.format(cond="0x1")
        get = self._get({url: _markt(tokens=[_tok("Over", 1, True), _tok("Under", 0, False)])}, [])
        import poly_slug_urteil as U
        echt = U.aufloesbar
        U.aufloesbar = lambda *a, **k: False
        CA.aufloesbar = U.aufloesbar
        try:
            neu, prob = CA.nachschlagen(
                [{"key": "epl-x-y-2026-09-12-more-markets", "cond": "0x1", "seite": "Over"}], get)
        finally:
            U.aufloesbar = echt
            CA.aufloesbar = echt
        self.assertEqual(neu, {})
        self.assertEqual(prob[0]["grund"], "Buendel ohne festgenagelten Markt")

    def test_muell_kandidaten_werfen_nicht(self):
        neu, prob = CA.nachschlagen([None, "x", {}, {"key": None}], self._get({}, []))
        self.assertEqual(neu, {})


class Bericht(unittest.TestCase):
    def test_echtes_geld_wird_namentlich_genannt(self):
        t = CA.bericht({}, [{"key": "big", "echt": True, "grund": "Markt noch offen"},
                            {"key": "papier", "echt": False, "grund": "keine conditionId"}])
        self.assertIn("big", t)
        self.assertIn("ECHTES GELD", t)
        # PROVOKATION: 18 Papier-Faelle je Lauf namentlich zu melden macht den Bericht unlesbar
        # und damit wertlos — sie zaehlen nur.
        self.assertNotIn("papier", t)

    def test_treffer_stehen_mit_sieger_drin(self):
        t = CA.bericht({"k": {"winner": "KOI", "ts": "x", "quelle": "clob"}}, [])
        self.assertIn("k", t)
        self.assertIn("KOI", t)


if __name__ == "__main__":
    unittest.main()
