"""19.07.2026 — STRUKTUR-GUARD gegen die wiederkehrende Platzhalter-Quoten-Bug-Klasse.

Lucas: „ich hasse es, wenn Fehler mehrfach auftauchen." Und genau das ist passiert: „aus
Platzhalter-Quoten (Remis 1.01) wird eine Fake-Fair/-Edge gerechnet" tauchte VIER Mal an
verschiedenen Stellen auf (Sharp Radar 13.07., Geister-Picks 14.07., market_drift 17.07.,
Telegram-Edge-Alerts 19.07.) — jedes Mal, weil jemand die 1X2-De-Vig neu inline schrieb OHNE die
Plausibilitätsprüfung.

Dieser Test macht Schluss damit: er scannt ALLE Top-Level-.py nach dem De-Vig-Fingerabdruck
`1/x + 1/y + 1/z` (drei-Wege-Inverssumme) und verlangt, dass die Datei entweder
`odds_plausibility` benutzt ODER bewusst auf der Allowlist steht (mit Begründung). Eine NEUE
ungeschützte De-Vig an einer fünften Stelle → dieser Test wird rot, bevor sie je ein Alert sendet.

Die kanonische, gegatete De-Vig ist `odds_plausibility.devig_1x2()` — implausibel → None. Wer sie
benutzt, KANN den Fehler nicht mehr machen.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Fingerabdruck einer 1X2-De-Vig: 1/a + 1/b + 1/c (mit Leerzeichen-Toleranz).
_DEVIG = re.compile(r"1\s*/\s*[\w\.\[\]'\"]+\s*\+\s*1\s*/\s*[\w\.\[\]'\"]+\s*\+\s*1\s*/\s*[\w\.\[\]'\"]+")

# Bewusst erlaubt — mit Grund. Wer hier etwas hinzufügt, trifft eine bewusste Entscheidung.
ALLOWLIST = {
    "odds_plausibility.py":            "DIE Quelle der Regel (devig_1x2 + plausible_1x2 selbst)",
    "wm_data_integrity.py":            "Guard: berechnet die Marge, um sie zu PRÜFEN (nicht zu handeln)",
    "generate_wm_picks.py":            "am Pick-Ausgang durch _is_ghost_pick abgesichert (14.07.)",
    "wm_story_angles/underdog_recap.py": "Content (Story-Text), kein Geld/Handel",
    "generate_match_pages.py":           "normalisiert bereits gegatete pinn_*_fair-Werte (Quelle: fetch_poly_prices, dort gefiltert), keine rohe De-Vig",
}


def _py_files():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("tests/") or "/.venv/" in rel or "actions-runner/" in rel:
            continue
        yield rel, p


def test_keine_ungeschuetzte_1x2_devig():
    verstoesse = []
    for rel, p in _py_files():
        src = p.read_text(encoding="utf-8", errors="ignore")
        if not _DEVIG.search(src):
            continue
        if rel in ALLOWLIST:
            continue
        # Nicht allowgelistet → MUSS odds_plausibility benutzen (import ODER devig_1x2/plausible_1x2).
        if "odds_plausibility" in src or "plausible_1x2" in src or "devig_1x2" in src:
            continue
        verstoesse.append(rel)

    assert not verstoesse, (
        "Ungeschützte 1X2-De-Vig gefunden (Platzhalter-Quoten-Bug-Klasse!). Nutze "
        "odds_plausibility.devig_1x2() ODER trage die Datei mit Begründung in die ALLOWLIST ein: "
        + ", ".join(verstoesse))


def test_allowlist_dateien_existieren_noch():
    """Verhindert, dass die Allowlist mit toten Einträgen verrottet."""
    for rel in ALLOWLIST:
        assert (ROOT / rel).exists(), f"Allowlist-Eintrag zeigt auf nicht-existente Datei: {rel}"


def test_devig_1x2_ist_gegatet():
    """Die kanonische De-Vig muss bei Platzhaltern None geben — das ist ihr ganzer Zweck."""
    import odds_plausibility as OP
    assert OP.devig_1x2(2.0, 1.01, 3.5) is None       # Remis-Platzhalter
    assert OP.devig_1x2(2.0, 3.5, 1.04) is None       # Auswärts-Platzhalter
    fair = OP.devig_1x2(2.10, 3.40, 3.30)             # echt
    assert fair and abs(sum(fair.values()) - 1.0) < 1e-6
