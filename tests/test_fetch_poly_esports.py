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
