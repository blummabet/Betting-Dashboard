"""tests/test_killer.py — 29.08.2026

Das Konjunktions-Element. Lucas' Anforderung war „dort kommst halt nur rein wenn" — also ist
das Wichtigste an diesen Tests nicht, WAS reinkommt, sondern was NICHT reinkommt.

Ein Test bewusst nicht: eine feste Trefferzahl fuer den heutigen Slate. Die waere morgen falsch
und wuerde nur die Fixture einbetonieren.
"""
import unittest
from datetime import datetime, timedelta, timezone

import killer
import betfair_track_record as BTR


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
# 30.08.2026: baue() haelt Treffer bis zum Anpfiff und liest den Halte-Zustand aus
# killer_state.json, wenn er nicht injiziert wird. Diese Tests pruefen die AUSWAHL, nicht das
# Halten — sie muessen mit leerem Zustand starten, sonst mischt sich der echte Slate darunter.
LEER = {"latch": {}}
KO = (NOW + timedelta(hours=3)).isoformat().replace("+00:00", "Z")


def sig(**kw):
    d = {"fav": "H", "share": 0.74, "odd": 1.80, "entryOdd": 1.78,
         "pinnClose": None, "pinnFair": None, "conc": True, "inflow": True, "dir": "in"}
    d.update(kw)
    return d


def state(signals=None, **kw):
    e = {"league": "English Premier League", "home": "Arsenal", "away": "Chelsea",
         "country": "GB", "kickoff": KO, "signals": signals or {"Match Odds": sig()}}
    e.update(kw)
    return {"pending": {"1": e}}


def cons(**kw):
    g = {"matchId": "1", "home": "Arsenal", "away": "Chelsea", "moneySide": "home",
         "poly": {"sharePct": 71, "vol": 40000, "odd": 1.75},
         "pinn": {"home": 0.58, "draw": 0.24, "away": 0.18, "fav": "home"},
         "pinnMove": {"movePP": 2.4, "stepPP": 0.6, "n": 5, "move": True, "laeuft": True},
         "verdict": "konsens"}
    g.update(kw)
    return {"games": [g]}


class Tor(unittest.TestCase):
    def test_schwellen_sind_gespiegelt_nicht_nachgebaut(self):
        # Laufen sie auseinander, empfiehlt die Sektion eine andere Menge, als spaeter
        # abgerechnet wird — genau der Fehler, den sharp_gate.py fuer die Wallets behoben hat.
        self.assertEqual(killer.CONC_THRESHOLD, BTR.CONC_THRESHOLD)
        self.assertEqual(killer.INFLOW_MIN_EUR, BTR.INFLOW_MIN_EUR)

    def test_alle_drei_bedingungen_noetig(self):
        self.assertTrue(killer.kern_ok(sig()))
        for weg in ({"conc": False}, {"inflow": False}, {"dir": "out"}, {"dir": "flat"}, {"dir": None}):
            self.assertFalse(killer.kern_ok(sig(**weg)), weg)

    def test_fehlende_angabe_ist_kein_ja(self):
        self.assertFalse(killer.kern_ok(None))
        self.assertFalse(killer.kern_ok({}))
        self.assertFalse(killer.kern_ok(sig(odd=None)))

    def test_quotenband(self):
        self.assertFalse(killer.kern_ok(sig(odd=1.10)), "unter 1.30 zahlt keine Kante die Varianz")
        self.assertFalse(killer.kern_ok(sig(odd=40.0)), "das ist eine Lotterie, kein Geld-Signal")
        self.assertTrue(killer.kern_ok(sig(odd=1.30)))
        self.assertTrue(killer.kern_ok(sig(odd=15.0)))


