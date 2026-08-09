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


if __name__ == "__main__":
    unittest.main()
