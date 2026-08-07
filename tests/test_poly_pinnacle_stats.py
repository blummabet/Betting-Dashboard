# tests/test_poly_pinnacle_stats.py — 07.08.2026 (Lucas): Phase-2 Lag-Backtest auf den breiten
# Scan-Daten. Einstieg wenn Pinnacle sich bewegt hat UND Poly hinterherhinkt; Ausstieg bei Poly-
# Konvergenz oder Zwangs-Close am letzten Vor-Anpfiff-Snap. Nur abgeschlossene Spiele; Ledger dedupt.
import importlib
from datetime import datetime, timezone, timedelta

st = importlib.import_module("poly_pinnacle_stats")
NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def _game(kickoff, snaps, league="MLS"):
    return {"league": league, "home": "H", "away": "A", "kickoff": iso(kickoff), "snaps": snaps}


def test_entry_bei_move_und_lag_exit_bei_konvergenz():
    ko = NOW
    snaps = [
        {"ts": iso(ko - timedelta(hours=3)), "pinn": [0.50, 0.30, 0.20], "poly": [0.50, 0.30, 0.20]},
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.56, 0.27, 0.17], "poly": [0.50, 0.30, 0.20]},  # ENTER home @.50 target .56
        {"ts": iso(ko - timedelta(hours=1)), "pinn": [0.56, 0.27, 0.17], "poly": [0.555, 0.28, 0.165]},  # konvergiert -> EXIT
    ]
    tr = st.backtest_game(_game(ko, snaps), min_snaps=2)
    assert len(tr) == 1
    t = tr[0]
    assert t["side"] == "home" and t["exitReason"] == "converged"
    assert t["entryPoly"] == 0.50 and t["exitPoly"] == 0.555
    assert abs(t["gainPP"] - 5.5) < 0.01


def test_kein_convergence_zwangs_close():
    ko = NOW
    snaps = [
        {"ts": iso(ko - timedelta(hours=3)), "pinn": [0.50, 0.30, 0.20], "poly": [0.50, 0.30, 0.20]},
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.56, 0.27, 0.17], "poly": [0.50, 0.30, 0.20]},  # ENTER
        {"ts": iso(ko - timedelta(hours=1)), "pinn": [0.56, 0.27, 0.17], "poly": [0.51, 0.30, 0.19]},   # nicht konvergiert
    ]
    tr = st.backtest_game(_game(ko, snaps), min_snaps=2)
    assert len(tr) == 1 and tr[0]["exitReason"] == "close"
    assert abs(tr[0]["gainPP"] - 1.0) < 0.01


def test_kein_entry_ohne_move():
    ko = NOW
    snaps = [
        {"ts": iso(ko - timedelta(hours=3)), "pinn": [0.50, 0.30, 0.20], "poly": [0.48, 0.30, 0.22]},
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.505, 0.30, 0.195], "poly": [0.48, 0.30, 0.22]},  # move nur +0.5pp
        {"ts": iso(ko - timedelta(hours=1)), "pinn": [0.505, 0.30, 0.195], "poly": [0.50, 0.30, 0.20]},
    ]
    assert st.backtest_game(_game(ko, snaps), min_snaps=2) == []


def test_kein_entry_wenn_poly_nicht_hinterherhinkt():
    ko = NOW
    snaps = [
        {"ts": iso(ko - timedelta(hours=3)), "pinn": [0.50, 0.30, 0.20], "poly": [0.50, 0.30, 0.20]},
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.56, 0.27, 0.17], "poly": [0.56, 0.27, 0.17]},  # Poly gleich mitgezogen -> kein Lag
        {"ts": iso(ko - timedelta(hours=1)), "pinn": [0.56, 0.27, 0.17], "poly": [0.56, 0.27, 0.17]},
    ]
    assert st.backtest_game(_game(ko, snaps), min_snaps=2) == []


def test_run_filtert_kommende_spiele():
    ko_past = NOW - timedelta(hours=1)
    ko_future = NOW + timedelta(hours=5)
    snaps = lambda ko: [
        {"ts": iso(ko - timedelta(hours=3)), "pinn": [0.50, 0.30, 0.20], "poly": [0.50, 0.30, 0.20]},
        {"ts": iso(ko - timedelta(hours=2)), "pinn": [0.56, 0.27, 0.17], "poly": [0.50, 0.30, 0.20]},
        {"ts": iso(ko - timedelta(hours=1)), "pinn": [0.56, 0.27, 0.17], "poly": [0.555, 0.28, 0.165]},
    ]
    store = {"games": {"past": _game(ko_past, snaps(ko_past)),
                       "future": _game(ko_future, snaps(ko_future))}}
    res = st.run(store, now=NOW, min_snaps=2)
    assert res["overall"]["n"] == 1   # nur das abgeschlossene Spiel


def test_merge_ledger_dedupt():
    t = {"home": "H", "away": "A", "side": "home", "entryTs": "x", "gainPP": 1, "roiPct": 1, "holdH": 1, "league": "MLS"}
    led, added = st.merge_ledger([], [t, dict(t)])
    assert added == 1 and len(led) == 1
    led2, added2 = st.merge_ledger(led, [t])
    assert added2 == 0 and len(led2) == 1
