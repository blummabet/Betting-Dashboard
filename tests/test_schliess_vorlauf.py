"""🔴 20.09.2026 — das Schliessfenster war an eine Taktung gekoppelt, die niemand nachgezählt hat.

Im Quelltext stand seit dem 16.06.2026: „40min …, weil GitHubs Scheduler real nur ~30min-Kadenz
liefert → bei 30min-Läufen landet garantiert einer im Fenster [KO-40,KO-10]".

Gemessen aus `health/liga-poly.json` am 20.09.2026: 4,7 statt 25 Läufe am Tag, kleinste Lücke im
Arbeitsfenster 63,7 Minuten — grösser als das 40-Minuten-Fenster. Bei 0 von 7 Liga-Positionen lag
je ein Lauf im Schliessfenster. Anlass war Schalke v Elversberg: Anpfiff 15:30 UTC, um 15:23 stand
die Position noch offen, kein Verkaufsversuch im Buch.

Fehlerklasse: eine Zusage, die an eine Taktung gekoppelt ist, die niemand nachgezählt hat.

Der Fix ist NICHT ein grösseres festes Fenster — das wäre dieselbe Wette auf eine unbelegte Zahl.
Geschlossen wird, wenn dieser Lauf der letzte sein könnte, der es rechtzeitig schafft: Fenster +
gemessene Lücke, gedeckelt. Läuft der Manager wieder dicht, zieht sich der Vorlauf von selbst
zusammen.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manage_wm_poly_positions as M


def _laeufe(abstand_min, n=20, start_h=10, fenster=(10, 21)):
    """Läufe im Arbeitsfenster, über mehrere Tage — wie im echten Protokoll."""
    t = datetime(2026, 9, 14, start_h, 0, tzinfo=timezone.utc)
    raus = []
    while len(raus) < n:
        if fenster[0] <= t.hour <= fenster[1]:
            raus.append({"ts": t.isoformat()})
        t += timedelta(minutes=abstand_min)
    return raus


class TestDieGemesseneLuecke(unittest.TestCase):
    def test_ein_sauberer_takt_gibt_den_takt_zurueck(self):
        self.assertAlmostEqual(M.naechste_luecke_h(_laeufe(30), stunden=set(range(10, 22))),
                               0.5, delta=0.01)

    def test_das_quantil_und_nicht_das_maximum_entscheidet(self):
        """Ein einzelner Ausfall darf die Regel nicht bestimmen — sonst schliesst ein
        Loch von gestern heute alle Positionen Stunden zu früh."""
        # Sauberer 30-Minuten-Takt, aber ein Tag hat mitten im Fenster ein 5-Stunden-Loch.
        laeufe = []
        for tag in (14, 15, 16):
            std = [10, 10.5, 11, 11.5, 12] + ([17, 17.5, 18] if tag == 15
                                              else [12.5, 13, 13.5])
            for h in std:
                laeufe.append({"ts": datetime(2026, 9, tag, int(h),
                                              30 if h % 1 else 0,
                                              tzinfo=timezone.utc).isoformat()})
        q90 = M.naechste_luecke_h(laeufe, quantil=0.9, stunden=set(range(10, 22)))
        mx = M.naechste_luecke_h(laeufe, quantil=1.0, stunden=set(range(10, 22)))
        self.assertAlmostEqual(mx, 5.0, delta=0.01, msg="das Maximum IST der Ausfall")
        self.assertLess(q90, mx, "das Quantil darf ihm nicht folgen")
        self.assertAlmostEqual(q90, 0.5, delta=0.1, msg="es bleibt beim echten Takt")

    def test_der_median_reicht_nicht(self):
        """Beim Median läge man in der Hälfte der Fälle daneben — und daneben heisst hier:
        die Position läuft ins Spiel."""
        laeufe = _laeufe(30, n=10) + _laeufe(150, n=10, start_h=11)
        self.assertGreater(M.naechste_luecke_h(laeufe, quantil=0.9, stunden=set(range(10, 22))),
                           M.naechste_luecke_h(laeufe, quantil=0.5, stunden=set(range(10, 22))))

    def test_zu_wenige_luecken_geben_None_und_nicht_null(self):
        """None heisst „nicht gemessen". Null hiesse „der nächste Lauf kommt sofort" — das
        Gegenteil dessen, was fehlende Information bedeutet."""
        self.assertIsNone(M.naechste_luecke_h([]))
        self.assertIsNone(M.naechste_luecke_h(_laeufe(30, n=3)))

    def test_unlesbare_zeitstempel_stuerzen_nicht(self):
        self.assertIsNone(M.naechste_luecke_h([{"ts": "gestern"}, {"ts": None}, {}]))

    def test_die_nachtluecke_wird_ausgeblendet_wenn_das_fenster_bekannt_ist(self):
        laeufe = _laeufe(30, n=30)
        mit = M.naechste_luecke_h(laeufe, quantil=1.0, stunden=set(range(10, 22)))
        ohne = M.naechste_luecke_h(laeufe, quantil=1.0, stunden=None)
        self.assertLess(mit, ohne, "über Nacht laeuft er nicht — das ist kein Ausfall")


class TestDerVorlauf(unittest.TestCase):
    def test_ohne_messung_bleibt_es_beim_festen_fenster(self):
        self.assertEqual(M.schliess_vorlauf_h(None), M.PRE_MATCH_CLOSE_HOURS)

    def test_ein_dichter_takt_verschiebt_kaum(self):
        """Der eigentliche Punkt: läuft der Manager wieder alle 30 Minuten, zieht sich der
        Vorlauf von selbst zusammen — die späte Steam bleibt erhalten."""
        self.assertAlmostEqual(M.schliess_vorlauf_h(0.5, fenster_h=0.67), 1.17, delta=0.001)

    def test_ein_duenner_takt_zieht_den_vorlauf_nach_vorn(self):
        self.assertAlmostEqual(M.schliess_vorlauf_h(1.5, fenster_h=0.67), 2.17, delta=0.001)

    def test_der_deckel_haelt(self):
        """Ohne Deckel würde eine 15-Stunden-Lücke Positionen einen halben Tag vor Anpfiff
        schliessen — der Schutz wäre teurer als der Schaden."""
        self.assertAlmostEqual(M.schliess_vorlauf_h(15.0, fenster_h=0.67, deckel_h=3.0),
                               3.67, delta=0.001)

    def test_eine_negative_luecke_macht_das_fenster_nicht_kleiner(self):
        self.assertAlmostEqual(M.schliess_vorlauf_h(-5.0, fenster_h=0.67), 0.67, delta=0.001)


class TestDerAusstiegSelbst(unittest.TestCase):
    def test_der_schalke_fall(self):
        """Der Lauf um 14:02 UTC sah h=1,47 vor Anpfiff. Mit dem alten festen Fenster (0,67h)
        tat er nichts, und danach kam kein Lauf mehr. Mit dem gemessenen Vorlauf schliesst er."""
        self.assertEqual(M.time_based_exit(1.47, 0.0)[0], False)
        self.assertEqual(M.time_based_exit(1.47, 0.0, vorlauf_h=2.17)[0], True)

    def test_die_begruendung_sagt_woher_die_schwelle_kommt(self):
        _, grund = M.time_based_exit(1.47, 0.0, vorlauf_h=2.17)
        self.assertIn("gemessene Lücke", grund)
        _, grund2 = M.time_based_exit(0.3, 0.0)
        self.assertNotIn("gemessene Lücke", grund2,
                         "ohne Messung darf die Begründung keine behaupten")

    def test_ohne_vorlauf_bleibt_das_alte_verhalten(self):
        self.assertTrue(M.time_based_exit(0.3, 0.0)[0])
        self.assertFalse(M.time_based_exit(5.0, 0.0)[0])

    def test_nach_anpfiff_greift_der_zeit_exit_nicht(self):
        """In-Play ist ein anderer Fall und hat seine eigene Regel (NO_INPLAY_LOSS_SELL)."""
        self.assertFalse(M.time_based_exit(-0.5, -50.0, vorlauf_h=3.0)[0])

    def test_der_stop_loss_bleibt_ausserhalb_des_vorlaufs(self):
        self.assertTrue(M.time_based_exit(1.9, -20.0, vorlauf_h=0.67)[0])
        self.assertFalse(M.time_based_exit(1.9, -5.0, vorlauf_h=0.67)[0])

    def test_ein_grosser_vorlauf_schluckt_das_stop_loss_fenster(self):
        """Kein Fehler, aber es muss jemandem auffallen: liegt der Vorlauf über
        EARLY_STOPLOSS_HOURS, wird ohnehin vorher geschlossen — der Stop-Loss kann dann gar
        nicht mehr feuern. Der Manager sagt das im Log."""
        self.assertGreaterEqual(3.67, M.EARLY_STOPLOSS_HOURS)
        an, grund = M.time_based_exit(1.9, -20.0, vorlauf_h=3.67)
        self.assertTrue(an)
        self.assertIn("Pre-Match Close", grund, "geschlossen wird als Close, nicht als Stop-Loss")


class TestDieQuelleWirdBenannt(unittest.TestCase):
    """„Fehlende Information rendert als harmloser Default" ist die Klasse, die diesen Umbau
    ausgeloest hat — ohne Protokoll muss das DASTEHEN und nicht wie eine Messung aussehen."""

    def test_ohne_protokoll_faellt_er_auf_das_feste_fenster_und_sagt_es(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            v, l, q = M.gemessener_vorlauf("gibts-nicht", basis=tmp)
        self.assertEqual(v, M.PRE_MATCH_CLOSE_HOURS)
        self.assertIsNone(l)
        self.assertEqual(q, "kein Protokoll")

    def test_mit_protokoll_kommt_eine_messung_heraus(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "health").mkdir()
            (Path(tmp) / "health" / "x.json").write_text(
                json.dumps({"runs": _laeufe(30, n=20)}), encoding="utf-8")
            v, l, q = M.gemessener_vorlauf("x", basis=tmp)
        self.assertEqual(q, "gemessen")
        self.assertAlmostEqual(l, 0.5, delta=0.1)
        self.assertGreater(v, M.PRE_MATCH_CLOSE_HOURS)

    def test_ein_kaputtes_protokoll_ist_kein_absturz_sondern_ein_rueckfall(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "health").mkdir()
            (Path(tmp) / "health" / "x.json").write_text("{kaputt", encoding="utf-8")
            v, l, q = M.gemessener_vorlauf("x", basis=tmp)
        self.assertEqual(q, "kein Protokoll")
        self.assertEqual(v, M.PRE_MATCH_CLOSE_HOURS)

    def test_am_echten_bestand(self):
        p = Path(__file__).resolve().parents[1] / "health" / "liga-poly.json"
        if not p.exists():
            self.skipTest("kein Protokoll")
        v, l, q = M.gemessener_vorlauf("liga-poly")
        self.assertEqual(q, "gemessen")
        self.assertGreaterEqual(v, M.PRE_MATCH_CLOSE_HOURS)
        self.assertLessEqual(v, M.PRE_MATCH_CLOSE_HOURS + M.VORLAUF_DECKEL_H)


class TestDieStundenAngabeStehtNurEinmal(unittest.TestCase):
    def test_der_workflow_setzt_sie_job_weit(self):
        """Zwei Kopien derselben Stundenangabe waren schon einmal der Fehler: run_health und
        der Positions-Manager müssen mit demselben Fenster rechnen."""
        t = (Path(__file__).resolve().parents[1]
             / ".github/workflows/manage-liga-poly.yml").read_text(encoding="utf-8")
        self.assertEqual(t.count("RUN_HEALTH_STUNDEN"), 1)
        import yaml
        d = yaml.safe_load(t)
        job = list(d["jobs"].values())[0]
        self.assertIn("RUN_HEALTH_STUNDEN", job.get("env") or {},
                      "job-weit, damit beide Schritte sie sehen")


if __name__ == "__main__":
    unittest.main()
