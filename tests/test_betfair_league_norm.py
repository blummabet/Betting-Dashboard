#!/usr/bin/env python3
"""test_betfair_league_norm.py — gelernte Liga-Basis fuers x-Norm-Badge (24.08.2026, Lucas).

Sichert die drei Stellen, an denen so eine Basis still falsch werden kann:
  1. Phasen-Zuordnung (p0/p1/l1/l2) — misst man l1 gegen p1, ist die Zahl um Faktoren daneben.
  2. NUR abgeschlossene Phasen als Stichprobe — ein gerade angepfiffenes Spiel wuerde sonst seinen
     halben l1-Stand beisteuern und den Median druecken.
  3. Dedup je Event — die History taucht bei jedem Lauf erneut auf; ohne Dedup misst der Median die
     Anzahl der Laeufe statt die Anzahl der Spiele.
"""
import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import betfair_league_norm as B

KO = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
KOMS = KO.timestamp() * 1000
H = 3.6e6


def _iso(dt):
    return dt.isoformat()


def _snap(offset_h, vol, kick=KO):
    return {"ts": _iso(kick + timedelta(hours=offset_h)), "totalVol": vol, "kickoff": _iso(kick)}


class TestStageOf(unittest.TestCase):
    def test_phasen(self):
        self.assertEqual(B.stage_of(KOMS - 6 * H, KOMS), "p0")
        self.assertEqual(B.stage_of(KOMS - 2 * H, KOMS), "p1")
        self.assertEqual(B.stage_of(KOMS + 10 * 60000, KOMS), "l1")
        self.assertEqual(B.stage_of(KOMS + 60 * 60000, KOMS), "l2")

    def test_grenzen(self):
        self.assertEqual(B.stage_of(KOMS - 3 * H, KOMS), "p1")        # genau 3h -> noch p1
        self.assertEqual(B.stage_of(KOMS - 3 * H - 1, KOMS), "p0")
        self.assertEqual(B.stage_of(KOMS + 45 * 60000, KOMS), "l1")   # genau 45' -> noch l1
        self.assertEqual(B.stage_of(KOMS + 45 * 60000 + 1, KOMS), "l2")

    def test_vorbei_und_unbekannt(self):
        self.assertIsNone(B.stage_of(KOMS + 5 * H, KOMS))
        self.assertIsNone(B.stage_of(KOMS, None))
        self.assertIsNone(B.stage_of(None, KOMS))


class TestSamples(unittest.TestCase):
    def _hist(self):
        return {"E1": [_snap(-6, 50000), _snap(-4, 60000), _snap(-2, 90000),
                       _snap(-0.5, 120000), _snap(0.3, 200000), _snap(1.2, 400000)]}

    def test_hoechster_stand_je_phase(self):
        now = KOMS + 5 * H          # Spiel vorbei -> alle Phasen abgeschlossen
        got = {s["stage"]: s["vol"] for s in B.samples_from_history(self._hist(), {"E1": "EPL"}, now)}
        self.assertEqual(got, {"p0": 60000, "p1": 120000, "l1": 200000, "l2": 400000})

    def test_laufende_phase_wird_nicht_eingefroren(self):
        # 20 Minuten nach Anpfiff: p0 und p1 sind fertig, l1 laeuft noch -> darf nicht zaehlen.
        got = {s["stage"] for s in B.samples_from_history(self._hist(), {"E1": "EPL"}, KOMS + 0.33 * H)}
        self.assertEqual(got, {"p0", "p1"})

    def test_ohne_liga_keine_stichprobe(self):
        self.assertEqual(B.samples_from_history(self._hist(), {}, KOMS + 5 * H), [])

    def test_kleckerbetraege_fliegen_raus(self):
        h = {"E1": [_snap(-6, 100), _snap(-2, 2999)]}
        self.assertEqual(B.samples_from_history(h, {"E1": "EPL"}, KOMS + 5 * H), [])

    def test_kaputte_daten_werfen_nicht(self):
        h = {"E1": "kaputt", "E2": [], "E3": [{"ts": "quatsch", "totalVol": 9000, "kickoff": _iso(KO)}],
             "E4": [{"totalVol": 9000}], "E5": [_snap(-2, None), _snap(-2, 50000)]}
        got = B.samples_from_history(h, {k: "EPL" for k in h}, KOMS + 5 * H)
        self.assertEqual([(s["eid"], s["stage"], s["vol"]) for s in got], [("E5", "p1", 50000)])


