"""Public-Regel ausserhalb der Top 5 (28.09.2026, Lucas: „1 bis 4 kannst du umsetzen").

Pinnacle-Konsens -> wie bisher. International ohne Konsens -> raus. Rest ohne Konsens -> nur bei
fallender Quote. Top 5 unberuehrt. Herleitung im Docstring von _pub_anker_grund.
"""
import inspect
import betfair_alerts as BA


def _a(league, tier, lead_dir=None, mid="1"):
    return {"matchId": mid, "league": league, "tier": tier, "leadDir": lead_dir,
            "scenario": "fresh", "market": "Match Odds"}


def _cidx(verdict):
    return {"1": {"verdict": verdict, "agree": verdict == "konsens"}}


def test_mit_pinnacle_konsens_bleibt_alles_wie_bisher():
    for tier, lg in (("rest", "Colombian Primera A"), ("top", "UEFA Nations League")):
        for d in ("in", "flat", None):
            assert BA._pub_anker_grund(_a(lg, tier, d), _cidx("konsens")) is None


def test_international_ohne_anker_raus():
    for v in ("no_anchor", "uneinig"):
        assert BA._pub_anker_grund(_a("UEFA Nations League", "top", "in"), _cidx(v)) == "intl_ohne_anker"
    assert BA._pub_anker_grund(_a("UEFA Nations League", "top", "in"), {}) == "intl_ohne_anker"


def test_rest_ohne_anker_nur_bei_fallender_quote():
    assert BA._pub_anker_grund(_a("Colombian Primera A", "rest", "in"), _cidx("no_anchor")) is None
    for d in ("flat", "out", None):
        assert BA._pub_anker_grund(_a("Colombian Primera A", "rest", d), _cidx("no_anchor")) \
            == "rest_ohne_anker_ohne_fall", d


def test_gegenbeweis_top5_ist_unberuehrt():
    """Die Top 5 sind eine eigene, noch offene Entscheidung — diese Regel fasst sie nicht an."""
    for d in ("flat", None):
        assert BA._pub_anker_grund(_a("English Premier League", "top", d), _cidx("no_anchor")) is None


def test_regel_sitzt_im_sendepfad_und_im_schattenbuch():
    src = inspect.getsource(BA.main)
    assert "pub_alerts = [a for a in pub_alerts if not _pub_anker_grund(a, cidx)]" in src
    assert '("intl_ohne_anker"' in src and '("rest_ohne_anker_ohne_fall"' in src
    # die Regel greift NACH der Konsens-Beschaffung
    assert src.index("cidx = _consensus_index()") < src.index("_pub_anker_grund(a, cidx)")


# ── 28.09.2026 abends: Top 5 nur noch Schattenbuch ──────────────────────────────────
def test_top5_geht_nicht_mehr_in_den_public_kanal():
    for lg in ("English Premier League", "Spanish La Liga", "German Bundesliga", "Italian Serie A",
               "French Ligue 1", "US MLS"):
        assert BA._pub_top5_raus({"league": lg}), lg


def test_gegenbeweis_zweite_ligen_frauen_und_international_bleiben():
    for lg in ("English Sky Bet Championship", "German Bundesliga 2", "Spanish La Liga Women",
               "UEFA Nations League", "UEFA Champions League", "Colombian Primera A"):
        assert not BA._pub_top5_raus({"league": lg}), lg


def test_top5_sitzt_im_sendepfad_und_im_schattenbuch():
    src = inspect.getsource(BA.main)
    assert "pub_alerts = [a for a in pub_alerts if not _pub_top5_raus(a)]" in src
    assert '("top5", _pub_top5_raus)' in src
    # nur Public: der Trades-Versand liegt vor dem Public-Block und kennt die Regel nicht
    assert src.index("_pub_top5_raus") > src.index("send_trades_message(msg)")
