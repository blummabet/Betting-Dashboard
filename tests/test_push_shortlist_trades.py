#!/usr/bin/env python3
"""test_push_shortlist_trades.py — 05.08.2026 (Lucas): „Heute spielenswert"-Plays in den Trades-
Channel. Reine Funktionen (Auswahl/Dedup/Format), kein Netz/kein node."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import push_shortlist_trades as P


def _play(key, side, conv, verdict="BET", price=0.6, league="UCL", htk=1.0, reasons=None, match=None):
    return {"key": key, "side": side, "conv": conv, "verdict": verdict, "price": price,
            "league": league, "htk": htk, "reasons": reasons or ["Steam läuft rein (+3pp)"],
            "match": match or (key + " match")}


class TestSelect(unittest.TestCase):
    def test_conv_gate_and_sort_and_cap(self):
        plays = [_play("a", "H", 7), _play("b", "H", 10), _play("c", "H", 8), _play("d", "H", 9)]
        sel = P.select(plays)
        self.assertEqual([p["conv"] for p in sel], [10, 9, 8])   # 7 raus, absteigend
        self.assertTrue(all(p["conv"] >= P.MIN_CONV for p in sel))

    def test_only_bet_and_fade(self):
        plays = [_play("a", "H", 10, verdict="NOBET"), _play("b", "H", 10, verdict="FADE")]
        sel = P.select(plays)
        self.assertEqual([p["key"] for p in sel], ["b"])

    def test_price_ceiling_skips_quasi_lock(self):
        plays = [_play("lock", "No", 10, price=0.97), _play("ok", "H", 10, price=0.80)]
        sel = P.select(plays)
        self.assertEqual([p["key"] for p in sel], ["ok"])   # 97¢ = Quasi-Lock raus

    def test_cap_max_plays(self):
        plays = [_play(str(i), "H", 10) for i in range(20)]
        self.assertEqual(len(P.select(plays)), P.MAX_PLAYS)


class TestFresh(unittest.TestCase):
    def test_new_is_fresh(self):
        sel = [_play("a", "H", 9)]
        self.assertEqual(P.fresh_plays(sel, {}), sel)

    def test_seen_same_conv_not_fresh(self):
        sel = [_play("a", "H", 9)]
        seen = {"a|H": {"conv": 9, "ts": "2026-08-05T10:00:00+00:00"}}
        self.assertEqual(P.fresh_plays(sel, seen), [])

    def test_conv_increase_repushes_same_or_lower_does_not(self):
        # 05.08.2026 (Lucas: „wenn 7->8 steigt, trotzdem schicken"): Re-Push nur bei neuem Hoechststand.
        seen = {"a|H": {"conv": 8, "ts": "2026-08-05T10:00:00+00:00"}}
        self.assertEqual(len(P.fresh_plays([_play("a", "H", 9)], seen)), 1)   # 8 -> 9: erneut schicken
        self.assertEqual(P.fresh_plays([_play("a", "H", 8)], seen), [])       # gleich: nicht
        self.assertEqual(P.fresh_plays([_play("a", "H", 8)], {"a|H": {"conv": 9}}), [])  # niedriger: nicht


class TestFormat(unittest.TestCase):
    def test_line_core_fields(self):
        ln = P._line(_play("mlb-a-b", "Yankees", 9, price=0.66, league="MLB", htk=2.0,
                           reasons=["großes Geld auf Yankees (70%)"], match="Yankees vs Red Sox"))
        self.assertIn("9/10 · BET", ln)
        self.assertIn("⚾", ln)                    # Sport-Icon
        self.assertIn("Yankees vs Red Sox", ln)
        self.assertIn("→ <b>Yankees</b> @66¢", ln)
        self.assertNotIn("LIVE", ln)              # htk>0 = nicht live

    def test_line_live_badge(self):
        ln = P._line(_play("ucl-x", "Yes", 10, htk=-1.5, match="ucl fen stu1"))
        self.assertIn("🔴 <b>LIVE</b>", ln)
        self.assertIn("ucl fen stu1", ln)         # Yes/No-Label aus dem Key (kein „Yes")

    def test_build_message_header_and_footer(self):
        msg = P.build_message([_play("a", "H", 10, match="A vs B")])
        self.assertIn("🔥 <b>Heute spielenswert</b>", msg)
        self.assertIn("Kein Auto-Bet", msg)
        self.assertIn("A vs B", msg)


if __name__ == "__main__":
    unittest.main()
