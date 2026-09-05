#!/usr/bin/env python3
"""
05.09.2026 (Lucas): „nun sieht man zwar line aber nicht welche Seite — Over oder Under".

Auf der Karte stand „💰 $32.7K auf Manchester City FC vs. Coventry City FC: O/U 3.5".
Die Linie war da, die SEITE weg — der Aufrufer ersetzte `side` durch die Marktfrage.

Zwei Defekte uebereinander:
  · `_linie_kurz` suchte „over 3.5"; Polymarket schreibt „O/U 3.5". Gemessen ueber den
    Bestand: von 344 Maerkten mit rein generischen Ausgaengen tragen 42 eine Frage — die
    alte Regex griff bei **0 von 42**. Sie fiel also IMMER auf `return frage` durch.
  · Der Aufrufer setzte `_label = _lin` statt die Seite zu ERGAENZEN.
"""
import re
import unittest

import poly_whale_watch as W

FRAGE = "Manchester City FC vs. Coventry City FC: O/U 3.5"
ALT = re.compile(r"\b(over|under|ueber|über)\s*(\d+(?:[.,]\d+)?)", re.I)


class TestLinie(unittest.TestCase):
    def test_polymarkets_echte_Schreibweise(self):
        self.assertEqual(W._linie_zahl(FRAGE), "3.5")
        self.assertEqual(W._linie_zahl("PFC Nasaf vs. FK Neftchi Fargona: O/U 1.5"), "1.5")
        self.assertEqual(W._linie_zahl("X vs. Y: Over/Under 2.5"), "2.5")
        self.assertEqual(W._linie_zahl("Spiel: Über 2,5 Tore"), "2.5")

    def test_die_alte_Regex_griff_bei_keiner_davon(self):
        """Der Beleg, dass es kein Randfall war: die alte Suche findet in Polymarkets
        Schreibweise nichts — und der Rueckfall gab die ganze Frage zurueck."""
        for f in (FRAGE, "PFC Nasaf vs. FK Neftchi Fargona: O/U 1.5", "X vs. Y: O/U 2.5"):
            self.assertIsNone(ALT.search(f))
            self.assertIsNotNone(W._linie_zahl(f))

    def test_ohne_Linie_keine_erfundene(self):
        self.assertIsNone(W._linie_zahl("Both Teams To Score"))
        self.assertIsNone(W._linie_zahl(None))
        self.assertIsNone(W._linie_zahl(""))


class TestAusgangLabel(unittest.TestCase):
    def test_die_Seite_wird_nie_ersetzt(self):
        """Der Kern des Funds."""
        self.assertEqual(W.ausgang_label("Over", FRAGE), "Over 3.5")
        self.assertEqual(W.ausgang_label("Under", FRAGE), "Under 3.5")

    def test_die_ganze_Frage_landet_nie_im_Label(self):
        for seite in ("Over", "Under", "Yes", "No"):
            lab = W.ausgang_label(seite, FRAGE)
            self.assertTrue(lab.startswith(seite), lab)
            self.assertNotEqual(lab, FRAGE)
            self.assertNotIn("Manchester City FC vs.", lab,
                             "der Paarungs-Vorspann gehoert nicht ins Ausgangs-Label")

    def test_Linie_nur_an_Over_Under(self):
        """„Yes 3.5" waere Beinahe-Richtigkeit — genau die Sorte, die Leeds-Brentford verursacht hat."""
        self.assertEqual(W.ausgang_label("Yes", FRAGE), "Yes — O/U 3.5")
        self.assertNotIn("Yes 3.5", str(W.ausgang_label("Yes", FRAGE)))

    def test_Teamname_bleibt_unveraendert(self):
        self.assertEqual(W.ausgang_label("Manchester City FC", FRAGE), "Manchester City FC")
        self.assertEqual(W.ausgang_label("Manchester City FC", None), "Manchester City FC")

    def test_generisch_ohne_Frage_ist_nicht_benennbar(self):
        """Ein nacktes „Over" bleibt verboten — fehlende Information ist keine Erlaubnis."""
        self.assertIsNone(W.ausgang_label("Over", None))
        self.assertIsNone(W.ausgang_label("Under", ""))

    def test_leere_Seite(self):
        self.assertIsNone(W.ausgang_label(None, FRAGE))
        self.assertIsNone(W.ausgang_label("", FRAGE))

    def test_BTTS_behaelt_seine_Seite_und_bekommt_Kontext(self):
        self.assertEqual(W.ausgang_label("Yes", "Man City vs. Coventry: Both Teams To Score"),
                         "Yes — Both Teams To Score")


