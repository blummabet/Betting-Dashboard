#!/usr/bin/env python3
"""
pick_constants.py — Single Source of Truth für Pick-Logik
==========================================================

Konstanten die von MEHREREN Modulen verwendet werden müssen:
  · DIRECTION_MAP    — Markt-Name → Direction (homeStrong, awayBias, over, ...)
  · INCOMPATIBLE     — Set von Direction-Paaren die nicht gleichzeitig BET sein können
  · ABWAEGEN_SAFER_*  — Reihenfolge-Regeln für Hero-Sort

WICHTIG: Wird sowohl von Python (direkt import) als auch von JS (via JSON-Mirror)
gelesen. Bei Änderungen IMMER auch pick_constants.json regenerieren:

    python pick_constants.py --dump-json > pick_constants.json

Erweiterungen für Liga-Saison gehen einfach: neue Markt-Namen + Directions
einfügen, das war's. Kein Code-Touch nötig.
"""
from __future__ import annotations
import json
import sys


# ─────────────────────────────────────────────────────────────────────────────
#  DIRECTION_MAP — welche Tendenz hat ein Markt-Pick?
# ─────────────────────────────────────────────────────────────────────────────
# Mögliche Directions:
#   homeStrong  — eindeutiger Heimsieg/Heim-Vorsprung (Heimsieg, AH Heim, DNB H)
#   homeBias    — Heim-Tendenz inkl. Remis (Doppelte Chance 1X)
#   awayStrong  — eindeutiger Auswärtssieg/Auswärts-Vorsprung
#   awayBias    — Auswärts-Tendenz inkl. Remis (Doppelte Chance X2)
#   drawOnly    — explizit Unentschieden
#   decisive    — kein Remis (Doppelte Chance 12)
#   over        — Tore über Linie (inkl. BTTS Ja)
#   under       — Tore unter Linie (inkl. BTTS Nein)
DIRECTION_MAP: dict[str, str] = {
    # ── 1X2 ──
    "Heimsieg":                   "homeStrong",
    "Auswärtssieg":               "awayStrong",
    "Unentschieden":              "drawOnly",
    # ── Doppelte Chance ──
    "Doppelte Chance — 1X":       "homeBias",
    "Doppelte Chance — X2":       "awayBias",
    "Doppelte Chance — 12":       "decisive",
    # ── Asian Handicap (alle Linien) ──
    "AH Heim −0.25":              "homeStrong",
    "AH Heim −0.5":               "homeStrong",
    "AH Heim −0.75":              "homeStrong",
    "AH Heim −1.0":               "homeStrong",
    "AH Heim −1.25":              "homeStrong",
    "AH Heim −1.5":               "homeStrong",
    "AH Heim −1.75":              "homeStrong",
    "AH Heim −2.0":               "homeStrong",
    "AH Heim −2.25":              "homeStrong",
    "AH Auswärts +0.25":          "awayStrong",
    "AH Auswärts +0.5":           "awayStrong",
    "AH Auswärts +0.75":          "awayStrong",
    "AH Auswärts +1.0":           "awayStrong",
    "AH Auswärts +1.25":          "awayStrong",
    "AH Auswärts +1.5":           "awayStrong",
    "AH Auswärts +1.75":          "awayStrong",
    "AH Auswärts +2.0":           "awayStrong",
    "AH Auswärts +2.25":          "awayStrong",
    # ── DNB ──
    "DNB: Heimteam":              "homeStrong",
    "DNB: Auswärtsteam":          "awayStrong",
    # ── Over/Under Tore ──
    "Über 0.5 Tore":              "over",
    "Über 1.5 Tore":              "over",
    "Über 2.5 Tore":              "over",
    "Über 3.5 Tore":              "over",
    "Über 4.5 Tore":              "over",
    "Unter 0.5 Tore":             "under",
    "Unter 1.5 Tore":             "under",
    "Unter 2.5 Tore":             "under",
    "Unter 3.5 Tore":             "under",
    "Unter 4.5 Tore":             "under",
    # ── BTTS ──
    "Beide Teams treffen":        "over",
    "Beide Teams treffen — Ja":   "over",
    "Beide Teams treffen — Nein": "under",
}


# ─────────────────────────────────────────────────────────────────────────────
#  INCOMPATIBLE — welche Direction-Paare sind logisch unvereinbar als BET?
# ─────────────────────────────────────────────────────────────────────────────
# Als Set für O(1)-Lookup. Beide Reihenfolgen werden inkludiert damit
# `(a, b) in INCOMPATIBLE` ohne Tuple-Sortierung funktioniert.
_INCOMPAT_PAIRS = [
    # Heim vs Auswärts/Draw
    ("homeStrong", "awayStrong"),
    ("homeStrong", "awayBias"),
    ("homeStrong", "drawOnly"),
    ("homeBias",   "awayStrong"),
    # Auswärts vs Heim/Draw
    ("awayStrong", "drawOnly"),
    ("awayBias",   "homeStrong"),
    # Decisive vs Draw
    ("decisive",   "drawOnly"),
    # Über vs Unter
    ("over",       "under"),
]
INCOMPATIBLE: set[tuple[str, str]] = set()
for a, b in _INCOMPAT_PAIRS:
    INCOMPATIBLE.add((a, b))
    INCOMPATIBLE.add((b, a))


def are_directions_incompatible(d1: str | None, d2: str | None) -> bool:
    """True wenn d1 und d2 nicht gleichzeitig BET sein können."""
    if not d1 or not d2:
        return False
    return (d1, d2) in INCOMPATIBLE


def get_pick_direction(market: str | None) -> str | None:
    """Returns Direction oder None wenn Markt unbekannt."""
    if not market:
        return None
    return DIRECTION_MAP.get(market)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI: --dump-json gibt JSON für JS-Konsumenten
# ─────────────────────────────────────────────────────────────────────────────
def dump_json() -> dict:
    """JSON-Struktur für JS-Mirror. Kompatibel mit JS Set-Konstruktion."""
    return {
        "_meta": {
            "version":     "1.0",
            "description": "Pick-Logik-Konstanten — auto-generiert aus pick_constants.py",
            "warning":     "Nicht von Hand editieren! Quelle: pick_constants.py",
        },
        "DIRECTION_MAP":   DIRECTION_MAP,
        "INCOMPATIBLE":    [list(pair) for pair in sorted(INCOMPATIBLE)],
    }


if __name__ == "__main__":
    if "--dump-json" in sys.argv:
        print(json.dumps(dump_json(), ensure_ascii=False, indent=2))
    else:
        print(f"pick_constants.py · DIRECTION_MAP: {len(DIRECTION_MAP)} Märkte · "
              f"INCOMPATIBLE: {len(_INCOMPAT_PAIRS)} Paare")
        print(f"\nZum Generieren der JSON-Mirror-Datei:")
        print(f"  python pick_constants.py --dump-json > pick_constants.json")
