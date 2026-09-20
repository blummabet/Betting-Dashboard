"""🔴 20.09.2026 — „Auto-Trading ist aus" galt nur fuer einen von mehreren Wegen.

Lucas hatte gesagt: „wir stellen das Auto trading mal ab und schreiben es nur im Cockpit mit
ala paper trading". Umgebaut wurde `auto_wm_poly_trigger.py`, gemeldet wurde „aus". Am selben
Tag gingen VIER echte Orders raus — 09:31, 11:31, 13:07, 13:31, je 5 $, mit orderId — aus
`shortlist_auto_bet.py`: ein zweiter Pfad zur selben Order-Schicht, eigener Schalter, ohne
jede Kenntnis vom Papierbetrieb.

Fehlerklasse: ein Schalter, der an einer Instanz haengt, waehrend die Klasse mehrere hat.

Die Tests hier sichern die Umkehrung: der Modus steht in EINEM Register in der Order-Schicht,
jeder Kauf muss dort durch, und ein Pfad, der sich nicht deklariert, kann kein Geld ausgeben.
"""
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import polymarket_bet as PB


class TestDasRegisterEntscheidet(unittest.TestCase):
    def test_jeder_bekannte_pfad_hat_einen_gueltigen_modus(self):
        self.assertTrue(PB.HANDELSPFADE, "ein leeres Register ist keine Entscheidung")
        for pfad, modus in PB.HANDELSPFADE.items():
            self.assertIn(modus, ("live", "papier"), f"{pfad}: {modus!r}")

    def test_der_stand_ist_der_von_lucas_gesetzte(self):
        """20.09.2026 woertlich: „die heute Spielenswert auf poly will ich weiter aktiv haben.
        Die nicht abdrehen / Nur das trading auf paper trading umstellen."

        Das ist kein Geschmack, das ist eine Anweisung — und sie gehoert an die Stelle, an der
        sie sonst beim naechsten Umbau still gekippt wird."""
        self.assertEqual(PB.HANDELSPFADE.get("shortlist"), "live",
                         '„Heute spielenswert“ bleibt aktiv')
        self.assertEqual(PB.HANDELSPFADE.get("auto-trigger"), "papier")
        self.assertEqual(PB.HANDELSPFADE.get("maker"), "papier")

    def test_ein_unbekannter_pfad_ist_ein_fehler_und_kein_default(self):
        """„Fehlende Information rendert als harmloser Default" — hier waere der harmlose
        Default eine echte Order."""
        with self.assertRaises(ValueError):
            PB.handelsmodus("gibt-es-nicht")

    def test_der_env_override_greift_in_beide_richtungen(self):
        alt = os.environ.pop("POLY_MODUS_AUTO_TRIGGER", None)
        try:
            os.environ["POLY_MODUS_AUTO_TRIGGER"] = "live"
            self.assertEqual(PB.handelsmodus("auto-trigger"), "live")
            os.environ["POLY_MODUS_AUTO_TRIGGER"] = "papier"
            self.assertEqual(PB.handelsmodus("auto-trigger"), "papier")
            os.environ["POLY_MODUS_AUTO_TRIGGER"] = "vielleicht"
            self.assertEqual(PB.handelsmodus("auto-trigger"), PB.HANDELSPFADE["auto-trigger"],
                             "Unsinn im Env faellt auf das Register zurueck, nicht auf live")
        finally:
            os.environ.pop("POLY_MODUS_AUTO_TRIGGER", None)
            if alt is not None:
                os.environ["POLY_MODUS_AUTO_TRIGGER"] = alt


class TestKeinKaufOhneDeklaration(unittest.TestCase):
    def test_ohne_pfad_wird_nicht_gekauft(self):
        with self.assertRaises(ValueError):
            PB.place_market_order("tok", 5.0, "key")

    def test_mit_unbekanntem_pfad_wird_nicht_gekauft(self):
        with self.assertRaises(ValueError):
            PB.place_market_order("tok", 5.0, "key", pfad="neuer-pfad-den-keiner-kennt")

    def test_papier_fasst_die_boerse_nicht_an(self):
        """Der Beweis, nicht die Behauptung: waehrend des Aufrufs ist der CLOB-Import
        unmoeglich gemacht. Kommt die Funktion trotzdem durch, hat sie ihn nie gebraucht."""
        class _Meta:
            def find_spec(self, name, path=None, target=None):
                if name.startswith("py_clob_client"):
                    raise AssertionError("Papierbetrieb hat den CLOB geladen")
                return None

        gemerkt = [m for m in list(sys.modules) if m.startswith("py_clob_client")]
        gesichert = {m: sys.modules.pop(m) for m in gemerkt}
        sys.meta_path.insert(0, _Meta())
        try:
            res = PB.place_market_order("tok", 5.0, "key", price_hint=0.42, pfad="auto-trigger")
        finally:
            sys.meta_path.pop(0)
            sys.modules.update(gesichert)
        self.assertEqual(res["status"], "papier")
        self.assertIsNone(res["orderId"])
        self.assertEqual(res["pfad"], "auto-trigger")
        self.assertEqual(res["amountUsdc"], 5.0)

    def test_live_laeuft_weiter_in_die_boerse(self):
        """Gegenprobe — sonst waere der Test oben auch gruen, wenn ALLES Papier waere.
        Der Live-Pfad muss den CLOB erreichen; dass er es tut, zeigt hier der Import-Fehler."""
        class _Meta:
            def find_spec(self, name, path=None, target=None):
                if name.startswith("py_clob_client"):
                    raise ModuleNotFoundError("Testschranke")
                return None

        gemerkt = [m for m in list(sys.modules) if m.startswith("py_clob_client")]
        gesichert = {m: sys.modules.pop(m) for m in gemerkt}
        sys.meta_path.insert(0, _Meta())
        try:
            with self.assertRaises(SystemExit):
                PB.place_market_order("tok", 5.0, "key", price_hint=0.42, pfad="shortlist")
        finally:
            sys.meta_path.pop(0)
            sys.modules.update(gesichert)


