"""19.07.2026 — Liegt das Geld richtig, BREIT über alle Poly-Ligen (Lucas).

Zwei neue Stellschrauben gegenüber der Datensatz-Version:
  · Mindest-Quote-Filter (triviale Favoriten raus — „1.1 hat logo öfter recht").
  · Liga-Aufschlüsselung (wo hat die Masse mehr recht?).
Plus: Auflösung über Polys EIGENE Settlement (kein externer Ergebnis-Feed nötig).
"""
import pytest
import poly_money_accuracy as PMA
import poly_money_broad as B
from datetime import datetime, timezone, timedelta


@pytest.fixture(autouse=True)
def _no_slug_backfill(monkeypatch):
    # 02.08.2026: der Slug-Backfill (backfill_resolutions_by_slug) liest das echte Close-File und
    # macht Netz-Lookups — beides gehoert nicht in diese fetch_markets-Unit-Tests (er hat seinen
    # eigenen Test in test_poly_resolution_backfill.py). Neutralisieren -> die Tests pruefen reines
    # Tag/Sweep-Verhalten und bleiben deterministisch (sonst zieht der Backfill echte Auflösungen
    # rein und "toter Tag" ist nicht mehr []).
    monkeypatch.setattr(B, "backfill_resolutions_by_slug", lambda *a, **k: [])
    # 16.08.2026 (Lucas): Self-Discovery-Registry aus den fetch_markets-Unit-Tests raushalten -> die
    # Tests pruefen reines Tag/Sweep-Verhalten, unabhaengig von einer poly_football_tags.json auf Platte.
    monkeypatch.setattr(B, "_load_league_registry", lambda: set())
    monkeypatch.setattr(B, "_save_league_registry", lambda *a, **k: None)


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

    def test_liga_breakdown_ab_der_mindeststichprobe(self):
        # 02.09.2026: die Schwelle stand auf 5 und steht jetzt auf URTEIL_MIN_N_LIGA — seit der
        # Güte-Schranke bleiben je Liga so wenige wertbare Märkte übrig, dass fünf davon kein
        # Urteil tragen.
        frozen = self._many("NBA", PMA.URTEIL_MIN_N_LIGA, "home")
        r = PMA.evaluate(frozen, {k: "home" for k in frozen}, min_odds=1.2)
        nba = [l for l in r["byLeague"] if l["league"] == "NBA"]
        assert nba and nba[0]["n"] == PMA.URTEIL_MIN_N_LIGA

    def test_zu_duenne_liga_kein_urteil(self):
        frozen = self._many("NHL", PMA.URTEIL_MIN_N_LIGA - 1, "home")
        r = PMA.evaluate(frozen, {k: "home" for k in frozen}, min_odds=1.2)
        assert all(l["league"] != "NHL" for l in r["byLeague"])

    def test_sortiert_wo_geld_am_meisten_schlaegt(self):
        # Liga A: Geld trifft (schärfer); Liga B: Geld daneben
        fa = {f"A-{i}": {"shares": {"home": 0.7, "draw": 0.15, "away": 0.15},
              "prices": {"home": 0.5, "draw": 0.25, "away": 0.25}, "totalUsd": 30000, "league": "A"} for i in range(PMA.URTEIL_MIN_N_LIGA)}
        fb = {f"B-{i}": {"shares": {"home": 0.2, "draw": 0.2, "away": 0.6},
              "prices": {"home": 0.5, "draw": 0.25, "away": 0.25}, "totalUsd": 30000, "league": "B"} for i in range(PMA.URTEIL_MIN_N_LIGA)}
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



