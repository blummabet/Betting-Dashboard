"""odds_plausibility.py — ist ein 1X2-Snapshot ein ECHTER Markt oder ein Platzhalter?

13.07.2026 (Lucas: „schau dir den Sharp Radar nochmal an"). Befund: die MLS-History enthielt
Eröffnungs-Snapshots wie hw=1.04 / dr=1.01 / aw=1.04 — Overround **291 %**. Ein echter 1X2-Markt
liegt bei 102–110 %. Das sind Platzhalter der Quellen-API beim Markt-Opening, keine Quoten.

Folgen (alle drei real eingetreten):
  · Sharp Radar zeigte Fake-Mover (PSG „1.02 → 1.40", +37pp)
  · detect_wm_sharp_moves meldete **80,8pp „STEAM"** und hat dafür schon Telegram-Alerts gesendet
  · jede CLV-/Drift-Rechnung auf snaps[0] war verseucht

`odds_open` in {ds}-data.json ist bereits geheilt (fetch_liga_odds friert das Opening kohärent ein).
Verseucht ist die **History** — und genau die lesen Radar und Detektor (`snaps[0]` / `prev`).

Diese Datei ist die EINE Quelle für die Regel. Vorher lag `_plausible_1x2` doppelt in
steam_engine.py und fetch_liga_odds.py — beide delegieren jetzt hierher, damit die Schwellen nie
auseinanderlaufen.

Regel (bewusst konservativ — lieber einen echten Extremmarkt verwerfen als einen Geist melden):
  · alle drei Quoten vorhanden
  · hw ≥ 1.05, aw ≥ 1.05  (kürzer gibt es real praktisch nicht)
  · dr ≥ 1.50            (ein Remis unter 1.50 existiert nicht)
  · Overround 1.00–1.30  (unter 1.0 = Arbitrage-Geschenk = Fehler; über 1.30 = Platzhalter)

Teil-Snapshots (nur hw gesetzt, kein volles 1X2) werden NICHT verworfen — dort lässt sich die
Marge nicht prüfen, und ein Fehlurteil wäre schlimmer als keins.
"""
from __future__ import annotations

MIN_SIDE_ODDS = 1.05
MIN_DRAW_ODDS = 1.50
MIN_OVERROUND = 1.00
MAX_OVERROUND = 1.30


def plausible_1x2(hw, dr, aw) -> bool:
    """True = echter Markt. Nur für VOLLE 1X2-Sätze aussagekräftig."""
    if not (hw and dr and aw):
        return False
    try:
        hw, dr, aw = float(hw), float(dr), float(aw)
    except (TypeError, ValueError):
        return False
    if hw < MIN_SIDE_ODDS or aw < MIN_SIDE_ODDS or dr < MIN_DRAW_ODDS:
        return False
    overround = 1.0 / hw + 1.0 / dr + 1.0 / aw
    return MIN_OVERROUND <= overround <= MAX_OVERROUND


def snap_ok(snap) -> bool:
    """Darf dieser History-Snapshot für Move-/Drift-Rechnungen benutzt werden?

    Teil-Snapshots (kein volles 1X2) → True (nicht beurteilbar, nicht verwerfen).
    Volles 1X2 → nur wenn plausibel.
    """
    if not isinstance(snap, dict):
        return False
    hw, dr, aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
    if not (hw and dr and aw):
        return True
    return plausible_1x2(hw, dr, aw)


def clean_snaps(snaps):
    """Platzhalter aus einer History-Liste werfen — DIE Stelle, an der Geister sterben.

    Wichtig: Reihenfolge bleibt erhalten, damit snaps[0] weiterhin „Opening" heißt (dann eben das
    erste ECHTE Opening) und prev/curr weiterhin echte Nachbarn sind.
    """
    if not snaps:
        return []
    return [s for s in snaps if snap_ok(s)]


def first_plausible(snaps):
    """Erster echter Snapshot (= geheiltes Opening) oder None."""
    for s in (snaps or []):
        if isinstance(s, dict) and s.get("hw") and s.get("dr") and s.get("aw"):
            if plausible_1x2(s["hw"], s["dr"], s["aw"]):
                return s
    return None
