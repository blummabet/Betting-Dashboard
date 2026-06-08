"""
sharp_signals/travel_burden.py — Anreise + Höhe als Pick-Adjustment

Konzept:
  Long-Haul-Travel (≥ 3000km) + wenig Pause (≤ 3 Tage) + Höhenwechsel (≥ 1500m)
  drücken die Angriffsstärke (xG) eines Teams in den ersten 60-90 Minuten.

  Sportwissenschaftliche Studien quantifizieren −5% bis −18% xG-Reduktion
  je nach Schwere — wir nutzen die gleichen Bucket-Faktoren wie das xG-Modell
  (siehe generate_wm_picks.travel_factor()).

  Killer-Differenzierung: kaum ein Bookmaker modelliert das systematisch.
  Wir haben wm_travel_burden.json mit km/rest_days/alt_shift pro Team und Matchday.

Score-Logik:
  Pick stützt Heim (Heimsieg, DNB Heim, AH Heim, DC 1X):
    + score wenn Auswärts kritisch reist (gepresst)
    - score wenn Heim kritisch reist (eigener Pick gepresst)
  Pick stützt Auswärts (Auswärtssieg, DNB Aus, AH Aus, DC X2):
    + score wenn Heim kritisch reist
    - score wenn Auswärts kritisch reist
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_factor_for_signal": 0.96,  # nur wenn xG-Reduktion ≥ 4%
    "score_scale_pp":        20.0,  # 1.0 - factor → multipliziert
    "altitude_bonus_pp":      0.8,  # extra Score bei Höhenwechsel ≥ 1500m
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("travel_burden") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


# Welche Seite stützt der Pick? +1 = Heim, -1 = Auswärts, 0 = ambivalent
def _pick_side(market: str) -> int:
    m = (market or "").lower()
    # Heim-Seite
    if "heimsieg" in m: return +1
    if "dnb" in m and ("heim" in m or "home" in m): return +1
    if "ah heim" in m: return +1
    if "doppelte chance" in m and "— 1x" in m: return +1
    # Auswärts-Seite
    if "auswärtssieg" in m or "auswartssieg" in m: return -1
    if "dnb" in m and ("ausw" in m or "away" in m): return -1
    if "ah auswärts" in m or "ah auswarts" in m: return -1
    if "doppelte chance" in m and "— x2" in m: return -1
    return 0


def _factor_from_burden(tb_team: dict, matchday: int) -> tuple[float, dict]:
    """
    Rekonstruiert den xG-Discount-Faktor und Metadata aus travel_data Eintrag.
    Same Logik wie generate_wm_picks.travel_factor() — bewusst dupliziert um die
    Signal-Engine eigenständig zu halten.
    """
    if not tb_team or not tb_team.get("legs"):
        return 1.0, {}
    leg = next((l for l in tb_team["legs"] if l.get("matchday_to") == matchday), None)
    if not leg or leg.get("same_venue"):
        return 1.0, {}

    km        = leg.get("km", 0) or 0
    rest_days = leg.get("rest_days", 99) or 99
    alt_shift = abs(leg.get("alt_shift", 0) or 0)
    burden    = (leg.get("burden", "") or "").lower()

    if burden == "critical":   factor = 0.85
    elif burden == "high":     factor = 0.90
    elif burden == "medium":   factor = 0.95
    else:
        if km >= 3000 and rest_days <= 3:   factor = 0.85
        elif km >= 3000 or rest_days <= 3:  factor = 0.90
        elif km >= 1500:                    factor = 0.95
        else:                               factor = 1.0

    if alt_shift >= 1500:
        factor = max(0.80, factor - 0.03)

    return factor, {
        "km":         km,
        "rest_days":  rest_days,
        "alt_shift":  alt_shift,
        "burden":     burden,
    }


class TravelBurdenSignal(Signal):
    """
    Adjustiert Pick-Score basierend auf Anreise + Höhe beider Teams.

    Context erwartet:
      home_id, away_id:    Team-Codes
      matchday:            ST 1/2/3
      travel:              dict aus wm_travel_burden.json {teamId: {...}}
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "travel_burden"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None  # O/U/BTTS/Corners: Travel kein direktes Signal

        travel = context.get("travel") or {}
        home_id = context.get("home_id")
        away_id = context.get("away_id")
        matchday = context.get("matchday")
        if not (home_id and away_id and matchday):
            return None

        f_home, meta_home = _factor_from_burden(travel.get(home_id), matchday)
        f_away, meta_away = _factor_from_burden(travel.get(away_id), matchday)

        min_factor = self._t["min_factor_for_signal"]
        scale      = self._t["score_scale_pp"]
        alt_bonus  = self._t["altitude_bonus_pp"]

        # Nichts berichtenswertes
        if f_home >= min_factor and f_away >= min_factor:
            return None

        # Score-Berechnung
        # Pick stützt Heim (side=+1): Auswärts gepresst (f_away < 1.0) → positiv,
        # Heim gepresst (f_home < 1.0) → negativ
        score = 0.0
        if f_away < min_factor:
            base = (1.0 - f_away) * scale
            if meta_away.get("alt_shift", 0) >= 1500:
                base += alt_bonus
            score += side * base   # +side wenn Gegner gepresst
        if f_home < min_factor:
            base = (1.0 - f_home) * scale
            if meta_home.get("alt_shift", 0) >= 1500:
                base += alt_bonus
            score -= side * base   # eigener Pick gepresst → −side

        if abs(score) < 0.5:
            return None  # netto zu klein

        # Confidence: je größer die Faktor-Diff zwischen Heim+Auswärts, desto klarer
        diff = abs(f_home - f_away)
        confidence = min(0.85, 0.55 + diff * 1.5)

        # Evidence-Text
        parts = []
        if f_away < min_factor:
            burden = meta_away.get("burden", "")
            parts.append(f"Auswärts {meta_away.get('km')}km/{meta_away.get('rest_days')}d "
                         f"({burden})")
        if f_home < min_factor:
            burden = meta_home.get("burden", "")
            parts.append(f"Heim {meta_home.get('km')}km/{meta_home.get('rest_days')}d "
                         f"({burden})")
        alt_notes = []
        if meta_home.get("alt_shift", 0) >= 1500:
            alt_notes.append(f"Heim Höhe +{meta_home['alt_shift']}m")
        if meta_away.get("alt_shift", 0) >= 1500:
            alt_notes.append(f"Auswärts Höhe +{meta_away['alt_shift']}m")
        if alt_notes:
            parts.extend(alt_notes)
        evidence = "✈️ " + " · ".join(parts) if parts else f"Travel-Effekt {score:+.1f}pp"

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "factor_home": round(f_home, 3),
                "factor_away": round(f_away, 3),
                "home":        meta_home,
                "away":        meta_away,
                "pick_side":   "home" if side == 1 else "away",
            },
        )
