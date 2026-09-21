"""🔴 21.09.2026, 01:04 UTC (Lucas: „Das kam. Aber auf poly wurde nicht gesetzt").

Die Nachricht sagte „🔥 AUTO-PLAY PLATZIERT", nannte Einsatz, Quote, „Fill: 75¢" und eine
Order-ID. Im Buch stand eine Zeile mit `status: "placed"`. Auf Polymarket lag keine Position.

`polymarket_bet.place_market_order` gibt an DREI Stellen `status: "placed"` zurück, und nur
eine davon ist ein Kauf:

    method="market"       die Market-Order wurde ausgeführt   -> Position
    method="maker_limit"  ruhende Limit-Order oben aufs Gebot -> KEINE Position
    method="limit_gtc"    Fallback nach FOK-Kill, liegt im Buch -> KEINE Position

In zwei von drei Fällen gibt es eine Order-ID und nichts ist gekauft. Die Order-Schicht liefert
`method` seit jeher mit — der Aufrufer hat es weggeworfen, und die Meldung nannte den ASK
„Fill", ein Wort, das „gekauft zu" heißt.

Fehlerklasse: „angenommen" und „gefüllt" sind zwei verschiedene Dinge, und die Meldung kannte
den Unterschied nicht.

Verwandt mit dem Verkaufsversuch vom 19.09., aber spiegelverkehrt: dort fehlte die Spur einer
ausgebliebenen Wirkung, hier behauptet die Spur eine Wirkung, die es nicht gab.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import poly_data_integrity as PI
import telegram_trades as TT


class TestDieOrderSchichtUnterscheidetDreiWege(unittest.TestCase):
    def test_alle_drei_geben_placed_zurueck(self):
        """Der Kern des Vorfalls, am Quelltext belegt: `status` allein trennt nicht."""
        import inspect
        import polymarket_bet as P
        src = inspect.getsource(P.place_market_order)
        self.assertEqual(src.count('"status": "placed"'), 3)
        for m in ('"method": "market"', '"method": "maker_limit"', '"method": "limit_gtc"'):
            self.assertIn(m, src, "die Schicht muss ihren Weg mitliefern: " + m)


class TestDieMeldungBehauptetKeinenKaufMehr(unittest.TestCase):
    def _text(self, method):
        gesendet = {}

        def fake(t):
            gesendet["text"] = t
            return True

        alt = TT.send_trades_message
        TT.send_trades_message = fake
        try:
            TT.notify_shortlist_opened(
                match="Deportivo Toluca FC vs Club Santos Laguna", side="Deportivo Toluca FC",
                stake=5.0, fill=0.751, conv=7, push_preis=0.76,
                order_id="0xbd5c144945657bb4bd626d", slug="mex-tol-san-2026-09-20",
                method=method)
        finally:
            TT.send_trades_message = alt
        return gesendet.get("text", "")

    def test_eine_ruhende_order_heisst_nicht_platziert(self):
        for m in ("maker_limit", "limit_gtc"):
            t = self._text(m)
            self.assertIn("ORDER IM BUCH", t, m)
            self.assertNotIn("PLATZIERT", t, m)
            self.assertIn("noch NICHT gefuellt", t, m)

    def test_eine_ruhende_order_nennt_den_preis_nicht_fill(self):
        """„Fill" heisst „gekauft zu". Bei einer ruhenden Order ist es ein Limit."""
        t = self._text("limit_gtc")
        self.assertIn("Limit:", t)
        self.assertNotIn("Fill:", t)

    def test_ein_echter_kauf_bleibt_wie_bisher(self):
        t = self._text("market")
        self.assertIn("PLATZIERT", t)
        self.assertIn("Fill:", t)
        self.assertNotIn("noch NICHT gefuellt", t)

    def test_ohne_method_wird_nichts_behauptet(self):
        """Ein alter Aufrufer liefert `method` nicht mit — dann darf die Meldung weder
        „gefuellt" noch „ruht" behaupten. Fehlende Information ist kein harmloser Default."""
        t = self._text(None)
        self.assertIn("steht nicht fest", t)
        self.assertNotIn("Fill:", t)


class TestDasBuchTraegtDenWeg(unittest.TestCase):
    def test_der_shortlist_pfad_schreibt_method_mit(self):
        q = (Path(__file__).resolve().parents[1] / "shortlist_auto_bet.py").read_text(
            encoding="utf-8")
        i = q.index('"tokenId": tok')
        self.assertIn('"method": res.get("method")', q[i:i + 700])

    def test_und_reicht_ihn_an_die_meldung_durch(self):
        q = (Path(__file__).resolve().parents[1] / "shortlist_auto_bet.py").read_text(
            encoding="utf-8")
        i = q.index("notify_shortlist_opened(")
        self.assertIn('method=bet.get("method")', q[i:i + 900])


class TestDerWaechterFindetRuhendeOrdernImBuch(unittest.TestCase):
    def _mit(self, zeilen, tmp):
        import json
        (Path(tmp) / "shortlist_auto_bets_placed.json").write_text(
            json.dumps({"bets": zeilen}), encoding="utf-8")
        alt = PI.__file__
        return alt

    def _lauf(self, zeilen):
        import json
        import tempfile
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shortlist_auto_bets_placed.json").write_text(
                json.dumps({"bets": zeilen}), encoding="utf-8")
            with mock.patch.object(PI, "__file__", str(Path(tmp) / "x.py")):
                return PI.check_ruhende_order_ist_keine_position(None)

    def test_eine_ruhende_order_wird_gemeldet(self):
        c = self._lauf([{"betKey": "mex-tol-san", "status": "placed", "method": "limit_gtc"}])
        self.assertEqual(c["nFail"], 1)
        self.assertIn("RUHENDE", " ".join(c["failures"]))
        self.assertIn("bewacht", " ".join(c["failures"]))

    def test_eine_zeile_ohne_method_ist_nicht_belegt(self):
        c = self._lauf([{"betKey": "mex-tol-san", "status": "placed"}])
        self.assertEqual(c["nFail"], 1)
        self.assertIn("ohne `method`", " ".join(c["failures"]))

    def test_ein_echter_kauf_meldet_nichts(self):
        self.assertEqual(self._lauf([{"betKey": "x", "status": "placed",
                                      "method": "market"}])["nFail"], 0)

    def test_abgerechnete_zeilen_interessieren_nicht(self):
        self.assertEqual(self._lauf([{"betKey": "x", "status": "lost"},
                                     {"betKey": "y", "status": "won", "method": None}])["nFail"], 0)

    def test_der_waechter_ist_registriert(self):
        namen = [f.__name__ for f in PI.POLY_CHECKS]
        self.assertIn("check_ruhende_order_ist_keine_position", namen)
        self.assertIn("check_trades_push_buch", namen,
                      "beim Einfuegen darf keinem Nachbarn der Dekorator abhanden kommen")


if __name__ == "__main__":
    unittest.main()
