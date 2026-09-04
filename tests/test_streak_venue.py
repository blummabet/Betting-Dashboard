"""tests/test_streak_venue.py — 04.09.2026

Lucas: „es wird mal wieder Zeit für einen Cards-Check."

Auf der Card Werder Bremen (Heim) v RB Leipzig (Auswaerts) standen beide Serien-Zeilen aus der
jeweils FALSCHEN Haelfte:

    RB Leipzig · 🔥 Ungeschlagen HEIM 6x          -> Leipzig spielt hier auswaerts
    Werder Bremen · 🚩 Ueber 9,5 Ecken AUSWAERTS 5x -> Werder spielt hier daheim

Nachgesehen in liga_streaks.json: Werder (162) hat AUSSCHLIESSLICH Auswaerts-Serien, Leipzig
(173) fast nur Heim-Serien. Die Box heisst „Serien in diesem Spiel" — dort gehoert nichts hin,
was ueber dieses Spiel nichts sagt.

Die Ursache war eine Praeferenz ohne Ausschluss:

    score = 2 if v == pref_venue else (1 if v == "all" else 0)
    if score > best_score:            # best_score startet bei -1

Die 0 hat gereicht. Hier wiegt es schwerer als in der Anzeige, denn diese Funktion speist das
Serien-Momentum-SIGNAL, das in die Pick-Bewertung eingeht.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_signals.streak_momentum import _pick_team_streak


def s(stype, venue, length):
    return {"type": stype, "venue": venue, "length": length}


class VenuePassung(unittest.TestCase):
    def test_der_reale_werder_fall(self):
        """Werder spielt daheim und hat nur eine Auswaerts-Serie — also gibt es keine."""
        self.assertIsNone(_pick_team_streak([s("corners_over", "A", 5)], "corners_over", "H"))

    def test_der_reale_leipzig_fall(self):
        """Leipzig spielt auswaerts, die 6er-Serie ist eine HEIM-Serie."""
        self.assertIsNone(_pick_team_streak([s("unbeaten", "H", 6)], "unbeaten", "A"))

    def test_laenge_rettet_die_falsche_haelfte_nicht(self):
        self.assertIsNone(_pick_team_streak([s("unbeaten", "A", 20)], "unbeaten", "H"))

    def test_die_passende_haelfte_gewinnt_gegen_gesamt(self):
        best = _pick_team_streak([s("unbeaten", "all", 9), s("unbeaten", "H", 3)], "unbeaten", "H")
        self.assertEqual(best["venue"], "H")

    def test_gesamt_serie_bleibt_gueltig(self):
        best = _pick_team_streak([s("unbeaten", "all", 4)], "unbeaten", "H")
        self.assertEqual(best["venue"], "all")

    def test_serie_ohne_venue_gilt_als_gesamt(self):
        """Alte Zeilen ohne venue-Feld duerfen nicht stillschweigend rausfallen."""
        best = _pick_team_streak([s("unbeaten", None, 4)], "unbeaten", "H")
        self.assertIsNotNone(best)

    def test_anderer_typ_wird_nie_genommen(self):
        self.assertIsNone(_pick_team_streak([s("scores", "H", 9)], "unbeaten", "H"))

    def test_leere_liste_kippt_nicht(self):
        self.assertIsNone(_pick_team_streak([], "unbeaten", "H"))
        self.assertIsNone(_pick_team_streak(None, "unbeaten", "H"))
