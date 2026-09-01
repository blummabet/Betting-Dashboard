"""Automatische Ligen-Entdeckung für den Pinnacle-Anker (01.09.2026).

Lucas: *„ich akzeptier keine andere Meinung, da wir extra die OddsAPI mit fünf Millionen API-Calls
zur Verfügung haben."* Er hatte recht — die Beschränkung war nie die Quota, sondern die handgepflegte
`LEAGUE_ODDS_KEY` (30 Ligen gegen 229 Ligastrings im Feed). Gemessen: von 57 Betfair-Spielen am
02.09. hatte **eines** einen Anker.

Der zweite Anlauf im globalen Pool macht das breit — und schafft dabei ein neues Risiko, das diese
Tests einfangen: über ~70 Wettbewerbe hinweg trifft dasselbe Klubpaar auch in Pokal, Liga und
Reserve. Ein falsch zugeordneter Anker wäre schlimmer als gar keiner, weil er wie ein Beleg
aussieht. Deshalb die Anpfiff-Schranke — und deshalb hier vor allem Tests dagegen.
"""
import unittest

import betfair_consensus as C


def sport(key, group="Soccer", active=True, outrights=False):
    return {"key": key, "group": group, "active": active, "has_outrights": outrights}


def ev(home="Kashima", away="Urawa", commence="2026-09-02T10:00:00Z"):
    return {"home": home, "away": away, "commence": commence, "pinn": [0.5, 0.3, 0.2]}


SPIEL = {"home": "Kashima", "away": "Urawa", "kickoff": "2026-09-02T10:00:00Z"}


class TestKeyAuswahl(unittest.TestCase):
    def test_nur_aktiver_fussball(self):
        k = C.aktive_fussball_keys([sport("soccer_epl"), sport("basketball_nba", group="Basketball"),
                                    sport("soccer_alt", active=False)])
        self.assertEqual(k, ["soccer_epl"])

    def test_outright_maerkte_fliegen_raus(self):
        """Ein Winner-Markt führt keine Einzelspiele — er kostet nur Laufzeit."""
        self.assertEqual(C.aktive_fussball_keys([sport("soccer_epl_winner", outrights=True)]), [])

    def test_deckel_begrenzt_die_laufzeit_nicht_die_quota(self):
        """Der Mac-Runner hat 12 Minuten. Der Deckel schützt die LAUFZEIT — Calls sind da genug."""
        viele = [sport("soccer_%02d" % i) for i in range(50)]
        self.assertEqual(len(C.aktive_fussball_keys(viele, max_keys=10)), 10)

    def test_muell_wirft_nicht(self):
        self.assertEqual(C.aktive_fussball_keys(None), [])
        self.assertEqual(C.aktive_fussball_keys([None, "x", {}, {"key": None, "group": "Soccer",
                                                               "active": True}]), [])

    def test_doppelte_keys_nur_einmal(self):
        self.assertEqual(C.aktive_fussball_keys([sport("soccer_epl"), sport("soccer_epl")]),
                         ["soccer_epl"])


class TestAnpfiffSchranke(unittest.TestCase):
    """Der Kern. Ohne diese Schranke wäre der globale Pool eine Verwechslungsmaschine."""

    def test_ohne_schranke_bleibt_alles_wie_bisher(self):
        self.assertIsNotNone(C.match_event(SPIEL, [ev()]))

    def test_gleiches_paar_eine_woche_spaeter_zaehlt_nicht(self):
        self.assertIsNone(C.match_event(SPIEL, [ev(commence="2026-09-09T10:00:00Z")], max_h=2.0))

    def test_das_richtige_von_zwei_gleichen_paaren_wird_genommen(self):
        """Liga- und Pokalspiel derselben Klubs — genau der Fall, den der globale Pool erzeugt."""
        treffer = C.match_event(SPIEL, [ev(commence="2026-09-09T10:00:00Z"), ev()], max_h=2.0)
        self.assertEqual(treffer["commence"], "2026-09-02T10:00:00Z")

    def test_fehlende_anpfiffzeit_ist_KEIN_treffer(self):
        """Ein Treffer, den wir nicht prüfen können, ist keiner — fehlende Information ist keine
        Erlaubnis, auch beim Zuordnen nicht."""
        self.assertIsNone(C.match_event(SPIEL, [ev(commence=None)], max_h=2.0))
        self.assertIsNone(C.match_event({"home": "Kashima", "away": "Urawa"}, [ev()], max_h=2.0))

    def test_kaputte_zeitstempel_sind_kein_treffer(self):
        self.assertIsNone(C.match_event(SPIEL, [ev(commence="morgen frueh")], max_h=2.0))

    def test_knapp_innerhalb_zaehlt_knapp_ausserhalb_nicht(self):
        self.assertIsNotNone(C.match_event(SPIEL, [ev(commence="2026-09-02T11:30:00Z")], max_h=2.0))
        self.assertIsNone(C.match_event(SPIEL, [ev(commence="2026-09-02T13:00:00Z")], max_h=2.0))

    def test_falsche_teams_bleiben_falsch_auch_mit_passender_zeit(self):
        self.assertIsNone(C.match_event(SPIEL, [ev(home="Gamba", away="Cerezo")], max_h=2.0))


class TestStunden(unittest.TestCase):
    def test_rechnet_ueber_zeitzonen(self):
        self.assertAlmostEqual(C._stunden("2026-09-02T10:00:00Z", "2026-09-02T12:00:00+00:00"), 2.0)

    def test_naive_zeit_gilt_als_utc(self):
        self.assertAlmostEqual(C._stunden("2026-09-02T10:00:00", "2026-09-02T11:00:00Z"), 1.0)

    def test_unlesbar_ergibt_None_nicht_null(self):
        """0.0 hiesse „gleichzeitig" — also ein Treffer. Genau falschherum."""
        for a, b in ((None, "2026-09-02T10:00:00Z"), ("x", "2026-09-02T10:00:00Z"), ("", "")):
            self.assertIsNone(C._stunden(a, b))


class TestHandlisteBleibtVorrang(unittest.TestCase):
    def test_mls_schreibweise_aus_dem_echten_feed(self):
        """Der Eintrag stand immer da — aber als „Major League Soccer", während Betfair „US MLS"
        schreibt. 105 Ledger-Zeilen, 0 Anker. Beide Schreibweisen bleiben stehen."""
        self.assertEqual(C.LEAGUE_ODDS_KEY.get("US MLS"), "soccer_usa_mls")
        self.assertEqual(C.LEAGUE_ODDS_KEY.get("Major League Soccer"), "soccer_usa_mls")


if __name__ == "__main__":
    unittest.main()
