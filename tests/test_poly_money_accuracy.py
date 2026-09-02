"""19.07.2026 — Liegt das Poly-Geld richtig? Empirischer Test unserer „Poly ist nicht sharp"-These.

Zwei Hälften: die Geld-Verteilung nah am Anpfiff einfrieren (zeitkonsistent), dann gegen den
Ausgang auflösen. Der entscheidende Wert ist NICHT die Trefferquote, sondern **Brier Geld vs.
Preis** — sagt das Geld mehr als der Preis, oder ist es nur Rauschen, das der Preis eh enthält?
"""
import poly_money_accuracy as M


# ── Einfrieren ───────────────────────────────────────────────────────────────

def _sm(htk, total=50000, key="A-B", shares=(0.6, 0.2, 0.2)):
    return {"matches": {key: {"hoursToKickoff": htk, "totalUsd": total,
        "outcomes": {"home": {"share": shares[0]}, "draw": {"share": shares[1]},
                     "away": {"share": shares[2]}}}}}


def _pr(key="A-B", hw=0.45, dr=0.30, aw=0.30):
    return {"prices": {key: {"hw": hw, "dr": dr, "aw": aw}}}


class TestCapture:
    def test_friert_im_anpfiff_fenster_ein(self):
        f = M.capture(_sm(2.0), _pr(), {})
        assert "A-B" in f and f["A-B"]["shares"]["home"] == 0.6
        assert f["A-B"]["prices"]["home"] == 0.45

    def test_ausserhalb_fenster_nicht(self):
        assert M.capture(_sm(6.0), _pr(), {}) == {}          # zu früh
        assert M.capture(_sm(-1.0), _pr(), {}) == {}         # Anpfiff vorbei, nicht neu anlegen

    def test_dichtester_snapshot_gewinnt(self):
        f = M.capture(_sm(2.5), _pr(), {})
        f = M.capture(_sm(0.5, shares=(0.7, 0.15, 0.15)), _pr(), f)   # näher am Anpfiff
        assert f["A-B"]["hoursToKickoff"] == 0.5
        assert f["A-B"]["shares"]["home"] == 0.7

    def test_alter_snapshot_ueberschreibt_nicht_den_dichteren(self):
        f = M.capture(_sm(0.5), _pr(), {})
        f = M.capture(_sm(2.5), _pr(), f)     # weiter weg → ignorieren
        assert f["A-B"]["hoursToKickoff"] == 0.5

    def test_duenner_markt_raus(self):
        assert M.capture(_sm(2.0, total=200), _pr(), {}) == {}


# ── Auflösen ─────────────────────────────────────────────────────────────────

def _frozen(shares, prices, total=40000):
    return {"shares": dict(zip(M._OUT, shares)), "prices": {"home": prices[0], "draw": prices[1],
            "away": prices[2]}, "totalUsd": total}


