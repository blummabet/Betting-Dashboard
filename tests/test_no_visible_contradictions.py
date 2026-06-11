"""
test_no_visible_contradictions.py — Launch-Day-Bug 11.06.2026

Auf einer Card/Telegram-Nachricht dürfen NIE zwei widersprüchliche Picks
gleichzeitig sichtbar sein (z.B. CAN-BIH "Auswärtssieg" + "AH Heim −0.5").

Der Cross-Market-Filter in generate_wm_picks markiert den schwächeren Konflikt-
Pick als trackingExcluded. Der Dashboard-Renderer filtert das seit 06.06., aber
telegram_wm.py / generate_daily_tiktok.py taten es bis 11.06. NICHT → Widerspruch
im ersten WM-Telegram-Pick.

Dieser Test sichert die INVARIANTE auf Daten-Ebene ab: unter den sichtbaren
Picks (BET/ABWÄGEN, nicht trackingExcluded, nicht synthetic) eines Matches darf
es keine inkompatiblen Richtungen geben.
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))


class TestNoVisibleContradictions(unittest.TestCase):
    def test_no_incompatible_visible_picks(self):
        from pick_helpers import get_pick_direction as gd, are_directions_incompatible as inc

        wm_file = BASE / "wm2026-data.json"
        if not wm_file.exists():
            self.skipTest("wm2026-data.json fehlt")
        picks = json.loads(wm_file.read_text(encoding="utf-8")).get("picks", {})

        conflicts = []
        for mk, plist in picks.items():
            if not isinstance(plist, list):
                continue
            # Sichtbar = was Telegram/Cards/TikTok zeigen würden
            visible = [p for p in plist
                       if p.get("verdict") in ("BET", "ABWÄGEN")
                       and not p.get("trackingExcluded")
                       and not p.get("synthetic")]
            for i, a in enumerate(visible):
                da = gd(a.get("market"))
                if not da:
                    continue
                for b in visible[i + 1:]:
                    db = gd(b.get("market"))
                    if db and inc(da, db):
                        conflicts.append(f"{mk}: '{a.get('market')}' <> '{b.get('market')}'")

        self.assertEqual(conflicts, [],
            "Widersprüchliche Picks gleichzeitig sichtbar (Cross-Market-Konflikt "
            f"nicht ausgeblendet): {conflicts[:5]}")


if __name__ == "__main__":
    unittest.main()