class TestJederAufruferDeklariertSich(unittest.TestCase):
    """Der Riegel oben wirkt zur Laufzeit — ein vergessener Pfad kracht beim ersten Kauf statt
    Geld auszugeben. Dieser Test zieht ihn nach vorn: er findet jeden Aufruf im Quelltext."""

    WURZEL = Path(__file__).resolve().parents[1]

    def _aufrufer(self):
        raus = []
        for p in self.WURZEL.glob("*.py"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            if "place_market_order(" in t and p.name != "polymarket_bet.py":
                raus.append(p)
        return raus

    def test_es_gibt_ueberhaupt_aufrufer(self):
        """Gegenprobe gegen sich selbst: findet die Suche nichts, waere der Test unten gruen."""
        self.assertGreaterEqual(len(self._aufrufer()), 2)

    def test_kein_aufruf_ohne_pfad(self):
        ohne = []
        for p in self._aufrufer():
            t = p.read_text(encoding="utf-8", errors="ignore")
            for i, zeile in enumerate(t.splitlines(), 1):
                if "place_market_order(" not in zeile or zeile.lstrip().startswith("#"):
                    continue
                # Der Aufruf geht ueber mehrere Zeilen — den ganzen Ausdruck ansehen.
                block = "\n".join(t.splitlines()[i - 1:i + 6])
                if "pfad=" not in block:
                    ohne.append(f"{p.name}:{i}")
        self.assertEqual(ohne, [],
                         "Aufruf der Order-Schicht ohne deklarierten Pfad: " + ", ".join(ohne))


class TestVerkaeufeBleibenImmerLive(unittest.TestCase):
    """Ein Ausgang, den man abschalten kann, ist die Mechanik hinter Toulouse: die Position
    laeuft ins Spiel, weil niemand sie zugemacht hat. Kaufen darf man sperren, verkaufen nie."""

    def test_der_verkauf_kennt_keinen_pfad_parameter(self):
        import inspect
        sig = inspect.signature(PB.place_sell_order)
        self.assertNotIn("pfad", sig.parameters,
                         "sobald der Verkauf einen Modus hat, kann ihn jemand auf Papier stellen")

    def test_das_register_enthaelt_keinen_verkaufspfad(self):
        for name in PB.HANDELSPFADE:
            self.assertNotIn("verkauf", name.lower())
            self.assertNotIn("sell", name.lower())


class TestDerPapierlaufHinterlaesstEineSpur(unittest.TestCase):
    """20.09.2026: `liga_paper_bets.json` existierte nach dem Umbau gar nicht. „Nichts
    qualifiziert" und „Pfad laeuft nicht" sahen identisch aus — naemlich nach nichts."""

    def setUp(self):
        import auto_wm_poly_trigger
        self.A = importlib.reload(auto_wm_poly_trigger)

    def test_ein_leerer_lauf_schreibt_trotzdem_einen_vermerk(self):
        laeufe = self.A.papier_lauf_marker([], "papier", 0, 0, "keine Kandidaten", ts="2026-09-20T15:00:00")
        self.assertEqual(len(laeufe), 1)
        self.assertEqual(laeufe[0]["grund"], "keine Kandidaten")
        self.assertEqual(laeufe[0]["gebucht"], 0)
        self.assertEqual(laeufe[0]["modus"], "papier")

    def test_der_vermerk_sagt_auch_wie_viele_kandidaten_es_gab(self):
        """Ohne diese Zahl bleibt „0 gebucht" zweideutig: keine Kandidaten, oder Kandidaten,
        die alle an einem Tor gescheitert sind."""
        a = self.A.papier_lauf_marker([], "papier", 0, 0, "keine Kandidaten", ts="t")[0]
        b = self.A.papier_lauf_marker([], "papier", 4, 0, "kein Kandidat durch alle Tore", ts="t")[0]
        self.assertNotEqual(a["kandidaten"], b["kandidaten"])

    def test_die_liste_waechst_nicht_unbegrenzt(self):
        viele = [{"ts": str(i)} for i in range(1000)]
        self.assertEqual(len(self.A.papier_lauf_marker(viele, "papier", 1, 0, "x", ts="t")),
                         self.A.LAUF_KEEP)

    def test_der_marker_haengt_am_finally_und_nicht_an_einem_ausgang(self):
        """`_main_lauf` hat neun fruehe `return`. Ein Marker je Ausgang waere die Reparatur an
        der Instanz — der naechste neue Ausgang haette ihn wieder nicht."""
        quelle = (Path(__file__).resolve().parents[1] / "auto_wm_poly_trigger.py").read_text(
            encoding="utf-8")
        i = quelle.index("def main():")
        block = quelle[i:i + 400]
        self.assertIn("finally:", block)
        self.assertIn("_papier_lauf_schreiben()", block)


if __name__ == "__main__":
    unittest.main()
