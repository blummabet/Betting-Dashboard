"""27.09.2026 (Lucas-Uebersicht-Check): „Denmark v Wales" stand in derselben Sektion als 9/10
(Tafel) und 10/10 (gehaltene Zeile), „Serbia v Netherlands" als 10/13 und 8/10."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import killer as K


class TestEinSpielEinPunktestand(unittest.TestCase):
    def test_gehaltene_zeile_traegt_den_score_der_tafel(self):
        now = datetime(2026, 9, 27, 11, 30, tzinfo=timezone.utc)
        ko = (now + timedelta(hours=4)).isoformat()
        sig_alt = {"fav": "home", "odd": 1.6, "share": 0.87, "conc": True, "inflow": True, "dir": "in"}
        sig_jetzt = dict(sig_alt, inflow=False)          # Zufluss vorbei: Tor zu, Zeile bleibt gehalten
        latch = {"latch": {"m1|%s" % K.MARKT: {
            "matchId": "m1", "markt": K.MARKT, "stufe": 1, "gehaltenSeit": (now - timedelta(hours=2)).isoformat(),
            "zuletztAktiv": (now - timedelta(hours=2)).isoformat(), "kickoff": ko, "odd": 1.6,
            "haltePreis": 1.6, "punkte": K.buecher_punkte(sig_alt, {}, "home", now=now)}}}
        state = {"pending": {"m1": {"home": "Denmark", "away": "Wales", "kickoff": ko, "league": "X",
                                    "signals": {K.MARKT: sig_jetzt}}}}
        out = K.baue(state=state, consensus={"games": []}, track={}, streaks={"streaks": []},
                     now=now, latch_state=latch, anker={"anker": {}}, stake_wetten=[])
        gehalten = (out["stufe1"] + out["stufe2"])[0]["punkte"]
        tafel = [r for r in out["alleBewertet"] if r["matchId"] == "m1"][0]
        self.assertEqual(gehalten["punkte"], tafel["punkte"])
        self.assertEqual(gehalten["moeglich"], tafel["moeglich"])


if __name__ == "__main__":
    unittest.main()


class TestGuard(unittest.TestCase):
    def test_guard_faengt_den_vorfall(self):
        import uebersicht_integrity as U
        k = {"alleBewertet": [{"matchId": "1", "punkte": 9, "moeglich": 10}],
             "stufe1": [{"matchId": "1", "home": "Denmark", "away": "Wales",
                         "punkte": {"punkte": 10, "moeglich": 10}}], "stufe2": []}
        self.assertFalse(U.check_ein_spiel_ein_punktestand({"killer": k})["ok"])
        k["stufe1"][0]["punkte"] = {"punkte": 9, "moeglich": 10}
        self.assertTrue(U.check_ein_spiel_ein_punktestand({"killer": k})["ok"])
