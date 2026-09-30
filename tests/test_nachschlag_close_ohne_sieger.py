"""30.09.2026 — cs2-bmb-gbc2-2026-09-24 hing 6,3 Tage: Polymarket 0,5/0,5 (UMA resolved), aber
die Close-Zeile stand auf resolved=True ohne Sieger und die offene Position fiel aus beiden
Nachschlag-Wegen."""
import poly_money_broad as P

KEY = "cs2-bmb-gbc2-2026-09-24"
COND = "0x0dcd"
CLOSE = {KEY: {"resolved": True, "resolvedWinner": None, "cond": COND,
               "resolvedPrices": {"BASEMENT BOYS": 0.5, "Gothboiclique": 0.5},
               "capturedAt": "2026-09-24T16:10:23+00:00"}}
EV = [{"slug": KEY, "closed": True, "markets": [{
    "conditionId": COND, "umaResolutionStatus": "resolved", "closed": True,
    "outcomes": '["BASEMENT BOYS", "Gothboiclique"]', "outcomePrices": '["0.5", "0.5"]'}]}]


def _lauf(close, extra):
    gefragt = []
    def get(url):
        gefragt.append(url)
        return EV if KEY in url else []
    rows = P.backfill_resolutions_by_slug(close, set(), get=get, extra=extra)
    return rows, gefragt


def test_offene_position_mit_close_ohne_sieger_wird_nachgeschlagen():
    rows, gefragt = _lauf(CLOSE, [{"key": KEY, "cond": COND}])
    assert any(KEY in u for u in gefragt), "Gegentest: der alte Filter fragte gar nicht erst"
    buch = P.update_resolutions({}, rows)
    assert (buch.get(KEY) or {}).get("teilung") == {"BASEMENT BOYS": 0.5, "Gothboiclique": 0.5}, \
        "die Zeile muss bis ins Aufloesungsbuch als Teilung ankommen"


def test_close_mit_sieger_bleibt_draussen():
    mit = {KEY: dict(CLOSE[KEY], resolvedWinner="BASEMENT BOYS")}
    _, gefragt = _lauf(mit, [{"key": KEY, "cond": COND}])
    assert not any(KEY in u for u in gefragt), "ein bekannter Sieger braucht keinen Nachschlag"


def test_meldung_nennt_den_wahren_grund():
    import poly_data_integrity as PI
    ctx = PI.PolyCtx(close={"atp-alcaraz-minaur-2026-09-27": {
        "resolved": True, "resolvedWinner": None,
        "resolvedPrices": {"Carlos Alcaraz": 0.5, "Alex de Minaur": 0.5}}}, resolutions={})
    txt = PI._warum_haengt({"key": "atp-alcaraz-minaur-2026-09-27"}, ctx)
    assert "ohne Sieger" in txt and "UMA" in txt, txt
    assert PI._warum_haengt({"key": "x"}, ctx) == "keine Auflösung gefunden"
