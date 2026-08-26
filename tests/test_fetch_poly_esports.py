"""19.07.2026 — E-Sport als eigener Poly-Datensatz. `build()` formt Gamma-Events + Holders-Geld-
Split in das Datensatz-Format (prices/smartmoney/wallets), das der Wallets-Tab wie eine Liga
rendert. Fetch/Holders sind Runner-only; hier die reine Formung mit injiziertem sm_fn."""
import fetch_poly_esports as E


def _ev(slug="cs2-navi-faze", vol=50000, names='["NAVI","FaZe"]', prices='["0.58","0.42"]'):
    return {"slug": slug, "volume": vol, "startTime": "2026-07-20T18:00:00Z",
            "markets": [{"outcomes": names, "outcomePrices": prices,
                         "clobTokenIds": '["t0","t1"]', "conditionId": "0xabc"}]}


def _sm(cond, token, price):
    return {"usd": 30000 if token == "t0" else 20000,
            "topHolderShare": 0.55 if token == "t0" else 0.80, "holders": 40,
            "_wallets": [{"wallet": "0x" + str(token), "usd": 5000, "shares": 9000}]}


def test_build_prices_smartmoney_wallets():
    out = E.build([_ev()], _sm)
    assert "cs2-navi-faze" in out["prices"]["prices"]
    m = out["smartmoney"]["matches"]["cs2-navi-faze"]
    assert m["totalUsd"] == 50000
    assert m["outcomes"]["home"]["share"] == 0.6 and m["outcomes"]["away"]["share"] == 0.4
    assert m["outcomes"]["away"]["topHolderShare"] == 0.80
    assert len(out["wallets"]["topPositionsAll"]) == 2


def test_duennes_volumen_raus():
    assert E.build([_ev(vol=1000)], _sm)["prices"]["prices"] == {}


def test_nur_zwei_wege():
    # 3-Wege (mit Draw) ist kein E-Sport-Moneyline → übersprungen
    ev = _ev(names='["A","Draw","B"]', prices='["0.4","0.3","0.3"]')
    assert E.build([ev], _sm)["prices"]["prices"] == {}


def test_ohne_geld_split_kein_markt():
    assert E.build([_ev()], lambda c, t, p: None)["prices"]["prices"] == {}


def test_wallets_nach_groesse_sortiert():
    def sm_big(cond, token, price):
        return {"usd": 30000, "topHolderShare": 0.5, "holders": 40,
                "_wallets": [{"wallet": "0xsmall", "usd": 1000, "shares": 100},
                             {"wallet": "0xbig", "usd": 9000, "shares": 900}]}
    top = E.build([_ev()], sm_big)["wallets"]["topPositionsAll"]
    assert top[0]["usd"] >= top[-1]["usd"]


def test_names_als_home_away():
    m = E.build([_ev()], _sm)["smartmoney"]["matches"]["cs2-navi-faze"]
    assert m["home"] == "NAVI" and m["away"] == "FaZe"


class TestFetchEventsDiagnose:
    """20.07.2026 — E-Sport lief seit Bau leer (0 Commits), aber STILL: man sah nie, ob die Tags
    ziehen. _fetch_events muss je-Tag-Rohzähler liefern, damit „warum leer" sichtbar ist."""

    def test_diag_zaehlt_je_tag(self):
        fetch = lambda tag: [_ev(slug=tag + "-1")] if tag == "cs2" else []
        events, diag = E._fetch_events(gamma_fetch=fetch)
        assert diag["cs2"] == 1
        assert diag["lol"] == 0 and diag["dota"] == 0
        assert len(events) == 1

    def test_dedup_ueber_tags(self):
        # Dasselbe Event unter zwei Tags → nur einmal in events, aber in beiden diag gezählt.
        fetch = lambda tag: [_ev(slug="same")] if tag in ("cs2", "lol") else []
        events, diag = E._fetch_events(gamma_fetch=fetch)
        assert len(events) == 1
        assert diag["cs2"] == 1 and diag["lol"] == 1

    def test_alles_leer_gibt_leer(self):
        events, diag = E._fetch_events(gamma_fetch=lambda tag: [])
        assert events == [] and sum(diag.values()) == 0


