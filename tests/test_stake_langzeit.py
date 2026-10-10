"""10.10.2026 (Übersicht-Check, Lucas „ja"): „Ballon dor 2026 ⏱ 378 h · Ballon d`Or - Winner:
Harry Kane $51.5K" stand in „Stake · größtes Geld" und „noch spielbar" — Kacheln für Spiele.
Am Bestand: 6 von 1.500 Zeilen ohne Paarung (Ballon d'Or, Nippon Series, Pro Wrestling)."""
import stake_highroller_fetch as SH
import uebersicht_integrity as U


def test_outright_ist_langzeit():
    assert SH.ist_langzeit({"event": "Ballon dor 2026", "markt": "Ballon d`Or - Winner"})
    assert SH.ist_langzeit({"event": "NPB 2026", "markt": "Nippon Series 2026 - Winner"})


def test_spiele_bleiben_spiele():
    assert not SH.ist_langzeit({"event": "Arsenal - Leeds United"})
    assert not SH.ist_langzeit({"event": "Buse I / Vallejo D - Andreozzi G / Guinard M"})


def test_ledger_mischen_setzt_das_feld_auf_jeder_zeile():
    alt = {"wetten": [{"id": "a", "ts": "2026-10-10T08:00:00Z", "event": "Ballon dor 2026",
                       "kat": "Fußball"}]}
    neu = [{"id": "b", "ts": "2026-10-10T09:00:00Z", "event": "Arsenal - Leeds United",
            "kat": "Fußball"}]
    led = SH.ledger_mischen(alt, neu, "2026-10-10T10:00:00Z")
    feld = {w["id"]: w["langzeit"] for w in led["wetten"]}
    assert feld == {"a": True, "b": False}


def test_guard_meldet_zeilen_ohne_feld():
    c = U.check_stake_wette_sagt_ob_spiel({"stake": {"wetten": [{"event": "x"}, {"event": "y", "langzeit": False}]}})
    assert c["nFail"] == 1
    assert U.check_stake_wette_sagt_ob_spiel in U.UEBERSICHT_CHECKS
