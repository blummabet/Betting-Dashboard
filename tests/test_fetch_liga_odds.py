#!/usr/bin/env python3
"""
test_fetch_liga_odds.py — Liga-Odds-Kern (25.06.2026, Lucas: Liga auf WM-Stack). Der wunde Punkt des
alten Liga-Frontends war das Team-Namens-Matching → hier robust getestet, plus Preis-Extraktion
(Heim/Auswärts korrekt, auch vertauscht) + Opening-Carry.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import fetch_liga_odds as L  # noqa: E402


class TestOpeningPlausibility(unittest.TestCase):
    """08.07.2026 (Lucas: Radar-Fake-Drops bis -84pp). odds_open darf keinen Platzhalter-Markt
    (dr=1.01, aw=1.06 …) per-Outcome einfrieren; 1X2-Opening kohärent + selbstheilend aus History."""

    def test_plausible(self):
        self.assertTrue(L._plausible_1x2(2.1, 3.4, 3.3))
        self.assertTrue(L._plausible_1x2(1.3, 5.8, 11.25))

    def test_implausible(self):
        self.assertFalse(L._plausible_1x2(1.32, 1.01, 1.32))   # dr-Platzhalter
        self.assertFalse(L._plausible_1x2(1.26, 4.9, 1.06))    # aw-Platzhalter, Overround 1.94
        self.assertFalse(L._plausible_1x2(None, 3.4, 3.3))

    def test_heals_garbage_from_history(self):
        existing = {"odds_open": {"hw": 1.26, "dr": 4.9, "aw": 1.06}}   # Müll
        hist = [{"hw": 1.26, "dr": 4.9, "aw": 1.06},                     # 1. Snap = Müll
                {"hw": 1.3, "dr": 5.8, "aw": 11.25}]                     # 1. plausibler = echte Eröffnung
        e = L.build_odds_entry({"hw": 1.39, "dr": 4.96, "aw": 6.81}, existing, "T", hist=hist)
        self.assertEqual((e["odds_open"]["hw"], e["odds_open"]["dr"], e["odds_open"]["aw"]), (1.3, 5.8, 11.25))

    def test_keeps_plausible_opening(self):
        existing = {"odds_open": {"hw": 2.1, "dr": 3.4, "aw": 3.3}}
        e = L.build_odds_entry({"hw": 1.9, "dr": 3.5, "aw": 4.0}, existing, "T", hist=[])
        self.assertEqual(e["odds_open"]["hw"], 2.1)   # echte Eröffnung bleibt

    def test_no_plausible_no_garbage_freeze(self):
        e = L.build_odds_entry({"hw": 1.02, "dr": 1.01, "aw": 1.03}, {}, "T", hist=[])
        self.assertNotIn("hw", e["odds_open"])   # nichts Plausibles → kein Müll-Freeze


class TestCurrentOddsGate(unittest.TestCase):
    """22.07.2026 (Lucas: „fix das ein für alle mal"). Die WIEDERKEHRENDE Platzhalter-Klasse: das
    AKTUELLE 1X2 (hw/dr/aw im `odds`-Feld) ging bisher ROH rein → Fair/Edge/Trade rechneten gegen
    Müll. Jetzt gate+carry an der Schreibquelle: nie ein implausibles 1X2 im odds-Feld."""

    def test_plausibel_wird_geschrieben(self):
        e = L.build_odds_entry({"hw": 2.1, "dr": 3.4, "aw": 3.3, "bookmaker": "pinnacle"}, {}, "T", hist=[])
        self.assertEqual((e["hw"], e["dr"], e["aw"]), (2.1, 3.4, 3.3))

    def test_platzhalter_wird_NICHT_geschrieben_sondern_getragen(self):
        existing = {"hw": 2.0, "dr": 3.5, "aw": 3.6, "bookmaker": "pinnacle"}
        e = L.build_odds_entry({"hw": 1.04, "dr": 1.01, "aw": 1.04}, existing, "T", hist=[])
        self.assertEqual((e["hw"], e["dr"], e["aw"]), (2.0, 3.5, 3.6), "Platzhalter → letzte plausible Quote tragen")
        self.assertEqual(e.get("oddsCarriedAt"), "T", "getragen muss markiert sein")

    def test_platzhalter_ohne_historie_laesst_1x2_ABSENT(self):
        e = L.build_odds_entry({"hw": 1.04, "dr": 1.01, "aw": 1.04}, {}, "T", hist=[])
        self.assertIsNone(e.get("hw"), "kein Fake-Anker — 1X2 bleibt weg statt Platzhalter zu schreiben")
        self.assertIsNone(e.get("aw"))

    def test_kein_platzhalter_ueberschreibt_gute_quote(self):
        # frische gute Quote gewinnt IMMER gegen alte
        existing = {"hw": 5.0, "dr": 4.0, "aw": 1.6}
        e = L.build_odds_entry({"hw": 2.1, "dr": 3.4, "aw": 3.3}, existing, "T", hist=[])
        self.assertEqual(e["hw"], 2.1)


class TestNameMatch(unittest.TestCase):
    def test_norm_strips_rechtsform_accents(self):
        self.assertEqual(L._norm_name("Atlético Madrid"), "atletico madrid")
        self.assertEqual(L._norm_name("AC Milan"), "milan")
        self.assertEqual(L._norm_name("1. FC Köln"), "koln")

    def test_alias(self):
        self.assertEqual(L._norm_name("Internazionale"), "inter")
        self.assertEqual(L._norm_name("Wolverhampton Wanderers"), "wolves")

    def test_match_variants(self):
        self.assertTrue(L._names_match("Real Madrid", "Real Madrid CF"))
        self.assertTrue(L._names_match("Inter", "Internazionale"))
        self.assertTrue(L._names_match("Wolves", "Wolverhampton Wanderers"))
        self.assertTrue(L._names_match("Bayern München", "Bayern Munich"))

    def test_no_false_match(self):
        self.assertFalse(L._names_match("Real Madrid", "Real Sociedad"))
        self.assertFalse(L._names_match("Manchester City", "Manchester United"))


class TestEventMatch(unittest.TestCase):
    def _ev(self, h, a):
        return {"home_team": h, "away_team": a, "bookmakers": []}

    def test_direct(self):
        self.assertEqual(L.match_event_to_fixture(self._ev("Liverpool", "Chelsea"),
                                                  "Liverpool", "Chelsea"), "direct")

    def test_swapped(self):
        self.assertEqual(L.match_event_to_fixture(self._ev("Chelsea", "Liverpool"),
                                                  "Liverpool", "Chelsea"), "swapped")

    def test_none(self):
        self.assertIsNone(L.match_event_to_fixture(self._ev("Arsenal", "Chelsea"),
                                                   "Liverpool", "Everton"))


def _event_full(home, away):
    return {"home_team": home, "away_team": away, "bookmakers": [{
        "key": "pinnacle", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": home, "price": 1.80}, {"name": "Draw", "price": 3.6},
                {"name": away, "price": 4.5}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 2.5, "price": 1.95},
                {"name": "Under", "point": 2.5, "price": 1.90}]},
            {"key": "btts", "outcomes": [
                {"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}]},
        ]}]}


def _event_with_soft(home, away):
    # Pinnacle (sharp) + bet365 (soft) — für Public-Konsens-Extraktion.
    return {"home_team": home, "away_team": away, "bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": 1.80}, {"name": "Draw", "price": 3.6},
            {"name": away, "price": 4.5}]}]},
        {"key": "bet365", "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": 1.70}, {"name": "Draw", "price": 3.7},
            {"name": away, "price": 5.0}]}]},
    ]}


class TestPublicConsensus(unittest.TestCase):
    def test_public_from_soft_book(self):
        p = L.extract_prices(_event_with_soft("Liverpool", "Chelsea"), "direct", "Liverpool", "Chelsea")
        self.assertEqual(p["hw"], 1.80)          # sharp = pinnacle
        self.assertEqual(p["public_hw"], 1.70)   # public = bet365
        self.assertEqual(p["public_bookmaker"], "bet365")

    def test_public_seeded_then_carried(self):
        pr1 = {"hw": 1.8, "dr": 3.6, "aw": 4.5, "bookmaker": "pinnacle",
               "public_hw": 1.7, "public_dr": 3.7, "public_aw": 5.0, "public_bookmaker": "bet365"}
        e1 = L.build_odds_entry(pr1, None, "2026-08-01T00:00:00Z")
        self.assertEqual(e1["public_hw_open"], 1.7)
        # Soft-Quote bewegt sich → Opening bleibt 1.7, public_hw aktualisiert
        pr2 = dict(pr1, public_hw=1.5)
        e2 = L.build_odds_entry(pr2, e1, "2026-08-10T00:00:00Z")
        self.assertEqual(e2["public_hw_open"], 1.7)
        self.assertEqual(e2["public_hw"], 1.5)


class TestSnapshot(unittest.TestCase):
    def test_appends_pinnacle_and_public(self):
        h = {}
        n = L.append_snapshot(h, "40-50",
                              {"hw": 1.8, "dr": 3.6, "aw": 4.5, "public_hw": 1.7, "public_dr": 3.7, "public_aw": 5.0},
                              "2026-08-01T00:00:00Z")
        self.assertEqual(n, 2)
        snaps = h["40-50"]
        self.assertEqual([s["bk"] for s in snaps], ["pinnacle", "public"])

    def test_no_dup_when_unchanged(self):
        h = {}
        pr = {"hw": 1.8, "dr": 3.6, "aw": 4.5}
        L.append_snapshot(h, "40-50", pr, "2026-08-01T00:00:00Z")
        n2 = L.append_snapshot(h, "40-50", pr, "2026-08-01T06:00:00Z")
        self.assertEqual(n2, 0)            # unverändert → kein neuer Snap
        self.assertEqual(len(h["40-50"]), 1)

    def test_appends_on_move(self):
        h = {}
        L.append_snapshot(h, "40-50", {"hw": 1.8, "dr": 3.6, "aw": 4.5}, "2026-08-01T00:00:00Z")
        n2 = L.append_snapshot(h, "40-50", {"hw": 1.6, "dr": 3.7, "aw": 5.2}, "2026-08-02T00:00:00Z")
        self.assertEqual(n2, 1)            # Bewegung → neuer Pinnacle-Snap
        self.assertEqual(len(h["40-50"]), 2)

    def test_platzhalter_wird_nicht_in_history_geschrieben(self):
        """20.07.2026 (MLS-Audit): Platzhalter-Quoten (1.04/1.01/1.04, Overround ~2.9) dürfen NIE in
        die Zeitreihe — sie ersticken sonst die Sharp-Money-Signale (Ghost-Move-Klasse)."""
        h = {}
        n = L.append_snapshot(h, "60-70",
                              {"hw": 1.04, "dr": 1.01, "aw": 1.04,
                               "public_hw": 1.04, "public_dr": 1.01, "public_aw": 1.04},
                              "2026-08-01T00:00:00Z")
        self.assertEqual(n, 0, "implausibles 1X2 darf keinen Snapshot erzeugen")
        self.assertEqual(h.get("60-70", []), [])

    def test_echte_quote_nach_platzhalter_ist_kein_fake_steam(self):
        """Kommt nach einem Platzhalter die erste ECHTE Quote, darf die History NUR die echte zeigen
        (kein Platzhalter→Echt-Sprung = kein Fake-Steam)."""
        h = {}
        L.append_snapshot(h, "60-70", {"hw": 1.04, "dr": 1.01, "aw": 1.04}, "2026-08-01T00:00:00Z")
        L.append_snapshot(h, "60-70", {"hw": 2.10, "dr": 3.30, "aw": 3.40}, "2026-08-02T00:00:00Z")
        snaps = h.get("60-70", [])
        self.assertEqual(len(snaps), 1, "nur die echte Quote steht in der History")
        self.assertEqual(snaps[0]["hw"], 2.10)


class TestExtractPrices(unittest.TestCase):
    def test_direct_mapping(self):
        p = L.extract_prices(_event_full("Liverpool", "Chelsea"), "direct", "Liverpool", "Chelsea")
        self.assertEqual((p["hw"], p["dr"], p["aw"]), (1.80, 3.6, 4.5))
        self.assertEqual((p["o25"], p["u25"]), (1.95, 1.90))
        self.assertEqual((p["bttsY"], p["bttsN"]), (1.85, 1.95))
        self.assertEqual(p["bookmaker"], "pinnacle")

    def test_swapped_mapping(self):
        # Event listet Chelsea als Heim — unser Fixture ist Liverpool(Heim) vs Chelsea
        ev = _event_full("Chelsea", "Liverpool")
        p = L.extract_prices(ev, "swapped", "Liverpool", "Chelsea")
        # Mapping per Name: Liverpool(unser Heim) hat im Event 4.5, Chelsea(unser Auswärts) 1.80.
        self.assertEqual(p["hw"], 4.5)   # Liverpool
        self.assertEqual(p["aw"], 1.80)  # Chelsea


class TestBuildEntry(unittest.TestCase):
    def test_opening_seeded_then_carried(self):
        e1 = L.build_odds_entry({"hw": 2.0, "dr": 3.4, "aw": 3.6, "bookmaker": "pinnacle"},
                                None, "2026-08-01T00:00:00Z")
        self.assertEqual(e1["odds_open"]["hw"], 2.0)
        # zweiter Lauf, Quote bewegt sich → Opening bleibt 2.0
        e2 = L.build_odds_entry({"hw": 1.7, "dr": 3.5, "aw": 4.5, "bookmaker": "pinnacle"},
                                e1, "2026-08-10T00:00:00Z")
        self.assertEqual(e2["odds_open"]["hw"], 2.0)   # Opening eingefroren
        self.assertEqual(e2["hw"], 1.7)                 # aktuelle Quote neu


if __name__ == "__main__":
    unittest.main()
