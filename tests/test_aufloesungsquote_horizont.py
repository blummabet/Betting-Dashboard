"""🔴 21.09.2026 (Lucas' Störungsmeldung): „TENNIS: nur 262/676 fällige Märkte aufgelöst (39 %),
ESPORTS 333/668 (50 %)" — rot, mit der Deutung „Settlement läuft ins Leere, genau in den Ligen,
auf denen die Shortlist steht".

Nachgemessen je Endtag statt je Sportart:

    04.09.  37/132  28 %      07.09.  89/ 92  97 %      12.09. 215/216 100 %
    05.09. 101/213  47 %      08.09. 111/112  99 %      ...
    06.09.  63/157  40 %      09.09. 153/154  99 %      20.09. 176/177  99 %

Der Sprung liegt exakt auf dem 07.09. — dem Tag, an dem `poly_resolutions.json` beginnt
(älteste Auflösung 07.09. 06:04). `poly_money_broad_close.json` reicht bis zum 22.08. zurück.
1998 Märkte endeten vor dem Beginn des Buchs und wurden als „nicht aufgelöst" gezählt, obwohl
für sie nie eine Auflösung existiert haben kann. Seit dem 07.09.: 96–100 % in JEDER Sportart.

Die Rangfolge der Sportarten war keine Aussage über Settlement, sondern darüber, wie viel
Altbestand vor dem 07.09. jede noch in der Close-Datei mitschleppt.

Fehlerklasse: eine Quote, deren Nenner weiter zurückreicht als ihr Zähler.

Der Schnitt darf die Prüfung aber nicht stillstellen: wird das Buch gekappt, wandert der
Horizont nach vorn, und ein echter Ausfall hätte immer weniger Märkte, an denen er sichtbar
würde. Zu wenig übrig ist deshalb selbst ein Befund.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import poly_data_integrity as PI

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc)


def _markt(ende, liga="tennis"):
    """Eine Close-Zeile, die `ende` als Spielende ergibt."""
    return {"capturedAt": (ende - timedelta(hours=2)).isoformat(), "hoursToKickoff": 2.0,
            "league": liga, "sport": "TENNIS", "prices": {"A": 0.6, "B": 0.4}}


BUCH_START = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
ALT_ENDE   = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)   # vor dem Beginn des Buchs
NEU_ENDE   = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)   # danach


def _bau(n_alt, n_neu, n_neu_aufgeloest, horizont=BUCH_START):
    """Die Maerkte liegen FEST — nur der Beginn des Auflösungsbuchs wandert. Sonst verschiebt
    ein anderer Horizont die Maerkte mit und die Gegenprobe misst nichts."""
    close, res = {}, {}
    res["anker"] = {"winner": "A", "ts": horizont.isoformat()}
    for i in range(n_alt):
        close[f"alt-{i}"] = _markt(ALT_ENDE)
    for i in range(n_neu):
        k = f"neu-{i}"
        close[k] = _markt(NEU_ENDE)
        if i < n_neu_aufgeloest:
            res[k] = {"winner": "A", "ts": (NEU_ENDE + timedelta(hours=2)).isoformat()}
    return PI.PolyCtx(now=NOW, close=close, resolutions=res)


class TestDerHorizont(unittest.TestCase):
    def test_er_ist_die_aelteste_auflösung(self):
        h = datetime(2026, 9, 7, 6, 4, tzinfo=timezone.utc)
        res = {"a": {"ts": h.isoformat()}, "b": {"ts": "2026-09-20T00:00:00+00:00"}}
        self.assertEqual(PI.horizont(res), h)

    def test_ohne_zeitstempel_ist_er_unbekannt(self):
        self.assertIsNone(PI.horizont({"a": {"winner": "A"}}))

    def test_unbekannter_horizont_ist_kein_gruenes_haekchen(self):
        """Mit fälligen Märkten, aber ohne lesbaren Buch-Beginn, ist keine Quote zu haben."""
        close = {f"x-{i}": _markt(NEU_ENDE) for i in range(20)}
        ctx = PI.PolyCtx(now=NOW, close=close, resolutions={"a": {"winner": "A"}})
        self.assertFalse(PI.check_resolutions_match_open_keys(ctx)["ok"])

    def test_ohne_faellige_maerkte_sagt_er_gar_nichts(self):
        """Kein Fälliges heisst nicht „kaputt" — und auch nicht „in Ordnung"."""
        ctx = PI.PolyCtx(now=NOW, close={}, resolutions={"a": {"winner": "A"}})
        self.assertTrue(PI.check_resolutions_match_open_keys(ctx)["ok"])


class TestAltbestandZaehltNichtGegenUns(unittest.TestCase):
    def test_der_echte_fall_tennis(self):
        """Viel Altbestand, sauber aufgelöste neue Märkte -> kein Befund."""
        c = PI.check_resolutions_match_open_keys(_bau(n_alt=414, n_neu=262, n_neu_aufgeloest=260))
        self.assertTrue(c["ok"], "Altbestand vor dem Buch ist kein Settlement-Fehler: " + str(c["failures"]))
        self.assertIn("414 ältere Märkte", c["note"])

    def test_ohne_den_schnitt_waere_es_rot(self):
        """Die Gegenprobe: dieselben Daten, Horizont ganz am Anfang -> die alte 39-%-Meldung."""
        ctx = _bau(n_alt=414, n_neu=262, n_neu_aufgeloest=260,
                   horizont=datetime(2026, 8, 1, tzinfo=timezone.utc))   # Buch reicht weiter zurueck
        c = PI.check_resolutions_match_open_keys(ctx)
        self.assertFalse(c["ok"])
        self.assertIn("%", c["failures"][0])

    def test_ein_echter_ausfall_nach_dem_horizont_bleibt_rot(self):
        """Der Schnitt darf nur Altbestand entfernen, nicht das Urteil."""
        c = PI.check_resolutions_match_open_keys(_bau(n_alt=400, n_neu=200, n_neu_aufgeloest=20))
        self.assertFalse(c["ok"], "10 % aufgelöst nach dem Horizont ist ein echter Ausfall")
        self.assertIn("20/200", " ".join(c["failures"]))

    def test_der_horizont_steht_in_der_notiz(self):
        c = PI.check_resolutions_match_open_keys(_bau(10, 20, 20))
        self.assertIn("2026-09-07", c["note"])


class TestDerSchnittStelltDiePruefungNichtStill(unittest.TestCase):
    def test_zu_wenig_uebrig_ist_ein_befund(self):
        """Ein gekapptes Auflösungsbuch schiebt den Horizont vor — dann kann dieser Check
        nichts mehr feststellen, auch keinen echten Ausfall. Das muss dastehen."""
        c = PI.check_resolutions_match_open_keys(_bau(n_alt=900, n_neu=3, n_neu_aufgeloest=3))
        self.assertFalse(c["ok"])
        self.assertIn("kann dieser Check nichts", " ".join(c["failures"]))

    def test_genug_uebrig_ist_still(self):
        c = PI.check_resolutions_match_open_keys(_bau(n_alt=900, n_neu=50, n_neu_aufgeloest=50))
        self.assertTrue(c["ok"])

    def test_er_ist_registriert(self):
        self.assertIn("check_resolutions_match_open_keys", [f.__name__ for f in PI.POLY_CHECKS])

    def test_kein_check_ist_zweimal_registriert(self):
        """🔴 21.09.2026: `check_wette_hat_die_kasse_beruehrt` trug `@poly_check` DOPPELT —
        der Waechter lief zweimal, jeder seiner Funde haette zweimal in der Störungsmeldung
        gestanden und `nFail` doppelt gezaehlt. Beim Einsetzen eines Nachbarn passiert das
        leicht; ich habe an derselben Stelle schon einmal einem Nachbarn den Dekorator
        weggenommen. Fehlerklasse: ein Waechter, der sich selbst zweimal meldet.
        Der Test prueft die Klasse, nicht den einen Namen."""
        from collections import Counter
        doppelt = [n for n, k in Counter(f.__name__ for f in PI.POLY_CHECKS).items() if k > 1]
        self.assertEqual(doppelt, [], "doppelt registriert: %s" % doppelt)

    def test_der_zweite_dekorator_bringt_den_import_um(self):
        """Ein Test faengt das erst, wenn ihn jemand laufen laesst — `poly_status.json` vom
        21.09. 06:03 trug den Doppel-Eintrag schon. Deshalb wirft die Registrierung selbst."""
        with self.assertRaises(RuntimeError):
            PI.poly_check(PI.check_settlement_alive)
        self.assertEqual([f.__name__ for f in PI.POLY_CHECKS].count("check_settlement_alive"), 1,
                         "die abgewiesene Registrierung darf nichts hinterlassen")

    def test_ein_neuer_name_wird_normal_registriert(self):
        def check_nur_fuer_diesen_test(ctx):      # noqa: ANN001
            return None
        try:
            PI.poly_check(check_nur_fuer_diesen_test)
            self.assertIn("check_nur_fuer_diesen_test", [f.__name__ for f in PI.POLY_CHECKS])
        finally:
            PI.POLY_CHECKS[:] = [f for f in PI.POLY_CHECKS
                                 if f.__name__ != "check_nur_fuer_diesen_test"]

    def test_horizont_ist_kein_check(self):
        """Eine reine Hilfsfunktion darf nicht in der Batterie landen — sie nimmt beim
        Einsetzen sonst dem darunterliegenden Check den Dekorator weg."""
        self.assertNotIn("horizont", [f.__name__ for f in PI.POLY_CHECKS])


if __name__ == "__main__":
    unittest.main()
