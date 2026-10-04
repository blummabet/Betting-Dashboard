"""04.10.2026 (Lucas: „ATP zeigen wir in Bursts nicht?" · „Live-Einstieg: viel Mist — niedrige Einsaetze,
US-Sport, ATP"). Fehlerklasse: eine Sperrliste, die nur dort gilt, wo jemand daran gedacht hat."""
import inspect

import poly_live_watch as P
import stake_burst_push as S


def burst(liga, phase="vor", kat="Tennis"):
    return {"wetten": [{"kat": kat, "liga": liga, "phase": phase}]}


def test_stake_atp_wta_auch_vor_anpfiff_stumm_itf_bleibt():
    assert S.stumm_grund(burst("ATP Beijing, China Men Singles")) == "ATP/WTA stumm (Lucas 04.10.)"
    assert S.stumm_grund(burst("WTA Wuhan, China Women Singles"))
    assert S.stumm_grund(burst("ITF Women Monastir")) is None
    assert S.stumm_grund(burst("Premier League", kat="Fußball")) is None


def _live(key, league, usd=30000):
    return {key: {"league": league, "totalUsd": 200000, "prices": {"A": 0.5, "B": 0.5},
                  "whales": [{"wallet": "0xw", "side": "A", "usd": usd}]}}


def test_live_watch_wendet_die_sperrliste_an():
    cats = ("US-Sport", "Kampfsport", "Cricket")
    assert P.find_alerts(_live("nba-lal-bos-2026-10-04", "NBA"), {}, {}, set(), cats=cats) == []
    assert P.find_alerts(_live("ufc-a-b-2026-10-04", "UFC"), {}, {}, set(), cats=cats) == []
    assert P.find_alerts(_live("atp-alcaraz-shapova-2026-10-04", "TENNIS"), {}, {}, set(), cats=cats) == []
    assert len(P.find_alerts(_live("cs2-a-b-2026-10-04", "ESPORTS"), {}, {}, set(), cats=cats)) == 1
    assert len(P.find_alerts(_live("itf-a-b-2026-10-04", "TENNIS"), {}, {}, set(), cats=cats)) == 1


def test_live_watch_holt_die_sperrliste_aus_der_einen_quelle():
    src = inspect.getsource(P.main)
    assert "W.blocked_cats(" in src and "cats=cats" in src


def test_scharfe_wallet_braucht_jetzt_10k():
    assert P.SHARP_MIN_USD == 10000
