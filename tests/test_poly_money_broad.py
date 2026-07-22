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


class TestGammaParser:
    """Die reinen Parser-Helfer (ohne Netz) — Gamma-Event → Ausgänge/Anpfiff."""

    def test_outcomes_zwei_wege(self):
        ev = {"markets": [{"outcomes": '["Lakers","Celtics"]',
                           "outcomePrices": '["0.62","0.38"]',
                           "clobTokenIds": '["t0","t1"]', "conditionId": "0xabc"}]}
        oc = B._outcomes(ev)
        assert [o["label"] for o in oc] == ["Lakers", "Celtics"]
        assert oc[0]["price"] == 0.62 and oc[0]["cond"] == "0xabc" and oc[0]["token"] == "t0"

    def test_outcomes_drei_wege(self):
        ev = {"markets": [{"outcomes": '["Home","Draw","Away"]',
                           "outcomePrices": '["0.5","0.3","0.2"]',
                           "clobTokenIds": '["a","b","c"]', "conditionId": "0x1"}]}
        assert len(B._outcomes(ev)) == 3

    def test_outcomes_kaputt_gibt_leer(self):
        assert B._outcomes({"markets": [{"outcomes": "nichtjson"}]}) == []
        assert B._outcomes({}) == []

    def test_hours_to_ko(self):
        from datetime import datetime, timedelta, timezone
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        ev = {"startTime": (now + timedelta(hours=2)).isoformat()}
        assert abs(B._hours_to_ko(ev, now) - 2.0) < 1e-6
        assert B._hours_to_ko({"startTime": "kaputt"}, now) is None


class TestFetchMarketsDedupUndDiagnose:
    """21.07.2026 (Lucas: „mehr Sport?"): ein Markt kann unter mehreren Tags liegen (cs2 ⊂ esports) —
    darf nur EINMAL zählen. rawByTag macht sichtbar, welche Sport-Tags überhaupt Events liefern."""

    def _ev(self):
        return {"slug": "cs2-navi-faze", "volume": 50000, "startTime": "2026-07-21T12:00:00Z",
                "markets": [{"outcomes": '["NAVI","FaZe"]', "outcomePrices": '["0.6","0.4"]',
                             "clobTokenIds": '["t0","t1"]', "conditionId": "0xabc"}]}

    def test_dedup_ueber_tags_und_rawbytag(self, monkeypatch):
        ev = self._ev()
        monkeypatch.setattr(B, "_tags", lambda: ["esports", "cs2"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: ([ev] if not closed else []))
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_money_shares", lambda oc: {"NAVI": 30000, "FaZe": 20000})
        markets = B.fetch_markets()
        # derselbe Markt unter zwei Tags → nur EINE offene Zeile
        assert sum(1 for m in markets if m["key"] == "cs2-navi-faze" and not m["resolved"]) == 1
        # Diagnose: beide Tags haben je 1 Roh-Event gesehen
        assert B.fetch_markets.raw_by_tag == {"esports": 1, "cs2": 1}

    def test_toter_tag_ist_null(self, monkeypatch):
        monkeypatch.setattr(B, "_tags", lambda: ["golf"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: [])
        assert B.fetch_markets() == []
        assert B.fetch_markets.raw_by_tag == {"golf": 0}

    def test_holders_budget_nach_volumen(self, monkeypatch):
        """Bei knappem Budget kriegt der VOLUMENSTÄRKSTE Markt den Geld-Split — egal welche Sportart
        (vorher fraßen die frühen Tags in Listen-Reihenfolge das Budget)."""
        def ev(slug, vol):
            return {"slug": slug, "volume": vol, "startTime": "2026-07-22T12:00:00Z",
                    "markets": [{"outcomes": '["A","B"]', "outcomePrices": '["0.6","0.4"]',
                                 "clobTokenIds": '["t0","t1"]', "conditionId": "0x" + slug}]}
        # mlb (früher Tag) klein, ufc (später Tag) GROSS
        gamma = {"mlb": [ev("mlb-small", 10000)], "ufc": [ev("ufc-big", 900000)]}
        monkeypatch.setattr(B, "_tags", lambda: ["mlb", "ufc"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: (gamma.get(tag, []) if not closed else []))
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_money_shares", lambda oc: {"A": 60, "B": 40})
        monkeypatch.setattr(B, "MAX_HOLDER_CALLS", 1)   # nur EIN Split möglich
        markets = B.fetch_markets()
        keys = [m["key"] for m in markets if not m["resolved"]]
        assert keys == ["ufc-big"], "der volumenstärkste Markt (UFC) muss den einen Split kriegen, nicht MLB"
