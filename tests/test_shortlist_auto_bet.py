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
import push_shortlist_trades as PST


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

    def test_etwas_billiger_ist_ok(self):
        """14.09.2026: hier stand „billiger ist IMMER ok". Das war der Satz, mit dem der
        BIG-Trade durchging — 25 Punkte unter dem Push-Preis, im laufenden Spiel."""
        ok, _ = SAB.preis_urteil(0.50, 0.41)
        self.assertTrue(ok, "9pp guenstiger vor Anpfiff ist eine Korrektur, kein Alarm")

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


class TestDerPreisDarfAuchNichtEINBRECHEN(unittest.TestCase):
    """🔴 14.09.2026, zweiter Anlauf (Lucas: „übrigens wurde dieses esport Match BIG doch
    gesetzt auf poly, hab ich grad gesehen").

    Ich hatte geschlossen, die Schranke habe den Trade verhindert. Sie hat ihn nur VERZOEGERT:

        17:50  Push 63,5¢ · Buch 66/68  →  blockiert (+4,5pp)   richtig
        18:21  gekauft @ 38¢                                     falsch

    Die Schranke kannte nur eine Richtung. 25 Punkte Preisverfall im laufenden Spiel (107. Min)
    sind kein Schnaeppchen — da ist im Match etwas passiert, und der Play, den das Signal fand,
    existierte nicht mehr. Dieselbe Adverse Selection, vor der ich bei der Limit-Order gewarnt
    und die ich im eigenen Code stehen gelassen habe.
    """

    PUSH = 0.635

    def test_der_echte_BIG_trade_wird_jetzt_geblockt(self):
        ok, grund = SAB.preis_urteil(self.PUSH, 0.38, live=True)
        self.assertFalse(ok)
        self.assertIn("UNTER", grund)
        self.assertIn("38¢", grund)

    def test_live_ist_die_grenze_enger_als_vor_anpfiff(self):
        """Vor Anpfiff ist ein Rutsch meist die Korrektur eines duennen Marktes; live ist er
        das Spiel."""
        ok_live, _ = SAB.preis_urteil(0.60, 0.52, live=True)     # -8pp
        ok_vor, _ = SAB.preis_urteil(0.60, 0.52, live=False)
        self.assertFalse(ok_live)
        self.assertTrue(ok_vor)

    def test_kleiner_rutsch_bleibt_erlaubt(self):
        self.assertTrue(SAB.preis_urteil(0.60, 0.57, live=True)[0], "-3pp live ist noch normal")

    def test_teurer_bleibt_wie_es_war(self):
        ok, grund = SAB.preis_urteil(self.PUSH, 0.68, live=True)
        self.assertFalse(ok)
        self.assertIn("ueber", grund)

    def test_live_erkennung_aus_dem_feed(self):
        self.assertTrue(SAB.ist_live({"m": {"hoursToKickoff": -2.78}}, "m"))
        self.assertFalse(SAB.ist_live({"m": {"hoursToKickoff": 0.22}}, "m"))

    def test_unbekannt_gilt_als_live(self):
        """Bei einer Grenze, die live enger ist, ist „live" der vorsichtige Default."""
        self.assertTrue(SAB.ist_live({}, "m"))
        self.assertTrue(SAB.ist_live({"m": {}}, "m"))

    def test_live_push_veraltet_nach_zehn_minuten(self):
        """Die zweite Ursache: der Push lag 31 Minuten im Buch, weil der erste Lauf ihn
        blockiert hatte und der naechste ihn wieder aufnahm."""
        from datetime import datetime as _d, timezone as _t
        jetzt = _d(2026, 9, 14, 18, 21, tzinfo=_t.utc)
        z = {"k": "a|A", "key": "a", "side": "A", "conv": 6,
             "sentAt": "2026-09-14T17:50:47+00:00", "pushPreis": 0.635}
        self.assertEqual(SAB.faellige_zeilen([z], set(), jetzt, live_fn=lambda k: True), [])
        self.assertEqual(len(SAB.faellige_zeilen([z], set(), jetzt, live_fn=lambda k: False)), 1)

    def test_der_lauf_fragt_live_auch_wirklich_ab(self):
        """⭐ Beide Schranken nuetzen nichts, wenn main() den Live-Zustand nicht durchreicht —
        dann gilt ueberall die weite Vor-Anpfiff-Grenze und der BIG-Fall geht wieder durch."""
        import inspect
        quelle = inspect.getsource(SAB.main)
        self.assertIn("live=_live(z.get(\"key\"))", quelle,
                      "preis_urteil muss wissen, ob das Spiel laeuft")
        self.assertIn("live_fn=_live", quelle,
                      "faellige_zeilen muss das engere Live-Fenster anwenden koennen")
        self.assertIn("poly_money_broad_live.json", quelle)

    def test_frischer_live_push_kommt_durch(self):
        from datetime import datetime as _d, timezone as _t
        jetzt = _d(2026, 9, 14, 17, 55, tzinfo=_t.utc)
        z = {"k": "a|A", "key": "a", "side": "A", "conv": 6,
             "sentAt": "2026-09-14T17:50:47+00:00", "pushPreis": 0.635}
        self.assertEqual(len(SAB.faellige_zeilen([z], set(), jetzt, live_fn=lambda k: True)), 1)


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


