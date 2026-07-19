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
        frozen = {
            "A": _frozen((0.6, 0.2, 0.2), (0.45, 0.30, 0.30)),   # Geld Heim, Preis Heim knapp
            "B": _frozen((0.2, 0.2, 0.6), (0.5, 0.25, 0.25)),    # Geld Auswärts, Preis Heim → uneinig
        }
        r = M.evaluate(frozen, {"A": "home", "B": "away"})
        assert r["verdict"] == "geld_schaerfer"
        assert r["brierMoney"] < r["brierPrice"]
        assert r["disagree"]["moneyWon"] == 1

    def test_preis_besser_wenn_geld_daneben(self):
        frozen = {
            "A": _frozen((0.2, 0.2, 0.6), (0.6, 0.2, 0.2)),   # Geld Auswärts, Heim gewinnt
            "B": _frozen((0.2, 0.2, 0.6), (0.6, 0.2, 0.2)),
        }
        r = M.evaluate(frozen, {"A": "home", "B": "home"})
        assert r["verdict"] == "preis_besser"

    def test_gleichauf_wenn_geld_gleich_preis(self):
        frozen = {f"M{i}": _frozen((0.5, 0.25, 0.25), (0.5, 0.25, 0.25)) for i in range(4)}
        r = M.evaluate(frozen, {f"M{i}": "home" for i in range(4)})
        assert r["verdict"] == "gleichauf"

    def test_trefferquoten(self):
        frozen = {"A": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2))}
        r = M.evaluate(frozen, {"A": "home"})
        assert r["moneyHitRate"] == 1.0 and r["priceHitRate"] == 1.0

    def test_nur_aufgeloeste_zaehlen(self):
        frozen = {"A": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2)),
                  "B": _frozen((0.6, 0.2, 0.2), (0.6, 0.2, 0.2))}
        r = M.evaluate(frozen, {"A": "home"})   # B nicht aufgelöst
        assert r["n"] == 1

    def test_zwei_wege_ohne_remis(self):
        """US-Sport-Stil: kein Draw. Fehlende Seite = 0, Normalisierung trägt das."""
        frozen = {"A": {"shares": {"home": 0.7, "away": 0.3}, "prices": {"home": 0.65, "away": 0.35}, "totalUsd": 40000}}
        r = M.evaluate(frozen, {"A": "home"})
        assert r["n"] == 1 and r["moneyHitRate"] == 1.0

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
