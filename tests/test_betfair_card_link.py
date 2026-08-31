"""26.08.2026 — „unsere Card sagt X, und das Geld?" · 28.08.2026 — Quelle korrigiert (Lucas)

Das Terminal zeigte in der Pick-Spalte immer die GELD-Seite von Betfair, nie unseren Pick.

⚠️ Der Kartenlink las zuerst `picks_output.json` — das ALTE breite 20-Ligen-System. Im Terminal
stand bei Bayern–Stuttgart deshalb „1. HZ: Over 0.5 Tore", ein Markt, den wir gar nicht mehr
anbieten, während die echte Card „Über 3.5 Tore @1.50" sagt. Es gibt ZWEI parallele Pick-Systeme
im Repo; die National-Cards kommen aus `liga-data.json`. Diese Tests halten die Quelle fest.
"""
import betfair_card_link as L


def _fx(home="Real Madrid", away="Real Sociedad", date="2026-08-26", picks=None):
    return {"home": home, "away": away, "dateIso": date,
            "picks": picks if picks is not None else [
                {"market": "Heimsieg", "odds": 1.5, "verdict": "ABWÄGEN", "convictionScore": 6}]}


def _game(mid="1", home="Real Madrid", away="Real Sociedad", side="home", ko="2026-08-26T19:00:00Z"):
    return {"matchId": mid, "home": home, "away": away, "moneySide": side, "kickoff": ko}


class TestSeitenAusDemLabel:
    """liga-data.json führt nur das deutsche Label, keinen marketKey."""

    def test_eindeutige_maerkte(self):
        assert L.sides_of("Heimsieg") == ("home",)
        assert L.sides_of("Auswärtssieg") == ("away",)
        assert L.sides_of("Unentschieden") == ("draw",)

    def test_doppelte_chance_mit_gedankenstrich(self):
        assert set(L.sides_of("Doppelte Chance — 1X")) == {"home", "draw"}
        assert set(L.sides_of("Doppelte Chance — X2")) == {"draw", "away"}

    def test_handicap_ist_richtungs_eindeutig(self):
        assert L.sides_of("AH Heim −1.25") == ("home",)
        assert L.sides_of("AH Auswärts −0.25") == ("away",)

    def test_andere_achse_bekommt_kein_urteil(self):
        for m in ("Über 3.5 Tore", "Unter 2.5 Tore", "Beide Teams treffen — Ja",
                  "Beide Teams treffen — Nein", "1. HZ: Over 0.5 Tore"):
            assert L.sides_of(m) == (), m

    def test_muell_wirft_nicht(self):
        for m in (None, "", 5, "voellig neu"):
            assert L.sides_of(m) == ()


class TestBesterPick:
    def test_nobet_ist_kein_pick(self):
        """140 von 172 Picks in liga-data sind NOBET — die dürfen nie als „unsere Card" gelten."""
        assert L.best_pick([{"market": "Heimsieg", "verdict": "NOBET", "convictionScore": 9}]) is None

    def test_bet_schlaegt_abwaegen(self):
        p = L.best_pick([{"market": "A", "verdict": "ABWÄGEN", "convictionScore": 9},
                         {"market": "B", "verdict": "BET", "convictionScore": 3}])
        assert p["market"] == "B"

    def test_dann_hoehere_conviction(self):
        p = L.best_pick([{"market": "A", "verdict": "ABWÄGEN", "convictionScore": 4},
                         {"market": "B", "verdict": "ABWÄGEN", "convictionScore": 7}])
        assert p["market"] == "B"

    def test_bei_gleichstand_die_vergleichbare_achse(self):
        p = L.best_pick([{"market": "Über 2.5 Tore", "verdict": "ABWÄGEN", "convictionScore": 6},
                         {"market": "Heimsieg", "verdict": "ABWÄGEN", "convictionScore": 6}])
        assert p["market"] == "Heimsieg"

    def test_kaputte_conviction_wirft_nicht(self):
        p = L.best_pick([{"market": "A", "verdict": "ABWÄGEN", "convictionScore": "x"},
                         {"market": "B", "verdict": "ABWÄGEN", "convictionScore": 2}])
        assert p["market"] == "B"

    def test_leer(self):
        assert L.best_pick([]) is None and L.best_pick(None) is None
        assert L.best_pick([None, "x"]) is None


