"""HZ-0:0-Finder + Team-Archiv (04.10.2026, Register hz-null-null).

Fehlerklasse, gegen die das Buch gebaut ist: am Endstand gesucht, am Signalzeitpunkt gefeuert.
Deshalb wird zur Quote DER PAUSE gebucht, nie zu einer spaeteren."""
import json
from datetime import datetime, timedelta, timezone

import hz_finder as H
import team_archiv as T

JETZT = datetime(2026, 10, 4, 15, tzinfo=timezone.utc)


def spiel(li=None, o05=1.32, o15=2.3, heim=1.9, mid="9"):
    return {"matchId": mid, "home": "Ararat", "away": "Noah", "league": "Armenian Premier League",
            "kickoff": "2026-10-04T14:00:00Z",
            "liveInfo": li if li is not None else {"is_ht": True, "time": 45, "goal_v1": 0, "goal_v2": 0},
            "markets": {"Over/Under 0.5 Goals": {"runners": [{"name": "Under 0.5 Goals", "odd": 4.1},
                                                             {"name": "Over 0.5 Goals", "odd": o05}]},
                        "Over/Under 1.5 Goals": {"runners": [{"name": "Over 1.5 Goals", "odd": o15}]},
                        "Match Odds": {"runners": [{"name": "Ararat", "odd": heim}]}}}


PEND_TORE = {"signals": {"Over/Under 2.5 Goals": {"fav": "OVER", "odd": 1.62}}}
HIST_HEIM = [{"ts": "2026-10-04T13:50", "min": None, "mo": {"hw": 1.48}},
             {"ts": "2026-10-04T14:20", "min": 20, "mo": {"hw": 1.70}}]


def test_tore_und_heim_erkannt_mit_pausenquoten():
    f = H.kandidat(spiel(), PEND_TORE, HIST_HEIM)
    assert f["gruppen"] == ["tore", "heim"] and f["vor"] == {"over25": 1.62, "heim": 1.48}
    assert f["quoten"] == {"over05": 1.32, "over15": 2.3, "heim": 1.9}, "Quote der PAUSE, nicht die Vorspielquote"


def test_nur_bei_null_null_und_nur_mit_erwartung():
    assert H.kandidat(spiel({"is_ht": True, "goal_v1": 1, "goal_v2": 0}), PEND_TORE, HIST_HEIM) is None
    assert H.kandidat(spiel({"time": 30, "goal_v1": 0, "goal_v2": 0}), PEND_TORE, HIST_HEIM) is None
    assert H.kandidat(spiel(), {"signals": {"Over/Under 2.5 Goals": {"fav": "OVER", "odd": 1.9}}}, []) is None
    assert H.kandidat(spiel(), {"signals": {"Over/Under 2.5 Goals": {"fav": "UNDER", "odd": 1.5}}}, []) is None


def test_spaeter_fund_in_zweiter_haelfte_markiert():
    f = H.kandidat(spiel({"time": 49, "goal_v1": 0, "goal_v2": 0}), PEND_TORE, [])
    assert f["phase"] == "2.HZ" and f["minute"] == 49


def test_vorquote_ignoriert_live_punkte():
    assert H.vor_heimquote(HIST_HEIM) == 1.48


def test_abrechnung_zur_pausenquote():
    f = dict(H.kandidat(spiel(), PEND_TORE, HIST_HEIM), gebuchtAt=JETZT.isoformat(), status="pending")
    [e] = H.abrechnen([f], {"9": ([1, 0], [0, 0])}, JETZT)
    assert e["wetten"]["over05"] == {"win": True, "quote": 1.32, "r": round(0.32 * 0.98, 4)}
    assert e["wetten"]["over15"]["r"] == -1.0 and e["wetten"]["heim"]["win"] is True


def test_widerspruch_zum_ergebnis_ist_ungueltig_und_alt_verfaellt():
    f = dict(H.kandidat(spiel(), PEND_TORE, []), gebuchtAt=JETZT.isoformat(), status="pending")
    assert H.abrechnen([f], {"9": ([1, 1], [1, 0])}, JETZT)[0]["status"] == "ungueltig"
    assert H.abrechnen([f], {}, JETZT + timedelta(days=4))[0]["status"] == "unaufgeloest"
    assert H.abrechnen([f], {}, JETZT + timedelta(days=1))[0]["status"] == "pending"


def test_bericht_urteil_erst_ab_mindestmenge():
    e = {"status": "abgerechnet", "gruppen": ["tore"],
         "wetten": {"over05": {"win": True, "quote": 1.3, "r": 0.294}}}
    b = H.bericht([e] * 10)
    assert b["tore/over05"]["n"] == 10 and b["tore/over05"]["urteil"] == "sammelt"
    assert b["tore/over05"]["erwartetPct"] == round(100 / 1.3, 1)
    assert b["heim/heim"]["n"] == 0


