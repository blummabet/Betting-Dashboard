"""22.07.2026 (Lucas: „Balance passt nicht — sind 122,96, nicht 99,93").
Der Balance-Fetcher zählte nur freies CLOB-Collateral (99.93). Das echte Wallet-Guthaben =
frei + Marktwert der offenen Positionen. Diese Tests fixieren die Positions-Summierung und die
Equity-Mathematik — und dass `usdc` (Sizing-Grundlage) NICHT durch Positionen aufgebläht wird."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

import fetch_wm_poly_balance as B


class TestPositionsValue:
    def test_currentvalue_wird_summiert(self, monkeypatch):
        rows = [{"currentValue": 12.5}, {"currentValue": 10.53}]
        monkeypatch.setattr(B.urllib.request, "urlopen", _fake_urlopen(rows))
        assert B.fetch_positions_value("0xabc") == 23.03

    def test_fallback_size_mal_curprice(self, monkeypatch):
        rows = [{"size": 20, "curPrice": 0.5}, {"size": 10, "curPrice": 1.303}]
        monkeypatch.setattr(B.urllib.request, "urlopen", _fake_urlopen(rows))
        # 10.0 + 13.03 = 23.03
        assert B.fetch_positions_value("0xabc") == 23.03

    def test_keine_positionen_ist_null_nicht_none(self, monkeypatch):
        monkeypatch.setattr(B.urllib.request, "urlopen", _fake_urlopen([]))
        assert B.fetch_positions_value("0xabc") == 0.0

    def test_leere_adresse_ist_none(self):
        assert B.fetch_positions_value("") is None

    def test_api_fehler_ist_none(self, monkeypatch):
        def _boom(*a, **k):
            raise OSError("network down")
        monkeypatch.setattr(B.urllib.request, "urlopen", _boom)
        assert B.fetch_positions_value("0xabc") is None


class TestSaveEquity:
    def test_total_ist_frei_plus_positionen(self, tmp_path, monkeypatch):
        monkeypatch.setattr(B, "OUT_FILE", tmp_path / "wm_poly_balance.json")
        out = B._save(99.9265, 0.0, "0xabc", positions=23.03)
        assert out["usdc"] == 99.9265          # Sizing-Grundlage unverändert
        assert out["positions"] == 23.03
        assert out["total"] == 122.9565        # Wallet-Equity = was Lucas in der Wallet sieht

    def test_ohne_positionen_bleibt_total_gleich_usdc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(B, "OUT_FILE", tmp_path / "wm_poly_balance.json")
        out = B._save(50.0, 0.0, "0xabc")
        assert out["positions"] == 0.0 and out["total"] == 50.0


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()
    def read(self):
        return self._p
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fake_urlopen(payload):
    def _f(req, timeout=None):
        return _Resp(payload)
    return _f
