"""tests/test_pick_push_ledger.py — 30.08.2026

Das Schattenbuch ist die Gegenprobe zum Gegensignal-Filter: es schreibt auch die AUSSORTIERTEN
Picks mit und rechnet sie ab. Ohne das koennte der Schnitt sich nicht widerlegen lassen.

Der heikelste Punkt ist der Einfrier-Zeitpunkt. Gemessen ueber 14 Tage blieben 87% der Picks in
ihrem Signal-Zustand, 13% kippten noch (4 von sauber zu Gegensignal, 2 zurueck). Beim ersten
Sehen einzufrieren waere also falsch — und nach Anpfiff weiterzuschreiben erst recht, weil ein
Pick dann nachtraeglich in die gerade besser aussehende Schublade wandern koennte.
"""
import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _wm(ko_h=5, **pickkw):
    ko = (NOW + timedelta(hours=ko_h)).isoformat().replace("+00:00", "Z")
    p = {"verdict": "ABWÄGEN", "market": "Über 2.5 Tore", "odds": 1.9,
         "signalCountPos": 3, "signalCountNeg": 0}
    p.update(pickkw)
    return {"groups": {"A": {"teams": [{"id": "MEX", "name": "Mexiko"}, {"id": "ZAF", "name": "Südafrika"}],
                             "fixtures": [{"home": "MEX", "away": "ZAF", "matchday": 1, "kickoff": ko}]}},
            "koFixtures": [], "picks": {"A-1-MEX-ZAF": [p]}}


