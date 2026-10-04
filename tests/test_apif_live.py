"""API-Football-Anreicherung fuer den HZ-0:0-Finder (04.10.2026). Ohne Netz: get() ist injiziert.
Zuordnung bewusst eng — ein falsch zugeordnetes Spiel waere schlimmer als keine Statistik."""
import apif_live as A
import hz_finder as H

FUND = {"matchId": "9", "home": "Den Bosch", "away": "FC Dordrecht", "kickoff": "2026-10-04T14:00:00Z",
        "phase": "HZ", "gruppen": ["tore"], "vor": {"over25": 1.36}, "quoten": {"over05": 1.18},
        "league": "Dutch Eerste Divisie", "country": "NL"}
LIVE = {"response": [
    {"fixture": {"id": 111, "date": "2026-10-04T14:00:00+00:00"}, "league": {"name": "Eerste Divisie"},
     "teams": {"home": {"id": 1, "name": "FC Den Bosch"}, "away": {"id": 2, "name": "Dordrecht"}},
     "goals": {"home": 0, "away": 0}},
    {"fixture": {"id": 222, "date": "2026-10-04T14:00:00+00:00"}, "league": {"name": "X"},
     "teams": {"home": {"id": 3, "name": "Ajax"}, "away": {"id": 4, "name": "PSV"}},
     "goals": {"home": 0, "away": 0}}]}
STAT = {"response": [
    {"team": {"id": 1}, "statistics": [{"type": "Shots on Goal", "value": 5}, {"type": "Total Shots", "value": 12},
                                        {"type": "Ball Possession", "value": "64%"}, {"type": "expected_goals", "value": "1.10"},
                                        {"type": "Corner Kicks", "value": 6}]},
    {"team": {"id": 2}, "statistics": [{"type": "Shots on Goal", "value": 1}, {"type": "Total Shots", "value": 4},
                                        {"type": "Ball Possession", "value": "36%"}, {"type": "expected_goals", "value": "0.20"},
                                        {"type": "Corner Kicks", "value": 2}]}]}


def _fx(d, h, a, hid, ft, ht):
    return {"fixture": {"date": d + "T18:00:00+00:00"}, "teams": {"home": {"id": hid}, "away": {"id": 99}},
            "score": {"fulltime": {"home": ft[0], "away": ft[1]}, "halftime": {"home": ht[0], "away": ht[1]}}}


SERIE = {"response": [_fx("2026-09-28", "x", "y", 1, (2, 1), (0, 0)), _fx("2026-09-21", "x", "y", 1, (0, 0), (0, 0)),
                      _fx("2026-09-14", "x", "y", 99, (1, 3), (1, 1))]}


def fake(pfad):
    if pfad.startswith("/fixtures?live"):
        return LIVE
    if pfad.startswith("/fixtures/statistics"):
        return STAT
    return SERIE


def test_zuordnung_eng_und_eindeutig():
    assert A.zuordnen(FUND, LIVE["response"])["fixture"]["id"] == 111
    spaet = dict(FUND, kickoff="2026-10-04T15:00:00Z")
    assert A.zuordnen(spaet, LIVE["response"]) is None, "Anpfiff 60 Min daneben = anderes Spiel"
    doppelt = LIVE["response"] + [dict(LIVE["response"][0], fixture={"id": 333, "date": "2026-10-04T14:00:00+00:00"})]
    assert A.zuordnen(FUND, doppelt) is None, "zwei Kandidaten = nicht raten"


def test_anreichern_statistik_und_rueckwirkende_serie():
    f = dict(FUND)
    z = A.anreichern([f], get=fake)
    assert z == {"funde": 1, "gematcht": 1, "mitStatistik": 1, "mitSerie": 1, "aufrufe": 4}
    st = f["apif"]["statistik"]
    assert st["heim"]["aufsTor"] == 5 and st["gast"]["ballbesitz"] == 36.0 and st["heim"]["xg"] == 1.1
    s = f["apif"]["serie"]["heim"]
    assert s["n"] == 3 and s["over25"] == 2 and s["ht00"] == 2 and s["torIn2hz"] == 2 and s["form"] == "SUS"


def test_ohne_live_liste_nichts_und_deckel():
    assert A.anreichern([dict(FUND)], get=lambda p: None)["gematcht"] == 0
    z = A.anreichern([dict(FUND), dict(FUND)], get=fake, max_aufrufe=3)
    assert z["aufrufe"] <= 3


def test_nachricht_zeigt_statistik_und_laengere_serie():
    f = dict(FUND)
    A.anreichern([f], get=fake)
    t = H.nachricht([f])
    assert "📊 <b>1. HZ:</b> aufs Tor 5–1 · Schüsse 12–4 · Ecken 6–2 · Ballbesitz 64–36 % · xG 1.10–0.20" in t
    assert "Tor in 2. HZ 2/3" in t
