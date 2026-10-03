"""Eingefrorene Ligen-Listen (03.10.2026, Register ligen-watch-betfair / ligen-watch-poly).

Fehlerklasse: wer die Gewinner-Ligen im Nachhinein waehlt, misst seine Auswahl. Gezaehlt wird
deshalb NUR, was nach dem Einfrieren abgerechnet wurde — und die Liste selbst darf sich nicht
still aendern."""
import ligen_watch as L


def bf(liga="Czech 2 Liga", win=True, odd=2.0, ts="2026-10-05T10:00:00+00:00", mid="1", markt="Match Odds"):
    return {"league": liga, "market": markt, "win": win, "odd": odd, "settledAt": ts, "matchId": mid}


def test_liste_ist_eingefroren():
    # Wer diese Zahl aendert, aendert die Messung — dann bitte neuen Register-Eintrag, nicht still.
    assert len(L.LISTEN["betfair_liste"]["ligen"]) == 12
    assert L.EINGEFROREN_AM == "2026-10-03" and L.FREEZE.startswith("2026-10-04")


def test_nur_vorwaerts():
    z = L.sammeln({}, [bf(ts="2026-10-02T10:00:00+00:00"), bf(mid="2")], [])
    assert list(z) == ["bf|2|Match Odds"], "vor dem Einfrieren abgerechnet = Auswahlbasis, nicht Messung"


def test_exakter_liganame():
    z = L.sammeln({}, [bf(liga="German Bundesliga 2"), bf(liga="German Bundesliga", mid="2")], [])
    assert [e["listen"] for e in z.values()] == [["betfair_kontrolle"]]


def test_rendite_mit_kommission():
    assert L.betfair_rendite(bf(odd=2.0)) == 0.98
    assert L.betfair_rendite(bf(win=False)) == -1.0


def test_buch_ueberschreibt_nicht_und_ueberlebt_deckel():
    z1 = L.sammeln({}, [bf()], [])
    # naechster Lauf: Zeile ist aus dem 40k-Ledger herausgerollt — sie bleibt im Buch
    z2 = L.sammeln({"zeilen": z1}, [], [])
    assert z2 == z1


def test_poly_listen():
    s = [{"key": "itf-a-b-2026-10-05", "side": "A", "cat": "Tennis", "league": "TENNIS",
          "result": "win", "pnl": 5.0, "stake": 10.0, "firstTs": "2026-10-05T01:00:00+00:00"},
         {"key": "cs2-x", "side": "X", "cat": "E-Sport", "league": "ESPORTS",
          "result": "loss", "pnl": -10.0, "stake": 10.0, "firstTs": "2026-10-05T01:00:00+00:00"},
         {"key": "atp-x", "side": "X", "cat": "Tennis", "league": "TENNIS",
          "result": "win", "pnl": 1.0, "stake": 10.0, "firstTs": "2026-10-05T01:00:00+00:00"}]
    z = L.sammeln({}, [], s)
    assert sorted(l for e in z.values() for l in e["listen"]) == ["poly_esport", "poly_itf"]


def test_urteil():
    gut = [0.5] * 200 + [-1.0] * 100 + [0.9] * 100
    k = L.kennzahlen(gut)
    assert L.urteil(k, 300) == "traegt" and k["ug"] > 0
    assert L.urteil(L.kennzahlen([-1.0, 0.98] * 10), 300) == "sammelt"
    schlecht = L.kennzahlen([-1.0] * 300 + [0.98] * 100)
    assert L.urteil(schlecht, 300) == "traegt nicht"


def test_bericht_vergleich():
    z = L.sammeln({}, [bf(), bf(liga="English Premier League", win=False, mid="9")], [])
    b = L.bericht(z)
    v = [x for x in b["vergleiche"] if x["liste"] == "betfair_liste"][0]
    assert v["abstandPP"] == 198.0
    assert b["listen"]["betfair_liste"]["urteil"] == "sammelt"