class TestKarten(unittest.TestCase):
    def _pos(self):
        return {"wallet": "0xa", "usd": 32700, "key": "epl-mac-cov-2026-09-05-more-markets",
                "side": "Over", "league": "EPL", "firstPrice": 0.47}

    def _broad(self):
        return {"epl-mac-cov-2026-09-05-more-markets": {
            "frage": FRAGE, "prices": {"Over": 0.52, "Under": 0.48}, "totalUsd": 200000}}

    def test_beide_Kanaele_nennen_dieselbe_Seite(self):
        """Vorher: Public zeigte die Marktfrage, Trades das nackte „Over". Zwei Kanaele,
        zwei verschiedene Auskuenfte ueber dieselbe Wette."""
        trades = W.build_card(self._pos(), {}, False, self._broad())
        self.assertIn("Over 3.5", trades)
        self.assertNotIn("auf <b>Over</b>", trades)
        self.assertNotIn("Coventry City FC: O/U 3.5</b>", trades)


if __name__ == "__main__":
    unittest.main()


class TestGegenEchteDaten(unittest.TestCase):
    """Der Test, der gefehlt hat: gegen den ECHTEN Bestand statt gegen eine erfundene Frage.

    Der alte Test benutzte „Will there be over 2.5 goals…" — eine Schreibweise, die Polymarket
    nie liefert. Er war gruen, waehrend die Produktion bei 0 von 42 Faellen richtig lag.
    """
    import os as _os
    from pathlib import Path as _Path
    DATEI = _Path(__file__).resolve().parent.parent / "poly_money_broad_close.json"

    def test_jeder_generische_Markt_mit_Frage_ist_benennbar(self):
        if not self.DATEI.exists():
            self.skipTest("Artefakt nicht vorhanden")
        import json
        d = json.loads(self.DATEI.read_text(encoding="utf-8"))
        geprueft = 0
        for k, v in d.items():
            if not isinstance(v, dict):
                continue
            outs = list((v.get("prices") or {}).keys())
            frage = v.get("frage")
            if not outs or not frage:
                continue
            if not all(str(o).strip().lower() in W._PUB_GENERISCH for o in outs):
                continue
            for seite in outs:
                lab = W.ausgang_label(seite, frage)
                geprueft += 1
                self.assertIsNotNone(lab, f"{k}/{seite}: kein Label trotz Frage")
                self.assertTrue(lab.startswith(str(seite)),
                                f"{k}: Label '{lab}' verschweigt die Seite '{seite}'")
                self.assertNotEqual(lab, frage, f"{k}: die ganze Frage als Label")
        self.assertGreater(geprueft, 0, "keine passenden Maerkte im Bestand — Test wertlos")

    def test_die_Linie_steht_an_jeder_Over_Under_Seite(self):
        if not self.DATEI.exists():
            self.skipTest("Artefakt nicht vorhanden")
        import json
        d = json.loads(self.DATEI.read_text(encoding="utf-8"))
        ohne = []
        for k, v in d.items():
            if not isinstance(v, dict) or not v.get("frage"):
                continue
            for seite in (v.get("prices") or {}):
                if str(seite).strip().lower() not in W._OU_SEITEN:
                    continue
                if W._linie_zahl(v["frage"]) is None:
                    ohne.append((k, v["frage"]))
        self.assertEqual(ohne[:3], [], f"{len(ohne)} Over/Under-Maerkte ohne lesbare Linie")
