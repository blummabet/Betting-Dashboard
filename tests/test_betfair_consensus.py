# tests/test_betfair_consensus.py — Betfair-Konsens (Zweitmeinung), 09.08.2026 (Lucas).
# Testet die reine Logik OHNE Netz: Namens-Match, De-vig, Event-Parse, Geld-Seite, Verdikt, Bewegung.
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_consensus as BC
from datetime import datetime, timezone, timedelta


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

    def test_away_lead_case_mismatch(self):
        # 22.08.2026 (Lucas): Betfair "Az Alkmaar" vs Team "AZ Alkmaar" — Casing darf die Seite nicht kippen.
        m = bf_match(home="Fortuna Sittard", away="AZ Alkmaar", runners=[
            {"name": "Fortuna Sittard", "odd": 8.0, "vol": 10000},
            {"name": "The Draw", "odd": 5.0, "vol": 10000},
            {"name": "Az Alkmaar", "odd": 1.3, "vol": 80000}])
        ms = BC.money_side(m)
        self.assertEqual(ms["side"], "away")   # 90% Geld auf AZ = away, nicht home

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

    def test_verdikt_ohne_anker_betfair_poly_einig(self):
        # UEFA Super Cup / Pokal: kein Pinnacle-Anker -> build_game liefert no_anchor. Liegen Betfair
        # UND Poly vor und sind einig -> Money-Map wertet es als Konsens (2/3), sonst faellt es aus der
        # Uebersicht (die no_anchor filtert). Genau der Paris-Villa-Fall.
        g = self._g(verdict="no_anchor", pinn=None, moneySide="home", moneyName="Bochum")
        pf = {"side": "home", "name": "Bochum", "sharePct": 55, "usd": 50000}
        row = BC.money_map_row(g, pf)
        self.assertEqual(row["verdict"], "konsens")
        self.assertEqual(row["nSources"], 2)
        self.assertIsNone(row["pinn"])

    def test_verdikt_ohne_anker_betfair_poly_uneinig(self):
        g = self._g(verdict="no_anchor", pinn=None, moneySide="home", moneyName="Bochum")
        pf = {"side": "away", "name": "Union Berlin", "sharePct": 52, "usd": 50000}
        row = BC.money_map_row(g, pf)
        self.assertEqual(row["verdict"], "uneinig")

    def test_verdikt_ohne_anker_nur_betfair_bleibt_no_anchor(self):
        g = self._g(verdict="no_anchor", pinn=None)
        row = BC.money_map_row(g, None)   # keine Poly -> nichts zu vergleichen
        self.assertEqual(row["verdict"], "no_anchor")
        self.assertEqual(row["nSources"], 1)

    def _entry(self, prices, **kw):
        d = {"src": "upcoming", "totalUsd": 50000, "prices": prices, "shares": {}}
        d.update(kw); return d

    def test_poly_fav_aus_preis_wenn_keine_shares(self):
        # upcoming-Erfassung: keine Shares -> Favorit aus dem Preis (Poly-Preis = Wahrscheinlichkeit)
        m = {"home": "Paris St-G", "away": "Aston Villa"}
        e = self._entry({"Paris St-G": 0.60, "Aston Villa": 0.28, "Draw": 0.12})
        pf = BC.poly_fav(m, [e])
        self.assertEqual(pf["side"], "home")
        self.assertEqual(pf["sharePct"], 60)
        self.assertEqual(pf["usd"], 50000)
        self.assertEqual(pf["src"], "upcoming")

    def test_matching_abkuerzung_paris(self):
        # Betfair "Paris St-G" vs Poly "Paris Saint-Germain": eine Seite exakt (Villa), andere abgeleitet
        m = {"home": "Paris St-G", "away": "Aston Villa"}
        e = self._entry({"Paris Saint-Germain": 0.60, "Aston Villa": 0.40})
        self.assertIsNotNone(BC._best_poly_entry(m, [e]))
        self.assertIsNotNone(BC.poly_fav(m, [e]))

    def test_matching_kein_falsch_match(self):
        # nur Villa gleich, Gegner voellig anders (kein geteiltes Token) -> KEIN Match
        m = {"home": "Paris St-G", "away": "Aston Villa"}
        e = self._entry({"Aston Villa": 0.5, "Chelsea": 0.5})
        self.assertIsNone(BC._best_poly_entry(m, [e]))

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