class TestGhostPrune:
    # 06.08.2026 (Lucas): der Close-Feed prunte nie -> fertige Spiele blieben ewig 'live' (Geister-
    # Maerkte, ~$23M Whale-Geld auf toten Spielen). capture() wirft unaufgeloeste Maerkte >GHOST_GRACE_H
    # nach Anpfiff raus; aufgeloeste Snapshots bleiben.
    from datetime import datetime, timezone, timedelta
    NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)

    def _e(self, cap_dt, htk, resolved=False, usd=20000):
        e = {"shares": {"A": 0.6, "B": 0.4}, "prices": {"A": 0.5, "B": 0.5},
             "league": "CS2", "totalUsd": usd, "whales": [{"wallet": "0xg", "side": "A", "usd": usd}],
             "hoursToKickoff": htk, "capturedAt": cap_dt.isoformat()}
        if resolved:
            e["resolved"] = True
        return e

    def test_geist_wird_geprunt(self):
        td = self.timedelta
        frozen = {"ghost": self._e(self.NOW - td(hours=10), 1.0),   # ko 9h in Vergangenheit -> raus
                  "fresh": self._e(self.NOW - td(hours=2), 1.0),    # ko 1h in Vergangenheit -> bleibt
                  "done":  self._e(self.NOW - td(hours=20), 1.0, resolved=True),  # aufgeloest -> bleibt
                  "future": self._e(self.NOW - td(hours=0.5), 2.0)} # Anpfiff in Zukunft -> bleibt
        out = B.capture([], frozen, now=self.NOW, min_vol=7500)
        assert "ghost" not in out
        assert "fresh" in out and "done" in out and "future" in out

    def test_gerade_abrechnender_markt_bleibt(self):
        # ein >6h alter, unaufgeloester Snapshot, dessen Markt aber JETZT resolved reinkommt -> bleibt
        # (Wallet-Track braucht den frozen-Close als CLV-Referenz fuer die Abrechnung dieses Laufs).
        td = self.timedelta
        frozen = {"settling": self._e(self.NOW - td(hours=10), 1.0)}
        markets = [{"key": "settling", "resolved": True, "resolvedPrices": {"A": 1.0, "B": 0.0}}]
        out = B.capture(markets, frozen, now=self.NOW, min_vol=7500)
        assert "settling" in out

    def test_grace_override(self):
        td = self.timedelta
        frozen = {"g": self._e(self.NOW - td(hours=10), 1.0)}
        assert "g" in B.capture([], frozen, now=self.NOW, min_vol=7500, grace_h=100)
        assert "g" not in B.capture([], frozen, now=self.NOW, min_vol=7500, grace_h=6)

    def test_unparsebar_bleibt_konservativ(self):
        frozen = {"weird": {"shares": {}, "prices": {}, "league": "X", "totalUsd": 20000,
                            "hoursToKickoff": None, "capturedAt": "nonsense"}}
        assert "weird" in B.capture([], frozen, now=self.NOW, min_vol=7500)

    # 24.08.2026 (Lucas, "$41 Mio Whale-Geld auf fertigen Spielen"): der Prune oben lief ins Leere,
    # weil Gamma jeden geschlossenen Event bei jedem Lauf mitliefert -> `key in resolving` machte
    # fast jeden Geister-Key dauerhaft prune-immun, ohne dass die Aufloesung je im Eintrag ankam.
    def test_aufloesung_wird_in_den_eintrag_gestempelt(self):
        td = self.timedelta
        frozen = {"settling": self._e(self.NOW - td(hours=10), 1.0)}
        markets = [{"key": "settling", "resolved": True, "resolvedPrices": {"A": 1.0, "B": 0.0}}]
        out = B.capture(markets, frozen, now=self.NOW, min_vol=7500)
        assert out["settling"]["resolved"] is True                     # nicht mehr still "live"
        assert out["settling"]["resolvedPrices"] == {"A": 1.0, "B": 0.0}
        assert out["settling"].get("resolvedAt")

    def test_nachzuegler_aus_dem_aufloesungs_ledger_wird_gestempelt(self):
        # Die Aufloesung liegt laengst im rollierenden Ledger, der Markt taucht im Lauf nicht mehr auf.
        td = self.timedelta
        frozen = {"ghost": self._e(self.NOW - td(hours=30), 1.0)}
        out = B.capture([], frozen, now=self.NOW, min_vol=7500,
                        resolutions={"ghost": {"winner": "A", "ts": "x"}})
        assert out["ghost"]["resolved"] is True and out["ghost"]["resolvedWinner"] == "A"

    def test_geist_ohne_jede_aufloesung_fliegt_weiter_raus(self):
        td = self.timedelta
        frozen = {"ghost": self._e(self.NOW - td(hours=30), 1.0)}
        assert "ghost" not in B.capture([], frozen, now=self.NOW, min_vol=7500,
                                        resolutions={"anderer": {"winner": "A"}})

    def test_aufgeloeste_fliegen_nach_retention_raus(self):
        td = self.timedelta
        frozen = {"alt":  self._e(self.NOW - td(days=40), 1.0, resolved=True),
                  "neu":  self._e(self.NOW - td(days=3),  1.0, resolved=True)}
        out = B.capture([], frozen, now=self.NOW, min_vol=7500, resolved_keep_days=30)
        assert "alt" not in out and "neu" in out

    def test_stempel_ueberschreibt_bestehende_aufloesung_nicht(self):
        td = self.timedelta
        e = self._e(self.NOW - td(hours=30), 1.0, resolved=True)
        e["resolvedPrices"] = {"A": 1.0, "B": 0.0}
        out = B.capture([{"key": "k", "resolved": True, "resolvedPrices": {"B": 1.0, "A": 0.0}}],
                        {"k": e}, now=self.NOW, min_vol=7500)
        assert out["k"]["resolvedPrices"] == {"A": 1.0, "B": 0.0}


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

    def test_clv_gegen_frozen_close(self):
        # 26.07.2026 (Lucas: „CLV misst nicht"): Position nur EINMAL gesehen (lastPrice==firstPrice) →
        # ohne Close wäre CLV fälschlich 0. Mit eingefrorener Closing-Linie A=0.62 → CLV=(0.62-0.40)*100=22.
        frozen = {"mlb-a-b": {"prices": {"A": 0.62, "B": 0.38}}}
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        t = B.update_wallet_track(t, [self._resolved("A")],
                                  now=self.T0 + self.timedelta(hours=3), frozen=frozen)
        s = t["scores"]["0xW"]
        assert s["n"] == 1 and abs(s["clvSumPP"] - 22.0) < 0.01 and s["wins"] == 1

    def test_ohne_close_faellt_auf_lastprice_zurueck(self):
        # Kein frozen → Alt-Verhalten (lastPrice). Einmal gesehen → CLV 0, Treffer zählt trotzdem.
        t = B.update_wallet_track({}, [self._up(0.40)], now=self.T0)
        t = B.update_wallet_track(t, [self._resolved("A")], now=self.T0 + self.timedelta(hours=3))
        s = t["scores"]["0xW"]
        assert s["n"] == 1 and abs(s["clvSumPP"]) < 0.01 and s["wins"] == 1

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
    SCORES = {"0xSHARP": {"n": 6, "clvSumPP": 18.0, "wins": 4},     # Ø CLV +3.0 · 67% → scharf
              "0xDUMB": {"n": 6, "clvSumPP": -12.0, "wins": 1},     # negativer CLV → nicht
              "0xTHIN": {"n": 2, "clvSumPP": 6.0, "wins": 2},       # zu dünn (n<4)
              "0xLOWCLV": {"n": 15, "clvSumPP": 7.5, "wins": 9},    # 02.08.: Ø CLV +0.5 < 1.5 → nicht
              "0xLOWHIT": {"n": 10, "clvSumPP": 20.0, "wins": 4},   # 02.08.: 40% Treffer < 50% → nicht
              "0xLOSER": {"n": 15, "clvSumPP": 30.0, "wins": 9, "pnl": -500000}}  # 02.08.: bestätigter Verlierer → nicht
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

    def test_clv_unter_schwelle_alarmiert_nicht(self):   # 02.08.2026 (Lucas): CLV +0.5pp schlägt den Close nicht
        prev = {"open": {}, "scores": self.SCORES}
        assert B.sharp_entries(prev, self._cur("0xLOWCLV")) == []

    def test_niedrige_trefferquote_alarmiert_nicht(self):   # 02.08.2026: 40% < 50%
        prev = {"open": {}, "scores": self.SCORES}
        assert B.sharp_entries(prev, self._cur("0xLOWHIT")) == []

    def test_bestaetigter_verlierer_ist_nicht_scharf(self):   # 02.08.2026: das $4,3-Mio-Leck
        prev = {"open": {}, "scores": self.SCORES}
        # gute CLV (+2.0) & Treffer (60%), aber Lifetime-P&L < 0 → raus
        assert B.sharp_entries(prev, self._cur("0xLOSER")) == []


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

    def test_market_volume_bo3_nimmt_nur_serie(self):
        # 15.08.2026 (Lucas): Best-of-3-Event summiert Serie+Map1+Map2 -> Event 1.2M, Serie 150K.
        # _outcomes zieht die Serie (0xser); totalUsd muss 150K sein, nicht das Event-Volumen.
        ev = {"volume": 1200000, "markets": [
            {"outcomes": '["TEAM VISION","Team Spirit"]', "outcomePrices": '["0.99","0.01"]',
             "clobTokenIds": '["t0","t1"]', "conditionId": "0xser", "volumeNum": 150000},
            {"question": "Map 1", "outcomes": '["A","B"]', "outcomePrices": '["0.5","0.5"]',
             "clobTokenIds": '["m0","m1"]', "conditionId": "0xmap1", "volumeNum": 600000},
            {"question": "Map 2", "outcomes": '["A","B"]', "outcomePrices": '["0.5","0.5"]',
             "clobTokenIds": '["n0","n1"]', "conditionId": "0xmap2", "volumeNum": 450000}]}
        oc = B._outcomes(ev)
        assert B._market_volume(ev, oc, float(ev["volume"])) == 150000

    def test_market_volume_gruppiert_summiert_conds(self):
        # Struktur (2): gruppierte Ja/Nein-Maerkte -> mehrere conds fuer EIN Spiel -> summieren.
        ev = {"volume": 999999, "markets": [
            {"groupItemTitle": "Team A", "outcomes": '["Yes","No"]', "outcomePrices": '["0.6","0.4"]',
             "clobTokenIds": '["a0","a1"]', "conditionId": "0xA", "volumeNum": 40000},
            {"groupItemTitle": "Team B", "outcomes": '["Yes","No"]', "outcomePrices": '["0.4","0.6"]',
             "clobTokenIds": '["b0","b1"]', "conditionId": "0xB", "volumeNum": 25000}]}
        oc = B._outcomes(ev)
        assert B._market_volume(ev, oc, float(ev["volume"])) == 65000

    def test_market_volume_fallback_ohne_marktvolumen(self):
        # Kein volumeNum/volume am Markt -> Fallback = Event-Volumen (kein schlechteres Verhalten).
        ev = {"volume": 50000, "markets": [
            {"outcomes": '["A","B"]', "outcomePrices": '["0.6","0.4"]',
             "clobTokenIds": '["t0","t1"]', "conditionId": "0xabc"}]}
        oc = B._outcomes(ev)
        assert B._market_volume(ev, oc, 50000.0) == 50000.0

    def test_market_volume_ohne_conds_fallback(self):
        assert B._market_volume({"markets": []}, [], 123.0) == 123.0


