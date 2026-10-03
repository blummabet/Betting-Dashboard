"""O/U 3.5 mit 65-80 % Geld (03.10.2026, vorangemeldet, Register `betfair-ou35`)."""
from datetime import datetime, timedelta, timezone

import betfair_alerts as B

NOW = datetime(2026, 10, 3, 14, tzinfo=timezone.utc)


def match(share=0.70, odd=1.9, h=2.0, live=None, name="Under 3.5 Goals"):
    andere = "Over 3.5 Goals" if name.startswith("Under") else "Under 3.5 Goals"
    return {"matchId": "1", "home": "A", "away": "B", "league": "L",
            "kickoff": (NOW + timedelta(hours=h)).isoformat(), "liveInfo": live or {},
            "markets": {"Over/Under 3.5 Goals": {"runners": [
                {"name": name, "vol": 1000 * share, "odd": odd},
                {"name": andere, "vol": 1000 * (1 - share), "odd": 2.1}]}}}


def test_meldet_im_fenster():
    a = B.ou35_alert(match(), now=NOW)
    assert a and a["leadName"] == "Under 3.5 Goals" and abs(a["leadShare"] - 0.70) < 1e-9


def test_grenzen():
    assert B.ou35_alert(match(share=0.64), now=NOW) is None
    assert B.ou35_alert(match(share=0.80), now=NOW) is None, "80 % gehoert nicht mehr dazu"
    assert B.ou35_alert(match(odd=1.25), now=NOW) is None
    assert B.ou35_alert(match(h=5), now=NOW) is None, "nur am Spieltag, <= 3 h"
    assert B.ou35_alert(match(h=-0.1), now=NOW) is None
    assert B.ou35_alert(match(live={"time": 12}), now=NOW) is None


def test_karte_nennt_testlauf_und_herkunft():
    k = B.build_ou35_message(B.ou35_alert(match(), now=NOW), bericht={"n": 0})
    assert "Testlauf" in k and "2.000" in k and "Under 3.5" in k


def test_main_hat_deckel_und_dedup():
    import inspect
    src = inspect.getsource(B.main)
    assert "ou35_runde(" in src and "_ou[:5]" not in src, "Deckel VOR dem Dedup verschluckt neue Kandidaten"


# ── 03.10.2026 abends: Buch statt Push (s. ou35_runde) ─────────────────────────────────────
def _kand(n):
    return [{"matchId": str(i), "value": 100.0, "leadName": "Under 3.5 Goals", "leadOdd": 1.8,
             "home": "A", "away": "B", "league": "L", "total": 100.0, "stundenVor": 1.0,
             "leadShare": 0.7} for i in range(n)]


def test_standard_bucht_ohne_zu_senden():
    gesendet, gebucht = [], []
    s, b = B.ou35_runde(_kand(3), {}, lambda t: gesendet.append(t) or True, gebucht.append, push=False)
    assert (s, b) == (0, 3) and gesendet == [] and len(gebucht) == 3
    assert B.OU35_PUSH is False, "Standard muss AUS sein — ~60 Kandidaten am Tag"


def test_deckel_steht_nach_dem_dedup():
    # alter Code: `_ou[:5]` VOR dem Dedup — fuenf gesehene belegten den Deckel, Nr. 6 fiel still raus
    seen = {"ou35:%d" % i: 1 for i in range(5)}
    gebucht = []
    s, b = B.ou35_runde(_kand(6), seen, lambda t: True, gebucht.append, push=True)
    assert (s, b) == (1, 1) and gebucht[0]["matchId"] == "5"


def test_push_deckel_bucht_den_rest_trotzdem():
    gebucht = []
    s, b = B.ou35_runde(_kand(8), {}, lambda t: True, gebucht.append, push=True)
    assert s == B.OU35_PUSH_DECKEL and b == 8


def test_buchlaenge_passt_zur_abrechnung():
    import betfair_public_eval as E
    assert E.OU35_KEEP == B.OU35_KEEP >= 3000
