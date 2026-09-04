"""tests/test_streak_staerke.py — 04.09.2026 (Lucas-Serien-Check)

`rate_strength` las `ratePct`. Fuellte die Serie das 15-Spiele-Formfenster, war das die Serie
SELBST — 100 %, also maximale Staerke. Gemessen ueber 733 aktive Serien:

    466 Serien passierten das Signal-Gate (len>=3, rate>=55)
    davon 307 — zwei Drittel — mit einer tautologischen Eigenrate
    allein 141-mal „Team trifft", der Markt mit 81 % Liga-Grundrate

compute_streaks liefert jetzt stattdessen die LIGA-Grundrate (`basis: "liga"`). Die darf aber
nicht durch dasselbe Gate: `min_rate_pct = 55` ist fuer eine TEAM-Rate gedacht. Auf eine
Liga-Norm angewandt wuerde es Zu null (28 %), Unter 2,5 (39 %) und Sieg-Serie (47 %)
komplett rauswerfen — ausgerechnet die aussagekraeftigsten Maerkte.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sharp_signals.streak_momentum import staerke, DEFAULTS, LIGA_DAEMPFUNG

CFG = DEFAULTS


class TeamHistorie(unittest.TestCase):
    def test_gestuetzte_serie_traegt(self):
        self.assertAlmostEqual(staerke({"length": 5, "ratePct": 80, "basis": "prior"}, CFG), 0.6, places=3)

    def test_serie_gegen_die_eigene_grundrate_traegt_nicht(self):
        self.assertIsNone(staerke({"length": 5, "ratePct": 50, "basis": "prior"}, CFG))

    def test_zu_kurz_traegt_nie(self):
        self.assertIsNone(staerke({"length": 2, "ratePct": 95, "basis": "prior"}, CFG))


class LigaBasis(unittest.TestCase):
    """Ohne Team-Vorgeschichte zaehlt, wie unwahrscheinlich der Lauf im Markt ist."""

    def test_eine_seltene_serie_traegt_auch_ohne_team_historie(self):
        # Parma 9x Unter 2,5 — 0,0217 % Zufallswahrscheinlichkeit.
        v = staerke({"length": 9, "basis": "liga", "zufallPct": 0.0217}, CFG)
        self.assertIsNotNone(v)
        self.assertGreater(v, 0.5)

    def test_eine_haeufige_serie_traegt_kaum_noch(self):
        """15x „Team trifft" — vorher volle Staerke aus 100 % Eigenrate, jetzt 3,9 % Zufall."""
        v = staerke({"length": 15, "basis": "liga", "zufallPct": 3.87}, CFG)
        self.assertLess(v, 0.3, "der haeufigste Markt darf das Signal nicht mehr pumpen")

    def test_liga_basis_kann_team_historie_nie_uebertreffen(self):
        beste = staerke({"length": 20, "basis": "liga", "zufallPct": 0.000001}, CFG)
        self.assertLessEqual(beste, LIGA_DAEMPFUNG)
        self.assertLess(beste, staerke({"length": 5, "ratePct": 100, "basis": "prior"}, CFG))

    def test_die_niedrigen_liga_maerkte_fliegen_nicht_raus(self):
        """Der Fehler, den das Raten-Gate hier verursacht haette: Zu null (28 %),
        Unter 2,5 (39 %), Sieg-Serie (47 %) liegen alle unter min_rate_pct=55."""
        for p, laenge in ((0.28, 4), (0.39, 5), (0.47, 6)):
            zufall = round((p ** laenge) * 100, 5)
            self.assertIsNotNone(staerke({"length": laenge, "basis": "liga", "zufallPct": zufall}, CFG),
                                 "p=%.2f, %dx" % (p, laenge))

    def test_ohne_seltenheitsmass_gibt_es_keine_staerke(self):
        self.assertIsNone(staerke({"length": 6, "basis": "liga"}, CFG))
        self.assertIsNone(staerke({"length": 6, "basis": "liga", "zufallPct": 0}, CFG))
        self.assertIsNone(staerke({"length": 6, "basis": "liga", "zufallPct": 100}, CFG))

    def test_ohne_jede_basis_traegt_nichts(self):
        self.assertIsNone(staerke({"length": 6, "basis": "keine"}, CFG))
