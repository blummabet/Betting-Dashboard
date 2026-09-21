"""🔴 21.09.2026 (Lucas, Statusseite): „6 Poly-Positionen seit 10–13 Tagen offen —
Auflösung existiert, matcht aber den Key nicht".

Nachgemessen: der Key matcht bei allen sechs EXAKT. Die Auflösung liegt unter demselben
Schlüssel und nennt einen Sieger. Sie hängen an etwas anderem — der Eintrag weiß nicht,
welchen Markt des `-more-markets`-Bündels er meint. Der Stempel vom 10.09. wurde nur beim
Öffnen gesetzt; genau die Einträge, die den Riegel ausgelöst haben, standen da schon offen.
Die Kennung lag die ganze Zeit in der Close-Zeile daneben.

Zwei Fehlerklassen in einem Fund:
  * eine Nachrüstung, die nur Neuzugänge erreicht
  * eine Meldung, die einen anderen Grund nennt als den, der zutrifft
     (sie hat mich selbst zuerst nach einem Key-Normalisierer suchen lassen)

Die Annahme hinter dem Nachtrag ist gemessen, nicht geglaubt: über 22 Stände von
`poly_money_broad_close.json` zwischen dem 07. und 21.09. hat keine der sechs Zeilen ihre
`cond` gewechselt. `condDrift` zählt im Produzenten mit, falls das aufhört.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import poly_shortlist_track as T
import poly_data_integrity as PI

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc)
KEY = "ucl-fen-rom-2026-09-10-more-markets"
COND = "0xfa3c68df51599232eeb1c4269958fdb75c31833df9cec78f2ffc620f829c00ed"


def _close(cond=COND, under=0.62, over=0.38):
    return {KEY: {"cond": cond, "frage": "Fenerbahçe SK vs. AS Roma: O/U 3.5",
                  "prices": {"Under": under, "Over": over},
                  "capturedAt": "2026-09-10T19:00:00+00:00", "hoursToKickoff": 0.2}}


def _offen(**extra):
    e = {"key": KEY, "side": "Under", "verdict": "BET", "conv": 6, "league": "SOCCER",
         "entryPrice": 0.615, "lastPrice": 0.615, "stake": 10.0,
         "firstTs": "2026-09-10T16:28:18+00:00", "lastTs": "2026-09-10T16:28:18+00:00"}
    e.update(extra)
    return {f"{KEY}|Under": e}


def _lauf(prev_open, close, res):
    return T.update_track({"open": dict(prev_open), "settled": [], "unaufloesbar": []},
                          {"plays": []}, close, res, now=NOW)


class TestDerStempelWirdNachgetragen(unittest.TestCase):
    def test_ein_offener_eintrag_ohne_kennung_bekommt_sie_aus_der_close_zeile(self):
        st = _lauf(_offen(), _close(), {})
        e = list(st["open"].values())[0]
        self.assertEqual(e.get("cond"), COND, "die Kennung lag daneben und wurde nicht geholt")
        self.assertIn("O/U 3.5", e.get("frage", ""), "die Linie im Klartext gehört mit")

    def test_und_rechnet_damit_ab_statt_zu_verfallen(self):
        st = _lauf(_offen(), _close(), {KEY: {"winner": "Under", "cond": COND,
                                              "ts": "2026-09-10T19:12:57+00:00"}})
        self.assertEqual(len(st["settled"]), 1, "mit Kennung ist „Under“ eindeutig")
        z = st["settled"][0]
        self.assertEqual(z["result"], "win")
        self.assertAlmostEqual(z["pnl"], round(10 / 0.615 - 10, 2), places=2)
        self.assertEqual(st["open"], {})

    def test_ein_vorhandener_stempel_wird_nie_ueberschrieben(self):
        """Der Nachtrag füllt Lücken. Er korrigiert nichts — sonst wäre er eine Behauptung."""
        anders = "0xdeadbeef"
        st = _lauf(_offen(cond=anders, frage="alte Linie"), _close(), {})
        self.assertEqual(list(st["open"].values())[0]["cond"], anders)

    def test_ohne_kennung_in_der_close_zeile_bleibt_er_ohne(self):
        """Fehlende Information rendert nicht als harmloser Default."""
        st = _lauf(_offen(), {KEY: {"prices": {"Under": 0.62}}}, {})
        self.assertNotIn("cond", list(st["open"].values())[0])

    def test_ohne_kennung_auf_der_auflösungs_seite_wird_weiter_nicht_geraten(self):
        """Altbestand: die Auflösung vor dem 10.09. trägt keine cond. Dann bleibt es offen."""
        st = _lauf(_offen(), _close(), {KEY: {"winner": "Under", "ts": "2026-09-08T20:00:00+00:00"}})
        self.assertEqual(st["settled"], [], "ohne Linie ist „Under“ kein Ergebnis")
        self.assertEqual(len(st["open"]), 1)


class TestDerZeigerWirdAngesehen(unittest.TestCase):
    def test_gleiche_kennung_ist_keine_drift(self):
        st = _lauf(_offen(cond=COND), _close(), {})
        self.assertEqual(st["condDrift"], 0)

    def test_eine_andere_kennung_zaehlt_und_haelt_den_preis_an(self):
        st = _lauf(_offen(cond=COND, lastPrice=0.615), _close(cond="0xandere", under=0.99), {})
        self.assertEqual(st["condDrift"], 1, "die Abweichung muss gezählt werden, nicht nur übersprungen")
        self.assertEqual(list(st["open"].values())[0]["lastPrice"], 0.615,
                         "eine alte Auskunft schlägt eine falsche")

    def test_der_waechter_sieht_den_zeiger_an(self):
        ctx = PI.PolyCtx(now=NOW, shortlist={"condDrift": 2, "open": {}})
        c = PI.check_buendel_cond_ist_stabil(ctx)
        self.assertFalse(c["ok"])
        self.assertIn("2 offene", " ".join(c["failures"]))

    def test_ein_fehlender_zeiger_ist_kein_gruenes_haekchen(self):
        c = PI.check_buendel_cond_ist_stabil(PI.PolyCtx(now=NOW, shortlist={"open": {}}))
        self.assertFalse(c["ok"], "kein Zähler heisst nicht „keine Drift“")

    def test_bei_null_ist_er_still(self):
        c = PI.check_buendel_cond_ist_stabil(PI.PolyCtx(now=NOW, shortlist={"condDrift": 0, "open": {}}))
        self.assertTrue(c["ok"])

    def test_er_ist_registriert(self):
        self.assertIn("check_buendel_cond_ist_stabil", [f.__name__ for f in PI.POLY_CHECKS])


class TestDieMeldungNenntDenGrundDerZutrifft(unittest.TestCase):
    """Die alte Zeile sagte bei JEDER vorhandenen Auflösung „matcht aber den Key nicht"."""

    def _meldung(self, eintrag, res):
        ctx = PI.PolyCtx(now=NOW, resolutions=res,
                         shortlist={"open": {f"{KEY}|Under": eintrag}})
        c = PI.check_settlement_alive(ctx)
        return " ".join(c["failures"])

    def test_der_key_matcht_und_das_steht_nicht_mehr_falsch_da(self):
        m = self._meldung(_offen()[f"{KEY}|Under"],
                          {KEY: {"winner": "Under", "cond": COND}})
        self.assertNotIn("matcht aber den Key nicht", m)
        self.assertIn("der Eintrag nicht", m)

    def test_altbestand_beide_ohne_kennung_wird_als_solcher_benannt(self):
        m = self._meldung(_offen()[f"{KEY}|Under"], {KEY: {"winner": "Under"}})
        self.assertIn("beide Seiten ohne Marktkennung", m)

    def test_ohne_auflösung_bleibt_es_dabei(self):
        m = self._meldung(_offen()[f"{KEY}|Under"], {})
        self.assertIn("keine Auflösung gefunden", m)

    def test_kein_buendel_bekommt_keine_buendel_begruendung(self):
        e = dict(_offen()[f"{KEY}|Under"], key="col1-llf-atn-2026-09-20")
        ctx = PI.PolyCtx(now=NOW, resolutions={"col1-llf-atn-2026-09-20": {"winner": "Llaneros FC"}},
                         shortlist={"open": {"x": e}})
        m = " ".join(PI.check_settlement_alive(ctx)["failures"])
        self.assertNotIn("Bündel", m)


if __name__ == "__main__":
    unittest.main()
