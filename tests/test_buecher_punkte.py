"""Der Bücher-Punktestand (killer.buecher_punkte + punkte_fortschreiben).

01.09.2026. Lucas: *„ich will die Bücher alle im Vergleich mit den Kriterien, wie viel erfüllt wird,
mit einer Punkteanzeige … das Maximum ist zehn von zehn."*

Die Gewichtung ist keine Geschmacksfrage — sie folgt der Messung an 500 Plays: **mehr Bücher trug
(+11,5%), mehr Signale aus demselben Buch nicht (−1,1%)**. Deshalb prüfen diese Tests vor allem
zwei Eigenschaften, ohne die der Score seine eigene Aussage verrät:

  1. Ein zustimmendes BUCH ist mehr wert als Tiefe im selben Buch. Wer das umdreht, bekommt genau
     die Bauform zurück, die gemessen NICHT trägt.
  2. Ein nicht erhobenes Buch senkt den NENNER, es kostet keine Punkte. „5 von 7" und „5 von 10"
     sind verschiedene Aussagen — die Verwechslung hat die Poly-Bedingung monatelang tot gehalten.
"""
import unittest
from datetime import datetime, timedelta, timezone

import killer as K

JETZT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
ANPFIFF = (JETZT + timedelta(hours=9)).isoformat()


def sig(conc=True, inflow=True, dirn="in", share=0.89, odd=1.93):
    return {"conc": conc, "inflow": inflow, "dir": dirn, "share": share, "odd": odd, "fav": "H"}


def spiel(poly_pct=71, whales=None, pinn_fav="home", move_pp=3.2, seite="home"):
    g = {"moneySide": seite}
    if poly_pct is not None:
        g["poly"] = {"sharePct": poly_pct, "whales": whales if whales is not None else []}
    if pinn_fav is not None:
        g["pinn"] = {"fav": pinn_fav}
    if move_pp is not None:
        g["pinnMove"] = {"move": True, "movePP": move_pp}
    return g


def punkte(s=None, g=None, seit=None, wallets=None, kickoff=ANPFIFF):
    return K.buecher_punkte(s or sig(), g if g is not None else spiel(), "home",
                            gehalten_seit=seit or JETZT.isoformat(), kickoff=kickoff,
                            wallets=wallets if wallets is not None else {"0xaa"}, now=JETZT)


def teil(r, buch):
    return next(t for t in r["teile"] if t["buch"] == buch)


class TestGewichtung(unittest.TestCase):
    def test_volle_zustimmung_ergibt_zehn_von_zehn(self):
        r = punkte(g=spiel(whales=[{"wallet": "0xAA", "usd": 900}]))
        self.assertEqual((r["punkte"], r["moeglich"]), (10, 10))

    def test_ein_buch_wiegt_schwerer_als_tiefe_im_selben_buch(self):
        """Der Kern der Messung. Dreht jemand das um, ist der Score wieder das, was nicht trägt."""
        self.assertGreater(K.PUNKTE_BUCH, K.PUNKTE_TIEFE)
        nur_breit = punkte(s=sig(inflow=False), g=spiel(whales=[], move_pp=None))
        nur_tief = punkte(g=spiel(poly_pct=10, pinn_fav="away", move_pp=None))
        self.assertGreater(nur_breit["punkte"], nur_tief["punkte"],
                           "drei zustimmende Bücher ohne Tiefe müssen ein tiefes Buch schlagen")

    def test_ein_buch_allein_kommt_nie_ueber_drei(self):
        """Betfair kann alle seine Kriterien erfüllen und bleibt bei 3 von 10."""
        r = punkte(g=spiel(poly_pct=10, pinn_fav="away", move_pp=None), seit=ANPFIFF)
        self.assertEqual(teil(r, "BF")["punkte"], 3)
        self.assertEqual(r["punkte"], 3)

    def test_sechs_punkte_verlangen_alle_drei_buecher(self):
        r = punkte(s=sig(inflow=False), g=spiel(whales=[], move_pp=None), seit=ANPFIFF)
        self.assertEqual(r["punkte"], 6)
        self.assertTrue(all(teil(r, b)["status"] == "ja" for b in ("BF", "POLY", "PIN")))