class Buch(unittest.TestCase):
    def setUp(self):
        os.environ["COCOBET_DATASET"] = "wm"
        import cocobet_dataset
        importlib.reload(cocobet_dataset)
        import pick_announce_state
        importlib.reload(pick_announce_state)
        import pick_push_ledger as L
        importlib.reload(L)
        self.L = L

    def test_beide_seiten_landen_im_buch(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertEqual(len(led), 1)
        self.assertTrue(led[0]["push"])
        led2 = self.L.erfassen([], _wm(signalCountNeg=2), "wm", NOW)
        self.assertEqual(len(led2), 1)
        self.assertFalse(led2[0]["push"], "die Aussortierten muessen mitgeschrieben werden")
        self.assertTrue(led2[0]["gegensignal"])

    def test_stand_wird_bis_zum_anpfiff_fortgeschrieben(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertTrue(led[0]["push"])
        # Ein Gegensignal taucht spaeter auf, das Spiel laeuft noch:
        led = self.L.erfassen(led, _wm(signalCountNeg=1), "wm", NOW + timedelta(hours=1))
        self.assertEqual(len(led), 1, "kein Duplikat")
        self.assertFalse(led[0]["push"], "der Stand muss dem folgen, was der Filter zuletzt sah")

    def test_nach_anpfiff_wird_eingefroren(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        # Spiel laeuft: iter_pick_units liefert nichts mehr -> Zeile bleibt stehen
        spaet = NOW + timedelta(hours=9)
        led2 = self.L.erfassen(led, _wm(signalCountNeg=5), "wm", spaet)
        self.assertEqual(len(led2), 1)
        self.assertTrue(led2[0]["push"], "nach Anpfiff darf sich der Stand nicht mehr drehen")

    def test_abgerechnete_zeile_wird_nie_wieder_angefasst(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW),
                               _wm(result="WIN"), "wm", NOW)
        self.assertEqual(led[0]["status"], "abgerechnet")
        self.assertTrue(led[0]["win"])
        led2 = self.L.erfassen(led, _wm(signalCountNeg=4), "wm", NOW)
        self.assertTrue(led2[0]["push"])
        self.assertEqual(led2[0]["sigNeg"], 0)

    def test_void_ist_kein_verlust(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW),
                               _wm(result="VOID"), "wm", NOW)
        self.assertEqual(led[0]["status"], "void")
        self.assertIsNone(led[0]["win"])
        self.assertEqual(self.L.schubladen(led), {}, "VOID darf in keiner Schublade landen")

    def test_offen_bleibt_offen(self):
        led = self.L.abrechnen(self.L.erfassen([], _wm(), "wm", NOW), _wm(), "wm", NOW)
        self.assertEqual(led[0]["status"], "offen")
        self.assertEqual(self.L.schubladen(led), {})

    def test_schubladen_trennen_gepusht_von_aussortiert(self):
        led = [
            {"k": "wm|a", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
             "push": True, "odds": 2.0, "win": True, "settledAt": "2026-08-29T10:00:00Z"},
            {"k": "wm|b", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
             "push": False, "odds": 2.0, "win": False, "settledAt": "2026-08-29T11:00:00Z"},
            {"k": "wm|c", "dataset": "wm", "verdict": "BET", "status": "abgerechnet",
             "push": True, "odds": 2.0, "win": True, "settledAt": "2026-08-29T12:00:00Z"},
        ]
        s = self.L.schubladen(led)
        self.assertEqual(set(s), {"ABWÄGEN · gepusht", "ABWÄGEN · aussortiert"},
                         "BET gehoert nicht in diese Frage — der Filter fasst ihn nicht an")
        self.assertEqual(s["ABWÄGEN · gepusht"]["renditen"], [1.0])
        self.assertEqual(s["ABWÄGEN · aussortiert"]["renditen"], [-1.0])

    # ── 14.09.2026: der Pick, den die Engine nachtraeglich zum Nicht-Pick erklaert ──────────
    def test_nachtraeglich_auf_NOBET_gestufter_pick_wird_trotzdem_abgerechnet(self):
        """🔴 Der echte Fall: 16 Liga-Zeilen hingen dauerhaft auf „offen", obwohl abgepfiffen.

        Rausgegangen als ABWÄGEN, spaeter von der Engine auf NOBET herabgestuft — und fuer NOBET
        schreibt der Resolver bewusst nur `shadowResult`, nie `result`. Ohne diesen Fall misst
        das Buch den Push nicht mehr, den es selbst verschickt hat."""
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertEqual(led[0]["verdict"], "ABWÄGEN", "eingefrorener Stand beim Push")
        spaet = _wm(verdict="NOBET", shadowResult="WIN")      # Engine hat es sich anders ueberlegt
        led = self.L.abrechnen(led, spaet, "wm", NOW)
        self.assertEqual(led[0]["status"], "abgerechnet")
        self.assertTrue(led[0]["win"])
        self.assertEqual(led[0]["ergebnisQuelle"], "schatten",
                         "die Herkunft muss dranstehen, sonst ist es eine stille Umdeutung")

    def test_ein_NOBET_kommt_gar_nicht_erst_ins_buch(self):
        """Erste Haelfte der Gegenprobe: NOBET wird nie erfasst — es ist keine Wette."""
        self.assertEqual(self.L.erfassen([], _wm(verdict="NOBET"), "wm", NOW), [])

    def test_zeile_die_als_NOBET_ins_buch_kam_bleibt_offen(self):
        """Zweite Haelfte: stuende eine NOBET-Zeile doch im Buch (Altbestand, anderer Erfasser),
        macht ein Schatten-Ergebnis keine Wette daraus. Der eingefrorene Stand entscheidet."""
        zeile = [{"k": "wm|A-1-MEX-ZAF|Über 2.5 Tore", "dataset": "wm",
                  "pickKey": "A-1-MEX-ZAF", "markt": "Über 2.5 Tore", "odds": 1.9,
                  "gesehenAm": NOW.isoformat(), "status": "offen", "win": None,
                  "settledAt": None, "verdict": "NOBET", "push": False}]
        led = self.L.abrechnen(zeile, _wm(verdict="NOBET", shadowResult="WIN"), "wm", NOW)
        self.assertEqual(led[0]["status"], "offen")

    def test_echtes_ergebnis_schlaegt_den_schatten(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        led = self.L.abrechnen(led, _wm(result="LOSS", shadowResult="WIN"), "wm", NOW)
        self.assertFalse(led[0]["win"])
        self.assertNotIn("ergebnisQuelle", led[0])

    def test_ohne_ergebnis_bleibt_die_zeile_offen(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        led = self.L.abrechnen(led, _wm(), "wm", NOW)
        self.assertEqual(led[0]["status"], "offen")

    def test_schatten_void_bleibt_void(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        led = self.L.abrechnen(led, _wm(verdict="NOBET", shadowResult="VOID"), "wm", NOW)
        self.assertEqual(led[0]["status"], "void")
        self.assertIsNone(led[0]["win"])

    # ── 14.09.2026: gebucht wird, wann es WIRKLICH rausging ─────────────────────────────────
    def test_slate_datum_folgt_dem_karten_fenster(self):
        """Spiegel von telegram_wm._in_slate: [Tag 08:00 UTC, +1 Tag 08:00 UTC).

        Ohne das Fenster landen die MLS-Spaetspiele (00:30 UTC) in der Karte des FOLGETAGS —
        also in einer Karte, in der sie nie standen."""
        self.assertEqual(self.L.slate_datum("2026-09-20T16:00:00Z"), "2026-09-20")
        self.assertEqual(self.L.slate_datum("2026-09-20T00:30:00Z"), "2026-09-19")
        self.assertEqual(self.L.slate_datum("2026-09-20T08:00:00Z"), "2026-09-20", "Grenze gehoert zum Tag")
        self.assertEqual(self.L.slate_datum("2026-09-20T07:59:00Z"), "2026-09-19")
        self.assertIsNone(self.L.slate_datum(None))

    def _zeile(self, **kw):
        r = {"k": "wm|A-1-MEX-ZAF|Über 2.5 Tore", "dataset": "wm", "push": True,
             "odds": 1.9, "status": "offen", "gesehenAm": NOW.isoformat(),
             "kickoff": "2026-09-20T16:00:00Z"}
        r.update(kw)
        return [r]

    def test_sendezeit_kommt_aus_dem_karten_buch(self):
        karten = {"morning_card:2026-09-20": "2026-09-20T09:12:00Z"}
        out = self.L.sendezeit_nachtragen(self._zeile(), karten, {}, "wm", NOW)
        self.assertEqual(out[0]["gesendetAm"], "2026-09-20T09:12:00Z")
        self.assertEqual(out[0]["sendeQuelle"], "morning_card")

    def test_ohne_karte_wird_NICHT_geraten(self):
        """⭐ Der Kern des Fundes: ein Pick fuer ein Spiel in drei Wochen ist noch nicht
        gesendet. Ihn trotzdem in die aktuelle Woche zu buchen, war der ganze Fehler."""
        out = self.L.sendezeit_nachtragen(self._zeile(), {}, {}, "wm", NOW)
        self.assertIsNone(out[0].get("gesendetAm"))

    def test_intraday_nachzuegler_schlaegt_die_karte(self):
        karten = {"morning_card:2026-09-20": "2026-09-20T09:12:00Z"}
        intraday = {"A-1-MEX-ZAF|Über 2.5 Tore": "2026-09-14T15:00:00Z"}
        out = self.L.sendezeit_nachtragen(self._zeile(), karten, intraday, "wm", NOW)
        self.assertEqual(out[0]["gesendetAm"], "2026-09-14T15:00:00Z")
        self.assertEqual(out[0]["sendeQuelle"], "intraday")

    def test_sende_quote_wird_nur_frisch_erfasst(self):
        """Die Quote im Moment des Sendens gibt es nur, solange der Lauf nah dran ist."""
        frisch = NOW.isoformat()
        out = self.L.sendezeit_nachtragen(self._zeile(gesendetAm=frisch), {}, {}, "wm", NOW)
        self.assertEqual(out[0]["pushOdds"], 1.9)
        self.assertEqual(out[0]["oddsQuelle"], "senden")

    def test_alte_zeile_bekommt_KEINE_erfundene_sende_quote(self):
        """⭐ Was ein Pick beim Senden kostete, steht nirgends nachtraeglich. Eine Zahl dafuer
        zu erfinden waere schlimmer als eine ehrlich beschriftete zweitbeste."""
        alt = (NOW - timedelta(days=3)).isoformat()
        out = self.L.sendezeit_nachtragen(self._zeile(gesendetAm=alt), {}, {}, "wm", NOW)
        self.assertNotIn("pushOdds", out[0])
        self.assertEqual(out[0]["oddsQuelle"], "vorAnpfiff")

    def test_sendezeit_wird_nie_ueberschrieben(self):
        karten = {"morning_card:2026-09-20": "2026-09-20T09:12:00Z"}
        out = self.L.sendezeit_nachtragen(self._zeile(gesendetAm="2026-09-01T07:00:00Z"),
                                          karten, {}, "wm", NOW)
        self.assertEqual(out[0]["gesendetAm"], "2026-09-01T07:00:00Z")

    def test_aussortierte_zeilen_bekommen_keine_sendezeit(self):
        karten = {"morning_card:2026-09-20": "2026-09-20T09:12:00Z"}
        out = self.L.sendezeit_nachtragen(self._zeile(push=False), karten, {}, "wm", NOW)
        self.assertIsNone(out[0].get("gesendetAm"), "was nie rausging, hat keine Sendezeit")

    def test_abrechnungs_quote_bevorzugt_die_sende_quote(self):
        self.assertEqual(self.L.abrechnungs_quote({"pushOdds": 1.7, "odds": 2.1}), 1.7)
        self.assertEqual(self.L.abrechnungs_quote({"odds": 2.1}), 2.1)
        self.assertIsNone(self.L.abrechnungs_quote({"odds": 1.0}), "1.0 ist keine Quote")
        self.assertIsNone(self.L.abrechnungs_quote({}))

    def test_das_announce_buch_ist_KEIN_sendebuch(self):
        """Die Lehre in einem Test: `mark` ohne `gesendet` fuellt nur `announced`."""
        import pick_announce_state as S
        st = {}
        S.mark(st, ["x|y"], "2026-09-14T06:00:00Z")
        self.assertIn("x|y", st["announced"])
        self.assertNotIn("x|y", st.get("gesendet") or {})
        S.mark(st, ["x|y"], "2026-09-14T15:00:00Z", gesendet=True)
        self.assertEqual(st["gesendet"]["x|y"], "2026-09-14T15:00:00Z")

    def test_unbrauchbare_quote_fliegt_raus(self):
        led = [{"k": "wm|a", "dataset": "wm", "verdict": "ABWÄGEN", "status": "abgerechnet",
                "push": True, "odds": o, "win": True, "settledAt": "2026-08-29T10:00:00Z"}
               for o in (None, 1.0, 0)]
        self.assertEqual(self.L.schubladen(led), {})

    def test_wurde_gepusht_kennt_den_unterschied_zu_unbekannt(self):
        led = self.L.erfassen([], _wm(), "wm", NOW)
        self.assertIs(self.L.wurde_gepusht(led, "wm", "A-1-MEX-ZAF", "Über 2.5 Tore"), True)
        self.assertIsNone(self.L.wurde_gepusht(led, "wm", "A-1-MEX-ZAF", "Gibtsnicht"),
                          "None heisst: steht nicht im Buch. Nicht: wurde nicht gepusht.")


class Register(unittest.TestCase):
    def test_beide_schubladen_landen_im_freigabe_register(self):
        import freigabe
        importlib.reload(freigabe)
        led = []
        for i in range(40):
            led.append({"k": f"wm|g{i}", "dataset": "wm", "verdict": "ABWÄGEN",
                        "status": "abgerechnet", "push": True, "odds": 2.0,
                        "win": i % 3 != 0, "settledAt": "2026-08-29T10:00:00Z"})
            led.append({"k": f"wm|s{i}", "dataset": "wm", "verdict": "ABWÄGEN",
                        "status": "abgerechnet", "push": False, "odds": 2.0,
                        "win": i % 3 == 0, "settledAt": "2026-08-29T10:00:00Z"})
        z = {r["schublade"]: r for r in freigabe.push_schubladen(
            led, now=datetime(2026, 8, 29, 18, tzinfo=timezone.utc))}
        self.assertEqual(set(z), {"ABWÄGEN · gepusht", "ABWÄGEN · aussortiert"})
        self.assertGreater(z["ABWÄGEN · gepusht"]["roi"], z["ABWÄGEN · aussortiert"]["roi"])
        # 08.09.2026 (Lucas: „ja Freigabe locker"): der fehlende CLV blockiert nicht mehr —
        # das Tor ist die ROI-Untergrenze. Was an die Stelle der alten Zusicherung tritt: die
        # Lücke muss AUF der Zeile stehen. „nicht erhoben" ist eine Datenlücke, kein Nein.
        self.assertEqual(z["ABWÄGEN · gepusht"]["clvUrteil"], "nicht erhoben")
        self.assertIn("kein CLV", z["ABWÄGEN · gepusht"]["grund"])

    def test_leeres_buch_erzeugt_keine_zeile(self):
        import freigabe
        importlib.reload(freigabe)
        self.assertEqual(freigabe.push_schubladen([]), [])


if __name__ == "__main__":
    unittest.main()
