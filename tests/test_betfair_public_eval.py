"""test_betfair_public_eval.py — Auswertung der öffentlichen Betfair-Pushs (31.07.2026, Lucas).
Grading gegen End-/HT-Stand (wiederverwendet betfair_track_record), Bilanz (Treffer/ROI)."""
import os, sys, unittest
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_public_eval as E

NOW = datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc)


def _p(mid, market, lead, odd, home="A", away="B", scn="fresh", ht=None):
    return {"k": mid, "matchId": mid, "scenario": scn, "market": market, "league": "L",
            "home": home, "away": away, "leadName": lead, "leadOdd": odd, "value": 30000,
            "sentAt": "2026-07-31T05:00:00+00:00", "status": "pending", "htScore": ht}


def _fin(mid, h, a, is_ht=False):
    return {"matchId": mid, "liveInfo": {"finished": True, "goal_v1": h, "goal_v2": a, "is_ht": is_ht}}


class TestSettle(unittest.TestCase):
    def test_over_under_win(self):
        led = [_p("100", "Over/Under 3.5 Goals", "Over 3.5 Goals", 2.0)]
        E.settle(led, {"matches": [_fin("100", 3, 2)]}, NOW)   # 5 Tore → OVER
        self.assertEqual(led[0]["status"], "won")
        self.assertAlmostEqual(led[0]["profit"], 1.0)

    def test_1x2_loss(self):
        led = [_p("102", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        E.settle(led, {"matches": [_fin("102", 1, 2)]}, NOW)   # Auswärtssieg → H verliert
        self.assertEqual(led[0]["status"], "lost")
        self.assertAlmostEqual(led[0]["profit"], -1.0)

    def test_ht_under_win_with_captured_score(self):
        led = [_p("101", "First Half Goals 1.5", "Under 1.5 Goals", 1.5, scn="ht", ht=[0, 0])]
        E.settle(led, {"matches": [_fin("101", 1, 1)]}, NOW)   # HT 0:0 → UNDER 1.5
        self.assertEqual(led[0]["status"], "won")

    def test_ht_market_without_score_is_void(self):
        led = [_p("103", "Half Time", "A", 2.0, scn="ht")]     # kein HT-Stand eingefangen
        E.settle(led, {"matches": [_fin("103", 2, 0)]}, NOW)
        self.assertEqual(led[0]["status"], "void")             # nicht abrechenbar → nicht gezählt

    def test_expire_stale_pending(self):
        led = [_p("999", "Match Odds", "A", 2.0)]              # sentAt 05:00, NOW +3d später
        late = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
        E.settle(led, {"matches": []}, late)
        self.assertEqual(led[0]["status"], "expired")

    def test_results_endpoint_rescues_orphan(self):
        # 10.08.2026 (Lucas): Push, dessen Spiel aus dem Feed fiel → ueber POST /results autoritativ abrechnen.
        led = [_p("300", "Match Odds", "TeamH", 2.0, home="TeamH", away="TeamA")]
        fake = lambda ids: {"300": {"goal_v1": 2, "goal_v2": 0, "finished": True}}
        E.settle(led, {"matches": []}, NOW, results_fetch=fake)   # leerer Feed, Fetcher liefert 2:0
        self.assertEqual(led[0]["status"], "won")                # Heim gewinnt
        self.assertAlmostEqual(led[0]["profit"], 1.0)

    def test_results_endpoint_ignores_unfinished(self):
        led = [_p("301", "Match Odds", "TeamH", 2.0, home="TeamH", away="TeamA")]
        fake = lambda ids: {"301": {"goal_v1": 1, "goal_v2": 0, "finished": False}}
        E.settle(led, {"matches": []}, NOW, results_fetch=fake)
        self.assertEqual(led[0]["status"], "pending")            # laeuft noch → nicht abrechnen

    def test_consensus_split(self):
        # 10.08.2026 (Lucas): Split nach Konsens-Zweitmeinung — agree vs uneinig getrennt ausgewertet.
        led = [
            {**_p("400", "Match Odds", "TeamH", 2.0, home="TeamH", away="TeamA"),
             "consensus": {"verdict": "konsens", "agree": True}},
            {**_p("401", "Match Odds", "TeamH", 2.0, home="TeamH", away="TeamA"),
             "consensus": {"verdict": "uneinig", "agree": False}},
        ]
        E.settle(led, {"matches": [_fin("400", 2, 0), _fin("401", 0, 1)]}, NOW)  # 400 Heim gewinnt, 401 verliert
        rec = E.summarize(led, NOW)
        self.assertEqual(rec["consensusSplit"]["agree"]["wins"], 1)
        self.assertEqual(rec["consensusSplit"]["disagree"]["wins"], 0)
        self.assertIn("konsens", rec["byConsensus"])
        self.assertIn("uneinig", rec["byConsensus"])


class TestCaptureHt(unittest.TestCase):
    def test_captures_halftime_score(self):
        led = [_p("200", "First Half Goals 1.5", "Under 1.5 Goals", 1.5, scn="ht")]
        prices = {"matches": [{"matchId": "200", "liveInfo": {"is_ht": True, "goal_v1": 1, "goal_v2": 0, "finished": False}}]}
        E.capture_ht(led, prices, NOW)
        self.assertEqual(led[0]["htScore"], [1, 0])


class TestSettleFromTrack(unittest.TestCase):
    """07.08.2026: Push-Bilanz erbt die Abrechnungen des breiten Track-Records (auch Verschwinde-Settle)."""

    def test_erbt_finished_vom_track(self):
        led = [_p("500", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        tr = [{"matchId": "500", "market": "Match Odds", "ft": [2, 0], "ht": None}]
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "won")
        self.assertEqual(led[0]["via"], "track")
        self.assertAlmostEqual(led[0]["profit"], 0.8)

    def test_erbt_auch_ohne_eigenen_feed(self):
        # Feed hier LEER — der Push wird trotzdem ueber den Track abgerechnet, danach laesst
        # der eigene Feed-Pfad den bereits gesettelten in Ruhe.
        led = [_p("501", "Over/Under 2.5 Goals", "Under 2.5 Goals", 1.5)]
        tr = [{"matchId": "501", "market": "Over/Under 2.5 Goals", "ft": [1, 0], "ht": None, "via": "vanish"}]
        E.settle_from_track(led, tr, NOW)
        E.settle(led, {"matches": []}, NOW)
        self.assertEqual(led[0]["status"], "won")            # 1 Tor < 2.5 → UNDER trifft

    def test_ht_markt_ohne_ht_stand_bleibt_pending(self):
        led = [_p("502", "Half Time", "A", 2.0, scn="ht")]
        tr = [{"matchId": "502", "market": "Half Time", "ft": [2, 0], "ht": None}]
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "pending")        # nicht abrechenbar → spaeter Feed/TTL

    def test_kein_track_treffer_bleibt_pending(self):
        led = [_p("503", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        E.settle_from_track(led, [], NOW)
        self.assertEqual(led[0]["status"], "pending")

    def test_alte_track_zeile_ohne_ft_ht_ignoriert(self):
        led = [_p("504", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        tr = [{"matchId": "504", "market": "Match Odds"}]    # alte Zeile ohne ft/ht → ignorieren
        E.settle_from_track(led, tr, NOW)
        self.assertEqual(led[0]["status"], "pending")


class TestSummarize(unittest.TestCase):
    def test_hitrate_roi_and_splits(self):
        led = [
            {"status": "won", "scenario": "fresh", "market": "Over/Under 3.5 Goals", "leadOdd": 2.0, "profit": 1.0},
            {"status": "lost", "scenario": "fresh", "market": "Match Odds", "leadOdd": 1.8, "profit": -1.0},
            {"status": "won", "scenario": "ht", "market": "First Half Goals 1.5", "leadOdd": 1.5, "profit": 0.5},
            {"status": "pending", "scenario": "fresh", "market": "Match Odds", "leadOdd": 2.0},
        ]
        r = E.summarize(led, NOW)
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["wins"], 2)
        self.assertAlmostEqual(r["hitRate"], 2/3, places=3)
        self.assertAlmostEqual(r["roi"], 0.5/3, places=3)
        self.assertEqual(r["pending"], 1)
        self.assertIn("fresh", r["byScenario"])
        self.assertIn("ht", r["byScenario"])
        self.assertEqual(r["byScenario"]["ht"]["wins"], 1)


def _settled(mid, market, lead, odd, status, ft, via="track", home="Plymouth", away="Exeter",
             settledAt="2026-07-31T21:00:00+00:00", ht=None, profit=None, resChk=None):
    e = {"k": mid, "matchId": mid, "scenario": "fresh", "market": market, "league": "L",
         "home": home, "away": away, "leadName": lead, "leadOdd": odd, "value": 30000,
         "sentAt": "2026-07-31T05:00:00+00:00", "status": status, "htScore": ht,
         "settledAt": settledAt, "ftScore": ft, "via": via}
    if profit is not None:
        e["profit"] = profit
    if resChk is not None:
        e["resChk"] = resChk
    return e


def _boom(ids):
    raise AssertionError("results_fetch darf hier nicht aufgerufen werden")


class TestVerifySettled(unittest.TestCase):
    # 11.08.2026 (Lucas, Plymouth-Fall): Live-Goal-Feed hing auf 0:0 -> faelschlich 'lost'; /results ist die Wahrheit.
    def test_flips_stuck_live_score(self):
        led = [_settled("500", "Match Odds", "Plymouth", 1.53, "lost", [0, 0])]
        fake = lambda ids: {"500": {"goal_v1": 2, "goal_v2": 0, "finished": True}}
        E.verify_settled(led, NOW, results_fetch=fake)
        self.assertEqual(led[0]["status"], "won")
        self.assertAlmostEqual(led[0]["profit"], 0.53)
        self.assertEqual(led[0]["ftScore"], [2, 0])
        self.assertEqual(led[0]["via"], "results-fix")
        self.assertTrue(led[0]["resChk"])

    def test_confirms_correct_without_change(self):
        led = [_settled("501", "Match Odds", "Plymouth", 1.53, "won", [2, 0], profit=0.53)]
        fake = lambda ids: {"501": {"goal_v1": 2, "goal_v2": 0, "finished": True}}
        E.verify_settled(led, NOW, results_fetch=fake)
        self.assertEqual(led[0]["status"], "won")
        self.assertEqual(led[0]["via"], "track")          # unveraendert, weil Ergebnis uebereinstimmt
        self.assertAlmostEqual(led[0]["profit"], 0.53)
        self.assertTrue(led[0]["resChk"])                 # aber als geprueft markiert

    def test_unknown_result_leaves_entry_and_retries(self):
        led = [_settled("503", "Match Odds", "Plymouth", 1.53, "lost", [0, 0])]
        E.verify_settled(led, NOW, results_fetch=lambda ids: {})   # /results kennt Spiel nicht
        self.assertEqual(led[0]["status"], "lost")        # unveraendert
        self.assertNotIn("resChk", led[0])                # NICHT markiert -> naechster Lauf erneut

    def test_skips_authoritative_and_checked(self):
        led = [_settled("504", "Match Odds", "Plymouth", 1.53, "lost", [0, 0], via="results"),
               _settled("505", "Match Odds", "Plymouth", 1.53, "lost", [0, 0], resChk=True)]
        E.verify_settled(led, NOW, results_fetch=_boom)   # darf gar nicht fetchen
        self.assertEqual(led[0]["status"], "lost")
        self.assertEqual(led[1]["status"], "lost")

    def test_outside_window_skipped(self):
        led = [_settled("506", "Match Odds", "Plymouth", 1.53, "lost", [0, 0],
                        settledAt="2026-07-29T00:00:00+00:00")]   # ~70h vor NOW > 30h
        E.verify_settled(led, NOW, results_fetch=_boom)
        self.assertEqual(led[0]["status"], "lost")

    def test_no_fetcher_is_noop(self):
        led = [_settled("507", "Match Odds", "Plymouth", 1.53, "lost", [0, 0])]
        E.verify_settled(led, NOW, results_fetch=None)
        self.assertEqual(led[0]["status"], "lost")



class TestManualResults(unittest.TestCase):
    """11.08.2026 (Lucas, Plymouth): manuell gepinnter Endstand ueberschreibt auch bereits (falsch)
    abgerechnete Zeilen und schlaegt Feed/Vanish."""
    def test_flips_wrong_lost_to_won(self):
        led = [_p("777", "Match Odds", "TeamH", 1.53, home="TeamH", away="TeamA")]
        led[0].update({"status": "lost", "ftScore": [0, 0], "via": "track", "profit": -1.0})
        E.apply_manual_results(led, {"777": {"ft": [2, 0]}}, NOW)
        self.assertEqual(led[0]["status"], "won")
        self.assertEqual(led[0]["ftScore"], [2, 0])
        self.assertEqual(led[0]["via"], "manual")
        self.assertTrue(led[0]["resChk"])
        self.assertAlmostEqual(led[0]["profit"], 0.53)

    def test_flips_win_to_loss_when_pinned_says_so(self):
        led = [_p("778", "Match Odds", "TeamH", 2.0, home="TeamH", away="TeamA")]
        led[0].update({"status": "won", "ftScore": [1, 0], "via": "finished", "profit": 1.0})
        E.apply_manual_results(led, {"778": {"ft": [0, 1]}}, NOW)   # in Wahrheit Auswaertssieg
        self.assertEqual(led[0]["status"], "lost")
        self.assertAlmostEqual(led[0]["profit"], -1.0)

    def test_ignores_unknown_and_malformed(self):
        led = [_p("779", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        led[0].update({"status": "lost", "ftScore": [0, 0], "via": "track"})
        E.apply_manual_results(led, {"999": {"ft": [3, 0]}}, NOW)          # andere matchId
        E.apply_manual_results(led, {"779": {"ft": "2:0"}}, NOW)           # kaputtes ft
        self.assertEqual(led[0]["status"], "lost")

    def test_empty_manual_is_noop(self):
        led = [_p("780", "Match Odds", "TeamH", 1.8, home="TeamH", away="TeamA")]
        led[0].update({"status": "lost", "ftScore": [0, 0]})
        E.apply_manual_results(led, {}, NOW)
        self.assertEqual(led[0]["status"], "lost")


if __name__ == "__main__":
    unittest.main()


class TestUntergrenzenUndVerfallene(unittest.TestCase):
    """🔴 08.09.2026 — das GRÖSSTE Push-Buch im Repo (n=190) war das einzige ohne Untergrenze.
    „58 % Treffer" und „ROI −2,6 %" standen als nackte Punktschätzer da; die 17 Zeilen, die NIE
    ein Ergebnis bekamen, fielen still aus dem Nenner und das Board zeigte nur „offen: 2"."""

    def _led(self, n_won, n_lost, odd=2.0, expired=0, void=0):
        led = []
        for i in range(n_won):
            led.append({"k": "w%d" % i, "status": "won", "profit": odd - 1.0,
                        "leadOdd": odd, "scenario": "fresh", "market": "Match Odds"})
        for i in range(n_lost):
            led.append({"k": "l%d" % i, "status": "lost", "profit": -1.0,
                        "leadOdd": odd, "scenario": "fresh", "market": "Match Odds"})
        for i in range(expired):
            led.append({"k": "e%d" % i, "status": "expired", "scenario": "fresh"})
        for i in range(void):
            led.append({"k": "v%d" % i, "status": "void", "scenario": "fresh"})
        return led

    def test_untergrenzen_stehen_im_artefakt(self):
        r = E.summarize(self._led(60, 40), now=NOW)
        self.assertEqual(r["n"], 100)
        self.assertIsNotNone(r["hitUg"])
        self.assertIsNotNone(r["roiUg"])
        self.assertLess(r["hitUg"], r["hitRate"], "die UG muss unter dem Punktschaetzer liegen")
        self.assertLess(r["roiUg"], r["roi"])

    def test_belegt_haengt_an_der_untergrenze_nicht_am_punkt(self):
        # +20 % ROI aus 100 Plays bei Quote 2.0 -> UG ueber null -> belegt.
        gut = E.summarize(self._led(60, 40), now=NOW)
        self.assertGreater(gut["roi"], 0)
        self.assertTrue(gut["belegt"])
        # knapp positiver Punktschaetzer, aber UG unter null -> NICHT belegt.
        knapp = E.summarize(self._led(51, 49), now=NOW)
        self.assertGreater(knapp["roi"], 0)
        self.assertLess(knapp["roiUg"], 0)
        self.assertFalse(knapp["belegt"])

    def test_kleine_stichprobe_bekommt_keine_erfundene_untergrenze(self):
        # n<30: `freigabe.untergrenze` liefert None — eine „UG" aus 10 Plays waere schlimmer
        # als gar keine (Vorfall vom 03.09.).
        r = E.summarize(self._led(7, 3), now=NOW)
        self.assertIsNone(r["roiUg"])
        self.assertFalse(r["belegt"])

    def test_verfallene_werden_gezaehlt_statt_zu_verschwinden(self):
        r = E.summarize(self._led(60, 40, expired=17, void=1), now=NOW)
        self.assertEqual(r["n"], 100, "verfallene duerfen nicht in den Nenner")
        self.assertEqual(r["verfallen"], 17)
        self.assertEqual(r["ungueltig"], 1)

    def test_szenarien_tragen_ihre_untergrenze_mit(self):
        r = E.summarize(self._led(60, 40), now=NOW)
        self.assertIn("roiUg", r["byScenario"]["fresh"])
        self.assertIn("hitUg", r["byScenario"]["fresh"])


class EntschiedenBeimSenden(unittest.TestCase):
    """🔴 15.09.2026 (Lucas: „den public push mit den over 0.5 muessen wir aber entfernen aus
    allen stats oder"). Ja — aber als VOID mit Grund, nicht als Loeschung.

    Der Fall: „First Half Goals 0.5 · Over 0.5 @1.51", gesendet bei Stand 0:1 in Minute 13.
    Der Ausgang stand fest. Als Treffer gezaehlt haette er die Quote mit einer SICHERHEIT
    aufgeblasen — und ein geschoenter Track Record ist schlimmer als ein schlechter."""

    def _e(self, market="First Half Goals 0.5", lead="Over 0.5 Goals",
           score=None, minute=13, **kw):
        e = {"k": "fresh:1:%s" % market, "matchId": "1", "market": market, "leadName": lead,
             "leadOdd": 1.51, "home": "Sporting U23", "away": "Viseu U23",
             "sentAt": "2026-09-15T14:16:26+00:00", "status": "pending",
             "live": {"time": minute, "score": [0, 1] if score is None else score}}
        e.update(kw)
        return e

    def test_der_echte_fall_wird_erkannt(self):
        self.assertTrue(E.entschieden_beim_senden(self._e()))

    def test_dieselbe_partie_mit_hoeherer_linie_bleibt_gueltig(self):
        # Over 1.5 bei 0:1 lebt — genau die Karte, die im Trades-Channel RICHTIG war.
        self.assertFalse(E.entschieden_beim_senden(
            self._e(market="First Half Goals 1.5", lead="Over 1.5 Goals")))

    def test_der_halbzeitstand_aus_der_abrechnung_zaehlt_NICHT(self):
        # 🔴 Die wichtigste Schranke. `htScore` ist der Stand bei HALBZEIT, aus der Abrechnung —
        # er sagt nichts darueber, was beim SENDEN bekannt war. Wer ihn hier benutzt, erklaert
        # nachtraeglich Zeilen fuer ungueltig, die damals offen waren. In meinem ersten Anlauf
        # fielen dadurch 14 statt 2 Zeilen — zwoelf davon zu Unrecht.
        e = self._e()
        e.pop("live")
        e["htScore"] = [0, 1]
        self.assertFalse(E.entschieden_beim_senden(e))

    def test_ohne_stand_wird_nicht_geraten(self):
        for e in ({}, self._e(score="kaputt"), self._e(score=[]), None, "x"):
            self.assertFalse(E.entschieden_beim_senden(e))

    def test_void_statt_loeschen_mit_grund(self):
        led = [self._e(), self._e(market="First Half Goals 1.5", lead="Over 1.5 Goals")]
        n = E.void_entschiedene(led)
        self.assertEqual(n, 1)
        self.assertEqual(len(led), 2, "die Zeile wurde geloescht statt entwertet")
        self.assertEqual(led[0]["status"], "void")
        self.assertEqual(led[0]["profit"], 0.0)
        self.assertEqual(led[0]["voidGrund"], E.VOID_ENTSCHIEDEN)
        self.assertEqual(led[1]["status"], "pending")

    def test_wirkt_auch_rueckwirkend_auf_gewonnene_zeilen(self):
        # Der 11.09.-Fall stand auf „won" und blies die Trefferquote auf.
        led = [self._e(market="First Half Goals 1.5", lead="Over 1.5 Goals",
                       score=[3, 1], minute=45, status="won", profit=0.74)]
        E.void_entschiedene(led)
        self.assertEqual(led[0]["status"], "void")
        self.assertEqual(led[0]["profit"], 0.0)

    def test_ist_idempotent(self):
        led = [self._e()]
        self.assertEqual(E.void_entschiedene(led), 1)
        self.assertEqual(E.void_entschiedene(led), 0, "zaehlt bei jedem Lauf erneut")

    def test_die_zeile_faellt_aus_zaehler_UND_nenner(self):
        led = [self._e(status="won", profit=0.51),
               self._e(market="Match Odds", lead="Sporting U23", score=[0, 1],
                       status="won", profit=1.0),
               self._e(market="Match Odds", lead="Viseu U23", score=[0, 1],
                       status="lost", profit=-1.0)]
        vor = E.summarize([dict(x) for x in led])
        E.void_entschiedene(led)
        nach = E.summarize(led)
        self.assertEqual(nach["n"], vor["n"] - 1)
        self.assertEqual(nach["wins"], vor["wins"] - 1)
        self.assertEqual(nach.get("ungueltig", 0), vor.get("ungueltig", 0) + 1)

    def test_die_abrechnung_selbst_entwertet_direkt(self):
        from datetime import datetime, timezone
        e = self._e()
        E._grade_ledger_entry(e, [2, 1], [0, 1], datetime(2026, 9, 15, 20, tzinfo=timezone.utc))
        self.assertEqual(e["status"], "void")
        self.assertEqual(e["voidGrund"], E.VOID_ENTSCHIEDEN)

    def test_die_linien_regel_steht_nur_an_einer_stelle(self):
        from pathlib import Path
        q = (Path(__file__).parent.parent / "betfair_public_eval.py").read_text(encoding="utf-8")
        self.assertIn("from betfair_alerts import ausgang_schon_entschieden", q)

    def test_der_lauf_ruft_es_auch_auf(self):
        """19.09.2026: hier stand ein Text-Griff auf „_nv = void_entschiedene(ledger)" in main().
        Die Kette ist seither in `abrechnen()` gebuendelt, damit das Schattenbuch der
        Beinahe-Treffer nicht seine eigene Reihenfolge bekommt — der Text-Griff waere daran
        zerbrochen, ohne dass die Regel weg war. Also pruefen wir jetzt die WIRKUNG."""
        buch, nvoid = E.abrechnen([self._e()], {}, [], manual={})
        self.assertEqual(nvoid, 1)
        self.assertEqual(buch[0]["status"], "void")
        self.assertEqual(buch[0]["voidGrund"], E.VOID_ENTSCHIEDEN)

    def test_und_der_lauf_faehrt_wirklich_diese_kette(self):
        from pathlib import Path
        q = (Path(__file__).parent.parent / "betfair_public_eval.py").read_text(encoding="utf-8")
        self.assertIn("ledger, _nv = abrechnen(ledger, prices, track_results)", q)
        self.assertIn("abrechnen(schatten, prices, track_results", q)


class DasKursrutschBuchWirdAbgerechnet(unittest.TestCase):
    """🔴 19.09.2026, am selben Abend nachgetragen. Der Kursrutsch-Alarm schrieb sein Buch —
    und niemand rechnete es ab. `zaehler_bf_rutsch` haette bis in alle Ewigkeit 0 gemeldet und
    die vorregistrierte Messung `betfair-kursrutsch` waere nie faellig geworden.

    Ein Buch ohne Abrechnung ist eine Behauptung. Genau dafuer steht
    `check_schattenbuch_fuellt_sich` in der Guard-Batterie — und genau daran habe ich beim Bau
    des Alarms nicht gedacht."""

    def test_der_lauf_faehrt_dieselbe_kette_auch_fuers_rutsch_buch(self):
        from pathlib import Path
        q = (Path(__file__).parent.parent / "betfair_public_eval.py").read_text(encoding="utf-8")
        self.assertIn("abrechnen(rutsch, prices, track_results", q)
        self.assertIn("RUTSCH_FILE", q)

    def test_eine_rutsch_zeile_laeuft_durch_die_kette(self):
        """Die Zeile hat die Form einer Public-Zeile — sonst greift settle() sie gar nicht an."""
        e = {"k": "rutsch:1:Match Odds", "matchId": "1", "scenario": "rutsch",
             "market": "Match Odds", "leadName": "Alpha", "leadOdd": 1.45, "entryOdd": 1.79,
             "home": "Alpha", "away": "Beta", "sentAt": "2026-09-19T17:00:00+00:00",
             "status": "pending", "live": {"time": None, "score": [None, None]}}
        buch, _ = E.abrechnen([e], {}, [], manual={})
        self.assertEqual(len(buch), 1)
        self.assertIn(buch[0]["status"], ("pending", "won", "lost", "void"))

    def test_live_gesendete_zeilen_werden_bei_jedem_lauf_aus_der_bilanz_genommen(self):
        """Die sechs Alarme des ersten Abends kamen ALLE aus laufenden Spielen (22., 63., 44.,
        40., 38., 45. Minute) — eine Population, die nie gemessen wurde.

        🔴 Und das ist eine REGEL, keine Handkorrektur: ich hatte die Zeilen einmal von Hand auf
        void gesetzt, und der naechste Pipeline-Lauf hat die Datei neu geschrieben — die
        Markierung war weg und drei neue Live-Zeilen standen daneben. Die Datei gehoert der
        Pipeline; was gelten soll, muss im Code stehen."""
        e = lambda t: {"k": "rutsch:1:X", "matchId": "1", "status": "pending",
                       "live": {"time": t, "score": [None, None]}}
        buch = [e(44), e(None), e(3)]
        self.assertEqual(E.void_live_rutsch(buch), 2)
        self.assertEqual([x["status"] for x in buch], ["void", "pending", "void"])
        self.assertTrue(all(x.get("voidGrund") for x in buch if x["status"] == "void"),
                        "void ohne Grund ist eine Loeschung")
        self.assertEqual(E.void_live_rutsch(buch), 0, "nicht idempotent")

    def test_der_lauf_wendet_die_regel_auch_an(self):
        from pathlib import Path
        q = (Path(__file__).parent.parent / "betfair_public_eval.py").read_text(encoding="utf-8")
        self.assertIn("void_live_rutsch(rutsch)", q)

    def test_die_regel_raeumt_auch_das_echte_buch(self):
        """Gegen die echten Zeilen — aber ueber die REGEL, nicht ueber den Dateizustand.

        19.09.2026: die erste Fassung las den Status direkt aus der Datei und fiel, sobald die
        Pipeline die Live-Zeilen vor dem Rollout als `won` abgerechnet hatte. Ein Test, der
        davon abhaengt, WANN der letzte Lauf war, misst den Lauf und nicht die Regel — dieselbe
        Falle wie heute Abend bei `alter_tage` und der mtime."""
        import json
        from pathlib import Path
        p = Path(__file__).parent.parent / "betfair_rutsch_ledger.json"
        if not p.exists():
            self.skipTest("noch kein Rutsch-Buch")
        buch = json.loads(p.read_text(encoding="utf-8"))
        live = [r for r in buch if (r.get("live") or {}).get("time") is not None]
        if not live:
            self.skipTest("keine Live-Zeilen im Buch")
        E.void_live_rutsch(buch)
        for r in live:
            self.assertEqual(r.get("status"), "void",
                             "die Regel laesst eine live gesendete Zeile in der Bilanz")


class VoidOhneGrundIstKeinUrteil(unittest.TestCase):
    """🔴 20.09.2026 (Lucas: „Beide Spiele stehen nicht in der Betfair-Public-Bilanz. Beide
    haben gewonnen.").

    Vasco da Gama gewann 5:0, gewettet zu 1.37 — die Zeile stand auf `void`, weil `fav_token`
    den Runner „Vasco Da Gama" nicht auf das Heimteam „Vasco da Gama" abbilden konnte (ein
    grosses D). Dasselbe traf Bochum v VfL Osnabruck („VFL" statt „VfL"), das ebenfalls
    gewonnen hatte.

    Der Zeichenvergleich ist seit heute normalisiert — aber die zwei Zeilen waeren trotzdem fuer
    immer void geblieben: `_grade_ledger_entry` setzt void ohne Grund, und void ist sonst
    endgueltig. Ein „nicht abrechenbar" ist kein Urteil ueber die Wette, sondern eins ueber uns,
    und gehoert wiederholt, sobald wir es besser koennen.
    """

    def test_void_ohne_grund_wird_neu_versucht(self):
        buch = [{"k": "a", "status": "void", "settledAt": "2026-09-20T02:00:00+00:00"},
                {"k": "b", "status": "void", "voidGrund": E.VOID_ENTSCHIEDEN},
                {"k": "c", "status": "won"},
                {"k": "d", "status": "pending"}]
        self.assertEqual(E.nachgrade_ungeklaerte(buch), 1)
        self.assertEqual([x["status"] for x in buch], ["pending", "void", "won", "pending"])
        self.assertNotIn("settledAt", buch[0], "ein neuer Versuch braucht auch ein neues Datum")

    def test_ein_void_MIT_grund_bleibt_stehen(self):
        """VOID_ENTSCHIEDEN und die Kursrutsch-Live-Regel sind Entscheidungen, keine Pannen."""
        buch = [{"k": "b", "status": "void", "voidGrund": E.RUTSCH_VOID_LIVE}]
        self.assertEqual(E.nachgrade_ungeklaerte(buch), 0)
        self.assertEqual(buch[0]["status"], "void")

    def test_idempotent(self):
        buch = [{"k": "a", "status": "void"}]
        E.nachgrade_ungeklaerte(buch)
        self.assertEqual(E.nachgrade_ungeklaerte(buch), 0)

    def test_die_kette_versucht_es_auch(self):
        """Behavioural, nicht per Textgriff: die erste Fassung suchte den Funktionsnamen im
        Quelltext und fand die DEFINITION — die Mutation „Aufruf entfernt" rutschte durch."""
        e = {"k": "fresh:1:Match Odds", "matchId": "1", "market": "Match Odds",
             "leadName": "VFL Osnabruck", "home": "Bochum", "away": "VfL Osnabruck",
             "leadOdd": 1.85, "sentAt": "2026-08-28T17:15:00+00:00", "status": "void"}
        spur = [{"matchId": "1", "market": "Match Odds", "ft": [0, 1], "ht": None,
                 "settledAt": "2026-08-28T21:00:00+00:00"}]
        buch, _ = E.abrechnen([e], {}, spur, manual={})
        self.assertEqual(buch[0]["status"], "won",
                         "die Kette holt eine unabgerechnete Zeile nicht nach")

    def test_der_echte_fall_rechnet_sich_jetzt_ab(self):
        """Bochum v VfL Osnabruck: gewonnen zu 1.85, stand als void in der Bilanz."""
        e = {"k": "fresh:1:Match Odds", "matchId": "1", "market": "Match Odds",
             "leadName": "VFL Osnabruck", "home": "Bochum", "away": "VfL Osnabruck",
             "leadOdd": 1.85, "sentAt": "2026-08-28T17:15:00+00:00", "status": "void"}
        self.assertEqual(E.nachgrade_ungeklaerte([e]), 1)
        from datetime import datetime, timezone
        E._grade_ledger_entry(e, [0, 1], None, datetime(2026, 8, 28, 21, tzinfo=timezone.utc))
        self.assertEqual(e["status"], "won")
        self.assertAlmostEqual(e["profit"], 0.85, places=2)


class DerBelegEinesPushsWirdSofortGesichert(unittest.TestCase):
    """🔴 20.09.2026. Lyon v Rennes WAR gesendet — betfair_public_seen.json trug den Schluessel
    `fresh:36039873`, den es nur bei erfolgreichem Versand bekommt. Im Ledger stand keine Zeile,
    und in keinem der letzten 40 Commits hat sie je gestanden. Ueber alle Eintraege geprueft:
    4 von 277 gesendeten Public-Pushes haben keine Ledger-Zeile (1,4 %).

    Der Grund liegt im Ablauf: der Lauf sendet und committet erst zwoelf Schritte spaeter, nach
    einem Schritt, der ~12 Minuten schlaeft — bei einem Takt von 15 Minuten. Dieselbe Klasse wie
    am 19.09. beim doppelten Poly-Play: **wer handelt, schreibt sofort.**"""

    def test_die_betfair_pipeline_sichert_direkt_nach_dem_senden(self):
        import os
        from pathlib import Path
        y = (Path(__file__).parent.parent / ".github/workflows/betfair.yml").read_text(encoding="utf-8")
        self.assertIn('ci_sichern.sh "Beleg der Betfair-Pushes"', y)
        i_send = y.index("betfair_alerts.py")
        i_sich = y.index('ci_sichern.sh "Beleg der Betfair-Pushes"')
        i_eval = y.index("betfair_public_eval.py")
        self.assertLess(i_send, i_sich, "gesichert wird NACH dem Senden")
        self.assertLess(i_sich, i_eval, "und VOR allem, was danach noch schiefgehen kann")
        for f in ("betfair_public_ledger.json", "betfair_public_seen.json"):
            self.assertIn(f, y[i_sich:i_sich + 500], "%s wird nicht sofort gesichert" % f)
