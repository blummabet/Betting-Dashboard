# tests/test_poly_shortlist_track.py — 02.08.2026 (Lucas): Buchhaltung des Shortlist-Paper-Trackers.
# Reine Funktionen (kein Netz, kein node): Öffnen, lastPrice-Update, Abrechnung (win/loss pnl/clv),
# Public-Split, Conviction-Aggregat, kein Doppel-Öffnen abgerechneter Plays. Plus Rolling-Resolutions.
import importlib
from datetime import datetime, timezone, timedelta

st = importlib.import_module("poly_shortlist_track")
pmb = importlib.import_module("poly_money_broad")

NOW = datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc)


def _emit(plays):
    return {"generatedAt": NOW.isoformat(), "plays": plays,
            "public": [f"{p['key']}|{p['side']}" for p in plays if p.get("public")]}


def test_open_new_play_at_snapshot_price():
    emit = _emit([{"key": "mlb-a-b", "side": "Team A", "verdict": "BET", "conv": 9,
                   "league": "MLB", "price": 0.62, "public": True, "reasons": ["x"]}])
    t = st.update_track({}, emit, {}, {}, now=NOW)
    assert "mlb-a-b|Team A" in t["open"]
    e = t["open"]["mlb-a-b|Team A"]
    assert e["entryPrice"] == 0.62 and e["public"] is True and e["stake"] == st.STAKE
    assert t["agg"]["all"]["n"] == 0            # noch nichts abgerechnet


def test_settle_win_pnl_and_clv():
    prev = {"open": {"mlb-a-b|Team A": {"key": "mlb-a-b", "side": "Team A", "verdict": "BET",
            "conv": 9, "league": "MLB", "entryPrice": 0.62, "lastPrice": 0.68,
            "public": True, "stake": 10.0, "firstTs": NOW.isoformat()}}}
    res = {"mlb-a-b": {"winner": "Team A", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), {}, res, now=NOW)
    assert not t["open"]
    s = t["settled"][0]
    assert s["result"] == "win"
    # shares = 10/0.62; Gewinn = 10*(1-0.62)/0.62 = 6.13
    assert abs(s["pnl"] - 6.13) < 0.01
    assert s["clvPP"] == round((0.68 - 0.62) * 100, 2)   # +6.0pp
    assert t["agg"]["all"]["wins"] == 1 and t["agg"]["public"]["n"] == 1
    assert t["agg"]["byConv"]["9"]["n"] == 1


def test_settle_loss_is_minus_stake():
    prev = {"open": {"nba-c-d|Club Y": {"key": "nba-c-d", "side": "Club Y", "verdict": "FADE",
            "conv": 7, "league": "NBA", "entryPrice": 0.40, "lastPrice": 0.35,
            "public": False, "stake": 10.0}}}
    res = {"nba-c-d": {"winner": "Club X", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), {}, res, now=NOW)
    s = t["settled"][0]
    assert s["result"] == "loss" and s["pnl"] == -10.0
    assert t["agg"]["all"]["pnl"] == -10.0 and t["agg"]["public"]["n"] == 0
    assert t["agg"]["byVerdict"]["FADE"]["n"] == 1


def test_lastprice_tracked_from_close_for_clv():
    prev = {"open": {"mlb-a-b|Team A": {"key": "mlb-a-b", "side": "Team A", "conv": 8,
            "entryPrice": 0.50, "lastPrice": 0.50, "stake": 10.0, "public": False}}}
    close = {"mlb-a-b": {"prices": {"Team A": 0.60, "Team B": 0.40}}}
    t = st.update_track(prev, _emit([]), close, {}, now=NOW)
    assert t["open"]["mlb-a-b|Team A"]["lastPrice"] == 0.60   # Schluss-Referenz nachgezogen


def test_no_reopen_of_settled_play():
    prev = {"settled": [{"key": "mlb-a-b", "side": "Team A", "verdict": "BET", "conv": 9,
            "result": "win", "pnl": 6.13, "clvPP": 6.0, "stake": 10.0, "public": True}]}
    emit = _emit([{"key": "mlb-a-b", "side": "Team A", "verdict": "BET", "conv": 9,
                   "league": "MLB", "price": 0.62, "public": True}])
    t = st.update_track(prev, emit, {}, {}, now=NOW)
    assert not t["open"]                    # bereits abgerechnet → nicht wieder öffnen
    assert len(t["settled"]) == 1


