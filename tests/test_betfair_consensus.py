# tests/test_betfair_consensus.py — Betfair-Konsens (Zweitmeinung), 09.08.2026 (Lucas).
# Testet die reine Logik OHNE Netz: Namens-Match, De-vig, Event-Parse, Geld-Seite, Verdikt, Bewegung.
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_consensus as BC


def bf_match(mid="1", home="Borac Banja Luka", away="Fk Velez Mostar",
             league="Bosnian Premier League", country="BA",
             kickoff="2026-08-09T16:30:00Z", runners=None, live=False):
    mk = runners or [
        {"name": home, "odd": 1.6, "vol": 80000},
        {"name": "The Draw", "odd": 3.8, "vol": 10000},
        {"name": away, "odd": 5.0, "vol": 10000},
    ]
    return {"matchId": mid, "home": home, "away": away, "league": league, "country": country,
            "kickoff": kickoff,
            "liveInfo": {"time": 55 if live else 0, "finished": False},
            "markets": {"Match Odds": {"runners": mk}}}


def odds_event(home="Borac Banja Luka", away="Velez Mostar", ph=1.6, pd=3.8, pa=5.0,
               with_soft=True):
    books = [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
        {"name": home, "price": ph}, {"name": away, "price": pa}, {"name": "Draw", "price": pd}]}]}]
    if with_soft:
        books.append({"key": "bet365", "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": ph * 0.98}, {"name": away, "price": pa * 0.98},
            {"name": "Draw", "price": pd * 0.98}]}]})
    return {"home_team": home, "away_team": away, "commence_time": "2026-08-09T16:30:00Z",
            "bookmakers": books}


class TestNameMatch(unittest.TestCase):
    def test_legal_forms_stripped(self):
        self.assertEqual(BC._name_score("Fk Velez Mostar", "Velez Mostar"), 1.0)
        self.assertEqual(BC._name_score("OGC Nice", "Nice"), 1.0)
        self.assertEqual(BC._name_score("SSC Napoli", "Napoli"), 1.0)
        self.assertEqual(BC._name_score("Como 1907", "Como"), 1.0)      # Zahl faellt weg
        self.assertEqual(BC._name_score("RCD Espanyol de Barcelona", "Espanyol Barcelona"), 1.0)

    def test_distinguishing_words_kept(self):
        # „United" vs „City" duerfen NICHT kollabieren
        self.assertLess(BC._name_score("Manchester United", "Manchester City"), 1.0)
        self.assertEqual(BC._name_score("Manchester United", "Manchester United"), 1.0)

    def test_no_shared_token_zero(self):
        self.assertEqual(BC._name_score("Arsenal", "Chelsea"), 0.0)


class TestDevig(unittest.TestCase):
    def test_sums_to_one_and_favorite(self):
        p = BC._devig3(1.6, 3.8, 5.0)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(sum(p), 1.0, places=6)
        self.assertEqual(BC._fav(p), "home")          # 1.6 = klarer Heim-Favorit
        self.assertGreater(p[0], p[2])

    def test_bad_input(self):
        self.assertIsNone(BC._devig3(0, 3.8, 5.0))
        self.assertIsNone(BC._devig3(None, 2, 2))


class TestParseEvent(unittest.TestCase):
    def test_pinnacle_and_soft(self):
        pe = BC.parse_event(odds_event())
        self.assertIsNotNone(pe["pinn"])
        self.assertIsNotNone(pe["soft"])
        self.assertEqual(pe["nSoft"], 1)
        self.assertAlmostEqual(sum(pe["pinn"]), 1.0, places=6)
        self.assertEqual(BC._fav(pe["pinn"]), "home")

    def test_no_pinnacle_only_soft(self):
        ev = odds_event(with_soft=True)
        ev["bookmakers"] = [ev["bookmakers"][1]]   # nur bet365
        pe = BC.parse_event(ev)
        self.assertIsNone(pe["pinn"])
        self.assertIsNotNone(pe["soft"])


class TestMatchEvent(unittest.TestCase):
    def test_direct_match(self):
        m = bf_match()
        ev = BC.parse_event(odds_event())
        got = BC.match_event(m, [ev])
        self.assertIsNotNone(got)
        self.assertEqual(BC._fav(got["pinn"]), "home")   # Borac (Heim) vorn

    def test_flip_when_home_away_swapped(self):
        # Odds-Quelle listet Velez als Heim -> muss gedreht werden, Probs neu orientiert
        m = bf_match()
        ev = BC.parse_event(odds_event(home="Velez Mostar", away="Borac Banja Luka",
                                       ph=5.0, pd=3.8, pa=1.6))
        got = BC.match_event(m, [ev])
        self.assertIsNotNone(got)
        # nach Flip zeigt „home" (Borac) mit Quote 1.6 vorn
        self.assertEqual(BC._fav(got["pinn"]), "home")

    def test_no_match_other_teams(self):
        m = bf_match()
        ev = BC.parse_event(odds_event(home="Arsenal", away="Chelsea"))
        self.assertIsNone(BC.match_event(m, [ev]))


