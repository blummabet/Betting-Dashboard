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
