"""19.07.2026 — Liegt das Geld richtig, BREIT über alle Poly-Ligen (Lucas).

Zwei neue Stellschrauben gegenüber der Datensatz-Version:
  · Mindest-Quote-Filter (triviale Favoriten raus — „1.1 hat logo öfter recht").
  · Liga-Aufschlüsselung (wo hat die Masse mehr recht?).
Plus: Auflösung über Polys EIGENE Settlement (kein externer Ergebnis-Feed nötig).
"""
import poly_money_accuracy as PMA
import poly_money_broad as B


class TestSportTags:
    """23.07.2026 (Lucas: „bei ‚Liegt das Geld richtig' fehlt MLS"). MLS war nicht in SPORT_TAGS →
    wurde nie von Gamma geholt, obwohl es die aktive Fußball-Liga mit Poly-Liquidität ist. Regression-
    Guard: die in-season Kern-Ligen MÜSSEN im Fetch-Umfang bleiben, sonst fällt eine wieder still raus."""

    def test_mls_und_kern_ligen_im_fetch_umfang(self):
        assert "mls" in B.SPORT_TAGS, "MLS fehlt → aktive Fußball-Liga wird nicht geholt"
        for t in ("mlb", "nba", "esports", "ucl", "epl"):
            assert t in B.SPORT_TAGS, f"Kern-Tag {t} fehlt"


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

    def test_wale_werden_getragen(self):
        # 25.07.2026 (Lucas): Einzel-Wale je Markt müssen in den Frozen-Eintrag (c).
        m = [{"key": "x", "league": "MLB", "hoursToKickoff": 1.0, "totalUsd": 20000,
              "shares": {"A": 0.6, "B": 0.4}, "prices": {"A": 0.5, "B": 0.5},
              "whales": [{"wallet": "0xabc", "side": "A", "usd": 5000}]}]
        assert B.capture(m, {})["x"]["whales"][0]["wallet"] == "0xabc"


class TestAppendHistory:
    # 25.07.2026 (Lucas ① Momentum): globale Poly-Preis-Zeitreihe je Markt fortschreiben.
    from datetime import datetime, timezone, timedelta
    T0 = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def _m(self, key="x", vol=20000, prices=None, resolved=False):
        return {"key": key, "league": "MLB", "hoursToKickoff": 2.0, "totalUsd": vol,
                "prices": prices or {"A": 0.55, "B": 0.45}, "resolved": resolved}

    def test_haengt_punkt_an(self):
        h = B.append_history({}, [self._m()], now=self.T0)
        assert h["x"][0]["p"] == {"A": 0.55, "B": 0.45} and h["x"][0]["v"] == 20000

    def test_fortschreiben_akkumuliert(self):
        h = B.append_history({}, [self._m(prices={"A": 0.55, "B": 0.45})], now=self.T0)
        h = B.append_history(h, [self._m(prices={"A": 0.60, "B": 0.40})],
                             now=self.T0 + self.timedelta(minutes=30))
        assert len(h["x"]) == 2 and h["x"][-1]["p"]["A"] == 0.60   # Bewegung sichtbar

    def test_deckelt_auf_max_points(self):
        h = {}
        for i in range(60):
            h = B.append_history(h, [self._m()], now=self.T0 + self.timedelta(minutes=i),
                                 max_points=48)
        assert len(h["x"]) == 48

    def test_prunt_stale_und_skippt_resolved_und_duenn(self):
        h = B.append_history({}, [self._m(key="alt")], now=self.T0)
        # 'alt' nicht mehr gesehen + weit in der Zukunft → fällt raus; neuer 'x' bleibt
        h = B.append_history(h, [self._m(key="x")], now=self.T0 + self.timedelta(hours=200))
        assert "x" in h and "alt" not in h
        # resolved + zu dünn werden nie erfasst
        h2 = B.append_history({}, [self._m(key="r", resolved=True), self._m(key="d", vol=100)],
                              now=self.T0)
        assert h2 == {}