# ── Befund 12 (25.08.2026): Conviction-Score und Exit-Watch waren per Konstruktion tot ──
# `clustersAll` stand hartkodiert auf [] und ein `matches`-Schlüssel wurde gar nicht erst
# geschrieben. Der Conviction-Score fand damit für JEDEN E-Sport-Markt nichts und gab null
# zurück; die Exit-Liquiditäts-Warnung konnte nie rendern. Gemessen: 60 Positionen, 60 Trades,
# 0 Cluster, kein matches-Key — während der Fußball-Fetcher beides korrekt schrieb.

def _trades(cond, pick, side, price):
    """Zwei unabhängige BUY-Wallets auf 'home', eine SELL auf 'away'."""
    if side != "home":
        return [{"wallet": "0xc", "side": "away", "action": "SELL", "usd": 4000,
                 "ts": "2026-07-20T12:00:00Z"}]
    return [{"wallet": "0xa", "side": "home", "action": "BUY", "usd": 6000,
             "ts": "2026-07-20T12:00:00Z"},
            {"wallet": "0xb", "side": "home", "action": "BUY", "usd": 3000,
             "ts": "2026-07-20T12:30:00Z"}]


class TestClusterUndMatches:
    def test_clusters_werden_gebaut(self):
        w = E.build([_ev()], _sm, _trades)["wallets"]
        home = next((c for c in w["clustersAll"] if c["side"] == "home"), None)
        assert home is not None, "clustersAll war der Befund — darf nicht wieder leer sein"
        assert home["cluster"] == 2                    # zwei DISTINKTE Buy-Wallets
        assert home["netFlowUsd"] == 9000
        assert home["pick"] == "NAVI" and home["key"] == "cs2-navi-faze"

    def test_verkaufsseite_hat_negativen_netflow(self):
        w = E.build([_ev()], _sm, _trades)["wallets"]
        away = next(c for c in w["clustersAll"] if c["side"] == "away")
        assert away["cluster"] == 0 and away["netFlowUsd"] == -4000

    def test_matches_schluessel_existiert(self):
        """Ohne `matches` findet der Conviction-Score nichts und gibt für jeden Markt null."""
        w = E.build([_ev()], _sm, _trades)["wallets"]
        assert "matches" in w
        m = w["matches"]["cs2-navi-faze"]
        assert m["home"] == "NAVI" and m["away"] == "FaZe"
        assert [t["wallet"] for t in m["bigTrades"]][:1] == ["0xb"]   # jüngster Trade zuerst
        assert len(m["topPositions"]) == 2

    def test_ohne_trades_keine_cluster_aber_matches(self):
        w = E.build([_ev()], _sm)["wallets"]
        assert w["clustersAll"] == []
        assert w["matches"]["cs2-navi-faze"]["bigTrades"] == []

    def test_gleiche_wallet_mehrfach_ist_kein_konsens(self):
        def einer(cond, pick, side, price):
            if side != "home":
                return []
            return [{"wallet": "0xa", "side": "home", "action": "BUY", "usd": 5000,
                     "ts": "2026-07-20T12:00:00Z"},
                    {"wallet": "0xa", "side": "home", "action": "BUY", "usd": 5000,
                     "ts": "2026-07-20T12:10:00Z"}]
        w = E.build([_ev()], _sm, einer)["wallets"]
        home = next(c for c in w["clustersAll"] if c["side"] == "home")
        assert home["cluster"] == 1, "eine Wallet ×2 ist kein Cluster"

    def test_trades_landen_weiterhin_im_globalen_feed(self):
        w = E.build([_ev()], _sm, _trades)["wallets"]
        assert len(w["bigTradesAll"]) == 3
        assert all(t.get("key") == "cs2-navi-faze" for t in w["bigTradesAll"])
