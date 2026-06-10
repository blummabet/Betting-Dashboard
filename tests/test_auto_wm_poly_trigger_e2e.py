"""
tests/test_auto_wm_poly_trigger_e2e.py — End-to-End Trigger-Logik mit Engine-Daten

Audit-Fix 08.06.2026: Auto-Trigger hatte bisher nur Constants-Tests.
Diese Suite simuliert den Filter-Pfad in find_trigger_candidates() mit
realistischen Engine-Daten — alle Hebel + Block-Gates + effective-Edge fallback.

Coverage:
  - Klassik BET ohne Engine-Felder → pass-through
  - Engine-Block-Gate: signalAdj ≤ -3pp → BLOCK
  - Engine-Downgrade: BET→ABWÄGEN + reason → BLOCK
  - Min-Positive-Signals bei ABWÄGEN → BLOCK
  - Hi-Conf-Bonus: ≥3 pos + ≥+3pp adj → -1pp Edge-Hürde
  - Steam-Lag-Immunität: kein Pre-Tournament-Hochsetzen
  - Pre-Tournament gestaffelte Schwelle (d=5/7/10)
  - effectiveEdge vs raw edge Fallback
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import auto_wm_poly_trigger as a


def _date_in(days: int) -> str:
    """ISO-Datum N Tage ab heute.

    FIX 10.06.2026 (Audit): Die Tests nutzten hartkodierte Daten (z.B.
    _date_in(3)), deren Tage-bis-Anpfiff sich mit fortschreitendem Kalender
    verschoben — am 10.06. war _date_in(3) 0 Tage entfernt und wurde vom
    Sicherheits-Gate "kein Kauf am Spieltag" korrekt geblockt, was die Tests
    fälschlich rot färbte. Jetzt relativ zu date.today(), reproduziert die
    ursprünglich gemeinten Lookahead-Distanzen stabil.
    """
    return (date.today() + timedelta(days=days)).isoformat()


def _make_fixture(**overrides):
    """Default fixture mit allen Pflicht-Feldern, plus Engine-Felder per overrides."""
    base = {
        "key":        "MEX-ZAF",
        "home":       "Mexico",  "away": "South Africa",
        "homeId":     "MEX",     "awayId": "ZAF",
        "date":       _date_in(16),   # 16d Lookahead = im normal-Modus
        "vol":        50000,
        "hasPinnacle": True,
        "dataQuality": "full",
        # Markt: HW. Edge raw 6pp, Pinn-Fair 0.60, Poly 0.50 (akzeptable Range).
        "edge_hw":    6.0,
        "poly_hw":    0.50,
        "fair_hw":    0.60,
        "verdict_hw": "BET",
        # Engine-Felder default leer (None) — simuliert alten Pick ohne Engine
        "signalAdj_hw":          None,
        "signalPos_hw":          None,
        "effectiveEdge_hw":      None,
        "engineDowngrade_hw":    None,
        # Andere Märkte aus weg (kein Edge)
        "edge_dr": None, "edge_aw": None, "edge_o25": None, "edge_u25": None,
        "verdict_dr": None, "verdict_aw": None, "verdict_o25": None, "verdict_u25": None,
        "poly_dr": 0.20, "poly_aw": 0.15, "poly_o25": 0.5, "poly_u25": 0.5,
        "fair_dr": 0.22, "fair_aw": 0.18, "fair_o25": 0.5, "fair_u25": 0.5,
        "steamLag":   False,
    }
    base.update(overrides)
    return base


def _is_in_candidates(fix):
    """Run find_trigger_candidates und prüf ob die HW-Wette drin ist."""
    cands = a.find_trigger_candidates([fix], placed_keys=set())
    return any(c["market"] == "Heimsieg" for c in cands)


class TestPassThrough(unittest.TestCase):
    """Picks die durchgehen sollen — keine Engine-Restriktion."""

    def test_classic_bet_no_engine_data(self):
        """Alter Pick ohne Engine-Felder: edge=6pp, BET, threshold=4 (normal) → PASS."""
        fix = _make_fixture()
        # Datum nah genug für normal-threshold
        fix["date"] = _date_in(3)   # < pre_tournament_days
        self.assertTrue(_is_in_candidates(fix))

    def test_engine_neutral_pass(self):
        """Engine neutral (+1.5pp adj, 2 pos) → PASS."""
        fix = _make_fixture(
            date=_date_in(3),
            signalAdj_hw=1.5, signalPos_hw=2,
            effectiveEdge_hw=7.5,
        )
        self.assertTrue(_is_in_candidates(fix))


class TestEngineBlockGate(unittest.TestCase):
    """ENGINE_BLOCK_ADJ_PP (-3pp) sollte triggern."""

    def test_engine_warning_blocks(self):
        """signalAdj = -3.5pp → BLOCK trotz hohem raw edge."""
        fix = _make_fixture(
            date=_date_in(3),
            edge_hw=8.0,
            signalAdj_hw=-3.5, signalPos_hw=0,
            effectiveEdge_hw=4.5,
        )
        self.assertFalse(_is_in_candidates(fix))

    def test_engine_boundary_minus_3(self):
        """Exakt -3.0pp → BLOCK (≤ Schwelle)."""
        fix = _make_fixture(
            date=_date_in(3),
            signalAdj_hw=-3.0, signalPos_hw=0,
            effectiveEdge_hw=3.0,
        )
        self.assertFalse(_is_in_candidates(fix))

    def test_engine_minus_2_9_passes(self):
        """-2.9pp passt durch (knapp über Schwelle)."""
        fix = _make_fixture(
            date=_date_in(3),
            edge_hw=8.0,
            signalAdj_hw=-2.9, signalPos_hw=2,   # 2 pos für BET-Verdict
            effectiveEdge_hw=5.1,
            verdict_hw="BET",
        )
        self.assertTrue(_is_in_candidates(fix))


class TestEngineDowngradeBlock(unittest.TestCase):
    """Engine-Downgrade BET→ABWÄGEN → BLOCK."""

    def test_downgraded_abwaegen_blocks(self):
        """verdict=ABWÄGEN + downgrade_reason → BLOCK."""
        fix = _make_fixture(
            date=_date_in(3),
            verdict_hw="ABWÄGEN",
            engineDowngrade_hw="Engine: nur 1 positives Signal, Mindest-Threshold 2 für BET",
            signalAdj_hw=0.5, signalPos_hw=1,
            effectiveEdge_hw=6.5,
        )
        self.assertFalse(_is_in_candidates(fix))

    def test_abwaegen_without_downgrade_min_pos(self):
        """verdict=ABWÄGEN ohne downgrade, signalPos<2 → BLOCK (min_pos-Gate)."""
        fix = _make_fixture(
            date=_date_in(3),
            verdict_hw="ABWÄGEN",
            signalAdj_hw=0.5, signalPos_hw=1,   # < min_pos
            effectiveEdge_hw=6.5,
        )
        self.assertFalse(_is_in_candidates(fix))

    def test_abwaegen_with_enough_pos_passes(self):
        """verdict=ABWÄGEN + 2+ pos signals → PASS (genug Konfidenz)."""
        fix = _make_fixture(
            date=_date_in(3),
            verdict_hw="ABWÄGEN",
            signalAdj_hw=1.0, signalPos_hw=2,
            effectiveEdge_hw=7.0,
        )
        self.assertTrue(_is_in_candidates(fix))


class TestHiConfBonus(unittest.TestCase):
    """Hi-Conf-Bonus senkt Edge-Schwelle um 1pp wenn ≥3 pos + ≥+3pp adj."""

    def test_hi_conf_lowers_threshold(self):
        """edge=4.5pp wäre unter normal-Schwelle 4.0pp PRE_TOURNAMENT_FAR_DAYS
        bei d=10 würde es 6.0pp, aber Hi-Conf senkt das."""
        fix = _make_fixture(
            date=_date_in(7),   # 7d → pre-tournament intermediate
            edge_hw=4.8,
            signalAdj_hw=3.5, signalPos_hw=3,
            effectiveEdge_hw=4.8,
        )
        # Bei d=7 normal threshold = 4 + 2/5 * (6-4) = 4.8pp
        # Hi-Conf -1pp → 3.8pp → 4.8 > 3.8 → PASS
        self.assertTrue(_is_in_candidates(fix))

    def test_no_hi_conf_only_2_pos(self):
        """Nur 2 positive Signale (statt 3) → kein Bonus."""
        fix = _make_fixture(
            date=_date_in(7),
            edge_hw=3.5,
            signalAdj_hw=3.5, signalPos_hw=2,   # < 3
            effectiveEdge_hw=3.5,
        )
        # normal threshold bei d=7 = 4.8pp, kein Bonus → 3.5 < 4.8 → BLOCK
        self.assertFalse(_is_in_candidates(fix))


class TestSteamLagImmunity(unittest.TestCase):
    """Steam-Lag-Picks dürfen nicht von Pre-Tournament hochgezogen werden."""

    def test_steam_lag_at_pre_tournament_far(self):
        """Pre-Tournament-Schwelle wäre 6pp bei d=10. Steam-Lag bleibt bei 3pp."""
        fix = _make_fixture(
            date=_date_in(12),   # ~12 Tage = pre_tournament_far
            edge_hw=3.5,         # über STEAM_LAG_EDGE_PP (3.0) aber unter PRE_TOURNAMENT (6.0)
            steamLag=True,
        )
        self.assertTrue(_is_in_candidates(fix))

    def test_no_steam_lag_at_pre_tournament_blocks(self):
        """Selber edge, kein steam_lag → BLOCKIERT (würde normal pre-tournament threshold)."""
        fix = _make_fixture(
            date=_date_in(12),
            edge_hw=3.5,
            steamLag=False,
        )
        # bei d≈12 → 6.0pp Schwelle, 3.5 < 6.0 → BLOCK
        self.assertFalse(_is_in_candidates(fix))


class TestPreTournamentStaggered(unittest.TestCase):
    """Gestaffelte Pre-Tournament-Schwelle (Hebel 2)."""

    def test_d5_uses_base_threshold(self):
        """d=5 = PRE_TOURNAMENT_DAYS-Grenze → base 4pp."""
        fix = _make_fixture(date=_date_in(5), edge_hw=4.5)
        # Bei Tag 13 = 5 Tage → base
        self.assertTrue(_is_in_candidates(fix))

    def test_d10_uses_far_threshold(self):
        """d=10 → 6pp Schwelle."""
        fix = _make_fixture(date=_date_in(10), edge_hw=5.0)
        # 10 Tage → 6pp → 5.0 < 6 → BLOCK
        self.assertFalse(_is_in_candidates(fix))

    def test_d10_with_enough_edge_passes(self):
        fix = _make_fixture(date=_date_in(10), edge_hw=6.5)
        # Aber bei d=10 ist threshold 6pp → 6.5 > 6 → PASS — leider hier dataQuality bremst
        # Actually verdict_hw="BET" mit dataQuality="full" → normal threshold (4)
        # Da bei d=10 pre-tournament → 6pp. Edge 6.5 > 6 → PASS
        self.assertTrue(_is_in_candidates(fix))


class TestEffectiveEdgeFallback(unittest.TestCase):
    """effectiveEdge wird genutzt wenn vorhanden, sonst raw edge."""

    def test_uses_effective_edge_when_lower(self):
        """raw=8 würde passen, effective=2 (engine zog runter) → BLOCK."""
        fix = _make_fixture(
            date=_date_in(3),
            edge_hw=8.0,
            effectiveEdge_hw=2.0,   # < threshold
            signalAdj_hw=-6.0,      # would also block via gate
            signalPos_hw=0,
        )
        self.assertFalse(_is_in_candidates(fix))

    def test_falls_back_to_raw_when_no_effective(self):
        """effectiveEdge=None → raw edge wird genutzt."""
        fix = _make_fixture(
            date=_date_in(3),
            edge_hw=6.0,
            effectiveEdge_hw=None,
        )
        self.assertTrue(_is_in_candidates(fix))


if __name__ == "__main__":
    unittest.main(verbosity=2)