class TestNennerStattStrafe(unittest.TestCase):
    """Fehlende Information ist keine Erlaubnis — und auch kein Nein."""

    def test_fehlendes_poly_senkt_den_nenner(self):
        r = punkte(g=spiel(poly_pct=None))
        self.assertEqual(teil(r, "POLY")["status"], "unbekannt")
        self.assertEqual(teil(r, "POLY")["moeglich"], 0)
        self.assertEqual(r["moeglich"], 7)

    def test_fehlendes_pinnacle_senkt_den_nenner(self):
        r = punkte(g=spiel(pinn_fav=None, move_pp=None))
        self.assertEqual(teil(r, "PIN")["status"], "unbekannt")
        self.assertEqual(r["moeglich"], 7)

    def test_ohne_beide_fremden_buecher_bleiben_vier(self):
        r = punkte(g=spiel(poly_pct=None, pinn_fav=None, move_pp=None))
        self.assertEqual(r["moeglich"], 4)

    def test_poly_dagegen_ist_etwas_anderes_als_poly_unbekannt(self):
        dagegen = punkte(g=spiel(poly_pct=10))
        unbekannt = punkte(g=spiel(poly_pct=None))
        self.assertEqual(teil(dagegen, "POLY")["status"], "nein")
        self.assertEqual(teil(dagegen, "POLY")["moeglich"], 3, "ein Nein zählt in den Nenner")
        self.assertEqual(teil(unbekannt, "POLY")["moeglich"], 0, "ein Achselzucken nicht")

    def test_ohne_anpfiff_ist_die_dauer_unbekannt_nicht_null(self):
        r = punkte(kickoff=None)
        self.assertEqual(teil(r, "ZEIT")["status"], "unbekannt")
        self.assertEqual(teil(r, "ZEIT")["moeglich"], 0)


class TestTiefe(unittest.TestCase):
    def test_tiefe_zaehlt_nur_wenn_das_buch_ueberhaupt_zustimmt(self):
        """Sonst wäre „viel Geld auf der GEGENSEITE, das schnell fließt" ein Pluspunkt."""
        r = punkte(g=spiel(poly_pct=10, whales=[{"wallet": "0xAA", "usd": 900}]))
        self.assertEqual(teil(r, "POLY")["punkte"], 0)
        self.assertFalse(teil(r, "POLY")["tiefe"]["ok"])

    def test_nur_bewiesene_wallets_zaehlen(self):
        """`smart` hieß früher GROSS statt treffsicher — der Fehler wird hier nicht wiederholt."""
        gross_aber_unbewiesen = punkte(g=spiel(whales=[{"wallet": "0xZZ", "usd": 99999}]))
        self.assertEqual(teil(gross_aber_unbewiesen, "POLY")["punkte"], K.PUNKTE_BUCH)
        bewiesen = punkte(g=spiel(whales=[{"wallet": "0xAA", "usd": 12}]))
        self.assertEqual(teil(bewiesen, "POLY")["punkte"], K.PUNKTE_BUCH + K.PUNKTE_TIEFE)

    def test_betfair_tiefe_verlangt_BEIDES(self):
        self.assertEqual(teil(punkte(s=sig(inflow=False)), "BF")["punkte"], K.PUNKTE_BUCH)
        self.assertEqual(teil(punkte(s=sig(dirn="flat")), "BF")["punkte"], K.PUNKTE_BUCH)
        self.assertEqual(teil(punkte(), "BF")["punkte"], K.PUNKTE_BUCH + K.PUNKTE_TIEFE)


class TestDauer(unittest.TestCase):
    """Gemessen am eigenen Buch (n=80): <1h vor Anpfiff −4,1%, ≥6h +48,9%. Der Vorlauf trennte
    stärker als jede zusätzliche Bedingung — deshalb ist er der zehnte Punkt."""

    def test_langer_vorlauf_gibt_den_punkt(self):
        self.assertEqual(teil(punkte(), "ZEIT")["punkte"], K.PUNKTE_DAUER)

    def test_kurz_vor_anpfiff_gibt_ihn_nicht(self):
        r = punkte(kickoff=(JETZT + timedelta(minutes=40)).isoformat())
        self.assertEqual(teil(r, "ZEIT")["punkte"], 0)
        self.assertEqual(teil(r, "ZEIT")["moeglich"], K.PUNKTE_DAUER, "gemessen, aber nicht erfüllt")