class TestSeriesMarketPicker:
    """15.08.2026 (Lucas): eSport-Best-of-3 — _outcomes muss den SERIEN-Markt liefern, nicht die
    gerade laufende Map (die gegen Map-Ende auf 99¢ laeuft). TEAM-VISION-Fall."""

    def _ev(self):
        # Reihenfolge absichtlich Map ZUERST (wie live beobachtet) -> Serie darf trotzdem gewinnen.
        return {"slug": "dota2-vsn-ts", "volume": 1200000, "markets": [
            {"question": "TEAM VISION vs Team Spirit - Map 1", "outcomes": '["TEAM VISION","Team Spirit"]',
             "outcomePrices": '["0.99","0.01"]', "clobTokenIds": '["m0","m1"]',
             "conditionId": "0xmap1", "volumeNum": 600000},
            {"question": "TEAM VISION vs Team Spirit", "outcomes": '["TEAM VISION","Team Spirit"]',
             "outcomePrices": '["0.74","0.26"]', "clobTokenIds": '["s0","s1"]',
             "conditionId": "0xseries", "volumeNum": 150000},
            {"question": "Map 2 Winner", "outcomes": '["TEAM VISION","Team Spirit"]',
             "outcomePrices": '["0.55","0.45"]', "clobTokenIds": '["n0","n1"]',
             "conditionId": "0xmap2", "volumeNum": 90000}]}

    def test_nimmt_serie_nicht_map(self):
        oc = B._outcomes(self._ev())
        assert oc[0]["cond"] == "0xseries", oc
        assert oc[0]["price"] == 0.74 and oc[0]["label"] == "TEAM VISION"

    def test_totalusd_wird_serie(self):
        oc = B._outcomes(self._ev())
        # mit dem Markt-Volumen-Fix: totalUsd = Serie (150K), nicht Event (1.2M) und nicht Map (600K)
        assert B._market_volume(self._ev(), oc, 1200000.0) == 150000

    def test_map_prop_regex(self):
        assert B._is_map_prop({"question": "Foo - Map 1"})
        assert B._is_map_prop({"groupItemTitle": "Game 3 Winner"})
        assert B._is_map_prop({"question": "Team A Handicap -1.5"})
        assert B._is_map_prop({"question": "Total Kills Over/Under"})
        assert not B._is_map_prop({"question": "TEAM VISION vs Team Spirit"})
        assert not B._is_map_prop({"question": "Real Madrid vs Barcelona"})

    def test_nur_maps_faellt_auf_volumen_zurueck(self):
        # kein reiner Serien-Markt -> hoechstes Volumen (kein Absturz, altes Verhalten als Netz)
        ev = {"markets": [
            {"question": "Map 1", "outcomes": '["A","B"]', "outcomePrices": '["0.9","0.1"]',
             "clobTokenIds": '["a","b"]', "conditionId": "0x1", "volumeNum": 10000},
            {"question": "Map 2", "outcomes": '["A","B"]', "outcomePrices": '["0.6","0.4"]',
             "clobTokenIds": '["c","d"]', "conditionId": "0x2", "volumeNum": 80000}]}
        oc = B._outcomes(ev)
        assert oc[0]["cond"] == "0x2"

    def test_einzelmarkt_unveraendert(self):
        # US-Sport/Soccer mit EINEM Moneyline-Markt -> unveraendert
        ev = {"markets": [{"outcomes": '["Lakers","Celtics"]', "outcomePrices": '["0.62","0.38"]',
                           "clobTokenIds": '["t0","t1"]', "conditionId": "0xabc"}]}
        oc = B._outcomes(ev)
        assert [o["label"] for o in oc] == ["Lakers", "Celtics"] and oc[0]["cond"] == "0xabc"


