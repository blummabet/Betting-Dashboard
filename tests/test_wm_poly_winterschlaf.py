"""🔴 09.10.2026 (Lucas: „wieder mal ein fail in einer action" — „💹 WM Poly Update 09:30 UTC",
fünf Push-Runden, rot). Die WM ist seit dem 20.07. winterisiert, aber der Mac-Timer stieß
manage-wm-poly.yml weiter alle 15 Minuten an (131 Läufe in 33 h) — Runner belegt, neun Dateien
mit neuem Zeitstempel, ein Push mehr im Gedränge.
"""
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "manage-wm-poly.yml"


def test_der_job_laeuft_nur_mit_ausdruecklichem_schalter():
    src = WF.read_text(encoding="utf-8")
    assert "if: ${{ vars.WM_POLY_AKTIV == 'true' }}" in src


def test_der_schalter_steht_auf_job_ebene_vor_der_runner_vergabe():
    src = WF.read_text(encoding="utf-8")
    i_job = src.index("monitor-positions:")
    i_if = src.index("if: ${{ vars.WM_POLY_AKTIV")
    i_steps = src.index("steps:", i_job)
    assert i_job < i_if < i_steps