def test_nachricht_buendelt_und_deckelt():
    funde = [dict(H.kandidat(spiel(mid=str(i)), PEND_TORE, HIST_HEIM)) for i in range(10)]
    t = H.nachricht(funde)
    assert t.count("<b>Ararat – Noah</b>") == H.PUSH_DECKEL and "+2 weitere" in t
    assert "Tor in 2. HZ <b>@1.32 <i>(76 %)</i></b>" in t, "Quote mit der Wahrscheinlichkeit, die sie sagt"


def test_nachricht_staerkste_erwartung_zuerst():
    schwach = dict(H.kandidat(spiel(mid="1"), {"signals": {"Over/Under 2.5 Goals": {"fav": "OVER", "odd": 1.74}}}, []), home="Schwach")
    stark = dict(H.kandidat(spiel(mid="2"), {"signals": {"Over/Under 2.5 Goals": {"fav": "OVER", "odd": 1.40}}}, []), home="Stark")
    t = H.nachricht([schwach, stark])
    assert t.index("Stark") < t.index("Schwach")
    assert "2 Spiele, in denen mehr erwartet war" in t and "┄" in t
    assert "1 Spiel, in dem mehr" in H.nachricht([stark])


# ── Team-Archiv ─────────────────────────────────────────────────────────────────────────────
def z(mid, h, a, ft, ht, d="2026-10-01"):
    return {"matchId": mid, "home": h, "away": a, "ft": ft, "ht": ht, "league": "L", "settledAt": d + "T20:00:00+00:00"}


def test_archiv_behaelt_was_das_ledger_verliert():
    s = T.aufnehmen({}, [z("1", "A", "B", [3, 1], [1, 0]), z("1", "A", "B", [3, 1], [1, 0])], JETZT)
    s = T.aufnehmen(s, [], JETZT)                      # Ledger hat die Zeile nicht mehr
    assert list(s) == ["1"]
    s = T.aufnehmen(s, [z("2", "C", "A", [0, 0], [0, 0], d="2025-01-01")], JETZT)
    assert "2" not in s, "aelter als ARCHIV_TAGE"


def test_serie_aus_sicht_des_teams():
    s = T.aufnehmen({}, [z("1", "A", "B", [3, 1], [1, 0], "2026-09-20"),
                         z("2", "C", "A", [1, 1], [0, 0], "2026-09-27"),
                         z("3", "A", "D", [0, 2], [0, 0], "2026-10-02")], JETZT)
    r = T.serie(s, "A")
    assert r == {"n": 3, "over25": 1, "btts": 2, "ht00": 2, "siege": 1, "toreSchnitt": 2.7, "form": "NUS",
                 "toreFuer": 1.3, "toreGegen": 1.3}
    assert T.serie(s, "Unbekannt") is None


def test_main_bucht_vor_dem_senden_und_nur_einmal(tmp_path, monkeypatch):
    monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "betfair_prices.json").write_text(json.dumps({"matches": [spiel()]}))
    (tmp_path / "betfair_track_state.json").write_text(json.dumps({"pending": {"9": PEND_TORE}}))
    (tmp_path / "betfair_history.json").write_text(json.dumps({"9": HIST_HEIM}))
    (tmp_path / "betfair_track_results.json").write_text("[]")
    gesendet = []

    def senden(t):
        assert json.loads((tmp_path / H.AUSGABE_FILE).read_text())["eintraege"], "Buch vor dem Senden"
        gesendet.append(t)
    H.main(str(tmp_path), JETZT, senden)
    H.main(str(tmp_path), JETZT + timedelta(minutes=15), senden)
    assert len(gesendet) == 1
    d = json.loads((tmp_path / H.AUSGABE_FILE).read_text())
    assert len(d["eintraege"]) == 1 and d["zuletzt"][0]["matchId"] == "9"


# ── 04.10.2026: frisches Geld auf O/U 1.5 rund um die Pause ─────────────────────────────────
def test_zufluss_seit_letztem_lauf():
    vorher = {"o15": {"over": 1000, "under": 800}, "o05": {"over": 500, "under": 100}}
    jetzt_ = {"o15": {"over": 3600, "under": 1000}, "o05": {"over": 500, "under": 100}}
    z = H.zufluss(vorher, jetzt_, (JETZT - timedelta(minutes=15)).isoformat(), JETZT)
    assert z["minuten"] == 15 and z["o15"] == {"over": 2600, "under": 200, "overAnteil": 0.929}
    assert z["o05"]["overAnteil"] is None
    assert H.over_zufluss(z) is True
    assert "O/U 1.5: €2.8K, davon 93 % auf Over" in H._zufluss_txt(z)
    assert "O/U 0.5: kein neues Geld" in H._zufluss_txt(z)


