#!/usr/bin/env python3
"""
test_poly_mls_name_resolution.py — Polymarket-MLS Namens-Zuordnung (12.07.2026, Lucas).

MLS ist auf Polymarket (Woche 25, Spiele ab 17.07.). Polymarket nennt die Klubs ANDERS als
API-Football („LA Galaxy", „Sporting KC", „CF Montréal", „D.C. United", „NYCFC"). Ohne robuste
Zuordnung liefe die ganze Poly-Kette still ins Leere (keine Edges, keine smart_money-Signale).

GELD-KRITISCH: „Los Angeles FC" normalisiert zu „los angeles" (FC ist Rechtsform-Stoppwort) und
hätte per Teilstring auf „Los Angeles Galaxy" gematcht → Trade auf das FALSCHE LA-Team.

ISOLATION: fetch_wm_poly_prices baut `_ACTIVE_NAME_MAP` beim IMPORT aus der Env → wir dürfen
COCOBET_DATASET nicht im Test-Prozess setzen (das verseuchte die Liga-Tests). Darum Subprozess.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent

# Realistische Polymarket-/TheOddsAPI-Schreibweisen → erwartete API-Football-Team-ID
POLY_NAMES = {
    "LA Galaxy": "1605", "Los Angeles FC": "1616", "LAFC": "1616",
    "Sporting KC": "1611", "NYCFC": "1604", "D.C. United": "1615", "CF Montréal": "1614",
    "St. Louis City SC": "20787", "San Diego FC": "25484", "Charlotte FC": "18310",
    "Austin FC": "16489", "Inter Miami CF": "9568", "Columbus Crew SC": "1613",
    "Vancouver Whitecaps FC": "1603", "Seattle Sounders FC": "1595",
    "Houston Dynamo FC": "1600", "Chicago Fire FC": "1607", "Nashville SC": "9569",
    "Toronto FC": "1601", "New York Red Bulls": "1602", "Atlanta United": "1608",
    "Philadelphia Union": "1599", "New England Revolution": "1609",
    "Portland Timbers": "1617", "Colorado Rapids": "1610", "Real Salt Lake": "1606",
    "FC Dallas": "1597", "FC Cincinnati": "2242", "Minnesota United": "1612",
    "Orlando City": "1598", "San Jose Earthquakes": "1596",
    # Unbekannt → muss None geben (nie raten, wenn Geld dranhängt)
    "Bayern München": None,
}

_SCRIPT = """
import json, sys
import fetch_wm_poly_prices as P
names = json.loads(sys.argv[1])
print(json.dumps({n: P.resolve_team_id(n) for n in names}))
"""


def _resolve_in_subprocess(names: list) -> dict:
    """Auflösung im eigenen Prozess mit COCOBET_DATASET=mls (kein Env-Leak in andere Tests)."""
    res = subprocess.run(
        [sys.executable, "-c", _SCRIPT, json.dumps(names)],
        cwd=str(REPO), capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "COCOBET_DATASET": "mls",
             "COCOBET_PROFILE": "mls_default", "HOME": "/tmp"},
    )
    if res.returncode != 0:
        raise AssertionError(f"Subprozess fehlgeschlagen: {res.stderr[-800:]}")
    return json.loads(res.stdout.strip().splitlines()[-1])


class TestPolyMLSNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.got = _resolve_in_subprocess(list(POLY_NAMES))

    def test_all_mls_clubs_resolve(self):
        wrong = {n: (self.got.get(n), exp) for n, exp in POLY_NAMES.items()
                 if self.got.get(n) != exp}
        self.assertEqual(wrong, {}, f"Falsch/nicht zugeordnet (ist, soll): {wrong}")

    def test_la_collision_is_prevented(self):
        """GELD-KRITISCH: die beiden LA-Teams dürfen NIE auf dieselbe ID fallen."""
        lafc, galaxy = self.got.get("Los Angeles FC"), self.got.get("LA Galaxy")
        self.assertEqual(lafc, "1616")
        self.assertEqual(galaxy, "1605")
        self.assertNotEqual(lafc, galaxy)

    def test_unknown_name_returns_none(self):
        self.assertIsNone(self.got.get("Bayern München"))


if __name__ == "__main__":
    unittest.main()
