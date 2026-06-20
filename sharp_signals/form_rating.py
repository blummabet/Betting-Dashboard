"""
sharp_signals/form_rating.py — Spieler-Rating-Momentum + Defensiv-Solidität

Quelle: fetch_wm_nt_xg.py aggregiert pro Team:
  · ratingAvg       — minutengewichtetes Ø-Spieler-Rating der letzten Spiele
                      (API-Football Match-Rating, ~6.0 schwach … ~7.5 stark)
  · xgSimAgainstAvg — kassiertes xGsim (Defensiv-Solidität, niedrig = solide)

Orthogonal zu xG-Ergebnis und Chancen-Kreation: das Rating bündelt Zweikämpfe,
Pässe, Defensiv-Aktionen in eine Performance-Zahl. Nur Outcome-Märkte
(1X2/DC/DNB/AH) — ein Form-Momentum-Modifikator, keine Tor-Linien-Aussage.

Score = side · [ rating_diff·w_rating − defense_diff·w_def ] · scale
  rating_diff  = heim_rating − ausw_rating          (höher besser)
  defense_diff = heim_xgSimAg − ausw_xgSimAg         (höher = schlechtere Abwehr)
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Optional
from sharp_signals.base import Signal, SignalResult

BASE = Path(__file__).resolve().parent.parent

DEFAULT_T = {
    "min_games":      3,
    "w_rating":       1.0,
    "w_defense":      0.6,
    "scale":          6.0,    # pp pro kombinierter Differenz-Einheit
    "min_signal_pp":  0.8,
    "max_signal_pp":  5.0,
}


def _load_t() -> dict:
    try:
        raw = json.loads((BASE / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = (raw["profiles"].get(active, {}).get("form_rating")) or {}
        return {**DEFAULT_T, **cfg}
    except Exception:
        return dict(DEFAULT_T)


def _pick_side(market: str) -> int:
    m = (market or "").lower()
    if "doppelte chance" in m or "double chance" in m:
        if "1x" in m or "— 1" in m: return +1
        if "x2" in m or "— 2" in m: return -1
    if "heim" in m or "home" in m: return +1
    if "auswärt" in m or "auswarts" in m or "away" in m: return -1
    return 0


class FormRatingSignal(Signal):
    def __init__(self):
        self._t = _load_t()

    def name(self) -> str:
        return "form_rating"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None
        xg = context.get("xg_stats") or {}
        rh, ra = xg.get(home_id) or {}, xg.get(away_id) or {}
        if (rh.get("games", 0) or 0) < self._t["min_games"] or (ra.get("games", 0) or 0) < self._t["min_games"]:
            return None
        rt_h, rt_a = rh.get("ratingAvg"), ra.get("ratingAvg")
        if rt_h is None or rt_a is None:
            return None
        rating_diff = rt_h - rt_a
        # Defensiv-Komponente optional (nur wenn beide xgSimAgainst haben)
        dh, da = rh.get("xgSimAgainstAvg"), ra.get("xgSimAgainstAvg")
        defense_diff = (dh - da) if (dh is not None and da is not None) else 0.0
        combined = rating_diff * self._t["w_rating"] - defense_diff * self._t["w_defense"]
        score = side * combined * self._t["scale"]
        if abs(score) < self._t["min_signal_pp"]:
            return None
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))
        conf = min(0.78, 0.48 + 0.5 * abs(rating_diff))
        ev = (f"📋 Im Form-Rating steht Heim bei {rt_h:.2f}, Auswärts bei {rt_a:.2f} "
              f"— Vorsprung {rating_diff:+.2f}" +
              (f", in der Abwehr {defense_diff:+.2f}" if defense_diff else "") + ".")
        return SignalResult(round(score, 2), round(conf, 2), ev,
                            {"home_rating": rt_h, "away_rating": rt_a,
                             "rating_diff": round(rating_diff, 2),
                             "defense_diff": round(defense_diff, 2)})
