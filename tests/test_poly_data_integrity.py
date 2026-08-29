# tests/test_poly_data_integrity.py — 02.08.2026 (Lucas' Skepsis: „wird noch mehr falsch sein,
# nur wir merkens nicht, und die 100 Guards merkens auch nicht"). Die Poly-Ausgabe-Integritäts-
# Batterie muss GENAU DANN feuern, wenn etwas still kaputt geht: toter Emitter, eingefrorenes
# Settlement, „bewiesene" Wallets die Geld verlieren, Slug-Mismatch bei den Auflösungen.
# Reine Funktionen (kein Netz, keine Datei): PolyCtx wird mit fixem now injiziert.
import importlib
from datetime import datetime, timezone, timedelta

pdi = importlib.import_module("poly_data_integrity")

NOW = datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def _by_id(res):
    return {c["id"]: c for c in res}


def _run(**kw):
    return _by_id(pdi.run_checks(pdi.PolyCtx(now=NOW, **kw)))


# ── Close-Feed-Frische ────────────────────────────────────────────────────────
def test_close_feed_fresh_green_when_recent():
    ctx = pdi.PolyCtx(now=NOW, close={"k": {"capturedAt": iso(NOW - timedelta(hours=0.5))}})
    c = pdi.check_close_feed_fresh(ctx)
    assert c["ok"] and c["id"] == "close_feed_fresh"


def test_close_feed_dead_is_error():
    ctx = pdi.PolyCtx(now=NOW, close={"k": {"capturedAt": iso(NOW - timedelta(hours=20))}})
    c = pdi.check_close_feed_fresh(ctx)
    assert not c["ok"] and c["severity"] == "error" and "steht" in c["failures"][0]


def test_close_feed_missing_timestamp_is_error():
    c = pdi.check_close_feed_fresh(pdi.PolyCtx(now=NOW, close={"k": {"prices": {}}}))
    assert not c["ok"] and c["severity"] == "error"


# ── Resolutions-Frische ───────────────────────────────────────────────────
def test_resolutions_fresh_green():
    ctx = pdi.PolyCtx(now=NOW, resolutions={"k": {"winner": "A", "ts": iso(NOW - timedelta(hours=1))}})
    assert pdi.check_resolutions_fresh(ctx)["ok"]


def test_resolutions_frozen_is_error():
    ctx = pdi.PolyCtx(now=NOW, resolutions={"k": {"winner": "A", "ts": iso(NOW - timedelta(hours=30))}})
    assert not pdi.check_resolutions_fresh(ctx)["ok"]


# ── Shortlist-Tracker schreibt (der stille jsdom-Bug) ─────────────────────────
def test_shortlist_tracker_lagging_behind_fresh_scan_fires():
    ctx = pdi.PolyCtx(
        now=NOW,
        close={"k": {"capturedAt": iso(NOW - timedelta(hours=1))}},          # Scan frisch
        shortlist={"updatedAt": iso(NOW - timedelta(hours=4)), "open": {"x": {}}, "settled": []},  # Tracker 3h hinterher
    )
    c = pdi.check_shortlist_tracker_writes(ctx)
    assert not c["ok"] and c["severity"] == "error"
    assert "tot" in c["failures"][0].lower() or "nichts" in c["failures"][0]


def test_shortlist_tracker_in_sync_is_ok():
    ctx = pdi.PolyCtx(
        now=NOW,
        close={"k": {"capturedAt": iso(NOW - timedelta(hours=1))}},
        shortlist={"updatedAt": iso(NOW - timedelta(hours=1)), "open": {"x": {}}, "settled": []},
    )
    assert pdi.check_shortlist_tracker_writes(ctx)["ok"]


def test_shortlist_tracker_zero_plays_on_fresh_feed_fires():
    ctx = pdi.PolyCtx(
        now=NOW,
        close={"k": {"capturedAt": iso(NOW - timedelta(hours=1))}},
        shortlist={"updatedAt": iso(NOW - timedelta(hours=1)), "open": {}, "settled": []},
    )
    c = pdi.check_shortlist_tracker_writes(ctx)
    assert not c["ok"] and any("0 offene" in f for f in c["failures"])


