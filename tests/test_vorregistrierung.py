"""Vorangemeldete Kandidaten (vorregistrierung.py + freigabe.vorregistrierte_schubladen).

01.09.2026. Anlass: die Teilmenge der Poly-Rangliste mit Betfair-Bestaetigung zeigte n=75,
ROI +18,1%, UG +1,1% — die erste ROI-Untergrenze ueber null in diesem Projekt. Und genau deshalb
belegt sie noch nichts: 57 dieser 75 Plays sind dieselben, aus denen die Hypothese gezogen wurde.

Diese Tests sichern die drei Eigenschaften, die aus einem nachtraeglichen Ausschnitt einen echten
Vorwaerts-Test machen. Faellt eine davon weg, ist „vorangemeldet" nur noch ein Wort.
"""
import unittest
from datetime import datetime, timedelta, timezone

import freigabe as F
import vorregistrierung as VR

JETZT = datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc)
ANMELDUNG = JETZT - timedelta(days=1)


def play(ts, pnl=5.0, stake=10.0, clv=1.0, bf=True):
    return {"settledTs": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "pnl": pnl, "stake": stake, "clvPP": clv,
            "signals": (["money", "bf"] if bf else ["money"])}


def reg(sig=None, ziel=60, angemeldet=ANMELDUNG):
    z = VR.ZUSCHNITTE["poly_bf_bestaetigt"]
    return {"poly_bf_bestaetigt": {"angemeldet": angemeldet.isoformat(),
                                   "signatur": sig if sig is not None else z["signatur"],
                                   "zielN": ziel, "rueckblick": {"n": 75, "roi": 0.1811}}}


class TestVorwaertsMessen(unittest.TestCase):
    """Die eine Eigenschaft, um die es geht: was vor der Anmeldung lag, zaehlt nicht."""

    def test_alte_plays_zaehlen_nicht_ins_urteil(self):
        plays = [play(ANMELDUNG - timedelta(days=i + 1)) for i in range(40)]
        seit, davor = VR.teilen(plays, "poly_bf_bestaetigt", reg()["poly_bf_bestaetigt"])
        self.assertEqual((len(seit), len(davor)), (0, 40))

    def test_neue_plays_zaehlen(self):
        plays = ([play(ANMELDUNG - timedelta(days=3))] * 5) + [play(JETZT) for _ in range(3)]
        seit, davor = VR.teilen(plays, "poly_bf_bestaetigt", reg()["poly_bf_bestaetigt"])
        self.assertEqual((len(seit), len(davor)), (3, 5))

    def test_play_ohne_zeitstempel_zaehlt_NICHT_als_neu(self):
        """Ein Play, dessen Zeitpunkt wir nicht kennen, koennte von vorher sein. Fehlende
        Information ist keine Erlaubnis — sonst waere der Vorwaerts-Test durch kaputte
        Zeitstempel aushebelbar."""
        seit, davor = VR.teilen([play(None), play("kaputt")], "poly_bf_bestaetigt",
                                reg()["poly_bf_bestaetigt"])
        self.assertEqual((len(seit), len(davor)), (0, 2))

    def test_der_zuschnitt_filtert_wirklich(self):
        plays = [play(JETZT, bf=True), play(JETZT, bf=False), play(JETZT, bf=False)]
        seit, _ = VR.teilen(plays, "poly_bf_bestaetigt", reg()["poly_bf_bestaetigt"])
        self.assertEqual(len(seit), 1)


class TestEingefrorenerZuschnitt(unittest.TestCase):
    """Ohne diese Sperre koennte man die Grenze verschieben, bis die Zahl passt — und es
    weiterhin einen Vorwaerts-Test nennen."""

    def test_geaenderte_signatur_macht_die_anmeldung_ungueltig(self):
        r = reg(sig="irgendein anderer zuschnitt")
        self.assertTrue(VR.signatur_bruch(r, "poly_bf_bestaetigt"))
        seit, davor = VR.teilen([play(JETZT)] * 9, "poly_bf_bestaetigt", r["poly_bf_bestaetigt"])
        self.assertEqual((seit, davor), ([], []), "bei Signaturbruch wird NICHTS mehr gezaehlt")

    def test_unveraenderte_signatur_ist_kein_bruch(self):
        self.assertFalse(VR.signatur_bruch(reg(), "poly_bf_bestaetigt"))

    def test_signaturbruch_meldet_ruht_statt_still_weiterzuzaehlen(self):
        rows = F.vorregistrierte_schubladen(track={"settled": [play(JETZT)] * 80},
                                            reg=reg(sig="anders"), now=JETZT, schreiben=False)
        self.assertEqual(rows[0]["status"], "ruht")
        self.assertTrue(rows[0]["ungueltig"])
        self.assertIn("geändert", rows[0]["grund"])


