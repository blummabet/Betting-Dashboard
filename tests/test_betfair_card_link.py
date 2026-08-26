"""26.08.2026 — „unsere Card sagt X, und das Geld?"

Das Terminal zeigte in der Pick-Spalte immer die GELD-Seite von Betfair, nie unseren eigenen
Pick — man konnte also nicht sehen, ob die Börse mit uns oder gegen uns steht. Der Kartenlink
schließt das. Er urteilt NICHT: die Engine bleibt die einzige Instanz, die Picks bewertet.
"""
import betfair_card_link as L


def _ev(home="Real Madrid", away="Real Sociedad", date="2026-08-26", picks=None):
    return {"home": home, "away": away, "dateIso": date,
            "picks": picks if picks is not None else [
                {"market": "Heimsieg", "marketKey": "homeWin", "odds": 1.5, "sc": 0.8, "conf": "high"}]}


def _game(mid="1", home="Real Madrid", away="Real Sociedad", side="home", ko="2026-08-26T19:00:00Z"):
    return {"matchId": mid, "home": home, "away": away, "moneySide": side, "kickoff": ko}


class TestSeiten:
    def test_eindeutige_maerkte(self):
        assert L.sides_of("homeWin") == ("home",)
        assert L.sides_of("awayWin") == ("away",)

    def test_doppelte_chance_deckt_zwei_seiten(self):
        assert set(L.sides_of("dc1X")) == {"home", "draw"}
        assert set(L.sides_of("dcX2")) == {"draw", "away"}

    def test_handicap_ist_richtungs_eindeutig(self):
        assert L.sides_of("ah_home:-0.75") == ("home",)
        assert L.sides_of("ah_away:+1.0") == ("away",)

    def test_andere_achse_gibt_leer(self):
        """Tore, Ecken, BTTS, Halbzeit liegen NICHT auf der 1X2-Achse — lieber kein Urteil
        als ein erfundenes."""
        for k in ("over25", "under25", "btts", "noBtts", "corners_over:9.5", "ht_over05"):
            assert L.sides_of(k) == (), k

    def test_unbekannt_gibt_leer(self):
        assert L.sides_of(None) == () and L.sides_of("voellig_neu") == ()


class TestUrteil:
    def test_geld_auf_unserer_seite(self):
        assert L.verdict(("home",), "home") is True

    def test_geld_dagegen(self):
        assert L.verdict(("home",), "away") is False

    def test_doppelte_chance_trifft_auch_das_remis(self):
        assert L.verdict(("home", "draw"), "draw") is True

    def test_nicht_vergleichbar_ist_none_nicht_false(self):
        """None heißt „andere Achse", False heißt „das Geld steht gegen uns". Die zu
        verwechseln würde im Terminal einen Widerspruch anzeigen, den es nicht gibt."""
        assert L.verdict((), "home") is None
        assert L.verdict(("home",), None) is None


class TestBesterPick:
    def test_hoechste_konviktion_gewinnt(self):
        p = L.best_pick([{"marketKey": "over25", "sc": 0.4}, {"marketKey": "homeWin", "sc": 0.9}])
        assert p["marketKey"] == "homeWin"

    def test_bei_gleichstand_gewinnt_die_vergleichbare_achse(self):
        p = L.best_pick([{"marketKey": "over25", "sc": 0.8}, {"marketKey": "homeWin", "sc": 0.8}])
        assert p["marketKey"] == "homeWin"

    def test_kaputte_konviktion_wirft_nicht(self):
        p = L.best_pick([{"marketKey": "over25", "sc": "kaputt"}, {"marketKey": "homeWin", "sc": 0.5}])
        assert p["marketKey"] == "homeWin"

    def test_leer(self):
        assert L.best_pick([]) is None and L.best_pick(None) is None

    def test_muell_wird_uebersprungen(self):
        assert L.best_pick([None, "x", {"marketKey": "homeWin", "sc": 0.3}])["marketKey"] == "homeWin"


class TestLink:
    def test_exakter_treffer(self):
        r = L.link([_game()], [_ev()])
        assert r["nExact"] == 1 and r["nBridge"] == 0
        row = r["links"]["1"]
        assert row["agree"] is True and row["market"] == "Heimsieg" and row["matchedBy"] == "exakt"

    def test_namens_bruecke(self):
        """Betwatch schreibt „Betis", unsere Fixtures „Real Betis"."""
        r = L.link([_game(home="Valencia", away="Betis", side="away")],
                   [_ev(home="Valencia", away="Real Betis",
                        picks=[{"market": "Auswärtssieg", "marketKey": "awayWin", "sc": 0.6}])])
        assert r["nBridge"] == 1 and r["links"]["1"]["agree"] is True

    def test_ohne_card_kein_eintrag(self):
        """Pokal- und Auslandsspiele haben keine Card — die Zeile bleibt wie bisher."""
        assert L.link([_game(home="Barnsley", away="Crewe")], [_ev()])["links"] == {}

    def test_event_ohne_picks_wird_uebersprungen(self):
        assert L.link([_game()], [_ev(picks=[])])["links"] == {}

    def test_spiel_ohne_matchid_wird_uebersprungen(self):
        g = _game(); g["matchId"] = ""
        assert L.link([g], [_ev()])["links"] == {}

    def test_geld_gegen_uns_wird_als_false_gemeldet(self):
        r = L.link([_game(side="away")], [_ev()])
        assert r["links"]["1"]["agree"] is False

    def test_andere_achse_bleibt_ohne_urteil(self):
        r = L.link([_game()], [_ev(picks=[{"market": "Über 2.5", "marketKey": "over25", "sc": 0.7}])])
        row = r["links"]["1"]
        assert row["agree"] is None and row["market"] == "Über 2.5"

    def test_zwei_kandidaten_am_selben_tag_geben_keinen_treffer(self):
        """Lieber kein Link als der falsche — ein falscher haengt einem Spiel fremdes Geld an."""
        evs = [_ev(home="Athletic Club", away="Real Sociedad"),
               _ev(home="Athletic Bilbao", away="Real Sociedad")]
        r = L.link([_game(home="Athletic", away="Sociedad")], evs)
        assert r["links"] == {}

    def test_muell_wirft_nicht(self):
        assert L.link([None, "x"], [None, 5])["links"] == {}
        assert L.link(None, None)["links"] == {}


class TestKandidaten:
    """„0 verlinkt" muss von „0 verlinkbar" unterscheidbar sein — sonst sieht ein kaputter Link
    aus wie ein ruhiger Dienstag ohne Top-5-Spiele."""

    def test_gleicher_tag_zaehlt_als_kandidat(self):
        assert L.candidates([_game()], [_ev(date="2026-08-26")]) == 1

    def test_anderer_tag_ist_kein_kandidat(self):
        assert L.candidates([_game()], [_ev(date="2026-09-30")]) == 0

    def test_ohne_cards_keine_kandidaten(self):
        assert L.candidates([_game()], []) == 0

    def test_leeres_datum_zaehlt_nicht(self):
        g = _game(); g["kickoff"] = ""
        assert L.candidates([g], [_ev(date="")]) == 0

    def test_muell_wirft_nicht(self):
        assert L.candidates([None, "x"], [None, 3]) == 0