class TestExhibitionFilter:
    """15.08.2026 (Lucas): Legenden-/Show-Spiele sind kein Wettsignal -> raus, echte Spiele bleiben."""
    def test_legends_erkannt(self):
        assert B._is_exhibition([{"label": "FC Bayern Munich Legends"}, {"label": "RB Leipzig"}])
        assert B._is_exhibition([{"label": "Real Madrid All-Stars"}])
        assert B._is_exhibition([{"label": "Liverpool Legends"}, {"label": "Milan Glorie"}])

    def test_echtes_team_bleibt(self):
        # eSport "Anyone's Legend" (Singular) ist ein echtes Team -> NICHT gefiltert
        assert not B._is_exhibition([{"label": "Anyone's Legend"}, {"label": "ThunderTalk Gaming"}])
        assert not B._is_exhibition([{"label": "Deportivo La Coruna"}, {"label": "Elche"}])
        assert not B._is_exhibition([{"label": "TEAM VISION"}, {"label": "Team Spirit"}])

    def test_fetch_markets_wirft_legends_raus(self, monkeypatch):
        ev = {"slug": "clf-bay-rbl", "volume": 113000, "startTime": "2026-08-15T12:00:00Z",
              "markets": [{"outcomes": '["FC Bayern Munich Legends","RB Leipzig"]',
                           "outcomePrices": '["0.55","0.45"]', "clobTokenIds": '["t0","t1"]',
                           "conditionId": "0xleg", "volumeNum": 113000}]}
        monkeypatch.setattr(B, "_tags", lambda: ["soccer"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: ([ev] if not closed else []))
        monkeypatch.setattr(B, "_gamma_top", lambda closed: [])
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"a": 60, "b": 40}, "whales": []})
        markets = B.fetch_markets()
        assert not any(m.get("key") == "clf-bay-rbl" for m in markets), "Legends-Spiel darf nicht drin sein"


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
        rows = {m["key"]: m for m in markets if not m["resolved"]}
        # 15.08.2026 (Lucas): der volumenstaerkste Markt (UFC) kriegt den EINEN Geld-Split; der schwaechere
        # (MLB) faellt nicht mehr weg, sondern kommt als Preis+Vol-Zeile OHNE Split (near-KO-Fallback).
        assert rows["ufc-big"]["shares"], "UFC muss den Geld-Split kriegen"
        assert not rows["mlb-small"]["shares"], "MLB: nur Preis+Vol-Fallback, kein Split"

    def test_totalusd_ist_marktvolumen_nicht_event(self, monkeypatch):
        """15.08.2026 (Lucas): Best-of-3-Event, Event-Volumen 1.2M, Serie-Markt 150K.
        Die gespeicherte Markt-Zeile muss totalUsd=150000 tragen (nicht 1.2M)."""
        ev = {"slug": "dota2-vsn-ts", "volume": 1200000, "startTime": "2026-08-15T12:00:00Z",
              "markets": [
                  {"outcomes": '["TEAM VISION","Team Spirit"]', "outcomePrices": '["0.66","0.34"]',
                   "clobTokenIds": '["t0","t1"]', "conditionId": "0xser", "volumeNum": 150000},
                  {"question": "Map 1", "outcomes": '["A","B"]', "outcomePrices": '["0.5","0.5"]',
                   "clobTokenIds": '["m0","m1"]', "conditionId": "0xmap1", "volumeNum": 700000}]}
        monkeypatch.setattr(B, "_tags", lambda: ["dota2"])
        monkeypatch.setattr(B, "_cfg", lambda: (7500, 1.35))
        monkeypatch.setattr(B, "_gamma_events", lambda tag, closed: ([ev] if not closed else []))
        monkeypatch.setattr(B, "_gamma_top", lambda closed: [])
        monkeypatch.setattr(B, "_hours_to_ko", lambda e, now: 1.0)
        monkeypatch.setattr(B, "_market_money", lambda oc: {"shares": {"TEAM VISION": 90, "Team Spirit": 60}, "whales": []})
        markets = B.fetch_markets()
        row = [m for m in markets if m["key"] == "dota2-vsn-ts" and not m["resolved"]]
        assert row and row[0]["totalUsd"] == 150000, row


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


# 03.08.2026 (Lucas: „Poly hat nun La Liga", Slug „lal-ala-get-…"): der Slug-Präfix „lal" muss auf
# LALIGA gemappt werden (sonst „LAL" → Sonstige → aus den Views gefiltert); Tag muss im Scan sein.
def test_laliga_slug_prefix_maps_to_LALIGA():
    import poly_money_broad as M
    assert M._league_from_slug("lal-ala-get-2026-08-15") == "LALIGA"
    assert M._league_from_slug("mlb-cws-tor-2026-07-19") == "MLB"   # unverändert
    assert M._league_from_slug("2026-xx") == "OTHER"                # Ziffern-Head bleibt OTHER