class TestAnmeldung(unittest.TestCase):
    def test_erste_anmeldung_setzt_den_zeitstempel(self):
        r = VR.anmelden({}, "poly_bf_bestaetigt", now=JETZT)
        self.assertEqual(r["poly_bf_bestaetigt"]["angemeldet"], JETZT.isoformat())

    def test_bestehende_anmeldung_wird_NIE_ueberschrieben(self):
        """Der Zeitstempel ist der ganze Wert dieser Datei. Wird er jeden Lauf neu gesetzt,
        ist das Fenster ewig leer und der Test kann nie abschliessen."""
        r = VR.anmelden(reg(), "poly_bf_bestaetigt", now=JETZT)
        self.assertEqual(r["poly_bf_bestaetigt"]["angemeldet"], ANMELDUNG.isoformat())

    def test_unbekannte_kennung_legt_nichts_an(self):
        self.assertEqual(VR.anmelden({}, "gibtsnicht", now=JETZT), {})

    def test_der_rueckblick_wird_als_anlass_markiert_nicht_als_beleg(self):
        rows = F.vorregistrierte_schubladen(
            track={"settled": [play(ANMELDUNG - timedelta(days=5)) for _ in range(75)]},
            reg={}, now=JETZT, schreiben=False)
        z = rows[0]
        self.assertEqual(z["n"], 0, "der Rueckblick darf nicht ins Urteil")
        self.assertEqual(z["nDavor"], 75)
        self.assertIn("NICHT Teil des Urteils", z["rueckblick"]["hinweis"])
        self.assertAlmostEqual(z["rueckblick"]["roi"], 0.5, places=2)


class TestZielVorher(unittest.TestCase):
    """Wer das Ziel-n erst nachtraeglich festlegt, hoert auf zu messen, sobald es gut aussieht."""

    def test_unter_dem_ziel_wird_nicht_freigegeben_auch_bei_glaenzendem_roi(self):
        plays = [play(JETZT, pnl=20.0) for _ in range(40)]     # ROI +200%
        rows = F.vorregistrierte_schubladen(track={"settled": plays}, reg=reg(ziel=60),
                                            now=JETZT, schreiben=False)
        self.assertNotEqual(rows[0]["status"], "freigegeben")
        self.assertEqual(rows[0]["fehltN"], 20)
        self.assertIn("SEIT der Anmeldung", rows[0]["grund"])

    def test_das_ziel_kommt_aus_der_anmeldung_nicht_aus_dem_code(self):
        plays = [play(JETZT) for _ in range(40)]
        rows = F.vorregistrierte_schubladen(track={"settled": plays}, reg=reg(ziel=12),
                                            now=JETZT, schreiben=False)
        self.assertNotIn("von 12", rows[0].get("grund", ""),
                         "bei erreichtem Ziel entscheidet wieder der normale Richter")
        self.assertGreaterEqual(rows[0]["n"], 12)


class TestGuard(unittest.TestCase):
    def _lauf(self, datei, now=JETZT, unlesbar=False):
        import wm_data_integrity as WDI
        echt, failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: (datei if name == "freigabe.json" else echt(name))
        (WDI._LAZY_FAILED.add if unlesbar else WDI._LAZY_FAILED.discard)("freigabe.json")
        try:
            return next(c for c in WDI.run_checks({"groups": {}}, {}, {}, {}, now=now)
                        if c["id"] == "vorregistrierung")
        finally:
            WDI._lazy = echt
            WDI._LAZY_FAILED.clear(); WDI._LAZY_FAILED.update(failed)

    def _reg(self, n=5, tage=3, ungueltig=False):
        return {"alle": [{"schublade": "🔒 X", "art": "vorangemeldet", "n": n, "zielN": 60,
                          "angemeldet": (JETZT - timedelta(days=tage)).isoformat(),
                          "ungueltig": ungueltig}]}

    def test_laufender_test_ist_gruen(self):
        self.assertTrue(self._lauf(self._reg())["ok"])

    def test_wochenlang_kein_einziger_play_schlaegt_an(self):
        """Der stille Tod: vorregistrierung.json wird nicht committet, jeder Lauf meldet neu an,
        das Fenster bleibt ewig leer — und im Register steht gesund aussehend `0 von 60`."""
        c = self._lauf(self._reg(n=0, tage=30))
        self.assertFalse(c["ok"])
        self.assertIn("committet", c["failures"][0])

    def test_frisch_angemeldet_und_leer_ist_normal(self):
        self.assertTrue(self._lauf(self._reg(n=0, tage=2))["ok"])

    def test_signaturbruch_schlaegt_an(self):
        c = self._lauf(self._reg(ungueltig=True))
        self.assertFalse(c["ok"])
        self.assertIn("geaendert", c["failures"][0])

    def test_keine_vorangemeldete_schublade_ist_unbekannt_nicht_gruen(self):
        c = self._lauf({"alle": []})
        self.assertEqual(c["severity"], "warn")
        self.assertFalse(c["ok"])

    def test_unlesbares_register_ist_unbekannt_nicht_gruen(self):
        c = self._lauf(None, unlesbar=True)
        self.assertEqual(c["severity"], "warn")
        self.assertFalse(c["ok"])


if __name__ == "__main__":
    unittest.main()
