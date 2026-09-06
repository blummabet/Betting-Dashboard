"""
sharp_signals/steam_lag.py — Pinnacle-Move + Polymarket-Lag-Detection

Konzept:
  Steam-Lag = Pinnacle hat sich gerade bewegt (Sharp-Money), aber Polymarket
  hat noch nicht reagiert. Konkret messen wir:
    1. Pinnacle-Move ≥ X pp in den letzten Y Stunden (Sharp-Pressure)
    2. Polymarket-Quote zeigt Edge gegen aktuelle Pinnacle-Quote (Lag)

  Wenn beide Bedingungen erfüllt → Pinnacle ist scharf, Polymarket noch alt →
  positives Signal für den Pinnacle-bewerteten Outcome.

  Unterscheidung zu LeadLagBiasSignal:
    LeadLag = Pinnacle vs William Hill / Unibet (Soft-Books)
    SteamLag = Pinnacle vs Polymarket (Crypto-Markt)
  → komplementäre Signal-Quelle.

Pre-Tournament: Polymarket-Volume oft niedrig → Signal feuert selten.
Tournament-Phase: Volume steigt → Signal wird scharf.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from sharp_signals.base import Signal, SignalResult, poly_volumen, snapshot_am_fensteranfang


DEFAULT_THRESHOLDS = {
    "pinn_min_move_pp":   2.0,
    "pinn_lookback_h":    24,
    "min_poly_volume":    3000,
    "min_lag_edge_pp":    2.0,    # Pinnacle-vs-Poly-Diff für Lag-Trigger
    "base_score_pp":      3.0,
    "magnitude_scale":    0.3,
    "max_signal_pp":      5.0,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("steam_lag") or {}
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


def _parse_ts(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


class SteamLagSignal(Signal):
    """
    Pinnacle-Move + Polymarket-Lag — komplementär zu LeadLagBiasSignal.

    Context erwartet:
      odds_history:  Pinnacle-Snapshots (für Move-Detection)
      odds_snapshot: aktuelle Pinnacle-Quote
      poly_snapshot: aktuelle Polymarket-Quote + Volume
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "steam_lag"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        # Pinnacle-Move im Lookback-Fenster
        history = [e for e in (context.get("odds_history") or [])
                   if (e.get("bk") or "").lower() == "pinnacle"]
        if len(history) < 2:
            return None
        history.sort(key=lambda x: x.get("ts", ""))
        now = datetime.now(timezone.utc)
        lookback = self._t["pinn_lookback_h"] * 3600

        # 06.09.2026 — siehe base.snapshot_am_fensteranfang: ein fehlender Snapshot ist keine
        # fehlende Information, sondern die Aussage „unveraendert". Vorher scheiterten hier
        # 60 von 279 Liga-Picks an einem Fenster, in dem nur der neue Preis stand.
        first_in_window = snapshot_am_fensteranfang(history, now, lookback)
        if first_in_window is None or first_in_window is history[-1]:
            return None

        p_before = _devig_1x2(first_in_window.get("hw"),
                              first_in_window.get("dr"),
                              first_in_window.get("aw"))
        p_after_pinn = _devig_1x2(history[-1].get("hw"),
                                  history[-1].get("dr"),
                                  history[-1].get("aw"))
        idx = {"hw": 0, "dr": 1, "aw": 2}[outcome]
        if p_before[idx] is None or p_after_pinn[idx] is None:
            return None

        pinn_move_pp = (p_after_pinn[idx] - p_before[idx]) * 100.0
        if abs(pinn_move_pp) < self._t["pinn_min_move_pp"]:
            return None

        # Polymarket-Lag: zeigt Polymarket noch alte Quote?
        poly = context.get("poly_snapshot") or {}
        # 06.09.2026: siehe base.poly_volumen — derselbe tote Feldname wie in polymarket_sharp.
        vol = poly_volumen(poly)
        if vol is None or vol < self._t["min_poly_volume"]:
            return None

        p_hw, p_dr, p_aw = poly.get("poly_hw"), poly.get("poly_dr"), poly.get("poly_aw")
        if None in (p_hw, p_dr, p_aw):
            return None
        s_poly = p_hw + p_dr + p_aw
        if s_poly <= 0:
            return None
        poly_p = (p_hw/s_poly, p_dr/s_poly, p_aw/s_poly)

        # Lag-Edge = Differenz aktuelle Pinnacle (scharf) vs Polymarket (alt)
        # Wenn Pinnacle den Outcome jetzt höher sieht als Poly → Poly hängt nach
        lag_diff_pp = (p_after_pinn[idx] - poly_p[idx]) * 100.0

        # Steam-Lag nur wenn:
        # 1. Pinnacle-Move in Richtung des Outcomes (sharp pressure)
        # 2. Polymarket sieht den Outcome noch WENIGER wahrscheinlich (lag)
        # → beide Bedingungen in selber Richtung
        if pinn_move_pp * lag_diff_pp <= 0:
            return None  # nicht beide in selber Richtung
        if abs(lag_diff_pp) < self._t["min_lag_edge_pp"]:
            return None

        direction = 1.0 if pinn_move_pp > 0 else -1.0
        mag_scale = min(1.5, abs(pinn_move_pp) / 3.0)
        score = direction * (self._t["base_score_pp"] + abs(lag_diff_pp) * self._t["magnitude_scale"]) * mag_scale
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

        confidence = min(0.85, 0.55 + abs(lag_diff_pp) * 0.03 + min(0.15, vol / 100000.0))

        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts"}[outcome]
        ev = (f"🔥 Steam-Lag {oc_label}: Pinnacle {pinn_move_pp:+.1f}pp · "
              f"Polymarket hinkt {lag_diff_pp:+.1f}pp nach (Vol ${vol/1000:.0f}k)")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "outcome":       outcome,
                "pinn_move_pp":  round(pinn_move_pp, 2),
                "lag_diff_pp":   round(lag_diff_pp, 2),
                "poly_volume":   vol,
            },
        )
