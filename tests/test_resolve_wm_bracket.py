#!/usr/bin/env python3
"""
test_resolve_wm_bracket.py — KO-Bracket-Auflösung (25.06.2026, Lucas: „sobald beide Teams feststehen
kann er schon eine Card generieren"). Prüft: Gruppenplatz löst NUR bei kompletter Gruppe; best_third
+ W-Refs bleiben TBD; kickoff UTC korrekt aus Venue-TZ; inkrementell + idempotent.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import resolve_wm_bracket as R  # noqa: E402

VENUES = {"los_angeles": {"city": "Los Angeles", "tz_offset_h_utc": -7},
          "boston":      {"city": "Boston",      "tz_offset_h_utc": -4}}

# Mini-Bracket: 1 R32-Spiel mit zwei Gruppenplätzen, 1 mit best_third, 1 R16 mit W-Refs
BRACKET = {
    "round_of_32": {
        "M73": {"matchNo": 73, "date": "2026-06-28", "kickoff_local": "12:00",
                "venue_id": "los_angeles",
                "side_a": {"type": "group_position", "group": "A", "position": 2},
                "side_b": {"type": "group_position", "group": "B", "position": 2},
                "winner_to": "M90"},
        "M74": {"matchNo": 74, "date": "2026-06-29", "kickoff_local": "16:30",
                "venue_id": "boston",
                "side_a": {"type": "group_position", "group": "A", "position": 1},
                "side_b": {"type": "best_third", "from_groups": ["C", "D", "F"]},
                "winner_to": "M89"},
    },
    "round_of_16": {
        "M90": {"matchNo": 90, "date": "2026-07-04", "kickoff_local": "12:00",
                "venue_id": "los_angeles", "side_a": "W73", "side_b": "W75", "winner_to": "M97"},
    },
}


def _complete_group(g):
    """4 Teams, alle 6 Spiele FT → Gruppe komplett."""
    teams = [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]
    fxs = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            fxs.append({"home": teams[i], "away": teams[j],
                        "result": {"status": "FT", "home_score": 1, "away_score": 0}})
    return {"teams": [{"id": t} for t in teams], "fixtures": fxs}


class TestKickoffUtc(unittest.TestCase):
    def test_la_noon_is_19utc(self):
        self.assertEqual(R._kickoff_utc("2026-06-28", "12:00", "los_angeles", VENUES),
                         "2026-06-28T19:00:00Z")

    def test_missing_tz_returns_none(self):
        self.assertIsNone(R._kickoff_utc("2026-06-28", "12:00", "unknown", VENUES))


class TestGroupComplete(unittest.TestCase):
    def test_complete(self):
        self.assertTrue(R._group_complete({"A": _complete_group("A")}, "A"))

    def test_incomplete(self):
        g = _complete_group("A")
        g["fixtures"][0]["result"]["status"] = "NS"
        self.assertFalse(R._group_complete({"A": g}, "A"))


class TestResolution(unittest.TestCase):
    def _build(self, groups):
        standings = {}
        for gid, gd in groups.items():
            # Tabelle in fixer Reihenfolge (G1..G4)
            standings[gid] = [{"team": t["id"], "pos": i + 1}
                              for i, t in enumerate(gd["teams"])]
        return R.build_ko_fixtures(BRACKET, groups, standings, VENUES, {})

    def test_group_position_resolves_when_complete(self):
        ko = self._build({"A": _complete_group("A"), "B": _complete_group("B")})
        m73 = next(f for f in ko if f["matchNo"] == 73)
        self.assertTrue(m73["bothResolved"])
        self.assertEqual((m73["home"], m73["away"]), ("A2", "B2"))
        self.assertEqual(m73["round"], "R32")
        self.assertEqual(m73["roundLabel"], "Sechzehntelfinale")

    def test_group_position_tbd_when_incomplete(self):
        g = _complete_group("B")
        g["fixtures"][0]["result"]["status"] = "NS"   # B nicht komplett
        ko = self._build({"A": _complete_group("A"), "B": g})
        m73 = next(f for f in ko if f["matchNo"] == 73)
        self.assertFalse(m73["bothResolved"])
        self.assertIsNone(m73["away"])
        self.assertEqual(m73["awayRef"], "2. Gruppe B")   # Ref-Label trotzdem da

    def test_best_third_stays_tbd(self):
        ko = self._build({"A": _complete_group("A")})
        m74 = next(f for f in ko if f["matchNo"] == 74)
        self.assertTrue(m74["homeResolved"])      # A1 aufgelöst
        self.assertFalse(m74["awayResolved"])     # best_third TBD
        self.assertIn("Bester Dritter", m74["awayRef"])

    def test_w_ref_stays_tbd_without_ko_results(self):
        ko = self._build({"A": _complete_group("A"), "B": _complete_group("B")})
        m90 = next(f for f in ko if f["matchNo"] == 90)
        self.assertFalse(m90["bothResolved"])
        self.assertEqual(m90["homeRef"], "Sieger Spiel 73")

    def test_winner_ref_resolves_with_result(self):
        groups = {"A": _complete_group("A"), "B": _complete_group("B")}
        standings = {g: [{"team": t["id"]} for t in gd["teams"]] for g, gd in groups.items()}
        ko = R.build_ko_fixtures(BRACKET, groups, standings, VENUES, {"73": "A2"})
        m90 = next(f for f in ko if f["matchNo"] == 90)
        self.assertEqual(m90["home"], "A2")       # Sieger M73 eingesetzt

    def test_apply_to_wm_writes_kofixtures(self):
        wm = {"groups": {"A": _complete_group("A"), "B": _complete_group("B")},
              "standings": {"A": [{"team": f"A{i}"} for i in range(1, 5)],
                            "B": [{"team": f"B{i}"} for i in range(1, 5)]}}
        ko = R.apply_to_wm(wm, bracket=BRACKET, venues=VENUES)
        self.assertIs(ko, wm["koFixtures"])
        self.assertTrue(any(f["bothResolved"] for f in ko))

    def test_apply_to_wm_preserves_api_filled_opponent(self):
        # 29.06.2026 (Lucas: GER-PRY/FRA-Cards verschwanden): M74-Gegner ist best_third (Bracket → None),
        # wurde aber von fetch_wm_match_results aus der echten API-Paarung gefüllt + Endstand geschrieben.
        # apply_to_wm darf das beim Neubau NICHT überbügeln.
        m74_key = next(f for f in R.build_ko_fixtures(BRACKET, {"A": _complete_group("A")},
                       {"A": [{"team": f"A{i}"} for i in range(1, 5)]}, VENUES, {})
                       if f["matchNo"] == 74)["matchKey"]
        wm = {"groups": {"A": _complete_group("A")},
              "standings": {"A": [{"team": f"A{i}"} for i in range(1, 5)]},
              "koFixtures": [{"matchKey": m74_key, "matchNo": 74, "home": "A1", "away": "PRY",
                              "result": {"status": "FT", "home_score": 2, "away_score": 0, "winner": "A1"}}]}
        ko = R.apply_to_wm(wm, bracket=BRACKET, venues=VENUES)
        m74 = next(f for f in ko if f["matchNo"] == 74)
        self.assertEqual(m74["away"], "PRY")                  # API-Gegner erhalten
        self.assertTrue(m74["bothResolved"])
        self.assertEqual(m74["result"]["home_score"], 2)     # Endstand erhalten


class TestDrawHandling(unittest.TestCase):
    """30.06.2026 (Lucas: „Kanada vs draw" in R16): ein KO-Sieger „draw" darf nie als Team in die
    nächste Runde wandern und nie aus alten Daten erhalten bleiben."""
    def _wm(self, ko_result):
        return {"groups": {"A": _complete_group("A"), "B": _complete_group("B")},
                "standings": {"A": [{"team": f"A{i}"} for i in range(1, 5)],
                              "B": [{"team": f"B{i}"} for i in range(1, 5)]},
                "koFixtures": [dict(matchKey="R32-M73", matchNo=73, home="A2", away="B2",
                                    result=ko_result)]}

    def test_draw_winner_not_propagated(self):
        wm = self._wm({"status": "PEN", "home_score": 1, "away_score": 1, "winner": "draw"})
        ko = R.apply_to_wm(wm, bracket=BRACKET, venues=VENUES)
        m90 = next(f for f in ko if f["matchNo"] == 90)   # refs W73
        self.assertIsNone(m90["home"])                    # NICHT aus „draw" gefüllt

    def test_real_winner_propagated(self):
        wm = self._wm({"status": "PEN", "home_score": 1, "away_score": 1, "winner": "A2"})
        ko = R.apply_to_wm(wm, bracket=BRACKET, venues=VENUES)
        m90 = next(f for f in ko if f["matchNo"] == 90)
        self.assertEqual(m90["home"], "A2")               # echter Sieger wandert weiter

    def test_draw_slot_not_preserved(self):
        # alter koFixtures-Slot trägt „draw" als Gegner → darf beim Neubau NICHT erhalten werden
        wm = {"groups": {"A": _complete_group("A")},
              "standings": {"A": [{"team": f"A{i}"} for i in range(1, 5)]},
              "koFixtures": [{"matchKey": "R16-M89", "matchNo": 89, "home": "CAN", "away": "draw"}]}
        ko = R.apply_to_wm(wm, bracket=BRACKET, venues=VENUES)
        bad = [f for f in ko if f.get("home") == "draw" or f.get("away") == "draw"]
        self.assertEqual(bad, [])


class TestFinalAndThirdPlace(unittest.TestCase):
    """01.07.2026 (Audit „KO endet eine Runde zu früh"): Finale (W-Refs) + Spiel um Platz 3
    (L-Refs = Halbfinal-Verlierer) müssen aus den SF-Ergebnissen aufgelöst werden."""
    BR = {"final": {"M104": {"matchNo": 104, "date": "2026-07-19", "kickoff_local": "15:00",
                             "venue_id": "nyc", "side_a": "W101", "side_b": "W102"}},
          "third_place": {"M103": {"matchNo": 103, "date": "2026-07-18", "kickoff_local": "15:00",
                                   "venue_id": "mia", "side_a": "L101", "side_b": "L102"}}}
    VEN = {"nyc": {"city": "NY", "tz_offset_h_utc": -4}, "mia": {"city": "Miami", "tz_offset_h_utc": -4}}

    def _wm(self):
        return {"groups": {}, "standings": {}, "koFixtures": [
            {"matchKey": "SF-M101", "matchNo": 101, "home": "ESP", "away": "FRA",
             "result": {"status": "FT", "home_score": 2, "away_score": 1, "winner": "ESP"}},
            {"matchKey": "SF-M102", "matchNo": 102, "home": "BRA", "away": "ARG",
             "result": {"status": "FT", "home_score": 0, "away_score": 1, "winner": "ARG"}}]}

    def test_final_from_winners(self):
        ko = R.apply_to_wm(self._wm(), bracket=self.BR, venues=self.VEN)
        f = next(x for x in ko if x["matchNo"] == 104)
        self.assertEqual((f["home"], f["away"]), ("ESP", "ARG"))
        self.assertTrue(f["bothResolved"])
        self.assertEqual(f["roundLabel"], "Finale")

    def test_third_place_from_losers(self):
        ko = R.apply_to_wm(self._wm(), bracket=self.BR, venues=self.VEN)
        t = next(x for x in ko if x["matchNo"] == 103)
        self.assertEqual((t["home"], t["away"]), ("FRA", "BRA"))   # die beiden SF-Verlierer
        self.assertTrue(t["bothResolved"])
        self.assertEqual(t["roundLabel"], "Spiel um Platz 3")

    def test_loser_ref_tbd_before_sf_result(self):
        # Ohne SF-Ergebnis bleiben Finale + Platz 3 TBD (keine Sieger/Verlierer bekannt)
        wm = {"groups": {}, "standings": {}, "koFixtures": []}
        ko = R.apply_to_wm(wm, bracket=self.BR, venues=self.VEN)
        for mno in (103, 104):
            m = next(x for x in ko if x["matchNo"] == mno)
            self.assertFalse(m["bothResolved"])

    def test_real_bracket_has_final_and_third(self):
        import json
        b = json.loads((REPO / "wm_bracket.json").read_text(encoding="utf-8"))
        self.assertIn("final", b)
        self.assertIn("third_place", b)
        self.assertEqual(b["final"]["M104"]["side_a"], "W101")
        self.assertEqual(b["third_place"]["M103"]["side_a"], "L101")


class TestResultsJobPropagates(unittest.TestCase):
    """01.07.2026 (Audit): fetch_wm_match_results muss den Bracket am Ende propagieren (importiert
    resolve_wm_bracket), sonst füllt sich der nächste Gegner erst beim nächsten picks/odds-Lauf."""
    def test_results_script_imports_bracket(self):
        src = (REPO / "fetch_wm_match_results.py").read_text(encoding="utf-8")
        self.assertIn("import resolve_wm_bracket", src)
        self.assertIn("resolve_wm_bracket.apply_to_wm", src)


if __name__ == "__main__":
    unittest.main()
