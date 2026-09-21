"""🔴 21.09.2026 (Lucas: „Das kam. Aber auf poly wurde nicht gesetzt").

Die Toluca-Order um 01:04 hat das Wallet nie berührt — usdc stand von 21:53 bis 04:39
unverändert bei 178,2312. Das Buch hat sie trotzdem abgerechnet: `result: LOSS, pnl: -5.00`.

Gemessen über das ganze Shortlist-Buch: 30 von 32 Zeilen sind durch einen Wallet-Abgang belegt,
zwei nicht — beide gebuchte Verluste von je 5 $. Die Bilanz war 10 $ schlechter als die
Wirklichkeit.

Fehlerklasse: ein Buch, das seine eigene Behauptung nie gegen die Kasse prüft.

Zwei eigene Fehlversuche stecken in diesem Modul, beide beim Nachmessen aufgefallen und hier
als Test festgehalten:

1. **Einzelsuche** — je Wette ein Abgang in Höhe ihres Einsatzes. Zwei Käufe im selben
   15-Minuten-Fenster zeigen sich als EIN Abgang von 10 $; drei gewonnene Wetten wären als
   erfunden gemeldet worden.
2. **Gruppierung nach Zeitfenster** — kettete 13:07 und 13:31 zu einer Gruppe, die es nie gab.
   Aus vier ungeklärten Zeilen wurden sechs.

Richtig ist eine Zuordnung: jeder Abgang hat ein Budget, jede Wette verbraucht daraus ihren
Einsatz.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wallet_abgleich as W


def _v(*paare):
    return [{"ts": t, "usdc": u} for t, u in paare]


def _b(key, ts, stake=5.0, **kw):
    d = {"betKey": key, "placedAt": ts, "stake": stake}
    d.update(kw)
    return d


T = "2026-09-20T%s:00+00:00"


class TestBewegungen(unittest.TestCase):
    def test_nur_echte_aenderungen(self):
        v = _v((T % "13:00", 100.0), (T % "13:15", 100.0), (T % "13:30", 95.0))
        b = W.bewegungen(v)
        self.assertEqual(len(b), 1)
        self.assertAlmostEqual(b[0]["delta"], -5.0)

    def test_rauschen_unter_der_schwelle_zaehlt_nicht(self):
        v = _v((T % "13:00", 100.0), (T % "13:15", 99.8))
        self.assertEqual(W.bewegungen(v), [])

    def test_unlesbare_punkte_stuerzen_nicht(self):
        self.assertEqual(W.bewegungen([{"ts": "gestern", "usdc": 1}, {"ts": None}, {}]), [])


class TestZuordnungStattGruppierung(unittest.TestCase):
    """Der Kern — und die zwei Fehlversuche, die hier nicht wiederkommen dürfen."""

    def test_ein_abgang_von_zehn_traegt_zwei_wetten(self):
        """Fehlversuch 1: die Einzelsuche fand diesen Abgang nicht und haette beide Wetten
        als unbelegt gemeldet."""
        v = _v((T % "13:00", 100.0), (T % "13:15", 90.0))
        r = W.pruefe_buch([_b("a", T % "13:07"), _b("b", T % "13:08")], v)
        self.assertEqual(len(r["belegt"]), 2)
        self.assertEqual(r["ohne"], [])

    def test_ein_abgang_von_fuenf_traegt_nur_eine(self):
        """Die Gegenprobe dazu — sonst wuerde jeder Abgang beliebig viele Wetten decken."""
        v = _v((T % "13:00", 100.0), (T % "13:15", 95.0))
        r = W.pruefe_buch([_b("a", T % "13:07"), _b("b", T % "13:08")], v)
        self.assertEqual(len(r["belegt"]), 1)
        self.assertEqual(len(r["ohne"]), 1)

    def test_zwei_abgaenge_zu_verschiedenen_zeiten_werden_nicht_verkettet(self):
        """Fehlversuch 2: die Gruppierung machte aus 13:07 und 13:31 eine Gruppe und suchte
        einen Abgang von 10 $, den es nie gab."""
        v = _v((T % "13:00", 100.0), (T % "13:15", 95.0), (T % "13:45", 90.0))
        r = W.pruefe_buch([_b("a", T % "13:07"), _b("b", T % "13:31")], v)
        self.assertEqual(len(r["belegt"]), 2, "beide haben ihren eigenen Abgang")
        self.assertEqual(r["ohne"], [])

    def test_der_echte_fall_toluca(self):
        """usdc unveraendert ueber das ganze Fenster — die Wette hat die Kasse nie beruehrt."""
        v = _v(("2026-09-20T21:53:00+00:00", 178.2312),
               ("2026-09-21T01:00:00+00:00", 178.2312),
               ("2026-09-21T04:39:00+00:00", 178.2312))
        r = W.pruefe_buch([_b("tol", "2026-09-21T01:04:00+00:00", pnl=-5.0, result="LOSS")], v)
        self.assertEqual(len(r["ohne"]), 1)
        self.assertEqual(r["summeOhne"], 5.0, "die Zahl, um die die Bilanz falsch ist")

    def test_die_gebuehr_faellt_in_die_toleranz(self):
        """Gemessen: 5 $ Einsatz zeigten sich als -5,07."""
        v = _v((T % "13:00", 100.0), (T % "13:15", 94.93))
        self.assertEqual(len(W.pruefe_buch([_b("a", T % "13:07")], v)["belegt"]), 1)


class TestNichtPruefbarIstNichtInOrdnung(unittest.TestCase):
    """„Fehlende Information rendert als harmloser Default" — hier waere der harmlose Default
    eine bestaetigte Wette."""

    def test_ohne_verlauf_ist_nichts_belegt(self):
        r = W.pruefe_buch([_b("a", T % "13:07")], [])
        self.assertEqual(len(r["unpruefbar"]), 1)
        self.assertEqual(r["belegt"], [])
        self.assertEqual(r["ohne"], [])

    def test_ausserhalb_des_verlaufs_ist_nicht_unbelegt(self):
        """Eine Wette von vor Beginn der Aufzeichnung ist NICHT widerlegt — sie ist ungeprueft.
        Der Unterschied entscheidet, ob man eine Zeile aus der Bilanz nimmt."""
        v = _v((T % "13:00", 100.0), (T % "13:15", 95.0))
        r = W.pruefe_buch([_b("alt", "2026-06-01T10:00:00+00:00")], v)
        self.assertEqual(len(r["unpruefbar"]), 1)
        self.assertIn("ausserhalb des Verlaufs", r["unpruefbar"][0]["grund"])

    def test_ohne_zeitstempel_ist_nicht_pruefbar(self):
        v = _v((T % "13:00", 100.0), (T % "13:15", 95.0))
        self.assertEqual(len(W.pruefe_buch([{"betKey": "x", "stake": 5.0}], v)["unpruefbar"]), 1)

    def test_ohne_einsatz_ebenfalls(self):
        v = _v((T % "13:00", 100.0), (T % "13:15", 95.0))
        self.assertEqual(len(W.pruefe_buch([{"betKey": "x", "placedAt": T % "13:07"}],
                                           v)["unpruefbar"]), 1)


class TestEinZugangIstKeinKauf(unittest.TestCase):
    def test_eine_auszahlung_belegt_keine_wette(self):
        v = _v((T % "13:00", 100.0), (T % "13:15", 106.0))
        self.assertEqual(len(W.pruefe_buch([_b("a", T % "13:07")], v)["ohne"]), 1)


class TestDerVerlaufWirdFortgeschrieben(unittest.TestCase):
    def test_gleiche_staende_blaehen_die_reihe_nicht_auf(self):
        import fetch_wm_poly_balance as F
        v = []
        for i in range(5):
            v = F.verlauf_anhaengen(v, {"updatedAt": "T%d" % i, "usdc": 100.0,
                                        "positions": 0, "total": 100.0})
        self.assertEqual(len(v), 1, "unveraenderte Staende werden zusammengefasst")
        # 🔴 21.09.2026 korrigiert: hier stand `ts == "T4"` — der Zeitstempel zog mit jedem
        # ruhigen Lauf nach. Damit wanderte der Moment der letzten AENDERUNG nach vorne: ein
        # Kauf um 01:15 stand nach drei Stunden Stille als 04:39 in der Reihe, und der Abgleich
        # (Fenster +/-25 Min) fand seine Wette nicht mehr. `ts` ist jetzt die erste Sichtung
        # dieses Standes, `bisTs` die letzte.
        self.assertEqual(v[-1]["ts"], "T0", "wann dieser Stand zuerst gesehen wurde")
        self.assertEqual(v[-1]["bisTs"], "T4", "bis wann er galt")

    def test_eine_aenderung_bekommt_eine_eigene_zeile(self):
        import fetch_wm_poly_balance as F
        v = F.verlauf_anhaengen([], {"updatedAt": "T1", "usdc": 100.0})
        v = F.verlauf_anhaengen(v, {"updatedAt": "T2", "usdc": 95.0})
        self.assertEqual([x["usdc"] for x in v], [100.0, 95.0])

    def test_der_verlauf_folgt_dem_stand_wohin_man_ihn_auch_legt(self):
        """🔴 21.09.2026: die Testsuite legte `wm_poly_verlauf.json` im echten Baum an.

        `test_poly_balance_positions.py` leitet fuer `_save` nur `OUT_FILE` nach `tmp_path` um.
        Der Verlauf hing an einer eigenen Konstanten und schrieb daran vorbei ins Repo — ein
        Pipeline-Artefakt aus einem Testlauf. Fehlerklasse: ein zweiter Schreibvorgang, den die
        Umleitung des ersten nicht mit erfasst.
        """
        import fetch_wm_poly_balance as F
        tmp = Path(tempfile.mkdtemp())
        alt = F.OUT_FILE
        try:
            F.OUT_FILE = tmp / "wm_poly_balance.json"
            F._save(50.0, 0.0, "0xabc", positions=0.0)
            self.assertTrue((tmp / "wm_poly_verlauf.json").exists(),
                            "der Verlauf landet neben seinem Stand")
        finally:
            F.OUT_FILE = alt

    def test_ohne_balance_im_namen_wird_der_stand_nicht_ueberschrieben(self):
        import fetch_wm_poly_balance as F
        alt = F.OUT_FILE
        try:
            F.OUT_FILE = Path("/tmp/irgendwas.json")
            self.assertNotEqual(F.verlauf_datei(), Path("/tmp/irgendwas.json"))
        finally:
            F.OUT_FILE = alt

    def test_die_reihe_wird_gekappt(self):
        import fetch_wm_poly_balance as F
        v = []
        for i in range(30):
            v = F.verlauf_anhaengen(v, {"updatedAt": "T%d" % i, "usdc": float(i)}, keep=10)
        self.assertEqual(len(v), 10)


class TestDerWaechter(unittest.TestCase):
    def test_ohne_verlauf_meldet_er_dass_er_nichts_pruefen_kann(self):
        """Kein Verlauf darf nicht als gruen durchgehen."""
        import poly_data_integrity as PI
        c = PI.check_wette_hat_die_kasse_beruehrt(None)
        self.assertIn(c["id"], ("wette_hat_die_kasse_beruehrt",))
        # Am echten Bestand: entweder es gibt noch keinen Verlauf (dann sagt er das),
        # oder er hat geprueft. Beides ist erlaubt — stumm sein ist es nicht.
        if not (Path(__file__).resolve().parents[1] / "wm_poly_verlauf.json").exists():
            self.assertFalse(c["ok"])
            self.assertIn("kein Wallet-Verlauf", " ".join(c["failures"]))

    def test_er_ist_registriert(self):
        import poly_data_integrity as PI
        self.assertIn("check_wette_hat_die_kasse_beruehrt",
                      [f.__name__ for f in PI.POLY_CHECKS])


if __name__ == "__main__":
    unittest.main()
