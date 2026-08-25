#!/usr/bin/env python3
"""test_eventpage_money_blocks.py — Poly- und Betfair-Block der Event-Pages (25.08.2026, Lucas).

Lucas: „dort sollte ja Polymarket und Betfair Block drin sein — seh aber immer noch keinen."
Die Bloecke waren gebaut, aber leer. Zwei Ursachen, beide hier festgepinnt:

  1. **Betfair** haengt an einem EXAKTEN Namens-Schluessel. „Real Betis" vs Feed „Betis" und
     „Athletic Club" vs Feed „Athletic Bilbao" fielen durch — 1 von 4 Spielen im Feed-Fenster hatte
     den Block. Die Bruecke muss diese Faelle fangen und trotzdem „Manchester United" nie mit
     „Manchester City" verwechseln.
  2. **Poly** las money_map.json (verlangt einen Betfair<->Poly-Doppeltreffer → aktuell 2 Zeilen).
     poly_money_upcoming.json fuehrt dieselben Spiele bis 48h vor Anpfiff.
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import generate_wm_match_pages as G


def _m(home, away, kickoff, league="Spanish La Liga", vol=50000, odds=None):
    od = odds or {"hw": 2.0, "dr": 3.4, "aw": 3.6}
    return {"home": home, "away": away, "kickoff": kickoff, "league": league, "mo": od,
            "markets": {"Match Odds": {"runners": [
                {"name": home, "vol": vol * 0.5, "odd": od["hw"]},
                {"name": "The Draw", "vol": vol * 0.2, "odd": od["dr"]},
                {"name": away, "vol": vol * 0.3, "odd": od["aw"]}]}}}


def _index(matches):
    snaps, fuzzy = {}, {}
    for m in matches:
        snaps[G._bf_event_key(m["home"], m["away"])] = m
        fuzzy.setdefault(str(m["kickoff"])[:10], []).append(m)
    return snaps, fuzzy


class TestNameBridge(unittest.TestCase):
    def test_identisch_und_enthalten(self):
        self.assertTrue(G._bf_compatible("Valencia", "Valencia"))
        self.assertTrue(G._bf_compatible("Real Betis", "Betis"))
        self.assertTrue(G._bf_compatible("Betis", "Real Betis"))

    def test_gemeinsames_markantes_wort(self):
        # Enthalten sich NICHT — teilen aber „Athletic".
        self.assertTrue(G._bf_compatible("Athletic Club", "Athletic Bilbao"))

    def test_kurze_gemeinsame_woerter_bruecken_nicht(self):
        # „Real" ist 4 Zeichen → unter der Schwelle. Sonst waeren Madrid und Sociedad dasselbe Team.
        self.assertFalse(G._bf_compatible("Real Madrid", "Real Sociedad"))

    def test_stadtnamen_bruecken_nicht(self):
        # Der gefaehrlichste Fall: gleiche Stadt, anderer Verein.
        self.assertFalse(G._bf_compatible("Manchester United", "Manchester City"))
        self.assertFalse(G._bf_compatible("Sheffield United", "Sheffield Wednesday"))

    def test_leer_und_muell(self):
        for a, b in ((None, "X"), ("", "X"), ("X", None), ("A", "B")):
            self.assertFalse(G._bf_compatible(a, b))


class TestBetfairFind(unittest.TestCase):
    def setUp(self):
        self.snaps, self.fuzzy = _index([
            _m("Valencia", "Betis", "2026-08-25T19:00:00Z"),
            _m("Barcelona", "Athletic Bilbao", "2026-08-27T19:00:00Z"),
        ])

    def test_exakt_zuerst(self):
        m = G._bf_find(self.snaps, self.fuzzy, "Valencia", "Betis", "2026-08-25")
        self.assertEqual(m["away"], "Betis")

    def test_bruecke_faengt_die_schreibweise(self):
        m = G._bf_find(self.snaps, self.fuzzy, "Valencia", "Real Betis", "2026-08-25")
        self.assertIsNotNone(m)
        m2 = G._bf_find(self.snaps, self.fuzzy, "Barcelona", "Athletic Club", "2026-08-27")
        self.assertIsNotNone(m2)

    def test_zeitzone_ein_tag_daneben(self):
        # Anpfiff 21:00 Ortszeit kann im Feed auf den Folgetag fallen.
        self.assertIsNotNone(G._bf_find(self.snaps, self.fuzzy, "Valencia", "Real Betis", "2026-08-24"))
        self.assertIsNone(G._bf_find(self.snaps, self.fuzzy, "Valencia", "Real Betis", "2026-08-22"))

    def test_falscher_gegner_kein_treffer(self):
        self.assertIsNone(G._bf_find(self.snaps, self.fuzzy, "Valencia", "Sevilla", "2026-08-25"))

    def test_mehrdeutig_lieber_nichts(self):
        # Zwei Kandidaten am selben Tag, die beide bruecken → kein Block statt der falsche.
        snaps, fuzzy = _index([
            _m("Barcelona", "Athletic Bilbao", "2026-08-27T19:00:00Z"),
            _m("Barcelona B", "Athletic Bilbao B", "2026-08-27T15:00:00Z"),
        ])
        self.assertIsNone(G._bf_find(snaps, fuzzy, "Barcelona", "Athletic Club", "2026-08-27"))

    def test_ohne_index_kein_absturz(self):
        self.assertIsNone(G._bf_find({}, None, "A", "B", "2026-08-25"))
        self.assertIsNone(G._bf_find(self.snaps, self.fuzzy, "Valencia", "Real Betis", None))


class TestOutcomeSlot(unittest.TestCase):
    def test_zuordnung(self):
        f = G._broad_outcome_slot
        self.assertEqual(f("Valencia CF", "Valencia", "Real Betis"), "home")
        self.assertEqual(f("Real Betis Balompié", "Valencia", "Real Betis"), "away")
        self.assertEqual(f("Draw (Valencia CF vs. Real Betis)", "Valencia", "Real Betis"), "draw")
        self.assertIsNone(f("Over", "Valencia", "Real Betis"))
        self.assertIsNone(f("", "Valencia", "Real Betis"))


class TestPolyUpcoming(unittest.TestCase):
    def setUp(self):
        G._UPCOMING_CACHE["r"] = {
            "lal-val-bet-2026-08-25": {
                "league": "LA-LIGA", "totalUsd": 12488,
                "prices": {"Valencia CF": 0.30, "Draw (Valencia CF vs. Real Betis)": 0.28,
                           "Real Betis Balompié": 0.42}},
            # Zusatzmarkt mit denselben Teamnamen — darf NICHT als Kandidat zaehlen.
            "lal-val-bet-2026-08-25-more-markets": {
                "league": "LA-LIGA", "totalUsd": 999999,
                "prices": {"Valencia CF": 0.9, "Real Betis Balompié": 0.1}},
        }

    def tearDown(self):
        G._UPCOMING_CACHE.clear()

    def test_favorit_und_volumen(self):
        pm = G.poly_upcoming_money("Valencia", "Real Betis")
        self.assertEqual(pm["favSide"], "away")
        self.assertEqual(pm["favTeam"], "Real Betis")
        self.assertEqual(pm["sharePct"], 42)      # de-viggt: 0.42 / 1.00
        self.assertEqual(pm["usd"], 12488)        # NICHT der Zusatzmarkt mit $999.999

    def test_cross_check_gegen_den_betfair_FAVORITEN(self):
        # Betfair-Geld liegt zu 60% auf dem Remis, Favorit ist per Quote aber die Auswaerts-Seite.
        # „Uneinig" darf hier NICHT stehen — das war der Fehlalarm bei Valencia–Betis.
        bf = {"mo": {"odds": {"home": 3.0, "draw": 3.4, "away": 2.7},
                     "shares": {"home": {"share": 0.10}, "draw": {"share": 0.60}, "away": {"share": 0.30}}}}
        pm = G.poly_upcoming_money("Valencia", "Real Betis", bf)
        self.assertIs(pm["betfairAgree"], True)
        self.assertEqual(pm["betfairPct"], 30)

    def test_echte_uneinigkeit_wird_gemeldet(self):
        bf = {"mo": {"odds": {"home": 1.5, "draw": 4.0, "away": 6.0},
                     "shares": {"home": {"share": 0.80}}}}
        self.assertIs(G.poly_upcoming_money("Valencia", "Real Betis", bf)["betfairAgree"], False)

    def test_ohne_betfair_kein_urteil(self):
        self.assertIsNone(G.poly_upcoming_money("Valencia", "Real Betis")["betfairAgree"])

    def test_unbekanntes_spiel(self):
        self.assertIsNone(G.poly_upcoming_money("Bayern München", "VfB Stuttgart"))


class TestPolyBroadSmartMoney(unittest.TestCase):
    def setUp(self):
        G._BROAD_CACHE["r"] = {
            "lal-val-bet-2026-08-25": {
                "league": "LA-LIGA", "resolved": None,
                "shares": {"Valencia CF": 10000, "Draw (Valencia CF vs. Real Betis)": 5000,
                           "Real Betis Balompié": 35000},
                "whales": [{"wallet": "0xa", "side": "Real Betis Balompié", "usd": 20000},
                           {"wallet": "0xb", "side": "Real Betis Balompié", "usd": 9000},
                           {"wallet": "0xc", "side": "Valencia CF", "usd": 500}]},
        }

    def tearDown(self):
        G._BROAD_CACHE.clear()

    def test_format_passt_zu_renderPoly(self):
        sm = G.poly_broad_smartmoney("Valencia", "Real Betis")
        self.assertEqual(sm["totalUsd"], 50000)
        o = sm["outcomes"]
        self.assertEqual(o["away"]["share"], 0.7)
        self.assertEqual(o["away"]["holders"], 2)
        self.assertAlmostEqual(o["away"]["topHolderShare"], 20000 / 35000, places=3)
        self.assertEqual(sm["topTraders"], 2)     # nur Wallets ab $1.000

    def test_aufgeloeste_maerkte_zaehlen_nicht(self):
        G._BROAD_CACHE["r"]["lal-val-bet-2026-08-25"]["resolved"] = "Real Betis Balompié"
        self.assertIsNone(G.poly_broad_smartmoney("Valencia", "Real Betis"))

    def test_unbekanntes_spiel(self):
        self.assertIsNone(G.poly_broad_smartmoney("Arsenal", "Chelsea"))


if __name__ == "__main__":
    unittest.main()
