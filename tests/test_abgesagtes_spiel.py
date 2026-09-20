"""🔴 20.09.2026 — ein Spiel, das nie stattgefunden hat, wurde 95 Stunden lang als
„abgepfiffen ohne Ergebnis" gemeldet.

Levante–Athletic Club, geplanter Anpfiff 16.09.2026 19:30 UTC. Die Guard-Batterie meldete jeden
Tag, der Resolver könne es nicht abrechnen. Nachgesehen: das Spiel wurde eine halbe Stunde vor
Beginn wegen Starkregen abgesagt. Es steht in keiner der beiden unabhängigen Ergebnisquellen des
Repos (`results-cache.json`, API-Nachlauf), während Levantes Spiele vom 13.09. und 20.09. in
beiden stehen.

Fehlerklasse: ein Anpfiff, der nur im Kalender stattgefunden hat. `kickoff` ist ein PLAN, und
alles dahinter behandelt einen vergangenen Plan als Ereignis.

Drei Zustände waren nicht zu unterscheiden, weil der Grund nur gedruckt und nie geschrieben wurde:
  · die API kennt das Spiel gar nicht
  · die API sagt „noch nicht fertig"
  · die API sagt „fällt aus"  ← löst sich NIE von selbst
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_liga_ergebnisse as F
import uebersicht_integrity as U


def _item(short, home=1, away=0, fid=1):
    return {"fixture": {"id": fid, "status": {"short": short}},
            "goals": {"home": home, "away": away}}


class TestDerStatusWirdGelesen(unittest.TestCase):
    def test_kurzstatus_normalisiert(self):
        self.assertEqual(F.api_status(_item("pst")), "PST")
        self.assertEqual(F.api_status({}), "")
        self.assertEqual(F.api_status({"fixture": {}}), "")

    def test_die_vier_absage_status(self):
        for st in ("PST", "CANC", "ABD", "SUSP"):
            self.assertTrue(F.ist_abgesagt(_item(st)), st)

    def test_laufende_und_fertige_sind_keine_absage(self):
        for st in ("NS", "1H", "HT", "2H", "FT", "AET", "PEN"):
            self.assertFalse(F.ist_abgesagt(_item(st)), st)

    def test_ein_abgesagtes_spiel_liefert_kein_ergebnis(self):
        """Gegenprobe: `ergebnis_aus_api` darf für PST nichts zurückgeben, auch wenn die API
        aus irgendeinem Grund Tore mitschickt."""
        self.assertIsNone(F.ergebnis_aus_api(_item("PST", 2, 1)))


class TestDieAbsageWirdVermerktAberNichtAlsErgebnis(unittest.TestCase):
    def test_sie_landet_in_einem_eigenen_feld(self):
        fx = {"homeName": "Levante", "awayName": "Athletic Club"}
        self.assertTrue(F.absage_eintragen(fx, "PST", "2026-09-20T19:00:00+00:00"))
        self.assertEqual(fx["absage"]["status"], "PST")

    def test_sie_macht_das_spiel_nicht_zu_einem_gespielten(self):
        """Der Kern: ein `result` würde das Spiel für JEDEN Leser zu einem gespielten machen —
        `hat_ergebnis` prüft nur, ob ein Status dasteht — und es in Bilanzen ziehen, in denen es
        nichts zu suchen hat."""
        fx = {}
        F.absage_eintragen(fx, "PST", "T")
        self.assertFalse(F.hat_ergebnis(fx), "eine Absage ist kein Ergebnis")
        self.assertNotIn("result", fx)
        self.assertTrue(F.ist_abgesagt_vermerkt(fx))

    def test_derselbe_status_zweimal_ist_keine_aenderung(self):
        """Sonst schriebe jeder Lauf die Datei neu und der Commit-Diff wäre täglich voll."""
        fx = {}
        self.assertTrue(F.absage_eintragen(fx, "PST", "T1"))
        self.assertFalse(F.absage_eintragen(fx, "PST", "T2"))

    def test_ein_leerer_status_vermerkt_nichts(self):
        fx = {}
        self.assertFalse(F.absage_eintragen(fx, "", "T"))
        self.assertEqual(fx, {})


class TestAbgesagteFallenAusDerWarteschlange(unittest.TestCase):
    """Die Wirkung, auf die es ankommt: der Nachlauf darf nicht ewig auf ein Ergebnis warten,
    das nie kommt — sonst steht die Batterie auf Dauerrot und sagt damit gar nichts mehr."""

    def _groups(self, fx_extra=None):
        vorbei = (datetime.now(timezone.utc) - timedelta(hours=95)).isoformat()
        fx = {"homeName": "Levante", "awayName": "Athletic Club", "kickoff": vorbei, "fid": 1570389}
        fx.update(fx_extra or {})
        return {"ESP": {"fixtures": [fx]}}

    def test_ohne_vermerk_steht_es_in_der_warteschlange(self):
        offen = F.offene_fixtures(self._groups(), datetime.now(timezone.utc))
        self.assertEqual(len(offen.get("ESP") or []), 1)

    def test_mit_vermerk_nicht_mehr(self):
        offen = F.offene_fixtures(self._groups({"absage": {"status": "PST"}}),
                                  datetime.now(timezone.utc))
        self.assertEqual(offen, {})

    def test_ein_echtes_ergebnis_nimmt_es_ebenfalls_heraus(self):
        offen = F.offene_fixtures(self._groups({"result": {"status": "FT"}}),
                                  datetime.now(timezone.utc))
        self.assertEqual(offen, {})


class TestDerGuardTrenntDieBeidenFaelle(unittest.TestCase):
    def _ctx(self, offen=(), abgesagt=()):
        return {"ergebnisNachlaufLiga": {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "offen": list(offen), "abgesagt": list(abgesagt)}}

    def test_ein_abgesagtes_spiel_ist_keine_ergebnis_stoerung(self):
        c = U.check_ergebnisse_kommen_an(self._ctx(
            abgesagt=[{"paarung": "Levante–Athletic Club", "status": "PST"}]))
        text = " ".join(c["failures"])
        self.assertIn("abgesagt", text)
        self.assertIn("Entscheidung", text, "eine Absage braucht eine Entscheidung, keine Geduld")
        self.assertNotIn("Resolver", text, "sie gehört nicht in dieselbe Meldung")

    def test_ein_echtes_fehlendes_ergebnis_meldet_weiter(self):
        c = U.check_ergebnisse_kommen_an(self._ctx(
            offen=[{"paarung": "A–B", "stundenHer": 20, "grund": "API-Status NS"}]))
        text = " ".join(c["failures"])
        self.assertIn("Resolver", text)
        self.assertIn("API-Status NS", text, "der Grund gehört in die Meldung")

    def test_der_satz_behauptet_keinen_anpfiff_mehr(self):
        """Der Vorfall selbst: „abgepfiffen" war die Behauptung, die 95 Stunden lang falsch war."""
        c = U.check_ergebnisse_kommen_an(self._ctx(
            offen=[{"paarung": "A–B", "stundenHer": 20}]))
        text = " ".join(c["failures"])
        self.assertNotIn("abgepfiffen", text)
        self.assertIn("vergangenem Anpfiff", text)

    def test_ohne_stoerung_bleibt_er_still(self):
        self.assertEqual(U.check_ergebnisse_kommen_an(self._ctx())["nFail"], 0)


if __name__ == "__main__":
    unittest.main()
