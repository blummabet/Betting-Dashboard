#!/usr/bin/env python3
"""test_betwatch.py — reiner Kern von fetch_betfair_betwatch (28.07.2026, Lucas).
Fixtures nachgebaut aus den ECHTEN Betwatch-Antworten (verifiziert im Browser)."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_betfair_betwatch as B

T0 = datetime(2026, 7, 28, 20, 0, tzinfo=timezone.utc)

# echte Event-Listen-Form
EVENTS = [
    {"match_id": 35785202, "teams": {"v1": "Augsburg", "v2": "Schalke 04"},
     "league": "German Bundesliga", "country": "DE", "kickoff": "2026-08-30T15:30:00Z", "live_info": {}},
    {"match_id": 35872941, "teams": {"v1": "CD Los Chankas", "v2": "Comerciantes Unidos"},
     "league": "Peruvian Primera Division", "country": "PE", "kickoff": "2026-07-29T02:00:00Z", "live_info": {}},
    {"match_id": 99, "teams": {"v1": "Nigeria (W)", "v2": "Malawi (W)"},
     "league": "CAF Ladies", "country": "International", "kickoff": "2026-07-28T19:00:00Z",
     "live_info": {"time": 9, "is_ht": False, "goal_v1": 0, "goal_v2": 0, "finished": False}},
]

# echte event/{id}-Form: markets[] mit name, average_volume, runners[{name, odd, volume}]
EVENT_DETAIL = {
    "match_id": 35785202, "teams": {"v1": "Augsburg", "v2": "Schalke 04"},
    "league_id": 59, "league": "German Bundesliga", "country": "DE",
    "kickoff": "2026-08-30T15:30:00Z", "live_info": {},
    # Markt-Geld = Summe der Runner-Volumina (average_volume ist bewusst „falsch groß" gelassen,
    # damit der Test fixiert, dass es NICHT benutzt wird).
    "markets": [
        {"market_id": 1, "name": "Match Odds", "average_volume": 1102159, "runners": [
            {"runner_id": 1, "name": "Augsburg", "odd": 2.0, "volume": 8000},
            {"runner_id": 2, "name": "The Draw", "odd": 3.5, "volume": 1500},
            {"runner_id": 3, "name": "Schalke 04", "odd": 4.0, "volume": 2500}]},   # Σ = 12000
        {"market_id": 2, "name": "Over/Under 2.5 Goals", "average_volume": 244387, "runners": [
            {"name": "Under 2.5 Goals", "odd": 2.1, "volume": 1500},
            {"name": "Over 2.5 Goals", "odd": 1.8, "volume": 3000}]},               # Σ = 4500
        {"market_id": 3, "name": "First Half Goals 1.5", "average_volume": 999999, "runners": [
            {"name": "Under 1.5 Goals", "odd": 1.7, "volume": 1200},
            {"name": "Over 1.5 Goals", "odd": 2.2, "volume": 800}]},                # Σ = 2000
        {"market_id": 4, "name": "Half Time", "average_volume": 777777, "runners": [
            {"name": "Augsburg", "odd": 2.6, "volume": 4000},
            {"name": "The Draw", "odd": 2.1, "volume": 2000},
            {"name": "Schalke 04", "odd": 4.5, "volume": 2000}]},                   # Σ = 8000
        {"market_id": 5, "name": "Both teams to Score?", "average_volume": 555555, "runners": [
            {"name": "Yes", "odd": 1.9, "volume": 6000},
            {"name": "No", "odd": 2.0, "volume": 5000}]},                           # Σ = 11000
    ],
}


def test_parse_events():
    p = B.parse_events(EVENTS)
    assert len(p) == 3
    assert p[0]["home"] == "Augsburg" and p[0]["away"] == "Schalke 04" and p[0]["live"] is False
    assert p[2]["live"] is True   # live_info gesetzt → live


def test_devig_1x2():
    f = B.devig_1x2(2.0, 3.5, 4.0)
    assert f and abs(f["home"] + f["draw"] + f["away"] - 1.0) < 1e-3
    assert f["home"] > f["away"]          # Favorit hat höhere Prob
    assert B.devig_1x2(None, 3.5, 4.0) is None
    assert B.devig_1x2(1.01, 1.01, 1.01) is None   # Platzhalter (Overround ~2.97) raus


def test_build_snapshot_haelt_alle_maerkte_inkl_HT():
    s = B.build_snapshot(EVENT_DETAIL, now=T0)
    assert s["matchId"] == 35785202 and s["league"] == "German Bundesliga" and s["leagueId"] == 59
    # Markt-Geld = SUMME der Runner-Volumina, NICHT average_volume (29.07.2026)
    assert s["mo"]["hw"] == 2.0 and s["mo"]["aw"] == 4.0 and s["mo"]["vol"] == 12000
    assert s["mo"]["fair"] and s["mo"]["fair"]["home"] > s["mo"]["fair"]["away"]
    # HT-Märkte müssen erhalten bleiben (Produkt B)
    assert "Half Time" in s["markets"]
    assert "First Half Goals 1.5" in s["markets"]
    assert s["markets"]["Half Time"]["vol"] == 8000            # 4000+2000+2000, nicht average_volume
    assert s["markets"]["Over/Under 2.5 Goals"]["vol"] == 4500  # 1500+3000
    # Runner sind eine geordnete Liste MIT Einzel-Volumen (Geld-Verteilung fürs Dashboard)
    ou = s["markets"]["Over/Under 2.5 Goals"]["runners"]
    assert isinstance(ou, list)
    over = next(r for r in ou if r["name"] == "Over 2.5 Goals")
    assert over["odd"] == 1.8 and over["vol"] == 3000
    mo_r = s["markets"]["Match Odds"]["runners"]
    assert {r["name"] for r in mo_r} == {"Augsburg", "The Draw", "Schalke 04"}
    assert next(r for r in mo_r if r["name"] == "Augsburg")["vol"] == 8000
    # Gesamt-Volumen = Summe aller Markt-Volumina (= Summe aller Runner)
    assert s["totalVol"] == 12000 + 4500 + 2000 + 8000 + 11000


def test_select_ids_live_zuerst_dann_fenster_dann_cap():
    parsed = B.parse_events(EVENTS)
    ids = B.select_ids(parsed, now=T0, window_h=26, cap=150)
    assert ids[0] == 99, "live-Match muss zuerst kommen"
    assert 35872941 in ids, "Peru (Anpfiff in <26h) ist im Fenster"
    assert 35785202 not in ids, "Bundesliga (30 Tage draußen) faellt aus dem Fenster"
    # Cap greift
    assert len(B.select_ids(parsed, now=T0, window_h=999, cap=1)) == 1


def test_select_ids_top5_prioritized_beyond_standard_window():
    # T0 = 28.07. 20:00. Standard 26h, Prio 72h. Top-5 in ~46h (außerhalb 26h, innerhalb 72h) → drin;
    # obskure Liga in ~46h (außerhalb 26h, nicht-prio) → draußen.
    evs = [
        {"match_id": 501, "teams": {"v1": "Bayern", "v2": "Dortmund"}, "league": "German Bundesliga",
         "country": "DE", "kickoff": "2026-07-30T18:00:00Z", "live_info": {}},
        {"match_id": 502, "teams": {"v1": "A", "v2": "B"}, "league": "Icelandic 2 Deild",
         "country": "IS", "kickoff": "2026-07-30T18:00:00Z", "live_info": {}},
    ]
    parsed = B.parse_events(evs)
    ids = B.select_ids(parsed, now=T0, window_h=26, prio_window_h=72, cap=150)
    assert 501 in ids, "Top-5 im 72h-Prio-Fenster wird erfasst"
    assert 502 not in ids, "Nicht-Prio-Liga außerhalb 26h bleibt draußen"


def test_history_anhaengen_und_prunen():
    s = B.build_snapshot(EVENT_DETAIL, now=T0)
    h = B.append_history({}, s, now=T0)
    assert h["35785202"][0]["totalVol"] == s["totalVol"]
    h = B.append_history(h, s, now=T0 + timedelta(hours=1))
    assert len(h["35785202"]) == 2
    # mkv: Markt-Volumina je Snapshot (für „frisches Geld"-Zufluss)
    assert h["35785202"][-1]["mkv"]["Match Odds"] == 12000    # Runner-Summe, nicht average_volume
    assert h["35785202"][-1]["mkv"]["Half Time"] == 8000
    # nur die letzten 2 Punkte tragen mkv (Platzspar-Trim)
    h = B.append_history(h, s, now=T0 + timedelta(hours=2))
    assert "mkv" not in h["35785202"][0]
    assert "mkv" in h["35785202"][-1] and "mkv" in h["35785202"][-2]
    # alter Eintrag (100h) wird geprunt
    old = {"35785202": [{"ts": (T0 - timedelta(hours=100)).isoformat(), "totalVol": 1}]}
    assert "35785202" not in B.prune_history(old, now=T0)


def test_history_speichert_live_minute():
    """09.08.2026 (Lucas): Live-Minute (liveInfo.time) im History-Punkt → Zufluss-Fenster als Spielminuten."""
    live_ev = dict(EVENT_DETAIL)
    live_ev["live_info"] = {"time": 63, "is_ht": False, "finished": False}
    s = B.build_snapshot(live_ev, now=T0)
    h = B.append_history({}, s, now=T0)
    assert h["35785202"][-1]["min"] == 63
    # Vor-Anpfiff (leeres live_info) → min ist None, nicht KeyError
    s0 = B.build_snapshot(EVENT_DETAIL, now=T0)
    h0 = B.append_history({}, s0, now=T0)
    assert h0["35785202"][-1]["min"] is None


def test_history_speichert_score_und_karten():
    """10.08.2026 (Lucas): echter Spielstand + rote Karten im History-Punkt → praezise Ereignis-Erkennung."""
    ev = dict(EVENT_DETAIL)
    ev["live_info"] = {"time": 70, "goal_v1": 2, "goal_v2": 1, "red_v1": 0, "red_v2": 1, "finished": False}
    h = B.append_history({}, B.build_snapshot(ev, now=T0), now=T0)
    p = h["35785202"][-1]
    assert p["sc"] == [2, 1]
    assert p["rc"] == [0, 1]
    # Vor-Anpfiff / kein Score → sc und rc None (kein KeyError)
    h0 = B.append_history({}, B.build_snapshot(EVENT_DETAIL, now=T0), now=T0)
    assert h0["35785202"][-1]["sc"] is None and h0["35785202"][-1]["rc"] is None


def test_fetch_results_guards():
    """10.08.2026 (Lucas): der Ergebnis-Endpoint-Helfer ist defensiv — ohne IDs / ohne KEY leeres Dict,
    damit die Aufrufer (track_record/public_eval) auf die bestehende finished/vanish-Logik zurueckfallen."""
    assert B.fetch_results([]) == {}            # keine IDs
    assert B.fetch_results(["abc"]) == {}       # keine numerischen IDs
    assert B.fetch_results([1, 2, 3]) == {}     # KEY im Testlauf leer → kein Netz-Call


def test_dedup_matchups_keeps_volume_winner():
    """Betwatch-Doppel-Listing (ein Spiel, zwei matchIds) → nur der Volumen-Sieger bleibt."""
    snaps = [
        {"matchId": "1", "home": "FC Cincinnati", "away": "San Jose",
         "kickoff": "2026-08-01T23:30:00Z", "totalVol": 29120},
        {"matchId": "2", "home": "FC Cincinnati", "away": "San Jose",
         "kickoff": "2026-08-01T23:30:00Z", "totalVol": 0},
        {"matchId": "3", "home": "Real Madrid", "away": "Fiorentina",
         "kickoff": "2026-08-01T20:00:00Z", "totalVol": 298000},
    ]
    out = B.dedup_matchups(snaps)
    assert len(out) == 2
    assert out[0]["matchId"] == "1"          # Volumen-Sieger behalten
    assert [o["matchId"] for o in out] == ["1", "3"]  # Reihenfolge erhalten


def test_dedup_matchups_rematch_not_merged():
    """Gleiche Paarung an VERSCHIEDENEN Tagen (Rückspiel) darf NICHT zusammengeführt werden."""
    snaps = [
        {"matchId": "a", "home": "X", "away": "Y", "kickoff": "2026-08-01T20:00:00Z", "totalVol": 10},
        {"matchId": "b", "home": "X", "away": "Y", "kickoff": "2026-08-08T20:00:00Z", "totalVol": 20},
    ]
    assert len(B.dedup_matchups(snaps)) == 2


if __name__ == "__main__":
    import types
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"\n{len(fns)} tests passed")
