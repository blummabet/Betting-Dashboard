# tests/test_build_betfair_overview.py — 02.08.2026 (Lucas): der Übersicht-Sidecar muss die zwei
# history-abhängigen Signale korrekt & radar-treu vorrechnen: Vor-Anpfiff-Steam (Implied-Prob-pp,
# erster→letzter Snapshot, live/gestartet ausgeschlossen) und frischer Zufluss (€, letzte zwei Snaps).
import importlib
from datetime import datetime, timezone, timedelta

bo = importlib.import_module("build_betfair_overview")
NOW = datetime(2026, 8, 2, 13, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


# ── implied_move (spiegelt Radar moveOf) ──────────────────────────────────────
def test_move_quote_falls_is_positive_pp():
    # Heim-Quote fällt 4.0 -> 2.0: implied 25% -> 50% = +25pp (Geld drauf)
    mv = bo.implied_move({"hw": 4.0, "dr": 4.0, "aw": 4.0}, {"hw": 2.0, "dr": 4.0, "aw": 4.0})
    assert mv["side"] == "hw" and mv["pp"] > 0 and abs(mv["pp"] - 25.0) < 0.1


def test_move_quote_rises_is_negative_pp():
    mv = bo.implied_move({"hw": 2.0}, {"hw": 4.0})
    assert mv["side"] == "hw" and mv["pp"] < 0


def test_move_below_threshold_is_none():
    assert bo.implied_move({"hw": 2.00}, {"hw": 2.01}) is None   # < 1.5pp


def test_move_skips_placeholder_none_side():
    # hw ist Platzhalter (None) im ersten Snap -> Seite übersprungen, aw zählt
    mv = bo.implied_move({"hw": None, "aw": 5.0}, {"hw": 1.5, "aw": 2.5})
    assert mv["side"] == "aw"


def test_move_picks_strongest_side():
    mv = bo.implied_move({"hw": 3.0, "aw": 3.0}, {"hw": 2.7, "aw": 1.8})
    assert mv["side"] == "aw"   # aw bewegt sich stärker


# ── _is_upcoming ──────────────────────────────────────────────────────────────
def test_upcoming_true_for_future_kickoff_no_clock():
    m = {"kickoff": iso(NOW + timedelta(hours=2)), "liveInfo": {}}
    assert bo._is_upcoming(m, NOW) is True


def test_upcoming_false_when_live_clock_running():
    m = {"kickoff": iso(NOW - timedelta(minutes=10)), "liveInfo": {"time": 23, "finished": False}}
    assert bo._is_upcoming(m, NOW) is False


def test_upcoming_false_when_started_no_clock():
    m = {"kickoff": iso(NOW - timedelta(hours=1)), "liveInfo": {}}
    assert bo._is_upcoming(m, NOW) is False


# ── steam_list ────────────────────────────────────────────────────────────────
def _match(mid, home, away, ko, mo_now, live=None):
    return {"matchId": mid, "home": home, "away": away, "country": "GB", "league": "L",
            "kickoff": ko, "liveInfo": live or {}, "mo": mo_now,
            "markets": {"Match Odds": {"runners": [{"name": home, "odd": mo_now.get("hw"), "vol": 9000},
                                                   {"name": away, "odd": mo_now.get("aw"), "vol": 1000}]}}}


def test_steam_list_ranks_and_excludes_live():
    ko = iso(NOW + timedelta(hours=2))
    prices = {"matches": [
        _match(1, "Genk", "Twente", ko, {"hw": 2.4, "aw": 3.0}),
        _match(2, "Live FC", "X", iso(NOW - timedelta(minutes=5)), {"hw": 2.0, "aw": 3.0},
               live={"time": 30, "finished": False}),   # live -> raus
    ]}
    hist = {
        "1": [{"mo": {"hw": 1.8, "aw": 3.0}}, {"mo": {"hw": 2.4, "aw": 3.0}}],   # Genk driftet (−pp)
        "2": [{"mo": {"hw": 4.0, "aw": 3.0}}, {"mo": {"hw": 2.0, "aw": 3.0}}],
    }
    out = bo.steam_list(prices, hist, NOW)
    assert len(out) == 1 and out[0]["home"] == "Genk"
    assert out[0]["side"] == "hw" and out[0]["pp"] < 0 and out[0]["sideName"] == "Genk"


def test_steam_list_needs_two_snapshots():
    ko = iso(NOW + timedelta(hours=1))
    prices = {"matches": [_match(1, "A", "B", ko, {"hw": 2.0, "aw": 2.0})]}
    assert bo.steam_list(prices, {"1": [{"mo": {"hw": 2.0}}]}, NOW) == []


# ── flow_list ────────────────────────────────────────────────────────────────
def test_flow_list_ranks_by_inflow_and_filters_small():
    prices = {"matches": [
        _match(1, "Brondby", "Viborg", iso(NOW + timedelta(hours=1)), {"hw": 2.2, "aw": 3.0}),
        _match(2, "Small", "Game", iso(NOW + timedelta(hours=1)), {"hw": 2.0, "aw": 2.0}),
    ]}
    hist = {
        "1": [{"totalVol": 100000}, {"totalVol": 161989}],   # +61989
        "2": [{"totalVol": 10000}, {"totalVol": 11000}],     # +1000 < 2000 -> raus
    }
    out = bo.flow_list(prices, hist)
    assert len(out) == 1 and out[0]["home"] == "Brondby"
    assert out[0]["deltaEur"] == 61989 and out[0]["nowEur"] == 161989
    assert out[0]["sideName"] == "Brondby"   # Lead des größten Marktes


def test_build_shape():
    prices = {"matches": [_match(1, "A", "B", iso(NOW + timedelta(hours=1)), {"hw": 2.0, "aw": 3.0})]}
    hist = {"1": [{"mo": {"hw": 4.0, "aw": 3.0}, "totalVol": 1000},
                  {"mo": {"hw": 2.0, "aw": 3.0}, "totalVol": 9000}]}
    d = bo.build(prices, hist, NOW)
    assert set(("_meta", "generatedAt", "steam", "flow")) <= set(d)
    assert d["steam"] and d["flow"]   # beide Signale feuern
