#!/usr/bin/env python3
"""
tests/test_wallet_profit_nachtrag.py — 22.09.2026: 15.085 abgerechnete Positionen, die die
ganze Zeit im Repo standen.

🔴 Lucas, zweimal am selben Tag: „Mir ist wirklich wichtig, dass wir den Profit und den ROI der
letzten sieben und 30 Tage mit tracken … Lifetime ist nett, sagt aber wenig aus, vor allem bei
alten Wallets."

Die Geld-Messung läuft seit heute. Eine Wallet bekommt ihre erste Zeile aber erst, wenn eine
ihrer Positionen NACH heute auflöst — die 30-Tage-Bilanz wäre also erst Ende Oktober
vollständig, und bis dahin stünde genau die Zahl leer, auf die es ankommt.

Sie muss nicht leer stehen: `poly_wallet_track.json` wird bei jedem Scan committet und trägt in
`open` Wallet, Einstieg, Grösse und Preis. Gemessen über 35 Tage: 1.561 Commits, 33.258
Positionen, davon 32.480 geschlossen und **15.085 mit eindeutiger Auflösung**.

Fehlerklasse: **eine Messung, die bei null anfängt, obwohl ihre Vergangenheit erfasst ist.**

Was die Rekonstruktion ehrlich hält, steht in den letzten beiden Klassen: sie schreibt in ein
eigenes Feld, und sie hört beim heutigen Tag auf.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poly_money_broad as B
import wallet_profit_nachtragen as N


def _pos(wallet="0xw", key="epl-a-b", side="A", usd=100, last=0.50, entry=0.50, cond=None):
    e = {"wallet": wallet, "key": key, "side": side, "usd": usd,
         "lastPrice": last, "entryPrice": entry}
    if cond:
        e["cond"] = cond
    return {"%s|%s|%s" % (wallet, key, side): e}


def _res(key="epl-a-b", winner="A", tag="2026-09-18"):
    return {key: {"winner": winner, "ts": tag + "T20:00:00+00:00"}}


HEUTE = "2026-09-22"


class TestDieRekonstruktion(unittest.TestCase):
    def test_eine_geschlossene_position_wird_gebucht(self):
        n = N.nachtrag_tage(_pos(), _res(), set(), HEUTE)
        self.assertEqual(n, {"0xw": {"2026-09-18": [1, 100.0, 100.0]}})

    def test_ein_verlust_ebenfalls(self):
        n = N.nachtrag_tage(_pos(), _res(winner="B"), set(), HEUTE)
        self.assertEqual(n["0xw"]["2026-09-18"], [1, -100.0, 100.0])

    def test_zwei_positionen_am_selben_tag_summieren_sich(self):
        p = {}
        p.update(_pos(key="a"))
        p.update(_pos(key="b", usd=50))
        r = {}
        r.update(_res(key="a"))
        r.update(_res(key="b", winner="B"))
        n = N.nachtrag_tage(p, r, set(), HEUTE)
        self.assertEqual(n["0xw"]["2026-09-18"], [2, 50.0, 150.0])

    def test_der_tag_kommt_aus_der_aufloesung_nicht_aus_dem_lauf(self):
        """Wann der Markt aufloeste, ist der ehrliche Zeitpunkt — nicht, wann wir es bemerkt
        haben. Sonst landet eine 30 Tage alte Wette im Sieben-Tage-Fenster."""
        n = N.nachtrag_tage(_pos(), _res(tag="2026-08-30"), set(), HEUTE)
        self.assertIn("2026-08-30", n["0xw"])


class TestWasSieAuslaesst(unittest.TestCase):
    def test_eine_noch_offene_position(self):
        offen = set(_pos())
        self.assertEqual(N.nachtrag_tage(_pos(), _res(), offen, HEUTE), {})

    def test_ohne_aufloesung(self):
        self.assertEqual(N.nachtrag_tage(_pos(), {}, set(), HEUTE), {})

    def test_ein_mehrdeutiges_buendel(self):
        """⭐ „Under" in einem `-more-markets`-Buendel ohne Marktkennung ist ein Muenzwurf —
        dieselbe Regel wie ueberall (`aufloesbar`). Gemessen fallen so 1.889 Positionen heraus,
        statt einen geratenen Ausgang zu bekommen."""
        p = _pos(key="ucl-a-b-more-markets", side="Under")
        r = _res(key="ucl-a-b-more-markets", winner="Under")
        self.assertEqual(N.nachtrag_tage(p, r, set(), HEUTE), {})

    def test_ein_buendel_mit_marktkennung_zaehlt(self):
        p = _pos(key="ucl-a-b-more-markets", side="Under", cond="0xAAA")
        r = _res(key="ucl-a-b-more-markets", winner="Under")
        self.assertEqual(N.nachtrag_tage(p, r, set(), HEUTE)["0xw"]["2026-09-18"][0], 1)

    def test_ohne_brauchbaren_preis(self):
        self.assertEqual(N.nachtrag_tage(_pos(last=0), _res(), set(), HEUTE), {})

    def test_ohne_wallet(self):
        p = _pos(); list(p.values())[0]["wallet"] = ""
        self.assertEqual(N.nachtrag_tage(p, _res(), set(), HEUTE), {})


class TestSieHoertBeimHeutigenTagAuf(unittest.TestCase):
    """⭐ Der Riegel gegen das Doppeln — per Bauart, nicht per Sorgfalt. Der laufende Betrieb
    schreibt ab heute; alles davor kann er nicht mehr nachholen."""

    def test_heute_wird_nicht_nachgetragen(self):
        self.assertEqual(N.nachtrag_tage(_pos(), _res(tag=HEUTE), set(), HEUTE), {})

    def test_gestern_schon(self):
        self.assertIn("2026-09-21", N.nachtrag_tage(_pos(), _res(tag="2026-09-21"),
                                                    set(), HEUTE)["0xw"])

    def test_morgen_erst_recht_nicht(self):
        self.assertEqual(N.nachtrag_tage(_pos(), _res(tag="2026-09-23"), set(), HEUTE), {})


class TestSieBleibtErkennbar(unittest.TestCase):
    """Rekonstruiert ist nicht gemessen. Beides in denselben Eimer zu kippen wäre genau die
    Sorte Zahl, der man später nicht mehr ansieht, woher sie kommt."""

    def test_sie_schreibt_in_ein_eigenes_feld(self):
        track = {"scores": {"0xw": {"n": 9, "tage": {"2026-09-21": [1, 0.5, 1, 0.5]}}}}
        N.einpflegen(track, {"0xw": {"2026-09-18": [1, 100.0, 100.0]}})
        s = track["scores"]["0xw"]
        self.assertEqual(s["tageNachtrag"], {"2026-09-18": [1, 100.0, 100.0]})
        self.assertEqual(s["tage"], {"2026-09-21": [1, 0.5, 1, 0.5]}, "der Betrieb bleibt unberührt")

    def test_zweimal_laufen_aendert_nichts(self):
        track = {"scores": {"0xw": {"n": 9}}}
        N.einpflegen(track, {"0xw": {"2026-09-18": [1, 100.0, 100.0]}})
        einmal = json_kopie(track)
        N.einpflegen(track, {"0xw": {"2026-09-18": [1, 100.0, 100.0]}})
        self.assertEqual(track, einmal)

    def test_eine_unbekannte_wallet_wird_nicht_erfunden(self):
        track = {"scores": {}}
        self.assertEqual(N.einpflegen(track, {"0xfremd": {"2026-09-18": [1, 1.0, 1.0]}}), 0)
        self.assertEqual(track["scores"], {})

    def test_die_bilanz_weist_ihn_getrennt_aus(self):
        s = {"tage": {"2026-09-21": [3, 1.5, 2, 4.0]},
             "tageNachtrag": {"2026-09-18": [5, 120.0, 300.0]}}
        b = B.zeitraum_bilanz(s, "2026-09-22", 7)
        self.assertEqual(b["gewinn"], 120.0)
        self.assertEqual((b["nGeld"], b["nGeldNachtrag"]), (5, 5))
        self.assertEqual(b["n"], 3, "die CLV-Basis bleibt die des Betriebs")

    def test_ein_zeitraum_ganz_ohne_betrieb_ist_trotzdem_eine_auskunft(self):
        """Vor dem 17.09. gibt es `tage` gar nicht — und genau dort liegt der grösste Teil
        einer 30-Tage-Frage."""
        b = B.zeitraum_bilanz({"tageNachtrag": {"2026-09-01": [9, 500.0, 1000.0]}},
                              "2026-09-22", 30)
        self.assertEqual((b["gewinn"], b["roi"], b["nGeld"]), (500.0, 0.5, 9))
        self.assertEqual(b["nGeldNachtrag"], 9,
                         "auch hier muss dastehen, dass die Zahl rekonstruiert ist — sonst ist "
                         "sie ausgerechnet dort nicht als solche erkennbar, wo sie ALLEIN steht")
        self.assertIsNone(b["clv"], "ohne Betrieb gibt es keinen CLV — und None sagt das")


def json_kopie(x):
    import json
    return json.loads(json.dumps(x))


if __name__ == "__main__":
    unittest.main()


class TestDieAnzeigeSagtDassEsRueckgerechnetIst(unittest.TestCase):
    """⭐ Wer das nicht dazuschreibt, verkauft eine Rückrechnung als laufende Messung — und in
    drei Wochen weiss niemand mehr, welche es war."""

    def setUp(self):
        import poly_whale_watch
        self.W = poly_whale_watch

    def _f(self, nach):
        return {"gewinn": 7500, "einsatz": 5000, "roi": 1.5, "n": 9, "nGeld": 9,
                "nGeldNachtrag": nach}

    def test_ganz_rueckgerechnet(self):
        self.assertIn("rückgerechnet", self.W._geld_zeile(self._f(9)))

    def test_teils_rueckgerechnet(self):
        self.assertIn("teils rückgerechnet", self.W._geld_zeile(self._f(4)))

    def test_rein_gemessen_traegt_keinen_zusatz(self):
        t = self.W._geld_zeile(self._f(0))
        self.assertNotIn("rückgerechnet", t)