def test_skip_play_without_clean_price():
    emit = _emit([{"key": "k", "side": "S", "verdict": "BET", "conv": 9, "price": None}])
    t = st.update_track({}, emit, {}, {}, now=NOW)
    assert not t["open"]                     # kein sauberer Einstiegspreis → nicht öffnen


def test_rolling_resolutions_merge_and_prune():
    old = {"stale-key": {"winner": "X", "ts": (NOW - timedelta(days=20)).isoformat()},
           "keep-key": {"winner": "Y", "ts": (NOW - timedelta(days=2)).isoformat()}}
    markets = [{"key": "new-key", "resolved": True, "resolvedPrices": {"A": 1.0, "B": 0.0}}]
    out = pmb.update_resolutions(old, markets, now=NOW)
    assert out["new-key"]["winner"] == "A"   # neue Auflösung übernommen
    assert "keep-key" in out                  # 2 Tage alt → bleibt
    assert "stale-key" not in out             # 20 Tage alt → geprunt


# ── 02.08.2026 (Lucas: „mmn sind da schon einige vorbei"): der flaky node-Emitter darf die
#    Abrechnung NICHT blockieren. Früher: emit is None → main() return 0 → aufgelöste Plays blieben
#    „offen", obwohl poly_resolutions.json den Sieger kennt. Jetzt: ohne Emit keine NEUEN Plays,
#    aber offene werden weiter abgerechnet. ────────────────────────────────────────────────────
def test_main_settles_open_plays_even_when_emitter_dead(tmp_path, monkeypatch):
    import json as _json
    # Vorstand: ein offener Play, dessen Markt bereits aufgelöst ist.
    prev = {"open": {"lol-a-b|Team A": {"key": "lol-a-b", "side": "Team A", "verdict": "BET",
            "conv": 9, "league": "LoL", "entryPrice": 0.60, "lastPrice": 0.60,
            "public": False, "stake": 10.0, "firstTs": NOW.isoformat()}}, "settled": []}
    (tmp_path / "poly_shortlist_track.json").write_text(_json.dumps(prev), encoding="utf-8")
    (tmp_path / "poly_resolutions.json").write_text(
        _json.dumps({"lol-a-b": {"winner": "Team A", "ts": NOW.isoformat()}}), encoding="utf-8")
    (tmp_path / "poly_money_broad_close.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(st, "BASE", tmp_path)          # I/O in den Temp-Ordner umlenken
    monkeypatch.setattr(st, "load_emit", lambda: None)  # Emitter „tot"

    rc = st.main()
    assert rc == 0
    out = _json.loads((tmp_path / "poly_shortlist_track.json").read_text(encoding="utf-8"))
    assert not out["open"], "offener Play muss trotz totem Emitter abgerechnet sein"
    assert len(out["settled"]) == 1 and out["settled"][0]["result"] == "win"


def test_main_dead_emitter_opens_no_new_play(tmp_path, monkeypatch):
    import json as _json
    (tmp_path / "poly_shortlist_track.json").write_text('{"open":{},"settled":[]}', encoding="utf-8")
    (tmp_path / "poly_resolutions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "poly_money_broad_close.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "BASE", tmp_path)
    monkeypatch.setattr(st, "load_emit", lambda: None)
    st.main()
    out = _json.loads((tmp_path / "poly_shortlist_track.json").read_text(encoding="utf-8"))
    assert out["open"] == {} and out["settled"] == []   # nichts geöffnet, kein Crash


def test_signal_attribution_bysignal():
    # 05.08.2026 (Lucas): jedes Signal wird getaggt, durch die Abrechnung getragen und je Signal
    # aggregiert. Ein Play mit mehreren Signalen zaehlt in mehreren Buckets (bewusste Ueberlappung).
    e = _emit([{"key": "mlb-a-b", "side": "Team A", "verdict": "BET", "conv": 9, "league": "MLB",
                "price": 0.60, "public": False, "reasons": ["x"], "signals": ["sharp", "steam"]}])
    t = st.update_track({}, e, {}, {}, now=NOW)
    assert t["open"]["mlb-a-b|Team A"]["signals"] == ["sharp", "steam"]
    prev = {"open": {"mlb-a-b|Team A": {"key": "mlb-a-b", "side": "Team A", "verdict": "BET",
            "conv": 9, "league": "MLB", "entryPrice": 0.60, "lastPrice": 0.66, "public": False,
            "stake": 10.0, "firstTs": NOW.isoformat(), "signals": ["sharp", "steam"]}}}
    res = {"mlb-a-b": {"winner": "Team A", "ts": NOW.isoformat()}}
    t2 = st.update_track(prev, _emit([]), {}, res, now=NOW)
    assert t2["settled"][0]["signals"] == ["sharp", "steam"]
    bs = t2["agg"]["bySignal"]
    assert bs["sharp"]["n"] == 1 and bs["steam"]["n"] == 1 and bs["sharp"]["wins"] == 1
    assert "gvp" not in bs


# ── Stale-Cleanup (10.08.2026, Lucas): unauflösbare Plays verfallen lassen ─────────────────────
def _old_open(key, side, days, first=None):
    ts = (NOW - timedelta(days=days)).isoformat()
    return {f"{key}|{side}": {"key": key, "side": side, "verdict": "BET", "conv": 8,
            "league": "ESPORTS", "entryPrice": 0.60, "lastPrice": 0.60, "public": False,
            "stake": 10.0, "firstTs": ts}}


def test_expire_untracked_stale_play():
    # nicht im close-file (poly_money_broad trackt es nicht) + älter als UNTRACKED_TTL_D + keine Auflösung
    prev = {"open": _old_open("lol-we-al-2026-08-06", "Anyone's Legend", st.UNTRACKED_TTL_D + 1)}
    t = st.update_track(prev, _emit([]), {}, {}, now=NOW)
    assert not t["open"], "unauflösbarer Play hätte verfallen müssen"
    assert t["expired"] == 1
    assert not t["settled"], "verfallener Play darf NICHT als win/loss zählen"
    assert t["agg"]["all"]["n"] == 0


def test_keep_tracked_recent_play():
    # im close-file (getrackt) → langer Backstop, bleibt offen obwohl > UNTRACKED_TTL_D
    key = "cs2-sf2-ef1-2026-08-08"
    prev = {"open": _old_open(key, "Eternal Fire", st.UNTRACKED_TTL_D + 1)}
    close = {key: {"prices": {"Eternal Fire": 0.58}}}
    t = st.update_track(prev, _emit([]), close, {}, now=NOW)
    assert f"{key}|Eternal Fire" in t["open"], "getrackter Play darf nicht früh verfallen"
    assert t["expired"] == 0


def test_expire_backstop_for_tracked_but_ancient():
    # getrackt, aber älter als STALE_TTL_D → Backstop greift trotzdem
    key = "cs2-old-old-2026-01-01"
    prev = {"open": _old_open(key, "Team X", st.STALE_TTL_D + 1)}
    close = {key: {"prices": {"Team X": 0.5}}}
    t = st.update_track(prev, _emit([]), close, {}, now=NOW)
    assert not t["open"] and t["expired"] == 1


def test_resolution_still_wins_over_expiry():
    # hat eine Auflösung → wird abgerechnet, NICHT verfallen (auch wenn alt)
    key = "mlb-a-b"
    prev = {"open": _old_open(key, "Team A", st.UNTRACKED_TTL_D + 5)}
    res = {key: {"winner": "Team A", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), {}, res, now=NOW)
    assert not t["open"] and t["expired"] == 0
    assert t["settled"][0]["result"] == "win"


# ── Bespielbar vs. nur beobachtet (24.08.2026) ───────────────────────────────
# Lucas: „sollen wir NFL/UFC/MLB/NBA ganz rausnehmen, wenn sie die Statistik runterziehen?"
# Antwort: nein — mitschreiben kostet nichts und ist die einzige Rückfahrkarte. Stattdessen wird
# die Kennzahl getrennt und ein Wiedereintritt am CLV gemessen.
BLOCKED = ["US-Sport", "Kampfsport"]


def _row(cat, league, result="loss", pnl=-10.0, clv=0.0, stake=10.0, public=False):
    return {"cat": cat, "league": league, "result": result, "pnl": pnl, "clvPP": clv,
            "stake": stake, "conv": 7, "verdict": "BET", "public": public, "signals": []}


def test_cat_fallback_fuer_altzeilen():
    # Alt-Zeilen tragen kein `cat` — die Kategorie muss aus der Liga fallen, sonst zaehlen
    # historische MLB-Plays faelschlich als bespielbar.
    assert st._row_cat({"league": "MLB"}) == "US-Sport"
    assert st._row_cat({"league": "NBA"}) == "US-Sport"
    assert st._row_cat({"league": "UFC"}) == "Kampfsport"
    assert st._row_cat({"league": "ATP"}) == "Tennis"
    assert st._row_cat({"league": "ESPORTS"}) == "E-Sport"
    assert st._row_cat({"league": "EPL"}) == "Fußball"
    # gestempeltes cat gewinnt immer gegen die Ableitung
    assert st._row_cat({"cat": "Tennis", "league": "MLB"}) == "Tennis"


def test_aggregate_trennt_bespielbar_von_gesperrt():
    settled = [_row("Fußball", "EPL", "win", 10.0), _row("Tennis", "ATP", "win", 10.0),
               _row("US-Sport", "MLB"), _row("Kampfsport", "UFC")]
    a = st.aggregate(settled, BLOCKED)
    assert a["all"]["n"] == 4
    assert a["bettable"]["n"] == 2 and a["bettable"]["pnl"] == 20.0
    assert a["blocked"]["n"] == 2 and a["blocked"]["pnl"] == -20.0
    assert a["byCat"]["US-Sport"]["n"] == 1


def test_aggregate_ohne_sperrliste_bleibt_alles_bespielbar():
    settled = [_row("US-Sport", "MLB")]
    a = st.aggregate(settled)
    assert a["bettable"]["n"] == 1 and a["blocked"]["n"] == 0


def test_reentry_braucht_genug_plays_UND_echte_schlusskurse():
    # 40 Plays mit gutem CLV -> zu wenige Plays; eligible bleibt False.
    settled = [_row("US-Sport", "MLB", clv=1.0) for _ in range(40)]
    r = st.reentry_status(settled, BLOCKED)["US-Sport"]
    assert r["eligible"] is False and r["needN"] == 10


def test_reentry_zaehlt_clv_null_nicht_als_flach():
    # clvPP == 0 heisst „keine Schluss-Referenz erfasst", nicht „flach" (Lehre 07.08.).
    settled = [_row("US-Sport", "MLB", clv=0.0) for _ in range(60)]
    r = st.reentry_status(settled, BLOCKED)["US-Sport"]
    assert r["clvN"] == 0 and r["clvAvg"] is None and r["eligible"] is False


def test_reentry_meldet_wenn_die_sportart_dreht():
    settled = [_row("US-Sport", "MLB", clv=1.2) for _ in range(30)] + \
              [_row("US-Sport", "MLB", clv=0.0) for _ in range(30)]
    r = st.reentry_status(settled, BLOCKED)["US-Sport"]
    assert r["n"] == 60 and r["clvN"] == 30 and r["clvAvg"] == 1.2
    assert r["eligible"] is True


def test_reentry_schaut_nur_auf_die_juengsten_plays():
    # Alte Katastrophe darf eine gedrehte Sportart nicht ewig blockieren.
    alt = [_row("US-Sport", "MLB", clv=-5.0) for _ in range(300)]
    neu = [_row("US-Sport", "MLB", clv=1.0) for _ in range(60)]
    r = st.reentry_status(alt + neu, BLOCKED, window=60)["US-Sport"]
    assert r["clvAvg"] == 1.0 and r["eligible"] is True


def test_update_track_nimmt_sperrliste_aus_dem_emitter():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    emit = {"blockedCats": BLOCKED, "plays": [
        {"key": "mlb-a-b", "side": "A", "verdict": "BET", "conv": 7, "league": "MLB",
         "cat": "US-Sport", "price": 0.5}]}
    out = st.update_track({}, emit, {}, {}, now=now)
    assert out["blockedCats"] == BLOCKED
    assert out["open"]["mlb-a-b|A"]["cat"] == "US-Sport"
    assert "US-Sport" in out["reentry"]


def test_update_track_faellt_auf_letzten_stand_zurueck_wenn_emitter_leer():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    out = st.update_track({"blockedCats": BLOCKED}, {"plays": []}, {}, {}, now=now)
    assert out["blockedCats"] == BLOCKED



# ── Engine-Stempel (29.08.2026, Lucas: „soll man das mit lernen und neu gewichten") ──────────
# Der Cards-Lernloop lernt seit dem 04.07. nur auf der AKTUELLEN Engine-Version — „so vergiftet
# ein Fix den Ledger nicht". Der Poly-Track hatte das nicht: die 500 abgerechneten Plays wurden
# alle unter den alten Gewichten bewertet (Wallet-Basis 2,5 statt 1,8, Sharp-Gate n>=4 mit roher
# Quote statt n>=8 mit Wilson). Der Kalibrierer warf beide Welten in denselben Topf.
# `ev` muss deshalb vom Emit bis in die abgerechnete Zeile durchlaufen.

def test_engine_stempel_landet_am_offenen_play():
    emit = _emit([{"key": "epl-a-b", "side": "A", "verdict": "BET", "conv": 7,
                   "league": "EPL", "price": 0.55, "ev": "2026-08-29"}])
    t = st.update_track({}, emit, {}, {}, now=NOW)
    assert t["open"]["epl-a-b|A"]["ev"] == "2026-08-29"


def test_engine_stempel_ueberlebt_die_abrechnung():
    prev = {"open": {"epl-a-b|A": {"key": "epl-a-b", "side": "A", "verdict": "BET", "conv": 7,
            "league": "EPL", "entryPrice": 0.55, "lastPrice": 0.6, "stake": 10.0,
            "ev": "2026-08-29", "firstTs": NOW.isoformat()}}}
    res = {"epl-a-b": {"winner": "A", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), {}, res, now=NOW)
    assert t["settled"][0]["ev"] == "2026-08-29"


def test_alt_emit_ohne_stempel_bleibt_none():
    # Nicht raten: ein Play ohne `ev` stammt aus einer aelteren Engine und wird als solche
    # behandelt (halbes Gewicht in der Kalibrierung), nicht stillschweigend als aktuell verbucht.
    emit = _emit([{"key": "epl-c-d", "side": "C", "verdict": "BET", "conv": 7,
                   "league": "EPL", "price": 0.55}])
    t = st.update_track({}, emit, {}, {}, now=NOW)
    assert t["open"]["epl-c-d|C"]["ev"] is None


# ── Das Lern-Gedaechtnis (04.09.2026) ────────────────────────────────────────
# Lucas: „ist das eh kein hard cap sondern lernt weiter auch wenn 500 erreicht?"
# Es lernt weiter, aber nur aus den letzten SETTLED_KEEP Plays. Bei 27 abgerechneten Plays
# pro Tag waren 500 genau 18,4 Tage — und seltene Signal-Mixe (0,6-0,7/Tag) sammeln langsamer,
# als das Fenster sie verdraengt. bf+money+sharp stand mit +77,1% ROI als beste Zeile auf dem
# Lern-Board und haette die Schwelle n>=8 nie erreicht.

def test_gedaechtnis_reicht_fuer_seltene_signal_mixe():
    """Ein Mix mit 0,6 Treffern/Tag braucht ~27 Tage fuer 16 Roh-Plays. Das Fenster muss
    laenger sein als die langsamste Kombination, sonst steht sie fuer immer bei n<8."""
    plays_pro_tag = 27
    tage = st.SETTLED_KEEP / plays_pro_tag
    assert tage >= 30, ("Gedaechtnis nur %.0f Tage — seltene Mixe erreichen die Schwelle nie" % tage)


def test_gedeckelt_wird_am_ALTEN_ende():
    """settled[-KEEP:] behaelt die juengsten. Andersherum waere das Lern-Board eingefroren."""
    import inspect
    quelle = inspect.getsource(st)
    assert "settled[-SETTLED_KEEP:]" in quelle


def test_das_gedaechtnis_bleibt_ueberschreibbar(monkeypatch):
    monkeypatch.setenv("SHORTLIST_SETTLED_KEEP", "42")
    m = importlib.reload(st)
    try:
        assert m.SETTLED_KEEP == 42
    finally:
        monkeypatch.delenv("SHORTLIST_SETTLED_KEEP", raising=False)
        importlib.reload(st)


# ── 10.09.2026: Bündel-Plays kennen ihren Markt ───────────────────────────────────────────
# Lucas: „vor allem die 2 Fußball sind mmn schon alle erledigt, nur schaffst du es nicht, sie
# aufzulösen." Stimmte — und der Grund war nicht die Abrechnung, sondern dass der Play nie
# aufschrieb, WELCHEN Markt des Bündels er meint.
KEY_B = "ucl-aek-lin-2026-09-08-more-markets"


def _buendel_emit(preis=0.705):
    return _emit([{"key": KEY_B, "side": "Under", "verdict": "BET", "conv": 7,
                   "league": "SOCCER", "price": preis, "public": True}])


def _offen(cond=None, entry=0.705):
    e = {"key": KEY_B, "side": "Under", "verdict": "BET", "conv": 7, "league": "SOCCER",
         "entryPrice": entry, "lastPrice": entry, "public": True, "stake": 10.0,
         "firstTs": NOW.isoformat()}
    if cond:
        e["cond"] = cond
    return {"open": {KEY_B + "|Under": e}}


def test_der_play_stempelt_den_markt_beim_eintrag():
    close = {KEY_B: {"prices": {"Under": 0.705}, "cond": "0xAAA", "frage": "AEK vs. LASK: O/U 3.5"}}
    t = st.update_track({}, _buendel_emit(), close, {}, now=NOW)
    e = t["open"][KEY_B + "|Under"]
    assert e["cond"] == "0xAAA"
    assert e["frage"] == "AEK vs. LASK: O/U 3.5", "die Linie im Klartext gehoert an den Play"


def test_ohne_bekannten_markt_wird_kein_feld_erfunden():
    """Fehlende Information rendert als NICHTS — sonst waere „Markt unbekannt" beim Abgleich
    nicht mehr von „Markt hat keine Kennung" zu unterscheiden."""
    t = st.update_track({}, _buendel_emit(), {KEY_B: {"prices": {"Under": 0.705}}}, {}, now=NOW)
    e = t["open"][KEY_B + "|Under"]
    assert "cond" not in e and "frage" not in e


def test_gleiche_marktkennung_rechnet_ab():
    """Der Riegel vom 04.09. hat jetzt einen Schluessel: dieselbe conditionId auf beiden Seiten
    macht „Under" eindeutig."""
    res = {KEY_B: {"winner": "Under", "ts": NOW.isoformat(), "cond": "0xAAA"}}
    t = st.update_track(_offen("0xAAA"), _emit([]), {}, res, now=NOW)
    assert not t["open"], "mit belegtem Markt muss abgerechnet werden"
    assert t["settled"][0]["result"] == "win"


def test_andere_marktkennung_rechnet_NICHT_ab():
    """Der eigentliche Gegenbeweis. Die Auflösung sagt „Under" — aber zu einer anderen Linie.
    Genau so entstand der Leeds-Brentford-Fehler: 1:1 gewinnt Over 1,5 und verliert Over 2,5."""
    res = {KEY_B: {"winner": "Under", "ts": NOW.isoformat(), "cond": "0xBBB"}}
    t = st.update_track(_offen("0xAAA"), _emit([]), {}, res, now=NOW)
    assert t["open"], "ein anderer Markt darf diese Wette nicht entscheiden"
    assert not t["settled"]


def test_fehlende_kennung_auf_EINER_seite_reicht_nicht():
    """Der Altbestand in poly_resolutions.json hat keine cond. Eine unbeantwortete Frage ist
    kein Ja — solche Plays bleiben offen."""
    for play_cond, res_cond in (("0xAAA", None), (None, "0xAAA"), (None, None)):
        res = {KEY_B: {"winner": "Under", "ts": NOW.isoformat()}}
        if res_cond:
            res[KEY_B]["cond"] = res_cond
        t = st.update_track(_offen(play_cond), _emit([]), {}, res, now=NOW)
        assert t["open"], "play=%r res=%r haette offen bleiben muessen" % (play_cond, res_cond)


def test_echter_ausgang_im_buendel_bleibt_abrechenbar():
    """Gegenprobe zur Gegenprobe: gesperrt wird das MEHRDEUTIGE, nicht der Slug. Ein Bündel mit
    einem echten Teamnamen als Sieger rechnet weiter ohne cond ab."""
    prev = {"open": {KEY_B + "|AEK Athen": {"key": KEY_B, "side": "AEK Athen", "verdict": "BET",
            "conv": 7, "league": "SOCCER", "entryPrice": 0.5, "lastPrice": 0.5,
            "public": True, "stake": 10.0, "firstTs": NOW.isoformat()}}}
    res = {KEY_B: {"winner": "AEK Athen", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), {}, res, now=NOW)
    assert not t["open"] and t["settled"][0]["result"] == "win"


def test_lastPrice_wird_nicht_aus_einer_fremden_linie_gezogen():
    """`lastPrice` speist das CLV. Zieht der Close-Stand inzwischen einen ANDEREN Markt des
    Bündels, misst „Einstieg → Schluss" zwei verschiedene Linien gegeneinander."""
    close = {KEY_B: {"prices": {"Under": 0.145}, "cond": "0xBBB"}}     # andere Linie!
    t = st.update_track(_offen("0xAAA"), _emit([]), close, {}, now=NOW)
    assert t["open"][KEY_B + "|Under"]["lastPrice"] == 0.705, "der alte Preis muss stehen bleiben"
    # Und mit demselben Markt zieht er ganz normal nach:
    close2 = {KEY_B: {"prices": {"Under": 0.605}, "cond": "0xAAA"}}
    t2 = st.update_track(_offen("0xAAA"), _emit([]), close2, {}, now=NOW)
    assert t2["open"][KEY_B + "|Under"]["lastPrice"] == 0.605


# ── 10.09.2026: verfallen ist ein Ergebnis und muss dastehen ──────────────────────────────
def test_verfallene_plays_kommen_ins_buch_statt_still_zu_verschwinden():
    """`expired` war ein Zaehler JE LAUF — was gestern verfiel, stand nirgends mehr. Am 10.09.
    waren 15 von 23 offenen Plays Bündel-Märkte, die nie abrechnen konnten; sie waeren auf einen
    Schlag weggewesen, ohne dass eine Zahl im Board sich bewegt haette."""
    alt = NOW - timedelta(days=20)
    prev = {"open": {KEY_B + "|Under": {"key": KEY_B, "side": "Under", "conv": 7,
            "league": "SOCCER", "cat": "Fußball", "entryPrice": 0.705, "lastPrice": 0.705,
            "public": True, "stake": 10.0, "firstTs": alt.isoformat()}}}
    close = {KEY_B: {"prices": {}}}                       # getrackt -> langer Backstop, aber 20d > 14d
    res = {KEY_B: {"winner": "Under", "ts": NOW.isoformat()}}
    t = st.update_track(prev, _emit([]), close, res, now=NOW)
    assert not t["open"] and t["expired"] == 1
    u = t["unaufloesbar"]
    assert len(u) == 1 and u[0]["key"] == KEY_B and u[0]["public"] is True
    assert u[0]["grund"] == "Bündel ohne Marktkennung", u[0]["grund"]
    assert t["unaufloesbarAgg"]["n"] == 1 and t["unaufloesbarAgg"]["publicN"] == 1
    assert t["unaufloesbarAgg"]["nachGrund"]["Bündel ohne Marktkennung"] == 1


def test_das_buch_wird_fortgeschrieben_nicht_je_lauf_neu_gezaehlt():
    """Der Punkt der ganzen Uebung: der naechste Lauf darf die Vorgeschichte nicht wegwerfen."""
    vorher = [{"key": "alt-1", "side": "Over", "grund": "nie aufgelöst", "public": False}]
    alt = NOW - timedelta(days=20)
    prev = {"unaufloesbar": vorher,
            "open": {KEY_B + "|Under": {"key": KEY_B, "side": "Under", "entryPrice": 0.7,
                     "stake": 10.0, "public": True, "firstTs": alt.isoformat()}}}
    t = st.update_track(prev, _emit([]), {KEY_B: {"prices": {}}}, {}, now=NOW)
    assert [u["key"] for u in t["unaufloesbar"]] == ["alt-1", KEY_B]
    assert t["unaufloesbarAgg"]["n"] == 2


def test_der_grund_unterscheidet_die_faelle():
    """„12 verfallen" nennt nur einen Verlust. „12 x Bündel ohne Marktkennung" nennt eine
    Ursache, die man beheben kann — und trennt sie von „nicht getrackt"."""
    alt = (NOW - timedelta(days=20)).isoformat()
    def _lauf(key, side, close, res, cond=None):
        e = {"key": key, "side": side, "entryPrice": 0.7, "stake": 10.0, "firstTs": alt}
        if cond:
            e["cond"] = cond
        t = st.update_track({"open": {key + "|" + side: e}}, _emit([]), close, res, now=NOW)
        return t["unaufloesbar"][0]["grund"]
    assert _lauf("x-more-markets", "Under", {}, {}) == "nicht getrackt"
    assert _lauf("x-more-markets", "Under", {"x-more-markets": {}}, {}) == "nie aufgelöst"
    assert _lauf("x-more-markets", "Under", {"x-more-markets": {}},
                 {"x-more-markets": {"winner": "Under"}}) == "Bündel ohne Marktkennung"
    assert _lauf("x-more-markets", "Under", {"x-more-markets": {}},
                 {"x-more-markets": {"winner": "Under", "cond": "0xB"}},
                 cond="0xA") == "Bündel: Auflösung nennt einen anderen Markt"


# ── 10.09.2026: der Public-Block meint dasselbe wie „Bespielbar" ──────────────────────────
def test_public_zaehlt_gesperrte_sportarten_nicht_mehr_mit():
    """Gemessen am 10.09.: n=188 statt 183, ROI +5,6 % statt +6,0 %. Fuenf US-Sport-Plays, auf
    die nie gesetzt wird, zogen die Public-Bilanz nach unten — mit Geld, das nie floss."""
    def _s(cat, pnl, public=True):
        return {"key": "k" + cat + str(pnl), "side": "A", "cat": cat, "result": "win" if pnl > 0 else "loss",
                "pnl": pnl, "stake": 10.0, "public": public, "conv": 7, "clvPP": 0.0}
    settled = [_s("Fußball", 5.0), _s("Tennis", 5.0), _s("US-Sport", -10.0)]
    a = st.aggregate(settled, ["US-Sport"])
    assert a["public"]["n"] == 2, "der gesperrte Play gehoert nicht in die Public-Bilanz"
    assert a["public"]["pnl"] == 10.0
    assert a["publicBlocked"]["n"] == 1 and a["publicBlocked"]["pnl"] == -10.0
    # Gegenprobe: ohne Sperrliste bleibt alles zusammen — die Regel filtert nicht auf Verdacht.
    a2 = st.aggregate(settled, [])
    assert a2["public"]["n"] == 3 and a2["publicBlocked"]["n"] == 0


def test_die_kontrollgruppe_wird_genauso_getrennt():
    """Sonst stuenden auf den beiden Seiten des Wallet-Vergleichs zwei verschieden
    zusammengesetzte Mengen, und der Unterschied waere teils Sportart statt Wallet-Tor."""
    settled = [{"key": "a", "cat": "US-Sport", "result": "loss", "pnl": -10.0, "stake": 10.0,
                "ohneWallet": True, "conv": 7, "clvPP": 0.0},
               {"key": "b", "cat": "Tennis", "result": "win", "pnl": 5.0, "stake": 10.0,
                "ohneWallet": True, "conv": 7, "clvPP": 0.0}]
    a = st.aggregate(settled, ["US-Sport"])
    assert a["publicOhneWallet"]["n"] == 1 and a["publicOhneWallet"]["pnl"] == 5.0
