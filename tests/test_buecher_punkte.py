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
    """🔴 08.09.2026 — bis heute reichte hier „genug Historie UND Ø CLV > 0". Am Stand des Tages
    galten damit 233 Wallets als bewiesen, davon 91 bestaetigte Verlierer (groesste: n=186,
    P&L −$7,78 Mio). Die Definition kommt jetzt aus `sharp_gate` — dieselbe, die Dashboard,
    Shortlist, Whale-Watch und Live-Watch benutzen. Die Fixtures brauchen deshalb eine
    Trefferbilanz: positiver CLV allein ist kein Beleg mehr.
    """

    def test_wenig_historie_zaehlt_nicht(self):
        w = K._bewiesene_wallets({"scores": {"0xA": {"n": 3, "wins": 3, "clvSumPP": 30.0}}})
        self.assertEqual(w, set())

    def test_negativer_clv_zaehlt_nicht(self):
        w = K._bewiesene_wallets({"scores": {"0xA": {"n": 20, "wins": 15, "clvSumPP": -5.0}}})
        self.assertEqual(w, set())

    def test_genug_historie_und_positiver_clv_zaehlt(self):
        w = K._bewiesene_wallets({"scores": {"0xAB": {"n": 20, "wins": 15, "clvSumPP": 40.0}}})
        self.assertEqual(w, {"0xab"}, "kleingeschrieben, damit der Vergleich nicht an Groß/Klein scheitert")

    def test_positiver_clv_ohne_trefferbilanz_reicht_nicht_mehr(self):
        # Genau die alte Fixture: n=20, CLV +40 — und keine einzige gewonnene Position.
        w = K._bewiesene_wallets({"scores": {"0xAB": {"n": 20, "clvSumPP": 40.0}}})
        self.assertEqual(w, set())

    def test_bestaetigter_verlierer_zaehlt_nicht(self):
        w = K._bewiesene_wallets({"scores": {"0xAB": {"n": 186, "wins": 97, "clvSumPP": 20.0,
                                                      "pnl": -7775708.0}}})
        self.assertEqual(w, set())

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


class TestStakeAlsViertesBuch(unittest.TestCase):
    """08.09.2026 (Lucas: „was fehlt da noch neben Stake?"). Der Punktestand kannte drei Bücher —
    Betfair, Polymarket, Pinnacle. Der Stake-Highroller ist die einzige der vier Quellen, die kein
    Buchmacher-Preis ist, sondern fremdes Geld auf einer Seite, und er war der einzige Grund,
    warum es die Spielzentrale daneben überhaupt gab."""

    SIG = {"fav": "H", "share": 0.78, "odd": 1.64, "conc": True, "inflow": False, "dir": "flat"}

    def _p(self, stake):
        return K.buecher_punkte(self.SIG, {}, "home", stake=stake)

    def _teil(self, p):
        return next(t for t in p["teile"] if t["buch"] == "STAKE")

    def test_geld_auf_derselben_seite_gibt_punkte(self):
        p = self._p({"seite": "home", "seiteUsd": 7318.0, "n": 9})
        t = self._teil(p)
        self.assertEqual(t["status"], "ja")
        self.assertEqual(t["punkte"], K.PUNKTE_BUCH + K.PUNKTE_TIEFE)
        self.assertIn("7.318", t["grund"]["text"])

    def test_gegenseite_gibt_keine_punkte_senkt_aber_den_nenner_nicht(self):
        t = self._teil(self._p({"seite": "away", "seiteUsd": 9000.0, "n": 9}))
        self.assertEqual(t["punkte"], 0)
        self.assertEqual(t["moeglich"], K.PUNKTE_BUCH + K.PUNKTE_TIEFE)

    def test_eine_einzelne_wette_hat_keine_tiefe(self):
        # Ein grosser einzelner Klick ist kein Konsens.
        t = self._teil(self._p({"seite": "home", "seiteUsd": 50000.0, "n": 1}))
        self.assertEqual(t["punkte"], K.PUNKTE_BUCH)

    def test_kleines_geld_stimmt_nicht_zu(self):
        t = self._teil(self._p({"seite": "home", "seiteUsd": 80.0, "n": 9}))
        self.assertEqual(t["punkte"], 0)

    def test_ohne_stake_ist_das_buch_unbekannt_und_senkt_den_nenner(self):
        ohne = self._p(None)
        t = self._teil(ohne)
        self.assertEqual(t["status"], "unbekannt")
        self.assertEqual(t["moeglich"], 0)
        # Der Nenner ist um genau ein Buch kleiner als mit erhobenem Stake.
        mit = self._p({"seite": "home", "seiteUsd": 7318.0, "n": 9})
        self.assertEqual(mit["moeglich"] - ohne["moeglich"], K.PUNKTE_BUCH + K.PUNKTE_TIEFE)

    def test_ohne_1x2_seite_ist_es_unbekannt_nicht_nein(self):
        # Eine Über/Unter-Wette trägt Geld, widerspricht uns aber nicht.
        t = self._teil(self._p({"seite": None, "usd": 20000.0, "seiteUsd": 0, "n": 3}))
        self.assertEqual(t["status"], "unbekannt")

    def test_punkte_und_nenner_bleiben_die_summe_der_teile(self):
        p = self._p({"seite": "home", "seiteUsd": 7318.0, "n": 9})
        self.assertEqual(p["punkte"], sum(t["punkte"] for t in p["teile"]))
        self.assertEqual(p["moeglich"], sum(t["moeglich"] for t in p["teile"]))


