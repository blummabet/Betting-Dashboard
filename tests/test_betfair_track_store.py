"""Das kompakte Ledger-Format (betfair_track_store.py).

01.09.2026. Der Ledger stand ewig auf 8000 Zeilen, weil RESULTS_KEEP ihn deckelte — sechs Tage
Gedaechtnis. Der Deckel steht jetzt auf 40.000, moeglich nur durch dieses Format. Die Tests hier
haben genau eine Aufgabe: beweisen, dass beim Komprimieren NICHTS still verschwindet. Ein Format,
das leise ein Feld frisst, waere schlimmer als der alte Deckel — der war wenigstens sichtbar.
"""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import betfair_track_store as S

BASE = Path(__file__).resolve().parent.parent


def _ohne_none(z):
    """Die eine dokumentierte Unschaerfe: ein Feld, das ausdruecklich None ist, kommt als
    fehlender Schluessel zurueck. Jeder Leser des Ledgers geht ueber .get() (am 01.09.2026
    geprueft), fuer den ist das dasselbe. Verglichen wird deshalb ohne die None-Felder —
    dass sie fehlen DUERFEN, prueft test_alle_typen_ueberleben ausdruecklich."""
    return {k: v for k, v in z.items() if v is not None}


def _auf_sekunde(z):
    """Der zweite dokumentierte Verlust: Mikrosekunden."""
    z = dict(z)
    s = z.get("settledAt")
    if isinstance(s, str):
        try:
            z["settledAt"] = datetime.fromisoformat(s.replace("Z", "+00:00")).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return z


def _zeile(**kw):
    z = {"league": "Italian Serie C", "market": "Match Odds", "home": "Foggia", "away": "Bari",
         "country": "IT", "fav": "H", "odd": 2.1, "entryOdd": 2.05, "pinnClose": None,
         "pinnFair": None, "clvBf": 2.4, "clvPinn": None, "conc": True, "inflow": False,
         "win": True, "settledAt": "2026-08-30T20:51:02+00:00", "matchId": "1234",
         "ft": [2, 1], "ht": [1, 0], "via": "finished", "dir": "in"}
    z.update(kw)
    return z


class TestRundreise(unittest.TestCase):
    def test_zeile_kommt_unveraendert_zurueck(self):
        z = _zeile()
        self.assertEqual(S.entpacken(S.packen([z]))[0], _ohne_none(z))

    def test_alle_typen_ueberleben(self):
        z = _zeile(odd=1.0, entryOdd=None, pinnClose=1.93, pinnFair=0.52, clvPinn=-3.1,
                   conc=False, inflow=True, win=False, ft=[0, 0], ht=None, dir="flat")
        raus = S.entpacken(S.packen([z]))[0]
        for k, v in z.items():
            if v is None:
                self.assertNotIn(k, raus, f"{k}: None wird zu fehlendem Schluessel (dokumentiert)")
            else:
                self.assertEqual(raus[k], v, k)
                self.assertIs(type(raus[k]), type(v), f"{k} Typ")

    def test_false_ueberlebt_als_false_nicht_als_fehlend(self):
        """Der gefaehrlichste Fehler in einer Bool-Spalte: False und „nicht da" verwechseln.
        conc=False heisst „gemessen, war nicht konzentriert" — ein fehlendes conc hiesse
        „nie geschaut". Die Aggregation zaehlt beides verschieden."""
        raus = S.entpacken(S.packen([_zeile(conc=False, inflow=False, win=False)]))[0]
        for k in ("conc", "inflow", "win"):
            self.assertIn(k, raus)
            self.assertIs(raus[k], False, k)

    def test_unbekanntes_feld_geht_nicht_verloren(self):
        """Wer morgen ein Feld an die Zeile haengt, darf es nicht still verlieren."""
        raus = S.entpacken(S.packen([_zeile(neuesFeld={"a": 1}, nochEins="x")]))[0]
        self.assertEqual(raus["neuesFeld"], {"a": 1})
        self.assertEqual(raus["nochEins"], "x")

    def test_wert_der_nicht_in_seine_spalte_passt_landet_in_rest(self):
        """conc=1 statt True: darf NICHT als True zurueckkommen — lieber unkomprimiert."""
        raus = S.entpacken(S.packen([_zeile(conc=1, league=42)]))[0]
        self.assertEqual(raus["conc"], 1)
        self.assertIs(type(raus["conc"]), int)
        self.assertEqual(raus["league"], 42)

    def test_kaputter_zeitstempel_geht_nicht_verloren(self):
        raus = S.entpacken(S.packen([_zeile(settledAt="gestern")]))[0]
        self.assertEqual(raus["settledAt"], "gestern")

    def test_mikrosekunden_sind_der_einzige_zeitverlust(self):
        raus = S.entpacken(S.packen([_zeile(settledAt="2026-08-30T20:51:02.110295+00:00")]))[0]
        self.assertEqual(raus["settledAt"], "2026-08-30T20:51:02+00:00")


