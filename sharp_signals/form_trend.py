"""
sharp_signals/form_trend.py — Form-Trend der letzten 5 Spiele

Konzept:
  Die letzten 5 Spiele eines Teams sind ein direkter Form-Indikator. Wir nutzen:
    · avgScored / avgConceded (Tore-Avg über die Form-Spiele)
    · games (wie viele Spiele in der Form-Datei — Sample-Size-Check)

  Wenn Team A klar bessere Form hat als Team B → Pick auf A erhält positiven
  Score. Bei xG-Übergap (Team über-performt vs Tor-Erwartung) → Mean-Reversion
  als negativer Modifier.

  Im Gegensatz zum Modell-internen xG: hier ist Form direkt erlebbar und
  nachvollziehbar für die Card-Story.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_games":          3,
    "scoring_score_scale": 3.0,    # pp pro Tor-Diff im avgScored
    "conceding_score_scale": 2.5,  # pp pro Tor-Diff im avgConceded (umgekehrtes Vorzeichen)
    "min_signal_pp":      0.8,
    "max_signal_pp":      6.0,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("form_trend") or {}
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


class FormTrendSignal(Signal):
    """
    Form-Differenz der letzten ~5 Spiele für 1X2/DNB/AH/DC-Picks.

    Context erwartet:
      home_id, away_id
      form: { teamId: { games, avgScored, avgConceded } }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "form_trend"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None

        form = context.get("form") or {}
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None

        fh = form.get(home_id) or {}
        fa = form.get(away_id) or {}
        if (fh.get("games", 0) < self._t["min_games"]
                or fa.get("games", 0) < self._t["min_games"]):
            return None

        h_scored = fh.get("avgScored", 0) or 0
        h_conced = fh.get("avgConceded", 0) or 0
        a_scored = fa.get("avgScored", 0) or 0
        a_conced = fa.get("avgConceded", 0) or 0

        # Differenz aus Sicht der gepickten Seite
        # Wenn Pick Heim: Vorteil Heim = (h_scored - a_scored) + (a_conced - h_conced)
        if side == +1:
            scoring_diff = h_scored - a_scored
            conceding_diff = a_conced - h_conced
        else:
            scoring_diff = a_scored - h_scored
            conceding_diff = h_conced - a_conced

        score = (scoring_diff * self._t["scoring_score_scale"]
                 + conceding_diff * self._t["conceding_score_scale"])

        if abs(score) < self._t["min_signal_pp"]:
            return None
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

        # Confidence: höher bei vielen Form-Spielen + großer Diff
        confidence = min(0.85,
            0.50
            + 0.04 * min(fh.get("games", 0), fa.get("games", 0))
            + 0.05 * (abs(scoring_diff) + abs(conceding_diff))
        )

        ev = (f"📈 Form letzte {min(fh['games'], fa['games'])}: "
              f"Heim {h_scored:.1f}:{h_conced:.1f} vs "
              f"Auswärts {a_scored:.1f}:{a_conced:.1f}")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "home_scored":   round(h_scored, 2),
                "home_conceded": round(h_conced, 2),
                "away_scored":   round(a_scored, 2),
                "away_conceded": round(a_conced, 2),
                "home_games":    fh.get("games"),
                "away_games":    fa.get("games"),
                "pick_side":     "home" if side == 1 else "away",
            },
        )
