"""Event-Page-Anreicherung (31.07.2026): Betfair-Geld-Block, Markt-Konsens, ×-Norm.
Reine Helfer-Tests (kein pytest nötig): python3 -m unittest tests.test_match_page_enrich"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_wm_match_pages as G


def _bf_match(home, away, mo_vols, mo_odds, fair, total_pad=0.0, ou=None):
    """Baut einen Betfair-Match-Snapshot wie in betfair_prices.json."""
    runners = [
        {"name": home, "odd": mo_odds[0], "vol": mo_vols[0]},
        {"name": "The Draw", "odd": mo_odds[1], "vol": mo_vols[1]},
        {"name": away, "odd": mo_odds[2], "vol": mo_vols[2]},
    ]
    markets = {"Match Odds": {"vol": sum(mo_vols), "runners": runners}}
    if total_pad:
        markets["Filler"] = {"runners": [{"name": "x", "vol": total_pad}]}
    if ou:
        markets["Over/Under 2.5 Goals"] = {"runners": [
            {"name": "Over 2.5 Goals", "odd": 1.8, "vol": ou[0]},
            {"name": "Under 2.5 Goals", "odd": 2.1, "vol": ou[1]}]}
    return {"home": home, "away": away, "kickoff": "2099-01-01T00:00:00Z",
            "liveInfo": {"finished": False}, "markets": markets,
            "mo": {"hw": mo_odds[0], "dr": mo_odds[1], "aw": mo_odds[2], "vol": sum(mo_vols), "fair": fair}}


class Consensus(unittest.TestCase):
    def test_all_agree(self):
        pinn = {"nowH": 1.5, "nowD": 4.0, "nowA": 6.0}
        soft = {"nowH": 1.6, "nowD": 3.8, "nowA": 5.5}
        bf = {"mo": {"odds": {"home": 1.55, "draw": 4.1, "away": 6.2}}}
        sm = {"outcomes": {"home": {"share": 0.7}, "draw": {"share": 0.1}, "away": {"share": 0.2}}}
        c = G.build_consensus(pinn, soft, sm, bf)
        self.assertTrue(c["agree"]); self.assertEqual(c["modal"], "home")
        self.assertEqual(c["n"], 4); self.assertEqual(c["nAgree"], 4)

    def test_split(self):
        pinn = {"nowH": 1.5, "nowD": 4.0, "nowA": 6.0}          # home
        soft = {"nowH": 4.0, "nowD": 1.5, "nowA": 6.0}          # draw
        c = G.build_consensus(pinn, soft, None, None)
        self.assertFalse(c["agree"]); self.assertEqual(c["n"], 2); self.assertEqual(c["nAgree"], 1)

    def test_too_few_sources_none(self):
        self.assertIsNone(G.build_consensus({"nowH": 1.5, "nowD": 4, "nowA": 6}, None, None, None))

    def test_fav_token(self):
        self.assertEqual(G._fav_token(1.5, 4.0, 6.0), "home")
        self.assertEqual(G._fav_token(4.0, 1.5, 6.0), "draw")
        self.assertEqual(G._fav_token(6.0, 4.0, 1.5), "away")
        self.assertIsNone(G._fav_token(None, None, None))


class Betfair(unittest.TestCase):
    def test_no_match_returns_none(self):
        self.assertIsNone(G.build_betfair_block("A", "B", {}, {}))
        snaps = {G._bf_event_key("X", "Y"): _bf_match("X", "Y", [5000, 1000, 1000], [1.5, 4, 6], {"home": .6, "draw": .2, "away": .2})}
        self.assertIsNone(G.build_betfair_block("A", "B", snaps, {}))

    def test_low_volume_returns_none(self):
        m = _bf_match("X", "Y", [500, 300, 200], [1.5, 4, 6], {"home": .6, "draw": .2, "away": .2})
        snaps = {G._bf_event_key("X", "Y"): m}
        self.assertIsNone(G.build_betfair_block("X", "Y", snaps, {}))  # total 1000 < 5000

    def test_shares_and_heavy(self):
        # Heim: 8000 von 10000 Geld (80%), fair 44% → heavy home +36pp
        m = _bf_match("X", "Y", [8000, 1100, 900], [1.6, 4, 6], {"home": .44, "draw": .24, "away": .32})
        snaps = {G._bf_event_key("X", "Y"): m}
        b = G.build_betfair_block("X", "Y", snaps, {})
        self.assertAlmostEqual(b["mo"]["shares"]["home"]["share"], 0.8, places=2)
        self.assertEqual(b["heavy"]["token"], "home")
        self.assertEqual(b["heavy"]["moneyPct"], 80)
        self.assertEqual(b["heavy"]["fairPct"], 44)
        self.assertEqual(b["heavy"]["edgePP"], 36)

    def test_xnorm_ratio(self):
        m = _bf_match("X", "Y", [8000, 1100, 900], [1.6, 4, 6], {"home": .44, "draw": .24, "away": .32})
        snaps = {G._bf_event_key("X", "Y"): m}
        # Peer-Median 5000 (5 Peers) → 10000/5000 = 2.0× → Level 1 (amber, >=1.6, <2.6)
        norm = {"p0": [4000, 4500, 5000, 5500, 6000]}
        b = G.build_betfair_block("X", "Y", snaps, norm)
        self.assertEqual(b["normRatio"], 2.0)
        self.assertEqual(b["normLvl"], 1)

    def test_bf_total(self):
        m = _bf_match("X", "Y", [5000, 1000, 1000], [1.5, 4, 6], {"home": .6, "draw": .2, "away": .2}, total_pad=3000)
        self.assertEqual(G._bf_market_total(m), 10000.0)


if __name__ == "__main__":
    unittest.main()
