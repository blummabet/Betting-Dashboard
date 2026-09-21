"""🔴 21.09.2026 (Lucas: „meine api keys sind abgelaufen hab sie verlängert").

Der the-odds-api-Schlüssel lief am 20.09. abends ab. Einen ganzen Tag lang hat es niemand
gemerkt: die Abrufe liefen weiter — rund 40 je Lauf, alle 15 Minuten, geschätzt 13.000 am Tag —
jede Antwort war leer, und das einzige Symptom war `ankerQuote` von 0,50 auf 0,0. Eine
abgeleitete Zahl, zwei Schritte vom Grund entfernt.

Zwei Fehler steckten darin, und beide sind meine:

1. **Der Schlüssel stand als Rückfall im Code** (`os.environ.get("ODDS_API_KEY") or "16154a…"`,
   in vier Dateien). Lief das Secret leer, griff still der fest verdrahtete — der seit dem
   20.09. tot war. Fehlerklasse: fehlende Information rendert als harmloser Default, und hier
   war der Default zusätzlich ein totes Zugangsdatum.

2. **`oddsKeysFetched` zählte die VERSUCHTEN Keys, nicht die erfolgreichen.** Am Morgen des
   21.09. hatte ich die richtige Vermutung — „der Key ist tot" — und habe sie mit genau dieser
   Zahl widerlegt: „40 Keys geholt, also lebt er". Der Wächter
   `check_consensus_anchor_coverage` trug denselben Fehlschluss im Docstring und zeigte einen
   Tag lang auf das Namens-Matching. Fehlerklasse: ein Zähler, der die Absicht zählt statt den
   Erfolg — und ein Urteil, das darauf gebaut war.

Der Grund stand die ganze Zeit in den Antwort-Headern (`x-requests-used`,
`x-requests-remaining`), die niemand gelesen hat.
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import betfair_data_integrity as B


def _ctx(**consensus):
    return B.BetfairCtx(consensus=consensus) if hasattr(B, "BetfairCtx") else None


class TestKeinToterSchluesselImCode(unittest.TestCase):
    ALT = "16154a94ee84482dcd5a4af88d521d73"

    def test_der_abgelaufene_schluessel_steht_nirgends_mehr(self):
        """Ein Zugangsdatum im Quelltext ist ein Rückfall, den niemand widerruft."""
        treffer = []
        for muster in ("*.py", "*.js"):
            for f in BASE.glob(muster):
                if self.ALT in f.read_text(encoding="utf-8", errors="ignore"):
                    treffer.append(f.name)
        self.assertEqual(sorted(treffer), [], "toter Key noch im Code: %s" % treffer)

    def test_kein_modul_baut_einen_odds_key_aus_dem_nichts(self):
        """Die Klasse, nicht die Instanz: ein `or "…"` hinter ODDS_API_KEY ist immer falsch."""
        import re
        rx = re.compile(r'ODDS_API_KEY[^\n]*?(?:or|,)\s*[\'"][0-9a-f]{16,}[\'"]')
        schuldig = [f.name for muster in ("*.py", "*.js") for f in BASE.glob(muster)
                    if rx.search(f.read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(sorted(schuldig), [],
                         "Modul mit fest verdrahtetem Odds-Key: %s" % schuldig)


class TestDerZaehlerZaehltDenErfolg(unittest.TestCase):
    def test_versucht_ist_nicht_gelungen(self):
        """Der Kern des Vorfalls: 40 Versuche, 0 Treffer — und der alte Zaehler sagte 40."""
        c = B.check_odds_zugang_lebt(_ctx(oddsKeysFetched=40, oddsKeysMitDaten=0,
                                          oddsKontingent={"used": 1, "remaining": 400,
                                                          "letzterFehler": None}))
        self.assertFalse(c["ok"])
        self.assertIn("KEINER hat Daten geliefert", " ".join(c["failures"]))

    def test_ein_http_fehler_wird_beim_namen_genannt(self):
        c = B.check_odds_zugang_lebt(_ctx(oddsKeysFetched=40, oddsKeysMitDaten=0,
                                          oddsKontingent={"letzterFehler": "HTTP 401"}))
        self.assertFalse(c["ok"])
        self.assertIn("HTTP 401", " ".join(c["failures"]))

    def test_leeres_kontingent_ist_ein_eigener_befund(self):
        c = B.check_odds_zugang_lebt(_ctx(oddsKeysFetched=40, oddsKeysMitDaten=40,
                                          oddsKontingent={"used": 500000, "remaining": 0}))
        self.assertFalse(c["ok"])
        self.assertIn("Kontingent", " ".join(c["failures"]))

    def test_ein_gesunder_lauf_ist_still(self):
        c = B.check_odds_zugang_lebt(_ctx(oddsKeysFetched=42, oddsKeysMitDaten=38,
                                          oddsKontingent={"used": 1200, "remaining": 380000,
                                                          "letzterFehler": None}))
        self.assertTrue(c["ok"], c["failures"])
        self.assertIn("380000", c["note"])

    def test_ohne_kontingent_feld_behauptet_er_nichts(self):
        """Ein alter Produzent ist eine eigene Auskunft, kein gruenes Haekchen."""
        c = B.check_odds_zugang_lebt(_ctx(oddsKeysFetched=40))
        self.assertTrue(c["ok"])
        self.assertIn("keine Aussage", c["note"])

    def test_er_ist_registriert(self):
        self.assertIn("check_odds_zugang_lebt", [f.__name__ for f in B.BETFAIR_CHECKS])


class TestDieZaehlungSelbst(unittest.TestCase):
    """Die Zahl wird dort gepruefte, wo sie entsteht — nicht erst beim Leser."""

    def test_leere_listen_zaehlen_nicht_als_erfolg(self):
        import betfair_consensus as C
        z = C.zaehle_keys({f"k{i}": [] for i in range(40)})
        self.assertEqual((z["versucht"], z["mitDaten"], z["events"]), (40, 0, 0),
                         "genau der Lauf vom 21.09.: 40 versucht, nichts bekommen")

    def test_gemischt_wird_richtig_getrennt(self):
        import betfair_consensus as C
        z = C.zaehle_keys({"a": [1, 2], "b": [], "c": [3]})
        self.assertEqual((z["versucht"], z["mitDaten"], z["events"]), (3, 2, 3))

    def test_nichts_ist_nichts(self):
        import betfair_consensus as C
        self.assertEqual(C.zaehle_keys({})["mitDaten"], 0)
        self.assertEqual(C.zaehle_keys(None)["versucht"], 0)


class TestDerAnkerWaechterZeigtNichtMehrAufsMatching(unittest.TestCase):
    """🔴 Er tat es einen Tag lang, weil er `oddsKeysFetched > 0` als „Key lebt" las."""

    def _anker(self, **kw):
        spiele = [{"league": lg, "verdict": "no_anchor"} for lg in
                  list(__import__("betfair_consensus").LEAGUE_ODDS_KEY)[:12]]
        return B.check_consensus_anchor_coverage(
            _ctx(games=spiele, covered=0, ankerN=len(spiele), **kw))

    def test_bei_totem_zugang_nennt_er_den_zugang(self):
        c = self._anker(oddsKeysFetched=40, oddsKeysMitDaten=0,
                        oddsKontingent={"letzterFehler": "HTTP 401"})
        t = " ".join(c["failures"])
        self.assertIn("HTTP 401", t)
        self.assertNotIn("Namens-Matching oder die Liga-Zuordnung", t)

    def test_auch_ohne_http_fehler_erkennt_er_den_toten_zugang(self):
        """Der Fall, den mein erster Testsatz uebersehen hat: die API antwortet sauber, liefert
        aber fuer keinen einzigen Key Daten. Ohne diesen Zweig zeigt der Waechter wieder aufs
        Matching — genau der Fehlschluss vom 20.09."""
        c = self._anker(oddsKeysFetched=40, oddsKeysMitDaten=0,
                        oddsKontingent={"letzterFehler": None, "remaining": 1000})
        t = " ".join(c["failures"])
        self.assertIn("kein einziger von 40", t)
        self.assertNotIn("Namens-Matching oder die Liga-Zuordnung", t)

    def test_bei_lebendem_zugang_nennt_er_das_matching(self):
        c = self._anker(oddsKeysFetched=40, oddsKeysMitDaten=38,
                        oddsKontingent={"letzterFehler": None, "remaining": 1000})
        self.assertIn("Namens-Matching", " ".join(c["failures"]))

    def test_ohne_den_neuen_zaehler_behauptet_er_keine_unterscheidung(self):
        """Der alte Stand darf nicht so klingen, als haette er entschieden."""
        c = self._anker(oddsKeysFetched=40)
        t = " ".join(c["failures"])
        self.assertIn("unterscheidet die beiden Ursachen NICHT", t)


if __name__ == "__main__":
    unittest.main()
