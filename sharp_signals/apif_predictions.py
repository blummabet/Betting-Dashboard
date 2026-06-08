"""
sharp_signals/apif_predictions.py — Externes Modell als Cross-Check

Konzept:
  API-Football hat ein eigenes Pricing-Modell für 1X2 (`/predictions`),
  unabhängig von unserem Skellam+Elo Hybrid und unabhängig von Pinnacle.
  Drittes Modell = echter externer Sanity-Check.

  Vergleich pro gepicktem Outcome:
    sharp_p      = Pinnacle implied (devigged)
    apif_p       = API-Football's implied
    diff_pp      = (apif_p - sharp_p) × 100

  Score-Direction:
    Pick auf X, APIF gibt X MEHR Wahrscheinlichkeit als Pinnacle
        → confirmatory positiv (externes Modell bestätigt unseren Pick)
    Pick auf X, APIF gibt X DEUTLICH WENIGER als Pinnacle
        → warnend negativ (externes Modell widerspricht)

  Magnitude:
    < 5pp Abweichung    → ignoriert (Rauschen)
    5-10pp              → moderater Score (1.0-2.0pp)
    10-20pp             → starker Score (2.0-3.0pp)
    > 20pp              → wahrscheinlich Daten-Anomalie, ignoriert

  Confidence:
    skaliert mit |diff_pp| im credible range, gecapped bei 0.75.

  Signal ist UNIQUE (kein Anti-Korr-Discount): orthogonal zu allen anderen
  Signalen weil es ein echtes externes Modell vergleicht.

Context erwartet:
    apif_predictions[match_key] = {percent: {home, draw, away}, ...}
    odds_snapshot               = {hw, dr, aw} (Pinnacle für Devig)
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_diff_pp":         5.0,
    "max_credible_pp":    20.0,
    "base_score_pp":       1.0,
    "magnitude_scale":     0.15,
    "confidence_floor":    0.40,
    "confidence_ceil":     0.75,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("apif_predictions_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_1x2(hw: float, dr: float, aw: float):
    if not (hw and dr and aw):
        return None
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return None
    return p_hw/s, p_dr/s, p_aw/s


def _outcome_key(market: str) -> Optional[str]:
    m = (market or "").lower()
    if "heimsieg" in m: return "home"
    if "unentsch" in m: return "draw"
    if "auswärtssieg" in m or "auswartssieg" in m: return "away"
    if "dnb" in m and ("heim" in m or "home" in m): return "home"
    if "dnb" in m and ("ausw" in m or "away" in m): return "away"
    return None


class ApifPredictionsSignal(Signal):
    """
    Externes-Modell-Cross-Check. Feuert nur für 1X2/DNB-Picks und nur wenn
    sowohl Pinnacle als auch API-Football-Predictions verfügbar sind.
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "apif_predictions"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key(pick.get("market", ""))
        if not outcome:
            return None

        mk = context.get("matchKey")
        preds = (context.get("apif_predictions") or {}).get(mk)
        if not preds:
            return None
        percent = preds.get("percent") or {}
        apif_p = percent.get(outcome)
        if apif_p is None:
            return None

        snap = context.get("odds_snapshot") or {}
        sharp = _devig_1x2(snap.get("hw"), snap.get("dr"), snap.get("aw"))
        if sharp is None:
            return None
        sharp_p = {"home": sharp[0], "draw": sharp[1], "away": sharp[2]}[outcome]

        diff_pp = (apif_p - sharp_p) * 100.0   # positiv = APIF höher als Pinnacle
        abs_diff = abs(diff_pp)

        if abs_diff < self._t["min_diff_pp"]:
            return None
        if abs_diff > self._t["max_credible_pp"]:
            return None   # Daten-Anomalie

        # Direction: APIF > Pinnacle für unser Outcome → confirmatory (positiv)
        direction = 1.0 if diff_pp > 0 else -1.0
        extra = (abs_diff - self._t["min_diff_pp"]) * self._t["magnitude_scale"]
        score = direction * (self._t["base_score_pp"] + extra)

        # Confidence skaliert moderat mit Bias-Größe
        conf_raw = self._t["confidence_floor"] + abs_diff * 0.015
        confidence = min(self._t["confidence_ceil"], conf_raw)

        side_de = {"home": "Heim", "draw": "X", "away": "Auswärts"}[outcome]
        if diff_pp > 0:
            evidence = (f"📊 API-Football sieht {side_de} um {abs_diff:.1f}pp "
                        f"höher als Pinnacle → bestätigt Pick")
        else:
            evidence = (f"📊 API-Football sieht {side_de} um {abs_diff:.1f}pp "
                        f"niedriger als Pinnacle → externes Modell warnt")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "outcome":  outcome,
                "apif_p":   round(apif_p, 4),
                "sharp_p":  round(sharp_p, 4),
                "diff_pp":  round(diff_pp, 2),
                "advice":   preds.get("advice"),
            },
        )
