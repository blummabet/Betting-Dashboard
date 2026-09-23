"""🔴 20.09.2026 — eine Narbe und eine frische Wunde in derselben Zahl.

Vier von 277 gesendeten Public-Pushes haben keine Ledger-Zeile (Lucas: „Beide Spiele stehen
nicht in der Betfair-Public-Bilanz. Beide haben gewonnen."). Lyon v Rennes war nachweislich
gesendet — `betfair_public_seen.json` trug `fresh:36039873`, und den Schlüssel bekommt ein
Spiel nur bei erfolgreichem Versand.

Der Roll-over-Verdacht ist widerlegt: das Ledger hält 282 von erlaubten 800 Zeilen, und alle
vier fehlenden matchIds liegen INNERHALB seines Bereichs (35.667.446 … 36.077.729). Sie sind
nicht herausgerollt, sie wurden nie geschrieben.

Die Ursache ist die Reihenfolge im Workflow: gesendet wird in Schritt N, committet zwölf
Schritte später — nach einem Schritt, der zwölf Minuten schläft, bei einem 15-Minuten-Takt.
Behoben durch `scripts/ci_sichern.sh` direkt nach dem Senden.

Nur: ob die Reparatur HÄLT, stand in derselben Zahl wie die alte Narbe. 4 würde bei einem
fünften Verlust zu 5, und das sieht in einer Warn-Zeile niemand. Deshalb stempelt der
Dedup-Stand ab jetzt die Sendezeit — jeder DATIERTE Verlust ist einer von nach der Reparatur.
Kein gepflegter Ausnahmen-Katalog, den in drei Wochen niemand mehr anfasst.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import betfair_public_eval as E
import uebersicht_integrity as U


def _seen(**kw):
    return kw


def _nach_der_reparatur(tage=1):
    """Ein Zeitstempel sicher NACH der letzten Reparatur — aus der Grenze selbst gerechnet.

    23.09.2026: hier stand ein festes Datum. Ein Test, dessen Ergebnis davon abhaengt, wo die
    Grenze gerade steht, wird beim naechsten Eintrag in REPARATUREN rot, ohne dass etwas kaputt
    ist — und wer ihn dann „repariert", verschiebt das Datum wieder um ein Stueck.
    """
    from datetime import datetime, timedelta
    t = datetime.fromisoformat(E.letzte_reparatur())
    return (t + timedelta(days=tage)).isoformat()


class TestDerZeitstempelTrenntNarbeUndWunde(unittest.TestCase):
    LEDGER = [{"scenario": "fresh", "matchId": "100"}]

    def test_ein_undatierter_verlust_ist_die_alte_narbe(self):
        s = {"fresh:200": {"v": 1, "n": 1}}
        self.assertEqual(E.gesendet_ohne_beleg(s, self.LEDGER), ["fresh:200"])
        self.assertEqual(E.gesendet_ohne_beleg_datiert(s, self.LEDGER), [])

    def test_ein_datierter_verlust_ist_ein_neuer(self):
        # 23.09.2026: die Grenze ist nicht mehr „traegt einen Zeitstempel", sondern „nach der
        # LETZTEN Reparatur" (s. tests/test_beleg_reparatur_grenze.py). Der Stempel wandert
        # deshalb hinter E.letzte_reparatur() statt auf ein festes Datum.
        s = {"fresh:200": {"v": 1, "n": 1, "t": _nach_der_reparatur(1)}}
        d = E.gesendet_ohne_beleg_datiert(s, self.LEDGER)
        self.assertEqual([z["key"] for z in d], ["fresh:200"])

    def test_ein_alter_float_eintrag_bleibt_lesbar(self):
        """Rückwärtskompatibel: der Dedup-Stand trägt seit jeher auch blanke Zahlen."""
        s = {"fresh:200": 34663.4}
        self.assertEqual(E.gesendet_ohne_beleg(s, self.LEDGER), ["fresh:200"])
        self.assertEqual(E.gesendet_ohne_beleg_datiert(s, self.LEDGER), [])

    def test_ein_push_mit_beleg_taucht_in_keiner_der_beiden_listen_auf(self):
        s = {"fresh:100": {"v": 1, "n": 1, "t": "2026-09-21T10:00:00+00:00"}}
        self.assertEqual(E.gesendet_ohne_beleg(s, self.LEDGER), [])
        self.assertEqual(E.gesendet_ohne_beleg_datiert(s, self.LEDGER), [])

    def test_die_neuesten_zuerst(self):
        s = {"fresh:200": {"t": _nach_der_reparatur(1)},
             "fresh:201": {"t": _nach_der_reparatur(2)}}
        self.assertEqual([z["key"] for z in E.gesendet_ohne_beleg_datiert(s, self.LEDGER)],
                         ["fresh:201", "fresh:200"])


class TestDerDedupStandStempelt(unittest.TestCase):
    def test_ein_neuer_eintrag_traegt_die_zeit(self):
        import betfair_alerts as A
        seen = {}
        A._pub_seen_put(seen, "fresh:1", 1000.0)
        self.assertIn("t", seen["fresh:1"])
        self.assertEqual(seen["fresh:1"]["n"], 1)

    def test_der_zaehler_laeuft_weiter_und_der_stempel_wird_frisch(self):
        import betfair_alerts as A
        seen = {"fresh:1": {"v": 500.0, "n": 2, "t": "2026-01-01T00:00:00+00:00"}}
        A._pub_seen_put(seen, "fresh:1", 1000.0)
        self.assertEqual(seen["fresh:1"]["n"], 3)
        self.assertGreater(seen["fresh:1"]["t"], "2026-01-01T00:00:00+00:00")

    def test_der_alte_float_stand_wird_nicht_verschluckt(self):
        import betfair_alerts as A
        seen = {"fresh:1": 500.0}
        A._pub_seen_put(seen, "fresh:1", 1000.0)
        self.assertEqual(seen["fresh:1"]["n"], 2, "ein float zaehlte immer als ein Push")


class TestDerGuardMeldetBeidesGetrennt(unittest.TestCase):
    def _ctx(self, n, neu, keys=(), neu_keys=()):
        return {"bfPublicRecord": {"gesendetOhneBeleg": n, "gesendetOhneBelegNeu": neu,
                                   "gesendetOhneBelegKeys": list(keys),
                                   "gesendetOhneBelegNeuKeys": list(neu_keys)}}

    def test_nur_die_alte_narbe_meldet_als_nicht_nachtragbar(self):
        c = U.check_jeder_push_hat_seinen_beleg(self._ctx(4, 0, ["fresh:36039873"]))
        text = " ".join(c["failures"])
        self.assertIn("vor der Sofort-", text)
        self.assertIn("Auswahl nach Ausgang", text)
        self.assertNotIn("greift nicht", text)

    def test_ein_neuer_verlust_sagt_dass_die_reparatur_nicht_greift(self):
        c = U.check_jeder_push_hat_seinen_beleg(
            self._ctx(5, 1, ["fresh:1"], [{"key": "fresh:9", "t": "2026-09-30T10:00:00+00:00"}]))
        text = " ".join(c["failures"])
        # 23.09.2026: „der Sicherungsschritt greift nicht" hiess der Satz, als es nur EINE
        # Reparatur gab. Inzwischen sind es zwei mit verschiedenen Ursachen — die Meldung nennt
        # jetzt den Pfad, nicht den einen Schritt.
        self.assertIn("leckt weiter", text)
        self.assertIn("fresh:9", text)
        self.assertEqual(c["nFail"], 2, "alte Narbe und neuer Verlust sind zwei Meldungen")

    def test_ohne_luecke_bleibt_er_still(self):
        self.assertEqual(U.check_jeder_push_hat_seinen_beleg(self._ctx(0, 0))["nFail"], 0)

    def test_ohne_bericht_urteilt_er_nicht(self):
        self.assertEqual(U.check_jeder_push_hat_seinen_beleg({})["nFail"], 0)


class TestDerBelegWirdSofortGesichert(unittest.TestCase):
    """Die Ursache selbst: gesendet in Schritt N, committet zwölf Schritte später."""

    def test_betfair_sichert_direkt_nach_dem_senden(self):
        t = (Path(__file__).resolve().parents[1]
             / ".github/workflows/betfair.yml").read_text(encoding="utf-8")
        # Auf den AUFRUF suchen, nicht auf den Namen: der Skriptname steht auch im Kommentar
        # darueber, und ein Test, der den Kommentar findet, misst den Abstand nicht mehr.
        i = t.index("run: ${{ env.BETFAIR_PY }} betfair_alerts.py")
        j = t.index("run: bash scripts/ci_sichern.sh", i)
        zwischen = t[i:j]
        self.assertLess(zwischen.count("- name:"), 2,
                        "zwischen Senden und Sichern darf kaum ein Schritt liegen — der Vorfall "
                        "entstand aus zwoelf Schritten und einem 12-Minuten-Schlaf dazwischen")
        self.assertNotIn("sleep", zwischen)
        self.assertIn("betfair_public_ledger.json", t[j:j + 400])
        self.assertIn("betfair_public_seen.json", t[j:j + 400])


if __name__ == "__main__":
    unittest.main()
