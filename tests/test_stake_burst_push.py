# -*- coding: utf-8 -*-
"""tests/test_stake_burst_push.py — 11.09.2026

Lucas schickte eine VIP-Gruppen-Nachricht: vier Wetten, EINE Auswahl, DIESELBE Quote (3,35),
innerhalb von 48 Sekunden, $17.605 zusammen. „Mir geht's bei Stake wirklich um die Geldeinsaetze,
die dort reinfliessen."

Diese Tests halten fest, was die Regel IST und was sie ausdruecklich NICHT ist:
  · nicht der Betrag — ab $50k dreht der gemessene ROI ins Minus, die Kante sitzt bei $10-20k
  · sondern die GLEICHE QUOTE: der Buchmacher hat auf das Geld nicht reagiert
  · und ein Deckel, weil Lucas „Angst hat, dass da zu viel kommt"
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import stake_burst_push as B  # noqa: E402

NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)


def bursts(feed, **kw):
    """`B.bursts` mit fester Uhr. Seit dem 12.09. hat die Erkennung eine Altersgrenze
    (MAX_ALTER_MIN) — ohne ein gesetztes `now` wuerde jeder Test hier gegen die echte Uhr laufen
    und ab morgen nur noch beweisen, dass alte Bursts nicht mehr gemeldet werden."""
    kw.setdefault("now", NOW)
    return B.bursts(feed, **kw)


def w(sek=0, usd=3000, quote=3.35, auswahl="a1", phase="vor", **over):
    d = {"id": "b%s-%s" % (auswahl, sek), "auswahlId": auswahl, "einsatzUsd": usd,
         "beinQuote": quote, "quote": quote, "kombi": False, "phase": phase,
         "ts": (NOW + timedelta(seconds=sek)).isoformat(),
         "event": "Cienciano - Montevideo City Torque", "eventId": "e1",
         "liga": "CONMEBOL Sudamericana", "kat": "Fußball",
         "markt": "Player to be carded (sure sub)", "auswahl": "Cabello, Carlos",
         "kat": "Fußball"}
    d.update(over)
    return d


class TestLucasBeispiel(unittest.TestCase):
    """Die Nachricht, die den Auftrag ausgeloest hat — Zeile fuer Zeile nachgebaut."""

    def _feed(self):
        return [w(0, 1041.29), w(30, 11580.35), w(45, 1994.0), w(48, 2990.0)]

    def test_das_beispiel_wird_erkannt(self):
        b = bursts(self._feed())
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]["wetten"]), 4)
        self.assertAlmostEqual(b[0]["summe"], 17605.64, places=2)
        self.assertAlmostEqual(b[0]["sekunden"], 48.0, places=1)

    def test_die_karte_nennt_das_wesentliche(self):
        k = B.build_burst_card(bursts(self._feed())[0])
        self.assertIn("STAKE-BURST", k)
        self.assertIn("4 Wetten", k)
        self.assertIn("48 Sek", k)
        self.assertIn("Cabello", k)
        self.assertIn("3.35", k)
        self.assertIn("$17.6K", k)

    def test_die_karte_sagt_dass_sie_kein_beleg_ist(self):
        """Bei n=221 gehoert das auf die Karte, nicht in eine Fussnote. Eine Karte, die aussieht
        wie eine Empfehlung, wird als eine gelesen."""
        k = B.build_burst_card(bursts(self._feed())[0])
        self.assertIn("Beobachtungsband", k)
        self.assertIn("kein Beleg", k)


class TestDieRegel(unittest.TestCase):

    def test_verschiedene_quoten_sind_kein_burst(self):
        """🔴 Der wichtigste Test. Die gleiche Quote IST die Regel — ohne sie faellt die Messung
        von +29 % ROI (UG +19 %) auf +10 % (UG +3 %) und die Frequenz steigt von 5,8 auf 16,5
        Pushs am Tag. Wer diese Zeile entfernt, dreht beides zugleich ins Schlechtere."""
        feed = [w(0, 5000, 3.35), w(10, 5000, 3.30), w(20, 5000, 3.35), w(30, 5000, 3.35)]
        self.assertEqual(bursts(feed), [])

    def test_zu_wenige_wetten(self):
        self.assertEqual(bursts([w(0, 9000), w(10, 9000), w(20, 9000)], min_n=4), [])
        self.assertEqual(len(bursts([w(0, 9000), w(10, 9000), w(20, 9000)], min_n=3)), 1)

    def test_zu_weit_auseinander(self):
        feed = [w(0), w(100), w(200), w(400)]
        self.assertEqual(bursts(feed, fenster_s=300, min_n=4), [])
        self.assertEqual(len(bursts(feed, fenster_s=600, min_n=4)), 1)

    def test_zu_wenig_geld(self):
        feed = [w(i * 10, 2000) for i in range(4)]      # $8.000
        self.assertEqual(bursts(feed), [])
        self.assertEqual(len(bursts(feed, min_usd=8000)), 1)

    def test_der_betrag_ist_NICHT_der_hebel(self):
        """Festgehalten, weil es kontraintuitiv ist und beim naechsten Aufraeumen sonst
        „optimiert" wird: gemessen liegt der ROI im Band $10-20k bei +25,2 % (UG +11,7 %) und
        ab $50k bei −12,3 %. Die Schwelle steht deshalb NIEDRIG, und die Frequenz wird ueber
        die gleiche Quote und den Deckel geregelt, nicht ueber den Betrag."""
        self.assertLessEqual(B.MIN_USD, 20000,
                             "eine hohe Betragsschwelle schneidet die gemessene Kante weg")

    def test_kombiwetten_bleiben_draussen(self):
        """Ihr Einsatz haengt an mehreren Spielen und ist keinem davon zurechenbar — dieselbe
        Regel wie im Stake-Radar."""
        feed = [w(i * 10, 9000, kombi=True) for i in range(4)]
        self.assertEqual(bursts(feed), [])

    def test_verschiedene_auswahlen_sind_kein_burst(self):
        """Vier grosse Wetten auf vier verschiedene Dinge sind ein voller Kanal, kein Signal."""
        feed = [w(i * 10, 9000, auswahl="a%d" % i) for i in range(4)]
        self.assertEqual(bursts(feed), [])

    def test_je_auswahl_nur_ein_burst(self):
        """Eine lange Serie darf nicht als fuenf Ereignisse im Kanal landen."""
        feed = [w(i * 5, 3000) for i in range(12)]
        self.assertEqual(len(bursts(feed)), 1)

    def test_kaputte_zeilen_reissen_nichts_mit(self):
        feed = [w(0), w(10), w(20), w(30),
                {"auswahlId": "a1"}, {"auswahlId": "a1", "ts": "kaputt", "einsatzUsd": 5000},
                w(40, usd=0), w(50, quote=None), w(60, quote=1.0), None, "x"]
        b = bursts(feed)
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]["wetten"]), 4, "nur die vier brauchbaren Zeilen")

    def test_leerer_feed(self):
        for leer in ([], None, "kaputt"):
            self.assertEqual(bursts(leer), [])


class TestGesperrteSportarten(unittest.TestCase):
    """12.09.2026 (Lucas: „ok das waeren dann nur bursts zu Top Ligen oder").

    Beim Nachzaehlen aufgefallen: der Burst-Push war die EINZIGE Stake-Flaeche ohne Sperrliste.
    Der Sammler fuehrt sie seit dem 03.09. („Ganze US-Sport brauch ich aktuell mal nicht") und
    schreibt sie als `gesperrt` ins Artefakt; der Radar liest sie von dort, dieser Push nicht.

    Zur Frage selbst: 58 von 72 Bursts sind Fussball, davon Champions League 19, Serie A 6,
    Sueper Lig 5, La Liga 5, Brasileirao 4. Dazu Tennis 8, E-Sport 3, Cricket 2, US-Sport 1.
    Also ueberwiegend grosse Wettbewerbe — zwangslaeufig, weil $10.000 in fuenf Minuten nur dort
    zusammenkommen, wo Verkehr ist.
    """

    def test_gesperrte_kategorie_erzeugt_keinen_burst(self):
        feed = [w(i * 10, 5000, kat="US-Sport") for i in range(4)]
        self.assertEqual(bursts(feed, gesperrt=["US-Sport"]), [])

    def test_die_liste_kommt_aus_dem_artefakt(self):
        """Eine zweite Liste hier waere genau die Drift, die im Poly-Band einen Tag vorher
        aufgeraeumt wurde: aendert Lucas die Sperre im Sammler, muss dieser Push mitziehen."""
        self.assertEqual(B.gesperrte_kats({"gesperrt": ["Cricket", "Darts"]}),
                         ["Cricket", "Darts"])
        feed = [w(i * 10, 5000, kat="Cricket") for i in range(4)]
        self.assertEqual(bursts(feed, gesperrt=["Cricket"]), [])
        self.assertEqual(len(bursts(feed, gesperrt=["US-Sport"])), 1,
                         "steht Cricket nicht auf der Liste, laeuft es mit — die LISTE regiert")

    def test_ohne_artefakt_liste_gilt_der_sichere_rueckfall(self):
        for leer in (None, {}, {"gesperrt": None}, {"gesperrt": []}, "kaputt"):
            self.assertEqual(sorted(B.gesperrte_kats(leer)), ["Cricket", "US-Sport"], repr(leer))

    def test_fussball_und_tennis_laufen_weiter(self):
        """Die Gegenprobe — ohne sie koennte die Sperre alles fangen und der Test waere gruen."""
        for kat in ("Fußball", "Tennis", "E-Sport"):
            self.assertEqual(len(bursts([w(i * 10, 5000, kat=kat) for i in range(4)],
                                          gesperrt=["US-Sport"])), 1, kat)

    def test_main_liest_die_liste_aus_derselben_datei_wie_die_wetten(self):
        """Sonst faellt beim naechsten Umbau auf, dass die Liste aus einer anderen Quelle kommt
        als die Daten — und das merkt niemand, weil beide heute gleich aussehen."""
        import inspect
        q = inspect.getsource(B.main)
        self.assertIn("gesperrte_kats(quelle)", q)
        self.assertIn("gesperrt=_gesperrt", q)


class TestQuotenboden(unittest.TestCase):
    """🔴 12.09.2026 (Lucas: „wieso kommt da so eine odd?", zu @1,01 und @1,15).

    Der Push hatte KEINEN Quotenboden. Beim Poly-Band habe ich einen gebaut (1,35, auf Lucas'
    eigene Ansage) und hier nie einen gesetzt — dieselbe Luecke, dieselbe Woche.

    Gemessen an 72 Bursts: **19 liegen unter Quote 1,10**, sechs davon bei 1,01. Das ist kein
    Signal, das ist jemand, der auf ein entschiedenes Spiel 1 % abgreift. Der Boden macht das
    Band auf BEIDEN Achsen besser — weniger Laerm UND mehr Kante:

        ohne Boden   72 Bursts   ROI +29,1 %   UG +22,3 %
        ab 1,35      36 Bursts   ROI +45,9 %   UG +34,3 %
    """

    def test_die_1_01_karte_kommt_nicht_mehr(self):
        """Venezia-Fiorentina, $43,6K auf Fiorentina @1,01, live. Woertlich der gemeldete Fall."""
        feed = [w(i * 20, 5000, quote=1.01) for i in range(9)]
        self.assertEqual(bursts(feed), [])

    def test_auch_1_15_bleibt_draussen(self):
        """Real Madrid - Rayo, $39,5K @1,15 vor Anpfiff — der zweite gemeldete Fall."""
        self.assertEqual(bursts([w(i * 20, 10000, quote=1.15) for i in range(4)]), [])

    def test_genau_auf_der_schwelle_zaehlt(self):
        self.assertEqual(len(bursts([w(i * 20, 5000, quote=1.35) for i in range(4)])), 1)
        self.assertEqual(bursts([w(i * 20, 5000, quote=1.34) for i in range(4)]), [])

    def test_der_boden_ist_derselbe_wie_ueberall(self):
        """1,35 steht im Projekt schon dreimal (pick-engine, stake-radar, Poly-Dominanz). Eine
        vierte Zahl waere nur eine weitere, die man im Kopf behalten muss."""
        self.assertEqual(B.MIN_QUOTE, 1.35)

    def test_hohe_quoten_laufen_weiter(self):
        """Gegenprobe — ohne sie koennte der Boden alles fangen und der Test waere gruen."""
        for q in (1.4, 1.8, 3.35, 12.0):
            self.assertEqual(len(bursts([w(i * 20, 5000, quote=q) for i in range(4)])), 1, q)


class TestFrische(unittest.TestCase):
    """🔴 12.09.2026 (Lucas: „Wertlos war gestern schon. Wieso kommt das jetzt?").

    Der gemeldete Burst lag auf Venezia-Fiorentina am 11.09. um 20:29 — gepusht am 12.09.
    `stake_highroller.json` haelt ein 48-Stunden-Fenster, und die Erkennung hatte keine
    Altersgrenze: sie fand Bursts irgendwo im Fenster, auch zwoelf Stunden alte.

    Dieselbe Fehlerklasse wie beim Betfair-Halbzeit-Push einen Tag vorher („die Tore alle schon
    ewig her"): die Regel prueft den ZUSTAND, aber nicht, WANN er galt.
    """

    def test_frischer_burst_kommt(self):
        self.assertEqual(len(bursts([w(i * 20, 5000) for i in range(4)],
                                    now=NOW + timedelta(minutes=5))), 1)

    def test_burst_von_gestern_kommt_nicht(self):
        self.assertEqual(bursts([w(i * 20, 5000) for i in range(4)],
                                now=NOW + timedelta(hours=10)), [])

    def test_die_grenze_liegt_wo_sie_steht(self):
        # Die letzte Wette liegt bei NOW+60s — das Alter zaehlt ab IHR, nicht ab NOW.
        feed = [w(i * 20, 5000) for i in range(4)]
        self.assertEqual(len(bursts(feed, now=NOW + timedelta(minutes=29))), 1)
        self.assertEqual(len(bursts(feed, now=NOW + timedelta(minutes=31))), 1,
                         "31 Min nach NOW sind erst 30,0 Min nach der letzten Wette")
        self.assertEqual(bursts(feed, now=NOW + timedelta(minutes=32)), [])

    def test_gemessen_wird_ab_der_LETZTEN_wette(self):
        """Ein Burst, der vor 40 Minuten begann und vor 5 Minuten endete, ist frisch. Die erste
        Wette als Massstab zu nehmen wuerde lange Serien grundlos verwerfen."""
        # Erste Wette vor 40 Min, letzte vor knapp 5 Min. Gegen die ERSTE gerechnet waere das
        # 40 Minuten alt und flaege raus — gegen die letzte ist es frisch, und das ist richtig:
        # der Burst hat gerade eben geendet.
        feed = [w(-2400, 5000), w(-2380, 5000), w(-300, 5000), w(-280, 5000)]
        self.assertEqual(len(bursts(feed, fenster_s=3000, now=NOW)), 1,
                         "gemessen wird ab der letzten Wette")
        # Gegenprobe: derselbe Aufbau, nur endet er vor einer Stunde.
        alt = [w(-6000, 5000), w(-5980, 5000), w(-3900, 5000), w(-3880, 5000)]
        self.assertEqual(bursts(alt, fenster_s=3000, now=NOW), [])

    def test_ein_lauf_hat_EINE_uhr(self):
        """Beim Provozieren gruen gelaufen: `now` nicht durchzureichen aendert heute nichts, weil
        `bursts` sich dann selbst eine Uhr holt. Trotzdem falsch — derselbe Lauf entscheidet dann
        Frische, Dedup-Aufraeumen und Buch-Zeitstempel mit drei verschiedenen Zeitpunkten. Das
        faellt nie auf und macht jede spaetere Rekonstruktion ungenau."""
        import inspect
        q = inspect.getsource(B.main)
        i = q.index("alle = bursts(")
        self.assertIn("now=now", q[i:i + 160])
        self.assertLess(q.index("now = datetime.now"), i)

    def test_der_puffer_reicht_fuer_einen_verzoegerten_lauf(self):
        """Der Runner laeuft alle 10 Minuten. Eine Grenze unter 15 Minuten wuerde bei einem
        einzigen verpassten Lauf Bursts verschlucken."""
        self.assertGreaterEqual(B.MAX_ALTER_MIN, 15)


class TestDeckelUndDedup(unittest.TestCase):

    def test_der_deckel_ist_keine_rangfolge(self):
        """Lucas: „hab Angst dass da zu viel kommt." Der Deckel nimmt die AELTESTEN zuerst —
        jede Sortierung nach Guete waere eine Behauptung, die wir nicht belegen koennen (der
        gemessene ROI faellt mit der Summe, steigt also NICHT mit ihr)."""
        # 🔴 Der Aufbau ist der Test: der AELTERE Burst ist der KLEINERE. Vorher war er auch der
        # groessere — dann liefert eine Sortierung nach Summe dieselbe Reihenfolge, und der Test
        # war gruen, waehrend die Regel entfernt war (beim Provozieren aufgefallen).
        feed = ([w(i * 10, 30000, auswahl="spaet") for i in range(4)] +
                [w(-500 + i * 10, 3000, auswahl="frueh") for i in range(4)])
        b = bursts(feed)
        self.assertEqual([x["auswahlId"] for x in b], ["frueh", "spaet"],
                         "aeltester zuerst — auch wenn er der kleinere ist")

    def test_das_zeitfenster_bleibt_eng(self):
        """Gemessen wurde auf 5 Minuten. Ein weiteres Fenster misst etwas anderes — dann ist es
        keine Haeufung mehr, sondern nur noch „viel Geld auf eine Auswahl", und genau das trennt
        gemessen NICHT (Anteil am Spielgeld: kein Effekt ueber 15.646 Wetten)."""
        self.assertLessEqual(B.FENSTER_S, 600,
                             "ueber 10 Minuten ist es keine Haeufung mehr")
        feed = [w(0), w(600), w(1200), w(1800)]
        self.assertEqual(bursts(feed), [], "halbe Stunde ist kein Burst")

    def test_dedup_je_auswahl(self):
        self.assertEqual(B.burst_key({"auswahlId": "a1"}), "a1")

    def test_der_dedup_stand_vergisst_wieder(self):
        """Ohne Aufraeumen waechst die Datei ewig, und eine Auswahl, die in zwei Wochen wieder
        auftaucht, bliebe fuer immer gesperrt."""
        alt = {"a1": {"ts": (NOW - timedelta(hours=72)).isoformat()}}
        neu = {"a2": {"ts": (NOW - timedelta(hours=2)).isoformat()}}
        d = dict(alt); d.update(neu)
        self.assertEqual(set(B.prune_seen(d, now=NOW)), {"a2"})

    def test_kaputter_dedup_stand_sperrt_nicht_alles(self):
        self.assertEqual(B.prune_seen(None, now=NOW), {})
        self.assertEqual(B.prune_seen({"a": None, "b": {"ts": "kaputt"}}, now=NOW), {})


class TestBuch(unittest.TestCase):

    def test_die_phase_wird_getrennt_gebucht(self):
        """Live +29 % gegen vor Anpfiff +8,8 % — zusammengerechnet waere keine der beiden Zahlen
        spaeter zu beantworten. Dieselbe Lehre wie bei der Poly-Kleinmarkt-Spur."""
        live = bursts([w(i * 10, 5000, phase="live") for i in range(4)])[0]
        vor = bursts([w(i * 10, 5000, phase="vor") for i in range(4)])[0]
        self.assertEqual(B.buch_zeile(live, NOW.isoformat())["phase"], "live")
        self.assertEqual(B.buch_zeile(vor, NOW.isoformat())["phase"], "vor")

    def test_gemischte_phase_wird_als_solche_gebucht(self):
        """Nicht als „live" und nicht als „vor" — ein Burst ueber den Anpfiff hinweg ist ein
        drittes Ding, und es als eines der beiden zu buchen verfaelscht beide Zahlen."""
        feed = [w(0, 5000, phase="vor"), w(10, 5000, phase="vor"),
                w(20, 5000, phase="live"), w(30, 5000, phase="live")]
        self.assertEqual(B.buch_zeile(bursts(feed)[0], NOW.isoformat())["phase"], "gemischt")

    def test_die_buchzeile_traegt_alles_zum_nachrechnen(self):
        z = B.buch_zeile(bursts([w(i * 10, 5000) for i in range(4)])[0], NOW.isoformat())
        for feld in ("auswahlId", "eventId", "quote", "summeUsd", "nWetten", "sekunden",
                     "betIds", "sentAt", "status"):
            self.assertIn(feld, z, feld)
        self.assertEqual(len(z["betIds"]), 4, "ohne die Bet-IDs ist die Zeile nicht abrechenbar")
        self.assertEqual(z["status"], "pending")


class TestRollout(unittest.TestCase):
    """🔴 12.09.2026 (Lucas: „wie wissen wir ob die klappen? sollte da nicht zumindest 1 Spiel am
    Tag sowas haben :)").

    Antwort: ja — 8 bis 21 am Tag, gemessen ueber sechs Tage Ledger. Gekommen ist keiner, weil
    ich den Push in `stake-radar.yml` eingehaengt habe. **Dieser Workflow hat nur
    `workflow_dispatch`, keinen Schedule** — letzter Lauf 07.09., von Hand. Gesammelt wird Stake
    in `betfair.yml` (*/10), und dorthin gehoert ein Push, der auf einen frischen Feed reagiert.

    Exakt die Fehlerklasse, die in stake-radar.yml SELBST dokumentiert steht (07.09.:
    „Rollout-Luecke … der Code war da, der Produzent nicht neu gelaufen"). Ich habe den Kommentar
    gelesen und den Push trotzdem daneben gehaengt. Kein Test hat das gefangen, weil alle Tests
    die FUNKTION pruefen und keiner gefragt hat, ob sie jemals aufgerufen wird.
    """

    def _wf(self, name):
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / ".github" / "workflows" / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def test_der_push_haengt_in_einem_workflow_mit_schedule(self):
        """Die eigentliche Regel: ein Push ohne Schedule ist kein Push."""
        import re
        treffer = []
        for name in ("betfair.yml", "stake-radar.yml", "poly.yml", "cards.yml"):
            q = self._wf(name)
            if "stake_burst_push.py" in q:
                treffer.append((name, bool(re.search(r"^\s*schedule:", q, re.M))))
        self.assertTrue(treffer, "der Push ist in KEINEM Workflow eingehaengt")
        self.assertTrue(any(hat_schedule for _, hat_schedule in treffer),
                        "eingehaengt nur in Workflows ohne Schedule: %r" % (treffer,))

    def test_er_haengt_hinter_dem_sammler(self):
        """Vor dem Sammler haette er den Feed des letzten Laufs gesehen — also bis zu 10 Minuten
        alt, und das ist bei einem Muster aus 5-Minuten-Fenstern der Unterschied."""
        q = self._wf("betfair.yml")
        self.assertIn("stake_burst_push.py", q)
        self.assertLess(q.index("stake_highroller_fetch.py"), q.index("stake_burst_push.py"))

    def test_die_secrets_stehen_am_richtigen_schritt(self):
        """Ohne sie schreibt `send_trades_message` die Karte auf die Konsole, meldet False — und
        der Lauf bleibt gruen, waehrend nichts ankommt. Lautloses Scheitern."""
        q = self._wf("betfair.yml")
        i = q.index("stake_burst_push.py")
        block = q[max(0, i - 500):i]
        self.assertIn("TELEGRAM_TRADES_CHAT_ID", block)

    def test_sein_buch_wird_auch_committet(self):
        """Ein Buch, das der Runner schreibt und nicht committet, ist beim naechsten Lauf weg —
        genau der Fehler von „Heute spielenswert" (10.09., drei Tage TTL statt Ledger)."""
        q = self._wf("betfair.yml")
        self.assertIn("stake_burst_ledger.json", q)
        self.assertIn("stake_burst_seen.json", q)


if __name__ == "__main__":
    unittest.main()
