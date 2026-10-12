"""12.10.2026 (Lucas: „diesen Push kann man auch abdrehen … unnötig für mich"): die
Trades-Meldung „📈 Kumulativer Drift" ist stumm. Erkannt und geloggt wird weiter."""
from pathlib import Path

QUELLE = (Path(__file__).resolve().parent.parent / "detect_wm_sharp_moves.py").read_text(encoding="utf-8")


def test_drift_wird_vor_dem_senden_abgefangen():
    stumm = QUELLE.index('if alert_type == "cumul" and os.environ.get("DRIFT_PUSH", "0") != "1":')
    senden = QUELLE.index("ok   = tg_send(card)")
    assert stumm < senden, "der Riegel muss VOR dem Senden stehen"
    block = QUELLE[stumm:senden]
    assert "_log_move(m, alert_type)" in block and "continue" in block, "loggen, dann ueberspringen"
