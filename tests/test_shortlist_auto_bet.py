#!/usr/bin/env python3
"""
tests/test_shortlist_auto_bet.py — 14.09.2026: der „Heute spielenswert"-Auto-Play und die
gemeinsame Offen-Definition.

Jede Schranke wird PROVOZIERT, nicht bloss im Gutfall abgefragt: zu jedem Test gehoert ein
Fall, der ohne die Schranke echtes Geld gekostet haette.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import poly_offen as PO
import shortlist_auto_bet as SAB


def _ts(minuten_alt=0, jetzt=None):
    jetzt = jetzt or datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    return (jetzt - timedelta(minutes=minuten_alt)).isoformat()


JETZT = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


class TestOffeneDefinition(unittest.TestCase):
    """poly_offen.ist_offen — der Deckel haengt daran."""

    def test_frische_wette_ist_offen(self):
        self.assertTrue(PO.ist_offen({"status": "placed", "stake": 5}))

    def test_ohne_jede_information_ist_offen(self):
        # Harmloser Default bei einem RISIKO-Deckel heisst „blockiert", nicht „frei".
        self.assertTrue(PO.ist_offen({"stake": 5}))

    def test_der_echte_fehler_verlorene_wette_zaehlt_nicht_mehr(self):
        # Genau die vier Zeilen aus wm_auto_bets_placed.json vom 14.09.2026: $22,00, die den
        # $80-Deckel blockierten, obwohl sie im Juni terminal wurden.
        bets = [
            {"status": "lost", "result": "LOSS", "stake": 5.5, "resolvedAt": "2026-06-13T22:07:09Z"},
            {"status": "lost", "result": "LOSS", "stake": 5.5, "resolvedAt": "2026-06-23T21:27:35Z"},
            {"status": "lost", "result": "LOSS", "stake": 5.5, "resolvedAt": "2026-06-23T22:17:43Z"},
            {"status": "sold", "stake": 5.5},
        ]
        alt = sum(b["stake"] for b in bets
                  if not b.get("resolved") and not b.get("soldAt"))
        self.assertEqual(alt, 22.0, "Gegenprobe: die alte Regel zaehlte wirklich $22")
        self.assertEqual(PO.offene_summe(bets), (0.0, 0))

    def test_dry_run_bindet_kein_geld(self):
        self.assertFalse(PO.ist_offen({"status": "dry-run", "stake": 5}))

    def test_summe_und_anzahl(self):
        bets = [{"status": "placed", "stake": 5}, {"status": "lost", "stake": 5},
                {"status": "placed", "stake": 7.5}]
        self.assertEqual(PO.offene_summe(bets), (12.5, 2))

    def test_shortlist_praefix_ist_dabei(self):
        # Fehlt er, zaehlt der Pinnacle-Trader die Shortlist-Positionen nicht → beide setzen
        # gegen denselben Deckel, ohne voneinander zu wissen.
        self.assertIn("shortlist_", PO.DATENSATZ_PRAEFIXE)


class TestFaelligeZeilen(unittest.TestCase):

    def _z(self, k="a", side="Home", conv=8, alt_min=5, preis=0.5):
        return {"k": f"{k}|{side}", "key": k, "side": side, "conv": conv,
                "sentAt": _ts(alt_min), "pushPreis": preis}

    def test_frische_zeile_kommt_durch(self):
        aus = SAB.faellige_zeilen([self._z()], set(), jetzt=JETZT)
        self.assertEqual(len(aus), 1)

    def test_schon_gesetzte_zeile_nicht_nochmal(self):
        z = self._z()
        self.assertEqual(SAB.faellige_zeilen([z], {"a|Home"}, jetzt=JETZT), [])

    def test_alter_push_wird_nicht_nachgesetzt(self):
        # Ohne diese Schranke haette ein Lauf nach einer Panne das ganze Buch auf einmal
        # nachgesetzt — dieselbe Klasse wie die Push-Flut im August, nur mit Geld.
        self.assertEqual(SAB.faellige_zeilen([self._z(alt_min=600)], set(), jetzt=JETZT), [])

    def test_ohne_zeitstempel_wird_nicht_gesetzt(self):
        z = self._z()
        z["sentAt"] = None
        self.assertEqual(SAB.faellige_zeilen([z], set(), jetzt=JETZT), [])

    def test_ohne_push_preis_wird_nicht_gesetzt(self):
        z = self._z()
        z["pushPreis"] = None
        self.assertEqual(SAB.faellige_zeilen([z], set(), jetzt=JETZT), [])

    def test_staerkste_conviction_zuerst(self):
        zs = [self._z("a", conv=6), self._z("b", conv=9), self._z("c", conv=7)]
        aus = SAB.faellige_zeilen(zs, set(), jetzt=JETZT)
        self.assertEqual([z["key"] for z in aus], ["b", "c", "a"])


class TestToken(unittest.TestCase):

    FEED = {"m1": {"tokens": {"Over": "T-OVER", "Under": "T-UNDER"}}}

    def test_token_wird_gefunden(self):
        self.assertEqual(SAB.token_aus_feed(self.FEED, "m1", "Under"), "T-UNDER")

    def test_unbekannte_seite_gibt_none_statt_irgendwas(self):
        # Ein falscher Token ist eine Wette auf den ANDEREN Ausgang — hier darf nie geraten werden.
        self.assertIsNone(SAB.token_aus_feed(self.FEED, "m1", "Draw"))

    def test_unbekannter_markt_gibt_none(self):
        self.assertIsNone(SAB.token_aus_feed(self.FEED, "m2", "Under"))


class TestPreisUrteil(unittest.TestCase):

    def test_gleicher_preis_ist_ok(self):
        ok, _ = SAB.preis_urteil(0.50, 0.50)
        self.assertTrue(ok)

    def test_kleiner_aufschlag_ist_ok(self):
        ok, _ = SAB.preis_urteil(0.50, 0.52)
        self.assertTrue(ok)

    def test_zu_teuer_gegenueber_dem_push(self):
        # Der Versuch misst, was der PUSH wert war. 8pp teurer einzukaufen misst etwas anderes.
        ok, grund = SAB.preis_urteil(0.50, 0.58)
        self.assertFalse(ok)
        self.assertIn("Push-Preis", grund)

    def test_billiger_ist_immer_ok(self):
        ok, _ = SAB.preis_urteil(0.50, 0.41)
        self.assertTrue(ok)

    def test_quasi_lock_wird_abgelehnt(self):
        ok, grund = SAB.preis_urteil(0.95, 0.95)
        self.assertFalse(ok)
        self.assertIn("Hoechstpreis", grund)

    def test_unter_mindestpreis_abgelehnt(self):
        ok, grund = SAB.preis_urteil(0.10, 0.10)
        self.assertFalse(ok)
        self.assertIn("Mindestpreis", grund)

    def test_kein_ask_kein_kauf(self):
        ok, _ = SAB.preis_urteil(0.50, None)
        self.assertFalse(ok)


class TestLiquiditaet(unittest.TestCase):

    def test_genug_volumen(self):
        buch = {"asks": [[0.50, 100]]}          # 100 Shares = $50 zu 50c
        self.assertTrue(SAB.liquide(buch, 5.0, 0.50))

    def test_zu_duenn(self):
        buch = {"asks": [[0.50, 3]]}            # 3 Shares = $1,50
        self.assertFalse(SAB.liquide(buch, 5.0, 0.50))

    def test_teurere_level_zaehlen_nicht_mit(self):
        # Volumen ueber dem erlaubten Preis wuerde den Slippage-Deckel aushebeln.
        buch = {"asks": [[0.50, 2], [0.70, 1000]]}
        self.assertFalse(SAB.liquide(buch, 5.0, 0.50))

    def test_ohne_buch_nicht_liquide(self):
        self.assertFalse(SAB.liquide(None, 5.0, 0.50))


class TestHandelnErlaubt(unittest.TestCase):

    def test_normalfall(self):
        ok, _ = SAB.handeln_erlaubt(balance=50, offen=10, stake=5, max_offen=100)
        self.assertTrue(ok)

    def test_deckel_greift_genau_an_der_grenze(self):
        ok, _ = SAB.handeln_erlaubt(balance=500, offen=95, stake=5, max_offen=100)
        self.assertTrue(ok, "95+5 = 100 ist noch erlaubt")
        ok, grund = SAB.handeln_erlaubt(balance=500, offen=95.01, stake=5, max_offen=100)
        self.assertFalse(ok)
        self.assertIn("Exposure-Deckel", grund)

    def test_leere_wallet_setzt_nicht(self):
        ok, grund = SAB.handeln_erlaubt(balance=0.03, offen=0, stake=5, max_offen=100)
        self.assertFalse(ok)
        self.assertIn("Balance", grund)

    def test_puffer_bleibt_stehen(self):
        ok, _ = SAB.handeln_erlaubt(balance=5.5, offen=0, stake=5, max_offen=100, puffer=1.0)
        self.assertFalse(ok, "5,50 - 5,00 = 0,50 < 1,00 Puffer")


class TestAbrechnung(unittest.TestCase):

    def _bet(self, k="m1|Home", fill=0.5, stake=5.0):
        return {"betKey": k, "status": "placed", "polyPrice": fill, "stake": stake}

    def test_treffer_zahlt_auf_den_echten_fuellpreis(self):
        bets = [self._bet(fill=0.5)]
        track = {"settled": [{"key": "m1", "side": "Home", "result": "win", "winner": "Home"}]}
        SAB.abgleichen(bets, track, jetzt=JETZT)
        self.assertEqual(bets[0]["status"], "won")
        self.assertAlmostEqual(bets[0]["pnl"], 5.0)      # 5/0,5 - 5
        self.assertFalse(PO.ist_offen(bets[0]))

    def test_niete_kostet_den_einsatz(self):
        bets = [self._bet()]
        track = {"settled": [{"key": "m1", "side": "Home", "result": "loss"}]}
        SAB.abgleichen(bets, track, jetzt=JETZT)
        self.assertEqual(bets[0]["pnl"], -5.0)

    def test_papier_gibt_auf_geld_bleibt_gebunden(self):
        # DER Punkt: der Tracker schreibt eine Zeile ab, die Position auf Poly lebt weiter.
        # Wuerde hier Exposure freigegeben, waere der Deckel eine Erfindung.
        bets = [self._bet()]
        track = {"unaufloesbar": [{"key": "m1", "side": "Home", "grund": "nicht getrackt"}]}
        SAB.abgleichen(bets, track, jetzt=JETZT)
        self.assertTrue(bets[0]["haengt"])
        self.assertTrue(PO.ist_offen(bets[0]), "haengende Position bindet weiter Geld")
        self.assertEqual(SAB.haengende(bets), (5.0, 1))

    def test_abrechnung_ist_idempotent(self):
        bets = [self._bet()]
        track = {"settled": [{"key": "m1", "side": "Home", "result": "win"}]}
        self.assertEqual(SAB.abgleichen(bets, track, jetzt=JETZT), 1)
        self.assertEqual(SAB.abgleichen(bets, track, jetzt=JETZT), 0)

    def test_fremde_zeile_ruehrt_die_wette_nicht_an(self):
        bets = [self._bet()]
        track = {"settled": [{"key": "m2", "side": "Home", "result": "win"}]}
        SAB.abgleichen(bets, track, jetzt=JETZT)
        self.assertEqual(bets[0]["status"], "placed")


class TestKillSwitch(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def _schreib(self, name, inhalt):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            f.write(inhalt)

    def test_ohne_datei_laeuft_es(self):
        self.assertEqual(SAB.kill_switch(self.dir), (False, ""))

    def test_fremder_kill_switch_stoppt_auch_uns(self):
        # „Handel aus" heisst nicht „ausser dem Shortlist-Bot" — es ist dieselbe Wallet.
        self._schreib("liga_kill_switch.json", json.dumps({"enabled": False, "reason": "Drawdown"}))
        gestoppt, grund = SAB.kill_switch(self.dir)
        self.assertTrue(gestoppt)
        self.assertIn("Drawdown", grund)

    def test_kaputte_datei_stoppt_fail_closed(self):
        self._schreib("wm_kill_switch.json", "{kaputt")
        gestoppt, grund = SAB.kill_switch(self.dir)
        self.assertTrue(gestoppt)
        self.assertIn("korrupt", grund)

    def test_eingeschaltet_laesst_durch(self):
        self._schreib("wm_kill_switch.json", json.dumps({"enabled": True}))
        self.assertEqual(SAB.kill_switch(self.dir), (False, ""))


class TestSchalterUndKopplung(unittest.TestCase):

    def test_default_ist_aus(self):
        # Ohne ausdruecklichen Schalter wird KEIN Geld gesetzt.
        self.assertIs(SAB.AN, os.environ.get("SHORTLIST_AUTO_BET", "").strip()
                      in ("1", "true", "yes", "on"))

    def test_parameter_wie_bestellt(self):
        self.assertEqual(SAB.STAKE, 5.0)
        self.assertEqual(SAB.MAX_OFFEN, 100.0)

    def test_quelle_ist_das_push_buch(self):
        # Die Kopplung „gesetzt wird, was gepusht wurde" ist Mechanik, keine Konvention:
        # dieses Skript liest ausschliesslich das Buch der gesendeten Pushes.
        import inspect
        quelle = inspect.getsource(SAB)
        self.assertIn("shortlist_push_ledger.json", quelle)
        self.assertNotIn("load_emit", quelle,
                         "eine eigene Auswahl waere eine fuenfte Menge neben Uebersicht, "
                         "Public-Tor, Paper-Track und Push")


class TestDieseTestsVergiftenDieUmgebungNicht(unittest.TestCase):
    """13.09.2026er Lehre: ein Testmodul, das beim Import Env setzt, kippt fremde Tests."""

    def test_kein_env_beim_import(self):
        for k in ("SHORTLIST_AUTO_BET", "POLY_PRIVATE_KEY", "COCOBET_DATASET"):
            if k == "COCOBET_DATASET":
                continue
            self.assertNotIn(k, os.environ,
                             f"{k} darf von diesem Modul nicht gesetzt werden")


if __name__ == "__main__":
    unittest.main()
