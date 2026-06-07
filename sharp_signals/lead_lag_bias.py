"""
sharp_signals/lead_lag_bias.py — Pinnacle Lead-Lag gegenüber Soft-Books

Konzept (Lucas 07.06.2026):
  Pinnacle ist der schärfste Buchmacher. Wenn Pinnacle eine Quote ändert
  (z.B. Heim von 2.10 → 1.85), reagiert sharp money als erstes. Soft-Books
  (William Hill, Bet365, Unibet, …) ziehen mit Verzögerung von Minuten bis
  Stunden nach.

  In dem Lag-Fenster ist die Pinnacle-Quote bereits "korrekt" (scharfer Preis),
  und die Soft-Book-Quoten noch "alt". Wenn wir auf Pinnacle-Niveau wetten,
  haben wir die scharfe Quote — bevor Konsens-Bookies sie korrigieren.

Zwei Stufen des Signals:

  EARLY (Pinnacle moved, Soft-Books NOT yet):
    → starkes Signal in Pinnacle's Bewegungsrichtung
    → Bewertung: bis zu +score je nach Pinnacle-Move-Größe

  CONFIRMED (Pinnacle moved, Soft-Books followed):
    → die These ist bestätigt — Sharp-Pressure war echt
    → noch stärkeres Signal weil mehrere Bookies "einig" sind
    → Bewertung: höherer score als EARLY

Implied Probabilities (devigt) werden verglichen, NICHT rohe Quoten —
weil verschiedene Bookies unterschiedliche Margins haben.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sharp_signals.base import Signal, SignalResult


# Schwellen — alle via cocobet_config.json profiles.<active>.lead_lag.* überschreibbar
DEFAULT_THRESHOLDS = {
    # Min. Pinnacle-Move (in pp implied prob) damit das Signal triggert
    "pinn_min_move_pp":    1.5,
    # Lookback-Fenster für Pinnacle-Move (Stunden)
    "pinn_lookback_h":     24,
    # Soft-Book Lag-Schwelle: wenn Soft-Move < lag_ratio × Pinn-Move → EARLY
    "soft_lag_ratio":      0.5,
    # Score-Beiträge in pp gegen den Markt — werden vom combiner gewichtet
    "early_base_score_pp":     2.5,
    "confirmed_base_score_pp": 4.0,
    # Confidence-Boost wenn mehrere Soft-Books bestätigen
    "multi_soft_bonus":    0.15,
}


def _load_thresholds() -> dict:
    """Lädt Schwellen aus cocobet_config.json mit Defaults als Fallback."""
    try:
        import json, os
        from pathlib import Path
        raw_path = Path(__file__).parent.parent / "cocobet_config.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("lead_lag") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _devig_implied(hw: float, dr: float, aw: float) -> tuple[float, float, float]:
    """
    Devigt eine 1X2-Quote (verhältnismäßige Proportional-Devigging).
    Returns implied probabilities ohne Margin.
    """
    if not (hw and dr and aw):
        return (None, None, None)
    p_hw, p_dr, p_aw = 1.0/hw, 1.0/dr, 1.0/aw
    s = p_hw + p_dr + p_aw
    if s <= 0:
        return (None, None, None)
    return (p_hw/s, p_dr/s, p_aw/s)


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # ISO 8601 mit oder ohne Z
        s = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _select_outcome_key_from_market(market: str) -> Optional[str]:
    """
    Welches 1X2-Outcome wird vom Pick bewettet?
    Mappt freie Market-Strings auf hw/dr/aw.
    Nicht-1X2-Märkte (O/U, AH, BTTS) → None (Signal nicht anwendbar).
    """
    m = (market or "").lower()
    if "heimsieg" in m or m == "1":
        return "hw"
    if "auswärtssieg" in m or "auswartssieg" in m or m == "2":
        return "aw"
    if "unentsch" in m or m == "x":
        return "dr"
    # DNB Heim/Auswärts ist verwandt mit hw/aw (Draw = Push)
    if "dnb" in m and ("heim" in m or "home" in m):
        return "hw"
    if "dnb" in m and ("ausw" in m or "away" in m):
        return "aw"
    return None


class LeadLagBiasSignal(Signal):
    """
    Pinnacle Lead-Lag vs Soft-Books für 1X2-/DNB-Picks.

    Nutzt context["odds_history"] (eine Liste {ts, hw, dr, aw, bk}).
    Für die gepickte Outcome-Seite (hw/dr/aw):
      1) Berechne Pinnacle-Move in den letzten lookback_h Stunden
      2) Berechne Soft-Book-Move im gleichen Fenster (William Hill, Unibet, …)
      3) Wenn Pinn-Move ≥ Schwelle UND Soft-Move signifikant kleiner → EARLY
      4) Wenn Pinn-Move ≥ Schwelle UND Soft-Move ähnlich groß → CONFIRMED
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "lead_lag_bias"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        # Nur für 1X2-/DNB-Märkte sinnvoll
        outcome = _select_outcome_key_from_market(pick.get("market", ""))
        if not outcome:
            return None

        history = context.get("odds_history") or []
        if len(history) < 2:
            return None

        snap_ts = _parse_ts(context.get("snapshot_ts") or "") or datetime.now(timezone.utc)
        lookback_seconds = self._t["pinn_lookback_h"] * 3600

        # Partitioniere History nach Bookmaker
        by_bk: dict[str, list[dict]] = {}
        for e in history:
            bk = (e.get("bk") or "?").lower()
            by_bk.setdefault(bk, []).append(e)

        # Sortiere chronologisch
        for bk in by_bk:
            by_bk[bk].sort(key=lambda x: x.get("ts", ""))

        # Pinnacle-Move berechnen
        pinn = by_bk.get("pinnacle") or []
        if len(pinn) < 2:
            return None  # ohne Pinn-History kein Signal

        pinn_move = self._compute_move_pp(pinn, outcome, snap_ts, lookback_seconds)
        if pinn_move is None or abs(pinn_move) < self._t["pinn_min_move_pp"]:
            return None  # keine relevante Pinn-Bewegung

        # Soft-Book-Moves berechnen
        soft_bks = [bk for bk in by_bk.keys() if bk != "pinnacle" and bk != "?"]
        soft_moves = []
        for bk in soft_bks:
            mv = self._compute_move_pp(by_bk[bk], outcome, snap_ts, lookback_seconds)
            if mv is not None:
                soft_moves.append((bk, mv))

        if not soft_moves:
            # Wir haben Pinnacle-Move aber keine Soft-Book-Vergleichsdaten →
            # Vorsicht: kein Signal feuern (wir wüssten nicht ob EARLY oder CONFIRMED)
            return None

        # Welcher Anteil der Soft-Books ist Pinnacle gefolgt?
        # "Gefolgt" = Move in selber Richtung UND Magnitude ≥ lag_ratio × Pinn-Move
        threshold = abs(pinn_move) * self._t["soft_lag_ratio"]
        followed = []
        lagging  = []
        for bk, mv in soft_moves:
            if mv * pinn_move > 0 and abs(mv) >= threshold:
                followed.append((bk, mv))
            else:
                lagging.append((bk, mv))

        # Score-Richtung: positiv = Pinnacle macht Outcome wahrscheinlicher
        # (Quote fällt → implied prob steigt → Signal sagt "BET das Outcome")
        # Für den picker-side bedeutet positives pinn_move auf hw, dass Heim
        # wahrscheinlicher wird — wenn der Pick auf Heim ist, ist das gut.
        direction = 1.0 if pinn_move > 0 else -1.0

        # EARLY: mehrheitlich Soft-Books haben nicht nachgezogen
        # CONFIRMED: mehrheitlich haben nachgezogen
        is_confirmed = len(followed) >= len(lagging) and len(followed) > 0
        is_early     = not is_confirmed and len(lagging) > 0

        base_score = (self._t["confirmed_base_score_pp"] if is_confirmed
                      else self._t["early_base_score_pp"])

        # Magnituden-Skalierung: größerer Pinn-Move → stärkeres Signal
        # (linear bis 5pp Pinn-Move = volle Stärke)
        mag_scale = min(1.5, abs(pinn_move) / 3.0)
        score = direction * base_score * mag_scale

        # Confidence: Anzahl Soft-Books × Bonus + Basis
        confidence = 0.55 + self._t["multi_soft_bonus"] * len(soft_moves)
        confidence = min(0.95, confidence)

        # Evidence-Text für die Card
        oc_label = {"hw": "Heim", "dr": "X", "aw": "Auswärts"}[outcome]
        if is_confirmed:
            soft_str = ", ".join(bk for bk, _ in followed[:2])
            evidence = (f"Pinnacle {oc_label} {pinn_move:+.1f}pp · "
                        f"{soft_str} folgt({len(followed)}) → bestätigt")
        else:
            soft_str = ", ".join(bk for bk, _ in lagging[:2])
            evidence = (f"Pinnacle {oc_label} {pinn_move:+.1f}pp · "
                        f"{soft_str} hinkt nach({len(lagging)}) → früh erkannt")

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "stage":       "confirmed" if is_confirmed else "early",
                "pinn_move_pp": round(pinn_move, 2),
                "soft_moves":   [{"bk": bk, "move_pp": round(mv, 2)}
                                 for bk, mv in soft_moves],
                "outcome":      outcome,
            },
        )

    @staticmethod
    def _compute_move_pp(snaps: list[dict], outcome: str,
                         snap_ts: datetime, lookback_seconds: float) -> Optional[float]:
        """
        Berechnet implied-prob-Bewegung von start_of_lookback bis jetzt
        in Prozentpunkten. Positiv = Outcome wahrscheinlicher geworden.
        """
        if len(snaps) < 2:
            return None

        # Jüngster Snap = "nach"
        last = snaps[-1]
        # Erster Snap im Lookback-Fenster = "vor"
        first_in_window = None
        for s in snaps:
            ts = _parse_ts(s.get("ts") or "")
            if ts is None:
                continue
            age = (snap_ts - ts).total_seconds()
            if age <= lookback_seconds and age >= 0:
                first_in_window = s
                break

        if first_in_window is None:
            return None
        if first_in_window is last:
            return None  # zu wenig Auflösung im Fenster

        p_before = _devig_implied(first_in_window.get("hw"),
                                  first_in_window.get("dr"),
                                  first_in_window.get("aw"))
        p_after  = _devig_implied(last.get("hw"), last.get("dr"), last.get("aw"))

        idx = {"hw": 0, "dr": 1, "aw": 2}[outcome]
        if p_before[idx] is None or p_after[idx] is None:
            return None
        return (p_after[idx] - p_before[idx]) * 100.0
