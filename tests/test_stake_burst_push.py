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


def w(sek=0, usd=3000, quote=3.35, auswahl="a1", phase="vor", **over):
    d = {"id": "b%s-%s" % (auswahl, sek), "auswahlId": auswahl, "einsatzUsd": usd,
         "beinQuote": quote, "quote": quote, "kombi": False, "phase": phase,
         "ts": (NOW + timedelta(seconds=sek)).isoformat(),
         "event": "Cienciano - Montevideo City Torque", "eventId": "e1",
         "liga": "CONMEBOL Sudamericana", "kat": "Fußball",
         "markt": "Player to be carded (sure sub)", "auswahl": "Cabello, Carlos"}
    d.update(over)
    return d


class TestLucasBeispiel(unittest.TestCase):
    """Die Nachricht, die den Auftrag ausgeloest hat — Zeile fuer Zeile nachgebaut."""

    def _feed(self):
        return [w(0, 1041.29), w(30, 11580.35), w(45, 1994.0), w(48, 2990.0)]

    def test_das_beispiel_wird_erkannt(self):
        b = B.bursts(self._feed())
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]["wetten"]), 4)
        self.assertAlmostEqual(b[0]["summe"], 17605.64, places=2)
        self.assertAlmostEqual(b[0]["sekunden"], 48.0, places=1)

    def test_die_karte_nennt_das_wesentliche(self):
        k = B.build_burst_card(B.bursts(self._feed())[0])
        self.assertIn("STAKE-BURST", k)
        self.assertIn("4 Wetten", k)
        self.assertIn("48 Sek", k)
        self.assertIn("Cabello", k)
        self.assertIn("3.35", k)
        self.assertIn("$17.6K", k)

    def test_die_karte_sagt_dass_sie_kein_beleg_ist(self):
        """Bei n=221 gehoert das auf die Karte, nicht in eine Fussnote. Eine Karte, die aussieht
        wie eine Empfehlung, wird als eine gelesen."""
        k = B.build_burst_card(B.bursts(self._feed())[0])
        self.assertIn("Beobachtungsband", k)
        self.assertIn("kein Beleg", k)


class TestDieRegel(unittest.TestCase):

    def test_verschiedene_quoten_sind_kein_burst(self):
        """🔴 Der wichtigste Test. Die gleiche Quote IST die Regel — ohne sie faellt die Messung
        von +29 % ROI (UG +19 %) auf +10 % (UG +3 %) und die Frequenz steigt von 5,8 auf 16,5
        Pushs am Tag. Wer diese Zeile entfernt, dreht beides zugleich ins Schlechtere."""
        feed = [w(0, 5000, 3.35), w(10, 5000, 3.30), w(20, 5000, 3.35), w(30, 5000, 3.35)]
        self.assertEqual(B.bursts(feed), [])

    def test_zu_wenige_wetten(self):
        self.assertEqual(B.bursts([w(0, 9000), w(10, 9000), w(20, 9000)], min_n=4), [])
        self.assertEqual(len(B.bursts([w(0, 9000), w(10, 9000), w(20, 9000)], min_n=3)), 1)

    def test_zu_weit_auseinander(self):
        feed = [w(0), w(100), w(200), w(400)]
        self.assertEqual(B.bursts(feed, fenster_s=300, min_n=4), [])
        self.assertEqual(len(B.bursts(feed, fenster_s=600, min_n=4)), 1)

    def test_zu_wenig_geld(self):
        feed = [w(i * 10, 2000) for i in range(4)]      # $8.000
        self.assertEqual(B.bursts(feed), [])
        self.assertEqual(len(B.bursts(feed, min_usd=8000)), 1)

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
        self.assertEqual(B.bursts(feed), [])

    def test_verschiedene_auswahlen_sind_kein_burst(self):
        """Vier grosse Wetten auf vier verschiedene Dinge sind ein voller Kanal, kein Signal."""
        feed = [w(i * 10, 9000, auswahl="a%d" % i) for i in range(4)]
        self.assertEqual(B.bursts(feed), [])

    def test_je_auswahl_nur_ein_burst(self):
        """Eine lange Serie darf nicht als fuenf Ereignisse im Kanal landen."""
        feed = [w(i * 5, 3000) for i in range(12)]
        self.assertEqual(len(B.bursts(feed)), 1)

    def test_kaputte_zeilen_reissen_nichts_mit(self):
        feed = [w(0), w(10), w(20), w(30),
                {"auswahlId": "a1"}, {"auswahlId": "a1", "ts": "kaputt", "einsatzUsd": 5000},
                w(40, usd=0), w(50, quote=None), w(60, quote=1.0), None, "x"]
        b = B.bursts(feed)
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]["wetten"]), 4, "nur die vier brauchbaren Zeilen")

    def test_leerer_feed(self):
        for leer in ([], None, "kaputt"):
            self.assertEqual(B.bursts(leer), [])


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
        b = B.bursts(feed)
        self.assertEqual([x["auswahlId"] for x in b], ["frueh", "spaet"],
                         "aeltester zuerst — auch wenn er der kleinere ist")

    def test_das_zeitfenster_bleibt_eng(self):
        """Gemessen wurde auf 5 Minuten. Ein weiteres Fenster misst etwas anderes — dann ist es
        keine Haeufung mehr, sondern nur noch „viel Geld auf eine Auswahl", und genau das trennt
        gemessen NICHT (Anteil am Spielgeld: kein Effekt ueber 15.646 Wetten)."""
        self.assertLessEqual(B.FENSTER_S, 600,
                             "ueber 10 Minuten ist es keine Haeufung mehr")
        feed = [w(0), w(600), w(1200), w(1800)]
        self.assertEqual(B.bursts(feed), [], "halbe Stunde ist kein Burst")

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
        live = B.bursts([w(i * 10, 5000, phase="live") for i in range(4)])[0]
        vor = B.bursts([w(i * 10, 5000, phase="vor") for i in range(4)])[0]
        self.assertEqual(B.buch_zeile(live, NOW.isoformat())["phase"], "live")
        self.assertEqual(B.buch_zeile(vor, NOW.isoformat())["phase"], "vor")

    def test_gemischte_phase_wird_als_solche_gebucht(self):
        """Nicht als „live" und nicht als „vor" — ein Burst ueber den Anpfiff hinweg ist ein
        drittes Ding, und es als eines der beiden zu buchen verfaelscht beide Zahlen."""
        feed = [w(0, 5000, phase="vor"), w(10, 5000, phase="vor"),
                w(20, 5000, phase="live"), w(30, 5000, phase="live")]
        self.assertEqual(B.buch_zeile(B.bursts(feed)[0], NOW.isoformat())["phase"], "gemischt")

    def test_die_buchzeile_traegt_alles_zum_nachrechnen(self):
        z = B.buch_zeile(B.bursts([w(i * 10, 5000) for i in range(4)])[0], NOW.isoformat())
        for feld in ("auswahlId", "eventId", "quote", "summeUsd", "nWetten", "sekunden",
                     "betIds", "sentAt", "status"):
            self.assertIn(feld, z, feld)
        self.assertEqual(len(z["betIds"]), 4, "ohne die Bet-IDs ist die Zeile nicht abrechenbar")
        self.assertEqual(z["status"], "pending")


if __name__ == "__main__":
    unittest.main()
