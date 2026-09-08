"""tests/test_spielzentrale.py — Ebene 0 der Uebersicht (08.09.2026).

Der Kern ist das Urteil, und das Urteil hat drei Faelle, die sich sehr aehnlich sehen und
verschiedene Dinge bedeuten: „zwei Geldquellen liegen gleich", „zwei Geldquellen liegen
verschieden" und „nur eine hat ueberhaupt gesprochen". Die dritte ist die haeufigste (77 von
123 Spielen am 08.09.) und ist KEIN Konsens — genau diese Verwechslung soll die Ebene abschaffen.
"""
import unittest
from datetime import datetime, timedelta, timezone

import spielzentrale as SZ

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


def mm(home="Real Madrid", away="Inter", ko_h=9.0, bf=("home", 88, 102861),
       poly=("home", 60, 294571), poly_geld=True, pinn_fav="home", league="UEFA Champions League"):
    return {
        "matchId": "1", "home": home, "away": away, "league": league,
        "kickoff": (NOW + timedelta(hours=ko_h)).isoformat().replace("+00:00", "Z"),
        "live": False,
        "betfair": ({"side": bf[0], "name": home if bf[0] == "home" else away,
                     "sharePct": bf[1], "eur": bf[2], "odd": 1.66} if bf else None),
        "poly": ({"side": poly[0], "name": home if poly[0] == "home" else away,
                  "sharePct": poly[1], "usd": poly[2]} if poly else None),
        "polyGeld": poly_geld,
        "pinn": ({"fav": pinn_fav, "home": 0.6, "draw": 0.21, "away": 0.19} if pinn_fav else None),
    }


def stake(event="Real Madrid - Inter", auswahl="Real Madrid", usd=9000.0, ko_h=9.0, markt="1x2"):
    return [{"kombi": False, "einsatzUsd": usd, "event": event, "markt": markt,
             "auswahl": auswahl, "eventId": "e1",
             "anpfiff": (NOW + timedelta(hours=ko_h)).isoformat().replace("+00:00", "Z")}]


class TestUrteil(unittest.TestCase):
    def test_zwei_geldquellen_gleiche_seite_ist_einig(self):
        d = SZ.baue([mm()], now=NOW)
        z = d["zeilen"][0]
        self.assertEqual(z["urteil"], "einig")
        self.assertEqual(sorted(z["dafuer"]), ["betfair", "poly"])
        self.assertEqual(z["gegen"], [])

    def test_verschiedene_seiten_sind_uneinig_nicht_einig(self):
        z = SZ.baue([mm(poly=("away", 62, 40000))], now=NOW)["zeilen"][0]
        self.assertEqual(z["urteil"], "uneinig")
        self.assertIn("Divergenz", z["text"])

    def test_eine_quelle_ist_kein_konsens(self):
        # Der haeufigste Fall im Feed. Er darf nie wie eine Deckung aussehen — und er steht
        # nicht in der Hauptliste, sondern gezaehlt daneben.
        d = SZ.baue([mm(poly=None)], now=NOW)
        self.assertEqual(d["zeilen"], [])
        self.assertEqual(d["rest"]["einzeln"], 1)
        self.assertEqual(d["einzeln"][0]["urteil"], "eine Geldquelle")

    def test_pinnacle_stiftet_keine_einigkeit(self):
        # Betfair allein + Pinnacle-Favorit auf derselben Seite ist der NORMALFALL (das Geld
        # liegt auf dem Favoriten) und kein Befund. Waere der Anker eine Stimme, waere fast
        # jede Zeile „einig".
        d = SZ.baue([mm(poly=None, pinn_fav="home")], now=NOW)
        self.assertEqual(d["zeilen"], [])
        self.assertEqual(d["einzeln"][0]["nGeld"], 1)

    def test_anker_widerspricht_wird_gesagt(self):
        z = SZ.baue([mm(pinn_fav="away")], now=NOW)["zeilen"][0]
        self.assertEqual(z["urteil"], "einig")
        self.assertEqual(z["anker"], "dagegen")
        self.assertIn("gegen den Anker", z["text"])

    def test_fehlende_quelle_ist_kein_widerspruch(self):
        z = SZ.baue([mm(pinn_fav=None)], now=NOW)["zeilen"][0]
        self.assertIsNone(z["anker"])
        self.assertEqual(z["gegen"], [])

    def test_reiner_poly_preis_stimmt_nicht_mit_ab(self):
        # `polyGeld: False` = Scan-Preis ohne echtes Geld. Er bleibt sichtbar, aber er darf
        # keine Uebereinstimmung erzeugen, die niemand bezahlt hat.
        d = SZ.baue([mm(poly_geld=False)], now=NOW)
        self.assertEqual(d["zeilen"], [])
        z = d["einzeln"][0]
        self.assertEqual(z["urteil"], "eine Geldquelle")
        self.assertEqual(z["poly"]["art"], "preis")
        self.assertIsNotNone(z["poly"]["usd"])   # sichtbar bleibt sie