# ── Settlement lebt (Key-Mismatch: ewig offene Position) ──────────────────────
def test_settlement_stale_open_play_fires():
    ctx = pdi.PolyCtx(now=NOW, shortlist={"open": {
        "lol-a-b-2026-07-20|A": {"key": "lol-a-b-2026-07-20", "side": "A", "firstTs": iso(NOW - timedelta(days=13))},
    }})
    c = pdi.check_settlement_alive(ctx)
    assert not c["ok"] and "offen" in c["failures"][0]


def test_settlement_flags_key_mismatch_when_resolution_exists():
    # Auflösung existiert unter dem Key nicht direkt -> Position hängt, obwohl der Markt aufgelöst ist
    ctx = pdi.PolyCtx(now=NOW,
        shortlist={"open": {"lol-a-b-2026-07-20|A": {"key": "lol-a-b-2026-07-20", "side": "A"}}},
        resolutions={"lol-a-b-2026-07-20": {"winner": "A", "ts": iso(NOW)}})
    c = pdi.check_settlement_alive(ctx)
    assert not c["ok"] and "matcht aber den Key nicht" in c["failures"][0]


def test_settlement_recent_open_is_ok():
    ctx = pdi.PolyCtx(now=NOW, shortlist={"open": {
        "lol-a-b-2026-08-02|A": {"key": "lol-a-b-2026-08-02", "side": "A", "firstTs": iso(NOW)},
    }})
    assert pdi.check_settlement_alive(ctx)["ok"]


# ── Auflösungen matchen Keys (Liga-Overlap) ───────────────────────────────────
def test_overlap_flags_league_below_floor():
    close = {}
    kicked = iso(NOW - timedelta(hours=12))       # kickoff = capturedAt + htk(2h) -> 10h her > Karenz 6h
    for i in range(10):
        close[f"esports-x{i}-2026-08-01"] = {"capturedAt": kicked, "hoursToKickoff": 2, "league": "ESPORTS"}
    resolutions = {"esports-x0-2026-08-01": {"winner": "A", "ts": iso(NOW)}}   # nur 1/10 aufgelöst
    c = pdi.check_resolutions_match_open_keys(pdi.PolyCtx(now=NOW, close=close, resolutions=resolutions))
    assert not c["ok"] and any("ESPORTS" in f for f in c["failures"])


def test_overlap_ok_when_all_resolved():
    close, resolutions = {}, {}
    kicked = iso(NOW - timedelta(hours=12))
    for i in range(10):
        k = f"mlb-x{i}-2026-08-01"
        close[k] = {"capturedAt": kicked, "hoursToKickoff": 2, "league": "MLB"}
        resolutions[k] = {"winner": "A", "ts": iso(NOW)}
    assert pdi.check_resolutions_match_open_keys(pdi.PolyCtx(now=NOW, close=close, resolutions=resolutions))["ok"]


def test_overlap_ignores_not_yet_due_keys():
    # frisch erfasst, noch nicht angepfiffen -> darf nicht als „unaufgelöst" gewertet werden
    close = {f"esports-x{i}-2026-08-02": {"capturedAt": iso(NOW), "hoursToKickoff": 5, "league": "ESPORTS"} for i in range(10)}
    assert pdi.check_resolutions_match_open_keys(pdi.PolyCtx(now=NOW, close=close, resolutions={}))["ok"]


# ── „Bewiesene" Wallets wirklich profitabel ───────────────────────────────────
def test_proven_wallets_netnegative_fires_on_pnl():
    scores = {
        "0xwin": {"n": 10, "wins": 6, "usd": 5000, "pnl": 4000},
        "0xtrap1": {"n": 12, "wins": 8, "usd": 40000, "pnl": -9000},   # hohe Quote, dickes Minus
        "0xtrap2": {"n": 9, "wins": 5, "usd": 8000, "pnl": -3000},
    }
    c = pdi.check_proven_wallets_profitable(pdi.PolyCtx(now=NOW, wallet_track={"scores": scores}))
    assert not c["ok"] and "netto-NEGATIV" in c["failures"][0]


