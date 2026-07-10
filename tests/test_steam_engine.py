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

    def test_implausible_full_opening_no_fake_steam(self):
        # 09.07.2026 (Lucas, MLS Chicago–Vancouver): Opening 1.17/1.01/1.17 (Overround 270%,
        # Platzhalter) erzeugte einen erfundenen +25pp-Move → Fake-Auswärtssieg-Pick. Ein
        # VOLLES, implausibles 1X2-Opening darf keinen 1X2-Steam auslösen.
        snap = {"hw": 2.95, "dr": 3.69, "aw": 2.27,
                "odds_open": {"hw": 1.17, "dr": 1.01, "aw": 1.17}}
        trigs = [t for t in se.detect_steam(snap) if t["kind"] == "1x2"]
        self.assertEqual(trigs, [])

    def test_implausible_current_snap_no_fake_steam(self):
        # 09.07.2026 (Lucas, MLS Nashville–Atlanta): umgekehrter Fall — der AKTUELLE Satz ist der
        # Platzhalter (1.04/1.02/1.04, Overround 290%), das Opening (1.36/4.6/7.0) ist real →
        # erfundener 1.36→1.04-Move. Auch das darf keinen 1X2-Steam auslösen.
        snap = {"hw": 1.04, "dr": 1.02, "aw": 1.04,
                "odds_open": {"hw": 1.36, "dr": 4.6, "aw": 7.0}}
        trigs = [t for t in se.detect_steam(snap) if t["kind"] == "1x2"]
        self.assertEqual(trigs, [])

    def test_partial_opening_still_triggers(self):
        # Teil-Opening (nur eine Seite, wie in echten Snaps/Tests) wird NICHT beurteilt → feuert.
        snap = {"hw": 1.70, "dr": 3.5, "aw": 5.0, "odds_open": {"hw": 1.90}}
        self.assertTrue(any(t["key"] == "hw" for t in se.detect_steam(snap)))

    def test_plausible_full_opening_triggers(self):
        # Echter Move mit plausiblem Voll-Opening (Overround ~1.06) → Steam feuert normal.
        snap = {"hw": 2.95, "dr": 3.40, "aw": 2.60,
                "odds_open": {"hw": 2.70, "dr": 3.30, "aw": 2.90}}
        self.assertTrue(any(t["key"] == "aw" for t in se.detect_steam(snap)))


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


class TestMarketDriftDetrend(unittest.TestCase):
    def test_market_wide_under_drift_removed(self):
        # 6 Spiele driften ALLE ~5pp Richtung Under (o25 von 1.80→~2.0, Markt-Drift).
        # Ein 7. Spiel driftet 5pp wie der Rest → NACH Detrend kein spielspez. Steam.
        odds = {}
        for i in range(6):
            odds[f"T{i}-X{i}"] = {"u25": 1.75, "o25": 2.05, "hw": 1.9,
                                  "odds_open": {"u25": 1.90, "o25": 1.80, "hw": 1.9}}
        drift = se.market_drift(odds, min_samples=3)
        # u25 ist markt-weit gefallen (Geld auf Under) → Drift positiv
        self.assertIn("u25", drift)
        self.assertGreater(drift["u25"], 3)
        # Ein Spiel das GENAU wie der Markt driftet → kein Trigger nach Detrend
        snap = {"u25": 1.75, "o25": 2.05, "odds_open": {"u25": 1.90, "o25": 1.80}}
        self.assertEqual(se.detect_steam(snap, drift=drift), [])

    def test_game_specific_excess_still_triggers(self):
        # Markt driftet Under ~+4pp; DIESES Spiel driftet Heim deutlich stärker als Markt
        odds = {f"T{i}-X{i}": {"u25": 1.75, "odds_open": {"u25": 1.90}} for i in range(6)}
        drift = se.market_drift(odds, min_samples=3)
        snap = {"hw": 1.55, "odds_open": {"hw": 1.75}}   # Heim +X über Markt-Drift (hw≈0)
        trigs = se.detect_steam(snap, drift=drift)
        self.assertTrue(any(t["key"] == "hw" for t in trigs))


class TestLongshotCeiling(unittest.TestCase):
    """Variante A (20.06.2026): Quote > max_trigger_odds → kein Steam-Trigger.
    Außenseiter-Move (Haiti 51→22 gg. Brasilien) ist Rauschen, keine Karte."""

    def _bra_hti(self):
        # aw = Haiti-Longshot 51→22 (triggert via Drift +3.8pp), bttsY Mainline 2.75→2.08
        return ({"odds_open": {"aw": 51.0, "bttsY": 2.75}, "aw": 22.0, "bttsY": 2.08},
                {"aw": -1.2})  # snap, drift

    def test_longshot_blocked_by_default_ceiling(self):
        snap, drift = self._bra_hti()
        labels = [t["label"] for t in se.detect_steam(snap, drift=drift)]
        self.assertNotIn("Auswärtssieg", labels)           # Longshot @22 raus
        self.assertIn("Beide Teams treffen — Ja", labels)   # Mainline bleibt

    def test_longshot_triggers_without_ceiling(self):
        # Kontrolle: ohne Ceiling würde der Longshot triggern (sonst testen wir nichts)
        snap, drift = self._bra_hti()
        labels = [t["label"] for t in se.detect_steam(snap, drift=drift, max_trigger_odds=999)]
        self.assertIn("Auswärtssieg", labels)

    def test_build_steam_picks_drops_longshot_card(self):
        snap, drift = self._bra_hti()
        markets = [p["market"] for p in se.build_steam_picks(snap, drift=drift, min_odds=1.35)]
        self.assertEqual(markets, ["Beide Teams treffen — Ja"])  # kein X2/Auswärts

    def test_mainline_favorite_not_affected(self):
        # Favorit @1.14 (weit unter Ceiling) triggert weiter normal
        snap = {"odds_open": {"hw": 1.30}, "hw": 1.14}
        labels = [t["label"] for t in se.detect_steam(snap)]
        self.assertIn("Heimsieg", labels)


class TestSoftConfirmation(unittest.TestCase):
    def test_soft_followed_confirmed(self):
        # Pini 1.90→1.70 (Heim). Soft-Konsens Opening 1.95 → jetzt 1.78 = gefolgt → bestätigt.
        snap = {"hw": 1.70, "public_hw": 1.78, "public_hw_open": 1.95,
                "odds_open": {"hw": 1.90}}
        p = se.build_steam_pick(snap)
        self.assertTrue(p["soft_confirmed"])
        self.assertGreater(p["soft_follow_pp"], 1.5)

    def test_soft_not_followed_not_confirmed(self):
        # Soft kaum bewegt (1.93→1.92) obwohl Pini fiel → nicht bestätigt, aber Lag = Value.
        snap = {"hw": 1.70, "public_hw": 1.92, "public_hw_open": 1.93,
                "odds_open": {"hw": 1.90}}
        p = se.build_steam_pick(snap)
        self.assertFalse(p["soft_confirmed"])
        self.assertGreater(p["soft_lagging"], 0)

    def test_no_soft_opening_no_confirm(self):
        # Ohne Soft-Opening kann nicht bestätigt werden (nur Momentaufnahme-Lag).
        snap = {"hw": 1.70, "public_hw": 1.78, "odds_open": {"hw": 1.90}}
        p = se.build_steam_pick(snap)
        self.assertIsNone(p["soft_follow_pp"])
        self.assertFalse(p["soft_confirmed"])


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