class TestMoneyMapSettle(unittest.TestCase):
    """11.08.2026 (Lucas Money-Map Tracking): Abrechnung gegen Endstand + Trefferquote je Verdikt."""
    NOW = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)

    def _led(self):
        ko = (self.NOW - timedelta(hours=4)).isoformat()
        return [
            {"matchId": "1", "kickoff": ko, "verdict": "konsens", "moneySide": "home", "pinnFav": "home", "status": "pending"},
            {"matchId": "2", "kickoff": ko, "verdict": "uneinig", "moneySide": "away", "pinnFav": "home", "status": "pending"},
            {"matchId": "3", "kickoff": (self.NOW - timedelta(hours=1)).isoformat(), "verdict": "konsens", "moneySide": "home", "status": "pending"},
        ]

    def _fake(self, ids):
        return {"1": {"goal_v1": 2, "goal_v2": 0, "finished": True},
                "2": {"goal_v1": 1, "goal_v2": 0, "finished": True}}

    def test_settle_won_lost(self):
        out = {e["matchId"]: e for e in BC.settle_mm_ledger(self._led(), results_fetch=self._fake, now=self.NOW)}
        self.assertEqual(out["1"]["status"], "won")
        self.assertTrue(out["1"]["moneyWin"])
        self.assertEqual(out["2"]["status"], "lost")     # Geld auf Auswaerts, Heim gewann
        self.assertTrue(out["2"]["pinnWin"])             # Pinnacle-Favorit (Heim) lag richtig
        self.assertEqual(out["3"]["status"], "pending")  # zu frisch

    def test_ohne_fetcher_noop(self):
        self.assertEqual(BC.settle_mm_ledger(self._led(), results_fetch=None, now=self.NOW)[0]["status"], "pending")

    def test_summary_je_verdict(self):
        out = BC.settle_mm_ledger(self._led(), results_fetch=self._fake, now=self.NOW)
        rec = BC.mm_summary(out)
        self.assertEqual(rec["byVerdict"]["konsens"]["hitRate"], 1.0)
        self.assertEqual(rec["byVerdict"]["uneinig"]["hitRate"], 0.0)
        self.assertEqual(rec["byVerdict"]["uneinig"]["pinnHitRate"], 1.0)
        self.assertEqual(rec["global"]["n"], 2)
        self.assertEqual(rec["pending"], 1)

class TestMmMoneyGate(unittest.TestCase):
    """12.08.2026 (Lucas): Money-Map nur mit echtem Vergleich — Betfair+Poly, oder eine Quelle >= 150K.
    Pinnacle zaehlt nicht (nur Odds-Anker)."""

    def _row(self, eur=None, usd=None):
        return {"betfair": ({"eur": eur} if eur is not None else None),
                "poly": ({"usd": usd} if usd is not None else None)}

    def test_beide_quellen_rein(self):
        self.assertTrue(BC._mm_money_ok(self._row(eur=21000, usd=36000)))   # Monterrey: klein, aber 2 Quellen

    def test_eine_quelle_klein_raus(self):
        self.assertFalse(BC._mm_money_ok(self._row(eur=18000)))             # Brann U19: nur Betfair, <150K

    def test_eine_quelle_gross_rein(self):
        self.assertTrue(BC._mm_money_ok(self._row(eur=418000)))            # Paris: nur Betfair, Marquee
        self.assertTrue(BC._mm_money_ok(self._row(usd=200000)))            # nur Poly, aber gross

    def test_gar_kein_geld_raus(self):
        self.assertFalse(BC._mm_money_ok(self._row()))

    def test_pinnacle_zaehlt_nicht(self):
        # Row mit Pinnacle-Anker aber nur kleinem Betfair, kein Poly -> raus (Pinnacle ist keine Geldquelle)
        r = self._row(eur=18000); r["pinn"] = {"fav": "home", "home": 0.6, "draw": 0.25, "away": 0.15}
        self.assertFalse(BC._mm_money_ok(r))


