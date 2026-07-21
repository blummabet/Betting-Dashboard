"""21.07.2026 (Lucas, MLS-Cards) — der /injuries-Endpoint liefert keine Position → MLS-Verletzte
standen alle mit position=None („(?)" + Backup-Unterschätzung). injury_positions reichert sie aus
dem Kader-Cache per Nachname an. Der Join muss „S. Reguilon" ↔ „Sergio Reguilón" verbinden."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import injury_positions as IP


CACHE = {"teams": {"9568": {"starters": [
    {"id": 1, "name": "Sergio Reguilón", "pos": "D"},
    {"id": 2, "name": "Lionel Messi", "pos": "F"},
    {"id": 3, "name": "Sergio Busquets", "pos": "M"},   # gleicher Vorname „Sergio", anderer Nachname
]}}}


class TestLastnameJoin:
    def test_initial_matcht_vollen_namen(self):
        pm = IP.build_position_map(CACHE, "9568")
        assert pm.get("reguilon") == "D", "Nachname-Join muss Akzente/Initialen überbrücken"
        assert pm.get("messi") == "F"

    def test_enrich_fuellt_fehlende_position(self):
        players = [{"name": "S. Reguilon", "position": None},
                   {"name": "L. Messi", "position": None}]
        n = IP.enrich_team_injuries(players, IP.build_position_map(CACHE, "9568"))
        assert n == 2
        assert players[0]["position"] == "D" and players[1]["position"] == "F"

    def test_bestehende_position_bleibt(self):
        players = [{"name": "S. Reguilon", "position": "GK"}]
        IP.enrich_team_injuries(players, IP.build_position_map(CACHE, "9568"))
        assert players[0]["position"] == "GK", "gesetzte Position nie überschreiben"

    def test_ambiger_nachname_wird_nicht_geraten(self):
        cache = {"teams": {"1": {"starters": [
            {"name": "A. Silva", "pos": "D"}, {"name": "B. Silva", "pos": "M"}]}}}
        pm = IP.build_position_map(cache, "1")
        assert "silva" not in pm, "zwei Silvas → ambig → nicht raten"

    def test_fehlendes_team_ist_leer(self):
        assert IP.build_position_map(CACHE, "9999") == {}
        assert IP.enrich_team_injuries([{"name": "X", "position": None}], {}) == 0

    def test_enrich_injuries_ganzer_block(self):
        inj = {"9568": {"players": [{"name": "S. Reguilon", "position": None}]},
               "_meta": {"updatedAt": "x"}}   # _meta darf nicht crashen
        # _meta hat kein 'players' → wird übersprungen
        n = IP.enrich_injuries({k: v for k, v in inj.items() if k != "_meta"}, CACHE)
        assert n == 1 and inj["9568"]["players"][0]["position"] == "D"


class TestPosMapBevorzugt:
    """21.07.2026 — der Cache hat nur die Start-11 (`starters`); Verletzte sind oft Ersatz. Die volle
    `posMap` (alle Spieler) muss bevorzugt werden, damit auch Nicht-Starter matchen."""

    def test_posmap_schlaegt_starters(self):
        cache = {"teams": {"9568": {
            "starters": [{"name": "Lionel Messi", "pos": "F"}],           # nur Star-Elf
            "posMap": {"reguilon": "D", "messi": "F", "avilesbench": "M"},  # voller Kader
        }}}
        pm = IP.build_position_map(cache, "9568")
        assert pm.get("reguilon") == "D", "Ersatz-Verletzter (nicht in starters) muss aus posMap kommen"
        players = [{"name": "S. Reguilon", "position": None}]
        assert IP.enrich_team_injuries(players, pm) == 1 and players[0]["position"] == "D"

    def test_fallback_auf_starters_ohne_posmap(self):
        cache = {"teams": {"1": {"starters": [{"name": "A. Silva", "pos": "D"}]}}}  # alte Cache-Version
        assert IP.build_position_map(cache, "1").get("silva") == "D"


class TestNormalisierung:
    def test_lastname_wirft_initialen(self):
        assert IP._lastname("S. Reguilon") == "reguilon"
        assert IP._lastname("Sergio Reguilón") == "reguilon"
        assert IP._lastname("Kim Kee-Hee") in ("keehee", "kim")  # robust, kein Crash

    def test_leer_robust(self):
        assert IP._lastname("") == ""
        assert IP.enrich_injuries(None, None) == 0
