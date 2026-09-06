"""Ein fehlender Snapshot heisst „unveraendert", nicht „keine Daten" — 06.09.2026.

`lead_lag_bias` und `steam_lag` suchten beide den ersten Snapshot INNERHALB des
Rueckblick-Fensters. Unsere Zeitreihe wird aber nur fortgeschrieben, wenn sich der Preis
AENDERT (`fetch_liga_odds.append_snapshot`). Ein Markt, der zwei Tage ruhig steht und dann
kippt, hat im 24-Stunden-Fenster genau EINEN Eintrag — den neuen — und beide Signale gaben auf.

Zurueckgerechnet ueber die gesamte Liga-Odds-History:

    Moves >= 2 pp, die die alte Fensterlogik sah:  1.032
    Moves >= 2 pp, die die neue Logik sieht:       1.320   (+288, +28 %)

Das trifft `lead_lag_bias` — das Signal mit dem staerksten gemessenen CLV-Zusammenhang
(r = +0,495) — genauso wie `steam_lag`. 60 von 279 Liga-Picks scheiterten am 06.09. genau hier.
"""
import unittest
from datetime import datetime, timedelta, timezone

from sharp_signals.base import snapshot_am_fensteranfang as anfang

JETZT = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
H24 = 24 * 3600


def _s(stunden_her, marke):
    return {"ts": (JETZT - timedelta(hours=stunden_her)).isoformat().replace("+00:00", "Z"),
            "marke": marke}


class TestFensteranfang(unittest.TestCase):
    def test_der_ruhige_markt_der_dann_kippt(self):
        """Der Kern des Fehlers. Alter Stand vor 60 h, dann eine Bewegung vor 2 h.
        Die alte Logik sah nur die Bewegung selbst und hatte nichts zum Vergleichen."""
        snaps = [_s(60, "alt"), _s(2, "neu")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "alt")

    def test_letzter_vor_der_grenze_gewinnt(self):
        snaps = [_s(72, "ganz alt"), _s(30, "richtig"), _s(20, "im Fenster"), _s(1, "neu")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "richtig")

    def test_reihe_beginnt_erst_im_fenster(self):
        """Kein Snapshot vor der Grenze — dann ist der erste im Fenster der Startpunkt."""
        snaps = [_s(10, "erster"), _s(3, "zweiter")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "erster")

    def test_alles_aelter_als_das_fenster(self):
        """Ein Markt, der seit Tagen still steht: Bezugspunkt ist der letzte bekannte Preis —
        und der ist zugleich der neueste. Der Aufrufer erkennt daran „keine Bewegung"."""
        snaps = [_s(100, "a"), _s(80, "b")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "b")

    def test_zukunft_wird_nicht_als_basis_genommen(self):
        snaps = [_s(-5, "zukunft"), _s(2, "neu")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "neu")

    def test_unlesbare_zeitstempel_werden_uebersprungen(self):
        snaps = [{"ts": "kaputt", "marke": "x"}, _s(40, "gut"), _s(1, "neu")]
        self.assertEqual(anfang(snaps, JETZT, H24)["marke"], "gut")

    def test_kaputte_eingaben(self):
        self.assertIsNone(anfang([], JETZT, H24))
        self.assertIsNone(anfang(None, JETZT, H24))
        self.assertIsNone(anfang([_s(1, "x")], None, H24))
        self.assertIsNone(anfang([_s(1, "x")], JETZT, 0))
        self.assertIsNone(anfang([{"ts": None}], JETZT, H24))


class TestGegenDieAlteLogik(unittest.TestCase):
    def test_sieht_mehr_als_das_alte_fenster(self):
        """Direkter Vergleich mit dem, was vorher im Code stand. Wird der Helfer eines Tages
        wieder auf „erster im Fenster" zurueckgedreht, faellt das hier auf."""
        def alt(snaps, bezug, lb):
            for s in snaps:
                t = datetime.fromisoformat(s["ts"].replace("Z", "+00:00"))
                age = (bezug - t).total_seconds()
                if 0 <= age <= lb:
                    return s
            return None

        snaps = [_s(60, "alt"), _s(2, "neu")]
        self.assertIsNotNone(anfang(snaps, JETZT, H24))
        self.assertIs(alt(snaps, JETZT, H24), snaps[1],
                      "die alte Logik fand nur den neuen Preis — nichts zum Vergleichen")
        self.assertIsNot(anfang(snaps, JETZT, H24), snaps[1])


if __name__ == "__main__":
    unittest.main()