class TestEvaluate:
    def test_geld_schaerfer_wird_erkannt(self):
        # je zur Hälfte einig/uneinig, damit derselbe Fall wie früher geprüft wird — nur mit
        # genug Zeilen für ein Urteil.
        frozen, res = {}, {}
        for i in range(M.URTEIL_MIN_N):
            if i % 2:
                frozen[f"A{i}"] = _frozen((0.6, 0.2, 0.2), (0.45, 0.30, 0.30)); res[f"A{i}"] = "home"
            else:
                frozen[f"B{i}"] = _frozen((0.2, 0.2, 0.6), (0.5, 0.25, 0.25)); res[f"B{i}"] = "away"
        r = M.evaluate(frozen, res)
        assert r["verdict"] == "geld_schaerfer"
        assert r["brierMoney"] < r["brierPrice"]
        assert r["disagree"]["moneyWon"] > 0

    def test_preis_besser_wenn_geld_daneben(self):
        frozen = {f"A{i}": _frozen((0.2, 0.2, 0.6), (0.6, 0.2, 0.2)) for i in range(M.URTEIL_MIN_N)}
        r = M.evaluate(frozen, {k: "home" for k in frozen})
        assert r["verdict"] == "preis_besser"

    def test_gleichauf_wenn_geld_gleich_preis(self):
        frozen = {f"M{i}": _frozen((0.5, 0.25, 0.25), (0.5, 0.25, 0.25)) for i in range(M.URTEIL_MIN_N)}
        r = M.evaluate(frozen, {k: "home" for k in frozen})
        assert r["verdict"] == "gleichauf"

    def test_unter_der_mindeststichprobe_gibt_es_gar_kein_urteil(self):
        """Der Kern des Wechsels: wenige Zeilen ergeben KEIN „gleichauf", sondern kein Urteil.
        „gleichauf" wäre eine Aussage — und die trägt eine Handvoll Spiele nicht."""
        frozen = {f"M{i}": _frozen((0.5, 0.25, 0.25), (0.5, 0.25, 0.25)) for i in range(3)}
        r = M.evaluate(frozen, {k: "home" for k in frozen})
        assert r["n"] == 3 and r["verdict"] == "zu wenig Daten"

    def test_trefferquoten(self):
        frozen = {"A": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2))}
        r = M.evaluate(frozen, {"A": "home"})
        assert r["moneyHitRate"] == 1.0 and r["priceHitRate"] == 1.0

    def test_nur_aufgeloeste_zaehlen(self):
        frozen = {"A": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2)),
                  "B": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2))}
        r = M.evaluate(frozen, {"A": "home"})   # B nicht aufgelöst
        assert r["n"] == 1

    def test_zwei_wege_markt_wird_nicht_mehr_gewertet(self):
        """02.09.2026, Vertragswechsel. Früher zählte ein Zwei-Wege-Markt normal mit. Gemessen an
        1.262 echten Märkten ist der Geld-Anteil dort aber rechnerisch der Preis (Abweichung
        Median 0,0pp) — Geld gegen Preis zu messen ist da keine Messung, sondern eine Tautologie,
        die das Gesamturteil Richtung „gleichauf" zieht. Er wird jetzt gezählt, aber nicht gewertet."""
        frozen = {"A": {"shares": {"home": 0.7, "away": 0.3}, "prices": {"home": 0.65, "away": 0.35}, "totalUsd": 40000}}
        r = M.evaluate(frozen, {"A": "home"})
        assert r["n"] == 0
        assert r["guete"]["preis_echo"] == 1

    def test_leer(self):
        assert M.evaluate({}, {})["verdict"] == "zu wenig Daten"


class TestResultsLookup:
    def test_home_draw_away(self):
        data = {"groups": {"L": {"fixtures": [
            {"home": "h1", "away": "a1", "result": {"status": "FT", "home_score": 2, "away_score": 0}},
            {"home": "h2", "away": "a2", "result": {"status": "FT", "home_score": 1, "away_score": 1}},
            {"home": "h3", "away": "a3", "result": {"status": "FT", "home_score": 0, "away_score": 3}}]}}}
        r = M.results_lookup(data)
        assert r["h1-a1"] == "home" and r["h2-a2"] == "draw" and r["h3-a3"] == "away"

    def test_ko_fixtures(self):
        data = {"koFixtures": [
            {"home": "h", "away": "a", "result": {"status": "AET", "home_score": 3, "away_score": 1}}]}
        assert M.results_lookup(data)["h-a"] == "home"

    def test_unaufgeloeste_raus(self):
        data = {"groups": {"L": {"fixtures": [
            {"home": "h", "away": "a", "result": {"status": "NS"}}]}}}
        assert M.results_lookup(data) == {}


# ── Befund 16 (25.08.2026): byLeague war per Konstruktion immer leer ─────────
# Der Producer (capture) schreibt kein `league`-Feld — er sieht die Liga gar nicht, weil
# smartmoney sie nicht mitliefert. Deshalb kommt sie jetzt beim AUSWERTEN aus den Fixtures
# dazu: das macht auch die bereits eingefrorene Historie rückwirkend nutzbar.

class TestLeaguesLookup:
    _DATA = {"groups": {
        "ENG": {"fixtures": [{"home": "42", "away": "1346"}]},
        "ESP": {"fixtures": [{"home": "542", "away": "546"}]},
        "A":   {"fixtures": [{"home": "MEX", "away": "ZAF"}]}}}

    def test_gruppenschluessel_ist_die_liga(self):
        assert M.leagues_lookup(self._DATA) == {
            "42-1346": "ENG", "542-546": "ESP", "MEX-ZAF": "A"}

    def test_wm_gruppen_sind_keine_ligen(self):
        """Ohne den valid-Filter würden bei der WM die Gruppen A–H als „Ligen" durchgehen.
        Ein falsches Label ist schlimmer als keines."""
        r = M.leagues_lookup(self._DATA, {"ENG", "ESP", "GER", "ITA", "FRA"})
        assert set(r.values()) == {"ENG", "ESP"}
        assert "MEX-ZAF" not in r

    def test_unvollstaendige_fixture_wird_uebersprungen(self):
        assert M.leagues_lookup({"groups": {"ENG": {"fixtures": [{"home": "42"}]}}}) == {}

    def test_leere_daten(self):
        assert M.leagues_lookup({}) == {}