class TestWalletTrack:
    # 25.07.2026 (Lucas ②): je Whale Einstieg merken, bei Auflösung CLV + Treffer werten.
    from datetime import datetime, timezone, timedelta
    T0 = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def _up(self, price, key="mlb-a-b", side="A", wallet="0xW", usd=5000):
        return {"key": key, "league": "MLB", "resolved": False, "hoursToKickoff": 2.0,
                "prices": {side: price, "B": round(1 - price, 4)},
                "whales": [{"wallet": wallet, "side": side, "usd": usd}]}

    def _resolved(self, winner="A", key="mlb-a-b"):
        return {"key": key, "resolved": True,
                "resolvedPrices": {winner: 1.0, ("B" if winner == "A" else "A"): 0.0}}

    def test_einstieg_gemerkt(self):
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        e = t["open"]["0xW|mlb-a-b|A"]
        assert e["firstPrice"] == 0.40 and e["lastPrice"] == 0.40

    def test_clv_und_treffer_bei_aufloesung(self):
        # Einstieg 0.40 → zog auf 0.50 (Linie geschlagen) → Seite A gewinnt
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        t = B.update_wallet_track(t, [self._up(0.50)], now=self.T0 + self.timedelta(hours=1))
        t = B.update_wallet_track(t, [self._resolved("A")], now=self.T0 + self.timedelta(hours=3))
        s = t["scores"]["0xW"]
        assert s["n"] == 1 and abs(s["clvSumPP"] - 10.0) < 0.01 and s["wins"] == 1
        assert "0xW|mlb-a-b|A" not in t["open"]   # gewertete Position ist geschlossen

    def test_verlierer_zaehlt_treffer_nicht(self):
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        t = B.update_wallet_track(t, [self._resolved("B")], now=self.T0 + self.timedelta(hours=2))
        s = t["scores"]["0xW"]
        assert s["n"] == 1 and s["wins"] == 0

    def test_prunt_verwaiste_offene_position(self):
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        # Markt taucht 200h später nirgends mehr auf (nie aufgelöst gesehen) → raus
        t = B.update_wallet_track(t, [self._up(0.55, key="other")],
                                  now=self.T0 + self.timedelta(hours=200))
        assert "0xW|mlb-a-b|A" not in t["open"]


class TestSharpAlert:
    # 25.07.2026 (Lucas 🔔): NEUE Einstiege bewiesen-scharfer Wallets erkennen (prev-vs-cur).
    SCORES = {"0xSHARP": {"n": 6, "clvSumPP": 18.0, "wins": 4},   # Ø CLV +3.0 → scharf
              "0xDUMB": {"n": 6, "clvSumPP": -12.0, "wins": 1},   # negativer CLV → nicht
              "0xTHIN": {"n": 2, "clvSumPP": 6.0, "wins": 2}}     # zu dünn (n<4)
    def _cur(self, *wallets):
        openp = {f"{w}|k{i}|A": {"wallet": w, "key": f"k{i}", "side": "A", "league": "MLB",
                                 "firstPrice": 0.42, "usd": 8000} for i, w in enumerate(wallets)}
        return {"open": openp, "scores": self.SCORES}

    def test_neuer_scharfer_einstieg_wird_erkannt(self):
        prev = {"open": {}, "scores": self.SCORES}
        e = B.sharp_entries(prev, self._cur("0xSHARP"))
        assert len(e) == 1 and e[0]["wallet"] == "0xSHARP" and e[0]["avgClv"] == 3.0

    def test_bestehende_position_ist_nicht_neu(self):
        cur = self._cur("0xSHARP")
        assert B.sharp_entries(cur, cur) == []   # gleicher open-Satz → nichts neu

    def test_dummes_und_duennes_geld_alarmiert_nicht(self):
        prev = {"open": {}, "scores": self.SCORES}
        assert B.sharp_entries(prev, self._cur("0xDUMB", "0xTHIN")) == []

    def test_format_enthaelt_track_record(self):
        prev = {"open": {}, "scores": self.SCORES}
        msg = B._format_sharp_alert(B.sharp_entries(prev, self._cur("0xSHARP")))
        assert "Sharp im Markt" in msg and "+3.0pp" in msg and "n6" in msg


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
        monkeypatch.setattr(B, "_gamma_top", lambda closed: [])
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"NAVI": 30000, "FaZe": 20000}, "whales": []})
        markets = B.fetch_markets()
        # derselbe Markt unter zwei Tags → nur EINE offene Zeile
        assert sum(1 for m in markets if m["key"] == "cs2-navi-faze" and not m["resolved"]) == 1
        # Diagnose: beide Tags haben je 1 Roh-Event gesehen
        assert B.fetch_markets.raw_by_tag == {"esports": 1, "cs2": 1}

    def test_toter_tag_ist_null(self, monkeypatch):
        monkeypatch.setattr(B, "_tags", lambda: ["golf"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: [])
        monkeypatch.setattr(B, "_gamma_top", lambda closed: [])
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
        monkeypatch.setattr(B, "_gamma_top", lambda closed: [])
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"A": 60, "B": 40}, "whales": []})
        monkeypatch.setattr(B, "MAX_HOLDER_CALLS", 1)   # nur EIN Split möglich
        markets = B.fetch_markets()
        keys = [m["key"] for m in markets if not m["resolved"]]
        assert keys == ["ufc-big"], "der volumenstärkste Markt (UFC) muss den einen Split kriegen, nicht MLB"


