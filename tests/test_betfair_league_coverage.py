# tests/test_betfair_league_coverage.py — grosse Ligen haben einen Pinnacle-Anker-Key (14.08.2026, Lucas).
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import betfair_consensus as BC


class TestLeagueCoverage(unittest.TestCase):
    def test_big_leagues_mapped(self):
        want = {
            "Turkish Super League":         "soccer_turkey_super_league",
            "Dutch Eredivisie":             "soccer_netherlands_eredivisie",
            "English Sky Bet Championship": "soccer_efl_champ",
            "German Bundesliga 2":          "soccer_germany_bundesliga2",
            "Swedish Allsvenskan":          "soccer_sweden_allsvenskan",
            "Saudi Professional League":    "soccer_saudi_arabia_pro_league",
        }
        for lg, key in want.items():
            self.assertEqual(BC.LEAGUE_ODDS_KEY.get(lg), key, "%s fehlt/falsch gemappt" % lg)

    def test_top5_and_mls_still_there(self):
        for lg in ("English Premier League", "Spanish La Liga", "German Bundesliga",
                   "Italian Serie A", "French Ligue 1", "Major League Soccer"):
            self.assertIn(lg, BC.LEAGUE_ODDS_KEY)

    def test_keys_are_soccer_prefixed(self):
        for key in BC.LEAGUE_ODDS_KEY.values():
            self.assertTrue(key.startswith("soccer_"), "%s ist kein soccer_-Key" % key)


if __name__ == "__main__":
    unittest.main()


# ════════════════════════════════════════════════════════════════════════════════════
# 🔴 25.09.2026 — die Handliste ist nicht mehr das Tor zum Anker, sondern das Tor zu den
# Totals. Gemessen: 38 Ligen mit Anker, 37 davon ueber den globalen Pool, 1 aus der Liste.
# Der Pool ist aber ein zweiter Anlauf NUR fuer die Match Odds.
# ════════════════════════════════════════════════════════════════════════════════════
import inspect
import re


NEU_25_09 = {
    "Japanese J League":        "soccer_japan_j_league",
    "Spanish Segunda Division": "soccer_spain_segunda_division",
    "Swedish Superettan":       "soccer_sweden_superettan",
    "Mexican Liga MX":          "soccer_mexico_ligamx",
    "Italian Serie B":          "soccer_italy_serie_b",
    "French Ligue 2":           "soccer_france_ligue_two",
    "South Korean K1 League":   "soccer_korea_kleague1",
    "Greek Super League":       "soccer_greece_super_league",
    "Swiss Super League":       "soccer_switzerland_superleague",
    "Chinese Super League":     "soccer_china_superleague",
    "German Frauen-Bundesliga": "soccer_germany_bundesliga_women",
    "English Sky Bet League 1": "soccer_england_league1",
    "English Sky Bet League 2": "soccer_england_league2",
}


class NeueZuordnungen(unittest.TestCase):
    def test_die_dreizehn_stehen_drin(self):
        """Von Hand gegen die Spielklasse des Landes geprueft. Faellt eine Zeile raus, verliert
        diese Liga ihren Totals-Anker — und niemand sieht es, weil 1X2 weiter funktioniert."""
        for lg, key in NEU_25_09.items():
            self.assertEqual(BC.LEAGUE_ODDS_KEY.get(lg), key, "%s fehlt/falsch gemappt" % lg)

    def test_keine_zweite_liga_auf_einem_erstliga_key(self):
        """Die Falle, die der erste Abgleich stellte: eine untere Spielklasse auf dem Key der
        obersten. Kein Key darf zweimal vorkommen, ausser der bewussten MLS-Ersatzschreibweise."""
        rueck = {}
        for lg, key in BC.LEAGUE_ODDS_KEY.items():
            rueck.setdefault(key, []).append(lg)
        doppelt = {k: v for k, v in rueck.items() if len(v) > 1}
        self.assertEqual(doppelt, {"soccer_usa_mls": ["US MLS", "Major League Soccer"]}, doppelt)

    def test_totals_haben_keinen_globalen_zweiten_anlauf(self):
        """DER Grund, warum die Handliste ueberhaupt noch waechst.

        `ev` bekommt einen zweiten Anlauf im globalen Pool, `tev` nicht — `totals_by_key` wird
        ausdruecklich nur fuer die kuratierten Keys gefuellt (Laufzeit, nicht Quota; der Job
        hat einen Minuten-Deckel). Ohne Eintrag in der Handliste gibt es also einen
        Pinnacle-Anker fuer 1X2, aber NIE einen fuer die Torlinien.

        Bekommt `tev` eines Tages einen Pool-Fallback, wird dieser Test rot — dann ist die
        Begruendung fuer die 13 Eintraege oben verfallen und gehoert neu geschrieben, nicht
        der Test geloescht."""
        src = inspect.getsource(BC)
        self.assertIn("totals_by_key = {}\n    for k in need:", src,
                      "Totals werden nicht mehr nur fuer die kuratierten Keys geholt")
        tev = [l for l in src.split("\n") if re.match(r"\s*tev = ", l)]
        self.assertTrue(tev, "tev wird nicht mehr gesetzt")
        for l in tev:
            self.assertIn("if k else None", l, l)
        self.assertNotIn("_global_totals", src)

    def test_abdeckung_wird_gemessen_nicht_behauptet(self):
        """`leaguesCovered` war `set(LEAGUE_ODDS_KEY.values())` — die Absicht, nicht die
        Messung. Sie stand unter einem Namen, der Abdeckung behauptete."""
        src = inspect.getsource(BC)
        self.assertNotIn('"leaguesCovered"', src)
        self.assertIn('"leaguesKuratiert"', src)
        self.assertIn('"leaguesMitAnker"', src)
        self.assertIn('"leaguesMitTotals"', src)
