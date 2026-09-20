"""🔴 20.09.2026 — der Wächter übersprang genau die Fälle, für die er gebaut wurde.

`check_takt_stimmt_mit_dem_cron` gibt es seit dem 17.09. Er prüfte aber nur Crons, die rund um
die Uhr laufen:

    if len(crons) != 1 or not re.match(r"^\\S+\\s+\\*\\s+\\*\\s+\\*\\s+\\*$", crons[0]):
        continue

Der Grund war richtig — bei „0,30 10-21" ist die Lücke über Nacht 13 Stunden, daraus einen
Ausfall zu lesen wäre derselbe Fehler, den der Guard fangen soll. Die Folge war es nicht:
übersprungen wurde damit ausgerechnet `manage-liga-poly` (0,30 10-21), der Workflow mit der
schärfsten Zeitanforderung im Repo — 40-Minuten-Schließfenster vor jedem Anpfiff.

Gemessen am 20.09.2026 aus `health/liga-poly.json`: 20 Läufe in 96,7 h = 5,0 statt 25 am Tag,
kleinste Lücke 63,7 Min (größer als das Fenster), und bei 0 von 7 Liga-Positionen lag je ein
Lauf im Schließfenster. Der Pre-Match-Close hat nie funktioniert.

Fehlerklasse: ein Wächter, der die Fälle überspringt, für die er gebaut wurde.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uebersicht_integrity as U
import run_health as R


class TestStundenfenster(unittest.TestCase):
    def test_der_volle_tag(self):
        self.assertEqual(U._cron_stunden("*/15 * * * *"), set(range(24)))

    def test_ein_bereich(self):
        self.assertEqual(U._cron_stunden("0,30 10-21 * * *"), set(range(10, 22)))

    def test_ein_bereich_ueber_mitternacht(self):
        self.assertEqual(U._cron_stunden("0,30 22-2 * * *"), {22, 23, 0, 1, 2})

    def test_einzelne_stunden_und_schritte(self):
        self.assertEqual(U._cron_stunden("0 6,10 * * *"), {6, 10})
        self.assertEqual(U._cron_stunden("0 */6 * * *"), {0, 6, 12, 18})

    def test_unsinn_gibt_none_und_nicht_alles(self):
        """„Nicht deutbar" darf nicht als „läuft immer" durchgehen — das wäre wieder ein
        harmloser Default für eine fehlende Information."""
        self.assertIsNone(U._cron_stunden("0 xx * * *"))
        self.assertIsNone(U._cron_stunden("0 99 * * *"))
        self.assertIsNone(U._cron_stunden("kaputt"))


class TestDerDichtesteCronIstDerMassstab(unittest.TestCase):
    def test_housekeeping_verdraengt_den_arbeitstakt_nicht(self):
        """`manage-liga-poly` hat zwei Crons: den Arbeitstakt (0,30 10-21) und ein Tages-
        Housekeeping (0 8). Die alte Bedingung `len(crons) != 1` liess deshalb den ganzen
        Workflow fallen."""
        ab, st = U._dichtester_cron(["0,30 10-21 * * *", "0 8 * * *"])
        self.assertEqual(ab, 30.0)
        self.assertEqual(st, set(range(10, 22)))

    def test_ein_fenster_cron_ist_messbar_und_wird_nicht_uebersprungen(self):
        """Der Vorfall selbst, als reine Funktion. Genau diese Liste steht in
        `manage-liga-poly.yml` — und genau sie fiel vorher durchs Raster."""
        self.assertEqual(U._messbare_crons(["0,30 10-21 * * *", "0 8 * * *"]),
                         ["0,30 10-21 * * *", "0 8 * * *"])
        self.assertTrue(U._messbare_crons(["*/15 9-21 * * *"]))

    def test_wochen_und_monats_crons_bleiben_draussen(self):
        """Aus zwanzig Laeufen laesst sich ein Wochentakt nicht beurteilen."""
        self.assertEqual(U._messbare_crons(["17 3 * * 1", "0 4 1 * *"]), [])

    def test_ohne_deutbaren_cron_kein_massstab(self):
        # (Wochen-/Tages-Crons filtert schon der Aufrufer heraus; hier geht es um Unsinn.)
        self.assertIsNone(U._dichtester_cron(["kaputt", "* * * *", "0 xx * * *"]))


class TestImFensterGemessenUndNichtUeberNacht(unittest.TestCase):
    """Die eigentliche Rechnung: die Nachtlücke darf nicht mitzählen, die Tageslücken schon."""

    def _datei(self, tmp, stempel):
        import json
        p = Path(tmp) / "x.json"
        p.write_text(json.dumps({"runs": [{"ts": t} for t in stempel]}), encoding="utf-8")
        return p

    def _lauf(self, tag, stunde, minute=0):
        return datetime(2026, 9, tag, stunde, minute, tzinfo=timezone.utc).isoformat()

    def test_im_fenster_kommt_der_echte_takt_heraus(self):
        import tempfile
        # Sauberer 30-Minuten-Takt von 10 bis 12 Uhr, an drei Tagen.
        stempel = [self._lauf(t, h, m)
                   for t in (14, 15, 16) for h in (10, 11, 12) for m in (0, 30)]
        with tempfile.TemporaryDirectory() as tmp:
            p = self._datei(tmp, stempel)
            mit = U._health_abstand(p, set(range(10, 22)))
            ohne = U._health_abstand(p, None)
        self.assertEqual(mit, 30.0)
        # Ehrlichkeit ueber den eigenen Fix: das 25-%-Quantil war gegen die Nachtluecke
        # ohnehin robust — hier kommt dieselbe Zahl heraus. Der Fehler war NICHT eine
        # verzerrte Messung, sondern dass Fenster-Crons gar nicht gemessen wurden.
        # Wo das Fenster wirklich noetig ist, zeigt `kadenz`: dort entscheiden Minimum und
        # Maximum, und die Nachtluecke ist immer groesser als jedes Schliessfenster.
        self.assertEqual(ohne, 30.0)

    def test_ohne_fenster_kann_kadenz_nie_sicher_sagen(self):
        """Der Fall, in dem das Fenster wirklich traegt."""
        laeufe = [{"ts": self._lauf(t, h, m)}
                  for t in (14, 15, 16) for h in (10, 11, 12) for m in (0, 30)]
        ohne = R.kadenz(laeufe, fenster_min=40)
        mit = R.kadenz(laeufe, fenster_min=40, stunden=set(range(10, 22)))
        self.assertEqual(ohne["fensterUrteil"], "Glueckssache",
                         "die Nachtluecke allein macht aus sauberen 30 Minuten eine Unsicherheit")
        self.assertEqual(mit["fensterUrteil"], "sicher")

    def test_ein_echter_ausfall_im_fenster_faellt_auf(self):
        import tempfile
        # Derselbe Aufbau, aber nur noch zwei Laeufe je Tag statt sechs.
        stempel = [self._lauf(t, h) for t in (14, 15, 16, 17) for h in (10, 13, 16, 19)]
        with tempfile.TemporaryDirectory() as tmp:
            mit = U._health_abstand(self._datei(tmp, stempel), set(range(10, 22)))
        self.assertEqual(mit, 180.0, "drei Stunden Abstand muessen als drei Stunden dastehen")

    def test_ein_lauf_pro_tag_gibt_im_fenster_kein_urteil_statt_der_nachtluecke(self):
        """Hier traegt der Filter wirklich: laeuft ein Workflow nur einmal taeglich, sind ALLE
        Luecken Nachtluecken. Ohne Filter kaeme „alle 24 Stunden" heraus — eine Zahl, die vom
        Fenster nichts weiss. Mit Filter kommt „kein Urteil" heraus, und das ist die
        ehrlichere Auskunft."""
        import tempfile
        stempel = [self._lauf(t, 11) for t in range(10, 20)]
        with tempfile.TemporaryDirectory() as tmp:
            p = self._datei(tmp, stempel)
            self.assertIsNone(U._health_abstand(p, set(range(10, 22))))
            self.assertAlmostEqual(U._health_abstand(p, None), 1440.0, delta=1.0)

    def test_zu_wenige_luecken_im_fenster_geben_kein_urteil(self):
        """Lieber kein Urteil als eines aus zwei Zahlen."""
        import tempfile
        stempel = [self._lauf(14, 10), self._lauf(14, 11), self._lauf(15, 10)]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(U._health_abstand(self._datei(tmp, stempel), set(range(10, 22))))


class TestDerGuardSiehtDenLigaWorkflowJetzt(unittest.TestCase):
    def test_liga_poly_wird_nicht_mehr_uebersprungen(self):
        """Der Vorfall selbst, gegen den echten Bestand. Faellt diese Zeile weg, weil die
        Taktung repariert wurde, ist das die gute Nachricht — dann sagt es der Test."""
        c = U.check_takt_stimmt_mit_dem_cron({})
        self.assertEqual(c["severity"], "warn", "eine Obergrenze rechtfertigt keinen Fehler")
        namen = " ".join(c["failures"])
        if "liga-poly" in namen:
            self.assertIn("Zeitfenster gemessen", namen,
                          "ein Fenster-Cron muss AUCH im Fenster gemessen worden sein")
        # Sonst: die Taktung haelt inzwischen — dann darf hier nichts stehen.

    def test_das_schliessfenster_wird_aus_dem_workflow_gelesen(self):
        t = (Path(__file__).resolve().parents[1]
             / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertEqual(U._schliessfenster_min(t), 40.0)
        self.assertIsNone(U._schliessfenster_min("kein Fenster hier"))

    def test_das_deklarierte_fenster_passt_zur_konfiguration(self):
        """Ein zweiter Wert an zweiter Stelle veraltet. Der Workflow sagt 40 Minuten — die
        Handelskonfiguration muss dasselbe sagen, sonst prueft der Guard ein Fenster, das es
        gar nicht gibt."""
        import manage_wm_poly_positions as M
        t = (Path(__file__).resolve().parents[1]
             / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertAlmostEqual(U._schliessfenster_min(t),
                               M.PRE_MATCH_CLOSE_HOURS * 60, delta=1.0)


class TestDerGuardGanzDurchgespielt(unittest.TestCase):
    """Die Tests oben pruefen die Bausteine. Dieser spielt den Guard komplett durch — gegen ein
    gebautes Repo, nicht gegen den Live-Bestand.

    Grund: ein Test, der nur anspringt, wenn der echte Bestand gerade rot ist, ist gruen, sobald
    jemand den Guard wieder blind macht. Genau das war beim Vorgaenger der Fall — er hat
    `manage-liga-poly` drei Tage lang nicht angesehen, ohne dass ein Test das gemerkt haette.
    """

    def _repo(self, tmp, cron_zeilen, stempel, fenster="40"):
        import json
        basis = Path(tmp)
        (basis / ".github" / "workflows").mkdir(parents=True)
        (basis / "health").mkdir()
        crons = "\n".join(f"    - cron: '{c}'" for c in cron_zeilen)
        (basis / ".github" / "workflows" / "w.yml").write_text(
            "on:\n  schedule:\n" + crons + "\n"
            "jobs:\n  x:\n    steps:\n"
            "      - run: python3 run_health.py --slug w\n"
            "        env:\n"
            f"          RUN_HEALTH_FENSTER_MIN:  '{fenster}'\n",
            encoding="utf-8")
        (basis / "health" / "w.json").write_text(
            json.dumps({"runs": [{"ts": s} for s in stempel]}), encoding="utf-8")
        return basis

    def _mit_basis(self, basis, fn):
        alt = U.BASE
        try:
            U.BASE = basis
            return fn()
        finally:
            U.BASE = alt

    def _stempel(self, abstand_min, n, start_h=10):
        t0 = datetime(2026, 9, 14, start_h, 0, tzinfo=timezone.utc)
        raus, t = [], t0
        while len(raus) < n:
            if 10 <= t.hour <= 21:
                raus.append(t.isoformat())
            t += timedelta(minutes=abstand_min)
        return raus

    def test_zwei_crons_mit_fenster_werden_geprueft_und_gemeldet(self):
        """Der Liga-Fall: Arbeitstakt + Housekeeping, Fenster 10-21, geliefert alle 3 Stunden."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            basis = self._repo(tmp, ["0,30 10-21 * * *", "0 8 * * *"],
                               self._stempel(180, 16))
            c = self._mit_basis(basis, lambda: U.check_takt_stimmt_mit_dem_cron({}))
        self.assertEqual(c["nFail"], 1, "der Workflow MUSS geprueft und gemeldet werden")
        self.assertIn("Zeitfenster gemessen", c["failures"][0])
        self.assertIn("40-Minuten-Fenster", c["failures"][0],
                      "das deklarierte Schliessfenster gehoert in die Meldung")

    def test_ein_gesunder_fenster_workflow_wird_nicht_gemeldet(self):
        """Gegenprobe — sonst waere der Test oben auch gruen, wenn der Guard IMMER meckert."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            basis = self._repo(tmp, ["0,30 10-21 * * *", "0 8 * * *"],
                               self._stempel(30, 20))
            c = self._mit_basis(basis, lambda: U.check_takt_stimmt_mit_dem_cron({}))
        self.assertEqual(c["nFail"], 0, "wer liefert, wird nicht gemeldet")

    def test_ein_wochen_cron_wird_weiterhin_in_ruhe_gelassen(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            basis = self._repo(tmp, ["17 3 * * 1"], self._stempel(180, 16))
            c = self._mit_basis(basis, lambda: U.check_takt_stimmt_mit_dem_cron({}))
        self.assertEqual(c["nFail"], 0)


class TestDieKadenzStehtImArtefakt(unittest.TestCase):
    """„Alle 30 Min, damit garantiert ein Lauf ins 40-Min-Fenster faellt" stand als Kommentar
    im Workflow. Ab jetzt steht die gelieferte Taktung als Zahl im Protokoll."""

    def _laeufe(self, abstand_min, n=20, start=None):
        t0 = start or datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
        return [{"ts": (t0 + timedelta(minutes=abstand_min * i)).isoformat()} for i in range(n)]

    def test_liefergrad_und_luecken(self):
        k = R.kadenz(self._laeufe(30), soll_pro_tag=48, fenster_min=40)
        self.assertEqual(k["nLaeufe"], 20)
        self.assertEqual(k["proTag"], 48.0)
        self.assertEqual(k["liefergradPct"], 100)
        self.assertEqual(k["lueckeMinMin"], 30.0)

    def test_ein_fenster_ist_sicher_wenn_jede_luecke_kleiner_ist(self):
        self.assertEqual(R.kadenz(self._laeufe(30), fenster_min=40)["fensterUrteil"], "sicher")

    def test_ein_fenster_ist_NIE_sicher_wenn_schon_die_kleinste_luecke_groesser_ist(self):
        """Das ist der Liga-Fall: kleinste gemessene Luecke 63,7 Min gegen ein 40-Min-Fenster.
        Auch bei perfekt gleichmaessiger Lieferung koennte es nicht getroffen werden."""
        self.assertEqual(R.kadenz(self._laeufe(64), fenster_min=40)["fensterUrteil"], "nie sicher")

    def test_dazwischen_heisst_glueckssache_und_nicht_in_ordnung(self):
        laeufe = self._laeufe(20, n=10)
        laeufe += [{"ts": (datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)).isoformat()}]
        self.assertEqual(R.kadenz(laeufe, fenster_min=40)["fensterUrteil"], "Glueckssache")

    def test_ohne_fenster_kein_urteil(self):
        self.assertIsNone(R.kadenz(self._laeufe(30))["fensterUrteil"])

    def test_ein_einzelner_lauf_gibt_keine_kadenz(self):
        k = R.kadenz(self._laeufe(30, n=1), soll_pro_tag=48)
        self.assertEqual(k["nLaeufe"], 1)
        self.assertIsNone(k["proTag"])

    def test_am_echten_bestand(self):
        import json
        p = Path(__file__).resolve().parents[1] / "health" / "liga-poly.json"
        if not p.exists():
            self.skipTest("kein Protokoll")
        k = R.kadenz(json.loads(p.read_text(encoding="utf-8")).get("runs"),
                     soll_pro_tag=25, fenster_min=40)
        self.assertIsNotNone(k["proTag"])
        self.assertIsNotNone(k["lueckeMinMin"])


class TestDieWartezeitTrenntDieBeidenErklaerungen(unittest.TestCase):
    """Ohne sie bleibt „warum laeuft er nur 5x" eine Vermutung: lange Wartezeit heisst Runner
    dicht, kurze heisst der Zeitplan feuert nicht."""

    def test_wartezeit_aus_den_beiden_zeitstempeln(self):
        e = R.baue_eintrag("W", "1", None, [], None,
                           {"createdAt": "2026-09-20T15:00:00Z",
                            "startedAt": "2026-09-20T15:18:30Z", "event": "schedule"})
        self.assertEqual(e["wartetS"], 1110.0)
        self.assertEqual(e["event"], "schedule")

    def test_fehlender_zeitstempel_ist_none_und_nicht_null(self):
        """Null Sekunden Wartezeit hiesse „sofort gestartet" — das Gegenteil dessen, was ein
        fehlender Wert bedeutet."""
        e = R.baue_eintrag("W", "1", None, [], None, {"createdAt": None, "startedAt": "x"})
        self.assertIsNone(e["wartetS"])
        e2 = R.baue_eintrag("W", "1", None, [], None, None)
        self.assertIsNone(e2["wartetS"])

    def test_unlesbare_zeitstempel_stuerzen_nicht(self):
        self.assertIsNone(R._sekunden_zwischen("gestern", "heute"))

    def test_der_lauf_kopf_kommt_aus_der_api(self):
        rufe = []

        def fake(url):
            rufe.append(url)
            return {"created_at": "2026-09-20T15:00:00Z",
                    "run_started_at": "2026-09-20T15:02:00Z",
                    "event": "schedule", "run_attempt": 1}

        d = R.hole_lauf("o/r", "42", "tok", fetch=fake)
        self.assertIn("/actions/runs/42", rufe[0])
        self.assertEqual(d["startedAt"], "2026-09-20T15:02:00Z")
        self.assertEqual(d["attempt"], 1)


if __name__ == "__main__":
    unittest.main()
