"""19.07.2026 — Liegt das Geld richtig, BREIT über alle Poly-Ligen (Lucas).

Zwei neue Stellschrauben gegenüber der Datensatz-Version:
  · Mindest-Quote-Filter (triviale Favoriten raus — „1.1 hat logo öfter recht").
  · Liga-Aufschlüsselung (wo hat die Masse mehr recht?).
Plus: Auflösung über Polys EIGENE Settlement (kein externer Ergebnis-Feed nötig).
"""
import poly_money_accuracy as PMA
import poly_money_broad as B


class TestMinOddsFilter:
    def _frozen(self):
        return {
            # Favorit-Preis 0.91 → Quote ~1.10 → trivial, muss bei min_odds 1.35 raus
            "trivial": {"shares": {"home": 0.9, "draw": 0.05, "away": 0.05},
                        "prices": {"home": 0.91, "draw": 0.05, "away": 0.04}, "totalUsd": 40000},
            # Favorit-Preis 0.55 → Quote ~1.82 → kompetitiv, bleibt
            "komp": {"shares": {"home": 0.55, "draw": 0.2, "away": 0.25},
                     "prices": {"home": 0.55, "draw": 0.25, "away": 0.20}, "totalUsd": 30000},
        }

    def test_trivialer_favorit_fliegt_raus(self):
        r = PMA.evaluate(self._frozen(), {"trivial": "home", "komp": "home"}, min_odds=1.35)
        assert r["n"] == 1, "1.1-Favorit muss bei min_odds 1.35 ausgeschlossen sein"

    def test_ohne_filter_zaehlt_alles(self):
        r = PMA.evaluate(self._frozen(), {"trivial": "home", "komp": "home"}, min_odds=1.0)
        assert r["n"] == 2

    def test_minodds_im_report(self):
        assert PMA.evaluate(self._frozen(), {"komp": "home"}, min_odds=1.35)["minOdds"] == 1.35


class TestByLeague:
    def _many(self, league, n, winner_side):
        return {f"{league}-{i}": {"shares": {"home": 0.6, "draw": 0.2, "away": 0.2},
                "prices": {"home": 0.5, "draw": 0.25, "away": 0.25}, "totalUsd": 30000,
                "league": league} for i in range(n)}

    def test_liga_breakdown_ab_5(self):
        frozen = self._many("NBA", 6, "home")
        r = PMA.evaluate(frozen, {k: "home" for k in frozen}, min_odds=1.2)
        nba = [l for l in r["byLeague"] if l["league"] == "NBA"]
        assert nba and nba[0]["n"] == 6

    def test_zu_duenne_liga_kein_urteil(self):
        frozen = self._many("NHL", 3, "home")   # < 5
        r = PMA.evaluate(frozen, {k: "home" for k in frozen}, min_odds=1.2)
        assert all(l["league"] != "NHL" for l in r["byLeague"])

    def test_sortiert_wo_geld_am_meisten_schlaegt(self):
        # Liga A: Geld trifft (schärfer); Liga B: Geld daneben
        fa = {f"A-{i}": {"shares": {"home": 0.7, "draw": 0.15, "away": 0.15},
              "prices": {"home": 0.5, "draw": 0.25, "away": 0.25}, "totalUsd": 30000, "league": "A"} for i in range(6)}
        fb = {f"B-{i}": {"shares": {"home": 0.2, "draw": 0.2, "away": 0.6},
              "prices": {"home": 0.5, "draw": 0.25, "away": 0.25}, "totalUsd": 30000, "league": "B"} for i in range(6)}
        frozen = {**fa, **fb}
        res = {**{k: "home" for k in fa}, **{k: "home" for k in fb}}
        r = PMA.evaluate(frozen, res, min_odds=1.2)
        assert r["byLeague"][0]["league"] == "A", "Liga, wo Geld den Preis am meisten schlägt, zuerst"


class TestPolyResolution:
    def test_gewinner_aus_settlement(self):
        assert B.winner_from_prices({"home": 1.0, "away": 0.0}) == "home"
        assert B.winner_from_prices({"home": 0.0, "draw": 0.0, "away": 1.0}) == "away"

    def test_noch_nicht_aufgeloest(self):
        assert B.winner_from_prices({"home": 0.6, "away": 0.4}) is None

    def test_resolutions_nur_settled(self):
        markets = [
            {"key": "a", "resolved": True, "resolvedPrices": {"home": 1.0, "away": 0.0}},
            {"key": "b", "resolved": False, "resolvedPrices": {"home": 0.6, "away": 0.4}},
        ]
        assert B.resolutions(markets) == {"a": "home"}


class TestCaptureBroad:
    def test_volumen_und_fenster(self):
        m = [{"key": "x", "league": "NBA", "hoursToKickoff": 1.0, "totalUsd": 20000,
              "shares": {"home": 0.6, "away": 0.4}, "prices": {"home": 0.5, "away": 0.5}}]
        assert "x" in B.capture(m, {}, min_vol=7500)
        # zu dünn
        m2 = [dict(m[0], key="y", totalUsd=1000)]
        assert B.capture(m2, {}, min_vol=7500) == {}
        # außerhalb Fenster
        m3 = [dict(m[0], key="z", hoursToKickoff=10)]
        assert B.capture(m3, {}, min_vol=7500) == {}

    def test_league_tag_bleibt(self):
        m = [{"key": "x", "league": "EPL", "hoursToKickoff": 1.0, "totalUsd": 20000,
              "shares": {"home": 0.6, "away": 0.4}, "prices": {"home": 0.5, "away": 0.5}}]
        assert B.capture(m, {})["x"]["league"] == "EPL"