# ── 08.09.2026: Geld je Buch, maschinenlesbar ───────────────────────────────────────────
# Lucas: „koennte man das optisch nicht ins Kaestchen schreiben, wieviel Kohle oben liegt? Bei
# Betfair, Poly und Stake. Nur +2 und ganz mini so ein %, das sieht man ja nicht gut."
#
# Der teure Teil ist nicht der Betrag, sondern die Frage, wann es ihn NICHT gibt.
class TestGeldJeBuch(unittest.TestCase):
    def test_betfair_betrag_ist_anteil_mal_volumen(self):
        g = spiel()
        g["totVol"] = 2000000
        t = teil(K.buecher_punkte(sig(share=0.88), g, "home", kickoff=ANPFIFF), "BF")
        self.assertEqual(t["geld"]["betrag"], 1760000)
        self.assertEqual(t["geld"]["waehrung"], "EUR")
        self.assertEqual(t["geld"]["quelle"], "geld")

    def test_ohne_volumen_gibt_es_den_anteil_aber_keinen_betrag(self):
        """Kommt real vor: Spiele unter der Radar-Schwelle laufen ueber den Anker. Der Balken
        stimmt trotzdem — erfunden wird nichts."""
        t = teil(K.buecher_punkte(sig(share=0.88), spiel(), "home", kickoff=ANPFIFF), "BF")
        self.assertAlmostEqual(t["geld"]["anteil"], 0.88)
        self.assertIsNone(t["geld"]["betrag"])

    def test_ein_poly_PREIS_bekommt_keinen_geldbetrag(self):
        """⭐ Der Kern. Bei Polymarket ist derselbe Anteil manchmal Geld und manchmal ein PREIS.
        68 % Preis heisst „der Markt haelt es fuer zu 68 % wahrscheinlich" und nicht „68 % des
        Geldes liegen da". Ein Betrag daraus waere eine erfundene Zahl an genau der Stelle, auf
        die Lucas ab jetzt schaut."""
        g = spiel(poly_pct=68)
        g["poly"].update({"vol": 1407, "shareSrc": "preis"})
        t = teil(K.buecher_punkte(sig(), g, "home", kickoff=ANPFIFF), "POLY")
        self.assertEqual(t["geld"]["quelle"], "preis")
        self.assertIsNone(t["geld"]["betrag"], "aus einem Preis folgt kein Geldbetrag")
        self.assertEqual(t["geld"]["gesamt"], 1407, "das Marktvolumen ist gemessen und bleibt")

    def test_ein_poly_GELDANTEIL_bekommt_seinen_betrag(self):
        g = spiel(poly_pct=75)
        g["poly"].update({"vol": 10756, "shareSrc": "geld"})
        t = teil(K.buecher_punkte(sig(), g, "home", kickoff=ANPFIFF), "POLY")
        self.assertEqual(t["geld"]["quelle"], "geld")
        self.assertEqual(t["geld"]["betrag"], 8067)

    def test_stake_traegt_seinen_seitenbetrag(self):
        st = {"seite": "home", "seiteUsd": 7318, "usd": 9000, "n": 4}
        t = teil(K.buecher_punkte(sig(), spiel(), "home", kickoff=ANPFIFF, stake=st), "STAKE")
        self.assertEqual(t["geld"]["betrag"], 7318)
        self.assertEqual(t["geld"]["gesamt"], 9000)

    def test_pinnacle_hat_gar_keinen_geldblock(self):
        """Ein Preisbuch hat kein Geld auf einer Seite. Ein Nullwert waere hier eine Aussage,
        die es nicht gibt — und im Frontend ein leerer Balken, der wie „null Geld" aussieht."""
        t = teil(K.buecher_punkte(sig(), spiel(), "home", kickoff=ANPFIFF), "PIN")
        self.assertIsNone(t["geld"])

    def test_nicht_erhoben_traegt_kein_geld(self):
        t = teil(K.buecher_punkte(sig(), spiel(), "home", kickoff=ANPFIFF), "STAKE")
        self.assertEqual(t["status"], "unbekannt")
        self.assertIsNone(t["geld"])