class TestStake(unittest.TestCase):
    def test_stake_wird_dritte_geldquelle(self):
        z = SZ.baue([mm()], stake_wetten=stake(), now=NOW)["zeilen"][0]
        self.assertEqual(sorted(z["dafuer"]), ["betfair", "poly", "stake"])
        self.assertEqual(z["nGeld"], 3)

    def test_nur_1x2_gibt_eine_seite(self):
        # „Over 1.5" traegt Geld, beantwortet aber eine andere Frage.
        z = SZ.baue([mm()], stake_wetten=stake(markt="Asian Total", auswahl="Over 1.5"),
                    now=NOW)["zeilen"][0]
        self.assertIsNone(z["stake"]["seite"])
        self.assertEqual(z["stake"]["usd"], 9000)          # Geld bleibt sichtbar
        self.assertEqual(sorted(z["dafuer"]), ["betfair", "poly"])

    def test_kleine_wette_zaehlt_nicht_als_geldstrom_bleibt_aber_sichtbar(self):
        z = SZ.baue([mm()], stake_wetten=stake(usd=80.0), now=NOW)["zeilen"][0]
        self.assertIsNone(z["stake"]["seite"])
        self.assertEqual(z["stake"]["usd"], 80)

    def test_kombi_zaehlt_nicht(self):
        w = stake(); w[0]["kombi"] = True
        z = SZ.baue([mm()], stake_wetten=w, now=NOW)["zeilen"][0]
        self.assertIsNone(z["stake"])

    def test_falsches_spiel_wird_nicht_gejoint(self):
        z = SZ.baue([mm()], stake_wetten=stake(event="Porto - Manchester City",
                                               auswahl="Porto"), now=NOW)["zeilen"][0]
        self.assertIsNone(z["stake"])

    def test_nachwuchs_wird_nicht_auf_die_erste_elf_gejoint(self):
        # Dieselbe Klasse wie der Poly-Join vom 08.09.: „Real Madrid U19" ist nicht Real Madrid.
        z = SZ.baue([mm(home="Real Madrid U19", away="Inter U19")],
                    stake_wetten=stake(), now=NOW)["zeilen"][0]
        self.assertIsNone(z["stake"])


class TestFensterUndRest(unittest.TestCase):
    def test_gelaufenes_spiel_faellt_raus_und_wird_gezaehlt(self):
        d = SZ.baue([mm(ko_h=-2)], now=NOW)
        self.assertEqual(d["zeilen"], [])
        self.assertEqual(d["rest"]["gelaufen"], 1)

    def test_spiel_hinter_dem_fenster_wird_gezaehlt_nicht_geloescht(self):
        d = SZ.baue([mm(ko_h=40)], now=NOW)
        self.assertEqual(d["rest"]["spaeter"], 1)

    def test_ohne_anpfiff_wird_nicht_geraten(self):
        m = mm(); m["kickoff"] = None
        d = SZ.baue([m], now=NOW)
        self.assertEqual(d["zeilen"], [])
        self.assertEqual(d["rest"]["gelaufen"], 1)

    def test_duenne_zeilen_stehen_unten(self):
        gross, klein = mm(), mm(bf=("home", 95, 627), poly=("home", 66, 3577))
        klein["matchId"] = "2"; klein["home"] = "Nomme Kalju"; klein["away"] = "Nomme Utd"
        d = SZ.baue([klein, gross], now=NOW)
        self.assertEqual([z["home"] for z in d["zeilen"]], ["Real Madrid", "Nomme Kalju"])
        self.assertFalse(d["zeilen"][0]["duenn"])
        self.assertTrue(d["zeilen"][1]["duenn"])