class Auswahl(unittest.TestCase):
    def test_stufe1_braucht_poly_und_pinnacle(self):
        out = killer.baue(state(), cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 1)
        self.assertEqual(out["stufe1"][0]["name"], "Arsenal")

    def test_ohne_poly_nur_stufe2(self):
        out = killer.baue(state(), cons(poly=None), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 0)
        self.assertEqual(len(out["stufe2"]), 1)
        self.assertIsNone(out["stufe2"][0]["poly"])

    def test_poly_auf_der_anderen_seite_zaehlt_nicht(self):
        out = killer.baue(state(), cons(moneySide="away"), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 0, "Poly-Geld auf der Gegenseite ist keine Deckung")

    def test_poly_zu_duenn_zaehlt_nicht(self):
        c = cons(poly={"sharePct": 52, "vol": 40000, "odd": 1.9})
        out = killer.baue(state(), c, {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 0)

    def test_angepfiffene_spiele_fliegen_raus(self):
        # Der Track erfasst NUR vor Anpfiff. Waere ein laufendes Spiel drin, wuerde die Sektion
        # etwas empfehlen, das nie in ihre eigene Messung eingeht.
        st = state()
        st["pending"]["1"]["kickoff"] = (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        out = killer.baue(st, cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(out["stufe1"] + out["stufe2"], [])

    def test_verlierender_liga_eimer_fliegt_raus(self):
        tr = {"byLeagueMarket": {"English Premier League|Match Odds": {"n": 40, "roi": -0.22, "roiUg": -0.15}}}
        out = killer.baue(state(), cons(), tr, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(out["stufe1"] + out["stufe2"], [],
                         "belegt verlierender Eimer gehoert nicht in eine Empfehlung")

    def test_duenner_liga_eimer_blockiert_nicht(self):
        tr = {"byLeagueMarket": {"English Premier League|Match Odds": {"n": 6, "roi": -0.9}}}
        out = killer.baue(state(), cons(), tr, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 1, "ohne Untergrenze gibt es kein Urteil, also kein Veto")

    def test_ein_eimer_ohne_untergrenze_vetot_nicht_egal_wie_schlecht_der_roi_aussieht(self):
        """04.09.2026 (Lucas-Betfair-Check). Vorher reichten n>=15 und ROI <= -10%. Gemessen
        erfuellten das 57 Buckets — und jede dieser Zeilen flog aus „Top-Wetten jetzt", obwohl
        ueber alle 1.641 Buckets nur DREI ueberhaupt eine Untergrenze tragen. Median-n ist 5."""
        tr = {"byLeagueMarket": {"English Premier League|Match Odds": {"n": 20, "roi": -0.35}}}
        out = killer.baue(state(), cons(), tr, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 1,
                         "-35% auf n=20 ist ein Punktschaetzer, kein belegter Verlust")

    def test_nur_match_odds(self):
        st = state(signals={"Over/Under 2.5 Goals": sig(fav="OVER")})
        out = killer.baue(st, cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(out["stufe1"] + out["stufe2"], [])


class Verstaerker(unittest.TestCase):
    def test_pinnacle_bewegung_wird_zum_chip(self):
        out = killer.baue(state(), cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        arten = [v["art"] for v in out["stufe1"][0]["verstaerker"]]
        self.assertIn("pinnMove", arten)

    def test_rauschen_ist_kein_chip(self):
        c = cons(pinnMove={"movePP": 0.3, "stepPP": 0.1, "n": 5, "move": False, "laeuft": True})
        out = killer.baue(state(), c, {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertNotIn("pinnMove", [v["art"] for v in out["stufe1"][0]["verstaerker"]])

    def _serie(self, **kw):
        d = {"team": "Arsenal", "market": "Ungeschlagen", "length": 9,
             "continuation": {"state": "intakt", "ratePct": 80}, "leagueName": "Premier League"}
        d.update(kw)
        return d

    def test_serie_nur_wenn_intakt_und_fuer_die_gespielte_seite(self):
        streaks = {"streaks": [self._serie(),
                               self._serie(team="Chelsea", length=12,
                                           continuation={"state": "gebrochen"})]}
        out = killer.baue(state(), cons(), {}, streaks, now=NOW, latch_state=LEER)
        self.assertEqual(out["stufe1"][0]["streak"]["laenge"], 9)
        out2 = killer.baue(state(), cons(moneySide="home"), {},
                           {"streaks": [streaks["streaks"][1]]}, now=NOW, latch_state=LEER)
        self.assertIsNone(out2["stufe1"][0]["streak"], "eine gebrochene Serie ist kein Verstaerker")

    # 30.08.2026 (Lucas-Checkup, dritte Runde): an der Chelsea-SIEGWETTE hing „Ueber 3,5 Karten
    # x7" als Verstaerker. Eine Kartenserie sagt nichts darueber, wer gewinnt.
    def test_serie_muss_vom_ausgang_handeln(self):
        for markt in ("Über 3,5 Karten", "Über 2,5 Tore", "Beide Teams treffen",
                      "Über 9,5 Ecken", "Team trifft"):
            out = killer.baue(state(), cons(), {},
                              {"streaks": [self._serie(market=markt, length=15)]},
                              now=NOW, latch_state=LEER)
            self.assertIsNone(out["stufe1"][0]["streak"], markt)
        for markt in ("Ungeschlagen", "Sieg-Serie", "Zu null"):
            out = killer.baue(state(), cons(), {},
                              {"streaks": [self._serie(market=markt)]}, now=NOW, latch_state=LEER)
            self.assertIsNotNone(out["stufe1"][0]["streak"], markt)

    def test_team_trifft_ist_tapete_keine_serie(self):
        # Von 205 „Team trifft"-Serien in liga+mls sind 192 intakt — 94%. Ein Chip, der bei fast
        # jedem Team feuert, traegt keine Information; dieselbe Lehre wie beim Torjaeger-Signal.
        self.assertNotIn("team trifft", killer.SERIEN_MAERKTE)

    def test_kurze_serie_zaehlt_nicht(self):
        # Lazio trug „Team trifft x3" bei Grundrate 67%. Die Serien-Kachel filtert bei >= 4.
        out = killer.baue(state(), cons(), {},
                          {"streaks": [self._serie(length=3)]}, now=NOW, latch_state=LEER)
        self.assertIsNone(out["stufe1"][0]["streak"])
        self.assertEqual(killer.SERIEN_MIN_LAENGE, 4)

    def test_die_laengste_serie_gewinnt_nicht_die_erste(self):
        # Inter hat „Ungeschlagen x15" UND „Team trifft x15"; angezeigt wurde, was zufaellig
        # zuerst im Array stand.
        streaks = {"streaks": [self._serie(market="Sieg-Serie", length=5),
                               self._serie(market="Ungeschlagen", length=11)]}
        out = killer.baue(state(), cons(), {}, streaks, now=NOW, latch_state=LEER)
        self.assertEqual(out["stufe1"][0]["streak"]["laenge"], 11)

    def test_verstaerker_heben_den_rang(self):
        viel = killer.baue(state(), cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)["stufe1"][0]
        wenig = killer.baue(state(), cons(poly=None, pinn=None, pinnMove=None), {},
                            {"streaks": []}, now=NOW, latch_state=LEER)["stufe2"][0]
        self.assertGreater(viel["rang"], wenig["rang"])

    def test_preis_wird_mitgeschrieben_aber_nicht_gefiltert(self):
        # 29.08.2026: die Preis-Bedingung (pinnFair x Quote >= 1) stand in den Daten ANDERSHERUM
        # (Wert>=0: -29,4% n=30 · Wert<0: +16,1% n=83). Also nur protokollieren.
        st = state(signals={"Match Odds": sig(pinnFair=0.50)})   # 0.50 x 1.80 - 1 = -0.10
        out = killer.baue(st, cons(), {}, {"streaks": []}, now=NOW, latch_state=LEER)
        self.assertEqual(len(out["stufe1"]), 1, "negativer Wert darf NICHT filtern")
        self.assertAlmostEqual(out["stufe1"][0]["wertVsPinn"], -0.10, places=2)


class Schublade(unittest.TestCase):
    def rows(self, n, win_ab=0, **kw):
        d = {"market": "Match Odds", "conc": True, "inflow": True, "dir": "in",
             "odd": 2.0, "clvBf": 1.0, "settledAt": "2026-08-29T12:00:00Z"}
        d.update(kw)
        return [dict(d, win=(i >= win_ab)) for i in range(n)]

    def test_nur_die_konjunktion_zaehlt(self):
        rows = self.rows(10) + self.rows(10, conc=False) + self.rows(10, dir="out") \
            + self.rows(10, inflow=False) + self.rows(10, market="Half Time")
        s = killer.schublade(rows)
        self.assertEqual(len(s["renditen"]), 10)

    def test_closing_quote_nicht_einstiegsquote(self):
        # entryOdd waere Look-ahead: das Signal steht am SCHLUSS fest, der Einstiegspreis war
        # vorher. Wer so rechnet, kauft sich einen Vorteil, den es nicht gab.
        s = killer.schublade(self.rows(4, odd=2.0, entryOdd=5.0))
        self.assertTrue(all(abs(r - 1.0) < 1e-9 for r in s["renditen"]))

    def test_clv_kommt_roh_mit(self):
        s = killer.schublade(self.rows(5, clvBf=2.5))
        self.assertEqual(s["clvs"], [2.5] * 5)

    def test_quotenband_gilt_auch_rueckwaerts(self):
        self.assertEqual(killer.schublade(self.rows(5, odd=1.05))["renditen"], [])

    def test_leere_eingabe(self):
        s = killer.schublade([])
        self.assertEqual((s["renditen"], s["clvs"], s["letzter"]), ([], [], None))


class Bilanz(unittest.TestCase):
    """30.08.2026 (Lucas: „damit ich seh wie gut es performt"). Die Bilanz DER SEKTION —
    nicht die des Betfair-Tracks, aus dem der Badge bisher seine Zahl bezog."""

    def zeile(self, **kw):
        d = {"k": "x", "dataset": "wm", "status": "abgerechnet", "stufe": 2,
             "haltePreis": 2.0, "schlussPreis": 1.8, "win": True, "name": "Team",
             "liga": "EPL", "settledAt": "2026-08-30T12:00:00Z"}
        d.update(kw)
        return d

    def test_zum_haltepreis_nicht_zur_schlussquote(self):
        # Der Haltepreis ist der einzige, der tatsaechlich nehmbar war.
        b = killer.bilanz([self.zeile(haltePreis=2.5, schlussPreis=1.2, win=True)])
        self.assertAlmostEqual(b["gesamt"]["einheiten"], 1.5, 2)

    def test_gewinn_und_verlust_werden_getrennt_gezaehlt(self):
        b = killer.bilanz([self.zeile(k="a", win=True), self.zeile(k="b", win=False)])
        g = b["gesamt"]
        self.assertEqual((g["n"], g["gewonnen"], g["verloren"]), (2, 1, 1))
        self.assertAlmostEqual(g["einheiten"], 0.0, 2)
        self.assertAlmostEqual(g["roi"], 0.0, 3)

    def test_je_stufe_getrennt(self):
        # Die zwei Stufen sind der ganze Punkt der Sektion — sie muessen einzeln ablesbar sein.
        b = killer.bilanz([self.zeile(k="a", stufe=1, win=True),
                           self.zeile(k="b", stufe=2, win=False)])
        self.assertEqual(b["jeStufe"]["1"]["gewonnen"], 1)
        self.assertEqual(b["jeStufe"]["2"]["verloren"], 1)

    def test_offene_zeilen_zaehlen_nicht_mit_aber_werden_gezaehlt(self):
        b = killer.bilanz([self.zeile(k="a"), self.zeile(k="b", status="offen")])
        self.assertEqual(b["gesamt"]["n"], 1)
        self.assertEqual(b["offen"], 1)

    def test_void_ist_weder_treffer_noch_fehlschlag(self):
        b = killer.bilanz([self.zeile(status="void", win=None)])
        self.assertEqual(b["gesamt"]["n"], 0)
        self.assertEqual(b["offen"], 0)

    def test_unbrauchbare_quote_fliegt_raus(self):
        for o in (None, 1.0, 0, 40.0):
            self.assertEqual(killer.bilanz([self.zeile(haltePreis=o)])["gesamt"]["n"], 0, o)

    def test_leeres_buch_erfindet_nichts(self):
        b = killer.bilanz([])
        self.assertEqual(b["gesamt"]["n"], 0)
        self.assertIsNone(b["gesamt"]["roi"])
        self.assertEqual(b["zeilen"], [])

    def test_juengste_zeilen_zuerst(self):
        b = killer.bilanz([self.zeile(k="alt", settledAt="2026-08-29T10:00:00Z", name="Alt"),
                           self.zeile(k="neu", settledAt="2026-08-30T10:00:00Z", name="Neu")])
        self.assertEqual([z["name"] for z in b["zeilen"]], ["Neu", "Alt"])


class Register(unittest.TestCase):
    def test_schublade_landet_im_freigabe_register(self):
        import freigabe
        rows = [dict(market="Match Odds", conc=True, inflow=True, dir="in", odd=2.0,
                     clvBf=1.0, win=(i % 3 != 0), settledAt="2026-08-29T12:00:00Z")
                for i in range(40)]
        z = freigabe.killer_schublade(rows, now=datetime(2026, 8, 29, 18, tzinfo=timezone.utc))
        # 30.08.2026: die Sektion haelt ihre Treffer jetzt bis zum Anpfiff. Das ist eine andere
        # Menge als der Schluss-Stand, den betfair_track_record abrechnet — deshalb kann hier
        # eine zweite Zeile („gehalten", zum Haltepreis) danebenstehen.
        # 31.08.2026: der Schluss-Stand ist in zwei Zuschnitte geteilt. Diese Zeilen tragen
        # keine Liga, gehoeren also alle in „uebrige Ligen" — eine unbekannte Liga darf nicht
        # als Top-5 durchgehen.
        rest = [r for r in z if r["schublade"] == "Konjunktion · übrige Ligen"]
        self.assertEqual(len(rest), 1, [r["schublade"] for r in z])
        self.assertEqual(rest[0]["n"], 40)
        self.assertIsNotNone(rest[0]["clvLb"], "anders als die Aggregat-Schubladen hat diese CLV")
        self.assertEqual([r for r in z if r["schublade"] == "Konjunktion · Top-5 + MLS"], [])

    def test_beide_zuschnitte_erscheinen_getrennt(self):
        """31.08.2026: Top-5 und Rest qualifizieren sich getrennt — je eine eigene Zeile."""
        import freigabe
        def row(liga, i):
            return dict(market="Match Odds", league=liga, conc=True, inflow=True, dir="in",
                        odd=2.0, clvBf=1.0, win=(i % 3 != 0), settledAt="2026-08-29T12:00:00Z")
        rows = ([row("English Premier League", i) for i in range(12)]
                + [row("Ukrainian Premier League", i) for i in range(30)])
        z = freigabe.killer_schublade(rows, now=datetime(2026, 8, 29, 18, tzinfo=timezone.utc))
        namen = {r["schublade"]: r["n"] for r in z}
        self.assertEqual(namen.get("Konjunktion · Top-5 + MLS"), 12)
        self.assertEqual(namen.get("Konjunktion · übrige Ligen"), 30)

    def test_ohne_zeilen_keine_schluss_schublade(self):
        import freigabe
        z = freigabe.killer_schublade([])
        self.assertEqual([r for r in z if str(r["schublade"]).startswith("Konjunktion · ")
                          and "gehalten" not in r["schublade"]], [])


class BilanzUntergrenze(unittest.TestCase):
    """30.08.2026: der Badge wurde gruen, sobald der ROI-PUNKTSCHAETZER ueber null lag.

    Bei n=32 / ROI +7,2% lag die einseitige 95%-Untergrenze bei -20,1% — waehrend die Fusszeile
    derselben Sektion weiter „keine Freigabe" sagte. Die Bilanz liefert die Untergrenze jetzt
    mit, damit die Anzeige denselben Richter benutzt wie freigabe.py.
    """

    @staticmethod
    def _led(gewinne, verluste, odd=2.0):
        z = []
        for i in range(gewinne + verluste):
            z.append({"status": "abgerechnet", "haltePreis": odd, "win": i < gewinne,
                      "stufe": 2, "name": f"T{i}", "liga": "L", "settledAt": "2026-08-29T12:00:00Z"})
        return z

    def test_untergrenze_liegt_unter_dem_punktschaetzer(self):
        b = killer.bilanz(self._led(19, 13))["gesamt"]
        self.assertGreater(b["roi"], 0)
        self.assertIsNotNone(b["roiLb"])
        self.assertLess(b["roiLb"], b["roi"])

    def test_ein_duennes_buch_belegt_nichts(self):
        # 32 Zeilen bei Quote 2.0 und 19 Treffern: +18,75% Punktschaetzer, Untergrenze klar negativ.
        b = killer.bilanz(self._led(19, 13))["gesamt"]
        self.assertLess(b["roiLb"], 0, "so duenn ist nichts belegt")

    def test_bei_klarer_kante_wird_die_untergrenze_positiv(self):
        b = killer.bilanz(self._led(160, 40))["gesamt"]
        self.assertGreater(b["roiLb"], 0)

    def test_unter_zwei_zeilen_gibt_es_keine_untergrenze(self):
        self.assertIsNone(killer.bilanz(self._led(1, 0))["gesamt"]["roiLb"])
        self.assertIsNone(killer.bilanz([])["gesamt"]["roiLb"])

    def test_je_stufe_hat_eigene_untergrenze(self):
        led = self._led(5, 1)
        for r in led:
            r["stufe"] = 1
        b = killer.bilanz(led + self._led(14, 12))
        self.assertIsNotNone(b["jeStufe"]["1"]["roiLb"])
        self.assertIsNotNone(b["jeStufe"]["2"]["roiLb"])

    def test_die_rohwerte_bleiben_draussen(self):
        # Die Renditeliste ist ein Zwischenschritt, kein Feld fuer killer.json.
        self.assertNotIn("renditen", killer.bilanz(self._led(3, 2))["gesamt"])


if __name__ == "__main__":
    unittest.main()


class TestLigenZuschnitt(unittest.TestCase):
    """31.08.2026 (Lucas: „nur die Top 5 lassen oder erweitert?").

    Gemessen war die Frage nicht entscheidbar: Top-5 hatte den besseren ROI-Punktschätzer
    (n=10), die übrigen Ligen den einzigen CLV mit Untergrenze über null (n=70). Statt zu
    raten werden beide Zuschnitte getrennt qualifiziert — hier wird festgehalten, dass der
    Filter wirklich trennt und keine Zeile doppelt oder gar nicht zählt.
    """

    def _rows(self):
        def r(liga, win, odd=2.0):
            return {"market": "Match Odds", "league": liga, "conc": True, "inflow": True,
                    "dir": "in", "odd": odd, "win": win, "clvBf": 1.0,
                    "settledAt": "2026-08-30T12:00:00+00:00"}
        return [r("English Premier League", True), r("US MLS", False),
                r("Ukrainian Premier League", True), r("Chilean Primera Division", False),
                r("Mexican Liga MX", True)]

    def test_top5_nimmt_nur_top5_und_mls(self):
        self.assertEqual(len(killer.schublade(self._rows(), scope="top5")["renditen"]), 2)

    def test_rest_nimmt_den_ganzen_rest(self):
        self.assertEqual(len(killer.schublade(self._rows(), scope="rest")["renditen"]), 3)

    def test_zusammen_ergeben_sie_wieder_das_ganze(self):
        """Kein Zuschnitt darf Zeilen verlieren oder doppelt zählen."""
        ganz = killer.schublade(self._rows())
        a = killer.schublade(self._rows(), scope="top5")
        b = killer.schublade(self._rows(), scope="rest")
        self.assertEqual(len(a["renditen"]) + len(b["renditen"]), len(ganz["renditen"]))
        self.assertAlmostEqual(sum(a["renditen"]) + sum(b["renditen"]), sum(ganz["renditen"]))

    def test_unbekannte_liga_landet_im_rest_nicht_im_nichts(self):
        """Eine neue Liga darf nicht stillschweigend aus BEIDEN Zuschnitten fallen."""
        self.assertTrue(killer.im_zuschnitt("Irgendeine Neue Liga", "rest"))
        self.assertFalse(killer.im_zuschnitt("Irgendeine Neue Liga", "top5"))

    def test_ohne_scope_bleibt_alles(self):
        self.assertTrue(killer.im_zuschnitt("Was auch immer", None))
        self.assertEqual(len(killer.schublade(self._rows())["renditen"]), 5)

    def test_leere_liga_kippt_nicht(self):
        for liga in (None, "", 5):
            self.assertFalse(killer.im_zuschnitt(liga, "top5"))
            self.assertTrue(killer.im_zuschnitt(liga, "rest"))


# ── 01.09.2026 (Lucas: „poly taucht da mmn nie aktiv auf? nur betfair und pini") ───────────────
# Er hatte recht. `(poly.get("sharePct") or 0) >= 60` machte aus einem UNBEKANNTEN Anteil eine 0,
# also ein Nein. Unbekannt ist er systematisch: die Holder-Anteile stehen nur im ~3h-Close-Freeze;
# weiter draussen liefert `poly_money_upcoming.json` Preis und Volumen, aber KEIN `shares`-Feld
# (0 von 120 Eintraegen). Bei 22% der gelatchten Zeilen konnte Poly deshalb gar nicht zustimmen —
# angezeigt identisch zu „Poly ist dagegen".
class TestPolyDreiZustaende(unittest.TestCase):
    def _zeile(self, poly, seite="home"):
        sig = {"fav": "H", "odd": 2.0, "conc": True, "inflow": True, "dir": "in", "share": 0.8}
        eintrag = {"home": "A", "away": "B", "league": "L", "kickoff": "2026-09-02T18:00:00Z"}
        cons = {"moneySide": seite, "poly": poly, "pinn": {"fav": "home"}}
        return killer.zeile("1", eintrag, sig, cons, None, None)

    def test_poly_stimmt_zu(self):
        z = self._zeile({"sharePct": 71, "vol": 9000, "odd": 1.5})
        self.assertEqual(z["polyStatus"], "ja")
        self.assertIsNotNone(z["poly"])
        self.assertEqual(z["stufe"], 1, "Poly + Pinnacle = Stufe 1")

    def test_poly_ist_bekannt_aber_zu_duenn(self):
        z = self._zeile({"sharePct": 48, "vol": 9000, "odd": 1.5})
        self.assertEqual(z["polyStatus"], "nein", "48% ist ein echtes Nein")
        self.assertIsNone(z["poly"])
        self.assertEqual(z["stufe"], 2)

    def test_poly_auf_der_ANDEREN_seite_ist_ein_nein(self):
        z = self._zeile({"sharePct": 80, "vol": 9000, "odd": 1.5}, seite="away")
        self.assertEqual(z["polyStatus"], "nein")

    def test_unbekannter_anteil_ist_KEIN_nein(self):
        # Der Kern: sharePct None (Spiel ausserhalb des Close-Freeze) darf nicht wie 0% wirken.
        z = self._zeile({"sharePct": None, "vol": 36373, "odd": 2.06})
        self.assertEqual(z["polyStatus"], "unbekannt")
        self.assertIsNone(z["poly"])

    def test_gar_kein_poly_markt_ist_auch_unbekannt(self):
        self.assertEqual(self._zeile(None)["polyStatus"], "unbekannt")

    def test_unbekannt_oeffnet_KEINE_stufe_1(self):
        # Fehlende Information ist keine Erlaubnis — das bleibt. Sichtbar wird nur der Unterschied.
        z = self._zeile({"sharePct": None, "vol": 36373, "odd": 2.06})
        self.assertEqual(z["stufe"], 2, "ohne echtes Ja keine Stufe 1")
