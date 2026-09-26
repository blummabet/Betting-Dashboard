"""26.09.2026 — North Macedonia v Switzerland & Co.: „Pinnacle nicht erhoben", obwohl der
Wettbewerb abgerufen war. Vier moegliche Ursachen sahen im Artefakt gleich aus."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import betfair_consensus as B

M = {"home": "Czechia", "away": "Croatia", "kickoff": "2026-09-26T18:45:00Z"}


def ev(h, a, t="2026-09-26T18:45:00Z", pinn=True):
    return {"home": h, "away": a, "commence": t, "pinn": [0.3, 0.3, 0.4] if pinn else None,
            "key": "soccer_uefa_nations_league"}


class TestAlias(unittest.TestCase):
    def test_czechia_trifft_czech_republic(self):
        self.assertIsNotNone(B.match_event(M, [ev("Czech Republic", "Croatia")], max_h=2))

    def test_turkiye_trifft_turkey(self):
        m = {"home": "Türkiye", "away": "Italy", "kickoff": "2026-09-28T18:45:00Z"}
        self.assertIsNotNone(B.match_event(m, [ev("Turkey", "Italy", "2026-09-28T18:45:00Z")], max_h=2))


class TestGrund(unittest.TestCase):
    def test_mit_pinnacle_kein_grund(self):
        self.assertIsNone(B.anker_grund(M, ev("Czech Republic", "Croatia"), []))

    def test_event_ohne_pinnacle(self):
        g = B.anker_grund(M, ev("Czech Republic", "Croatia", pinn=False), [])
        self.assertEqual(g["grund"], "kein_pinnacle")
        self.assertEqual(g["spiel"], "Czechia v Croatia")

    def test_zeit(self):
        g = B.anker_grund(M, None, [ev("Czech Republic", "Croatia", "2026-09-27T18:45:00Z")])
        self.assertEqual(g["grund"], "zeit")
        self.assertEqual(g["abstandH"], 24.0)

    def test_name(self):
        m = {"home": "Bosnia", "away": "Ruritania", "kickoff": "2026-09-26T18:45:00Z"}
        g = B.anker_grund(m, None, [ev("Bosnia and Herzegovina", "Romania")])
        self.assertEqual(g["grund"], "name")

    def test_kein_kandidat(self):
        self.assertEqual(B.anker_grund(M, None, [ev("Spain", "England")])["grund"], "kein_kandidat")


class TestWaechter(unittest.TestCase):
    def _ctx(self, **c):
        import betfair_data_integrity as D
        return D, D.BetfairCtx(consensus=c)

    def test_namensluecke_wird_gemeldet(self):
        D, ctx = self._ctx(ankerDiagnose={"nach": {"name": 1}, "beispiele": [
            {"spiel": "Czechia v Croatia", "liga": "UEFA Nations League", "grund": "name",
             "kandidat": "Czech Republic v Croatia"}]})
        self.assertFalse(D.check_anker_namensabgleich(ctx)["ok"])

    def test_fehlendes_event_ist_kein_fund(self):
        D, ctx = self._ctx(ankerDiagnose={"nach": {"kein_kandidat": 12}, "beispiele": []})
        self.assertTrue(D.check_anker_namensabgleich(ctx)["ok"])


if __name__ == "__main__":
    unittest.main()
