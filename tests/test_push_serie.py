"""tests/test_push_serie.py — 04.09.2026

Lucas: „wenn wir einen Favoriten haben und der hat eine lange Serie zu Hause ungeschlagen, dann
ist es ja okay, den zu pushen. Wenn wir auf den gar keine Serie haben, eher nicht. … aber das
muessten wir alles haben, die Infos."

Hatten wir nicht — und konnten es auch nicht nachholen: liga_streaks.json ist eine Momentaufnahme,
welche Serie ein Team an einem Push-Tag vor drei Wochen hatte, steht nirgends. Der Push-Ledger
schrieb nichts davon mit. Die Frage „tragen Pushs mit Serie besser als ohne?" war unbeantwortbar,
egal wie lange man wartet.

Was hier festgenagelt wird, ist vor allem die EHRLICHKEIT der drei Nicht-Faelle. „Kein
Team-Treffer", „keine Serie" und „Markt nicht abgebildet" sehen im Ledger gleich harmlos aus und
bedeuten beim Auswerten voellig Verschiedenes.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from push_serie import serie_fuer_push


def s(team, typ, laenge, venue="all", zufall=None, markt=None, state="intakt"):
    return {"team": team, "type": typ, "length": laenge, "venue": venue,
            "zufallPct": zufall, "market": markt or typ,
            "continuation": {"state": state}}


MADRID = s("Real Madrid", "win", 6, "A", 1.05, "Sieg-Serie")
STUTTGART = s("Stuttgart", "unbeaten", 5, "H", 16.15, "Ungeschlagen")


class DerNormalfall(unittest.TestCase):
    def test_serie_des_gepushten_teams_wird_gefunden(self):
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Madrid",
                             "home": "Betis", "away": "Real Madrid"}, [MADRID])
        self.assertTrue(r["gefunden"])
        self.assertEqual(r["serie"]["typ"], "win")
        self.assertEqual(r["serie"]["venue"], "A", "Real spielt auswaerts")

    def test_die_seltenere_serie_gewinnt_nicht_die_laengere(self):
        """Seit dem 04.09. ist Seltenheit der Massstab — eine 12er-Trifft-Serie sagt weniger
        als eine 6er-Siegesserie."""
        lang = s("Real Madrid", "unbeaten", 12, "A", 40.0, "Ungeschlagen")
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Madrid",
                             "home": "Betis", "away": "Real Madrid"}, [MADRID, lang])
        self.assertEqual(r["serie"]["laenge"], 6)

    def test_ohne_seltenheitsmass_entscheidet_die_laenge(self):
        a = s("X", "win", 4, "H"); b = s("X", "unbeaten", 9, "H")
        r = serie_fuer_push({"market": "Match Odds", "leadName": "X", "home": "X", "away": "Y"}, [a, b])
        self.assertEqual(r["serie"]["laenge"], 9)


class DieDreiNichtFaelle(unittest.TestCase):
    """Der Kern. Alle drei heissen NICHT „keine Serie"."""

    def test_kein_team_treffer_ist_nicht_keine_serie(self):
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Al Ain",
                             "home": "Al Ain", "away": "Al Shamal"}, [MADRID])
        self.assertFalse(r["gefunden"])
        self.assertEqual(r["grund"], "kein Team-Treffer")

    def test_team_erkannt_aber_ohne_passende_serie(self):
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Stuttgart",
                             "home": "Stuttgart", "away": "Koeln"},
                            [s("Stuttgart", "cards", 5, "H")])
        self.assertFalse(r["gefunden"])
        self.assertEqual(r["grund"], "keine Serie")

    def test_nicht_abgebildeter_markt_gibt_None(self):
        self.assertIsNone(serie_fuer_push(
            {"market": "Correct Score", "leadName": "2 - 1", "home": "A", "away": "B"}, [MADRID]))


class DieSerieMussPassen(unittest.TestCase):
    def test_serie_der_anderen_haelfte_zaehlt_nicht(self):
        """Derselbe Fehler stand am 04.09. in der Card-Serien-Box: eine Heim-Serie sagt
        ueber ein Auswaertsspiel nichts."""
        heim = s("Real Madrid", "win", 9, "H", 0.5, "Sieg-Serie")
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Madrid",
                             "home": "Betis", "away": "Real Madrid"}, [heim])
        self.assertFalse(r["gefunden"], "Real spielt auswaerts — die Heim-Serie gilt hier nicht")

    def test_gesamt_serie_gilt_auf_beiden_haelften(self):
        ges = s("Real Madrid", "win", 5, "all", 2.0, "Sieg-Serie")
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Madrid",
                             "home": "Betis", "away": "Real Madrid"}, [ges])
        self.assertTrue(r["gefunden"])

    def test_falscher_serientyp_zaehlt_nicht(self):
        """Bei „Match Odds → Real" ist die Ueber-2,5-Serie des Gegners irrelevant."""
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Madrid",
                             "home": "Betis", "away": "Real Madrid"},
                            [s("Real Madrid", "over25", 8, "A", 0.1)])
        self.assertEqual(r["grund"], "keine Serie")

    def test_totals_schauen_auf_beide_mannschaften(self):
        r = serie_fuer_push({"market": "Over/Under 2.5 Goals", "leadName": "Over 2.5 Goals",
                             "home": "Ipswich", "away": "Liverpool"},
                            [s("Ipswich", "over25", 5, "H", 8.3, "Über 2,5 Tore")])
        self.assertTrue(r["gefunden"])
        self.assertEqual(r["serie"]["typ"], "over25")

    def test_unter_pick_nimmt_die_unter_serie(self):
        r = serie_fuer_push({"market": "Over/Under 2.5 Goals", "leadName": "Under 2.5 Goals",
                             "home": "A", "away": "B"},
                            [s("A", "over25", 9, "H", 0.1), s("A", "under25", 3, "H", 20.0)])
        self.assertEqual(r["serie"]["typ"], "under25")


class Robustheit(unittest.TestCase):
    def test_leere_serienliste_kippt_nicht(self):
        r = serie_fuer_push({"market": "Match Odds", "leadName": "X", "home": "X", "away": "Y"}, [])
        self.assertFalse(r["gefunden"])

    def test_none_serienliste_kippt_nicht(self):
        self.assertFalse(serie_fuer_push(
            {"market": "Match Odds", "leadName": "X", "home": "X", "away": "Y"}, None)["gefunden"])

    def test_leerer_alert_kippt_nicht(self):
        self.assertIsNone(serie_fuer_push({}, [MADRID]))

    def test_die_bruecke_bleibt_eng(self):
        """Real Madrid und Real Sociedad duerfen nie verwechselt werden — die Namensbruecke
        haelt „Real"/„Real" bewusst draussen."""
        r = serie_fuer_push({"market": "Match Odds", "leadName": "Real Sociedad",
                             "home": "Betis", "away": "Real Sociedad"}, [MADRID])
        self.assertFalse(r["gefunden"])
