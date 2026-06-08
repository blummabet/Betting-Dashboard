"""
sharp_signals/public_static_bias.py — Konsens-Bookmaker vs Pinnacle

Konzept:
  Wenn Pinnacle (sharp) und ein Konsens-Soft-Book (bet365, William Hill, …)
  unterschiedliche implied probabilities für denselben Outcome haben, ist
  das ein direkter Bias-Indikator.

  Public überbettet hw (z.B. +5pp) → die Masse glaubt Heim wahrscheinlicher
  als Pinnacle's sharp Schätzung. Historisch verlieren Public-Konsens-Picks
  → ein Pick AUF hw bei Pinnacle reitet GEGEN den Public-Bias und gewinnt
  meistens (Pinnacle hat häufiger recht).

  Score-Direction:
    Pick auf X mit Public-Bias_X > 0  →  positiver Score (wir contrarian zu Public)
    Pick auf X mit Public-Bias_X < 0  →  negativer Score (wir mit Public → no edge)

Migration von generate_wm_picks.compute_public_bias() ins neue Signal-Interface.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_bias_pp":      3.0,   # darunter zu rauschig
    "max_credible_pp": 15.0,   # darüber wahrscheinlich Daten-Anomalie
    "base_score_pp":    1.8,   # Score-Beitrag bei moderatem Bias (5pp)
    "magnitude_scale":  0.4,   # weiterer Score pro pp Bias über min_bias
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("public_bias") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_1x2(hw: float, dr: float, aw: float) -> tuple[float, float, float] | tuple[None, None, None]:
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


def _outcome_key_from_market(market: str) -> Optional[str]:
    """Map freier Market-String auf hw/dr/aw — gleiches Pattern wie LeadLag."""
    m = (market or "").lower()
    if "heimsieg" in m: return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m: return "aw"
    if "unentsch" in m: return "dr"
    if "dnb" in m and ("heim" in m or "home" in m): return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m): return "aw"
    return None


class PublicStaticBiasSignal(Signal):
    """
    Vergleicht Pinnacle vs Konsens-Bookmaker für den gepickten Outcome.

    Context erwartet:
      odds_snapshot: { "hw": float, "dr": float, "aw": float,
                       "public_hw": float, "public_dr": float, "public_aw": float,
                       "public_bookmaker": str }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "public_static_bias"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        snap = context.get("odds_snapshot") or {}
        s_hw, s_dr, s_aw = snap.get("hw"), snap.get("dr"), snap.get("aw")
        p_hw, p_dr, p_aw = snap.get("public_hw"), snap.get("public_dr"), snap.get("public_aw")
        if not all([s_hw, s_dr, s_aw, p_hw, p_dr, p_aw]):
            return None

        sharp  = _devig_1x2(s_hw, s_dr, s_aw)
        public = _devig_1x2(p_hw, p_dr, p_aw)
        if sharp[0] is None or public[0] is None:
            return None

        idx = {"hw": 0, "dr": 1, "aw": 2}[outcome]
        diff_pp = (public[idx] - sharp[idx]) * 100.0   # positiv = Public überbettet

        abs_diff = abs(diff_pp)
        if abs_diff < self._t["min_bias_pp"]:
            return None  # zu rauschig
        if abs_diff > self._t["max_credible_pp"]:
            return None  # wahrscheinlich Daten-Anomalie

        # Direction: wenn Public überbettet (diff > 0), reitet ein Pick auf
        # diesem Outcome GEGEN den Public-Konsens → positives Signal
        direction = 1.0 if diff_pp > 0 else -1.0

        # Magnitude: Base + linear über min_bias_pp
        extra = (abs_diff - self._t["min_bias_pp"]) * self._t["magnitude_scale"]
        score = direction * (self._t["base_score_pp"] + extra)

        # Confidence steigt mit Bias-Größe (bis Cap)
        confidence = min(0.85, 0.45 + abs_diff * 0.04)

        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts"}[outcome]
        public_bk = snap.get("public_bookmaker", "Public")
        direction_str = "über-bettet" if diff_pp > 0 else "unter-bettet"
        if diff_pp > 0:
            evidence = (f"{public_bk} {direction_str} {oc_label} um {abs_diff:.1f}pp "
                        f"vs Pinnacle → contrarian Pick")
        else:
            evidence = (f"{public_bk} {direction_str} {oc_label} um {abs_diff:.1f}pp "
                        f"vs Pinnacle → kein Public-Edge")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "outcome":   outcome,
                "diff_pp":   round(diff_pp, 2),
                "sharp_p":   round(sharp[idx], 4),
                "public_p":  round(public[idx], 4),
                "public_bk": public_bk,
            },
        )