class TestCard(unittest.TestCase):
    def _fx(self, markt="Heimsieg", verdict="BET", conv=8):
        return [{"home": "Real Madrid", "away": "Inter",
                 "picks": [{"market": markt, "verdict": verdict, "convictionScore": conv,
                            "odds": 1.8}]}]

    def test_eigene_card_wird_gezeigt_stimmt_aber_nicht_mit_ab(self):
        z = SZ.baue([mm(poly=None)], fixtures=self._fx(), now=NOW)
        # Nur Betfair spricht -> keine Deckung; die Card haelt die Zeile trotzdem in der Liste,
        # weil sie unsere eigene Aussage zu diesem Spiel ist.
        self.assertEqual(len(z["zeilen"]), 1)
        r = z["zeilen"][0]
        self.assertEqual(r["urteil"], "eine Geldquelle")
        self.assertEqual(r["card"]["seite"], "home")
        self.assertEqual(r["nGeld"], 1)

    def test_nur_bet_picks(self):
        z = SZ.baue([mm()], fixtures=self._fx(verdict="NOBET"), now=NOW)["zeilen"][0]
        self.assertIsNone(z["card"])

    def test_markt_ohne_vergleichbare_seite_bekommt_keine(self):
        z = SZ.baue([mm()], fixtures=self._fx(markt="Über 2.5 Tore"), now=NOW)["zeilen"][0]
        self.assertIsNotNone(z["card"])
        self.assertIsNone(z["card"]["seite"])

    def test_auswaertssieg_ist_away(self):
        # Tippfehler-Falle: „Auswärtssieg" muss away sein, nicht home.
        z = SZ.baue([mm()], fixtures=self._fx(markt="Auswärtssieg"), now=NOW)["zeilen"][0]
        self.assertEqual(z["card"]["seite"], "away")


class TestFixturesJoin(unittest.TestCase):
    def test_picks_haengen_in_der_map_nicht_am_fixture(self):
        liga = {"groups": {"ENG": {"fixtures": [
            {"home": "42", "away": "1346", "homeName": "Arsenal", "awayName": "Coventry",
             "matchday": 1, "kickoff": "2026-09-08T19:00:00Z"}]}},
            "picks": {"ENG-1-42-1346": [{"market": "Heimsieg", "verdict": "BET",
                                         "convictionScore": 9, "odds": 1.5}]}}
        fx = SZ.fixtures_aus(liga, None)
        self.assertEqual(len(fx), 1)
        self.assertEqual(fx[0]["home"], "Arsenal")
        self.assertEqual(fx[0]["picks"][0]["market"], "Heimsieg")

    def test_fixture_ohne_picks_kommt_nicht_mit(self):
        liga = {"groups": {"ENG": {"fixtures": [
            {"home": "42", "away": "1346", "homeName": "Arsenal", "awayName": "Coventry",
             "matchday": 1}]}}, "picks": {}}
        self.assertEqual(SZ.fixtures_aus(liga, None), [])


if __name__ == "__main__":
    unittest.main()


# ── 08.09.2026: der Join ueber den Poly-Marktschluessel (Ebene 3) ───────────────────────
def _wette(event, markt, auswahl, usd, stunden=4.0, liga="X"):
    from datetime import timedelta
    ko = (SZ._now() + timedelta(hours=stunden)).isoformat()
    return {"event": event, "markt": markt, "auswahl": auswahl, "einsatzUsd": usd,
            "anpfiff": ko, "liga": liga, "eventId": event}


class TestPaartBrauchtBeideNamen:
    """⭐ Die Fehlerklasse, die der Poly-Join sichtbar gemacht hat.

    Gemessen am 08.09.: `Cincinnati Reds / Los Angeles Dodgers` wurde mit dem Stake-Event
    `Boston Red Sox - Los Angeles Angels` gepaart. „Los Angeles Dodgers" gegen „Los Angeles
    Angels" bringt 0,67 (die STADT), „Cincinnati Reds" gegen „Boston Red Sox" bringt 0,00 —
    Summe ueber der Huerde. Ein Name trug den ganzen Join, der andere widersprach.
    """

    def test_ein_name_allein_traegt_keinen_join(self):
        assert not SZ.paart("Cincinnati Reds", "Los Angeles Dodgers",
                            "Boston Red Sox", "Los Angeles Angels")

    def test_richtige_paarung_bleibt(self):
        assert SZ.paart("Cincinnati Reds", "Los Angeles Dodgers",
                        "Cincinnati Reds", "Los Angeles Dodgers")
        assert SZ.paart("Ben Shelton", "Carlos Alcaraz", "Ben Shelton", "Carlos Alcaraz")

    def test_teilnamen_reichen_weiterhin(self):
        """Die Huerde darf keinen echten Treffer kosten — der Fussball-Join lebt von
        Kurzformen („Gill, Felix" gegen „Felix Gill")."""
        assert SZ.paart("Felix Gill", "Sebastian Ofner", "Gill, Felix", "Sebastian Ofner")


