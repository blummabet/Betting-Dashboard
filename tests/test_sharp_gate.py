"""tests/test_sharp_gate.py — 29.08.2026 (Lucas: „prinzipiell checken").

Prueft sharp_gate.py gegen den geteilten Vertrag (tests/fixtures/sharp_gate_cases.json). Die
gleiche Datei prueft tests/frontend/sharp-gate-vertrag.test.mjs gegen die JS-Spiegelung. Vorher
gab es vier Definitionen von „scharf" in vier Dateien, zwei davon lebendig und in der Behandlung
fehlender Daten genau gegenlaeufig.
"""
import json
import math
from pathlib import Path

import pytest

import sharp_gate as SG

CASES = json.loads((Path(__file__).parent / "fixtures" / "sharp_gate_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("c", CASES, ids=[c["name"] for c in CASES])
def test_vertrag(c):
    assert SG.is_sharp(c["score"]) is c["sharp"], c["warum"]


def test_wilson_zieht_sich_mit_der_stichprobe_zusammen():
    # Dieselbe rohe Quote, verschiedene Stichproben -> die Untergrenze wandert nach oben.
    lo = SG.wilson_lb(5, 9)      # 55.6%
    hi = SG.wilson_lb(500, 900)  # 55.6%
    assert lo < 0.5 < hi
    assert math.isclose(SG.wilson_lb(0, 0), 0.0)


def test_abgeleitete_form_gleicht_der_rohen():
    # Das Frontend reicht {n, hit, avgClv} durch, der Tracker {n, wins, clvSumPP}. Gleiches Urteil.
    roh = {"n": 60, "wins": 42, "clvSumPP": 120.0, "pnl": 5}
    abgeleitet = {"n": 60, "hit": 42 / 60, "avgClv": 2.0, "pnl": 5}
    assert SG.is_sharp(roh) == SG.is_sharp(abgeleitet) is True


def test_unbekannter_pnl_ist_kein_verlierer():
    assert SG.is_confirmed_loser({"n": 10, "wins": 8}) is False
    assert SG.is_confirmed_loser({"n": 10, "wins": 8, "pnl": 0}) is False
    assert SG.is_confirmed_loser({"n": 10, "wins": 8, "pnl": -1}) is True
