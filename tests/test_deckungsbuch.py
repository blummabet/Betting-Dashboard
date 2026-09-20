"""🔴 20.09.2026 — eine Lücke, die anpfeift, verschwindet aus der Messung.

Die Batterie meldete: „sea-mil-lec-2026-09-20 (AC Milan v US Lecce, Anpfiff in 0.1h) — der
Liga-Fetcher hat den Markt, der Money-Scan nie". Zwanzig Minuten später war die Messung leer:
`luecken()` nimmt nur Märkte mit `0 < htk <= fenster_h`, und mit dem Anpfiff fällt die Lücke aus
dem Fenster. Auf „passiert das oft?" gab es deshalb nie eine Zahl — nur „gerade keine".

Fehlerklasse: eine Lücke, die sich durch Zeitablauf selbst erledigt, hinterlässt keine Statistik.
Dieselbe Klasse wie beim ausgebliebenen Verkaufsversuch: eine Wirkung, die ausbleibt, hinterlässt
keine Spur.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import poly_deckung as PD
import uebersicht_integrity as U

T0 = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


def _l(slug="sea-mil-lec", htk=4.0, vol=1200):
    return {"slug": slug, "home": "AC Milan", "away": "US Lecce", "htk": htk, "vol": vol}


class TestDasBuchHaeltDieLueckeFest(unittest.TestCase):
    def test_eine_luecke_ueberlebt_den_anpfiff(self):
        """Der Vorfall: nach dem Anpfiff liefert `luecken()` nichts mehr — das Buch schon."""
        b = PD.buchen({}, [_l(htk=0.1)], 10, set(), now=T0)
        b = PD.buchen(b, [], 10, set(), now=T0 + timedelta(hours=1))
        self.assertIn("sea-mil-lec", b["slugs"])
        self.assertEqual(b["slugs"]["sea-mil-lec"]["minHtk"], 0.1)

    def test_die_engste_annaeherung_zaehlt_nicht_die_letzte(self):
        """Eine Lücke bei 100h ist ein Fetch-Rückstand, eine bei 0,1h ist ein Spiel, das blind
        zum Geld gesetzt wurde. Die teure Zahl ist das Minimum."""
        b = PD.buchen({}, [_l(htk=90.0)], 10, set(), now=T0)
        b = PD.buchen(b, [_l(htk=0.3)], 10, set(), now=T0 + timedelta(hours=89))
        b = PD.buchen(b, [_l(htk=0.9)], 10, set(), now=T0 + timedelta(hours=89.5))
        self.assertEqual(b["slugs"]["sea-mil-lec"]["minHtk"], 0.3)

    def test_jeder_lauf_bringt_seinen_nenner_mit(self):
        """„3 Lücken" ohne die Zahl der Märkte ist keine Auskunft — dieselbe Klasse wie ein
        Prozentsatz ohne seinen Nenner."""
        b = PD.buchen({}, [_l()], 17, set(), now=T0)
        self.assertEqual(b["laeufe"][-1]["nLigaMaerkte"], 17)
        self.assertEqual(b["laeufe"][-1]["nLuecken"], 1)

    def test_nachgeholt_statt_geloescht(self):
        """„Spät gesehen" und „nie gesehen" sind zwei verschiedene Befunde."""
        b = PD.buchen({}, [_l(htk=40.0)], 10, set(), now=T0)
        b = PD.buchen(b, [], 10, {"sea-mil-lec"}, now=T0 + timedelta(hours=2))
        z = b["slugs"]["sea-mil-lec"]
        self.assertTrue(z["nachgeholt"])
        self.assertIn("nachgeholtAt", z)

    def test_das_buch_waechst_nicht_unbegrenzt(self):
        b = {}
        for i in range(30):
            b = PD.buchen(b, [_l(slug="s%03d" % i)], 10, set(),
                          now=T0 + timedelta(minutes=i), keep_laeufe=10, keep_slugs=12)
        self.assertEqual(len(b["laeufe"]), 10)
        self.assertEqual(len(b["slugs"]), 12)

    def test_die_juengsten_slugs_ueberleben_das_kappen(self):
        b = {}
        for i in range(20):
            b = PD.buchen(b, [_l(slug="s%03d" % i)], 10, set(),
                          now=T0 + timedelta(minutes=i), keep_slugs=5)
        self.assertIn("s019", b["slugs"], "der juengste Fund darf nicht wegfallen")
        self.assertNotIn("s000", b["slugs"])


class TestDieBilanzHatEinenNenner(unittest.TestCase):
    def test_ohne_laeufe_kein_urteil_und_keine_null(self):
        b = PD.bilanz({})
        self.assertIsNone(b['quotePct'], '0 % hiesse „gemessen und dicht“, und das ist es nicht')
        self.assertEqual(b["urteil"], "nicht belegt")

    def test_wenige_laeufe_bleiben_unbelegt(self):
        b = {}
        for i in range(5):
            b = PD.buchen(b, [], 10, set(), now=T0 + timedelta(minutes=i))
        self.assertEqual(PD.bilanz(b)["urteil"], "nicht belegt")

    def test_genug_laeufe_ohne_luecke_heisst_dicht(self):
        b = {}
        for i in range(25):
            b = PD.buchen(b, [], 10, set(), now=T0 + timedelta(minutes=i))
        bi = PD.bilanz(b)
        self.assertEqual(bi["urteil"], "Deckung dicht")
        self.assertEqual(bi["quotePct"], 0)

    def test_genug_laeufe_mit_luecken_heisst_loecher(self):
        b = {}
        for i in range(25):
            b = PD.buchen(b, [_l()] if i % 5 == 0 else [], 10, set(),
                          now=T0 + timedelta(minutes=i))
        bi = PD.bilanz(b)
        self.assertEqual(bi["urteil"], "Deckung hat Loecher")
        self.assertEqual(bi["quotePct"], 20)


class TestDerGuardLiestDasBuch(unittest.TestCase):
    def _ctx(self, buch):
        return {"ligaPoly": {"prices": {"x": {"slug": "a", "kickoff": None}}},
                "polyClose": {"a": 1}, "polyDeckungBuch": buch}

    def test_ein_bis_zum_anpfiff_nie_erfasster_markt_wird_gemeldet(self):
        b = PD.buchen({}, [_l(htk=0.1)], 10, set(), now=T0)
        c = U.check_poly_deckung(self._ctx(b))
        text = " ".join(c["failures"])
        self.assertIn("bis zum Anpfiff nie erfasst", text)
        self.assertIn("blind zum Geld", text)

    def test_nachgeholte_luecken_melden_als_quote_nicht_als_stoerung(self):
        b = PD.buchen({}, [_l(htk=40.0)], 10, set(), now=T0)
        b = PD.buchen(b, [], 10, {"sea-mil-lec"}, now=T0 + timedelta(hours=1))
        c = U.check_poly_deckung(self._ctx(b))
        text = " ".join(c["failures"])
        self.assertIn("nachgeholt", text)
        self.assertNotIn("blind zum Geld", text)

    def test_ein_leeres_buch_meldet_nichts(self):
        self.assertEqual(U.check_poly_deckung(self._ctx({}))["nFail"], 0)


class TestDerScannerSchreibtDasBuchUeberhaupt(unittest.TestCase):
    def test_der_produzent_kennt_die_datei(self):
        import poly_money_broad as M
        self.assertEqual(M.DECKUNG_FILE, "poly_deckung_buch.json")
        self.assertEqual(M.LIGA_PREISE_FILE, "liga_poly_prices.json")

    def test_ohne_zweite_quelle_gibt_es_keine_gruene_meldung(self):
        """Keine Gegenprobe ist etwas anderes als keine Lücken — das darf nicht als dicht
        durchgehen."""
        q = (Path(__file__).resolve().parents[1] / "poly_money_broad.py").read_text(encoding="utf-8")
        i = q.index("[DECKUNG]")
        block = q[i - 1200:i + 900]
        self.assertIn("keine Deckungsmessung moeglich", block)


if __name__ == "__main__":
    unittest.main()