class TestStakeJePolyKey:
    MARKT = {"atp-a-b-2026-09-08": {"prices": {"Frances Tiafoe": 0.7, "Alex Michelsen": 0.3},
                                    "league": "TENNIS"}}

    def test_join_findet_das_spiel_und_die_seite(self):
        idx = SZ.stake_je_polykey(self.MARKT, [
            _wette("Frances Tiafoe - Alex Michelsen", "Winner", "Frances Tiafoe", 6404),
            _wette("Frances Tiafoe - Alex Michelsen", "1st Set - Winner", "Alex Michelsen", 1023)])
        e = idx["atp-a-b-2026-09-08"]
        assert e["seite"] == "Frances Tiafoe", "die Seite kommt im POLY-Namen zurueck"
        assert e["usd"] == 7427 and e["n"] == 2

    def test_satzsieger_ist_keine_spielseite(self):
        """„1st Set - Winner" traegt Geld, aber keine Seite fuer das ganze Spiel — genau wie
        „Over 1.5" beim Fussball. Wer beides addiert, macht aus zwei Wetten eine Meinung."""
        idx = SZ.stake_je_polykey(self.MARKT, [
            _wette("Frances Tiafoe - Alex Michelsen", "2nd Set - Winner", "Alex Michelsen", 9000)])
        e = idx["atp-a-b-2026-09-08"]
        assert e["seite"] is None
        assert e["usd"] == 9000, "das Geld bleibt sichtbar, es stimmt nur nicht mit ab"

    def test_winner_zaehlt_auch_ausserhalb_des_fussballs(self):
        """Der Grund fuer die Erweiterung: bei Tennis heisst 1X2 „Winner". Vorher hatte in
        Ebene 3 KEIN einziger Tennis-Play eine Stake-Seite, obwohl Geld dalag."""
        for markt in ("Winner", "Match Winner - Twoway", "Winner (Incl. Extra Innings)"):
            idx = SZ.stake_je_polykey(self.MARKT, [
                _wette("Frances Tiafoe - Alex Michelsen", markt, "Frances Tiafoe", 5000)])
            assert idx["atp-a-b-2026-09-08"]["seite"] == "Frances Tiafoe", markt

    def test_unter_dem_boden_stimmt_stake_nicht_mit(self):
        idx = SZ.stake_je_polykey(self.MARKT, [
            _wette("Frances Tiafoe - Alex Michelsen", "Winner", "Frances Tiafoe", 120)])
        assert idx["atp-a-b-2026-09-08"]["seite"] is None

    def test_drei_wege_markt_kommt_gar_nicht_in_den_join(self):
        """Mit Remis gibt es keine zwei Seiten, die sich mit „A - B" paaren lassen — dann wird
        nicht mit zwei von drei Namen verglichen, sondern gar nicht."""
        # Die beiden ERSTEN Namen passen hier absichtlich exakt zum Stake-Event — nur die
        # Drei-Wege-Regel selbst haelt den Eintrag draussen. Mit einem Remis-Namen an dritter
        # Stelle waere sonst offen, ob die Namenshuerde oder diese Regel gegriffen hat.
        drei = {"k": {"prices": {"Bayern": 0.5, "Dortmund": 0.3, "Draw": 0.2}}}
        assert SZ.stake_je_polykey(drei, [_wette("Bayern - Dortmund", "1x2", "Bayern", 5000)]) == {}
        # Gegenprobe: dasselbe Spiel als Zwei-Wege-Markt geht durch.
        zwei = {"k": {"prices": {"Bayern": 0.6, "Dortmund": 0.4}}}
        assert SZ.stake_je_polykey(zwei, [_wette("Bayern - Dortmund", "1x2", "Bayern", 5000)])

    def test_more_markets_landet_unter_dem_basisschluessel(self):
        m = {"atp-a-b-2026-09-08-more-markets": self.MARKT["atp-a-b-2026-09-08"]}
        idx = SZ.stake_je_polykey(m, [
            _wette("Frances Tiafoe - Alex Michelsen", "Winner", "Frances Tiafoe", 5000)])
        assert list(idx) == ["atp-a-b-2026-09-08"]

    def test_falsche_paarung_kommt_nicht_durch(self):
        """Der reale Fall vom 08.09., jetzt als Wachhund."""
        m = {"mlb-cin-lad": {"prices": {"Cincinnati Reds": 0.5, "Los Angeles Dodgers": 0.5}}}
        idx = SZ.stake_je_polykey(m, [
            _wette("Boston Red Sox - Los Angeles Angels", "Winner", "Boston Red Sox", 9000)])
        assert idx == {}

    def test_ohne_daten_leerer_index_statt_raten(self):
        assert SZ.stake_je_polykey(None, []) == {}
        assert SZ.stake_je_polykey({}, [_wette("A - B", "Winner", "A", 5000)]) == {}