class TestMoneySide(unittest.TestCase):
    def test_lead_runner_home(self):
        ms = BC.money_side(bf_match())
        self.assertEqual(ms["side"], "home")
        self.assertAlmostEqual(ms["share"], 0.8, places=3)

    def test_draw_lead(self):
        m = bf_match(runners=[
            {"name": "Borac Banja Luka", "odd": 2.5, "vol": 10000},
            {"name": "The Draw", "odd": 3.0, "vol": 60000},
            {"name": "Fk Velez Mostar", "odd": 3.2, "vol": 10000}])
        self.assertEqual(BC.money_side(m)["side"], "draw")


class TestBuildGame(unittest.TestCase):
    def test_konsens(self):
        m = bf_match()                       # Geld auf Borac (Heim)
        ev = BC.parse_event(odds_event())    # Pinnacle+Soft sehen Borac vorn
        g = BC.build_game(m, ev, None, {})
        self.assertEqual(g["verdict"], "konsens")
        self.assertTrue(g["agree"])
        self.assertEqual(g["moneySide"], "home")
        self.assertEqual(g["pinn"]["fav"], "home")

    def test_uneinig(self):
        # Geld auf Borac (Heim), aber Buchmacher sehen Velez (Auswaerts) vorn
        m = bf_match()
        ev = BC.parse_event(odds_event(ph=5.0, pd=3.8, pa=1.6))
        g = BC.build_game(m, ev, None, {})
        self.assertEqual(g["verdict"], "uneinig")
        self.assertFalse(g["agree"])

    def test_no_anchor(self):
        g = BC.build_game(bf_match(), None, None, {})
        self.assertEqual(g["verdict"], "no_anchor")
        self.assertIsNone(g["pinn"])
        self.assertIsNone(g["agree"])

    def test_movement_pp(self):
        m = bf_match()
        ev = BC.parse_event(odds_event())
        pinn_now = ev["pinn"]                     # home-Prob aktuell
        prev = {"pinn": [pinn_now[0] - 0.05, pinn_now[1], pinn_now[2]]}   # war 5pp niedriger
        g = BC.build_game(m, ev, prev, {})
        self.assertAlmostEqual(g["pinnMovePP"], 5.0, places=1)   # Pinnacle zog +5pp auf die Geld-Seite

    def test_direction_from_direction_file(self):
        m = bf_match()
        direction = {"1": {"Match Odds": {"Borac Banja Luka": {"dir": "in"}}}}
        g = BC.build_game(m, BC.parse_event(odds_event()), None, direction)
        self.assertEqual(g["moneyDir"], "in")


class TestOddsCarry(unittest.TestCase):
    def test_parse_event_keeps_raw_odds(self):
        pe = BC.parse_event(odds_event(ph=1.6, pd=3.8, pa=5.0))
        self.assertEqual(pe["pinnOdds"], [1.6, 3.8, 5.0])
        self.assertIsNotNone(pe["softOdds"])

    def test_build_game_money_side_odds(self):
        m = bf_match()                                   # Geld auf Heim (Borac)
        g = BC.build_game(m, BC.parse_event(odds_event(ph=1.6, pd=3.8, pa=5.0)), None, {})
        self.assertEqual(g["pinnOdd"], 1.6)              # Pinnacle-Quote DER Geld-Seite (Heim)
        self.assertIsNotNone(g["softOdd"])
        self.assertGreaterEqual(g["softN"], 1)

    def test_odds_flip_when_swapped(self):
        m = bf_match()                                   # Geld auf Borac (Heim), Quote 1.6
        ev = BC.parse_event(odds_event(home="Velez Mostar", away="Borac Banja Luka",
                                       ph=5.0, pd=3.8, pa=1.6))
        g = BC.build_game(m, BC.match_event(m, [ev]), None, {})
        self.assertEqual(g["pinnOdd"], 1.6)              # nach Flip richtig der Geld-Seite zugeordnet