def test_zufluss_nur_mit_frischem_vergleich():
    st = {"o15": {"over": 1, "under": 1}}
    assert H.zufluss(st, st, (JETZT - timedelta(minutes=90)).isoformat(), JETZT) is None, "zu alt"
    assert H.zufluss(None, st, JETZT.isoformat(), JETZT) is None


def test_geldstand_aus_preisstand():
    m = {"markets": {"Over/Under 1.5 Goals": {"runners": [{"name": "Under 1.5 Goals", "vol": 300},
                                                          {"name": "Over 1.5 Goals", "vol": 900}]}}}
    assert H.geldstand(m) == {"o15": {"over": 900.0, "under": 300.0}}


def test_main_merkt_geldstand_und_traegt_zufluss_ein(tmp_path, monkeypatch):
    monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("APISPORTS_KEY", raising=False)
    def m_(li, o15):
        x = spiel(li)
        x["markets"]["Over/Under 1.5 Goals"] = {"runners": [{"name": "Over 1.5 Goals", "odd": 2.3, "vol": o15},
                                                            {"name": "Under 1.5 Goals", "odd": 1.7, "vol": 500}]}
        return x
    (tmp_path / "betfair_track_state.json").write_text(json.dumps({"pending": {"9": PEND_TORE}}))
    (tmp_path / "betfair_history.json").write_text("{}")
    (tmp_path / "betfair_track_results.json").write_text("[]")
    (tmp_path / "betfair_prices.json").write_text(json.dumps({"matches": [m_({"time": 32, "goal_v1": 0, "goal_v2": 0}, 1000)]}))
    H.main(str(tmp_path), JETZT - timedelta(minutes=15), lambda t: True)
    (tmp_path / "betfair_prices.json").write_text(json.dumps({"matches": [m_({"is_ht": True, "time": 45, "goal_v1": 0, "goal_v2": 0}, 4000)]}))
    H.main(str(tmp_path), JETZT, lambda t: True)
    e = json.loads((tmp_path / H.AUSGABE_FILE).read_text())["eintraege"][0]
    assert e["zufluss"]["o15"]["over"] == 3000 and e["zufluss"]["o15"]["overAnteil"] == 1.0
    b = json.loads((tmp_path / H.AUSGABE_FILE).read_text())["bericht"]["tore/over05"]
    assert "mitOverZufluss" in b and "ohneOverZufluss" in b


# ── 09.10.2026: Vereine / Nationalteams getrennt ────────────────────────────────────────────
# Lucas: „hab die Spiele der Nationalteams ausgelassen, weil die nicht gut als Streak messbar
# sind mmn — und hab da echt viele Winner mitgenommen". Die Tabelle mass das ganze Feature.

def test_nationalteam_am_wettbewerb_erkannt():
    import hz_finder as H
    for lg in ("Friendlies International", "Friendlies International U20", "UEFA U21 Euro Qualifiers",
               "CONCACAF Nations League B", "UEFA Nations League C", "Friendlies Women's U23 Internationals",
               "World Cup Qualifiers - Europe", "Africa Cup of Nations"):
        assert H.ist_nationalteam(lg), lg
    for lg in ("EFL Trophy", "Argentinian Primera Division Reserves", "Elite Friendlies",
               "Japanese Emperor Cup", "Chinese U20", None, ""):
        assert not H.ist_nationalteam(lg), lg


def test_bericht_teilt_jede_wette_auf():
    import hz_finder as H
    def e(league, win):
        return {"status": "abgerechnet", "gruppen": ["tore"], "league": league,
                "wetten": {"over15": {"win": win, "quote": 2.0, "r": 0.98 if win else -1.0}}}
    eintraege = [e("Friendlies International", False), e("Friendlies International", False),
                 e("EFL Trophy", True), e("Dutch Eerste Divisie", True), e("EFL Trophy", False)]
    b = H.bericht(eintraege)["tore/over15"]
    assert b["n"] == 5
    assert b["vereine"]["n"] == 3 and b["vereine"]["trefferPct"] == 66.7
    assert b["nationalteams"]["n"] == 2 and b["nationalteams"]["trefferPct"] == 0.0


def test_serie_zeigt_geschossen_zu_kassiert():
    """10.10.2026 (Lucas: „sind die 4.1 und 4.6 Tore gesamt?"). „Ø 4.1 Tore" las sich wie eigene
    Tore; es war die Summe aus beiden Seiten."""
    s = {"form": "SUN", "toreSchnitt": 4.1, "toreFuer": 2.6, "toreGegen": 1.5, "over25": 6, "n": 7}
    assert "Ø 2.6:1.5 Tore" in H._serie_txt(s)
    alt = {"form": "SUN", "toreSchnitt": 4.1, "over25": 6, "n": 7}
    assert "Ø 4.1 Tore" in H._serie_txt(alt), "alte Serie ohne Felder bleibt lesbar"