class TestMerge(unittest.TestCase):
    def _s(self, eid, vol, ts=None, league="EPL", stage="p1"):
        return {"league": league, "stage": stage, "vol": vol, "eid": eid, "ts": ts or KOMS}

    def test_dedup_je_event(self):
        # Derselbe Lauf zweimal darf die Stichprobe nicht verdoppeln.
        st = B.merge_samples({}, [self._s("E1", 100000)], KOMS)
        st = B.merge_samples(st, [self._s("E1", 100000)], KOMS)
        self.assertEqual(len(st["EPL|p1"]), 1)

    def test_hoeherer_stand_ersetzt(self):
        st = B.merge_samples({}, [self._s("E1", 100000)], KOMS)
        st = B.merge_samples(st, [self._s("E1", 180000)], KOMS)
        self.assertEqual([r[1] for r in st["EPL|p1"]], [180000])
        st = B.merge_samples(st, [self._s("E1", 90000)], KOMS)
        self.assertEqual([r[1] for r in st["EPL|p1"]], [180000], "niedriger ueberschreibt nicht")

    def test_fenster_prunt(self):
        alt = KOMS - (B.WINDOW_DAYS + 1) * 86400000
        st = B.merge_samples({}, [self._s("ALT", 100000, ts=alt), self._s("NEU", 120000)], KOMS)
        self.assertEqual([r[2] for r in st["EPL|p1"]], ["NEU"])

    def test_kappung_behaelt_die_neuesten(self):
        neu = [self._s("E%d" % i, 1000 + i, ts=KOMS - (B.SAMPLE_CAP - i) * 60000)
               for i in range(B.SAMPLE_CAP + 20)]
        st = B.merge_samples({}, neu, KOMS)
        self.assertEqual(len(st["EPL|p1"]), B.SAMPLE_CAP)
        self.assertEqual(st["EPL|p1"][-1][2], "E%d" % (B.SAMPLE_CAP + 19))

    def test_buckets_bleiben_getrennt(self):
        st = B.merge_samples({}, [self._s("E1", 100000, stage="p1"),
                                  self._s("E1", 900000, stage="l2"),
                                  self._s("E1", 5000, league="Liga2")], KOMS)
        self.assertEqual(sorted(st.keys()), ["EPL|l2", "EPL|p1", "Liga2|p1"])


class TestAggregate(unittest.TestCase):
    def test_median_nicht_mittel(self):
        # Genau davor soll das Badge warnen: ein Ausreisser darf die Basis nicht mitziehen.
        rows = [[KOMS, v, "E%d" % i] for i, v in enumerate([10000, 11000, 12000, 13000, 900000])]
        self.assertEqual(B.aggregate({"EPL|p1": rows})["EPL|p1"], {"med": 12000, "n": 5})

    def test_leere_und_kaputte_buckets(self):
        self.assertEqual(B.aggregate({}), {})
        self.assertEqual(B.aggregate({"EPL|p1": [], "X|p1": [["ts"]]}), {})


class TestLeagueMap(unittest.TestCase):
    def test_prices_gewinnt_ueber_ledger(self):
        m = B.league_map({"matches": [{"matchId": 1, "league": "Neu"}]},
                         [{"matchId": "1", "league": "Alt"}, {"matchId": "2", "league": "Zwei"}])
        self.assertEqual(m, {"1": "Neu", "2": "Zwei"})

    def test_unvollstaendige_zeilen(self):
        self.assertEqual(B.league_map({"matches": [{"league": "X"}, "kaputt"]},
                                      [{"matchId": "3"}, None]), {})


if __name__ == "__main__":
    unittest.main()