class TestPoly(unittest.TestCase):
    POLY = [{"prices": {"Borac Banja Luka": 0.6, "Velez Mostar": 0.4},
             "shares": {"Borac Banja Luka": 60000.0, "Velez Mostar": 40000.0},
             "totalUsd": 100000}]

    def test_match_and_side_odd(self):
        m = bf_match()                                   # Geld auf Borac (Heim)
        p = BC.match_poly(m, BC.money_side(m), self.POLY)
        self.assertIsNotNone(p)
        self.assertEqual(p["vol"], 100000)
        self.assertAlmostEqual(p["odd"], round(1 / 0.6, 2), places=2)
        self.assertEqual(p["sharePct"], 60)

    def test_no_market_none(self):
        m = bf_match()
        other = [{"prices": {"Arsenal": 0.5, "Chelsea": 0.5}, "shares": {}, "totalUsd": 5000}]
        self.assertIsNone(BC.match_poly(m, BC.money_side(m), other))

    def test_side_absent_keeps_volume(self):
        # Geld auf Remis, Poly nur 2-Weg (kein Draw) -> Volumen ja, Odd None
        m = bf_match(runners=[
            {"name": "Borac Banja Luka", "odd": 2.5, "vol": 10000},
            {"name": "The Draw", "odd": 3.0, "vol": 60000},
            {"name": "Fk Velez Mostar", "odd": 3.2, "vol": 10000}])
        p = BC.match_poly(m, BC.money_side(m), self.POLY)
        self.assertIsNotNone(p)
        self.assertEqual(p["vol"], 100000)
        self.assertIsNone(p["odd"])


class TestQualifiesRadar(unittest.TestCase):
    def _ft(self, vol, league="Bosnian Premier League"):
        return bf_match(league=league, runners=[
            {"name": "Borac Banja Luka", "odd": 2.0, "vol": vol},
            {"name": "The Draw", "odd": 3.0, "vol": 0},
            {"name": "Fk Velez Mostar", "odd": 3.5, "vol": 0}])

    def test_rest_ft_threshold_15k(self):
        self.assertTrue(BC.qualifies_radar(self._ft(16000)))    # >= 15K Rest
        self.assertFalse(BC.qualifies_radar(self._ft(9000)))    # < 15K

    def test_top_tier_needs_20k(self):
        # Serie A = Top-5 -> 20K noetig; 16K reicht NICHT
        self.assertFalse(BC.qualifies_radar(self._ft(16000, league="Italian Serie A")))
        self.assertTrue(BC.qualifies_radar(self._ft(21000, league="Italian Serie A")))

    def test_ht_market_qualifies(self):
        m = self._ft(3000)                                      # FT zu dünn
        m["markets"]["Half Time"] = {"runners": [{"name": "Over 0.5", "odd": 1.5, "vol": 6000}]}
        self.assertTrue(BC.qualifies_radar(m))                  # HT >= 5K Rest


