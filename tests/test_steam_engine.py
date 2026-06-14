"""
test_steam_engine.py — Steam-Following-Kern (Lucas' echtes Modell, 14.06.2026).
Trigger = Pini-Drop; aus starkem Favoriten-Drop wird eine Handicap-Linie in der
1,5-1,8-Region abgeleitet (ESP 1,13→1,09 → ESP −2 @1,60).
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import steam_engine as se  # noqa: E402


class TestDetect(unittest.TestCase):
    def test_drop_triggers(self):
        snap = {"hw": 1.70, "dr": 3.5, "aw": 5.0, "odds_open": {"hw": 1.90}}
        trigs = se.detect_steam(snap)
        hw = [t for t in trigs if t["key"] == "hw"]
        self.assertTrue(hw)
        self.assertAlmostEqual(hw[0]["move_pp"], round((1/1.70 - 1/1.90) * 100, 1), places=1)
        self.assertEqual(hw[0]["kind"], "1x2")

    def test_no_move_no_trigger(self):
        snap = {"hw": 1.88, "odds_open": {"hw": 1.90}}   # ~0.6pp < 3
        self.assertEqual(se.detect_steam(snap), [])

    def test_drift_up_not_triggered(self):
        snap = {"hw": 2.10, "odds_open": {"hw": 1.90}}   # Quote gestiegen → kein Steam
        self.assertEqual([t for t in se.detect_steam(snap) if t["key"] == "hw"], [])

    def test_ou_steam_detected(self):
        snap = {"o25": 1.80, "odds_open": {"o25": 2.05}}
        trigs = se.detect_steam(snap)
        self.assertTrue(any(t["key"] == "o25" for t in trigs))


class TestDerive(unittest.TestCase):
    def test_heavy_favorite_to_handicap(self):
        # ESP 1,13 → 1,09, AH-Leiter vorhanden → AH −2 @1,60 (in Zielzone, nächste an 1,65)
        snap = {"hw": 1.09, "odds_open": {"hw": 1.13},
                "ahH_n050": 1.11, "ahH_n075": 1.13, "ahH_n100": 1.11,
                "ahH_n150": 1.37, "ahH_n200": 1.60}
        pick = se.build_steam_pick(snap)
        self.assertIsNotNone(pick)
        self.assertTrue(pick["derived"])
        self.assertEqual(pick["market"], "AH Heim −2")
        self.assertEqual(pick["entry_odd"], 1.60)

    def test_moderate_favorite_straight_side_softbook(self):
        # mäßiger Drop, gerade Seite bettbar → Softbook-Quote bevorzugt
        snap = {"hw": 1.70, "public_hw": 1.78, "odds_open": {"hw": 1.90}}
        pick = se.build_steam_pick(snap)
        self.assertFalse(pick["derived"])
        self.assertEqual(pick["market"], "Heimsieg")
        self.assertEqual(pick["book"], "soft")
        self.assertEqual(pick["entry_odd"], 1.78)
        self.assertGreater(pick["soft_lagging"], 0)   # Soft hinkt nach = Value

    def test_away_favorite_without_ladder_skipped(self):
        # Auswärts-Favorit kurz, keine Minus-Leiter → kein Pick (sauber None)
        snap = {"aw": 1.20, "odds_open": {"aw": 1.30}}
        self.assertIsNone(se.build_steam_pick(snap))

    def test_ou_pick_uses_softbook(self):
        snap = {"o25": 1.80, "public_o25": 1.90, "odds_open": {"o25": 2.05}}
        pick = se.build_steam_pick(snap)
        self.assertEqual(pick["market"], "Über 2.5 Tore")
        self.assertEqual(pick["entry_odd"], 1.90)


class TestLifecycleAndCLV(unittest.TestCase):
    def test_late_entry_flag_by_days(self):
        snap = {"hw": 1.70, "public_hw": 1.74, "odds_open": {"hw": 1.90}}
        early = se.build_steam_pick(snap, days_to_ko=9)
        late = se.build_steam_pick(snap, days_to_ko=1)
        self.assertFalse(early["lateEntry"])
        self.assertTrue(late["lateEntry"])

    def test_late_when_soft_converged(self):
        # Soft schon konvergiert (kein Lag) → lateEntry trotz früh
        snap = {"hw": 1.70, "public_hw": 1.70, "odds_open": {"hw": 1.90}}
        pick = se.build_steam_pick(snap, days_to_ko=9)
        self.assertTrue(pick["lateEntry"])

    def test_clv_record_shape(self):
        snap = {"hw": 1.70, "public_hw": 1.78, "odds_open": {"hw": 1.90}}
        pick = se.build_steam_pick(snap, days_to_ko=5)
        rec = se.clv_record(snap, pick, "ESP-SAU", "2026-06-14T12:00:00Z")
        self.assertEqual(rec["fixture"], "ESP-SAU")
        self.assertEqual(rec["entry_odd"], 1.78)
        self.assertEqual(rec["pini_open"], 1.90)
        self.assertIsNone(rec["closing_odd"])   # wird beim Resolve nachgetragen


if __name__ == "__main__":
    unittest.main()