if __name__ == "__main__":
    unittest.main()


class TestPolyUpcomingFallback(unittest.TestCase):
    """18.08.2026 (Lucas): Poly-Quote muss auch >3h vor Anpfiff kommen (upcoming-Pool, nur Preis+Vol,
    kein Holder-Freeze). Atletico-Malaga zeigte 'kein Poly-Markt' obwohl Poly den Markt hat."""

    def _upcoming_entry(self):
        # Form wie poly_money_upcoming.json: prices (Poly-Labels, mit Akzent/„Club … de"), totalUsd, KEINE shares
        return {"prices": {"Club Atlético de Madrid": 0.735,
                           "Draw (Club Atlético de Madrid vs. Málaga CF)": 0.165,
                           "Málaga CF": 0.085},
                "totalUsd": 61467, "src": "upcoming"}

    def test_match_poly_ohne_shares_liefert_odd_und_vol(self):
        m = bf_match(home="Atletico Madrid", away="Malaga", league="Spanish La Liga", country="ES",
                     runners=[{"name": "Atletico Madrid", "odd": 1.36},
                              {"name": "The Draw", "odd": 5.0},
                              {"name": "Malaga", "odd": 8.0}])
        res = BC.match_poly(m, BC.money_side(m), [self._upcoming_entry()])
        self.assertIsNotNone(res, "Poly-Markt muss (per Namens-Match) gefunden werden")
        self.assertAlmostEqual(res["odd"], 1.36, places=2)     # 1/0.735
        self.assertEqual(res["vol"], 61467)
        # 06.09.2026 — hier stand `assertIsNone(res["sharePct"])` mit dem Kommentar
        # „kein Holder-Freeze -> Share None (Preis reicht)". Der Preis reichte eben NICHT:
        # `killer.py` las aus `sharePct=None` ein `polyStatus="unbekannt"`, und das Board zeigte
        # POLY ❔ fuer jedes Spiel ausserhalb des ~3h-Freeze — auch dort, wo Markt und Preis
        # vorlagen und die Money Map daneben „Konsens 3/3" schrieb. Der Test hat das Verhalten
        # zementiert, das der Fund war. Jetzt: Preis-Anteil ja, aber als solcher gekennzeichnet.
        self.assertEqual(res["sharePct"], 74)                  # 0.735 -> 74 %
        self.assertEqual(res["shareSrc"], "preis")             # und NICHT als Geld-Anteil ausgegeben

    def test_fallback_kette_close_leer_dann_upcoming(self):
        m = bf_match(home="Atletico Madrid", away="Malaga", league="Spanish La Liga", country="ES",
                     runners=[{"name": "Atletico Madrid", "odd": 1.36},
                              {"name": "The Draw", "odd": 5.0},
                              {"name": "Malaga", "odd": 8.0}])
        ms = BC.money_side(m)
        close_entries = []                                     # Close-Freeze hat den Markt (noch) nicht
        upcoming_entries = [self._upcoming_entry()]
        poly = BC.match_poly(m, ms, close_entries) or BC.match_poly(m, ms, upcoming_entries)
        self.assertIsNotNone(poly)                             # Fallback fuellt das vorher leere poly
        self.assertAlmostEqual(poly["odd"], 1.36, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# 18.08.2026 (Lucas): Pinnacle-Totals andocken -> O/U-Edge. De-vig 2-Weg, parse_totals (volle Leiter
# aus totals+alternate_totals, nur Pinnacle), _fmt_line, und build_game haengt pinnTotals an.
def _odds_totals_event(home="Borac Banja Luka", away="Fk Velez Mostar"):
    return {
        "home_team": home, "away_team": away, "commence_time": "2026-08-09T16:30:00Z",
        "bookmakers": [
            {"key": "pinnacle", "markets": [
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 1.95, "point": 2.5},
                    {"name": "Under", "price": 1.90, "point": 2.5}]},
                {"key": "alternate_totals", "outcomes": [
                    {"name": "Over", "price": 1.30, "point": 1.5},
                    {"name": "Under", "price": 3.60, "point": 1.5},
                    {"name": "Over", "price": 3.30, "point": 3.5},
                    {"name": "Under", "price": 1.34, "point": 3.5}]}]},
            # Soft-Buch wird ignoriert (nur Pinnacle ist der Anker)
            {"key": "betfair_ex_eu", "markets": [
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 2.5, "point": 2.5},
                    {"name": "Under", "price": 1.5, "point": 2.5}]}]},
        ]}