class TestSoftMedian(unittest.TestCase):
    """11.08.2026 (Lucas, Union-Santa-Fe-Fall): Die angezeigte Soft-Quote wird als MEDIAN der rohen
    Buch-Quoten gebildet, nicht als arithmetischer Schnitt. Bei einem Aussenseiter zieht ein einzelnes
    Buch mit einer irren (live-traegen) Quote den Mittelwert massiv hoch (11 -> 34); der Median bleibt
    stabil."""

    def _ev_with_outlier(self):
        # Heim klarer Favorit; Auswaerts grosser Aussenseiter. 3 normale + 2 Ausreisser-Soft-Buecher.
        def bk(key, ph, pd, pa):
            return {"key": key, "markets": [{"key": "h2h", "outcomes": [
                {"name": "Union Santa Fe", "price": ph},
                {"name": "Central Cordoba", "price": pa},
                {"name": "Draw", "price": pd}]}]}
        books = [bk("pinnacle", 1.30, 5.0, 9.35),
                 bk("bet365",   1.31, 5.1, 10.0),
                 bk("williamhill", 1.30, 5.0, 11.0),
                 bk("unibet",   1.32, 5.2, 9.5),
                 bk("book_stale1", 1.05, 20.0, 150.0),   # live-traege / ausgeduennt
                 bk("book_stale2", 1.04, 22.0, 225.0)]
        return {"home_team": "Union Santa Fe", "away_team": "Central Cordoba",
                "commence_time": "2026-08-11T00:00:00Z", "bookmakers": books}

    def test_median_helper(self):
        self.assertIsNone(BC._median([]))
        self.assertEqual(BC._median([5]), 5)
        self.assertEqual(BC._median([9.5, 10, 11, 150, 225]), 11)   # ungerade -> mittleres
        self.assertEqual(BC._median([10, 11, 150, 225]), 80.5)      # gerade -> Schnitt der beiden mittleren

    def test_soft_odd_is_median_not_mean(self):
        pe = BC.parse_event(self._ev_with_outlier())
        away = pe["softOdds"][2]                       # 5 Soft-Buecher: [10,11,9.5,150,225]
        mean = (10 + 11 + 9.5 + 150 + 225) / 5.0       # ~81.1 -> vom Ausreisser verzerrt
        self.assertAlmostEqual(away, 11.0, places=6)   # Median haelt stand
        self.assertLess(away, 20.0)
        self.assertLess(away, mean / 3)                # deutlich unter dem verzerrten Mittelwert

    def test_two_books_median_equals_mean(self):
        # Sanity: bei genau 2 Buechern ist Median == Mittelwert (keine Verhaltensaenderung fuer Alt-Tests).
        def bk(key, pa):
            return {"key": key, "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 1.6}, {"name": "B", "price": pa}, {"name": "Draw", "price": 3.8}]}]}
        ev = {"home_team": "A", "away_team": "B", "commence_time": "x",
              "bookmakers": [bk("pinnacle", 5.0), bk("bet365", 6.0), bk("unibet", 4.0)]}
        pe = BC.parse_event(ev)
        # 2 Soft (bet365 6.0, unibet 4.0) -> Median = 5.0 = Mittelwert
        self.assertAlmostEqual(pe["softOdds"][2], 5.0, places=6)



class TestMoneyMap(unittest.TestCase):
    """11.08.2026 (Lucas Money-Map): Poly-eigene-Seite, Bubble-Zeile, Konsens-Ledger."""

    def _poly(self):
        return [{"prices": {"Bochum": 0.35, "Union Berlin": 0.5, "Draw": 0.15},
                 "shares": {"Bochum": 20000, "Union Berlin": 66000, "Draw": 14000}, "totalUsd": 100000}]

    def test_poly_fav_eigene_seite(self):
        pf = BC.poly_fav({"home": "Bochum", "away": "Union Berlin"}, self._poly())
        self.assertEqual(pf["side"], "away")          # Union fuehrt bei Poly
        self.assertEqual(pf["sharePct"], 66)
        self.assertEqual(pf["usd"], 100000)

    def test_poly_fav_kein_match(self):
        self.assertIsNone(BC.poly_fav({"home": "X", "away": "Y"}, self._poly()))

    def _g(self, **kw):
        g = {"matchId": "1", "home": "Bochum", "away": "Union Berlin", "league": "Bundesliga",
             "live": False, "kickoff": "t", "moneySide": "away", "moneyName": "Union Berlin",
             "moneySharePct": 71, "totVol": 82000,
             "pinn": {"home": 0.26, "draw": 0.24, "away": 0.50, "fav": "away"}, "verdict": "konsens"}
        g.update(kw)
        return g

    def test_money_map_row_dreiquellen(self):
        pf = BC.poly_fav({"home": "Bochum", "away": "Union Berlin"}, self._poly())
        row = BC.money_map_row(self._g(), pf)
        self.assertEqual(row["betfair"]["eur"], 82000)
        self.assertEqual(row["poly"]["usd"], 100000)
        self.assertEqual(row["pinn"]["fav"], "away")
        self.assertEqual(row["nSources"], 3)

    def test_money_map_row_ohne_poly(self):
        row = BC.money_map_row(self._g(), None)
        self.assertIsNone(row["poly"])
        self.assertEqual(row["nSources"], 2)

    def test_ledger_upsert_pending(self):
        pf = BC.poly_fav({"home": "Bochum", "away": "Union Berlin"}, self._poly())
        led = BC.update_mm_ledger([], [BC.money_map_row(self._g(), pf)], now="2026-08-11T12:00:00+00:00")
        self.assertEqual(len(led), 1)
        self.assertEqual(led[0]["status"], "pending")
        self.assertEqual(led[0]["moneySide"], "away")
        self.assertEqual(led[0]["polySide"], "away")
        self.assertEqual(led[0]["pinnFav"], "away")

    def test_ledger_no_anchor_nicht_geloggt(self):
        row = BC.money_map_row(self._g(verdict="no_anchor", pinn=None), None)
        self.assertEqual(BC.update_mm_ledger([], [row], now="t"), [])

    def test_ledger_settled_bleibt(self):
        pf = BC.poly_fav({"home": "Bochum", "away": "Union Berlin"}, self._poly())
        prev = [{"matchId": "1", "status": "won", "verdict": "konsens", "firstSeen": "x"}]
        led = BC.update_mm_ledger(prev, [BC.money_map_row(self._g(), pf)], now="t2")
        self.assertEqual(led[0]["status"], "won")     # abgerechnete nicht ueberschreiben

if __name__ == "__main__":
    unittest.main()