class TestBewieseneWallets(unittest.TestCase):
    def test_wenig_historie_zaehlt_nicht(self):
        w = K._bewiesene_wallets({"scores": {"0xA": {"n": 3, "clvSumPP": 30.0}}})
        self.assertEqual(w, set())

    def test_negativer_clv_zaehlt_nicht(self):
        w = K._bewiesene_wallets({"scores": {"0xA": {"n": 20, "clvSumPP": -5.0}}})
        self.assertEqual(w, set())

    def test_genug_historie_und_positiver_clv_zaehlt(self):
        w = K._bewiesene_wallets({"scores": {"0xAB": {"n": 20, "clvSumPP": 40.0}}})
        self.assertEqual(w, {"0xab"}, "kleingeschrieben, damit der Vergleich nicht an Groß/Klein scheitert")

    def test_fehlende_datei_ergibt_leere_menge_nicht_absturz(self):
        self.assertEqual(K._bewiesene_wallets(None), set())
        self.assertEqual(K._bewiesene_wallets({}), set())


class TestGradient(unittest.TestCase):
    """Mitschreiben, nicht filtern: ohne die 2er und 4er lässt sich nie sagen, ob eine 8 besser
    war — oder nur seltener."""

    def zeile(self, mid, p, ko_h, odd=2.0):
        return {"matchId": mid, "markt": "Match Odds", "liga": "L", "name": "A", "seite": "home",
                "odd": odd, "kickoff": (JETZT + timedelta(hours=ko_h)).isoformat(),
                "punkte": p, "moeglich": 10, "dauerH": 4.0, "torOk": p >= 6}

    def test_vor_anpfiff_wird_der_stand_aufgefrischt_nicht_abgerechnet(self):
        st, zu = K.punkte_fortschreiben({}, [self.zeile("1", 4, +2)], [], JETZT)
        self.assertEqual(zu, [])
        self.assertEqual(st["1|Match Odds"]["punkte"], 4)
        st2, _ = K.punkte_fortschreiben(st, [self.zeile("1", 7, +1)], [], JETZT)
        self.assertEqual(st2["1|Match Odds"]["punkte"], 7, "der letzte Stand vor Anpfiff gilt")

    def test_nach_anpfiff_mit_ergebnis_wird_abgerechnet(self):
        st, zu = K.punkte_fortschreiben({}, [self.zeile("1", 8, -1)],
                                        [{"matchId": "1", "market": "Match Odds", "win": True}], JETZT)
        self.assertEqual(len(zu), 1)
        self.assertTrue(zu[0]["win"])
        self.assertNotIn("1|Match Odds", st)

    def test_spaetes_ergebnis_geht_nicht_verloren(self):
        """Sonst verschwänden genau die Spiele, deren Abrechnung sich zieht — eine stille Auswahl
        mitten im Gradienten."""
        st, zu = K.punkte_fortschreiben({}, [self.zeile("1", 8, -2)], [], JETZT)
        self.assertEqual(zu, [])
        self.assertIn("1|Match Odds", st, "bleibt offen, bis das Ergebnis da ist")
        _, zu2 = K.punkte_fortschreiben(st, [], [{"matchId": "1", "market": "Match Odds", "win": False}], JETZT)
        self.assertEqual(len(zu2), 1)

    def test_uralte_unabgerechnete_zeilen_laufen_aus(self):
        st, _ = K.punkte_fortschreiben({}, [self.zeile("1", 8, -100)], [], JETZT)
        self.assertNotIn("1|Match Odds", st)

    def test_bilanz_trennt_nach_punktzahl(self):
        led = ([{"odd": 2.0, "punkte": 8, "moeglich": 10, "win": True}] * 4
               + [{"odd": 2.0, "punkte": 3, "moeglich": 10, "win": False}] * 4)
        b = {(r["punkte"], r["moeglich"]): r for r in K.punkte_bilanz(led)}
        self.assertEqual(b[(8, 10)]["roi"], 1.0)
        self.assertEqual(b[(3, 10)]["roi"], -1.0)
        self.assertEqual(b[(8, 10)]["n"], 4)

    def test_verschiedene_nenner_werden_nicht_vermischt(self):
        """Eine 5 aus 6 ist eine andere Aussage als eine 5 aus 10 — sie in einen Eimer zu werfen
        wäre genau die Verwechslung, gegen die der Nenner gebaut ist."""
        led = [{"odd": 2.0, "punkte": 5, "moeglich": 6, "win": True},
               {"odd": 2.0, "punkte": 5, "moeglich": 10, "win": False}]
        self.assertEqual(len(K.punkte_bilanz(led)), 2)

    def test_zeilen_ohne_ergebnis_oder_quote_zaehlen_nicht(self):
        led = [{"odd": None, "punkte": 8, "moeglich": 10, "win": True},
               {"odd": 2.0, "punkte": 8, "moeglich": 10, "win": None}]
        self.assertEqual(K.punkte_bilanz(led), [])