def test_proven_wallets_all_profitable_is_ok():
    scores = {"0xa": {"n": 10, "wins": 6, "pnl": 100}, "0xb": {"n": 8, "wins": 5, "pnl": 50}}
    assert pdi.check_proven_wallets_profitable(pdi.PolyCtx(now=NOW, wallet_track={"scores": scores}))["ok"]


def test_proven_wallets_flags_pnl_blind_spot():
    # viele „bewiesene" Wallets ohne pnl-Feld -> Confirmed-Loser-Gate ist für sie blind
    # 29.08.2026: n an PROVEN_MIN_TR gekoppelt statt hart 5. Die Schwelle folgt jetzt dem echten
    # Push-Gate (poly_whale_watch.MIN_TR, seit 02.08. = 8); mit festem n=5 galt hier plötzlich
    # kein Wallet mehr als „bewiesen" und der Test wurde grün, ohne etwas zu prüfen.
    n = pdi.PROVEN_MIN_TR + 2
    scores = {f"0x{i}": {"n": n, "wins": int(n * 0.6)} for i in range(10)}
    c = pdi.check_proven_wallets_profitable(pdi.PolyCtx(now=NOW, wallet_track={"scores": scores}))
    assert not c["ok"] and any("ohne P&L" in f for f in c["failures"])


# ── Genauigkeits-Backtest frisch & belastbar ──────────────────────────────────
def test_backtest_small_sample_warns():
    ctx = pdi.PolyCtx(now=NOW, broad={"generatedAt": iso(NOW), "n": 5})
    c = pdi.check_accuracy_backtest_fresh(ctx)
    assert not c["ok"] and any("geschrumpft" in f for f in c["failures"])


def test_backtest_fresh_and_large_is_ok():
    assert pdi.check_accuracy_backtest_fresh(pdi.PolyCtx(now=NOW, broad={"generatedAt": iso(NOW), "n": 200}))["ok"]


# ── Registry / Schema ─────────────────────────────────────────────────────────
def test_run_checks_shape_and_all_ids_present():
    res = pdi.run_checks(pdi.PolyCtx(now=NOW))
    ids = {c["id"] for c in res}
    for want in ("close_feed_fresh", "resolutions_fresh", "wallet_track_fresh",
                 "shortlist_tracker_writes", "settlement_alive", "resolutions_match_open_keys",
                 "proven_wallets_profitabel", "accuracy_backtest_fresh"):
        assert want in ids or want.replace("bel","ble") in ids
    for c in res:
        assert set(("id", "label", "severity", "ok", "nFail", "failures", "note")) <= set(c)


# ── 03.08.2026 (Lucas: „schau alles an … in der Status-View aufnehmen"): Geister-Märkte-Check —
#    fertige Spiele, die der Feed noch als live (resolved==null) mit Whale-Geld führt. Das ist die
#    Klasse Bug, die an mehreren Views auftauchte (Neu, einzelne Wale). ────────────────────────────
def _mkt(htk, usd=9000, resolved=None):
    return {"league": "MLB", "capturedAt": iso(NOW), "hoursToKickoff": htk,
            "resolved": resolved, "whales": [{"wallet": "0xW", "side": "A", "usd": usd}]}


def test_stale_live_markets_green_when_all_upcoming():
    close = {f"mlb-up-{i}": _mkt(2) for i in range(25)}   # alle in 2h → keine Geister
    assert pdi.check_stale_live_markets(pdi.PolyCtx(now=NOW, close=close))["ok"]


def test_stale_live_markets_fires_when_feed_full_of_ghosts():
    close = {f"mlb-done-{i}": _mkt(-10) for i in range(25)}   # alle 10h nach Anpfiff, resolved==null
    c = pdi.check_stale_live_markets(pdi.PolyCtx(now=NOW, close=close))
    assert not c["ok"] and c["severity"] == "warn"
    assert "nach Anpfiff" in c["failures"][0] and "25/25" in c["failures"][0]


def test_stale_live_markets_ignores_resolved_and_moneyless():
    close = {}
    close.update({f"res-{i}": _mkt(-10, resolved="A") for i in range(25)})     # aufgelöst → zählt nicht als live
    close.update({f"nomoney-{i}": {"league": "MLB", "capturedAt": iso(NOW),    # kein Whale-Geld → egal
                                    "hoursToKickoff": -10, "resolved": None, "whales": []} for i in range(25)})
    assert pdi.check_stale_live_markets(pdi.PolyCtx(now=NOW, close=close))["ok"]


