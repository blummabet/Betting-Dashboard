"""Was „Top 5 + MLS" ist, steht an drei Stellen — und muss an allen dreien dasselbe heissen.

🔴 28.09.2026: „German Bundesliga 2", „English Premier League 2 - Div 1" (U21) und „US MLS Next
Pro League" liefen als Top 5 durch, weil „german bundesliga" auch die zweite Liga traf. 537
Signale im Buch und 4 gesendete Pushes standen in der falschen Schublade — ausgerechnet an dem
Tag, an dem die Top 5 aus dem Public-Kanal genommen wurden (die Zweitligen haetten es mit).
"""
import pathlib
import re

import betfair_alerts as BA
import betfair_consensus as BC

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOP = ["English Premier League", "German Bundesliga", "Spanish La Liga", "Spanish LaLiga",
       "Italian Serie A", "French Ligue 1", "US MLS", "Major League Soccer"]
NICHT = ["German Bundesliga 2", "English Premier League 2 - Div 1", "Spanish La Liga 2",
         "US MLS Next Pro League", "English Sky Bet Championship", "Italian Serie B",
         "French Ligue 2", "Spanish La Liga Women", "UEFA Nations League"]


def test_python_regel():
    for lg in TOP:
        assert BA.is_top5(lg), lg
    for lg in NICHT:
        assert not BA.is_top5(lg), lg


def test_alle_kopien_gleich():
    js = (ROOT / "betfair-radar.js").read_text(encoding="utf-8")
    m = re.search(r"var TOP5_RX = /(.*)/i;", js)
    assert m, "TOP5_RX im Radar nicht gefunden"
    assert BA.TOP5_RX.pattern == BC._TOP5_RX.pattern == m.group(1)


def test_gegenbeweis_der_alte_ausdruck_haette_die_zweite_liga_genommen():
    alt = re.compile(r"(german bundesliga|english premier league|spanish la ?liga|italian serie a|"
                     r"french ligue 1|\bmls\b|major league soccer)", re.I)
    assert alt.search("German Bundesliga 2") and alt.search("English Premier League 2 - Div 1")
