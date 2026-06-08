"""
sharp_signals/xg_strength.py — Expected-Goals als Team-Stärke-Modifier

Konzept:
  Understat liefert pro Team xgForAvg (erwartete eigene Tore) und
  xgAgainstAvg (erwartete Gegentore). Das ist schärfer als reine Tor-Statistik
  weil es Chancen-Qualität misst — nicht Glück/Pech bei Abschlüssen.

  xG-Diff eines Teams = xgFor - xgAgainst
  → hohe Diff = dominant, niedrige = schwach

  Wenn Heim deutlich höhere xG-Diff hat als Auswärts → positiver Score auf
  Heim-Pick. Verfügbar primär für UEFA-Teams (Understat-Coverage).

Mean-Reversion-Notiz:
  Wenn avgScored > xgForAvg → Team über-performt (mehr Tore als Modell erwartet)
  → mean reversion-Risiko. Aktuell nicht eingebaut, könnte als Sub-Signal kommen.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_games":          5,    # mind. 5 xG-Spiele pro Team (echtes xG)
    "min_games_proxy":    5,    # für Form-Proxy
    "score_scale_pp":     2.0,  # pp pro xG-Diff-pp Differenz
    "score_scale_proxy":  1.2,  # Form-Proxy wird gedämpft (kein echtes xG)
    "min_signal_pp":      0.8,
    "max_signal_pp":      6.0,
    "proxy_confidence_max": 0.65,  # cap für Form-derived "xG"
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("xg_strength") or {}
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


class XGStrengthSignal(Signal):
    """
    xG-basierter Team-Stärke-Vergleich.

    Context erwartet:
      home_id, away_id
      xg_stats: { teamId: { xgForAvg, xgAgainstAvg, games } }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "xg_strength"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None

        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None

        # ── 1. Echtes xG bevorzugen wenn beidseitig verfügbar ──
        xg = context.get("xg_stats") or {}
        xh = xg.get(home_id) or {}
        xa = xg.get(away_id) or {}
        h_for, h_ag = xh.get("xgForAvg"), xh.get("xgAgainstAvg")
        a_for, a_ag = xa.get("xgForAvg"), xa.get("xgAgainstAvg")
        h_games = xh.get("games", 0) or 0
        a_games = xa.get("games", 0) or 0

        is_proxy = False
        # ── 2. Fallback auf Form-Proxy wenn echtes xG fehlt ──
        # API-Football hat für CONMEBOL/AFC-Quali keine xG-Statistik. Wir nutzen
        # avgScored/avgConceded als Proxy mit niedriger Confidence — markiert
        # mit is_proxy=True damit Backtest/Lernen es separat behandeln kann.
        if None in (h_for, h_ag, a_for, a_ag) or h_games < self._t["min_games"] or a_games < self._t["min_games"]:
            form = context.get("form") or {}
            fh, fa = form.get(home_id) or {}, form.get(away_id) or {}
            min_proxy = self._t["min_games_proxy"]
            if (fh.get("games", 0) < min_proxy or fa.get("games", 0) < min_proxy):
                return None
            for v in (fh.get("avgScored"), fh.get("avgConceded"),
                      fa.get("avgScored"), fa.get("avgConceded")):
                if v is None:
                    return None
            h_for, h_ag = fh["avgScored"], fh["avgConceded"]
            a_for, a_ag = fa["avgScored"], fa["avgConceded"]
            h_games, a_games = fh["games"], fa["games"]
            is_proxy = True

        home_diff = h_for - h_ag
        away_diff = a_for - a_ag
        relative = home_diff - away_diff

        scale = self._t["score_scale_proxy"] if is_proxy else self._t["score_scale_pp"]
        score = side * relative * scale
        if abs(score) < self._t["min_signal_pp"]:
            return None
        score = max(-self._t["max_signal_pp"], min(self._t["max_signal_pp"], score))

        # Confidence — bei Proxy gecapt
        n_min = min(h_games, a_games)
        confidence = min(0.90, 0.55 + 0.03 * n_min + 0.04 * abs(relative))
        if is_proxy:
            confidence = min(self._t["proxy_confidence_max"], confidence)

        label = "Form-xG (Proxy)" if is_proxy else "xG-Stärke"
        ev = (f"⚡ {label}: Heim {h_for:.2f}-{h_ag:.2f} "
              f"vs Auswärts {a_for:.2f}-{a_ag:.2f} (Δ {relative:+.2f})")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "home_xg_for":     round(h_for, 2),
                "home_xg_against": round(h_ag, 2),
                "away_xg_for":     round(a_for, 2),
                "away_xg_against": round(a_ag, 2),
                "relative_diff":   round(relative, 2),
                "home_games":      h_games,
                "away_games":      a_games,
                "is_proxy":        is_proxy,
                "pick_side":       "home" if side == 1 else "away",
            },
        )
