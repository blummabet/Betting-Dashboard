"""26.09.2026 — Ebene 2 zeigte „−70 % UG −119 % bei n6" und „+59 % UG +23 % bei n9 · trägt".

Zwei Fehler an derselben Zeile: eine Untergrenze unter −100 % (gibt es nicht) und ein Urteil
„traegt" aus neun Wetten, gefaellt im Frontend ohne Mindestzahl.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import killer as K
import uebersicht_integrity as U


def _l(p, m, odd, wins, losses):
    return ([{"odd": odd, "punkte": p, "moeglich": m, "win": True}] * wins
            + [{"odd": odd, "punkte": p, "moeglich": m, "win": False}] * losses)


class TestPunkteBilanz(unittest.TestCase):
    def test_untergrenze_nie_unter_minus_100(self):
        b = K.punkte_bilanz(_l(7, 13, 4.0, 1, 5))
        self.assertGreaterEqual(b[0]["roiLb"], -1.0)

    def test_neun_treffer_sind_kein_urteil(self):
        b = K.punkte_bilanz(_l(6, 7, 1.6, 8, 1))
        self.assertGreater(b[0]["roiLb"], 0)
        self.assertEqual(b[0]["urteil"], "zu_wenige")

    def test_ab_mindestzahl_urteilt_der_produzent(self):
        b = K.punkte_bilanz(_l(8, 10, 1.9, 30, 10))
        self.assertEqual(b[0]["urteil"], "traegt")
        b = K.punkte_bilanz(_l(8, 10, 1.9, 15, 25))
        self.assertEqual(b[0]["urteil"], "traegt_nicht")


class TestGuards(unittest.TestCase):
    def test_guard_faengt_die_minus_119(self):
        ctx = {"killer": {"punkteBilanz": [{"punkte": 7, "moeglich": 13, "n": 6, "roi": -0.7, "roiLb": -1.1946}]}}
        self.assertFalse(U.check_keine_untergrenze_unter_minus_100(ctx)["ok"])

    def test_guard_faengt_traegt_unter_mindestzahl(self):
        ctx = {"killer": {"punkteBilanz": [{"punkte": 6, "moeglich": 7, "n": 9, "roiLb": 0.23,
                                             "urteil": "traegt", "minN": 30}]}}
        self.assertFalse(U.check_punkte_urteil_hat_seine_mindestzahl(ctx)["ok"])

    def test_guard_faengt_fehlendes_urteil(self):
        ctx = {"killer": {"punkteBilanz": [{"punkte": 6, "moeglich": 7, "n": 9, "roiLb": 0.23}]}}
        self.assertFalse(U.check_punkte_urteil_hat_seine_mindestzahl(ctx)["ok"])

    def test_sauber_ist_gruen(self):
        b = K.punkte_bilanz(_l(6, 7, 1.6, 8, 1) + _l(7, 13, 4.0, 1, 5))
        ctx = {"killer": {"punkteBilanz": b}}
        self.assertTrue(U.check_keine_untergrenze_unter_minus_100(ctx)["ok"])
        self.assertTrue(U.check_punkte_urteil_hat_seine_mindestzahl(ctx)["ok"])


if __name__ == "__main__":
    unittest.main()
