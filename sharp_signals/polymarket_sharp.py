"""
sharp_signals/polymarket_sharp.py — Polymarket als zweiter Sharp-Anker

Konzept:
  Polymarket ist ein dezentraler Prognose-Markt mit hohem Crypto-Volumen.
  Im Gegensatz zu Soft-Books (Public-Bias) sind Polymarket-Trader oft selbst
  scharf — manche Crypto-Funds machen dort 6-stellige Positions.

  Wenn Polymarket UND Pinnacle in derselben Richtung zeigen → 2 Sharp-Quellen
  bestätigen sich → höhere Confidence für den Pick.
  Wenn Polymarket gegen Pinnacle steht → eine Quelle liegt daneben →
  konservatives Signal (kein BET).

Volume-Gating: nur signifikant wenn polymarket_vol ≥ MIN_VOL_USDC.
Pre-Tournament-Märkte haben oft niedriges Volume → Signal überspringt sie.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, poly_volumen


DEFAULT_THRESHOLDS = {
    "min_volume_usdc":   5000,
    "min_diff_pp":       2.5,   # Polymarket vs Pinnacle implied
    "score_scale_pp":    0.6,   # pp pro pp Diff
    "max_signal_pp":     4.0,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("polymarket_sharp") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_1x2(hw, dr, aw):
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


def _outcome_key_from_market(market: str) -> Optional[str]:
    m = (market or "").lower()
    if "heimsieg" in m: return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m: return "aw"
    if "unentsch" in m: return "dr"
    if "dnb" in m and ("heim" in m or "home" in m): return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m): return "aw"
    return None


class PolymarketSharpSignal(Signal):
    """
    Polymarket-implied vs Pinnacle-implied für 1X2-/DNB-Picks.

    Context erwartet:
      odds_snapshot: { hw, dr, aw }  # Pinnacle
      poly_snapshot: { poly_hw, poly_dr, poly_aw, poly_vol }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "polymarket_sharp"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        # Pinnacle-Snap (devigt) als Anker
        snap = context.get("odds_snapshot") or {}
        pinn_p = _devig_1x2(snap.get("hw"), snap.get("dr"), snap.get("aw"))
        if pinn_p[0] is None:
            return None

        # Polymarket implied probs (rohe Markt-Preise, schon prob-like)
        poly = context.get("poly_snapshot") or {}
        p_hw, p_dr, p_aw = poly.get("poly_hw"), poly.get("poly_dr"), poly.get("poly_aw")
        # 06.09.2026: liest jetzt `vol` UND `poly_vol` (s. base.poly_volumen). Vorher stand hier
        # `poly.get("poly_vol", 0)` — ein Feld, das die Produktion nie schreibt. Dieses Signal
        # hat deswegen nie gefeuert.
        vol = poly_volumen(poly)
        if None in (p_hw, p_dr, p_aw):
            return None
        if vol is None or vol < self._t["min_volume_usdc"]:
            return None  # kein bekanntes Volumen oder zu wenig Geld dahinter

        # Normalisieren (Polymarket-Implied sum ≈ 1.0 - 1.05)
        s = p_hw + p_dr + p_aw
        if s <= 0:
            return None
        poly_p = (p_hw/s, p_dr/s, p_aw/s)

        idx = {"hw": 0, "dr": 1, "aw": 2}[outcome]
        diff_pp = (poly_p[idx] - pinn_p[idx]) * 100.0

        if abs(diff_pp) < self._t["min_diff_pp"]:
            return None

        # Positive Diff = Polymarket sieht Outcome wahrscheinlicher → bestätigt Pick
        # Negative Diff = Polymarket sieht weniger wahrscheinlich → warnt
        score = diff_pp * self._t["score_scale_pp"]
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

        # Confidence steigt mit Volume + Diff-Größe
        vol_factor = min(1.0, vol / 50000.0)
        confidence = min(0.90, 0.50 + 0.15 * vol_factor + abs(diff_pp) * 0.03)

        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts"}[outcome]
        direction = "bestätigt" if diff_pp > 0 else "widerspricht"
        ev = (f"🟣 Polymarket ({oc_label}) {direction} Pinnacle: "
              f"Poly {poly_p[idx]*100:.0f}% vs Pinn {pinn_p[idx]*100:.0f}% "
              f"· Vol ${vol/1000:.0f}k")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "outcome":       outcome,
                "diff_pp":       round(diff_pp, 2),
                "poly_implied":  round(poly_p[idx], 4),
                "pinn_implied":  round(pinn_p[idx], 4),
                "volume_usdc":   vol,
            },
        )
