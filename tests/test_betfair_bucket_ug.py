"""tests/test_betfair_bucket_ug.py — 04.09.2026

Lucas: „mach ma mal Betfair-Check."

Der Fund war nicht im Radar, sondern im Terminal: `_tMute` blendete Zeilen aus, wenn der
Liga-Bucket `n>=10 && roi<=-0.05` erfuellte. Gemessen an dem Tag:

    Premier League  n10  -11,1%  -> 9 Zeilen gemutet, darunter die drei ueberzeugtesten
    Ligue 1         n10  -21,1%  -> gemutet
    Bundesliga      n 9   -5,6%  -> NICHT gemutet, nur weil n=9 statt 10 war
    La Liga         n14  +13,1%  -> "gruen"
    Serie A         n10  +52,1%  -> "gruen"

Rauschprobe: dieselben Stichprobengroessen zufaellig aus dem gemeinsamen Topf aller 1.652
Match-Odds-Plays gezogen, ergibt in 91% der Laeufe eine MINDESTENS so grosse Spanne zwischen
bester und schlechtester Liga. Der Bucket sortiert Rauschen — und hat damit Man City
(Konviktion 93), PSG (100) und Arsenal (85) vom Board genommen.

Dass das bekannt war, steht seit dem 05.08. im Kopf von `aggregate`: „451 winzige Buckets ->
pro Bucket sagt es fast nichts." Zwoelf Tage spaeter hat das Terminal trotzdem hart darauf
gegatet. Diese Tests halten fest, dass ein Bucket ohne Untergrenze nichts mehr entscheidet.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_track_record as T
from freigabe import UG_MIN_N


def plays(n, odd, wins, league="X", market="Match Odds"):
    """n Plays zur selben Quote, davon `wins` getroffen."""
    return [{"league": league, "market": market, "odd": odd, "win": i < wins,
             "home": "H", "away": "A"} for i in range(n)]


class UntergrenzeAusQuadratsumme(unittest.TestCase):
    def test_unter_der_grenze_gibt_es_keine_zahl(self):
        for n in (1, 5, 10, 14, UG_MIN_N - 1):
            b = T.aggregate(plays(n, 2.0, n // 2))["byLeagueMarket"]["X|Match Odds"]
            self.assertEqual(b["n"], n)
            self.assertIsNotNone(b["roi"], "der Punktschaetzer bleibt sichtbar")
            self.assertIsNone(b["roiUg"], "aber er urteilt nicht (n=%d)" % n)

    def test_ab_der_grenze_gibt_es_eine_zahl_und_sie_liegt_unter_dem_roi(self):
        b = T.aggregate(plays(60, 2.0, 36))["byLeagueMarket"]["X|Match Odds"]
        self.assertIsNotNone(b["roiUg"])
        self.assertLess(b["roiUg"], b["roi"])

    def test_ohne_streuung_gibt_es_keine_untergrenze(self):
        """60 identische Gewinne haben Streuung null — daraus faellt die Schranke auf den
        Mittelwert zusammen. Das ist keine Gewissheit, sondern zu wenig Information; genau
        dieselbe Krankheit wurde am 03.09. in freigabe.untergrenze behandelt."""
        b = T.aggregate(plays(60, 2.0, 60))["byLeagueMarket"]["X|Match Odds"]
        self.assertIsNone(b["roiUg"])

    def test_die_schranke_kommt_aus_denselben_daten_wie_der_roi(self):
        """Quadratsumme statt Werteliste — das Ergebnis muss dasselbe sein."""
        from freigabe import untergrenze
        ps = plays(40, 3.0, 15)
        renditen = [(p["odd"] - 1) if p["win"] else -1.0 for p in ps]
        b = T.aggregate(ps)["byLeagueMarket"]["X|Match Odds"]
        self.assertAlmostEqual(b["roiUg"], round(untergrenze(renditen), 4), places=3)

    def test_jeder_bucket_traegt_die_grenze_die_er_verlangt(self):
        b = T.aggregate(plays(5, 2.0, 3))["byLeagueMarket"]["X|Match Odds"]
        self.assertEqual(b["ugAb"], UG_MIN_N, "damit die Anzeige sagen kann, ab wann es ein Urteil gibt")


class DerRealeFall(unittest.TestCase):
    def test_die_fuenf_ligen_des_boards_tragen_kein_urteil(self):
        """Alle fuenf lagen zwischen n=9 und n=14 — keine bekommt eine Untergrenze, also darf
        keine etwas ausblenden und keine „gruen" heissen."""
        for n, odd, wins in ((10, 1.9, 4), (10, 2.2, 3), (9, 1.8, 4), (14, 2.0, 8), (10, 2.5, 6)):
            b = T.aggregate(plays(n, odd, wins))["byLeagueMarket"]["X|Match Odds"]
            self.assertIsNone(b["roiUg"], "n=%d" % n)

    def test_die_knife_edge_bei_n_gleich_zehn_ist_weg(self):
        """Vorher entschied ein einziger abgerechneter Play daruber, ob eine ganze Liga vom
        Board faellt: bei n=9 blieb sie, bei n=10 mit demselben ROI verschwand sie."""
        neun = T.aggregate(plays(9, 1.8, 4))["byLeagueMarket"]["X|Match Odds"]
        zehn = T.aggregate(plays(10, 1.8, 4))["byLeagueMarket"]["X|Match Odds"]
        self.assertIsNone(neun["roiUg"])
        self.assertIsNone(zehn["roiUg"])

    def test_das_globale_rollup_traegt_sehr_wohl_ein_urteil(self):
        """Der Punkt ist nicht, dass nichts messbar waere — ueber alle Ligen zusammen ist es das.
        Nur je Liga eben nicht."""
        b = T.aggregate(plays(400, 2.0, 210, league="A") + plays(400, 2.0, 190, league="B"))
        self.assertIsNotNone(b["global"]["roiUg"])
        self.assertIsNotNone(b["byMarket"]["Match Odds"]["roiUg"])
