#!/usr/bin/env python3
"""test_poly_pinnacle_scan.py — Broad Pinnacle x Poly Scanner (04.08.2026, Lucas).
Injizierte Fetcher: kein Netz. Prueft Paarung (direct + swapped), Snapshot-Anhaengen, Prune, Cap."""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import poly_pinnacle_scan as S

NOW = datetime(2026, 8, 4, 13, 0, tzinfo=timezone.utc)
def ko(h): return (NOW + timedelta(hours=h)).isoformat()

# zwei Poly-Spiele: A normal orientiert, B (Pinnacle liefert vertauscht)
def poly_fetch(series):
    return [
        {"slug": "a-2026", "home": "Ajax", "away": "PSV", "kickoff": ko(3), "poly": [0.50, 0.30, 0.20], "vol": 9000},
        {"slug": "b-2026", "home": "Feyenoord", "away": "Twente", "kickoff": ko(5), "poly": [0.40, 0.30, 0.30], "vol": 4000},
    ]
def pinn_fetch(key):
    return [
        {"home": "Ajax", "away": "PSV", "commence": ko(3), "book": "pinnacle", "pinn": [0.55, 0.28, 0.17], "dec": []},
        # Pinnacle liefert B vertauscht: Twente(Heim) vs Feyenoord(Auswaerts)
        {"home": "Twente", "away": "Feyenoord", "commence": ko(5), "book": "pinnacle", "pinn": [0.20, 0.30, 0.50], "dec": []},
    ]
LG = [{"name": "Eredivisie", "poly": "10286", "odds": "soccer_netherlands_eredivisie"}]


class TestScan(unittest.TestCase):
    def test_pairing_und_swap(self):
        rows, nact, npair, ts, now = S.scan(LG, poly_fetch, pinn_fetch, now=NOW)
        self.assertEqual(nact, 1)
        self.assertEqual(npair, 2)
        a = rows["Eredivisie|Ajax|PSV|2026-08-04"]
        self.assertEqual(a["snap"]["pinn"], [0.55, 0.28, 0.17])   # direct: unveraendert
        self.assertEqual(a["snap"]["poly"], [0.50, 0.30, 0.20])
        b = rows["Eredivisie|Feyenoord|Twente|2026-08-04"]
        # swapped: Pinnacle [Twente0.20, X0.30, Fey0.50] -> Poly-Rahmen [Fey0.50, X0.30, Twente0.20]
        self.assertEqual(b["snap"]["pinn"], [0.50, 0.30, 0.20])
        self.assertEqual(b["snap"]["book"], "pinnacle")

    def test_snapshots_haengen_an(self):
        store = {}
        for _ in range(3):
            rows, *_rest = S.scan(LG, poly_fetch, pinn_fetch, now=NOW)
            store = S.merge_store(store, rows, NOW)
        g = store["games"]["Eredivisie|Ajax|PSV|2026-08-04"]
        self.assertEqual(len(g["snaps"]), 3)

    def test_prune_nach_anpfiff(self):
        # Spiel liegt >6h nach Anpfiff -> raus
        old = [{"slug": "old", "home": "Ajax", "away": "PSV", "kickoff": ko(-8), "poly": [0.5, 0.3, 0.2], "vol": 100}]
        rows, *_r = S.scan(LG, lambda s: old, pinn_fetch, now=NOW)
        store = S.merge_store({}, rows, NOW)
        self.assertNotIn("Eredivisie|Ajax|PSV|2026-08-04", store.get("games", {}))

    def test_cap_max_snaps(self):
        store = {"games": {"k": {"league": "X", "home": "H", "away": "A", "kickoff": ko(2),
                                  "snaps": [{"ts": str(i)} for i in range(S.MAX_SNAPS + 20)]}}}
        rows = {"k": {"league": "X", "home": "H", "away": "A", "kickoff": ko(2),
                      "snap": {"ts": "neu"}}}
        store = S.merge_store(store, rows, NOW)
        self.assertEqual(len(store["games"]["k"]["snaps"]), S.MAX_SNAPS)
        self.assertEqual(store["games"]["k"]["snaps"][-1]["ts"], "neu")


    def test_multi_key_merge(self):
        # UCL/UEL: mehrere Odds-Keys (Haupt + Quali) -> beide abfragen, Events mergen.
        def ev(home, away, hw, dr, aw):
            return {"home_team": home, "away_team": away, "commence_time": "2026-08-04T15:00:00Z",
                    "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                        {"name": home, "price": hw}, {"name": "Draw", "price": dr}, {"name": away, "price": aw}]}]}]}
        calls = []
        def og(path):
            calls.append(path)
            return [ev("Ajax", "PSV", 2.0, 3.5, 4.0)] if "/main/" in path else [ev("Roma", "Lazio", 2.2, 3.3, 3.4)]
        out = S.fetch_pinn_games(["main", "quali"], odds_get=og)
        self.assertEqual(len(calls), 2)                       # beide Keys abgefragt
        homes = {g["home"] for g in out}
        self.assertEqual(homes, {"Ajax", "Roma"})            # Events aus beiden gemerged

    def test_devig(self):
        self.assertIsNone(S._devig_1x2(1.0, 3.0, 3.0))     # implausibel
        self.assertIsNone(S._devig_1x2(None, 3, 3))
        f = S._devig_1x2(2.0, 4.0, 4.0)
        self.assertAlmostEqual(sum(f), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
