#!/usr/bin/env python3
"""test_monitor_open_positions.py — 25.08.2026 (Audit-Befund 13).

Ist die Wett-Datei unlesbar, schrieb der Monitor `position_health.json` mit LEERER Positionsliste
und FRISCHEM `lastRun`. Das Dashboard rendert daraufhin "Keine offenen" — und weil der Zeitstempel
frisch ist, schlaegt auch der Stale-Check nicht an. Offene Positionen ohne Ueberwachung, und die
Oberflaeche beruhigt. "Keine offenen" und "ich weiss es nicht" muessen zwei Zustaende sein.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import monitor_open_positions as M



def test_fehlende_datei_ist_kein_lesefehler(tmp_path):
    M._UNREADABLE.clear()
    p = tmp_path / "weg.json"
    assert M._load(p, {"bets": []}) == {"bets": []}
    assert str(p) not in M._UNREADABLE


def test_kaputte_datei_wird_gemerkt(tmp_path):
    M._UNREADABLE.clear()
    p = tmp_path / "kaputt.json"
    p.write_text("{ nein", encoding="utf-8")
    assert M._load(p, {"bets": []}) == {"bets": []}
    assert str(p) in M._UNREADABLE
    M._UNREADABLE.clear()


def test_health_meldet_unbekannt_statt_keine_offenen(tmp_path, monkeypatch, capsys):
    M._UNREADABLE.clear()
    bets = tmp_path / "bets.json"
    bets.write_text("{ kaputt", encoding="utf-8")
    health = tmp_path / "health.json"
    monkeypatch.setattr(M, "BETS_FILE", bets)
    monkeypatch.setattr(M, "HEALTH_FILE", health)
    M.main()
    out = json.loads(health.read_text())
    assert out["positions"] == []
    assert out["error"], "der Report muss selbst sagen, dass er blind ist"
    assert "nicht lesbar" in capsys.readouterr().out
    M._UNREADABLE.clear()


def test_echt_leer_bleibt_ohne_fehler(tmp_path, monkeypatch):
    M._UNREADABLE.clear()
    bets = tmp_path / "bets.json"
    bets.write_text(json.dumps({"bets": []}), encoding="utf-8")
    health = tmp_path / "health.json"
    monkeypatch.setattr(M, "BETS_FILE", bets)
    monkeypatch.setattr(M, "HEALTH_FILE", health)
    M.main()
    out = json.loads(health.read_text())
    assert out["positions"] == [] and out["error"] is None, "leer ist nicht dasselbe wie kaputt"


# ── Unbekannter Markt erfindet keine Zahl (25.08.2026, Audit-Befund 06) ──────────────────────
# Jedes Label, das keinem Muster entsprach, fiel still auf "hw" zurueck. Der Health-Score einer
# Over-4.5-Position wurde damit gegen den HEIMSIEG gerechnet — und als gueltiger Score mit
# Faktoren-Aufschluesselung ins Telegram-Alert gerendert.
_FX = {"edge_hw": 5.0, "poly_hw": 0.5, "fair_hw": 0.45,
       "edge_o25": 2.0, "poly_o25": 0.6, "fair_o25": 0.58}


def test_bekannter_markt_wird_aufgeloest():
    e, p_, f = M.resolve_current_market({"market": "Über 2.5 Tore"}, _FX)
    assert (e, p_, f) == (2.0, 0.6, 0.58)


def test_unbekannter_markt_gibt_nichts_statt_heimsieg(capsys):
    e, p_, f = M.resolve_current_market({"market": "Über 4.5 Tore"}, _FX)
    assert (e, p_, f) == (None, None, None), "darf NICHT auf den Heimsieg zurueckfallen"
    assert "nicht zuordenbar" in capsys.readouterr().out


def test_health_score_kommt_mit_none_zurecht():
    h = M.compute_health({"market": "Völlig neuer Markt", "stake": 5, "polyPrice": 0.5}, _FX)
    assert isinstance(h, dict), "darf nicht werfen — nur eben ohne Edge-Faktoren rechnen"