class TestFixturesIndex:
    DATA = {
        "groups": {"GER": {"fixtures": [
            {"home": "157", "away": "172", "homeName": "Bayern München", "awayName": "VfB Stuttgart",
             "date": "2026-08-28", "matchday": 1}]}},
        "koFixtures": [{"home": "1", "away": "2", "homeName": "A", "awayName": "B",
                        "date": "2026-09-01", "matchday": 30, "round": "R16"}],
        "picks": {"GER-1-157-172": [{"market": "Über 3.5 Tore", "odds": 1.5,
                                     "verdict": "ABWÄGEN", "convictionScore": 6}],
                  "R16-30-1-2": [{"market": "Heimsieg", "odds": 2.0,
                                  "verdict": "BET", "convictionScore": 8}]},
    }

    def test_der_echte_fall_bayern_stuttgart(self):
        """Nicht „1. HZ: Over 0.5" aus dem alten System, sondern die echte Card."""
        idx = L.fixtures_index(self.DATA)
        b = next(f for f in idx if f["home"] == "Bayern München")
        assert [p["market"] for p in b["picks"]] == ["Über 3.5 Tore"]

    def test_ko_fixtures_kommen_mit(self):
        """KO-Spiele liegen in koFixtures, nicht in groups — das hat schon mehrfach Picks gekostet."""
        idx = L.fixtures_index(self.DATA)
        ko = next(f for f in idx if f["home"] == "A")
        assert ko["picks"] and ko["picks"][0]["verdict"] == "BET"

    def test_fixture_ohne_picks_bleibt_drin_aber_leer(self):
        d = {"groups": {"GER": {"fixtures": [{"home": "9", "away": "8", "date": "2026-09-01", "matchday": 2}]}}}
        assert L.fixtures_index(d)[0]["picks"] == []

    def test_muell_wirft_nicht(self):
        assert L.fixtures_index(None) == []
        assert L.fixtures_index({"groups": {"X": {"fixtures": [None, "y"]}}}) == []


class TestUrteil:
    def test_geld_auf_unserer_seite(self):
        assert L.verdict(("home",), "home") is True

    def test_geld_dagegen(self):
        assert L.verdict(("home",), "away") is False

    def test_nicht_vergleichbar_ist_none_nicht_false(self):
        """None heißt „andere Achse", False heißt „das Geld steht gegen uns"."""
        assert L.verdict((), "home") is None
        assert L.verdict(("home",), None) is None


class TestLink:
    def test_exakter_treffer(self):
        r = L.link([_game()], [_fx()])
        assert r["nExact"] == 1
        row = r["links"]["1"]
        assert row["agree"] is True and row["market"] == "Heimsieg" and row["sc"] == 6

    def test_namens_bruecke(self):
        """Betwatch schreibt „Stuttgart", unsere Fixtures „VfB Stuttgart"."""
        r = L.link([_game(home="Bayern Munich", away="Stuttgart", side="home", ko="2026-08-28T18:30:00Z")],
                   [_fx(home="Bayern München", away="VfB Stuttgart", date="2026-08-28")])
        assert r["nBridge"] == 1 and r["links"]["1"]["agree"] is True

    def test_nur_nobet_ergibt_keinen_link(self):
        r = L.link([_game()], [_fx(picks=[{"market": "Heimsieg", "verdict": "NOBET", "convictionScore": 9}])])
        assert r["links"] == {}

    def test_tor_pick_bleibt_ohne_urteil(self):
        r = L.link([_game()], [_fx(picks=[{"market": "Über 3.5 Tore", "odds": 1.5,
                                           "verdict": "ABWÄGEN", "convictionScore": 6}])])
        row = r["links"]["1"]
        assert row["agree"] is None and row["market"] == "Über 3.5 Tore"

    def test_ohne_card_kein_eintrag(self):
        assert L.link([_game(home="Barnsley", away="Crewe")], [_fx()])["links"] == {}

    def test_zwei_kandidaten_am_selben_tag_geben_keinen_treffer(self):
        evs = [_fx(home="Athletic Club", away="Real Sociedad"),
               _fx(home="Athletic Bilbao", away="Real Sociedad")]
        assert L.link([_game(home="Athletic", away="Sociedad")], evs)["links"] == {}

    def test_muell_wirft_nicht(self):
        assert L.link([None, "x"], [None, 5])["links"] == {}
        assert L.link(None, None)["links"] == {}


