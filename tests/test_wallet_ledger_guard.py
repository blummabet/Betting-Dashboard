"""18.07.2026 — Guard: schlägt der Wallet-Ledger-Check auch WIRKLICH an?

Warum das ein eigener Test ist: `build_poly_wallet_ledger.py` läuft in den Workflows mit
`continue-on-error: true` — er darf den Datenlauf nie kippen. Damit ist jeder Fehler dort STILL.
Und weil die Ledger-Datei nach dem ersten Lauf existiert, sieht ein naiver „gibt es die Datei"-
Check für immer grün aus, während die Sammlung längst steht. Exakt die Klasse Bug, die uns bei
CLV wochenlang unentdeckt blieb (`check_closing_capture_alive`).

Live gegen das Repo lässt sich das nicht prüfen — dort ist der Ledger frisch, also grün. Ein
Guard, der nie beim Anschlagen beobachtet wurde, ist kein Guard.
"""
from datetime import datetime, timedelta, timezone

import pytest

import wm_data_integrity as W


def _ctx():
    return W.IntegrityCtx(wm={"groups": {}, "odds": {}, "_meta": {"profile": "mls_default"}},
                          poly={}, schedule={}, venues={}, history={}, streaks={})


def _snapshot(leer=False):
    if leer:
        return {}
    return {"topPositionsAll": [{"wallet": "0xa", "usd": 5000, "shares": 10000,
                                 "key": "K", "side": "home"}],
            "bigTradesAll": []}


def _ledger(stunden_alt=1.0, leer=False):
    ts = (datetime.now(timezone.utc) - timedelta(hours=stunden_alt)).isoformat()
    if leer:
        return {"trades": [], "positions": {}, "updatedAt": ts}
    return {"trades": [{"wallet": "0xa"}], "positions": {"0xa|K|home": {"wallet": "0xa"}},
            "updatedAt": ts}


def _files(monkeypatch, snapshot, ledger):
    """_lazy wird nach Dateiname aufgerufen — hier je nach Name das passende Objekt liefern."""
    def fake(name, *_a, **_k):
        return ledger if "ledger" in str(name) else snapshot
    monkeypatch.setattr(W, "_lazy", fake)


@pytest.fixture(autouse=True)
def _mls(monkeypatch):
    monkeypatch.setenv("COCOBET_DATASET", "mls")


class TestGuardSchlaegtAn:
    def test_input_da_aber_ledger_fehlt(self, monkeypatch):
        """Der teuerste Fall: Wallet-Daten laufen ein, werden aber nie weggeschrieben.
        Jeder solche Lauf ist unwiederbringlich — die API liefert das Fenster kein zweites Mal."""
        _files(monkeypatch, _snapshot(), {})
        r = W.check_wallet_ledger_growing(_ctx())
        assert not r["ok"], "fehlender Ledger bei frischem Input wird nicht erkannt"
        assert "fehlt komplett" in r["failures"][0]

    def test_ledger_eingefroren(self, monkeypatch):
        """Datei da, korrekt verdrahtet, aber seit Tagen nicht fortgeschrieben."""
        _files(monkeypatch, _snapshot(), _ledger(stunden_alt=72))
        r = W.check_wallet_ledger_growing(_ctx())
        assert not r["ok"], "stehende Sammlung sieht weiter gesund aus"
        assert "nicht fortgeschrieben" in r["failures"][0]

    def test_ledger_da_aber_inhaltslos(self, monkeypatch):
        """Format-Drift: Fetcher benennt bigTradesAll/topPositionsAll um → wir sammeln Luft."""
        _files(monkeypatch, _snapshot(), _ledger(leer=True))
        r = W.check_wallet_ledger_growing(_ctx())
        assert not r["ok"]
        assert any("leer" in f for f in r["failures"])


class TestGuardBleibtStill:
    def test_frischer_ledger_ist_gruen(self, monkeypatch):
        _files(monkeypatch, _snapshot(), _ledger(stunden_alt=1))
        assert W.check_wallet_ledger_growing(_ctx())["ok"]

    def test_kein_input_kein_alarm(self, monkeypatch):
        """Spielpause oder Mac-Runner aus → nichts zu sammeln. Kein Dauer-Gelb."""
        _files(monkeypatch, _snapshot(leer=True), {})
        assert W.check_wallet_ledger_growing(_ctx())["ok"]

    def test_liga_ist_ausgenommen(self, monkeypatch):
        """Liga hat bewusst kein Polymarket (Liquidität fehlt) — sonst leuchtet es ewig gelb."""
        monkeypatch.setenv("COCOBET_DATASET", "liga")
        _files(monkeypatch, _snapshot(), {})
        assert W.check_wallet_ledger_growing(_ctx())["ok"]

    def test_zwoelf_stunden_sind_noch_ok(self, monkeypatch):
        """Der dichteste Takt ist 2h, aber der WM-Lauf nur 5×/Tag — 12h dürfen kein Alarm sein."""
        _files(monkeypatch, _snapshot(), _ledger(stunden_alt=12))
        assert W.check_wallet_ledger_growing(_ctx())["ok"]


def test_guard_ist_registriert():
    assert any(getattr(c, "__name__", "") == "check_wallet_ledger_growing"
               for c in W.INTEGRITY_CHECKS), "Guard läuft nie mit"
