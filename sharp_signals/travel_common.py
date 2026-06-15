"""
sharp_signals/travel_common.py — EINE Quelle für Reise-Last → xG-Discount.

Vorher war diese Logik dupliziert (generate_wm_picks.travel_factor() UND
sharp_signals/travel_burden._factor_from_burden()). Das führte am 15.06.2026 zum
Drift: travel_factor wurde gefixt (Label-Mapping + Carry-over), der Signal-Klon
nicht → die Engine adjustierte anders als der Pick-Bau. Jetzt nur noch hier.

Leg-Schema (compute_wm_travel_burden.py, Base-Camp-Modell): pro Spieltag ein Leg
Base Camp → Stadion mit km, effective_km (km + Carry-over), rest_days, alt_shift,
burden (critical/significant/moderate/low/none).
"""


def factor_from_leg(leg: dict) -> tuple[float, dict]:
    """xG-Discount-Faktor (0.80–1.0) + Metadata für EIN Reise-Leg.

    Befund 3 (15.06.2026): Labels sind critical/significant/moderate/low/none.
    Befund 2: Fallback nutzt effective_km (eigene Strecke + Carry-over), nicht nur km.
    Höhen-Penalty additiv (Stadion-Höhe vs Base-Camp-Höhe)."""
    if not leg or leg.get("same_venue"):
        return 1.0, {}

    km        = leg.get("km", 0) or 0
    eff_km    = leg.get("effective_km", km) or km
    rest_days = leg.get("rest_days", 99) or 99
    alt_shift = abs(leg.get("alt_shift", 0) or 0)
    burden    = (leg.get("burden", "") or "").lower()

    if burden == "critical":
        factor = 0.85
    elif burden == "significant":
        factor = 0.90
    elif burden == "moderate":
        factor = 0.95
    elif burden in ("low", "none", ""):
        factor = 1.0
    else:
        # Fallback (unbekanntes Label): nach effektiver Last selbst beurteilen
        if eff_km >= 3000 and rest_days <= 3:   factor = 0.85
        elif eff_km >= 3000 or rest_days <= 3:  factor = 0.90
        elif eff_km >= 1500:                    factor = 0.95
        else:                                   factor = 1.0

    if alt_shift >= 1500:
        factor = max(0.80, factor - 0.03)

    return factor, {
        "km":           km,
        "effective_km": eff_km,
        "carry_km":     leg.get("carry_km", 0) or 0,
        "rest_days":    rest_days,
        "alt_shift":    alt_shift,
        "burden":       burden,
    }


def leg_for_matchday(tb_team: dict, matchday: int) -> dict | None:
    """Das Reise-Leg eines Teams für einen Spieltag (matchday_to == matchday)."""
    if not tb_team or not tb_team.get("legs"):
        return None
    return next((l for l in tb_team["legs"] if l.get("matchday_to") == matchday), None)