class TestKandidaten:
    def test_gleicher_tag_zaehlt_als_kandidat(self):
        assert L.candidates([_game()], [_fx(date="2026-08-26")]) == 1

    def test_anderer_tag_ist_kein_kandidat(self):
        assert L.candidates([_game()], [_fx(date="2026-09-30")]) == 0

    def test_muell_wirft_nicht(self):
        assert L.candidates([None, "x"], [None, 3]) == 0


# ── Tor-/BTTS-Achse (28.08.2026, Lucas) ─────────────────────────────────────
# „Wieso wird ein Über-Pick nicht mit der Over-Seite verglichen? Da liegt was oben."
# Zu Recht: der Roh-Snapshot hat die ganze Leiter. Bayern–Stuttgart, Ü/U 3.5: 7.039 € gematcht,
# davon 6.140 auf Over — 87 % auf unserer Seite. Diese Aussage wurde vorher verschenkt.

def _snap(markets):
    return {"matchId": "1", "home": "Bayern Munich", "away": "Stuttgart", "markets": markets}


def _ou(linie, under_vol, over_vol):
    return {"Over/Under %s Goals" % linie: {"runners": [
        {"name": "Under %s Goals" % linie, "vol": under_vol},
        {"name": "Over %s Goals" % linie, "vol": over_vol}]}}


class TestBoersenZiel:
    def test_ueber_unter_wird_auf_die_leiter_abgebildet(self):
        assert L.betfair_target("Über 3.5 Tore") == ("Over/Under 3.5 Goals", "Over")
        assert L.betfair_target("Unter 2.5 Tore") == ("Over/Under 2.5 Goals", "Under")

    def test_btts(self):
        assert L.betfair_target("Beide Teams treffen — Ja") == ("Both teams to Score?", "Yes")
        assert L.betfair_target("Beide Teams treffen — Nein") == ("Both teams to Score?", "No")

    def test_1x2_hat_hier_nichts_zu_suchen(self):
        for m in ("Heimsieg", "Auswärtssieg", "AH Heim −1.25", "Doppelte Chance — X2"):
            assert L.betfair_target(m) is None, m

    def test_muell(self):
        for m in (None, "", "Über Tore", 5):
            assert L.betfair_target(m) is None


