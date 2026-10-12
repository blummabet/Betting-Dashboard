"""Claudes eigene Picks (12.10.2026): Buch, CLV, Versand. Das Urteil haengt am CLV."""
import json
from datetime import datetime, timezone

import claude_picks as C

P = {"id": "x", "matchId": "1", "spiel": "Oviedo – Eibar", "liga": "Segunda", "anpfiff": "2026-10-12T16:30:00Z",
     "markt": "dnb", "seite": "away", "auswahl": "Eibar (DNB)", "kurs": 2.25,
     "pinnBeimPick": [0.3764, 0.3214, 0.3023], "grund": "Pinnacle läuft <auf> Eibar"}
VOR = datetime(2026, 10, 12, 15, 20, tzinfo=timezone.utc)
NACH = datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)
HIST = {"1": [{"ts": "2026-10-12T16:20:00+00:00", "pinn": [0.36, 0.32, 0.32]},
              {"ts": "2026-10-12T17:00:00+00:00", "pinn": [0.1, 0.1, 0.8]}]}   # nach Anpfiff: zaehlt nicht


def test_dnb_renormiert_ohne_remis():
    assert abs(C.seiten_p([0.4, 0.3, 0.3], "dnb", "away") - 0.3 / 0.7) < 1e-9
    assert C.seiten_p([0.4, 0.3, 0.3], "1x2", "away") == 0.3


def test_ausgang_dnb_remis_ist_push():
    assert C.ausgang("dnb", "away", [1, 1]) == "push"
    assert C.ausgang("1x2", "away", [1, 1]) == "loss"
    assert C.ausgang("1x2", "away", [0, 2]) == "win"


def test_clv_aus_letztem_stand_vor_anpfiff():
    z = C.bewerte(P, HIST, {"1": [0, 1]}, NACH)
    p0 = 0.3023 / (0.3023 + 0.3764)
    p1 = 0.32 / (0.32 + 0.36)
    assert abs(z["clvPP"] - round((p1 - p0) * 100, 2)) < 1e-9
    assert z["ergebnis"] == "win" and abs(z["rendite"] - 1.25) < 1e-9 and z["status"] == "abgerechnet"


def test_bilanz_urteil_erst_ab_mindestzahl():
    zs = [{"rendite": 0.5, "ergebnis": "win", "clvPP": 1.0}] * 5
    b = C.bilanz(zs)
    assert b["clvSchnittPP"] == 1.0 and b["clvUgPP"] is None and b["urteil"].startswith("sammelt")


def _lauf(tmp_path, monkeypatch, jetzt, gesendet):
    (tmp_path / "claude_picks.json").write_text(json.dumps({"picks": [P]}))
    monkeypatch.setattr(C, "BASE", tmp_path)
    C.main(jetzt=jetzt, senden=lambda t: gesendet.append(t) or True)
    return json.loads((tmp_path / "claude_picks_buch.json").read_text())


def test_versand_einmal_vor_anpfiff_html_sicher(tmp_path, monkeypatch):
    g = []
    _lauf(tmp_path, monkeypatch, VOR, g)
    buch = _lauf(tmp_path, monkeypatch, VOR, g)
    assert len(g) == 1, "nur einmal senden"
    assert "&lt;auf&gt;" in g[0] and "@2.25" in g[0]
    assert buch["zeilen"][0]["versand"] == "gesendet"


def test_nach_anpfiff_wird_nicht_mehr_gesendet(tmp_path, monkeypatch):
    g = []
    buch = _lauf(tmp_path, monkeypatch, NACH, g)
    assert g == [] and buch["zeilen"][0]["versand"] == "zu_spaet"
