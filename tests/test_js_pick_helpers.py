#!/usr/bin/env python3
"""
test_js_pick_helpers.py — Anti-Drift-Test JS ↔ Python

Stellt sicher, dass _pick_helpers.js (Browser/Node) und pick_constants.json
(Python-Master) NIEMALS auseinanderlaufen. Beide müssen identische
DIRECTION_MAP + INCOMPATIBLE-Pairs definieren — sonst zeigt UI andere
Konflikte als Validator/Tracking.

Plus Funktional-Tests via Node-Runtime: wenn `node` verfügbar, werden die
JS-Helper auch tatsächlich ausgeführt und gegen Python-Erwartungen
abgeglichen.
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).parent.parent
JS_FILE = BASE / "_pick_helpers.js"
JSON_FILE = BASE / "pick_constants.json"


def _parse_js_direction_map() -> dict[str, str]:
    """Parse `const DIRECTION_MAP = Object.freeze({...})` aus _pick_helpers.js."""
    src = JS_FILE.read_text(encoding="utf-8")
    match = re.search(
        r"const DIRECTION_MAP = Object\.freeze\(\{(.*?)\}\);",
        src, re.DOTALL
    )
    if not match:
        raise AssertionError("DIRECTION_MAP-Block nicht gefunden in _pick_helpers.js")
    body = match.group(1)
    # Quote-Strings extrahieren: 'Heimsieg':                'homeStrong',
    pairs = re.findall(r"'([^']+)':\s*'([^']+)'", body)
    return {k: v for k, v in pairs}


def _parse_js_incompatible() -> set[tuple[str, str]]:
    """Parse `const INCOMPATIBLE = Object.freeze(new Set([...]))` aus _pick_helpers.js."""
    src = JS_FILE.read_text(encoding="utf-8")
    match = re.search(
        r"const INCOMPATIBLE = Object\.freeze\(new Set\(\[(.*?)\]\)\);",
        src, re.DOTALL
    )
    if not match:
        raise AssertionError("INCOMPATIBLE-Block nicht gefunden in _pick_helpers.js")
    body = match.group(1)
    pairs = re.findall(r"'([a-zA-Z]+)\|([a-zA-Z]+)'", body)
    return set(pairs)


class TestJSMirrorOfPickConstants(unittest.TestCase):
    """JS DIRECTION_MAP + INCOMPATIBLE müssen exakt pick_constants.json spiegeln."""

    @classmethod
    def setUpClass(cls):
        cls.json_data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
        cls.js_dir_map = _parse_js_direction_map()
        cls.js_incompat = _parse_js_incompatible()

    def test_direction_map_size(self):
        py_size = len(self.json_data["DIRECTION_MAP"])
        js_size = len(self.js_dir_map)
        self.assertEqual(js_size, py_size,
            f"JS hat {js_size} Markets, Python hat {py_size}")

    def test_direction_map_all_markets_match(self):
        py_map = self.json_data["DIRECTION_MAP"]
        for market, py_dir in py_map.items():
            with self.subTest(market=market):
                self.assertIn(market, self.js_dir_map,
                    f"Market '{market}' fehlt in _pick_helpers.js")
                js_dir = self.js_dir_map[market]
                self.assertEqual(js_dir, py_dir,
                    f"Drift bei '{market}': JS={js_dir} vs Python={py_dir}")

    def test_no_extra_js_markets(self):
        """JS darf KEINE Markets enthalten, die Python nicht kennt."""
        py_set = set(self.json_data["DIRECTION_MAP"].keys())
        js_set = set(self.js_dir_map.keys())
        extra = js_set - py_set
        self.assertEqual(extra, set(),
            f"JS hat Extra-Markets die Python nicht kennt: {extra}")

    def test_incompatible_pairs_match(self):
        # Python: List[List[str,str]] → Set[Tuple]
        py_pairs = {(a, b) for a, b in self.json_data["INCOMPATIBLE"]}
        # JS: Set[str] → wir extrahieren "a|b" → Tuple
        js_pairs = self.js_incompat
        self.assertEqual(js_pairs, py_pairs,
            f"INCOMPATIBLE-Pairs unterscheiden sich.\n"
            f"  In JS aber nicht Py: {js_pairs - py_pairs}\n"
            f"  In Py aber nicht JS: {py_pairs - js_pairs}")


class TestJSFunctionalViaNode(unittest.TestCase):
    """Wenn `node` verfügbar ist, exekutieren wir die Helper tatsächlich."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node nicht verfügbar — funktionale Tests übersprungen")

    def _run_node(self, script: str) -> str:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, cwd=str(BASE), timeout=10
        )
        self.assertEqual(result.returncode, 0,
            f"Node-Script fehlgeschlagen: {result.stderr}")
        return result.stdout.strip()

    def test_is_legitimate_pick(self):
        out = self._run_node("""
            const H = require('./_pick_helpers.js');
            console.log(H.isLegitimatePick(null));
            console.log(H.isLegitimatePick({market:'x'}));
            console.log(H.isLegitimatePick({trackingExcluded:true}));
            console.log(H.isLegitimatePick({trackingExcluded:false}));
        """)
        self.assertEqual(out.split("\n"), ["false", "true", "false", "true"])

    def test_are_pick_directions_incompatible(self):
        out = self._run_node("""
            const H = require('./_pick_helpers.js');
            console.log(H.areDirectionsIncompatible('homeStrong','awayStrong'));
            console.log(H.areDirectionsIncompatible('over','under'));
            console.log(H.areDirectionsIncompatible('over','over'));
            console.log(H.areDirectionsIncompatible(null, 'over'));
        """)
        self.assertEqual(out.split("\n"), ["true", "true", "false", "false"])

    def test_select_hero_prefers_safer_alt(self):
        """SWE-TUN-Szenario: saferAlt schlägt riskanten BET mit höherer Edge."""
        out = self._run_node("""
            const H = require('./_pick_helpers.js');
            const picks = [
                {market:'Heimsieg', verdict:'BET', edgePP:5},
                {market:'AH Heim −0.5', saferAltFor:'Heimsieg', verdict:'ABWÄGEN', edgePP:3},
                {market:'Über 2.5 Tore', verdict:'BET', edgePP:8},
            ];
            const hero = H.selectHero(picks);
            console.log(hero.market);
        """)
        self.assertEqual(out, "AH Heim −0.5")

    def test_find_conflicting_picks(self):
        """X2 (awayBias) konfligiert mit AH Heim (homeStrong)."""
        out = self._run_node("""
            const H = require('./_pick_helpers.js');
            const hero = {market:'Doppelte Chance — X2'};
            const others = [
                {market:'AH Heim −0.5'},
                {market:'Über 2.5 Tore'},
                {market:'Auswärtssieg'},
            ];
            const c = H.findConflictingPicks(hero, others);
            console.log(c.map(p=>p.market).join(','));
        """)
        self.assertEqual(out, "AH Heim −0.5")

    def test_select_hero_ignores_tracking_excluded(self):
        """trackingExcluded Picks dürfen nicht Hero werden."""
        out = self._run_node("""
            const H = require('./_pick_helpers.js');
            const picks = [
                {market:'Heimsieg', verdict:'BET', edgePP:9, trackingExcluded:true},
                {market:'Über 2.5 Tore', verdict:'ABWÄGEN', edgePP:5},
            ];
            const hero = H.selectHero(picks);
            console.log(hero ? hero.market : 'null');
        """)
        self.assertEqual(out, "Über 2.5 Tore")


class TestPythonJSAPISurfaceParity(unittest.TestCase):
    """JS-Helper exportiert dieselben Funktionsnamen wie pick_helpers.py-Pendant."""

    def test_js_exports_expected_functions(self):
        src = JS_FILE.read_text(encoding="utf-8")
        for fn in ("isLegitimatePick", "arePicksConflicting", "findConflictingPicks",
                   "heroSortKey", "heroSortCompare", "selectHero",
                   "getPickDirection", "areDirectionsIncompatible"):
            with self.subTest(fn=fn):
                self.assertIn(f"function {fn}(", src,
                    f"JS-Helper exportiert {fn} nicht")


if __name__ == "__main__":
    unittest.main()
