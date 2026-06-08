"""
sharp_signals/h2h_pattern.py — Head-to-Head Pattern als Pick-Adjustment

Konzept:
  Direkte Vergleiche zeigen oft persistente Spielstil-Konflikte (Tiki-Taka vs
  Konter, Höhe-Vorteile, mentaler Bonus). Wenn ein Team in ≥5 H2H-Spielen
  dominiert hat (≥60% Win-Rate inkl. Draws), ist das ein Indikator.

  Sample-Size-Anforderung: ≥5 Spiele. Darunter Signal zu rauschig.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_h2h_games":      5,
    "dominance_threshold": 0.55,   # ≥55% Win-Rate als Dominanz
    "score_scale_pp":     8.0,     # bei 70% Win-Rate: ~1.6pp Score
    "min_signal_pp":      0.8,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("h2h_pattern") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _pick_side(market: str) -> int:
    m = (market or "").lower()
    if "heimsieg" in m: return +1
    if "dnb" in m and ("heim" in m or "home" in m): return +1
    if "ah heim" in m: return +1
    if "doppelte chance" in m and "— 1x" in m: return +1
    if "auswärtssieg" in m or "auswartssieg" in m: return -1
    if "dnb" in m and ("ausw" in m or "away" in m): return -1
    if "ah auswärts" in m or "ah auswarts" in m: return -1
    if "doppelte chance" in m and "— x2" in m: return -1
    return 0


class H2HPatternSignal(Signal):
    """
    H2H Win-Rate-basiertes Signal.

    Context erwartet:
      h2h: { games, homeWins, draws, awayWins }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "h2h_pattern"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None

        h2h = context.get("h2h") or {}
        games = h2h.get("games", 0)
        if games < self._t["min_h2h_games"]:
            return None

        home_wins = h2h.get("homeWins", 0)
        draws     = h2h.get("draws", 0)
        away_wins = h2h.get("awayWins", 0)

        # Win-Rate-equivalent für die gepickte Seite (inkl. Draws teilweise)
        # Heim-Seite: Heimsiege voll, Draws halb (DC 1X / DNB-Logik)
        if side == +1:
            picked_rate = (home_wins + 0.5 * draws) / games
        else:
            picked_rate = (away_wins + 0.5 * draws) / games

        # Score = (rate - 0.5) × scale → bei 0.7 rate → 0.2 × 8 = +1.6pp
        score = (picked_rate - 0.5) * self._t["score_scale_pp"]

        if abs(score) < self._t["min_signal_pp"]:
            return None

        # Confidence steigt mit Sample-Size
        confidence = min(0.85, 0.45 + 0.04 * min(games, 10))

        oc_label = "Heim" if side == +1 else "Auswärts"
        ev = (f"⚔️ H2H {games} Spiele: "
              f"{home_wins}H-{draws}X-{away_wins}A · "
              f"{oc_label}-Rate {picked_rate*100:.0f}%")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "games":       games,
                "home_wins":   home_wins,
                "draws":       draws,
                "away_wins":   away_wins,
                "picked_rate": round(picked_rate, 3),
                "pick_side":   "home" if side == 1 else "away",
            },
        )
