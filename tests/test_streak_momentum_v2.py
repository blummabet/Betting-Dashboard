#!/usr/bin/env python3
"""test_streak_momentum_v2.py — Streak-Signal-Aufbohrung (04.07.2026, Lucas: „Streaks zu starken
Zahlen machen"). Friert die Experten-Tweaks ein: xG-Deckung, gelockerte Gates (MIN_LENGTH 3),
Ecken freigeschaltet, Markt-Persistenz (Backtest), Gegner-Normalisierung.

Grundthese (Backtest): reine Tor-/BTTS-Ergebnis-Serien sind Rauschen (gedämpft), xG-gedeckte +
stil-persistente (Ecken) tragen. Ohne diese Differenzierung war das Signal aktiv schädlich."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── compute_streaks: xG-Deckung ──────────────────────────────────────────────
class TestXgBacked(unittest.TestCase):
    def setUp(self):
        import compute_streaks as C
        self.C = C

    def test_over_serie_xg_gedeckt(self):
        # letzte Spiele alle xG-Total > 2.5 → gedeckt
        self.assertTrue(self.C._xg_backed("over25", [3.1, 2.8, 3.4]))

    def test_over_serie_gluecks_tore(self):
        # Über-Serie, aber xG lag drunter → NICHT gedeckt (Regressions-Kandidat)
        self.assertFalse(self.C._xg_backed("over25", [1.9, 2.1, 1.6]))

    def test_under_serie_gedeckt(self):
        self.assertTrue(self.C._xg_backed("under25", [1.5, 2.0, 1.1]))

    def test_nicht_ou_markt_none(self):
        self.assertIsNone(self.C._xg_backed("bttsYes", [3.0, 3.0]))
        self.assertIsNone(self.C._xg_backed("over25", []))

    def test_team_xg_totals_recent_first(self):
        wm = {
            "groups": {"A": {"fixtures": [
                {"home": "X", "away": "Y", "date": "2026-06-10",
                 "result": {"status": "FT", "stats": {"xgTotal": 2.0}}},
                {"home": "X", "away": "Z", "date": "2026-06-14",
                 "result": {"status": "FT", "stats": {"homeXg": 1.5, "awayXg": 2.0}}},  # xgTotal fehlt → aus home+away
            ]}},
            "koFixtures": [],
        }
        tot = self.C._team_xg_totals(wm)
        self.assertEqual(tot["X"], [3.5, 2.0])   # 14. (neuer) zuerst, dann 10.


# ── streak_momentum: Gates, Ecken, Persistenz, xG, Gegner ────────────────────
def _ctx(streaks):
    return {"home_id": "H", "away_id": "A", "streaks": streaks}


def _streak(stype, length=5, rate=80, venue="all", xg=None, opp=None):
    s = {"type": stype, "length": length, "ratePct": rate, "venue": venue,
         "market": stype, "team": "T", "xgBacked": xg}
    if opp is not None:
        s["next"] = {"oppRatePct": opp}
    return s


class TestStreakSignal(unittest.TestCase):
    def setUp(self):
        from sharp_signals.streak_momentum import StreakMomentumSignal, _market_family_dir
        self.sig = StreakMomentumSignal()
        self.fam = _market_family_dir

    def _score(self, market, streaks):
        r = self.sig.evaluate({"market": market}, _ctx(streaks))
        return r.score if r else 0.0

    def test_min_length_3_qualifiziert(self):
        # Länge 3 qualifiziert jetzt (früher MIN_LENGTH 4 → hart geblockt). Bei einer
        # persistenten Serie (Ecken) reicht das zum Feuern; eine EINZELNE 3er-Tor-Serie
        # bleibt bewusst unter der Schwelle (Persistenz 0.5 = Backtest-Disziplin).
        corners3 = self._score("Über 9,5 Ecken", {"H": [_streak("cornersOver", length=3, rate=80)]})
        self.assertGreater(corners3, 0)   # 3er-Serie feuert → MIN_LENGTH wurde gelockert
        # 06.09.2026: hier stand `assertEqual(lone_goal3, 0.0)` — eine schwache Tor-Serie
        # sollte SCHWEIGEN. Gemessen war das Ergebnis dieser Disziplin aber, dass das Signal
        # praktisch nie feuerte: auf den Ergebnis-Maerkten kam KEINER von 58 Faellen ueber die
        # Schwelle 0,25 (hoechster Score 0,214). Ein Signal ohne Beobachtungen kann die Bilanz
        # nie beurteilen — es konnte weder helfen noch widerlegt werden.
        #
        # Die Disziplin liegt jetzt in der GROESSE, nicht im Stummschalten: die Serie spricht,
        # aber so leise, dass sie keinen Pick dreht. Genau das ist „nur mehr beobachten".
        lone_goal3 = self._score("Über 2,5 Tore", {"H": [_streak("over25", length=3, rate=80, xg=True)]})
        self.assertGreater(lone_goal3, 0.0, "die Serie muss messbar sein, sonst lernen wir nie")
        self.assertLess(lone_goal3, 0.5,
                        "aber sie darf keinen Pick drehen — andere Signale liefern 1-3 pp")

    def test_beide_teams_stapeln(self):
        # zwei 3er-Tor-Serien (Heim+Auswärts) stapeln über die Schwelle
        both = self._score("Über 2,5 Tore", {
            "H": [_streak("over25", length=4, rate=85, xg=True)],
            "A": [_streak("over25", length=4, rate=85, xg=True)]})
        self.assertGreater(both, 0)

    def test_ecken_freigeschaltet(self):
        fam, d = self.fam("Über 9,5 Ecken")
        self.assertEqual(fam, "corners")
        self.assertEqual(d, +1)
        sc = self._score("Über 9,5 Ecken", {"H": [_streak("cornersOver", length=6)]})
        self.assertGreater(sc, 0)

    def test_karten_bleiben_aus(self):
        self.assertEqual(self.fam("Über 3,5 Karten"), (None, None))

    def test_xg_gedeckt_staerker_als_gluecks_serie(self):
        backed   = self._score("Über 2,5 Tore", {"H": [_streak("over25", xg=True)]})
        unbacked = self._score("Über 2,5 Tore", {"H": [_streak("over25", xg=False)]})
        self.assertGreater(backed, unbacked)
        self.assertGreater(backed, unbacked * 2)   # Dämpfung deutlich (unbacked_factor 0.35)

    def test_ecken_persistenter_als_tore(self):
        # gleiche Serie, aber Ecken (persist 1.0) > Tore (persist 0.5)
        corners = self._score("Über 9,5 Ecken", {"H": [_streak("cornersOver", length=6)]})
        goals   = self._score("Über 2,5 Tore",  {"H": [_streak("over25", length=6, xg=None)]})
        self.assertGreater(corners, goals)

    def test_gegner_normalisierung(self):
        # hohe Gegner-Über-Rate stützt eine Über-Serie stärker
        hi = self._score("Über 2,5 Tore", {"H": [_streak("over25", xg=True, opp=90)]})
        lo = self._score("Über 2,5 Tore", {"H": [_streak("over25", xg=True, opp=20)]})
        self.assertGreater(hi, lo)

    def test_deckel_haelt(self):
        sc = self._score("Über 9,5 Ecken", {
            "H": [_streak("cornersOver", length=8, rate=100, opp=100)],
            "A": [_streak("cornersOver", length=8, rate=100, opp=100)]})
        self.assertLessEqual(abs(sc), 2.5)

    def test_metadata_market_type(self):
        r = self.sig.evaluate({"market": "Über 2,5 Tore"},
                              _ctx({"H": [_streak("over25", xg=True)]}))
        self.assertEqual(r.metadata["market_type"], "over25")
        self.assertEqual(r.metadata["n_xg_backed"], 1)


class TestConfigOverride(unittest.TestCase):
    def test_config_wird_geladen(self):
        # cocobet_config.json muss den streak_momentum-Block haben (Tuning-Fläche)
        import json
        c = json.loads((Path(__file__).parent.parent / "cocobet_config.json").read_text(encoding="utf-8"))
        for p in ("wm2026", "liga_default", "mls_default"):
            self.assertIn("streak_momentum", c["profiles"][p])
            self.assertIn("market_persistence", c["profiles"][p]["streak_momentum"])


if __name__ == "__main__":
    unittest.main()
