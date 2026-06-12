"""Regression: Multibook-Konsens schreibt unter UNSEREN Fixture-Key (Spiegel-Fix 12.06.2026)."""
import importlib

mb = importlib.import_module("fetch_wm_multibook_odds")


def _fake_fixtures(monkeypatch, fixtures_resp):
    monkeypatch.setattr(mb, "_apif_get", lambda path, timeout=20: {"response": fixtures_resp})


def test_build_fixture_map_normalisiert_spiegel(monkeypatch):
    # APIF listet das Spiel gespiegelt (Heim=SUI, Auswärts=CAN); unser Fixture ist CAN-SUI
    apif_to_code = {100: "CAN", 200: "SUI"}
    real_keys = {"CAN-SUI"}
    _fake_fixtures(monkeypatch, [
        {"fixture": {"id": 9}, "teams": {"home": {"id": 200}, "away": {"id": 100}}},
    ])
    fmap = mb.build_fixture_map(apif_to_code, real_keys)
    assert fmap[9] == ("CAN-SUI", True)   # auf unsere Reihenfolge normalisiert, flipped


def test_build_fixture_map_nicht_gespiegelt(monkeypatch):
    apif_to_code = {100: "CAN", 200: "SUI"}
    real_keys = {"CAN-SUI"}
    _fake_fixtures(monkeypatch, [
        {"fixture": {"id": 9}, "teams": {"home": {"id": 100}, "away": {"id": 200}}},
    ])
    fmap = mb.build_fixture_map(apif_to_code, real_keys)
    assert fmap[9] == ("CAN-SUI", False)


def test_flip_tauscht_hw_aw_im_konsens(monkeypatch):
    """Bei flipped müssen public_hw/aw getauscht werden, dr/o25/u25/btts bleiben."""
    wm = {
        "teamIds": {"CAN": 100, "SUI": 200},
        "groups": {"G": {"fixtures": [{"home": "CAN", "away": "SUI"}]}},
        "odds": {"CAN-SUI": {"public_hw": 9.9, "public_bookmaker": "williamhill"}},
    }
    monkeypatch.setattr(mb.json, "loads", lambda *_a, **_k: wm)

    class _FakeFile:
        def read_text(self, *a, **k): return "{}"
        def write_text(self, data, *a, **k): pass
    monkeypatch.setattr(mb, "WM_FILE", _FakeFile())
    # APIF gespiegelt: Heim=SUI(200) Auswärts=CAN(100), Konsens hw(SUI-win)=2.0, aw(CAN-win)=3.5
    _fake_fixtures(monkeypatch, [
        {"fixture": {"id": 9}, "teams": {"home": {"id": 200}, "away": {"id": 100}}},
    ])
    monkeypatch.setattr(mb, "_paged", lambda path: [{
        "fixture": {"id": 9},
        "bookmakers": [
            {"name": "Bet365", "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.0"}, {"value": "Away", "odd": "3.5"}]}]},
            {"name": "Unibet", "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.0"}, {"value": "Away", "odd": "3.5"}]}]},
        ],
    }])
    import sys
    monkeypatch.setattr(sys, "argv", ["x", "--write"])
    assert mb.main() == 0
    o = wm["odds"]["CAN-SUI"]
    # CAN ist Heim → public_hw muss CAN-win (3.5) sein, public_aw SUI-win (2.0)
    assert o["public_hw"] == 3.5 and o["public_aw"] == 2.0
    assert o["public_bookmaker"].startswith("Konsens")
    # kein Phantom-Key SUI-CAN entstanden
    assert "SUI-CAN" not in wm["odds"]
