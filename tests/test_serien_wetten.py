"""Serien-Wetten (01.10.2026).

Lucas: „die Streaks-Sektion ist in der Form für mich nicht zu verwenden … ich will die Wette ja
gewinnen, egal ob gepreist oder nicht". Die Tafel zeigte Serien ohne naechstes Spiel, ohne Markt
und ohne Chance. Jetzt: je Serie das naechste Spiel, der Markt, die Quote und die Trefferchance
(faire Marktwahrscheinlichkeit; Backtest Top-5, 7.156 Spiele: Serien treffen so oft, wie der
Markt sagt), sortiert nach Chance.

Erster Fehler beim Bau: „ungeschlagen" bekam die Quote aus ZWEI Soft-Quoten abgeleitet — zwei
Margen addiert ergaben @1,13 bei fairer 1,22 (Seattle). Eine Quote unter der fairen ist auf der
Tafel eine Lüge über den Preis.
"""
from datetime import datetime, timedelta, timezone

import compute_streaks as cs

JETZT = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def serie(typ="win", heim=True, h=24, **kw):
    s = {"teamId": "10", "team": "Seattle", "league": "MLS", "leagueName": "MLS", "type": typ,
         "market": typ, "length": 5, "venue": "all",
         "next": {"oppId": "20", "oppName": "Portland", "atHome": heim,
                  "kickoff": (JETZT + timedelta(hours=h)).isoformat()}}
    s.update(kw)
    return s


ODDS = {"10-20": {"hw": 1.80, "dr": 3.80, "aw": 4.50, "public_hw": 1.75, "public_aw": 4.2,
                  "o25": 1.60, "u25": 2.40, "public_o25": 1.55, "bttsY": 1.70, "bttsN": 2.15,
                  "bookmaker": "pinnacle"}}


def _fair():
    inv = [1 / 1.80, 1 / 3.80, 1 / 4.50]
    t = sum(inv)
    return [x / t for x in inv]


def test_sieg_heim_ist_entmargte_marktchance():
    w = cs.wette_fuer_serie(serie("win"), ODDS)
    assert w["chanceAus"] == "markt" and w["scharf"] is True
    assert abs(w["trefferPct"] - 100 * _fair()[0]) < 0.1
    assert w["quote"] == 1.75, "gespielt wird beim Soft-Buch — die Konsens-Quote steht da"


def test_sieg_auswaerts_nimmt_die_auswaertsseite():
    odds = {"20-10": ODDS["10-20"]}
    w = cs.wette_fuer_serie(serie("win", heim=False), odds)
    assert abs(w["trefferPct"] - 100 * _fair()[2]) < 0.1
    assert w["quote"] == 4.2


def test_ungeschlagen_quote_nie_unter_der_fairen():
    # Gegentest zum Seattle-Fehler: die alte Ableitung aus public_hw + Soft-Remis lag unter fair.
    w = cs.wette_fuer_serie(serie("unbeaten"), ODDS)
    ph, pd, _ = _fair()
    assert abs(w["trefferPct"] - 100 * (ph + pd)) < 0.1
    assert w["quote"] == round(1 / (1 / 1.80 + 1 / 3.80), 2)
    assert w["quote"] <= w["fairQuote"], "Hauptquote mit Marge liegt knapp unter fair, nicht weit darunter"
    assert w["fairQuote"] - w["quote"] < 0.06


def test_ungeschlagen_nimmt_echte_dc_quote_wenn_da():
    odds = {"10-20": dict(ODDS["10-20"], dc1X=1.27)}
    assert cs.wette_fuer_serie(serie("unbeaten"), odds)["quote"] == 1.27


def test_ueber_unter_paar_entmargt():
    o = cs.wette_fuer_serie(serie("over25"), ODDS)
    u = cs.wette_fuer_serie(serie("under25"), ODDS)
    assert abs(o["trefferPct"] + u["trefferPct"] - 100) < 0.2
    assert o["quote"] == 1.55 and u["quote"] == 2.40


def test_ohne_markt_modell_und_so_beschriftet():
    w = cs.wette_fuer_serie(serie("teamScores", matchupPct=71.0), {})
    assert w["chanceAus"] == "modell" and w["trefferPct"] == 71.0 and w["quote"] is None
    w2 = cs.wette_fuer_serie(serie("teamScores", continuation={"ratePct": 64}), {})
    assert w2["trefferPct"] == 64.0


def test_ohne_naechstes_spiel_keine_wette():
    assert cs.wette_fuer_serie({"teamId": "1", "type": "win", "next": None}, ODDS) is None


def _mit_wette(s):
    s["wette"] = cs.wette_fuer_serie(s, ODDS)
    return s


def test_wettliste_fenster_filter_und_sortierung():
    rows = cs.wettliste([
        _mit_wette(serie("win", h=24)),
        _mit_wette(serie("unbeaten", h=24)),
        _mit_wette(serie("over25", h=200)),                       # ausserhalb 7 Tage
        _mit_wette(serie("under25", h=-1)),                       # schon gespielt
        _mit_wette(serie("bttsYes", h=24, venue="home")),         # Teil-Serie
        _mit_wette(serie("bttsNo", h=24, impliziertVon="win")),   # abgeleitet
        _mit_wette(serie("teamScores", h=24)),                    # ohne Chance
    ], now=JETZT)
    assert [r["type"] for r in rows] == ["unbeaten", "win"]
    assert rows[0]["gegner"] == "Portland" and rows[0]["chanceAus"] == "markt"


def test_wettliste_je_team_und_markt_nur_einmal():
    rows = cs.wettliste([_mit_wette(serie("win")), _mit_wette(serie("win"))], now=JETZT)
    assert len(rows) == 1


def test_markt_vor_modell_bei_gleichstand():
    m = _mit_wette(serie("win"))
    mo = serie("teamScores", matchupPct=m["wette"]["trefferPct"])
    mo["wette"] = cs.wette_fuer_serie(mo, {})
    rows = cs.wettliste([mo, m], now=JETZT)
    assert rows[0]["chanceAus"] == "markt"