def test_stale_live_markets_small_sample_stays_green():
    close = {f"mlb-done-{i}": _mkt(-10) for i in range(5)}   # < GHOST_MIN_N → nicht bewerten
    assert pdi.check_stale_live_markets(pdi.PolyCtx(now=NOW, close=close))["ok"]


# ── Auflösung landet im Close-Eintrag (24.08.2026) ────────────────────────────
def _close_unstamped(n):
    return {f"k{i}": {"capturedAt": iso(NOW), "hoursToKickoff": 1.0} for i in range(n)}


def test_close_resolution_stamped_green_when_stamped():
    close = {"k0": {"capturedAt": iso(NOW), "hoursToKickoff": 1.0, "resolved": True}}
    c = pdi.check_close_resolution_stamped(
        pdi.PolyCtx(now=NOW, close=close, resolutions={"k0": {"winner": "A"}}))
    assert c["ok"] and c["id"] == "close_resolution_stamped"


def test_close_resolution_stamped_fires_when_ledger_knows_but_entry_does_not():
    n = pdi.STAMP_MISS_MAX + 5
    close = _close_unstamped(n)
    res = {k: {"winner": "A"} for k in close}
    c = pdi.check_close_resolution_stamped(pdi.PolyCtx(now=NOW, close=close, resolutions=res))
    assert not c["ok"] and str(n) in c["failures"][0]


def test_close_resolution_stamped_tolerates_few_stragglers():
    close = _close_unstamped(pdi.STAMP_MISS_MAX)
    res = {k: {"winner": "A"} for k in close}
    assert pdi.check_close_resolution_stamped(pdi.PolyCtx(now=NOW, close=close, resolutions=res))["ok"]


def test_close_resolution_stamped_ignores_entries_without_ledger_entry():
    close = _close_unstamped(pdi.STAMP_MISS_MAX + 5)
    assert pdi.check_close_resolution_stamped(pdi.PolyCtx(now=NOW, close=close, resolutions={}))["ok"]


# ── Direkt gesetzte Wetten rechnen ab (24.08.2026) ────────────────────────────
# Echtes Geld: ein Bet aus dem „Heute"-Tab hat kein Fixture und wird nur ueber den Poly-Slug
# aufgeloest. Haengt er, fehlt er still in P&L UND CLV — der Guard ist die einzige Sichtbarkeit.
def test_direct_bets_settling_green_when_fresh():
    ctx = pdi.PolyCtx(now=NOW, direct_bets={"open": [
        {"key": "cs2-a-b", "side": "Team A", "ageDays": 0.5, "stake": 10}]})
    c = pdi.check_direct_bets_settling(ctx)
    assert c["ok"] and c["id"] == "direct_bets_settling"


def test_direct_bets_settling_fires_on_stuck_bet():
    ctx = pdi.PolyCtx(now=NOW, direct_bets={"open": [
        {"key": "cs2-a-b", "side": "Team A", "ageDays": pdi.DIRECT_OPEN_MAX_D + 2, "stake": 25}]})
    c = pdi.check_direct_bets_settling(ctx)
    assert not c["ok"]
    assert "cs2-a-b" in c["failures"][0] and "Team A" in c["failures"][0]


def test_direct_bets_settling_lists_at_most_five_plus_rest():
    open_ = [{"key": f"k{i}", "side": "A", "ageDays": 9.0, "stake": 10} for i in range(8)]
    c = pdi.check_direct_bets_settling(pdi.PolyCtx(now=NOW, direct_bets={"open": open_}))
    assert not c["ok"] and len(c["failures"]) == 6 and "3 weitere" in c["failures"][-1]


def test_direct_bets_settling_green_without_file():
    # Feature frisch / noch nie gesetzt -> kein Alarm.
    assert pdi.check_direct_bets_settling(pdi.PolyCtx(now=NOW))["ok"]


def test_direct_bets_settling_in_registry():
    assert "direct_bets_settling" in {c["id"] for c in pdi.run_checks(pdi.PolyCtx(now=NOW))}

