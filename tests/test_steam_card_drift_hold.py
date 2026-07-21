"""21.07.2026 (Lucas, MLS Colorado) — steamMovePP ist DRIFT-BEREINIGT. Wenn die Roh-Quote fast
steht (move_raw ≈ 0), der Markt aber wegdriftete, ist +move_pp ein „Halten gegen den Markt", KEIN
Quotensturz. Die Card las sich vorher „Pinnacle 2.10→2.09 (Sharp-Money-Drop +3.5pp)", als wären die
Quoten um 3.5pp gefallen. Diese Tests fixieren die ehrliche Formulierung + dass die Roh-pp mitkommt."""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import generate_wm_picks as G  # noqa: E402


def _pick(move_pp, move_raw_pp, open_odd=2.10, cur_odd=2.09):
    return {
        "trigger": {"key": "hw", "label": "Heimsieg", "open": open_odd, "cur": cur_odd,
                    "move_pp": move_pp, "move_raw_pp": move_raw_pp, "sweet": False, "kind": "1x2"},
        "market": "Heimsieg", "entry_odd": cur_odd, "book": "pini",
    }


class TestDriftHoldWording(unittest.TestCase):
    def test_drift_hold_ist_ehrlich(self):
        """Quote hielt (0.2pp roh), Signal +3.5pp drift-relativ → NICHT als Quotensturz verkaufen."""
        card = G._steam_card_pick({}, _pick(move_pp=3.5, move_raw_pp=0.2))
        self.assertIn("hielt", card["info"])
        self.assertIn("wegdriftete", card["info"])
        self.assertNotIn("Sharp-Money-Drop +3.5pp", card["info"],
                         "darf nicht so tun, als wäre die Quote um 3.5pp gefallen")
        self.assertEqual(card["steamMoveRawPP"], 0.2, "Roh-pp muss für die Anzeige mitkommen")

    def test_echter_drop_bleibt_klassisch(self):
        """Quote fiel echt (4.5pp roh ≈ 3.2pp bereinigt) → klassische Sharp-Money-Drop-Formulierung."""
        card = G._steam_card_pick({}, _pick(move_pp=3.2, move_raw_pp=4.5, open_odd=2.78, cur_odd=2.47))
        self.assertIn("Sharp-Money-Drop", card["info"])
        self.assertNotIn("hielt", card["info"])

    def test_roh_pp_immer_gespeichert(self):
        card = G._steam_card_pick({}, _pick(move_pp=3.0, move_raw_pp=3.1))
        self.assertIn("steamMoveRawPP", card)


if __name__ == "__main__":
    unittest.main()
