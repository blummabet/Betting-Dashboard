"""Whale-Rangliste, Sport-Scores, Vorlauf und Sport-Inventar (02.09.2026).

Lucas: *„hast du da noch Ideen, wie wir bessere Whales rausfinden?"* — der Audit ergab einen harten
Befund: sortiert wurde nach `pnl`, und das ist die **Polymarket-weite** Lebenszeit-P&L (Wahlen,
Krypto, alles), nicht unsere getrackten Sportwetten. Gemessen trug die Sortierung **null**
Information über die Kante:

    Median Ø-CLV der Top-20        0,59 pp
    Median Ø-CLV aller 86 Quali.   0,60 pp
    Korrelation P&L ~ Ø CLV        0,06

CLV dagegen persistiert (getrennte Fenster, r = 0,78). Diese Tests sichern die Bausteine, mit denen
die Rangliste stattdessen auf CLV, Sportart und Vorlauf umgestellt wird.
"""
import unittest
from datetime import datetime, timezone

import poly_money_broad as B

JETZT = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


class TestSportKategorie(unittest.TestCase):
    """🔴 `_tag_category` gab für JEDEN unbekannten Tag „Fußball" zurück. Gemessen im Close-Freeze:
    sechs `lec-*`-Märkte (League of Legends EMEA, $63.563 im größten) standen als Fußball."""

    def test_unbekannter_tag_ist_NICHT_fussball(self):
        for t in ("lec", "rugby", "handball", "volleyball", "darts", "snooker", ""):
            self.assertIsNone(B._tag_category(t), f"{t!r} wurde zu Fußball gemacht")

    def test_bekannte_sportarten_bleiben(self):
        self.assertEqual(B._tag_category("nba"), "US-Sport")
        self.assertEqual(B._tag_category("lol"), "E-Sport")
        self.assertEqual(B._tag_category("atp"), "Tennis")
        self.assertEqual(B._tag_category("ufc"), "Kampfsport")

    def test_fussball_tags_und_registry_bleiben_fussball(self):
        self.assertEqual(B._tag_category("epl"), "Fußball")
        self.assertEqual(B._tag_category("italian-serie-c"), "Fußball")
        self.assertEqual(B._tag_category("aus-a-league", {"aus-a-league"}), "Fußball",
                         "entdeckte Ligen SIND Fussball — so wurden sie gefunden")


class TestSportScore(unittest.TestCase):
    def test_je_sportart_getrennt(self):
        s = {}
        B._wallet_sport(s, "Fußball", 2.0, True)
        B._wallet_sport(s, "Fußball", -1.0, False)
        B._wallet_sport(s, "E-Sport", 5.0, True)
        self.assertEqual(s["bySport"]["Fußball"], {"n": 2, "clvSumPP": 1.0, "wins": 1})
        self.assertEqual(s["bySport"]["E-Sport"]["n"], 1)

    def test_ohne_sportart_wird_NICHTS_verbucht(self):
        """Ein Eimer „unbekannt" wäre schlimmer als keiner — er läse sich wie eine Sportart."""
        s = {}
        B._wallet_sport(s, None, 9.0, True)
        B._wallet_sport(s, "", 9.0, True)
        self.assertNotIn("bySport", s)


class TestVorlauf(unittest.TestCase):
    """Früh drin und der Markt kommt nach = Information. Spät drin nach dem Move = Mitläufer.
    Im Killer-Buch war der Vorlauf der stärkste Trenner (≥6h: +48,9%, UG +7,6%)."""

    def test_frueh_und_spaet_getrennt(self):
        s = {}
        B._wallet_vorlauf(s, 8.0, 2.0, True)
        B._wallet_vorlauf(s, 6.0, 1.0, True)
        B._wallet_vorlauf(s, 0.5, -3.0, False)
        self.assertEqual(s["vorlauf"]["frueh"]["n"], 2, "6h zaehlt noch als frueh (>=)")
        self.assertEqual(s["vorlauf"]["spaet"], {"n": 1, "clvSumPP": -3.0, "wins": 0})

    def test_ohne_vorlauf_wird_nichts_verbucht(self):
        s = {}
        B._wallet_vorlauf(s, None, 5.0, True)
        B._wallet_vorlauf(s, "spaeter", 5.0, True)
        self.assertNotIn("vorlauf", s)


