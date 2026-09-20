#!/usr/bin/env python3
"""test_sell_versuch_im_buch.py — ein gescheiterter Verkauf muss eine Spur hinterlassen.

Vorfall 19.09.2026 (Lucas: „es wurde vorm spielstart nicht geschlossen und ist nun lost").
Toulouse–Le Havre lief ins Spiel. Im Buch stand danach genau das, was auch dort stuende,
waere der Manager nie gelaufen: `status: "placed"` und sonst nichts. `update_auto_bet_status`
lief NUR bei `sell_result["status"] == "placed"`.

Fehlerklasse: eine Wirkung, die ausbleibt, hinterlaesst keine Spur.

Der Quelltest unten prueft nicht, dass eine Zeichenkette vorkommt — das haelt jeder
Umbenennung stand und keiner Loeschung. Er prueft, dass die drei Nicht-Erfolgs-Ausgaenge
im Code tatsaechlich `vermerke_sell_versuch` aufrufen, indem er den Aufruf zaehlt.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import manage_wm_poly_positions as M  # noqa: E402

NOW = "2026-09-19T17:06:00+00:00"


def _bet(**kw):
    b = {"betKey": "96-111-Under 2.5 Tore", "home": "Toulouse", "away": "Le Havre",
         "market": "Under 2.5 Tore", "status": "placed", "stake": 5.5,
         "kickoff": "2026-09-19T18:45:00Z"}
    b.update(kw)
    return b


class TestVersuchEintragen(unittest.TestCase):
    def test_der_erste_gescheiterte_versuch_steht_im_buch(self):
        b = M.versuch_eintragen(_bet(), "Order abgelehnt", "Pre-Match Close (1.65h vor Anpfiff)",
                                0.42, "not enough balance", NOW)
        self.assertEqual(b["sellVersuche"], 1)
        self.assertEqual(b["sellVersuchGrund"], "Order abgelehnt")
        self.assertEqual(b["sellFehler"], "not enough balance")
        self.assertEqual(b["sellVersuchAm"], NOW)
        self.assertEqual(b["sellVersuchPreis"], 0.42)

    def test_die_wette_bleibt_offen(self):
        """Ein gescheiterter Verkauf ist kein Verkauf. Wer hier `status` anfasst, faelscht
        das Buch in die andere Richtung — genau der Schaden vom 18.09.
        (`check_geschlossen_heisst_belegt`)."""
        b = M.versuch_eintragen(_bet(), "Auto-Sell aus (Secret/Schalter)", "x", 0.42, None, NOW)
        self.assertEqual(b["status"], "placed")

    def test_versuche_zaehlen_hoch(self):
        b = _bet()
        for i in range(3):
            M.versuch_eintragen(b, "Order abgelehnt", "x", 0.42, "boom", NOW)
        self.assertEqual(b["sellVersuche"], 3)

    def test_kaputter_zaehler_blockiert_nicht(self):
        b = M.versuch_eintragen(_bet(sellVersuche="viele"), "g", "x", 0.4, None, NOW)
        self.assertEqual(b["sellVersuche"], 1)

    def test_ohne_fehlertext_kein_erfundener_fehler(self):
        b = M.versuch_eintragen(_bet(), "Auto-Sell aus (Secret/Schalter)", "x", 0.4, None, NOW)
        self.assertNotIn("sellFehler", b)


class TestBuchSchreiben(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                               encoding="utf-8")
        json.dump({"bets": [_bet(), _bet(betKey="andere")]}, self.tmp)
        self.tmp.close()
        self._alt = M.AUTO_BETS_FILE
        M.AUTO_BETS_FILE = self.tmp.name

    def tearDown(self):
        M.AUTO_BETS_FILE = self._alt
        Path(self.tmp.name).unlink(missing_ok=True)

    def _buch(self):
        return json.loads(Path(self.tmp.name).read_text(encoding="utf-8"))

    def test_nur_die_getroffene_zeile_wird_angefasst(self):
        M.vermerke_sell_versuch("96-111-Under 2.5 Tore", "Order abgelehnt", "Pre-Match Close",
                                0.42, "boom")
        bets = {b["betKey"]: b for b in self._buch()["bets"]}
        self.assertEqual(bets["96-111-Under 2.5 Tore"]["sellVersuche"], 1)
        self.assertNotIn("sellVersuche", bets["andere"])

    def test_unbekannter_betkey_schreibt_nichts(self):
        vorher = Path(self.tmp.name).read_text(encoding="utf-8")
        M.vermerke_sell_versuch("gibtsnicht", "g", "x", 0.4, None)
        self.assertEqual(Path(self.tmp.name).read_text(encoding="utf-8"), vorher)

    def test_leerer_betkey_schreibt_nichts(self):
        vorher = Path(self.tmp.name).read_text(encoding="utf-8")
        M.vermerke_sell_versuch("", "g", "x", 0.4, None)
        self.assertEqual(Path(self.tmp.name).read_text(encoding="utf-8"), vorher)


    def test_die_spaetere_bewertung_loescht_die_spur_nicht(self):
        """`persist_auto_bet_valuations` schreibt NACH der Schleife dieselbe Datei neu
        (Zeile 1039). Wuerde sie den Versuch mitnehmen, waere der Vermerk nach jedem Lauf
        wieder weg — dieselbe Klasse, nur eine Etage tiefer."""
        M.vermerke_sell_versuch("96-111-Under 2.5 Tore", "Order abgelehnt", "Pre-Match Close",
                                0.42, "boom")
        M.persist_auto_bet_valuations([{"_betKey": "96-111-Under 2.5 Tore",
                                        "currentPrice": 0.74, "pnlPct": 64.4,
                                        "priceSource": "live_bid"}])
        b = {x["betKey"]: x for x in self._buch()["bets"]}["96-111-Under 2.5 Tore"]
        self.assertEqual(b["sellVersuche"], 1)
        self.assertEqual(b["sellVersuchGrund"], "Order abgelehnt")
        self.assertEqual(b["currentPrice"], 0.74)


class TestJederAusgangSchreibt(unittest.TestCase):
    def test_alle_nicht_erfolgs_pfade_rufen_den_vermerk(self):
        """Drei Ausgaenge fuehren am Verkauf vorbei: Order abgelehnt, Auto-Sell aus,
        tokenId fehlt. Loescht jemand einen der beiden Aufrufe, faellt dieser Test."""
        q = (REPO / "manage_wm_poly_positions.py").read_text(encoding="utf-8")
        koerper = q.split("def main():", 1)[1]
        self.assertEqual(koerper.count("vermerke_sell_versuch("), 2, koerper.count(
            "vermerke_sell_versuch("))
        self.assertIn('_grund = "Auto-Sell aus (Secret/Schalter)"', koerper)
        self.assertIn('_grund = "tokenId fehlt — nicht verkaufbar"', koerper)

    def test_der_erfolgspfad_bleibt_unberuehrt(self):
        q = (REPO / "manage_wm_poly_positions.py").read_text(encoding="utf-8")
        self.assertIn('new_status="sold"', q)


if __name__ == "__main__":
    unittest.main()
