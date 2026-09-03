"""tests/test_stake_league_norm.py — 03.09.2026

Lucas: "das heisst wir lernen jetzt auch schon mit, was normale Einsaetze fuer eine Liga sind
und was dann hoeher ist, je mehr Daten wir sammeln?"

Ja — aber nicht so, wie es zuerst gebaut war. Die Norm kam aus dem Ledger, und das ist auf
20.000 Wetten gedeckelt: bei gemessenen 4,3 Wetten/Minute reicht es rund 3,2 Tage zurueck.
Eine Liga, die einmal pro Woche spielt, haette darin NIE die 15 Wetten fuer eine Norm erreicht
— also ausgerechnet die kleinen Ligen, um die es geht.

Derselbe Fehler wie im Betfair-Badge am 24.08.: die Basis kam aus dem Moment statt aus der Zeit.
Deshalb fuehrt stake_league_norm.py einen eigenen, wachsenden Stand.
"""
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("stake_norm_t", ROOT / "stake_league_norm.py")
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)


def w(wid, liga="La Liga", usd=2000, vor_tagen=0, **extra):
    ts = (datetime.now(timezone.utc) - timedelta(days=vor_tagen)).isoformat().replace("+00:00", "Z")
    d = {"id": wid, "liga": liga, "einsatzUsd": usd, "ts": ts, "kombi": False,
         "sport": "soccer", "kat": "Fussball"}
    d.update(extra)
    return d


# -- Was in die Norm darf --------------------------------------------------
def test_kombis_zaehlen_nicht():
    """Der Einsatz einer Kombi haengt an mehreren Spielen und gehoert keinem allein."""
    assert N.taugt(w("a")) is True
    assert N.taugt(w("b", kombi=True)) is False


def test_unbekannter_usd_wert_zaehlt_nicht():
    assert N.taugt(w("a", usd=None)) is False


def test_gesperrte_sportart_verzieht_die_norm_nicht():
    assert N.taugt(w("a", liga="MLB", sport="baseball", kat="US-Sport")) is False


def test_ohne_liga_oder_id_geht_nichts():
    assert N.taugt(w("a", liga=None)) is False
    assert N.taugt(w(None)) is False


# -- Der Stand waechst -----------------------------------------------------
def test_zweiter_lauf_zaehlt_nicht_doppelt():
    st = N.nachtragen({}, [w("x1"), w("x2")])
    assert st["zugangLetzterLauf"] == 2
    st2 = N.nachtragen(st, [w("x1"), w("x2"), w("x3")])
    assert st2["zugangLetzterLauf"] == 1
    assert len(st2["samples"]["La Liga"]) == 3


def test_der_stand_ueberlebt_ein_geleertes_ledger():
    """Genau das ist der Punkt: das Ledger laeuft nach ~3 Tagen ueber, der Stand nicht."""
    st = N.nachtragen({}, [w("x%d" % i) for i in range(20)])
    st2 = N.nachtragen(st, [])
    assert len(st2["samples"]["La Liga"]) == 20
    assert N.norm_bauen(st2)["La Liga"]["basis"] == "gelernt"


def test_zu_alte_stichproben_fallen_raus():
    st = N.nachtragen({}, [w("alt", vor_tagen=N.ALTER_MAX_TAGE + 5), w("neu")])
    assert len(st["samples"]["La Liga"]) == 1


def test_je_liga_gedeckelt_am_alten_ende():
    viele = [w("i%d" % i, usd=1000 + i, vor_tagen=(N.JE_LIGA_MAX + 10 - i) / 24.0)
             for i in range(N.JE_LIGA_MAX + 10)]
    st = N.nachtragen({}, viele)
    reihe = st["samples"]["La Liga"]
    assert len(reihe) == N.JE_LIGA_MAX
    assert reihe[0][0] < reihe[-1][0], "sortiert, juengste hinten"


# -- Die Norm selbst -------------------------------------------------------
def test_unter_min_n_gibt_es_keine_zahl():
    st = N.nachtragen({}, [w("i%d" % i) for i in range(N.MIN_N - 1)])
    e = N.norm_bauen(st)["La Liga"]
    assert e["basis"] == "zu duenn"
    assert e["median"] is None, "keine erfundene Zahl, wo nichts gemessen ist"


def test_ab_min_n_median_und_p90():
    st = N.nachtragen({}, [w("i%d" % i, usd=1000 * (i + 1)) for i in range(20)])
    e = N.norm_bauen(st)["La Liga"]
    assert e["basis"] == "gelernt"
    assert e["n"] == 20
    assert e["median"] == 10500.0
    assert e["max"] == 20000.0


def test_die_norm_nennt_ihren_zeitraum():
    st = N.nachtragen({}, [w("a", vor_tagen=10), w("b", vor_tagen=0)])
    e = N.norm_bauen(st)["La Liga"]
    assert e["tage"] >= 9.9
    assert e["seit"] and e["bis"], "eine Zahl nennt ihre Basis, auch zeitlich"


def test_ligen_bleiben_getrennt():
    st = N.nachtragen({}, [w("a%d" % i, liga="A", usd=1000) for i in range(20)]
                          + [w("b%d" % i, liga="B", usd=9000) for i in range(20)])
    n = N.norm_bauen(st)
    assert n["A"]["median"] == 1000.0
    assert n["B"]["median"] == 9000.0
