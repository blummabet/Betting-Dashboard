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


# ── Der Regler (01.09.2026) ──────────────────────────────────────────────────
# Das binaere Gate warf eine Wallet mit 60% aus 65 Plays (Wilson-UG 49,8%) genauso raus wie eine
# mit 30% aus 8 — und genau diese Bande lieferte out of sample den besten CLV (+0,94pp, n=136).
# Der Regler behebt die FORM, nicht die Schwelle: dieselben harten Ausschluesse, aber zwischen
# 40% und 50% Untergrenze laeuft der Beitrag linear statt zu springen.

@pytest.mark.parametrize("c", CASES, ids=[c["name"] for c in CASES])
def test_vertrag_grade(c):
    if "grade" not in c:
        pytest.skip("Fall ohne erwarteten Grad")
    assert round(SG.sharp_grade(c["score"]), 2) == pytest.approx(c["grade"], abs=0.005), c["warum"]


def test_is_sharp_ist_der_volle_grad():
    """Eine Definition, zwei Lesarten — sonst sagen Push und Conviction Verschiedenes."""
    for c in CASES:
        assert SG.is_sharp(c["score"]) is (SG.sharp_grade(c["score"]) >= 1.0), c["name"]


def test_rampe_ist_monoton():
    """Mehr Beleg darf nie weniger Gewicht bedeuten."""
    vorher = -1.0
    for wins in range(4, 41):                      # gleiche Stichprobe, steigende Trefferzahl
        g = SG.sharp_grade({"n": 40, "wins": wins, "clvSumPP": 40.0})
        assert g >= vorher - 1e-9, f"Grad faellt bei {wins}/40"
        vorher = g
    assert SG.sharp_grade({"n": 40, "wins": 4, "clvSumPP": 40.0}) == 0.0
    assert SG.sharp_grade({"n": 40, "wins": 40, "clvSumPP": 40.0}) == 1.0


def test_harte_ausschluesse_schlagen_die_rampe():
    """Ein Ausschluss ist kein Abschlag: er fuehrt zu 0, nicht zu 'ein bisschen'."""
    gut = {"n": 65, "wins": 39, "clvSumPP": 18.2, "pnl": 457319}
    assert SG.sharp_grade(gut) > 0
    assert SG.sharp_grade({**gut, "clvSumPP": -1.0}) == 0.0        # CLV negativ
    assert SG.sharp_grade({**gut, "pnl": -1}) == 0.0               # bestaetigter Verlierer
    assert SG.sharp_grade({**gut, "n": 7, "wins": 5}) == 0.0       # zu wenig Plays


def test_grad_bleibt_im_band():
    for n in (8, 20, 65, 300):
        for wins in range(0, n + 1):
            g = SG.sharp_grade({"n": n, "wins": wins, "clvSumPP": float(n)})
            assert 0.0 <= g <= 1.0
