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


def _ou_market(market: str):
    """O/U-Markt: returns direction (Über=+1 / Unter=-1) oder None."""
    m = (market or "").lower()
    if "ecken" in m or "corner" in m: return None
    if "über" in m or "uber" in m or "over" in m: return +1
    if "unter" in m or "under" in m: return -1
    return None


def _factor_from_burden(tb_team: dict, matchday: int) -> tuple[float, dict]:
    """xG-Discount + Metadata aus travel_data. Delegiert an travel_common — EINE
    Quelle, geteilt mit generate_wm_picks.travel_factor() (kein Duplikat mehr,
    siehe Drift 15.06.2026)."""
    from .travel_common import factor_from_leg, leg_for_matchday
    leg = leg_for_matchday(tb_team, matchday)
    if not leg:
        return 1.0, {}
    return factor_from_leg(leg)


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
        market = pick.get("market", "")
        side = _pick_side(market)
        ou_dir = _ou_market(market) if side == 0 else None
        if side == 0 and ou_dir is None:
            return None  # BTTS/AH-Sondercases ignorieren (zu indirekt)

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

        # ── O/U-Pfad (NEU 09.06.2026): Reise dämpft Offensive auf BEIDEN Seiten ──
        # Wenn beide Teams Reise-Penalty haben, sinkt erwartete Tor-Summe → Unter-Vorteil.
        # Halbierter Effekt vs 1X2 weil O/U weiter weg von der Reise-Mechanik ist.
        if ou_dir is not None:
            # Summe der "fehlenden" Performance beider Teams (max 0.3 = 30% Penalty)
            home_penalty = max(0, 1.0 - f_home)
            away_penalty = max(0, 1.0 - f_away)
            total_penalty = home_penalty + away_penalty
            if total_penalty < 0.05:
                return None
            # Reise drückt Tore → positiv auf Unter, negativ auf Über
            ou_score = -ou_dir * total_penalty * scale * 0.5   # halber Effekt
            if abs(ou_score) < 0.5:
                return None
            confidence = min(0.70, 0.45 + total_penalty * 1.5)
            parts = []
            if home_penalty > 0:
                parts.append(f"Heim {meta_home.get('km',0)}km/{meta_home.get('rest_days',0)}d")
            if away_penalty > 0:
                parts.append(f"Auswärts {meta_away.get('km',0)}km/{meta_away.get('rest_days',0)}d")
            side_str = "Über" if ou_dir == +1 else "Unter"
            ev = f"✈️ Reise-Erschöpfung dämpft Tore: " + " · ".join(parts) + f" → {side_str}-Bias"
            return SignalResult(
                score=round(ou_score, 2), confidence=round(confidence, 2), evidence=ev,
                metadata={"factor_home": round(f_home, 3), "factor_away": round(f_away, 3),
                          "total_penalty": round(total_penalty, 3), "pick_side": side_str},
            )

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