if __name__ == "__main__":
    unittest.main()


class TestAnkerPool(unittest.TestCase):
    """02.09.2026 (Lucas: „Wieso gibt es kein Pini? Das Spiel ist zu 100% bei Pinnacle").

    Er hatte recht, und die Ursache lag zwei Schichten tiefer: `betfair_consensus.games` ist die
    RADAR-Liste und mit `qualifies_radar()` auf ≥15.000 € Marktvolumen gefiltert. Sassuolo–Frosinone
    (Coppa Italia — in der Ankerkarte!) lag bei 10.289 € und bekam deshalb **nie eine Pinnacle-
    Abfrage**. Der Punktestand meldete korrekt ❔ — nur war die Lücke nicht bei Pinnacle.

    ⭐ Eine Schwelle, die entscheidet WAS ANGEZEIGT wird, darf nicht entscheiden, OB WIR FRAGEN.
    `betfair_anker.json` trägt die Zweitmeinungen ohne diese Schwelle.
    """

    def _pending(self):
        return {"pending": {"77": {
            "home": "Sassuolo", "away": "Frosinone", "league": "Italian Coppa Italia",
            "kickoff": (JETZT + timedelta(hours=8)).isoformat(),
            "signals": {"Match Odds": sig()}}}}

    def _baue(self, cons, anker):
        return K.baue(state=self._pending(), consensus=cons, track={}, streaks={"streaks": []},
                      now=JETZT, latch_state={}, anker=anker)

    def test_ohne_anker_bleibt_es_bei_betfair_allein(self):
        d = self._baue({"games": []}, {"anker": {}})
        z = d["alleBewertet"][0]
        self.assertEqual((z["punkte"], z["moeglich"]), (4, 4), "nur Betfair + Dauer im Nenner")

    def test_der_anker_bringt_das_zweite_und_dritte_buch(self):
        anker = {"anker": {"77": {"moneySide": "home", "pinn": {"fav": "home"},
                                  "pinnMove": {"move": True, "movePP": 3.0},
                                  "poly": {"sharePct": 71, "whales": []}}}}
        z = self._baue({"games": []}, anker)["alleBewertet"][0]
        self.assertEqual(z["moeglich"], 10, "beide fremden Buecher sind jetzt erhoben")
        self.assertGreaterEqual(z["punkte"], 8)

    def test_die_radar_zeile_hat_vorrang_vor_dem_anker(self):
        """Die Konsens-Zeile ist vollständiger (Totals, Soft-Bücher). Der Anker füllt nur Lücken."""
        cons = {"games": [{"matchId": "77", "moneySide": "home", "pinn": {"fav": "away"},
                           "poly": {"sharePct": 10}}]}
        anker = {"anker": {"77": {"moneySide": "home", "pinn": {"fav": "home"},
                                  "poly": {"sharePct": 90}}}}
        z = self._baue(cons, anker)["alleBewertet"][0]
        teile = {t["buch"]: t for t in K.buecher_punkte(
            sig(), cons["games"][0], "home", gehalten_seit=JETZT.isoformat(),
            kickoff=(JETZT + timedelta(hours=8)).isoformat(), now=JETZT)["teile"]}
        self.assertEqual(teile["PIN"]["status"], "nein", "Radar-Zeile sagt: Pinnacle sieht die andere Seite")
        self.assertLess(z["punkte"], 8, "der guenstigere Anker darf die Radar-Zeile nicht ueberschreiben")

    def test_kaputter_anker_wirft_nicht(self):
        for a in (None, {}, {"anker": None}, {"anker": {"77": "kaputt"}}, {"anker": []}):
            self.assertTrue(self._baue({"games": []}, a)["alleBewertet"])