class TestTrackFuehrtDieNeuenFelder(unittest.TestCase):
    def _markt(self, resolved=False, htk=8.0, sport="Fußball"):
        m = {"key": "epl-a-b-2026-09-02", "league": "EPL", "sport": sport,
             "hoursToKickoff": htk, "prices": {"A": 0.4, "B": 0.6},
             "whales": [{"wallet": "0xA", "side": "A", "usd": 5000}]}
        if resolved:
            m.update({"resolved": True, "resolvedPrices": {"A": 1.0, "B": 0.0}, "whales": []})
        return m

    def test_offene_position_merkt_sport_und_vorlauf(self):
        t = B.update_wallet_track({}, [self._markt()], now=JETZT)
        e = list(t["open"].values())[0]
        self.assertEqual(e["sport"], "Fußball")
        self.assertEqual(e["htkFirst"], 8.0)

    def test_vorlauf_wird_beim_auffrischen_NICHT_ueberschrieben(self):
        """Der Vorlauf ist der beim ERSTEN Sehen — sonst schrumpft er mit jedem Lauf gegen null
        und jede Position sähe am Ende wie ein Last-Minute-Einstieg aus."""
        t = B.update_wallet_track({}, [self._markt(htk=8.0)], now=JETZT)
        t2 = B.update_wallet_track(t, [self._markt(htk=1.0)], now=JETZT)
        self.assertEqual(list(t2["open"].values())[0]["htkFirst"], 8.0)

    def test_beim_aufloesen_landen_sport_vorlauf_und_quadratsumme_im_score(self):
        t = B.update_wallet_track({}, [self._markt()], now=JETZT)
        t2 = B.update_wallet_track(t, [self._markt(resolved=True)], now=JETZT)
        s = t2["scores"]["0xA"]
        self.assertEqual(s["n"], 1)
        self.assertIn("Fußball", s["bySport"])
        self.assertIn("frueh", s["vorlauf"])
        self.assertIsInstance(s["clvSqSum"], float)

    def test_quadratsumme_erlaubt_die_streuung(self):
        """Ohne sie kennt die Rangliste nur den Punktschätzer — und der ist kein Beleg."""
        s = {"n": 0, "clvSumPP": 0.0, "wins": 0, "usd": 0}
        for clv in (2.0, -2.0, 4.0):
            s["n"] += 1
            s["clvSumPP"] = round(s["clvSumPP"] + clv, 2)
            s["clvSqSum"] = round((s.get("clvSqSum") or 0.0) + clv * clv, 2)
        mittel = s["clvSumPP"] / s["n"]
        var = (s["clvSqSum"] - s["n"] * mittel ** 2) / (s["n"] - 1)
        self.assertAlmostEqual(mittel, 4 / 3, places=4)
        self.assertGreater(var, 0)


class TestSportInventar(unittest.TestCase):
    """Aus unseren eigenen Dateien ist die Frage „welche Sportart fehlt uns?" NICHT beantwortbar:
    `open` entsteht aus unserem Scan und ist per Konstruktion vollständig. Die Antwort steckt in
    den /positions-Antworten, die wir für den Ø-Einstieg ohnehin holen."""

    CACHE = {"0xA": [{"eventSlug": "nba-lal-bos-2026-09-02", "currentValue": 5000},
                     {"slug": "epl-ars-che-2026-09-02", "currentValue": 9000},
                     {"title": "rugby-nz-aus", "currentValue": 4000},
                     {"eventSlug": "darts-pdc-final", "currentValue": 50}]}

    def test_findet_nur_was_wir_NICHT_scannen(self):
        inv = B.sport_inventar(self.CACHE, {"epl-ars-che-2026-09-02"})
        self.assertIn("nba", inv)
        self.assertIn("rugby", inv)
        self.assertNotIn("epl", inv, "was wir scannen, ist keine Luecke")

    def test_kleinkram_zaehlt_nicht(self):
        self.assertNotIn("darts", B.sport_inventar(self.CACHE, set()),
                         "$50 sagt nichts ueber eine fehlende Sportart")

    def test_nach_geld_sortiert(self):
        self.assertEqual(list(B.sport_inventar(self.CACHE, {"epl-x"}))[0], "nba")

    def test_muell_wirft_nicht(self):
        self.assertEqual(B.sport_inventar(None, None), {})
        self.assertEqual(B.sport_inventar({"0xA": [None, "x", {}]}, set()), {})


if __name__ == "__main__":
    unittest.main()
