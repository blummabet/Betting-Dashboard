#!/usr/bin/env python3
"""
test_weather_climate_dome.py — Klima-Dome-Dämpfung im weather_signal (17.06.2026).

Stadien mit schließbarem Dach + Vollklima (AT&T Dallas, NRG Houston,
Mercedes-Benz Atlanta) halten ~21°C → die Außen-Hitze erreicht die Spieler nicht.
Das Hitze-Signal (feuert >30°C) muss dort gedämpft werden (Faktor 0.25), sonst
Phantom-Under (z.B. „Deutschland leidet in Dallas-Hitze" trotz Klimahalle).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from sharp_signals.weather_signal import WeatherSignal


def _ctx(venue, home="GER", away="MEX"):
    # GER=temperate, MEX=hot → nur Heim hat Hitze-Penalty; klare, einseitige Wertung.
    return {
        "home_id": home, "away_id": away,
        "venue": venue, "kickoff_time": "21:00",   # 21:00 Wien
        "weather": {f"{home.lower()}-{away.lower()}-x": {
            "forecastAvailable": True, "tempMax": 36.0, "tempAtKickoff": 35.0,
            "venue": venue,
        }},
    }


PICK = {"market": "Über 2.5 Tore"}


class TestClimateDome(unittest.TestCase):
    def setUp(self):
        self.sig = WeatherSignal()

    def _score(self, venue):
        r = self.sig.evaluate(PICK, _ctx(venue))
        return r.score if r else 0.0, r

    def test_open_air_full_penalty(self):
        # Lincoln Financial (kein Dome) → voller Penalty
        score, r = self._score("Lincoln Financial Field, Philadelphia")
        self.assertIsNotNone(r)
        self.assertLess(score, 0)            # Über → negativ
        self.assertFalse(r.metadata.get("climate_controlled"))
        self._open_air_score = score

    def test_dome_damped_vs_open(self):
        open_score, _  = self._score("Lincoln Financial Field, Philadelphia")
        dome_score, rd = self._score("AT&T Stadium, Dallas")
        # Dome muss klar schwächer sein (≈25% des offenen Penaltys) oder ganz aus
        self.assertGreater(dome_score, open_score)   # näher an 0
        if rd is not None:
            self.assertTrue(rd.metadata.get("climate_controlled"))
            self.assertAlmostEqual(dome_score, open_score * 0.25, places=2)

    def test_all_three_domes_flagged(self):
        for v in ["AT&T Stadium, Arlington", "NRG Stadium, Houston",
                  "Mercedes-Benz Stadium, Atlanta"]:
            _, r = self._score(v)
            # entweder gedämpft-aber-feuernd (climate_controlled True) oder ganz aus
            if r is not None:
                self.assertTrue(r.metadata.get("climate_controlled"),
                                f"{v} nicht als Klima-Dome erkannt")

    def test_normal_venue_not_flagged(self):
        _, r = self._score("Hard Rock Stadium, Miami")
        self.assertIsNotNone(r)
        self.assertFalse(r.metadata.get("climate_controlled"))


if __name__ == "__main__":
    unittest.main()
