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
from sharp_signals.pressure_index import PressureIndexSignal
from sharp_signals.lineup_signal import LineupSignal


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
    PressureIndexSignal(),
    LineupSignal(),
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


# ── Anti-Korrelation: Signal-Gruppen die dasselbe messen ──────────────────
# Wenn mehrere Signale aus derselben Gruppe gleichzeitig triggern, ist das
# meist ein Effekt (nicht 3 unabhängige Beobachtungen). Wir nehmen nur das
# stärkste mit voller Gewichtung, der Rest wird mit CORRELATION_DISCOUNT
# gedämpft.
#
#   sharp_money_family:  alle Signale die auf Pinnacle/Polymarket-Move basieren
#   form_family:         alle Signale die auf Vergangenheits-Form basieren
#   public_family:       alle Signale die auf Public-vs-Sharp-Bias basieren
SIGNAL_GROUPS: dict[str, str] = {
    "lead_lag_bias":      "sharp_money",
    "steam_lag":          "sharp_money",
    "polymarket_sharp":   "sharp_money",
    "form_trend":         "form",
    "xg_strength":        "form",
    "h2h_pattern":        "form",
    "public_static_bias": "public",
    "travel_burden":      "context",
    "injury":             "context",
    "pressure_index":     "context",
    # lineup_signal ist UNIQUE (kein Anti-Korrelations-Discount):
    # T-1h Aufstellungs-Info ist orthogonal zu allen anderen Signalen —
    # die anderen modellieren historische/statische Daten, lineup_signal
    # injiziert die spätestmögliche realtime Wahrheit. Volle Gewichtung.
    "lineup_signal":      "unique",
}
CORRELATION_DISCOUNT = 0.4   # zweites Signal aus selber Gruppe nur zu 40%


def _apply_anti_correlation(signal_outputs: list[dict]) -> list[dict]:
    """
    Gruppiert Signale nach Korrelations-Familie. Pro Gruppe: stärkster Score
    voll, alle weiteren auf CORRELATION_DISCOUNT × Score gedämpft.
    Mutiert die `weighted_score` Felder in-place und gibt die Liste zurück.
    """
    # Sortiere innerhalb jeder Gruppe nach |weighted_score| absteigend
    by_group: dict[str, list[dict]] = {}
    for s in signal_outputs:
        g = SIGNAL_GROUPS.get(s["name"], "unique")
        by_group.setdefault(g, []).append(s)

    for g, members in by_group.items():
        if g == "unique" or len(members) <= 1:
            continue
        members.sort(key=lambda x: abs(x["weighted_score"]), reverse=True)
        for idx, m in enumerate(members):
            if idx == 0:
                continue   # stärkster bleibt voll
            m["weighted_score"] = round(m["weighted_score"] * CORRELATION_DISCOUNT, 2)
            m["correlation_discount_applied"] = CORRELATION_DISCOUNT
    return signal_outputs


def evaluate_signals(pick: dict, context: dict,
                     weights: Optional[dict] = None) -> dict:
    """
    Ruft alle aktiven Signale auf, sammelt die Results, gewichtet sie.

    Anti-Korrelation: Signale aus derselben Gruppe (z.B. Sharp-Money) zählen
    nur das stärkste voll; weitere werden gedämpft (CORRELATION_DISCOUNT).

    Returns:
      {
        "signals": [
          {"name": "lead_lag_bias", "score": +2.5, "confidence": 0.7,
           "evidence": "...", "weight": 1.0, "weighted_score": +2.5,
           "correlation_discount_applied": null | 0.4},
          ...
        ],
        "combined_score_pp":  float,  # gewichteter Score (nach Anti-Korrelation)
        "n_positive_signals": int,    # für Min-Threshold-Logik
        "n_negative_signals": int,
        "highest_confidence": float,
        "evidence_lines":     [str, ...]
      }
    """
    if weights is None:
        weights = load_signal_weights()

    signal_outputs = []
    evidence_lines = []
    max_conf       = 0.0

    for signal in ACTIVE_SIGNALS:
        try:
            result = signal.evaluate(pick, context)
        except Exception as e:
            result = None
            print(f"  ⚠️  Signal {signal.name()} crashed: {e}")
        if result is None:
            continue

        w = get_weight(weights, signal.name())
        weighted_score = result.score * w * result.confidence
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

    # Anti-Korrelation anwenden (in-place auf weighted_score)
    signal_outputs = _apply_anti_correlation(signal_outputs)

    # Combined-Score: sum of weighted_score / sum of effective weights
    # (gewichtet by confidence × weight × discount-effective)
    weighted_sum = sum(s["weighted_score"] for s in signal_outputs)
    sum_of_w = 0.0
    for s in signal_outputs:
        eff_w = s["weight"] * s["confidence"]
        if s.get("correlation_discount_applied"):
            eff_w *= s["correlation_discount_applied"]
        sum_of_w += eff_w
    combined = weighted_sum / sum_of_w if sum_of_w > 0 else 0.0

    n_pos = sum(1 for s in signal_outputs if s["score"] > 0)
    n_neg = sum(1 for s in signal_outputs if s["score"] < 0)

    return {
        "signals":            signal_outputs,
        "combined_score_pp":  round(combined, 2),
        "n_positive_signals": n_pos,
        "n_negative_signals": n_neg,
        "highest_confidence": round(max_conf, 2),
        "evidence_lines":     evidence_lines,
    }