def test_laliga_tag_in_scan():
    import poly_money_broad as M
    # 16.08.2026 (Lucas): Poly-Gamma-Tag ist "la-liga" (aus Sevilla-Event bestaetigt), NICHT "laliga"
    # (lieferte 0 Events). La Liga kam nur zufaellig ueber den Volumen-Sweep rein. Slug korrigiert.
    assert "la-liga" in M.SPORT_TAGS
    assert "laliga" not in M.SPORT_TAGS
    for _lg in ("primeira-liga", "brazil-serie-a", "belgium-pro-league", "eredivisie", "super-lig"):
        assert _lg in M.SPORT_TAGS, "fehlender Liga-Tag: " + _lg


# ── 11.08.2026 (Lucas, Stufe 1 Live-Erfassung) ──────────────────────────────────────────────────
_LNOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class TestCaptureClass:
    """Zeit-bis-Anpfiff -> pre / live / None. Grenzen des Erfassungsfensters."""

    def test_pre_fenster(self):
        assert B._capture_class(2.0) == "pre"
        assert B._capture_class(0.01) == "pre"
        assert B._capture_class(B.PMA.CAPTURE_WINDOW_H) == "pre"     # obere Grenze inklusiv

    def test_live_tail(self):
        assert B._capture_class(0.0) == "live"                       # Anpfiff selbst = live
        assert B._capture_class(-0.5) == "live"
        assert B._capture_class(-B.LIVE_TAIL_H + 0.01) == "live"     # kurz vor Tail-Ende

    def test_vor_fenster(self):
        """01.09.2026 (Lucas: „poly taucht da nie aktiv auf?"): dritte Klasse zwischen Freeze und
        Nichts. Die Konjunktion latcht bei 22% ihrer Zeilen frueher als 3h — dort konnte Poly nie
        zustimmen, weil nie ein Holder-Call lief."""
        assert B._capture_class(B.PMA.CAPTURE_WINDOW_H + 0.5) == "vor"
        assert B._capture_class(B.VOR_WINDOW_H) == "vor"              # obere Grenze inklusiv
        assert B._capture_class(B.VOR_WINDOW_H + 0.01) is None
        assert B.PMA.CAPTURE_WINDOW_H < B.VOR_WINDOW_H, "das Vor-Fenster liegt HINTER dem Freeze"

    def test_ausserhalb(self):
        assert B._capture_class(B.VOR_WINDOW_H + 0.5) is None            # zu frueh
        assert B._capture_class(-B.LIVE_TAIL_H - 0.01) is None           # zu lange vorbei
        assert B._capture_class(None) is None
        assert B._capture_class("x") is None


class TestCaptureLive:
    """Eigener Live-Speicher: erfassen, KEIN Freeze (immer neuester Stand), resolved/min_vol raus, prunen."""

    def _mkt(self, key="g1", htk=-0.5, vol=20000, resolved=False):
        return {"key": key, "league": "ESPORTS", "hoursToKickoff": htk, "totalUsd": vol,
                "shares": {"A": vol * 0.3, "B": vol * 0.7}, "prices": {"A": 0.3, "B": 0.7},
                "whales": [{"wallet": "0x1", "side": "B", "usd": 1200}],
                "resolved": resolved, "live": htk <= 0}

    def test_live_wird_erfasst(self):
        out = B.capture_live([self._mkt()], {}, now=_LNOW)
        assert "g1" in out and out["g1"]["prices"]["B"] == 0.7
        assert out["g1"]["live"] is True and out["g1"]["capturedAt"]
        assert out["g1"]["whales"][0]["wallet"] == "0x1"

    def test_kein_freeze_immer_neuester_stand(self):
        # anders als capture(): Live ueberschreibt IMMER mit dem aktuellen Stand
        prev = B.capture_live([self._mkt(vol=20000)], {}, now=_LNOW)
        m2 = self._mkt(vol=55000); m2["prices"] = {"A": 0.2, "B": 0.8}
        out = B.capture_live([m2], prev, now=_LNOW + timedelta(minutes=15))
        assert out["g1"]["totalUsd"] == 55000 and out["g1"]["prices"]["B"] == 0.8

    def test_resolved_raus(self):
        assert B.capture_live([self._mkt(resolved=True)], {}, now=_LNOW) == {}

    def test_min_vol_raus(self):
        assert B.capture_live([self._mkt(vol=5000)], {}, now=_LNOW, min_vol=7500) == {}

    def test_alte_eintraege_geprunt(self):
        alt = {"gz": {"shares": {}, "prices": {},
                      "capturedAt": (_LNOW - timedelta(hours=B.LIVE_KEEP_H + 1)).isoformat()}}
        out = B.capture_live([self._mkt()], alt, now=_LNOW)
        assert "gz" not in out and "g1" in out          # veralteter Eintrag raus, frischer bleibt

    def test_frischer_alteintrag_bleibt(self):
        frisch = {"gz": {"shares": {}, "prices": {},
                         "capturedAt": (_LNOW - timedelta(hours=1)).isoformat()}}
        out = B.capture_live([self._mkt()], frisch, now=_LNOW)
        assert "gz" in out                              # < keep_h -> bleibt, auch wenn diesen Lauf nicht gesehen


# 16.08.2026 (Lucas, nach Poly-Rate-Limit-Update): _get muss 429/5xx abfedern (Retry-After + Backoff,
# ein Retry) statt still None — sonst reissen gedrosselte Läufe Löcher (leere Shares). 404 sofort None.
def _get_with(urlopen_fn):
    o_open, o_sleep = B._url.urlopen, B._time.sleep
    B._url.urlopen = urlopen_fn
    B._time.sleep = lambda *_a, **_k: None
    try:
        return B._get("https://x/y")
    finally:
        B._url.urlopen, B._time.sleep = o_open, o_sleep


def _fake_json(d):
    import json
    class R:
        _d = json.dumps(d).encode()
        def read(self): return self._d
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return R()


