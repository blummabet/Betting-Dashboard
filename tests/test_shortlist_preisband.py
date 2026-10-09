"""🔴 09.10.2026 (Lucas: „Heute spielenswert … am Anfang recht gut, seit 2 Wochen fast nur Miese").

174 abgerechnete Auto-Plays: im Band 0,60–0,90 n=151 ROI +0,8 %; ausserhalb n=23 ROI −37,9 %
(12 Aussenseiter unter 0,60 mit 2 Treffern). Vorher erlaubte die Auto-Order 0,15–0,92.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shortlist_auto_bet as A  # noqa: E402


def test_band_gilt_fuer_die_echte_order():
    assert (A.MIN_PREIS, A.MAX_PREIS) == (0.60, 0.90)


def test_aussenseiter_und_fast_sicher_werden_nicht_gekauft():
    ok, grund = A.preis_urteil(0.45, 0.45)
    assert not ok and "Mindestpreis" in grund
    ok, grund = A.preis_urteil(0.92, 0.92)
    assert not ok and "Hoechstpreis" in grund
    assert A.preis_urteil(0.72, 0.72)[0]


def test_dasselbe_band_wie_im_public_gate():
    src = (Path(A.__file__).parent / "poly-wallets.js").read_text(encoding="utf-8")
    assert "const PW_PUB_PREIS_MIN=0.60, PW_PUB_PREIS_MAX=0.90;" in src
    assert "_pwImPreisband(r)" in src[src.index("function _pwTermPublicRest"):][:300]


def test_vorregistriert():
    reg = json.loads((Path(A.__file__).parent / "messungen_register.json").read_text(encoding="utf-8"))
    assert any(x["id"] == "poly-preisband" for x in reg["messungen"])
