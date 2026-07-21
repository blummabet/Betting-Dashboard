"""19.07.2026 — Cross-Sport-Radar: Poly vs. scharfe Pinnacle über mehrere Sportarten.

Read-only Kandidaten-Radar (Lucas: „ein bisschen tracken"). Der Wert steckt NICHT im Finden einer
Lücke, sondern im KONVERGENZ-Tracking: eine Lücke ist erst echt, wenn sie sich über die Tage
schließt. Diese Tests fixieren beide Hälften — und die Grenzen, an denen eine Scheinlücke NICHT
gelistet werden darf (Krypto-Lehre: Poly vs. eine Fair verliert, wenn man Artefakte für Edge hält).
"""
import poly_cross_sport as X


def _poly(prob, vol=45000, ekey="lakers-celtics", okey="lakers", sport="NBA"):
    return {"sport": sport, "event": "Lakers vs Celtics", "market": "Moneyline",
            "outcome": "Lakers", "prob": prob, "vol": vol,
            "eventKey": ekey, "outcomeKey": okey}


IDX = {("lakers-celtics", "lakers"): 0.55, ("lakers-celtics", "celtics"): 0.45}


class TestDevig:
    def test_zwei_wege_summiert_auf_eins(self):
        a, b = X.devig_2way(1 / 1.9, 1 / 2.1)
        assert abs((a + b) - 1.0) < 1e-9

    def test_kaputt_gibt_none(self):
        assert X.devig_2way(0, 0) == (None, None)
        assert X.devig_2way(None, 0.5) == (None, None)


class TestDiscrepancies:
    def test_grosse_luecke_wird_gefunden_mit_richtung(self):
        d = X.compute_discrepancies([_poly(0.62)], IDX)
        assert len(d) == 1 and d[0]["gapPP"] == 7.0
        assert "faden" in d[0]["richtung"], "Poly zu hoch → faden"

    def test_poly_zu_niedrig_ist_backen(self):
        d = X.compute_discrepancies([_poly(0.45)], IDX)   # Poll 45 vs fair 55 = -10pp
        assert d[0]["gapPP"] == -10.0 and "backen" in d[0]["richtung"]

    def test_kleine_luecke_raus(self):
        assert X.compute_discrepancies([_poly(0.58)], IDX) == []   # 3pp < MIN_GAP 6

    def test_duenner_markt_raus(self):
        assert X.compute_discrepancies([_poly(0.70, vol=200)], IDX) == []

    def test_ohne_pinnacle_gegenstueck_nicht_bewertbar(self):
        d = X.compute_discrepancies([_poly(0.70, okey="unbekannt")], IDX)
        assert d == [], "ohne scharfen Anker darf nichts gelistet werden"

    def test_groesste_luecke_zuerst(self):
        d = X.compute_discrepancies([_poly(0.62), _poly(0.80, okey="lakers")], IDX)
        # zweite hätte 25pp; da gleicher key nur einer im idx — beide gegen fair 0.55
        assert abs(d[0]["gapPP"]) >= abs(d[-1]["gapPP"])


class TestKonvergenz:
    def test_erste_luecke_wird_festgehalten(self):
        d = X.compute_discrepancies([_poly(0.62)], IDX)
        h = X.update_history({}, d)
        key = d[0]["id"]
        assert h[key]["firstGapPP"] == 7.0

    def test_schrumpfende_luecke_ist_positive_konvergenz(self):
        d1 = X.compute_discrepancies([_poly(0.62)], IDX)         # 7pp
        h = X.update_history({}, d1)
        d2 = X.compute_discrepancies([_poly(0.58)], IDX, {"min_gap_pp": 1})  # 3pp
        X.update_history(h, d2)
        assert d2[0]["convergePP"] == 4.0, "7→3pp = 4pp geschlossen (Poly läuft zur Pinnacle = echt)"

    def test_stehende_luecke_ist_null_konvergenz(self):
        d1 = X.compute_discrepancies([_poly(0.62)], IDX)
        h = X.update_history({}, d1)
        d2 = X.compute_discrepancies([_poly(0.62)], IDX)         # unverändert
        X.update_history(h, d2)
        assert d2[0]["convergePP"] == 0.0, "bleibt stehen → Artefakt-Verdacht, keine Konvergenz"

    def test_alte_eintraege_werden_gepruned(self):
        from datetime import datetime, timedelta, timezone
        alt = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        h = {"NBA|x-y|z": {"firstGapPP": 8, "lastGapPP": 8, "lastSeen": alt,
                           "firstSeen": alt, "event": "e", "outcome": "o", "sport": "NBA"}}
        h2 = X.update_history(h, [])
        assert "NBA|x-y|z" not in h2, "verschwundener Markt muss gepruned werden"


def test_norm_matcht_ueber_venues():
    assert X.norm("Los Angeles Lakers") == X.norm("los angeles lakers")
    assert X.norm("St. Louis") == "stlouis"


