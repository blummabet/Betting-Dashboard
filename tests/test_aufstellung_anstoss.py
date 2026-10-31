"""Wächter: der Betfair-Lauf stösst den Aufstellungs-Lauf nur an, wenn ein Top-5-Spiel bald anpfeift."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("af", ROOT / "scripts" / "aufstellung_faellig.py")
af = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(af)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _d(g, ko):
    return {"groups": {g: {"fixtures": [{"home": 1, "away": 2, "kickoff": ko}]}}}


def test_spiel_in_einer_stunde_loest_aus():
    assert af.faellige(_d("ENG", "2026-10-31T13:00:00Z"), NOW)


def test_zu_frueh_zu_spaet_und_andere_liga_nicht():
    assert not af.faellige(_d("ENG", "2026-10-31T15:00:00Z"), NOW)
    assert not af.faellige(_d("ENG", "2026-10-31T12:02:00Z"), NOW)
    assert not af.faellige(_d("MLS", "2026-10-31T13:00:00Z"), NOW)
    assert not af.faellige({"groups": {"ENG": {"fixtures": [{"kickoff": None}]}}}, NOW)


def test_betfair_workflow_stoesst_an():
    y = (ROOT / ".github" / "workflows" / "betfair.yml").read_text(encoding="utf-8")
    assert "liga-aufstellungen.yml/dispatches" in y
    assert "scripts/aufstellung_faellig.py" in y
