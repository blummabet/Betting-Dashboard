"""Reihenfolge-Protokoll (03.10.2026, Register reihenfolge-signale).

Fehlerklasse: eine Frage ueber den VERLAUF, gestellt an Daten, die nur den Endstand kennen.
Zwei Gegentests halten die Ehrlichkeit: was beim ersten Blick schon da war, bekommt KEINE
erfundene Reihenfolge; und ab Anpfiff wird nichts mehr ergaenzt."""
from datetime import datetime, timedelta, timezone

import reihenfolge_protokoll as R

T0 = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
KO = (T0 + timedelta(hours=6)).isoformat()


def row(bf=None, poly=None, pinn=(0.40, 0.30, 0.30), live=False, ko=KO):
    r = {"matchId": "7", "home": "A", "away": "B", "league": "L", "kickoff": ko, "live": live,
         "pinn": {"home": pinn[0], "draw": pinn[1], "away": pinn[2]}}
    if bf:
        r["betfair"] = {"side": bf[0], "sharePct": bf[1], "odd": bf[2]}
    if poly:
        r["poly"] = {"side": poly[0], "sharePct": poly[1]}
    return r


def test_erster_blick_ist_gleichstand():
    s = R.erfassen({}, [row(bf=("home", 80, 2.1), poly=("home", 70))], T0)
    sig = s["7"]["seiten"]["home"]
    assert R.muster(sig) == "betfair=poly" and R.erster(sig) is None


def test_poly_zuerst_dann_betfair_dann_pinn():
    s = R.erfassen({}, [row(poly=("home", 70))], T0)
    s = R.erfassen(s, [row(bf=("home", 75, 2.2), poly=("home", 72))], T0 + timedelta(hours=1))
    s = R.erfassen(s, [row(bf=("home", 75, 2.0), poly=("home", 72), pinn=(0.44, 0.28, 0.28))],
                   T0 + timedelta(hours=2))
    sig = s["7"]["seiten"]["home"]
    assert R.muster(sig) == "poly>betfair>pinn" and R.erster(sig) == "poly"
    assert R.wertungsquote(sig) == (2.0, "betfair")


def test_unter_schwelle_kein_signal():
    s = R.erfassen({}, [row(bf=("home", 64, 2.1), pinn=(0.40, 0.30, 0.30))], T0)
    s = R.erfassen(s, [row(pinn=(0.42, 0.29, 0.29))], T0 + timedelta(hours=1))
    assert s["7"]["seiten"] == {}


def test_nach_anpfiff_nichts_mehr():
    s = R.erfassen({}, [row(poly=("home", 70))], T0)
    nach = T0 + timedelta(hours=7)
    s2 = R.erfassen(s, [row(bf=("home", 90, 1.5), poly=("home", 70))], nach)
    assert "betfair" not in s2["7"]["seiten"]["home"]
    s3 = R.erfassen(s, [row(bf=("home", 90, 1.5), live=True, ko=(nach + timedelta(hours=1)).isoformat())], T0)
    assert "betfair" not in s3["7"]["seiten"]["home"]


def test_abrechnung_und_verfall():
    s = R.erfassen({}, [row(poly=("home", 70))], T0)
    s = R.erfassen(s, [row(bf=("home", 75, 2.0), poly=("home", 72))], T0 + timedelta(hours=1))
    offen, buch = R.abrechnen(s, [], {}, T0 + timedelta(hours=8))
    assert "7" in offen and buch == [], "noch kein Ergebnis -> warten"
    offen, buch = R.abrechnen(s, [], {"7": "home"}, T0 + timedelta(hours=8))
    assert offen == {} and buch[0]["result"] == "win" and buch[0]["r"] == 0.98
    offen, buch = R.abrechnen(s, [], {}, T0 + timedelta(days=5))
    assert buch[0]["result"] == "unaufgeloest" and "r" not in buch[0]


def test_pinn_quote_ohne_kommission():
    s = R.erfassen({}, [row(poly=("away", 70), pinn=(0.40, 0.30, 0.25))], T0)
    s = R.erfassen(s, [row(poly=("away", 70), pinn=(0.36, 0.30, 0.30))], T0 + timedelta(hours=1))
    _, buch = R.abrechnen(s, [], {"7": "away"}, T0 + timedelta(hours=8))
    assert buch[0]["muster"] == "poly>pinn" and buch[0]["quoteAus"] == "pinn"
    assert abs(buch[0]["r"] - (1 / 0.30 - 1)) < 0.01


def test_bericht_zaehlt_nur_eindeutige_erste():
    buch = [{"muster": "poly>betfair", "erster": "poly", "nSignale": 2, "r": 0.5},
            {"muster": "betfair=poly", "erster": None, "nSignale": 2, "r": -1.0},
            {"muster": "betfair", "erster": None, "nSignale": 1, "r": -1.0}]
    b = R.bericht(buch)
    assert b["zweiPlusMitErstem"] == 1 and list(b["jeErster"]) == ["poly"]