# ── 02.09.2026: Vertragswechsel nach dem Lucas-Audit „Großes Geld" ────────────
# `evaluate` wertet seit heute NUR noch Märkte, deren Geld-Split etwas anderes sagen kann als
# der Preis (siehe split_guete): Zwei-Wege-Märkte sind rechnerisch der Preis, Drei-Wege-Märkte
# mit unter 70% Erfassung sind ein Artefakt. Dazu bekam das Urteil eine Mindest-Stichprobe
# (URTEIL_MIN_N global, URTEIL_MIN_N_LIGA je Liga), weil ein Brier-Vergleich auf n=2 ein
# Punktschätzer ist. Die Tests unten trugen den ALTEN Vertrag; sie sind hier migriert, nicht
# gelöscht — was sie prüfen, gilt weiter, nur mit einer tragfähigen Stichprobe.


class TestByLeagueBefuellt:
    @staticmethod
    def _frozen(n, key_prefix):
        # klar getrennte Verteilungen, damit Brier nicht zufällig gleich ist.
        # 02.09.2026: DREI Ausgänge statt zwei — ein Zwei-Wege-Markt ist seit dem Audit ein
        # Preis-Echo und wird nicht mehr gewertet, der Test prüfte dann eine leere Liste.
        # Anteile summieren sich auf 1 (die capture()-Konvention), also volle Abdeckung.
        return {f"{key_prefix}{i}": {"shares": {"home": 0.6, "draw": 0.15, "away": 0.25},
                                     "prices": {"home": 0.55, "draw": 0.2, "away": 0.25},
                                     "totalUsd": 40000}
                for i in range(n)}

    def test_liga_kommt_aus_dem_lookup_nicht_aus_der_datei(self):
        frozen = self._frozen(M.URTEIL_MIN_N_LIGA, "E")
        results = {k: "home" for k in frozen}
        leagues = {k: "ENG" for k in frozen}
        rep = M.evaluate(frozen, results, leagues=leagues)
        assert [r["league"] for r in rep["byLeague"]] == ["ENG"]
        assert rep["byLeague"][0]["n"] == M.URTEIL_MIN_N_LIGA

    def test_ohne_lookup_bleibt_byleague_leer(self):
        """Das war der Befund: der Aufrufer gab nie eine Liga mit → immer []."""
        frozen = self._frozen(M.URTEIL_MIN_N_LIGA, "E")
        rep = M.evaluate(frozen, {k: "home" for k in frozen})
        assert rep["byLeague"] == []

    def test_feld_in_der_datei_schlaegt_den_lookup(self):
        frozen = self._frozen(M.URTEIL_MIN_N_LIGA, "E")
        for v in frozen.values():
            v["league"] = "ESP"
        rep = M.evaluate(frozen, {k: "home" for k in frozen}, leagues={k: "ENG" for k in frozen})
        assert [r["league"] for r in rep["byLeague"]] == ["ESP"]


class TestSnapshotNichtUeberschreiben:
    """Der eingefrorene Schluss-Snapshot ist nicht rekonstruierbar — ein Lesefehler darf ihn
    nicht durch einen Teil-Stand ersetzen (dieselbe Familie wie Befund 01/02)."""

    def test_fehlend_ist_nicht_kaputt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "BASE", tmp_path)
        M._LOAD_FAILED.clear()
        assert M._load("gibtsnicht.json") == {}
        assert M._LOAD_FAILED == set()

    def test_kaputt_wird_gemerkt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "BASE", tmp_path)
        M._LOAD_FAILED.clear()
        (tmp_path / "kaputt.json").write_text("{nicht json", encoding="utf-8")
        assert M._load("kaputt.json") == {}
        assert "kaputt.json" in M._LOAD_FAILED

    def test_markierung_verschwindet_nach_erfolg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "BASE", tmp_path)
        M._LOAD_FAILED.clear()
        f = tmp_path / "x.json"
        f.write_text("{kaputt", encoding="utf-8")
        M._load("x.json")
        f.write_text('{"a": 1}', encoding="utf-8")
        assert M._load("x.json") == {"a": 1}
        assert M._LOAD_FAILED == set()