class TestPinnacleTotals(unittest.TestCase):
    def test_devig2_symmetric(self):
        p = BC._devig2(1.95, 1.95)
        self.assertAlmostEqual(p[0], 0.5, places=6)
        self.assertAlmostEqual(p[0] + p[1], 1.0, places=9)

    def test_devig2_lopsided_and_bad(self):
        p = BC._devig2(1.10, 8.0)         # Over klarer Favorit
        self.assertGreater(p[0], 0.8)
        self.assertIsNone(BC._devig2(None, 1.9))
        self.assertIsNone(BC._devig2(0, 1.9))

    def test_fmt_line(self):
        self.assertEqual(BC._fmt_line(2.5), "2.5")
        self.assertEqual(BC._fmt_line(3.0), "3")
        self.assertIsNone(BC._fmt_line(None))

    def test_parse_totals_full_ladder_pinnacle_only(self):
        t = BC.parse_totals(_odds_totals_event())
        tot = t["totals"]
        self.assertEqual(set(tot), {"1.5", "2.5", "3.5"})   # totals + alternate_totals zusammen
        # jede Linie de-viggt auf Summe 1
        for ln, v in tot.items():
            self.assertAlmostEqual(v["overFair"] + v["underFair"], 1.0, places=6)
        # 2.5 ~ Coinflip, leicht Under-lastig (Under-Quote kuerzer)
        self.assertGreater(tot["2.5"]["underFair"], tot["2.5"]["overFair"])
        # Soft-Buch-Quoten dürfen NICHT durchschlagen (Over@2.5 bleibt Pinnacle 1.95, nicht 2.5)
        self.assertEqual(tot["2.5"]["overOdd"], 1.95)

    def test_build_game_attaches_pinn_totals(self):
        m = bf_match()
        tev = BC.parse_totals(_odds_totals_event())
        g = BC.build_game(m, None, None, {}, None, totals_ev=tev)
        self.assertIn("pinnTotals", g)
        self.assertEqual(set(g["pinnTotals"]), {"1.5", "2.5", "3.5"})
        # ohne totals_ev bleibt es None (rueckwaertskompatibel)
        g2 = BC.build_game(m, None, None, {}, None)
        self.assertIsNone(g2["pinnTotals"])

    def test_match_event_carries_totals_when_flipped(self):
        # Betfair-Heim/Auswaerts vertauscht ggue. odds-api -> _flip muss totals erhalten
        m = bf_match(home="Fk Velez Mostar", away="Borac Banja Luka")
        tev = BC.match_event(m, [BC.parse_totals(_odds_totals_event())])
        self.assertIsNotNone(tev)
        self.assertIn("2.5", tev.get("totals") or {})




