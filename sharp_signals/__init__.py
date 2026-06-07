"""
sharp_signals — Modulare Pick-Signal-Engine

Architektur:
  · base.py     — SignalResult dataclass + abstract Signal-Interface
  · registry.py — Listet alle aktiven Signale + load_signal_weights()
  · combiner.py — Kombiniert mehrere Signale gewichtet → finaler Adjustment
  · *_signal.py — Einzelne Signal-Implementations (lead_lag_bias, public_static_bias, …)

Lern-Loop:
  generate_wm_picks → ruft evaluate_signals() → schreibt signals[] in jeden Pick
  resolve_wm_results → ruft update_signal_weights → Bayesian-Update der Weights
  signal_weights.json wird kommittet → nächster Cron nutzt frische Weights

Initial werden alle Weights mit 1.0 geseedet. Sobald WM-Spiele resolved sind
(ab 12.06.2026), startet das Lernen automatisch.
"""
from sharp_signals.base import Signal, SignalResult
from sharp_signals.registry import evaluate_signals, load_signal_weights

__all__ = ["Signal", "SignalResult", "evaluate_signals", "load_signal_weights"]
