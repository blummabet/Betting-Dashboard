"""
sharp_signals/freshness_signal.py — Frische-Modell als lernbares Signal (18.06.2026, Lucas)

Konzept:
  Der „Move seit Eröffnung" kann ALT sein. Das Frische-Modell (generate_wm_picks.
  analyze_recent_move) klassifiziert den LETZTEN Bewegungs-Abschnitt der de-viggten
  Pinnacle-Reihe (latest leg, fenster-frei) in confirm / drift / reverse und hängt das
  als pick["freshnessState"] + pick["recentMovePP"] + pick["legSnaps"] an — BEVOR die
  Signal-Engine läuft.

  Dieses Signal liest diesen Zustand und macht ihn LERNBAR: es fließt in pick["signals"]
  → build_signal_ledger → Bayesian-Weight-Update. So lernt das System nach jedem Spiel,
  ob frische Bestätigung wirklich gewinnt und Reverser wirklich verlieren — statt dass die
  Frische nur eine statische Regel bleibt.

  WICHTIG (kein Doppel-Count): die Conviction dämpft sharp_money deterministisch über
  freshnessState (reverse→0, drift→cap) — das bleibt die Conviction-Autorität. Dieses
  Signal zählt in KEINE Conviction-Familie (Name nicht in den Familien-Listen), es speist
  nur den Lern-Loop + signalAdjustmentPP (Verdict-Override). So wirkt Frische genau einmal
  pro Mechanismus.

  Liga-ready: rein zustands-getrieben (kein WM-Spezifikum), config pro Profil. Beim Liga-
  Switch lernt der Bayesian-Loop das Gewicht aus dem dichten Liga-Datenstrom automatisch.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "score_scale":     0.5,    # recentMovePP (pp) × scale → Signal-Score (pp)
    "max_signal_pp":   4.0,    # Cap je Richtung
    "drift_score_pp":  0.0,    # Drift = neutral (Move ruht), niedrige Confidence
    "base_conf":       0.50,
    "conf_per_snap":   0.04,   # mehr Snaps im Leg = mehr Vertrauen
    "max_conf":        0.85,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("freshness_leg") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


class FreshnessLegSignal(Signal):
    """Latest-leg-Frische als lernbares Signal: confirm → +, reverse → −, drift → ~0.

    Liest den schon berechneten Zustand vom Pick (analyze_recent_move lief vorher). Gibt
    None, wenn keine Frische ermittelbar war (Markt nicht mappbar, gepostete Picks, oder
    Nicht-Steam) — None heißt „nicht auswertbar", nicht „neutral"."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "freshness_leg"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        state = pick.get("freshnessState")
        if state not in ("confirm", "drift", "reverse"):
            return None
        rmv = pick.get("recentMovePP")
        if not isinstance(rmv, (int, float)):
            return None
        snaps = pick.get("legSnaps") or 0

        cap = self._t["max_signal_pp"]
        if state == "drift":
            score = self._t["drift_score_pp"]
            ev = f"⏸ Move ruht (Drift, letzter Abschnitt {rmv:+.1f}pp) — kein frisches Geld"
        else:
            # recentMovePP trägt die Richtung schon (+ für Pick / − gegen Pick)
            score = max(-cap, min(cap, rmv * self._t["score_scale"]))
            if state == "confirm":
                ev = f"✅ Frisch bestätigt: Pinnacle {rmv:+.1f}pp im letzten Abschnitt (für den Pick)"
            else:
                ev = f"⚠️ Reverser: frisches Geld {rmv:+.1f}pp im letzten Abschnitt GEGEN den Pick"

        confidence = min(self._t["max_conf"],
                         self._t["base_conf"] + snaps * self._t["conf_per_snap"])
        if state == "drift":
            confidence = min(confidence, 0.5)

        return SignalResult(
            score=round(float(score), 2),
            confidence=round(float(confidence), 2),
            evidence=ev,
            metadata={
                "state":        state,
                "recentMovePP": round(float(rmv), 1),
                "legSnaps":     snaps,
                "legHours":     pick.get("legHours"),
                "flipReady":    bool(pick.get("flipReady")) if pick.get("flipReady") is not None else None,
            },
        )
