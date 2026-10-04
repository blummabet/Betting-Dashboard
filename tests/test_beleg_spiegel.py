"""Beleg-Spiegel (03.10.2026, fresh:36132098 ohne Ledger-Zeile).

Fehlerklasse: zwei Belege derselben Handlung mit unterschiedlicher Haltbarkeit. Der Seen-Stand
hatte einen Runner-Spiegel in ~/.cocobet_state, das Ledger nicht — ein abgebrochener Lauf verlor
die Zeile, der naechste Runner wusste trotzdem „gesendet"."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import betfair_alerts as B

JETZT = datetime(2026, 10, 3, 16, tzinfo=timezone.utc)


def z(k, h=1):
    return {"k": k, "sentAt": (JETZT - timedelta(hours=h)).isoformat(), "status": "pending"}


def test_traegt_nur_fehlende_juengere_nach():
    led = [dict(z("a"), status="won")]
    neu = B.belege_nachtragen(led, [z("a"), z("b"), z("alt", h=24 * 5), z("b")], jetzt=JETZT)
    assert [x["k"] for x in neu] == ["b"], "abgerechnetes a nie ueberschreiben, altes nicht zurueck, b nur einmal"


@pytest.fixture
def ort(tmp_path, monkeypatch):
    monkeypatch.setenv("COCOBET_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(B, "_consensus_for_push", lambda a, c: None)
    monkeypatch.setattr(B, "_serie_fuer_push", lambda a: None)
    return tmp_path


def test_abgebrochener_lauf_verliert_den_beleg_nicht(ort):
    a = {"scenario": "fresh", "matchId": "36132098", "market": "Match Odds", "leadName": "X",
         "leadOdd": 1.9, "value": 66107.0, "live": {}}
    B._log_public_push(a)
    # der naechste Runner checkt frisch aus: Repo-Ledger ohne die Zeile
    (ort / B.PUB_LEDGER_FILE).write_text("[]", encoding="utf-8")
    assert B._belege_aus_spiegel(B.PUB_LEDGER_FILE, 800) == 1
    led = json.loads((ort / B.PUB_LEDGER_FILE).read_text(encoding="utf-8"))
    assert [e["k"] for e in led] == ["fresh:36132098:Match Odds"]
    assert B._belege_aus_spiegel(B.PUB_LEDGER_FILE, 800) == 0, "idempotent"


def test_kaputtes_ledger_wird_nicht_ueberschrieben(ort):
    B._beleg_spiegeln(B.PUB_LEDGER_FILE, z("x", h=0))
    (ort / B.PUB_LEDGER_FILE).write_text("{kaputt", encoding="utf-8")
    assert B._belege_aus_spiegel(B.PUB_LEDGER_FILE, 800) == 0
    assert (ort / B.PUB_LEDGER_FILE).read_text(encoding="utf-8") == "{kaputt"


def test_alle_drei_buecher_spiegeln():
    import inspect
    for fn in (B._log_public_push, B._log_rutsch, B._log_ou35):
        assert "_beleg_spiegeln(" in inspect.getsource(fn), fn.__name__
    assert "_belege_aus_spiegel(" in inspect.getsource(B.main)