class TestTorGeld:
    def test_der_echte_fall_bayern_stuttgart(self):
        r = L.goal_market_money(_snap(_ou("3.5", 898, 6140)), "Über 3.5 Tore")
        assert r["eur"] == 7038 and r["sharePct"] == 87 and r["agree"] is True
        assert r["marketName"] == "Over/Under 3.5 Goals" and r["side"] == "Over"

    def test_geld_gegen_uns(self):
        r = L.goal_market_money(_snap(_ou("2.5", 4000, 1000)), "Über 2.5 Tore")
        assert r["agree"] is False and r["sharePct"] == 20

    def test_unter_seite_wird_richtig_gezaehlt(self):
        r = L.goal_market_money(_snap(_ou("2.5", 4000, 1000)), "Unter 2.5 Tore")
        assert r["agree"] is True and r["sharePct"] == 80

    def test_falsche_linie_zaehlt_nicht_mit(self):
        """Ü/U 2.5 und Ü/U 3.5 sind verschiedene Märkte — hier darf nichts durchrutschen."""
        assert L.goal_market_money(_snap(_ou("2.5", 100, 900)), "Über 3.5 Tore") is None

    def test_markt_ohne_geld_gibt_kein_urteil(self):
        assert L.goal_market_money(_snap(_ou("3.5", 0, 0)), "Über 3.5 Tore") is None

    def test_fehlender_snapshot(self):
        assert L.goal_market_money(None, "Über 3.5 Tore") is None
        assert L.goal_market_money({}, "Über 3.5 Tore") is None

    def test_muell_wirft_nicht(self):
        snap = _snap({"Over/Under 3.5 Goals": {"runners": [None, {"name": None, "vol": "x"}]}})
        assert L.goal_market_money(snap, "Über 3.5 Tore") is None


class TestLinkMitTorAchse:
    def test_tor_pick_bekommt_jetzt_ein_urteil(self):
        fx = _fx(home="Bayern München", away="VfB Stuttgart", date="2026-08-28",
                 picks=[{"market": "Über 3.5 Tore", "odds": 1.5,
                         "verdict": "ABWÄGEN", "convictionScore": 6}])
        g = _game(home="Bayern Munich", away="Stuttgart", ko="2026-08-28T18:30:00Z")
        r = L.link([g], [fx], {"1": _snap(_ou("3.5", 898, 6140))})
        row = r["links"]["1"]
        assert row["agree"] is True and row["achse"] == "tor"
        assert row["torSharePct"] == 87 and row["torEur"] == 7038

    def test_ohne_snapshot_bleibt_es_ohne_urteil(self):
        fx = _fx(picks=[{"market": "Über 3.5 Tore", "odds": 1.5,
                         "verdict": "ABWÄGEN", "convictionScore": 6}])
        r = L.link([_game()], [fx], {})
        assert r["links"]["1"]["agree"] is None and r["links"]["1"]["achse"] is None

    def test_1x2_bleibt_die_1x2_achse(self):
        """Der neue Pfad darf den alten nicht überschreiben."""
        r = L.link([_game(side="home")], [_fx()], {"1": _snap(_ou("3.5", 900, 6000))})
        row = r["links"]["1"]
        assert row["achse"] == "1X2" and row["agree"] is True and row["torMarkt"] is None


