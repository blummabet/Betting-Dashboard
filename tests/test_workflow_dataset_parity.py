#!/usr/bin/env python3
"""test_workflow_dataset_parity.py — 25.08.2026 (Audit-Befund 07).

Liga tradet seit dem 19.08. real auf Polymarket. Die sechs Analyse-Skripte liefen aber nur in den
MLS- und WM-Workflows — sieben liga_poly_*-Dateien existierten schlicht nicht, und der einzige
Poly-Guard fuer Liga war mit der Begruendung "Liga hat bewusst kein Polymarket" abgeschaltet.
Niemand hat es gemerkt, weil nichts danach gefragt hat.

Dieser Test fragt danach: was fuer MLS im Workflow steht, muss auch fuer Liga drinstehen. Er ist
absichtlich stumpf (Textsuche im YAML) — genau das faellt auf, wenn jemand einen Datensatz vergisst.
"""
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
WF = BASE / ".github" / "workflows"

# Skripte, die je Datensatz laufen muessen, damit die Poly-Flaechen ueberhaupt Daten bekommen.
POLY_SKRIPTE = [
    "fetch_wm_poly_smartmoney.py",
    "build_poly_wallet_ledger.py",
    "poly_coherence.py",
    "poly_settlement_gap.py",
    "poly_markout.py",
    "poly_money_accuracy.py",
]


def _text(name):
    p = WF / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_liga_vollauf_hat_dieselben_poly_schritte_wie_mls():
    liga, mls = _text("update-liga.yml"), _text("update-mls.yml")
    assert liga and mls, "Workflow-Dateien nicht gefunden"
    fehlt = [s for s in POLY_SKRIPTE if s in mls and s not in liga]
    assert not fehlt, f"update-liga.yml fehlen Poly-Schritte, die MLS hat: {fehlt}"


def test_wallet_ledger_laeuft_im_dichten_takt():
    """Der Wallet-Snapshot haelt nur das AKTUELLE Fenster — was der 2h-Lauf nicht wegschreibt,
    ist weg. Zweimal taeglich reicht dafuer nicht."""
    for datei in ("fetch-liga-odds-dense.yml", "fetch-mls-odds-dense.yml"):
        t = _text(datei)
        assert t, f"{datei} nicht gefunden"
        assert "build_poly_wallet_ledger.py" in t, \
            f"{datei} sammelt keine Wallet-Historie — sie entsteht dann nie"


def test_erzeugte_dateien_werden_auch_committet():
    """Ein Schritt, dessen Ergebnis nicht gestaged wird, laeuft umsonst."""
    liga = _text("update-liga.yml")
    for datei in ("liga_poly_wallets.json", "liga_poly_smartmoney.json",
                  "liga_poly_wallet_ledger.json"):
        assert datei in liga, f"{datei} wird in update-liga.yml nie committet"


def test_liga_poly_guard_ist_nicht_abgeschaltet():
    """Der einzige Poly-Guard fuer Liga war hart deaktiviert — deshalb fiel nichts auf.

    Geprueft wird der CODE, nicht der Kommentar: der Guard darf fuer Liga nicht mehr vorzeitig
    aussteigen. (Die alte Begruendung steht bewusst noch als Historie im Docstring.)
    """
    import inspect
    import wm_data_integrity as W
    quelle = inspect.getsource(W.check_wallet_ledger_growing)
    rumpf = quelle.split('"""')[2] if quelle.count('"""') >= 2 else quelle
    assert 'active_dataset() == "liga"' not in rumpf, \
        "Liga steigt immer noch vorzeitig aus — seit dem 19.08. tradet Liga real auf Polymarket"
    assert "Check nicht anwendbar" not in rumpf