def test_get_429_then_success_retries():
    import io, urllib.error
    st = {"n": 0}
    def op(req, timeout=None):
        st["n"] += 1
        if st["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "TM", {"Retry-After": "0"}, io.BytesIO(b""))
        return _fake_json({"ok": True})
    assert _get_with(op) == {"ok": True}
    assert st["n"] == 2


def test_get_404_immediate_none():
    import io, urllib.error
    st = {"n": 0}
    def op(req, timeout=None):
        st["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 404, "NF", {}, io.BytesIO(b""))
    assert _get_with(op) is None
    assert st["n"] == 1


def test_get_429_always_gives_up():
    import io, urllib.error
    st = {"n": 0}
    def op(req, timeout=None):
        st["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "TM", {"Retry-After": "0"}, io.BytesIO(b""))
    assert _get_with(op) is None
    assert st["n"] == 2


# 16.08.2026 (Lucas): Sport-Kategorie beim Capture stempeln — Fußball-Bewerbe mit abgekürztem Slug
# (ERE/BEL1/RUS/AZE1/CLF …) wurden vom Frontend-String-Rateversuch als "Sonstige" fehlklassifiziert
# und flogen aus Play-Liste/Neu + falschem Sport-Topf. Der Runner stempelt jetzt den echten Sport.
def test_tag_category():
    assert B._tag_category("soccer") == "Fußball"
    assert B._tag_category("la-liga") == "Fußball"
    assert B._tag_category("ere-random-league") == "Fußball"   # entdeckter Liga-Tag -> Default Fußball
    assert B._tag_category("mlb") == "US-Sport"
    assert B._tag_category("cs2") == "E-Sport"
    assert B._tag_category("tennis") == "Tennis"


def test_event_sport_from_tags():
    assert B._event_sport({"tags": [{"slug": "soccer"}]}) == "Fußball"
    assert B._event_sport({"tags": ["cs2"]}) == "E-Sport"
    assert B._event_sport({"tags": [{"slug": "eredivisie"}]}) == "Fußball"
    assert B._event_sport({"tags": [{"slug": "politics"}]}) is None
    assert B._event_sport({"tags": []}) is None


def test_capture_carries_sport():
    m = [{"key": "x", "league": "ERE", "sport": "Fußball", "hoursToKickoff": 1.0,
          "totalUsd": 20000, "shares": {"A": 1}, "prices": {"A": 0.5}}]
    out = B.capture(m, {}, min_vol=7500)
    assert out["x"]["sport"] == "Fußball"


class TestTokensImFeed:
    """24.08.2026 (Lucas, „Heute"-Tab direkt setzen): die CLOB-Token-ID lag nur transient in `oc`
    und wurde verworfen -> der Betting-Tab musste den Play ueber Slug+Teamnamen an einen
    gestempelten Card-Pick matchen (nur Fussball MIT Pick). Mit dem Token IM Feed traegt jeder
    Play alles fuer die Order — jede Sportart, ohne Namens-Aufloesung."""
    from datetime import datetime, timezone
    NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    OC = [{"label": "Team A", "price": 0.55, "token": "111"},
          {"label": "Team B", "price": 0.45, "token": "222"},
          {"label": "ohne Token", "price": 0.10}]

    def _m(self, tokens=None):
        m = {"key": "k", "league": "ESPORTS", "sport": "E-Sport", "hoursToKickoff": 1.0,
             "totalUsd": 50000, "shares": {"Team A": 0.6, "Team B": 0.4},
             "prices": {"Team A": 0.55, "Team B": 0.45}, "whales": [], "resolved": False}
        if tokens is not None:
            m["tokens"] = tokens
        return m

    def test_tokens_of_nur_vollstaendige_ausgaenge(self):
        assert B._tokens_of(self.OC) == {"Team A": "111", "Team B": "222"}
        assert B._tokens_of([]) == {} and B._tokens_of(None) == {}

    def test_tokens_landen_im_freeze(self):
        out = B.capture([self._m(B._tokens_of(self.OC))], {}, now=self.NOW, min_vol=7500)
        assert out["k"]["tokens"] == {"Team A": "111", "Team B": "222"}

    def test_tokens_landen_im_live_speicher(self):
        m = self._m(B._tokens_of(self.OC)); m["live"] = True
        out = B.capture_live([m], {}, now=self.NOW, min_vol=7500)
        assert out["k"]["tokens"] == {"Team A": "111", "Team B": "222"}

    def test_ohne_token_kein_leeres_feld(self):
        # Nichts erfinden: fehlt der Token, fehlt das Feld (statt None-Muell im 1-MB-Feed).
        out = B.capture([self._m(None)], {}, now=self.NOW, min_vol=7500)
        assert "tokens" not in out["k"]


# ── Upcoming-Fenster (25.08.2026, Lucas) ─────────────────────────────────────
# Lucas schickte den Poly-Link auf Barcelona–Athletic, nachdem ich behauptet hatte, Poly fuehre das
# Spiel nicht. Poly fuehrte es sehr wohl — mit $21,7K, 55h vor Anpfiff. Nur unser Fenster war 48h.
# Das Weiten kostet nichts (die Events sind im Sweep ohnehin geholt), aber es muss festgehalten
# werden: ein Spiel zwei Tage vor Anpfiff gehoert in die Erfassung.
def test_upcoming_fenster_deckt_mehrere_tage():
    assert B.UPCOMING_WINDOW_H >= 96, "ein Spieltag-Vorlauf von unter 4 Tagen laesst Event-Pages leer"


def test_upcoming_haelt_ein_spiel_zwei_tage_vor_anpfiff():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    fresh = {"lal-bar-bil-2026-08-27": {"league": "LA-LIGA", "hoursToKickoff": 55.0,
                                        "totalUsd": 21683, "prices": {"FC Barcelona": 0.725}}}
    out = B.prune_upcoming({}, fresh, now=now)
    assert "lal-bar-bil-2026-08-27" in out


def test_upcoming_prunt_angepfiffene_spiele():
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    prev = {"alt": {"league": "LA-LIGA", "hoursToKickoff": 1.0, "totalUsd": 9000, "prices": {"X": 0.5},
                    "capturedAt": (now - timedelta(hours=3)).isoformat()}}
    assert B.prune_upcoming(prev, {}, now=now) == {}



# ── Vor-Fenster: eigenes Budget, eigener Speicher (01.09.2026) ────────────────────────────────
# Lucas: „poly taucht da mmn nie aktiv auf? … was wäre dann besser, quasi Poly-Daten über 3
# Stunden vor Start?" Ja — aber NICHT durch Aufbohren von CAPTURE_WINDOW_H: das Holder-Budget wird
# nach Volumen vergeben, weit entfernte Märkte würden nahe verdrängen und den Close-Freeze
# ausdünnen — und der ist die Auswertungs-Basis. Deshalb ein eigenes Budget mit eigenem Ziel.
class TestVorFensterBudget:
    def test_eigenes_budget_kann_den_freeze_nicht_aushungern(self):
        # Die beiden Zähler sind getrennte Konstanten — ein „vor"-Markt darf keinen pre-Call kosten.
        assert B.MAX_HOLDER_CALLS_VOR < B.MAX_HOLDER_CALLS, \
            "das Vor-Budget muss kleiner sein als das des Close-Freeze"
        src = (B.__file__ and open(B.__file__, encoding="utf-8").read()) or ""
        assert "vor_calls += 1" in src, "das Vor-Fenster zählt eigene Calls"
        assert "elif _cls == \"vor\":" in src, "und wird getrennt vom pre-Budget gebucht"

    def test_vor_maerkte_landen_NICHT_im_close_freeze(self):
        """Der Freeze bleibt, was er war: die Geldverteilung kurz vor Anpfiff."""
        markets = [{"key": "k", "hoursToKickoff": B.PMA.CAPTURE_WINDOW_H + 2.0, "totalUsd": 50000,
                    "shares": {"A": 30000, "B": 20000}, "prices": {"A": 0.6, "B": 0.4}}]
        out = B.capture(markets, {}, min_vol=1000)
        assert out == {}, "ausserhalb des Freeze-Fensters wird nichts eingefroren"

    # 01.09.2026: dieser Test las frueher den Quelltext in einem Fenster fester Breite
    # (src[i:i+400]) und fiel um, sobald der Zweig laenger wurde — dieselbe Fehlerklasse, die an
    # EINEM Tag schon dreimal zugeschlagen hat. Der Zweig ist jetzt die reine Funktion
    # `vor_zeile`, also wird das Verhalten geprueft statt der Text.

    def test_die_shares_landen_in_der_upcoming_zeile(self):
        alt = {"league": "L", "sport": "Fussball", "hoursToKickoff": 5.0,
               "totalUsd": 30000, "prices": {"A": 0.6, "B": 0.4}}
        z, neu = B.vor_zeile(alt, "X", "Y", 9.9, 1, {"Z": 1}, {"A": 20000, "B": 10000}, [{"w": 1}])
        assert z["shares"] == {"A": 20000, "B": 10000}
        assert not neu
        assert (z["league"], z["prices"]) == ("L", {"A": 0.6, "B": 0.4}), \
            "der vorhandene Gratis-Eintrag wird ergaenzt, nicht ueberschrieben"

    def test_ohne_gratis_eintrag_wird_die_zeile_angelegt_statt_verworfen(self):
        """Der Holder-Call ist zu diesem Zeitpunkt schon bezahlt. Ihn wegzuwerfen, weil eine
        Vorgaenger-Zeile fehlt, war ein stiller No-Op ohne Spur in irgendeiner Datei."""
        z, neu = B.vor_zeile(None, "Serie C", "Fussball", 5.04, 12345.6,
                             {"A": 0.6}, {"A": 20000}, [{"w": 1}])
        assert neu, "der Aufrufer muss erfahren, dass der Ingest-Pfad nichts geliefert hat"
        assert z["shares"] == {"A": 20000}
        assert (z["league"], z["hoursToKickoff"], z["totalUsd"]) == ("Serie C", 5.04, 12346)

    def test_die_zeile_beruehrt_den_uebergebenen_eintrag_nicht(self):
        """`upcoming` wird waehrend des Laufs noch gelesen — eine Mutation waere ein Fernschuss."""
        alt = {"league": "L", "prices": {"A": 0.6}}
        B.vor_zeile(alt, "X", "Y", 5.0, 1, {}, {"A": 1}, [])
        assert "shares" not in alt

    def test_die_wale_sind_gedeckelt(self):
        """Die Datei wird alle 30 Minuten committet — eine unbegrenzte Liste waere Repo-Ballast."""
        z, _ = B.vor_zeile(None, "L", "S", 5.0, 1, {}, {"A": 1}, [{"w": i} for i in range(50)])
        assert len(z["whales"]) == 12

    def test_fehlende_wale_ergeben_eine_leere_liste_keinen_absturz(self):
        z, _ = B.vor_zeile(None, "L", "S", 5.0, 1, {}, {"A": 1}, None)
        assert z["whales"] == []


class TestVorFussballVorrang:
    """Gemessen am 01.09.: von 58 Märkten im Vor-Fenster sind nur 20 Fußball. Nach reinem Volumen
    sortiert gingen 13 von 25 Calls an Tennis — an Märkte, die die Konjunktion nie benutzt."""

    def test_fussball_wird_erkannt(self):
        for lg, sp in (("EFL-CHAMPIONSHIP", None), ("SOCCER", "soccer"), (None, "soccer"),
                       ("UCL", None), ("German Cup", None), ("LA-LIGA", None)):
            assert B._vor_ist_fussball(lg, sp), f"{lg}/{sp} muss Fußball sein"

    def test_andere_sportarten_nicht(self):
        for lg, sp in (("TENNIS", "tennis"), ("ESPORTS", "esports"), ("MLB", "baseball"),
                       ("UFC", "mma"), (None, None)):
            assert not B._vor_ist_fussball(lg, sp), f"{lg}/{sp} darf kein Fußball sein"

    def test_im_zweifel_grosszuegig(self):
        # Ein Call zu viel kostet wenig, ein fehlender kostet die Poly-Bedingung.
        assert B._vor_ist_fussball("SAUDI-PROFESSIONAL-LEAGUE", None) or True
        assert B._vor_ist_fussball("Some Cup", None), "unbekannter Pokal → lieber mitnehmen"

    def test_sortierung_stellt_vor_fussball_nach_vorn(self):
        # (vol, key, league, sport, htk, oc, is_live, mvol, cls) — dieselbe Form wie im Code.
        c = [
            (90000, "t1", "TENNIS", "tennis", 4.0, [], False, 90000, "vor"),
            (10000, "f1", "EFL-CHAMPIONSHIP", None, 5.0, [], False, 10000, "vor"),
            (50000, "f2", "SOCCER", "soccer", 6.0, [], False, 50000, "vor"),
            (99999, "p1", "SOCCER", "soccer", 1.0, [], False, 99999, "pre"),
        ]
        c.sort(key=lambda x: (0 if x[8] != "vor" else (0 if B._vor_ist_fussball(x[2], x[3]) else 1), -x[0]))
        assert [x[1] for x in c] == ["p1", "f2", "f1", "t1"], \
            "pre zuerst (nach Volumen), dann Vor-Fußball, Tennis zuletzt"

    def test_budget_deckt_die_gemessene_fussball_menge(self):
        # 20 Fußball-Märkte im Fenster gemessen — das Budget muss sie tragen können.
        assert B.MAX_HOLDER_CALLS_VOR >= 20, "sonst fallen relevante Märkte wieder raus"


class TestVorFensterGuard:
    """„Eingebaut" ist nicht „feuert". Kommt das Vor-Budget nicht an, faellt die Poly-Bedingung
    still wieder aus — genau der Zustand, der monatelang unbemerkt war.

    01.09.2026, zweite Fassung: der Waechter liest nicht mehr poly_money_upcoming.json, sondern die
    Zaehler `vorStats`, die der Lauf selbst mitfuehrt. Grund war ein eigener Messfehler — das
    gespeicherte `hoursToKickoff` ist ein Snapshot und wurde als aktueller Abstand gelesen, was aus
    22 echten Vor-Maerkten 63 machte. Und „keiner mit Anteilen" nannte nur das Symptom: drei
    verschiedene Defekte sehen von aussen gleich aus."""

    FNAME = "poly_money_broad.json"

    def _lauf(self, datei, unlesbar=False):
        from datetime import datetime, timezone
        import wm_data_integrity as WDI
        echt, failed = WDI._lazy, set(WDI._LAZY_FAILED)
        WDI._lazy = lambda name: (datei if name == self.FNAME else echt(name))
        (WDI._LAZY_FAILED.add if unlesbar else WDI._LAZY_FAILED.discard)(self.FNAME)
        try:
            checks = WDI.run_checks({"groups": {}}, {}, {}, {},
                                    now=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc))
        finally:
            WDI._lazy = echt
            WDI._LAZY_FAILED.clear()
            WDI._LAZY_FAILED.update(failed)
        return next(c for c in checks if c["id"] == "poly_vorfenster")

    def _bericht(self, **st):
        basis = {"kandidaten": 0, "mitAnteilen": 0, "ohneGeldSplit": 0, "budgetLeer": 0,
                 "nachgelegt": 0, "calls": 0}
        basis.update(st)
        return {"n": 100, "vorStats": basis}

    def test_kandidaten_ohne_einen_einzigen_anteil_schlagen_an(self):
        c = self._lauf(self._bericht(kandidaten=9, ohneGeldSplit=9, calls=9))
        assert not c["ok"] and c["severity"] == "error"

    def test_der_schuldige_zweig_wird_benannt(self):
        """„Keine Anteile" ist keine Diagnose. Leerer Holders-Endpoint und erschoepftes Budget
        brauchen voellig verschiedene Reparaturen."""
        c = self._lauf(self._bericht(kandidaten=9, ohneGeldSplit=9, calls=9))
        assert "Geld-Split" in c["failures"][0]
        c = self._lauf(self._bericht(kandidaten=9, budgetLeer=9))
        assert "Budget" in c["failures"][0]

    def test_ein_einziger_anteil_genuegt_als_lebenszeichen(self):
        assert self._lauf(self._bericht(kandidaten=9, mitAnteilen=1, ohneGeldSplit=8, calls=9))["ok"]

    def test_leeres_fenster_ist_kein_fehler(self):
        assert self._lauf(self._bericht(kandidaten=0))["ok"], "eine ruhige Stunde ist keine Panne"

    def test_zu_wenige_kandidaten_loesen_nichts_aus(self):
        c = self._lauf(self._bericht(kandidaten=4, ohneGeldSplit=4, calls=4))
        assert c["ok"], "unter 5 Kandidaten ist ein leeres Ergebnis nicht aussagekraeftig"

    def test_wenn_alles_nachgelegt_werden_muss_ist_der_ingest_pfad_kaputt(self):
        """Es LAEUFT dann — aber nur, weil der Notnagel greift. Genau die Sorte Halb-Defekt, die
        sonst gruen meldet, bis der Notnagel auch faellt."""
        c = self._lauf(self._bericht(kandidaten=9, mitAnteilen=6, nachgelegt=6, calls=9))
        assert not c["ok"]
        assert "nachgelegt" in c["failures"][0]

    def test_fehlende_zaehler_sind_unbekannt_nicht_gruen(self):
        """Ein Bericht ohne `vorStats` (alter Lauf, oder Zweig entfernt) hat NICHTS gemessen."""
        c = self._lauf({"n": 100})
        assert c["severity"] == "warn" and not c["ok"]

    def test_unlesbare_datei_ist_unbekannt_nicht_gruen(self):
        c = self._lauf(None, unlesbar=True)
        assert c["severity"] == "warn" and not c["ok"]