# 18.08.2026 (Lucas: „live beim Betfair-Terminal die Poly-Odds"): pick_poly waehlt die Poly-Quelle je
# Phase. LAUFENDES Spiel -> frische Live-Poly ZUERST (nicht die eingefrorene Close-Quote); nicht-live ->
# Close zuerst, dann Upcoming. Fixt: Live-Spiel im Close-Pool zeigte veraltete Pre-Match-Poly-Odds.
class TestPickPolyPhase(unittest.TestCase):
    def _pools(self):
        close = [{"prices": {"Borac Banja Luka": 0.60, "Fk Velez Mostar": 0.40},
                  "shares": {"Borac Banja Luka": 60000, "Fk Velez Mostar": 40000}, "totalUsd": 100000}]
        live  = [{"prices": {"Borac Banja Luka": 0.70, "Fk Velez Mostar": 0.30},
                  "shares": {"Borac Banja Luka": 70000, "Fk Velez Mostar": 30000}, "totalUsd": 50000}]
        up    = [{"prices": {"Borac Banja Luka": 0.55, "Fk Velez Mostar": 0.45},
                  "shares": {}, "totalUsd": 8000}]
        return close, live, up

    def test_live_prefers_fresh_live_pool(self):
        m = bf_match(); close, live, up = self._pools()
        r = BC.pick_poly(m, BC.money_side(m), True, close, live, up)
        self.assertEqual(r["odd"], round(1 / 0.70, 2))   # Live-Quote, NICHT die eingefrorene Close-Quote

    def test_nonlive_prefers_close(self):
        m = bf_match(); close, live, up = self._pools()
        r = BC.pick_poly(m, BC.money_side(m), False, close, live, up)
        self.assertEqual(r["odd"], round(1 / 0.60, 2))   # Close (mit Holder-Shares)

    def test_fallback_chain(self):
        m = bf_match(); close, live, up = self._pools()
        self.assertEqual(BC.pick_poly(m, BC.money_side(m), True, close, [], up)["odd"], round(1 / 0.60, 2))  # live leer -> close
        self.assertEqual(BC.pick_poly(m, BC.money_side(m), True, [], [], up)["odd"], round(1 / 0.55, 2))     # -> upcoming
        self.assertIsNone(BC.pick_poly(m, BC.money_side(m), True, [], [], []))                                # nichts


class TestPolyScanFallback(unittest.TestCase):
    # 23.08.2026 (Lucas: „Serie A ist alles da, aber Money-Map zeigt kein Poly"): dünner Markt →
    # fairer Poly-Preis aus pinnacle_poly_scan als Fallback. Füllt die Poly-SEITE, zählt aber NICHT
    # als Geldquelle.
    def _scan_entry(self, home, away, ph, pd, pa, vol=597):
        return {"prices": {home: ph, "Draw": pd, away: pa}, "shares": {}, "totalUsd": vol, "src": "scan"}

    def test_poly_fav_from_scan_price(self):
        e = [self._scan_entry("Frosinone Calcio", "Juventus FC", 0.115, 0.205, 0.675)]
        pf = BC.poly_fav({"home": "Frosinone", "away": "Juventus"}, e)
        self.assertIsNotNone(pf)
        self.assertEqual(pf["side"], "away")
        self.assertEqual(pf["name"], "Juventus FC")
        self.assertEqual(pf["sharePct"], 68)     # 0.675 * 100
        self.assertEqual(pf["src"], "scan")

    def test_scan_poly_not_a_money_source(self):
        # schwacher Betfair (<150K) + Scan-Poly → NICHT gerettet (Scan zählt nicht als Geld)
        self.assertFalse(BC._mm_money_ok({"betfair": {"eur": 50000}, "poly": {"usd": 597, "src": "scan"}}))
        # aber echtes Poly-Geld rettet den schwachen Betfair
        self.assertTrue(BC._mm_money_ok({"betfair": {"eur": 50000}, "poly": {"usd": 40000, "src": "close"}}))
        # starker Betfair alleine (>=150K) bleibt auch mit Scan-Poly drin
        self.assertTrue(BC._mm_money_ok({"betfair": {"eur": 161000}, "poly": {"usd": 597, "src": "scan"}}))
