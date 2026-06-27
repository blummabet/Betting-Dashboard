#!/usr/bin/env python3
"""
test_architecture_drift.py — Anti-Drift-Wächter (26.06.2026, Lucas: „alles sauber, ohne Wenn und
Aber"). Hält die Konsolidierung dauerhaft: schlägt fehl, wenn jemand wieder lokal hardcodet statt
die Single-Source-Schicht (cocobet_dataset, sharp_signals.base.market_side) zu nutzen.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


class TestNoDuplication(unittest.TestCase):
    def test_no_local_market_side(self):
        """market_side lebt NUR in sharp_signals/base.py — kein Signal definiert es neu."""
        offenders = [p.name for p in (REPO / "sharp_signals").glob("*.py")
                     if p.name != "base.py" and "def _market_side" in p.read_text(encoding="utf-8")
                     or (p.name != "base.py" and "def market_side" in p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [], f"market_side dupliziert in: {offenders} → base.market_side nutzen")

    def test_no_raw_dataset_env(self):
        """Niemand liest COCOBET_DATASET roh aus — nur cocobet_dataset (Quelle) + generate_liga_picks
        (Setter). Sonst → cocobet_dataset.is_liga()/active_dataset() nutzen."""
        allow = {"cocobet_dataset.py", "generate_liga_picks.py"}
        pat = re.compile(r'environ\.get\(\s*["\']COCOBET_DATASET')
        offenders = [p.name for p in REPO.glob("*.py")
                     if p.name not in allow and pat.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [], f"Rohes COCOBET_DATASET in: {offenders} → cocobet_dataset nutzen")

    def test_league_map_single_source(self):
        """Die Liga-Liga-IDs gibt es an EINER Stelle (cocobet_dataset.leagues()); build_liga_data
        darf eine reiche Map (id+name+flag) haben, aber die IDs müssen übereinstimmen."""
        import cocobet_dataset as D
        import build_liga_data as B
        ids_dataset = set(D.leagues().values())
        ids_builder = {cfg["apif_id"] for cfg in B.LEAGUES_TOP5.values()}
        self.assertEqual(ids_dataset, ids_builder,
                         "Liga-IDs driften zwischen cocobet_dataset.leagues() und build_liga_data.LEAGUES_TOP5")


if __name__ == "__main__":
    unittest.main()
