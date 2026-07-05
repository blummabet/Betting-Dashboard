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


# ── Stufenloses Reise-Modell (04.07.2026, Lucas: „nicht zu stark bei milder Reise, nicht zu
# schwach bei tausenden km mit wenig Zeit"). Ersetzt das grobe 4-Stufen-Bucket: Totzone unter
# DEAD_KM (keine Penalty), dann km-Last LINEAR hoch bis KM_FULL (keine frühe Sättigung wie beim
# 0.85-Deckel), MODULIERT durch die Ruhezeit (viel Pause dämpft, wenig verstärkt). So bekommt ein
# 3357-km-Flug mit 6 Tagen Pause fast keinen Malus, ein 2600-km-Trip mit 3 Tagen einen echten. ──
DEFAULT_MODEL = {
    "continuous":   True,
    "dead_km":      1200.0,   # unter dieser eff. Distanz: keine Reise-Penalty (Totzone)
    "km_full":      4000.0,   # ab hier volle km-Last
    "km_max_pp":    0.15,     # max Reduktion aus reiner Distanz (bei rest-Mult 1.0)
    "floor":        0.80,     # härtester Faktor
    "alt_shift_min": 1500,    # Höhenwechsel-Penalty ab
    "alt_penalty":  0.03,     # additiv
    # Ruhezeit-Multiplikator auf die km-Last (≤2 Tage verstärkt, ≥6 dämpft stark)
    "rest_mult":    {"2": 1.30, "3": 1.05, "4": 0.85, "5": 0.60, "6": 0.40},
}


def _load_model_cfg() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("travel_model") or {}
        merged = {**DEFAULT_MODEL, **cfg}
        merged["rest_mult"] = {**DEFAULT_MODEL["rest_mult"], **(cfg.get("rest_mult") or {})}
        return merged
    except Exception:
        return DEFAULT_MODEL


def _rest_mult(rest_days, table: dict) -> float:
    """Ruhezeit → Multiplikator. Clamp auf [2,6]; dazwischen der Tabellenwert."""
    try:
        r = int(round(rest_days))
    except Exception:
        return table.get("5", 0.6)
    r = max(2, min(6, r))
    return float(table.get(str(r), 1.0))


def factor_from_leg(leg: dict) -> tuple[float, dict]:
    """xG-Discount-Faktor (floor–1.0) + Metadata für EIN Reise-Leg.

    Stufenlos (04.07.2026): Faktor = 1 − km_last·rest_mult − höhe. km_last skaliert linear von der
    Totzone (dead_km) bis km_full; rest_mult moduliert nach Ruhezeit. Bucket-Modell nur noch, wenn
    travel_model.continuous=false gesetzt ist (Fallback). Metadata trägt burden-Label unverändert."""
    if not leg or leg.get("same_venue"):
        return 1.0, {}

    km        = leg.get("km", 0) or 0
    eff_km    = leg.get("effective_km", km) or km
    rest_days = leg.get("rest_days", 99) or 99
    alt_shift = abs(leg.get("alt_shift", 0) or 0)
    burden    = (leg.get("burden", "") or "").lower()

    m = _load_model_cfg()

    if m.get("continuous", True):
        dead, full = m["dead_km"], m["km_full"]
        km_frac = 0.0 if full <= dead else max(0.0, min(1.0, (eff_km - dead) / (full - dead)))
        km_pen  = km_frac * m["km_max_pp"] * _rest_mult(rest_days, m["rest_mult"])
        alt_pen = m["alt_penalty"] if alt_shift >= m["alt_shift_min"] else 0.0
        factor  = max(m["floor"], round(1.0 - km_pen - alt_pen, 3))
    else:
        # Fallback: altes 4-Stufen-Bucket
        if burden == "critical":       factor = 0.85
        elif burden == "significant":  factor = 0.90
        elif burden == "moderate":     factor = 0.95
        elif burden in ("low", "none", ""): factor = 1.0
        else:
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
