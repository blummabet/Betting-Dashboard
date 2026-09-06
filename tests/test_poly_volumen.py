"""Das Poly-Volumen muss dort gelesen werden, wo es steht — 06.09.2026.

Lucas: „wir haben Poly, wir haben Betfair, wir tracken Wallets — und sind mit schlechter
Engine unterwegs." Der Beweis lag in einem Feldnamen.

`polymarket_sharp` und `steam_lag` lasen `poly_snapshot.get("poly_vol", 0) or 0` und gaten auf
5.000 bzw. 3.000 USD. Die Produktion schreibt das Volumen in `*_poly_prices.json → allFixtures`
unter **`vol`**. Von 104 Liga-Fixtures trug KEINE das Feld `poly_vol`; 104 trugen `poly_hw`.
Everton–Manchester United stand mit 7,87 Mio. USD in unserer eigenen Datei.

Folge: beide Signale haben in 318 abgerechneten Picks **nie** gefeuert. Nach dem Fix feuert
`polymarket_sharp` auf dem aktuellen Bestand 6-mal.

Die Tests dazu waren gruen — sie bauten ihre Fixture selbst, mit `poly_vol`. Ein Test, der die
erfundene Form prueft statt der echten, deckt nichts ab. Deshalb prueft dieser Test gegen die
Form, die auf der Platte liegt.
"""
import json
import unittest
from pathlib import Path

from sharp_signals.base import poly_volumen

BASE = Path(__file__).resolve().parents[1]


class TestPolyVolumen(unittest.TestCase):
    def test_liest_das_produktionsfeld_vol(self):
        self.assertEqual(poly_volumen({"vol": 182263.0}), 182263.0)

    def test_liest_auch_den_alten_namen(self):
        self.assertEqual(poly_volumen({"poly_vol": 12000}), 12000.0)

    def test_produktionsfeld_gewinnt(self):
        self.assertEqual(poly_volumen({"vol": 5000, "poly_vol": 1}), 5000.0)

    def test_unbekannt_ist_none_nicht_null(self):
        """Der ganze Fehler in einer Zeile: 0 hiess „kein Geld da", gemeint war „nicht gefragt".
        Ein Signal darf an fehlender Information nicht stumm scheitern, ohne dass es auffaellt."""
        self.assertIsNone(poly_volumen({}))
        self.assertIsNone(poly_volumen({"poly_hw": 0.6}))
        self.assertIsNone(poly_volumen(None))
        self.assertIsNone(poly_volumen("182263"))

    def test_null_bleibt_null(self):
        """Eine gemessene Null ist etwas anderes als eine fehlende Angabe."""
        self.assertEqual(poly_volumen({"vol": 0}), 0.0)

    def test_bool_ist_keine_zahl(self):
        self.assertIsNone(poly_volumen({"vol": True}))


class TestGegenDieEchtenDaten(unittest.TestCase):
    """Kein erfundenes Fixture: gegen die Datei, die die Pipeline wirklich schreibt."""

    def _fixtures(self):
        p = BASE / "liga_poly_prices.json"
        if not p.exists():
            self.skipTest("liga_poly_prices.json nicht vorhanden")
        return json.loads(p.read_text(encoding="utf-8")).get("allFixtures") or []

    def test_die_echte_datei_traegt_ein_lesbares_volumen(self):
        fx = [f for f in self._fixtures() if f.get("poly_hw") is not None]
        if not fx:
            self.skipTest("keine Fixture mit Poly-Preis")
        lesbar = [f for f in fx if poly_volumen(f) is not None]
        self.assertGreater(
            len(lesbar), 0,
            "Kein einziger Poly-Fixture liefert ein lesbares Volumen — genau der Zustand, "
            "in dem polymarket_sharp und steam_lag monatelang stumm waren.")

    def test_das_alte_feld_kommt_in_der_produktion_gar_nicht_vor(self):
        """Haelt fest, WARUM der alte Code nie feuern konnte. Sollte die Pipeline `poly_vol`
        eines Tages wieder schreiben, ist das keine Regression — dieser Test darf dann weg."""
        fx = self._fixtures()
        if not fx:
            self.skipTest("keine Fixtures")
        mit_altem_feld = sum(1 for f in fx if "poly_vol" in f)
        mit_preis = sum(1 for f in fx if f.get("poly_hw") is not None)
        if mit_preis == 0:
            self.skipTest("keine Fixture mit Poly-Preis")
        self.assertEqual(
            mit_altem_feld, 0,
            "Die Produktion schreibt `poly_vol` — dann war der alte Code nicht die Ursache "
            "und der Befund muss neu untersucht werden.")


if __name__ == "__main__":
    unittest.main()