class TestAltformat(unittest.TestCase):
    def test_blanke_liste_wird_weiter_gelesen(self):
        """Der erste Lauf nach dem Deployment liest die alten 8000 Zeilen. Kein Stichtag.
        Beim LESEN des Altformats wird nichts angefasst — auch None-Felder bleiben stehen."""
        alt = [_zeile(), _zeile(matchId="9")]
        self.assertEqual(S.entpacken(alt), alt)

    def test_muell_in_der_liste_fliegt_raus_statt_zu_werfen(self):
        self.assertEqual(len(S.entpacken([_zeile(), None, "x", 5])), 1)


class TestKaputt(unittest.TestCase):
    def test_unlesbares_gibt_leer_statt_zu_werfen(self):
        for x in (None, {}, {"fmt": 1}, {"zeilen": "nope"}, 5, "text"):
            self.assertEqual(S.entpacken(x), [], repr(x))

    def test_fehlende_datei_gibt_leer(self):
        self.assertEqual(S.load(BASE / "gibtsnicht_xyz.json"), [])

    def test_index_ausserhalb_des_woerterbuchs_wird_weggelassen_nicht_geraten(self):
        p = S.packen([_zeile()])
        p["zeilen"][0][0] = 999            # Liga-Index ins Nichts
        raus = S.entpacken(p)[0]
        self.assertNotIn("league", raus)   # lieber fehlend als falsch geraten
        self.assertEqual(raus["market"], "Match Odds")

    def test_zu_kurze_zeile_wirft_nicht(self):
        p = S.packen([_zeile()])
        p["zeilen"][0] = p["zeilen"][0][:4]
        self.assertEqual(S.entpacken(p)[0]["league"], "Italian Serie C")


class TestFenster(unittest.TestCase):
    def test_dauer_wird_gemessen_nicht_geschaetzt(self):
        f = S.fenster([_zeile(settledAt="2026-08-01T00:00:00+00:00"),
                       _zeile(settledAt="2026-08-11T00:00:00+00:00")])
        self.assertEqual((f["n"], f["tage"]), (2, 10.0))

    def test_ohne_zeitstempel_ist_die_dauer_unbekannt_nicht_null(self):
        f = S.fenster([{"league": "X"}])
        self.assertIsNone(f["tage"])
        self.assertEqual(f["n"], 1)

    def test_leer(self):
        self.assertEqual(S.fenster([])["n"], 0)


class TestEchterLedger(unittest.TestCase):
    """Der Beweis am echten Bestand — synthetische Zeilen koennen jede Eigenheit uebersehen."""

    @classmethod
    def setUpClass(cls):
        cls.roh = None
        p = BASE / "betfair_track_results.json"
        try:
            cls.roh = S.load(p)
        except Exception:
            pass

    def test_rundreise_ueber_den_ganzen_ledger(self):
        if not self.roh:
            self.skipTest("kein Ledger auf Platte")
        zurueck = S.entpacken(S.packen(self.roh))
        self.assertEqual(len(zurueck), len(self.roh))
        for a, b in zip(self.roh, zurueck):
            self.assertEqual(_ohne_none(_auf_sekunde(a)), _ohne_none(_auf_sekunde(b)))

    def test_format_ist_deutlich_kompakter(self):
        """Der ganze Zweck. Faellt der Gewinn weg, sind 40.000 Zeilen nicht mehr tragbar."""
        if not self.roh or len(self.roh) < 500:
            self.skipTest("zu wenig Zeilen fuer eine Groessenaussage")
        kompakt = len(json.dumps(S.packen(self.roh), ensure_ascii=False, separators=(",", ":")))
        alt = len(json.dumps(self.roh, ensure_ascii=False, separators=(",", ":")))
        self.assertLess(kompakt / alt, 0.45, f"nur {alt / kompakt:.1f}x kleiner — zu wenig")

    def test_aggregat_bleibt_identisch(self):
        """Das Format darf die Auswertung nicht anfassen — kein Bucket, kein ROI, kein n."""
        if not self.roh:
            self.skipTest("kein Ledger auf Platte")
        import betfair_track_record as T
        a = T.aggregate(self.roh)
        b = T.aggregate(S.entpacken(S.packen(self.roh)))
        for k in ("global", "byMarket", "byLeagueMarket", "byTeamMarket"):
            self.assertEqual(json.dumps(a[k], sort_keys=True), json.dumps(b[k], sort_keys=True), k)


class TestDeckel(unittest.TestCase):
    def test_deckel_haelt_mehr_als_eine_woche(self):
        """Der Befund vom 01.09.: ~1.300 Abrechnungen/Tag. 8000 hielten sechs Tage und deckelten
        damit jeden Liga×Markt-Bucket auf n≈24, waehrend das Lern-Board ab n=15 Signale umdreht."""
        import betfair_track_record as T
        self.assertGreaterEqual(T.RESULTS_KEEP / 1300.0, 21.0,
                                "Deckel deckt weniger als drei Wochen ab")


if __name__ == "__main__":
    unittest.main()
