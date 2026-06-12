"""Tests: build_signal_ledger.py (Lern-Ledger) + Updater liest Ledger (12.06.2026)."""
import importlib

bl = importlib.import_module("build_signal_ledger")


def _wm(picks):
    return {"picks": picks}


def test_collect_nur_aufgeloeste_mit_signalen():
    wm = _wm({
        "A-1-MEX-ZAF": [
            {"market": "Unter 1.5", "result": "LOSS",
             "signals": [{"name": "form_trend", "score": -3.0}, {"name": "x", "score": 0.0}]},
            {"market": "Over 0.5", "result": None,  # unaufgelöst → raus
             "signals": [{"name": "form_trend", "score": 1.0}]},
            {"market": "BTTS", "result": "WIN", "signals": []},  # keine Signale → raus
        ],
    })
    recs = bl.collect_observations(wm)
    assert len(recs) == 1
    r = recs[0]
    assert r["key"] == "A-1-MEX-ZAF|Unter 1.5"
    assert r["result"] == "LOSS"
    # score=0.0-Signal rausgefiltert
    assert [s["name"] for s in r["signals"]] == ["form_trend"]


def test_upsert_idempotent():
    ledger = {"records": []}
    obs = bl.collect_observations(_wm({
        "M": [{"market": "Over 2.5", "result": "WIN", "signals": [{"name": "xg_strength", "score": 2.0}]}],
    }))
    new, upd = bl.upsert(ledger, obs)
    assert (new, upd) == (1, 0)
    # zweiter Lauf mit identischen Daten → nichts ändert sich
    new2, upd2 = bl.upsert(ledger, obs)
    assert (new2, upd2) == (0, 0)
    assert len(ledger["records"]) == 1


def test_upsert_aktualisiert_bei_result_flip():
    ledger = {"records": [
        {"key": "M|Over 2.5", "matchKey": "M", "market": "Over 2.5",
         "result": "PENDING", "signals": [{"name": "xg_strength", "score": 2.0}]},
    ]}
    obs = [{"key": "M|Over 2.5", "matchKey": "M", "market": "Over 2.5",
            "result": "WIN", "signals": [{"name": "xg_strength", "score": 2.0}]}]
    new, upd = bl.upsert(ledger, obs)
    assert (new, upd) == (0, 1)
    assert ledger["records"][0]["result"] == "WIN"


def test_updater_liest_ledger(tmp_path, monkeypatch):
    """update_signal_weights._load_results muss den Ledger (records[]) lesen."""
    uw = importlib.import_module("update_signal_weights")
    ledger = tmp_path / "wm_signal_ledger.json"
    ledger.write_text('{"records":[{"result":"WIN","signals":[{"name":"xg_strength","score":2.0}]}]}',
                      encoding="utf-8")
    monkeypatch.setattr(uw, "LEDGER_FILE", ledger)
    recs = uw._load_results()
    assert len(recs) == 1 and recs[0]["result"] == "WIN"
