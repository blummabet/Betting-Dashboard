"""12.10.2026 (Lucas: „Orsomarso – Boca Juniors de Cali … Half Time 11.904 € auf Boca … Wieso
finden wir dieses Spiel nicht?").

Lauf 19:05 UTC: 150 Detail-Calls = 40 live + 110 vor Anpfiff, davon KEINES in den naechsten 6 h.
Der 72h-Prioritaets-Topf (Land INT: Frauen-Laenderspiele, U19, AFC) kam vor dem heutigen Abend.
Auf dem alten select_ids faellt Orsomarso hier raus."""
from datetime import datetime, timedelta, timezone

import betfair_data_integrity as BI
import fetch_betfair_betwatch as B

T0 = datetime(2026, 10, 12, 19, 5, tzinfo=timezone.utc)


def _ev(mid, liga, ko_h, live=False, land=None):
    t = T0 + timedelta(hours=ko_h)
    return {"matchId": mid, "home": "H%s" % mid, "away": "A%s" % mid, "league": liga,
            "country": land, "kickoff": t.isoformat().replace("+00:00", "Z"), "live": live}


def _abend():
    live = [_ev(i, "Irgendwas", -0.5, live=True) for i in range(40)]
    vorschau = [_ev(1000 + i, "Friendlies Women's International", 7 + i * 0.5, land="INT")
                for i in range(110)]
    orso = _ev(36000001, "Colombian Primera B", 1.4)          # Orsomarso, Anpfiff 20:30 UTC
    return live + vorschau + [orso]


def test_der_heutige_abend_kommt_vor_der_vorschau():
    ids = B.select_ids(_abend(), now=T0, cap=150)
    assert 36000001 in ids, "Orsomarso (Anpfiff in 1,4 h) muss einen Detail-Call bekommen"
    assert ids[:40] == list(range(40)), "live bleibt vorn"
    assert ids[40] == 36000001


def test_ohne_nahfenster_waere_es_der_alte_fehler():
    assert 36000001 not in B.select_ids(_abend(), now=T0, cap=150, nah_h=0)


def test_prioritaet_bleibt_vor_dem_rest_und_sortiert_nach_geld():
    evs = [_ev(1, "Friendlies Women's International", 40, land="INT"),
           _ev(2, "German Bundesliga", 50),
           _ev(3, "Icelandic 2 Deild", 20)]
    ids = B.select_ids(evs, now=T0, cap=10, vol_bekannt={2: 50000})
    assert ids == [2, 1, 3]


def test_nah_abdeckung_zaehlt_gegen_die_liste():
    evs = _abend()
    a = B.nah_abdeckung(evs, ids=list(range(40)), now=T0)
    assert a["nahGesamt"] == 1 and a["nahDrin"] == 0      # nur Orsomarso pfeift in 6 h an
    assert any("Colombian Primera B" in x for x in a["nahFehlt"])


def _ctx(meta):
    return BI.BetfairCtx(now=T0, prices={"_meta": meta, "matches": []}, history={})


def test_guard_schlaegt_an_wenn_der_abend_fehlt():
    r = BI.check_nahe_spiele_im_feed(_ctx({"nahH": 6, "nahGesamt": 30, "nahDrin": 0,
                                           "nahFehlt": ["Orsomarso SC v Boca Juniors de Cali (Primera B)"]}))
    assert not r["ok"] and "Orsomarso" in r["failures"][0]


def test_guard_schweigt_bei_voller_abdeckung_und_ohne_feld():
    assert BI.check_nahe_spiele_im_feed(_ctx({"nahGesamt": 30, "nahDrin": 30}))["ok"]
    assert BI.check_nahe_spiele_im_feed(_ctx({}))["ok"]
    assert BI.check_nahe_spiele_im_feed(_ctx({"nahGesamt": 3, "nahDrin": 0}))["ok"], "zu wenige"


def test_bekannt_grosses_geld_bleibt_vor_dem_nahtopf():
    """Der 08.09.-Fall darf durch den Nah-Topf nicht zurueckkommen."""
    evs = [_ev(i, "Scottish Challenge Cup", 2 + i * 0.01) for i in range(40)] + [_ev(999, "UEFA Champions League", 11)]
    assert B.select_ids(evs, now=T0, cap=40, vol_bekannt={999: 102861})[0] == 999
