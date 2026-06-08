"""
sharp_signals/registry.py — Active-Signal-Registry + Weights

Alle aktiven Signale werden hier instanziert. Lern-Hook:
  signal_weights.json hält pro Signal aktuelle Vertrauenswürdigkeit.
  update_signal_weights.py aktualisiert das nach jedem resolved Pick.

Beim Hinzufügen neuer Signale:
  1. sharp_signals/<new>_signal.py mit Signal-Subclass
  2. Hier in ACTIVE_SIGNALS importieren + instanziieren
  3. signal_weights.json bekommt einen neuen Default-Eintrag (initial weight 1.0)
  4. Test in tests/test_<name>_signal.py
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from sharp_signals.base import Signal, SignalResult
from sharp_signals.lead_lag_bias import LeadLagBiasSignal
from sharp_signals.public_static_bias import PublicStaticBiasSignal
from sharp_signals.travel_burden import TravelBurdenSignal
from sharp_signals.injury_signal import InjurySignal
from sharp_signals.form_trend import FormTrendSignal
from sharp_signals.h2h_pattern import H2HPatternSignal
from sharp_signals.xg_strength import XGStrengthSignal
from sharp_signals.polymarket_sharp import PolymarketSharpSignal
from sharp_signals.steam_lag import SteamLagSignal


# Liste aller aktiv evaluierten Signale.
# Reihenfolge ist nur kosmetisch (Output-Reihenfolge auf der Card).
ACTIVE_SIGNALS: list[Signal] = [
    LeadLagBiasSignal(),
    PublicStaticBiasSignal(),
    TravelBurdenSignal(),
    InjurySignal(),
    FormTrendSignal(),
    H2HPatternSignal(),
    XGStrengthSignal(),
    PolymarketSharpSignal(),
    SteamLagSignal(),
]


def _weights_path() -> Path:
    return Path(__file__).parent.parent / "signal_weights.json"


def load_signal_weights() -> dict:
    """
    Lädt signal_weights.json. Falls nicht vorhanden oder ein Signal noch nicht
    drin ist, default = 1.0.

    Format:
      {
        "lead_lag_bias": {
          "weight": 1.0,
          "n_observations": 0,
          "wins_when_triggered": 0,
          "last_updated": "2026-06-07T..."
        },
        ...
      }
    """
    path = _weights_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_signal_weights(weights: dict) -> None:
    """Schreibt signal_weights.json atomar."""
    path = _weights_path()
    tmp  = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_weight(weights: dict, signal_name: str) -> float:
    """Aktuelles Vertrauen für ein Signal (default 1.0 wenn ungesehen)."""
    entry = weights.get(signal_name) or {}
    w = entry.get("weight")
    return float(w) if isinstance(w, (int, float)) else 1.0


def evaluate_signals(pick: dict, context: dict,
                     weights: Optional[dict] = None) -> dict:
    """
    Ruft alle aktiven Signale auf, sammelt die Results, gewichtet sie.

    Returns:
      {
        "signals": [
          {"name": "lead_lag_bias", "score": +2.5, "confidence": 0.7,
           "evidence": "...", "weight": 1.0, "weighted_score": +2.5},
          ...
        ],
        "combined_score_pp": Float,   # gewichteter Score-Summen (für edge adjustment)
        "highest_confidence": Float,
        "evidence_lines": [str, ...]  # für die Card
      }
    """
    if weights is None:
        weights = load_signal_weights()

    signal_outputs = []
    evidence_lines = []
    weighted_sum   = 0.0
    sum_of_weights = 0.0
    max_conf       = 0.0

    for signal in ACTIVE_SIGNALS:
        try:
            result = signal.evaluate(pick, context)
        except Exception as e:
            # Ein einzelnes Signal darf den ganzen Pick nicht killen
            result = None
            print(f"  ⚠️  Signal {signal.name()} crashed: {e}")
        if result is None:
            continue

        w = get_weight(weights, signal.name())
        weighted_score = result.score * w * result.confidence
        weighted_sum   += weighted_score
        sum_of_weights += w * result.confidence
        max_conf       = max(max_conf, result.confidence)
        evidence_lines.append(f"{signal.name()}: {result.evidence}")

        signal_outputs.append({
            "name":          signal.name(),
            "score":         result.score,
            "confidence":    result.confidence,
            "evidence":      result.evidence,
            "weight":        w,
            "weighted_score": round(weighted_score, 2),
            "metadata":      result.metadata,
        })

    combined = weighted_sum / sum_of_weights if sum_of_weights > 0 else 0.0
    return {
        "signals":            signal_outputs,
        "combined_score_pp":  round(combined, 2),
        "highest_confidence": round(max_conf, 2),
        "evidence_lines":     evidence_lines,
    }