class TestDieBestaetigungNenntDenVerzug(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „Push kam ca 30 min nach der empfehlenswert Push").

    Genau so war es — und die Nachricht sagte es nicht. Er sah um 17:50 einen Push, es passierte
    nichts, er hatte ihn abgehakt; eine halbe Stunde spaeter kam eine Bestaetigung fuer einen
    Play, den er gedanklich weggelegt hatte. Zwei Nachrichten, die zusammengehoeren, aber nicht
    zusammen aussehen.
    """

    def _bau(self, minuten):
        from datetime import datetime as _d, timedelta as _td, timezone as _t
        import telegram_trades as TT
        gesendet = []
        alt = TT.send_trades_message
        TT.send_trades_message = lambda t, **kw: gesendet.append(t) or True
        try:
            TT.notify_shortlist_opened(
                match="BIG vs KOI", side="BIG", stake=5.0, fill=0.38, conv=6,
                push_preis=0.635, slug="x",
                push_at=(_d.now(_t.utc) - _td(minutes=minuten)).isoformat())
        finally:
            TT.send_trades_message = alt
        return gesendet[0]

    def test_eine_halbe_stunde_spaeter_steht_dran(self):
        t = self._bau(31)
        self.assertIn("31 Min nach dem Push", t)

    def test_sofortiger_kauf_bleibt_schlank(self):
        """Der Normalfall — Push und Kauf im selben Lauf — braucht die Zeile nicht."""
        self.assertNotIn("nach dem Push", self._bau(0))

    def test_kaputter_zeitstempel_erfindet_keinen_verzug(self):
        import telegram_trades as TT
        gesendet = []
        alt = TT.send_trades_message
        TT.send_trades_message = lambda t, **kw: gesendet.append(t) or True
        try:
            TT.notify_shortlist_opened(match="A vs B", side="A", stake=5.0, fill=0.5,
                                       push_preis=0.5, slug="x", push_at="gestern")
        finally:
            TT.send_trades_message = alt
        self.assertNotIn("nach dem Push", gesendet[0])

    def test_der_lauf_reicht_den_push_zeitpunkt_durch(self):
        """Ohne das ist die Zeile tot — der Zeitstempel steht im Push-Buch, nicht in der Wette."""
        import inspect
        self.assertIn('push_at=zeile.get("sentAt")', inspect.getsource(SAB._melden))


class TestDieKarteWeissDassSieEineVerstaerkungIst(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „A hso ich Trottel — das ja selbe Spiel").

    Er war es nicht. Der zweite Ostersunds-Push (Conviction 7→8, 55,5¢ → 61¢) sah aus wie ein
    neuer Play; dass er eine Verstaerkung war und dass die Position seit einer halben Stunde
    lief, stand nirgends. Beides lag vor: die vorige Conviction im Dedup-Buch (nur deshalb
    feuert der Push erneut), die Position im Wett-Buch. Eine Nachricht, die den Leser zum
    Nachschlagen zwingt, hat ihre Aufgabe nicht erfuellt.
    """

    VORHER = {"conv": 7, "ts": "2026-09-14T16:20:46+00:00"}
    POS = {"stake": 5.0, "polyPrice": 0.56, "placedAt": "2026-09-14T16:20:47+00:00"}

    def _play(self, conv=8):
        return {"key": "swe2-of-hel-2026-09-14", "side": "Ostersunds FK", "conv": conv,
                "verdict": "BET", "price": 0.61, "match": "Ostersunds FK vs Helsingborgs IF"}

    def test_gestiegene_conviction_wird_als_verstaerkung_benannt(self):
        z = PST.kontext_zeilen(self._play(), self.VORHER, None)
        self.assertTrue(any("Verstärkung" in x and "7→8" in x for x in z), z)

    def test_die_uhrzeit_des_ersten_pushs_steht_dabei(self):
        z = PST.kontext_zeilen(self._play(), self.VORHER, None)
        self.assertIn("16:20", " ".join(z))

    def test_erster_push_bekommt_keine_verstaerkungs_zeile(self):
        self.assertEqual(PST.kontext_zeilen(self._play(), None, None), [])

    def test_gleiche_conviction_ist_keine_verstaerkung(self):
        self.assertEqual(PST.kontext_zeilen(self._play(conv=7), self.VORHER, None), [])

    def test_bestehende_position_steht_mit_preis_und_zeit_dabei(self):
        z = " ".join(PST.kontext_zeilen(self._play(), self.VORHER, self.POS))
        self.assertIn("$5.00", z)
        self.assertIn("56¢", z)
        self.assertIn("16:20", z)

    def test_kein_nachkauf_steht_ausdruecklich_dran(self):
        """Sonst wartet der Leser auf eine Bestaetigung, die nie kommt."""
        z = " ".join(PST.kontext_zeilen(self._play(), self.VORHER, self.POS))
        self.assertIn("kein Nachkauf", z)

    def test_unlesbare_zeit_erfindet_keine_uhrzeit(self):
        z = " ".join(PST.kontext_zeilen(self._play(), {"conv": 7, "ts": "kaputt"}, None))
        self.assertIn("Verstärkung", z)
        self.assertNotIn("UTC", z)

    def test_offene_positionen_nur_wirklich_offene(self):
        buch = {"bets": [
            {"betKey": "a|A", "status": "placed"},
            {"betKey": "b|B", "status": "placed", "soldAt": "2026-09-14T17:00:00Z"},
            {"betKey": "c|C", "status": "won"},
        ]}
        import json, tempfile, os
        fd, pfad = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(buch, f)
        try:
            self.assertEqual(sorted(PST.offene_positionen(pfad)), ["a|A"])
        finally:
            os.unlink(pfad)

    def test_die_fertige_nachricht_traegt_den_kontext(self):
        """⭐ Der Test, der den ganzen Fix haelt: es genuegt nicht, dass die Zeilen BERECHNET
        werden — sie muessen in der Nachricht stehen, die Lucas liest."""
        txt = PST.build_message(
            [self._play()], auto_an=True,
            seen={"swe2-of-hel-2026-09-14|Ostersunds FK": self.VORHER},
            positionen={"swe2-of-hel-2026-09-14|Ostersunds FK": self.POS})
        self.assertIn("Verstärkung", txt)
        self.assertIn("7→8", txt)
        self.assertIn("du bist drin", txt)
        self.assertIn("56¢", txt)

    def test_ein_neuer_play_bleibt_schlank(self):
        txt = PST.build_message([self._play()], auto_an=True, seen={}, positionen={})
        self.assertNotIn("Verstärkung", txt)
        self.assertNotIn("du bist drin", txt)

    def test_fehlendes_buch_kippt_den_push_nicht(self):
        self.assertEqual(PST.offene_positionen("/gibt/es/nicht.json"), {})


class TestDerRePushBrauchtNeueEvidenz(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „aja der kam nun 3. mal — wieso wird der so wild in die Hoehe
    gepusht?"). Ostersunds FK, drei Karten in einer Stunde: conv 7 → 8 → 10, die letzte LIVE in
    der 12. Minute.

    Der Motor war `steam`: es misst die Bewegung gegen ein festes 6-Stunden-Fenster, also waechst
    dieselbe Bewegung darin von selbst weiter (+2,5 → +8,0 → +8,5pp) und schiebt die Conviction
    mit hoch. „Conviction gestiegen" war deshalb kein Beleg fuer neue Erkenntnis, sondern fuer
    ein Mass, das sich selbst nachlaedt.
    """

    def _p(self, conv, sig, htk=2.0):
        return {"key": "swe2-of-hel-2026-09-14", "side": "Ostersunds FK",
                "conv": conv, "signals": sig, "htk": htk}

    VORHER = {"conv": 7, "sig": ["money", "steam"], "ts": "2026-09-14T16:20:46+00:00"}

    def _seen(self):
        return {"swe2-of-hel-2026-09-14|Ostersunds FK": dict(self.VORHER)}

    def test_dieselben_signale_nur_groessere_zahlen_pushen_nicht(self):
        """⭐ Genau der Ostersunds-Fall: conv 7 → 10, aber kein neues Argument."""
        self.assertEqual(PST.fresh_plays([self._p(10, ["money", "steam"])], self._seen()), [])

    def test_ein_neues_signal_kommt_durch(self):
        aus = PST.fresh_plays([self._p(8, ["money", "steam", "sharp"])], self._seen())
        self.assertEqual(len(aus), 1)

    def test_nach_anpfiff_kein_re_push_auch_mit_neuem_signal(self):
        """Nach dem Anpfiff ist „mehr Geld auf der fuehrenden Seite" der Spielstand, kein Signal."""
        self.assertEqual(PST.fresh_plays(
            [self._p(10, ["money", "steam", "sharp"], htk=-0.2)], self._seen()), [])

    def test_ohne_anpfiffzeit_kein_re_push(self):
        self.assertEqual(PST.fresh_plays(
            [self._p(10, ["money", "steam", "sharp"], htk=None)], self._seen()), [])

    def test_der_erste_push_bleibt_unberuehrt_auch_live(self):
        self.assertEqual(len(PST.fresh_plays([self._p(7, ["money"], htk=-0.2)], {})), 1)

    def test_gesunkene_conviction_pusht_nicht(self):
        self.assertEqual(PST.fresh_plays([self._p(6, ["money", "steam", "sharp"])], self._seen()), [])

    def test_das_buch_merkt_sich_die_signale(self):
        """Ohne diese Zeile ist die Schranke zahnlos: ein Buch-Eintrag mit leerer Signal-Liste
        laesst beim naechsten Lauf JEDES Signal als „neu" gelten."""
        e = PST.seen_eintrag(self._p(8, ["steam", "money"]), "2026-09-14T16:20:00Z")
        self.assertEqual(e["sig"], ["money", "steam"])
        self.assertEqual(e["conv"], 8)
        # und die Runde schliesst sich: mit diesem Eintrag pusht derselbe Play nicht nach
        self.assertEqual(PST.fresh_plays([self._p(10, ["steam", "money"])],
                                         {"swe2-of-hel-2026-09-14|Ostersunds FK": e}), [])

    def test_main_schreibt_das_buch_ueber_seen_eintrag(self):
        """Die reine Funktion nuetzt nichts, wenn der Lauf sie umgeht — dann steht die
        Signal-Liste wieder nicht im Buch und die Schranke ist zahnlos."""
        import inspect
        quelle = inspect.getsource(PST.main)
        self.assertIn("seen_eintrag(", quelle)

    def test_altes_buch_ohne_signalmenge_pusht_nicht_nach(self):
        """Ohne Signal-Liste im Buch ist „neue Evidenz" nicht entscheidbar — dann lieber still.
        Das Buch raeumt sich nach drei Tagen selbst auf, der Fall heilt also von allein."""
        alt = {"swe2-of-hel-2026-09-14|Ostersunds FK": {"conv": 7, "ts": "x"}}
        self.assertEqual(PST.fresh_plays([self._p(10, ["money", "steam"])], alt), [])


class TestDieFusszeileKenntDenFall(unittest.TestCase):
    """Eine reine Verstaerkungs-Karte darf nicht „werden automatisch nachgespielt" sagen."""

    def test_alles_laeuft_schon(self):
        self.assertIn("nicht", PST.fusszeile(True, n_plays=1, n_gehalten=1))
        self.assertNotIn("Bestätigung", PST.fusszeile(True, n_plays=1, n_gehalten=1))

    def test_gemischt_nennt_beide_haelften(self):
        t = PST.fusszeile(True, n_plays=2, n_gehalten=1)
        self.assertIn("neuen Plays", t)
        self.assertIn("bereits laufenden", t)

    def test_nur_neue_plays(self):
        self.assertIn("Bestätigung", PST.fusszeile(True, n_plays=2, n_gehalten=0))

    def test_auto_aus_schlaegt_alles(self):
        self.assertIn("Kein Auto-Bet", PST.fusszeile(False, n_plays=1, n_gehalten=1))


class TestDieFusszeileSagtDieWahrheit(unittest.TestCase):
    """14.09.2026, erster Live-Fall: Push „Ostersunds FK" 16:20, Auto-Play 16:20 — und unter dem
    Push stand „Kein Auto-Bet". Zwei Nachrichten im selben Channel, die sich binnen Sekunden
    widersprechen. Was ein Kanal ueber sich selbst behauptet, muss stimmen, sonst ist keine
    seiner Angaben mehr etwas wert."""

    def test_bei_eingeschaltetem_auto_play_steht_es_dran(self):
        import push_shortlist_trades as P
        t = P.fusszeile(True)
        self.assertIn("automatisch", t)
        self.assertNotIn("Kein Auto-Bet", t)

    def test_ohne_auto_play_bleibt_der_alte_satz(self):
        import push_shortlist_trades as P
        self.assertIn("Kein Auto-Bet", P.fusszeile(False))

    def test_die_nachricht_traegt_die_fusszeile(self):
        import push_shortlist_trades as P
        plays = [{"key": "k", "side": "A", "conv": 7, "verdict": "BET", "price": 0.5}]
        self.assertIn("automatisch", P.build_message(plays, auto_an=True))
        self.assertIn("Kein Auto-Bet", P.build_message(plays, auto_an=False))

    def test_beide_lesen_denselben_schalter(self):
        # Zwei Schalter waeren zwei Zustaende — und genau einer davon waere irgendwann falsch.
        import inspect, push_shortlist_trades as P
        self.assertIn("SHORTLIST_AUTO_BET", inspect.getsource(P))
        self.assertEqual(P.AUTO_AN, SAB.AN)


class TestStilleHatEinenGrund(unittest.TestCase):
    """🔴 14.09.2026 (Lucas: „wenn so eine push kommt und danach keine auto bet push, weiss ich
    quote nicht erreicht oder?"). Nein — und das war die Luecke.

    Neun Gruende sahen im Telegram identisch aus: Preis davongelaufen, kein Token, kein Buch, zu
    duenn, Deckel, Boerse abgelehnt, Push zu alt, Schalter aus, Schritt nicht gelaufen. Der Lauf
    kennt jeden davon und behielt ihn fuer sich. Wer nicht handeln kann, muss es sagen.
    """

    def test_ohne_faelle_keine_nachricht(self):
        """Der wichtigste Fall: nichts liegengeblieben = kein Rauschen."""
        self.assertEqual(SAB.liegengeblieben_text([]), "")

    def test_der_grund_steht_in_der_nachricht(self):
        ok, grund = SAB.preis_urteil(0.635, 0.68)
        self.assertFalse(ok)
        t = SAB.liegengeblieben_text([{"titel": "BIG vs KOI · BIG (conv 6)", "grund": grund}])
        self.assertIn("BIG vs KOI", t)
        self.assertIn("68¢", t)
        self.assertIn("64¢", t)
        self.assertIn("4.5pp", t)

    def test_der_echte_BIG_fall(self):
        """Push 63,5¢, Buch bid 66 / ask 68 — die Wette, die heute nicht kam."""
        ok, grund = SAB.preis_urteil(0.635, 0.68)
        self.assertFalse(ok, "68¢ auf einen 63,5¢-Push ist +4,5pp und muss blocken")
        self.assertTrue(SAB.preis_urteil(0.635, 0.66)[0], "+2,5pp ist noch erlaubt")

    def test_trockenlauf_ist_gekennzeichnet(self):
        """Sonst hiesse Stille wieder zweierlei — und ein ausgeschalteter Schalter saehe aus
        wie ein Markt, der zu teuer war."""
        t = SAB.liegengeblieben_text([{"titel": "x", "grund": "y"}], dry=True)
        self.assertIn("Trockenlauf", t)
        self.assertNotIn("Trockenlauf", SAB.liegengeblieben_text([{"titel": "x", "grund": "y"}]))

    def test_lange_liste_wird_gekuerzt(self):
        viele = [{"titel": f"p{i}", "grund": "zu teuer"} for i in range(12)]
        t = SAB.liegengeblieben_text(viele)
        self.assertIn("(12)", t)
        self.assertIn("4 weitere", t)
        self.assertLessEqual(t.count("•"), 8)

    def test_jeder_uebersprungene_pfad_sammelt_seinen_grund(self):
        """⭐ Die Meldung nuetzt nichts, wenn ein Zweig sie umgeht: dann ist genau DER Fall
        wieder stumm. Jeder Abbruch im Lauf muss den Grund vermerken, nicht nur drucken."""
        import inspect
        quelle = inspect.getsource(SAB.main)
        # Die Skip-Zeile darf es nur EINMAL geben — im Helfer, der auch vermerkt. Jede
        # zweite waere ein Zweig, der wieder nur ins Log spricht.
        self.assertEqual(quelle.count('print(f"  ⏭'), 1,
                         "ein uebersprungener Play darf nicht nur gedruckt werden")
        self.assertGreaterEqual(quelle.count("_liegen("), 5)
        self.assertIn("liegengeblieben_text(liegen", quelle)

    def test_preisgruende_sprechen_cent(self):
        # Im Channel steht alles in Cent; 0.680 waere eine zweite Einheit in derselben Zeile.
        for ask, feld in ((0.98, "Hoechstpreis"), (0.05, "Mindestpreis")):
            ok, g = SAB.preis_urteil(0.5, ask)
            self.assertFalse(ok)
            self.assertIn(feld, g)
            self.assertIn("¢", g)


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


def test_main_meldet_den_liegengebliebenen_play(tmp_path, monkeypatch):
    """⭐ Die Gegenprobe am ganzen Lauf statt an den Bausteinen: ein Play, der uebersprungen
    wird, MUSS im Channel landen. Ohne diesen Test ueberlebt die Mutation „Gruende werden nicht
    mehr gesammelt" — und dann ist die Stille wieder unerklaert, genau wie vor dem Fix.

    Trockenlauf, kein Netz: das Push-Buch kennt einen frischen Play, der Feed keinen Token.
    """
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    jetzt = _dt.now(_tz.utc).isoformat()

    led = tmp_path / "ledger.json"
    led.write_text(_json.dumps([{"k": "m1|Heim", "key": "m1", "side": "Heim",
                                 "match": "Alpha vs Beta", "sentAt": jetzt,
                                 "conv": 8, "pushPreis": 0.55}]), encoding="utf-8")
    placed = tmp_path / "placed.json"
    placed.write_text(_json.dumps({"bets": []}), encoding="utf-8")
    leer = tmp_path / "leer.json"
    leer.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(SAB, "LEDGER_FILE", led)
    monkeypatch.setattr(SAB, "PLACED_FILE", placed)
    monkeypatch.setattr(SAB, "TRACK_FILE", leer)
    monkeypatch.setattr(SAB, "OFFEN_FILE", leer)      # kein Token → uebersprungen
    monkeypatch.setattr(SAB, "CLOSE_FILE", leer)
    monkeypatch.setattr(SAB, "BASE", tmp_path)        # keine fremden Wett-/Kill-Dateien
    monkeypatch.setattr(SAB, "_balance", lambda base_dir=None: (250.0, "TEST"))

    gesendet = []
    import telegram_trades as _TT
    monkeypatch.setattr(_TT, "send_trades_message", lambda t, **kw: gesendet.append(t) or True)

    SAB.main()

    assert gesendet, "der uebersprungene Play wurde nirgends gemeldet"
    text = "\n".join(gesendet)
    assert "Nicht nachgespielt" in text
    assert "Alpha vs Beta" in text
    assert "kein Token" in text
    assert "Trockenlauf" in text, "ohne Schalter muss die Meldung das sagen"