class TestHinUndRueckspiel:
    """⚠️ 31.08.2026 — der Bug, der den exakten Pfad unmöglich machte.

    `event_key` ist reihenfolge-unabhängig: Hin- und Rückspiel derselben Paarung ergeben
    denselben Schlüssel. Der Index lief nur über dieses Paar, also überschrieb das zuletzt
    eingelesene Fixture — über eine Saison praktisch immer das Rückspiel im Frühjahr, das noch
    keine Picks hat. Gemessen am 31.08.: 876 von 876 Schlüsseln doppelt belegt, 1 von 12
    Börsen-Spielen verlinkt. Der Schlüssel trägt seitdem den Tag.
    """

    def _paarung(self):
        heute = _fx(home="Aston Villa", away="Arsenal", date="2026-08-31",
                    picks=[{"market": "Auswärtssieg", "odds": 2.4,
                            "verdict": "ABWÄGEN", "convictionScore": 5}])
        rueck = _fx(home="Arsenal", away="Aston Villa", date="2027-04-17", picks=[])
        return heute, rueck

    def test_rueckspiel_ueberschreibt_das_heutige_spiel_nicht(self):
        heute, rueck = self._paarung()
        g = _game(home="Aston Villa", away="Arsenal", side="away",
                  ko="2026-08-31T19:00:00Z")
        r = L.link([g], [heute, rueck], {})
        assert r["links"]["1"]["market"] == "Auswärtssieg"
        assert r["nExact"] == 1 and r["nBridge"] == 0

    def test_reihenfolge_im_index_ist_egal(self):
        """Vorher hing das Ergebnis daran, welches Fixture zuletzt gelesen wurde."""
        heute, rueck = self._paarung()
        g = _game(home="Aston Villa", away="Arsenal", side="away",
                  ko="2026-08-31T19:00:00Z")
        a = L.link([g], [heute, rueck], {})
        b = L.link([g], [rueck, heute], {})
        assert a["links"].keys() == b["links"].keys()
        assert a["links"]["1"]["market"] == b["links"]["1"]["market"] == "Auswärtssieg"

    def test_das_rueckspiel_zieht_seinen_eigenen_tag(self):
        """Umgekehrt darf das Hinspiel nicht auf das Rückspiel durchschlagen."""
        heute, rueck = self._paarung()
        g = _game(home="Arsenal", away="Aston Villa", side="home",
                  ko="2027-04-17T14:00:00Z")
        r = L.link([g], [heute, rueck], {})
        assert r["links"] == {}          # Rückspiel hat (noch) keine Picks

    def test_anpfiff_kippt_ueber_mitternacht(self):
        """Anpfiff 00:15 UTC am Folgetag — das Fixture von gestern muss trotzdem greifen."""
        fx = _fx(home="Estudiantes", away="Newells", date="2026-08-31",
                 picks=[{"market": "Heimsieg", "odds": 1.9,
                         "verdict": "BET", "convictionScore": 7}])
        g = _game(home="Estudiantes", away="Newells", side="home",
                  ko="2026-09-01T00:15:00Z")
        r = L.link([g], [fx], {})
        assert r["links"]["1"]["market"] == "Heimsieg"


class TestKandidatenZahlWirdGemeldet:
    """`candidates()` gab es seit dem 26.08. — aber nur als Log-Zeile. Ohne sie in der Datei
    kann niemand „0 verlinkt" von „0 verlinkbar" unterscheiden, und genau daran blieb der
    Hin-/Rückspiel-Bug fünf Tage unsichtbar."""

    def test_kandidat_ohne_link_ist_nicht_dasselbe_wie_kein_kandidat(self):
        fx = _fx(home="Aston Villa", away="Arsenal", date="2026-08-31", picks=[])
        g = _game(home="Aston Villa", away="Arsenal", ko="2026-08-31T19:00:00Z")
        assert L.candidates([g], [fx]) == 1
        assert L.link([g], [fx], {})["links"] == {}


class TestCardQuellen:
    """⚠️ 31.08.2026 — der zweite Bruch, und der schwerere.

    `PICKS_FILE` hing an `D.data_file()`, also an `COCOBET_DATASET` — und `betfair.yml` setzt
    die Variable nicht. Gelesen wurde damit `wm2026-data.json`; die WM ist seit Juli vorbei,
    die Datei hat keine kommenden Fixtures. `nCandidates` war deshalb immer 0, und die Warnung
    „Kandidaten, aber kein Treffer" konnte gar nicht anschlagen. Die Börse ist nicht
    datensatz-gebunden: ein Radar-Lauf sieht Top-5 und MLS am selben Tag.
    """

    def test_beide_klub_datensaetze_werden_gelesen(self):
        namen = [f.name for f in L.PICKS_FILES]
        assert "liga-data.json" in namen and "mls-data.json" in namen

    def test_quellen_haengen_nicht_an_der_env(self, monkeypatch=None):
        """Ohne COCOBET_DATASET darf die WM-Datei nicht die einzige Quelle sein."""
        import os
        alt = os.environ.pop("COCOBET_DATASET", None)
        try:
            import importlib
            m = importlib.reload(L)
            namen = [f.name for f in m.PICKS_FILES]
            assert "liga-data.json" in namen and "mls-data.json" in namen
            assert namen[0] != "wm2026-data.json"
        finally:
            if alt is not None:
                os.environ["COCOBET_DATASET"] = alt
            import importlib
            importlib.reload(L)