class TestVolumeSweep:
    """23.07.2026 (Lucas: „alles nehmen wo Volumen drauf ist, egal welche Sportart"). Der tag-lose
    Volumen-Sweep fängt Ligen ein, die KEIN kuratierter Tag abdeckt — ohne Nicht-Sport (Politik/
    Krypto) reinzulassen (die haben keinen unmittelbaren Anpfiff → htk-Fenster wirft sie raus)."""

    def _ev(self, slug, vol=50000):
        return {"slug": slug, "volume": vol, "startTime": "2026-07-23T12:00:00Z",
                "markets": [{"outcomes": '["A","B"]', "outcomePrices": '["0.6","0.4"]',
                             "clobTokenIds": '["t0","t1"]', "conditionId": "0x" + slug}]}

    def test_league_from_slug(self):
        assert B._league_from_slug("mls-phi-nyr-2026-07-22") == "MLS"
        assert B._league_from_slug("ucl-psg-rma") == "UCL"
        assert B._league_from_slug("rugby-abc-def") == "RUGBY"
        assert B._league_from_slug("12345") == "OTHER"

    def test_sweep_findet_liga_ohne_tag(self, monkeypatch):
        # KEIN Tag deckt „rugby" ab, aber der Volumen-Sweep liefert es → landet mit Liga=RUGBY.
        monkeypatch.setattr(B, "_tags", lambda: ["mlb"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: [])
        monkeypatch.setattr(B, "_gamma_top",
                            lambda closed: ([self._ev("rugby-lei-sar")] if not closed else []))
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"A": 60, "B": 40}, "whales": []})
        markets = B.fetch_markets()
        rugby = [m for m in markets if m["key"] == "rugby-lei-sar"]
        assert rugby and rugby[0]["league"] == "RUGBY"
        assert B.fetch_markets.sweep_stats["sweepAdded"] == 1

    def test_sweep_dedupt_gegen_tags(self, monkeypatch):
        # Derselbe Markt aus Tag UND Sweep → nur EINE Zeile (seen-Dedup).
        ev = self._ev("mlb-nyy-bos")
        monkeypatch.setattr(B, "_tags", lambda: ["mlb"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: ([ev] if not closed else []))
        monkeypatch.setattr(B, "_gamma_top", lambda closed: ([ev] if not closed else []))
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"A": 60, "B": 40}, "whales": []})
        markets = B.fetch_markets()
        assert sum(1 for m in markets if m["key"] == "mlb-nyy-bos" and not m["resolved"]) == 1

    def test_sweep_wirft_nicht_sport_raus_ueber_anpfiff_fenster(self, monkeypatch):
        # Politik-Markt: Volumen ja, aber Start liegt in der Vergangenheit → htk<0 → NICHT drin.
        pol = self._ev("us-election-winner", vol=999999)
        monkeypatch.setattr(B, "_tags", lambda: [])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: [])
        monkeypatch.setattr(B, "_gamma_top", lambda closed: ([pol] if not closed else []))
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: -240.0)   # Start 10 Tage her
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"A": 60, "B": 40}, "whales": []})
        markets = B.fetch_markets()
        assert not any(m["key"] == "us-election-winner" for m in markets)
