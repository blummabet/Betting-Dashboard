#!/usr/bin/env python3
"""
pick_helpers.py — Shared Pick-Verarbeitung
============================================

Helper-Funktionen die von MEHREREN Modulen verwendet werden:
  · is_legitimate_pick(p)      — Single Source of Truth: zählt der Pick fürs Tracking?
  · pick_direction(p)          — Direction-Lookup (delegated to pick_constants)
  · picks_are_incompatible(...) — Cross-Market-Konflikt-Check
  · hero_sort_key(p)           — Sortierung: saferAlt > BET > Edge desc
  · select_hero(picks)         — Wählt den Hero aus einer Pick-Liste

Wird sowohl von Pick-Generierung als auch von Tracking + Renderern verwendet.
Backwards-compatible: ohne pick_constants läuft jeder Caller einfach mit
False/None Default → keine Regression möglich.
"""
from __future__ import annotations

try:
    from pick_constants import (
        DIRECTION_MAP,
        INCOMPATIBLE,
        are_directions_incompatible,
        get_pick_direction,
    )
except ImportError:
    # Soft-Fallback wenn pick_constants nicht importierbar (z.B. CI ohne PYTHONPATH)
    DIRECTION_MAP = {}
    INCOMPATIBLE = set()
    def are_directions_incompatible(d1, d2): return False
    def get_pick_direction(market): return None


# ─────────────────────────────────────────────────────────────────────────────
#  is_legitimate_pick — wird der Pick fürs Tracking gezählt?
# ─────────────────────────────────────────────────────────────────────────────
def is_legitimate_pick(p: dict | None) -> bool:
    """True wenn der Pick fürs Tracking/Display zählt.

    NICHT legitim:
      · trackingExcluded=True (vom Konflikt-Filter markiert)
      · None / leerer dict

    Ein Pick mit Result=WIN/LOSS/VOID ist trotzdem legitim — nur
    trackingExcluded macht ihn illegitim.
    """
    if p is None or not isinstance(p, dict):
        return False
    if p.get("trackingExcluded"):
        return False
    return True


def pick_direction(p: dict | None) -> str | None:
    """Returns Direction des Picks via Market-Lookup."""
    if not p or not isinstance(p, dict):
        return None
    return get_pick_direction(p.get("market"))


def picks_are_incompatible(p_a: dict, p_b: dict) -> bool:
    """True wenn die beiden Picks logisch unvereinbar als gleichzeitige BETs sind."""
    return are_directions_incompatible(pick_direction(p_a), pick_direction(p_b))


# ─────────────────────────────────────────────────────────────────────────────
#  hero_sort_key — Sortier-Logik für Hero-Auswahl
# ─────────────────────────────────────────────────────────────────────────────
def hero_sort_key(p: dict) -> tuple:
    """Sortierreihenfolge für Hero-Selection.

    Tuple-Vergleich: kleinerer Wert wird zuerst gewählt.
      1. saferAlt-Picks bevorzugen (False=0, True=1 → invertiert mit "0 if X else 1")
      2. BET vor ABWÄGEN
      3. Edge descending

    Beispiel:
        sorted(picks, key=hero_sort_key)[0]  → Hero
    """
    has_safer = bool(p.get("saferAltFor"))
    is_bet    = p.get("verdict") == "BET"
    edge_pp   = float(p.get("edgePP") or 0)
    return (
        0 if has_safer else 1,   # safer zuerst
        0 if is_bet    else 1,   # BET zuerst
        -edge_pp,                # höhere Edge zuerst
    )


def select_hero(picks: list, include_abwaegen: bool = True) -> dict | None:
    """Wählt den Hero aus einer Pick-Liste.

    Filtert auto:
      · trackingExcluded raus (is_legitimate_pick)
      · WATCH/STAT raus (nur BET + optional ABWÄGEN)

    Returns: Hero-Pick dict oder None wenn nichts qualifiziert.
    """
    valid_verdicts = {"BET", "ABWÄGEN"} if include_abwaegen else {"BET"}
    candidates = [
        p for p in picks
        if is_legitimate_pick(p) and p.get("verdict") in valid_verdicts
    ]
    if not candidates:
        return None
    return sorted(candidates, key=hero_sort_key)[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Cross-Market-Konflikt-Filter
# ─────────────────────────────────────────────────────────────────────────────
def find_picks_conflicting_with_hero(picks: list, hero: dict) -> list[dict]:
    """Returns Liste von Picks die direktional mit Hero unvereinbar sind.

    Hilfreich für:
      · Renderer-Filter (Secondary-Picks ausblenden)
      · Tracker (als VOID/trackingExcluded markieren)
      · Validator (Errors melden)
    """
    if not hero:
        return []
    hero_dir = pick_direction(hero)
    if not hero_dir:
        return []
    conflicts = []
    for p in picks:
        if p is hero:
            continue
        if not is_legitimate_pick(p):
            continue
        d = pick_direction(p)
        if d and are_directions_incompatible(hero_dir, d):
            conflicts.append(p)
    return conflicts


if __name__ == "__main__":
    # Smoketest
    print("pick_helpers.py smoketest:")
    sample = [
        {"market": "Heimsieg",                "verdict": "BET",     "edgePP": 12, "odds": 2.01},
        {"market": "DNB: Heimteam",           "verdict": "ABWÄGEN", "edgePP": 6,  "odds": 1.46},
        {"market": "Über 1.5 Tore",           "verdict": "BET",     "edgePP": 9,  "odds": 1.40, "saferAltFor": "Über 3.5 Tore"},
        {"market": "AH Auswärts +0.5",        "verdict": "ABWÄGEN", "edgePP": 12, "odds": 1.87},  # inkompatibel mit Heimsieg!
    ]
    hero = select_hero(sample)
    print(f"  Hero: {hero.get('market')} edge={hero.get('edgePP')}pp (saferAltFor={hero.get('saferAltFor')!r})")
    conflicts = find_picks_conflicting_with_hero(sample, hero)
    print(f"  Konflikte: {[c.get('market') for c in conflicts]}")
    assert hero["market"] == "Über 1.5 Tore", "Hero sollte saferAlt-Pick sein"
    print("  ✅ Hero-Sort: saferAlt vor BET-Edge")