class TestEventKeyReihenfolgeUnabhaengig:
    """20.07.2026 — der Radar war leer, u.a. weil ein `home-away`-Key bei gedrehter Poly-Reihenfolge
    nie matchte. event_key muss reihenfolge-UNABHÄNGIG sein, sonst findet compute_discrepancies nie
    das scharfe Gegenstück."""

    def test_gedrehte_reihenfolge_gleicher_key(self):
        assert X.event_key("Los Angeles Lakers", "Boston Celtics") == \
               X.event_key("Boston Celtics", "Los Angeles Lakers")

    def test_key_form(self):
        assert X.event_key("Boston Celtics", "Los Angeles Lakers") == "bostonceltics-losangeleslakers"

    def test_poly_matcht_pinnacle_trotz_drehung(self):
        # Pinnacle kennt Heim/Auswärts (Lakers Heim), Poly listet Celtics zuerst → muss trotzdem matchen.
        pinn = X.fetch_pinnacle_index(
            ["basketball_nba"],
            fetch=lambda sk: [{
                "home_team": "Los Angeles Lakers", "away_team": "Boston Celtics",
                "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Los Angeles Lakers", "price": 1.8},
                    {"name": "Boston Celtics", "price": 2.1}]}]}],
            }])
        rows = X.fetch_poly_rows(
            ["basketball_nba"],
            gamma_fetch=lambda tag: [{
                "volume": 50000,
                "markets": [{"conditionId": "0xabc",
                             "outcomes": '["Boston Celtics", "Los Angeles Lakers"]',
                             "outcomePrices": '["0.40", "0.60"]',
                             "clobTokenIds": '["t1", "t2"]'}],
            }])
        disc = X.compute_discrepancies(rows, pinn)
        # Lakers: Poly 60% vs de-viggte Pinnacle ~53.8% → ~6pp Lücke; Match GELINGT trotz Drehung.
        assert disc, "Poly-Reihenfolge gedreht → muss trotzdem gegen Pinnacle matchen"
        assert any(d["outcome"] == "Los Angeles Lakers" for d in disc)


class TestMatchedDiagnose:
    """21.07.2026 (Lucas: „hängt da was?") — die Ausgabe muss messbar machen, ob die Poly-Rows
    überhaupt ein Pinnacle-Gegenstück finden. matched=0 bei pinnKeys>0 = Namens-Matching kaputt."""

    def _rows(self):
        return [
            {"sport": "basketball_nba", "event": "A vs B", "market": "Moneyline",
             "outcome": "A", "prob": 0.60, "vol": 50000, "eventKey": "a-b", "outcomeKey": "a"},
            {"sport": "basketball_nba", "event": "A vs B", "market": "Moneyline",
             "outcome": "B", "prob": 0.40, "vol": 50000, "eventKey": "a-b", "outcomeKey": "b"},
        ]

    def test_matched_und_pinnkeys_werden_geschrieben(self, tmp_path, monkeypatch):
        import json as _j
        monkeypatch.setattr(X, "BASE", tmp_path)
        monkeypatch.setattr(X, "fetch_poly_rows", lambda sports: self._rows())
        monkeypatch.setattr(X, "fetch_pinnacle_index",
                            lambda sports: {("a-b", "a"): 0.55, ("a-b", "b"): 0.45})
        X.main()
        out = _j.loads((tmp_path / "poly_cross_sport.json").read_text())
        assert out["matched"] == 2 and out["pinnKeys"] == 2

    def test_kein_match_ist_sichtbar(self, tmp_path, monkeypatch):
        # Pinnacle hat Daten, aber unter anderen Namen → matched=0 (Matching-Problem sichtbar).
        import json as _j
        monkeypatch.setattr(X, "BASE", tmp_path)
        monkeypatch.setattr(X, "fetch_poly_rows", lambda sports: self._rows())
        monkeypatch.setattr(X, "fetch_pinnacle_index",
                            lambda sports: {("x-y", "x"): 0.55, ("x-y", "y"): 0.45})
        X.main()
        out = _j.loads((tmp_path / "poly_cross_sport.json").read_text())
        assert out["matched"] == 0 and out["pinnKeys"] == 2


class TestFetchPolyRows:
    def _ev(self, a, b, pa, pb, vol=50000):
        import json as _j
        return {"volume": vol, "markets": [{"conditionId": "0x1",
                "outcomes": _j.dumps([a, b]), "outcomePrices": _j.dumps([str(pa), str(pb)]),
                "clobTokenIds": '["t1","t2"]'}]}

    def test_zwei_wege_gibt_zwei_zeilen(self):
        rows = X.fetch_poly_rows(["baseball_mlb"],
                                 gamma_fetch=lambda tag: [self._ev("A", "B", 0.55, 0.45)])
        assert len(rows) == 2
        assert {r["outcome"] for r in rows} == {"A", "B"}
        assert all(r["eventKey"] == "a-b" for r in rows)
        assert rows[0]["vol"] == 50000 and rows[0]["market"] == "Moneyline"

    def test_nicht_zwei_wege_wird_verworfen(self):
        # 3-Wege (Fußball) hat hier keine 2-Wege-Pinnacle-Entsprechung → überspringen.
        ev = self._ev("A", "B", 0.4, 0.35)
        import json as _j
        ev["markets"][0]["outcomes"] = _j.dumps(["A", "Draw", "B"])
        ev["markets"][0]["outcomePrices"] = _j.dumps(["0.4", "0.25", "0.35"])
        assert X.fetch_poly_rows(["soccer_epl"], gamma_fetch=lambda tag: [ev]) == []

    def test_tag_mapping(self):
        assert X._poly_tag_for("basketball_nba") == "nba"
        assert X._poly_tag_for("americanfootball_nfl") == "nfl"
        assert X._poly_tag_for("soccer_epl") == "epl"
        assert X._poly_tag_for("unbekannt_xyz") == "xyz"   # Fallback: letztes Segment

    def test_dedup_gleiches_event_gleicher_sport(self):
        ev = self._ev("A", "B", 0.55, 0.45)
        rows = X.fetch_poly_rows(["baseball_mlb"], gamma_fetch=lambda tag: [ev, ev])
        assert len(rows) == 2, "dasselbe Event doppelt geliefert → nur einmal (2 Ausgänge)"

    def test_leerer_fetch_ist_leer(self):
        assert X.fetch_poly_rows(["baseball_mlb"], gamma_fetch=lambda tag: []) == []
