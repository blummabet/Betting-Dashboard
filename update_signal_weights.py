#!/usr/bin/env python3
"""
update_signal_weights.py — Bayesian Lern-Loop für sharp_signals

Wird nach build_signal_ledger.py aufgerufen:
  · Liest das Lern-Ledger (wm_signal_ledger.json) — je aufgelöster Card-Pick ein
    Snapshot der gefeuerten Signale + Outcome (WIN/LOSS).
  · Für jeden Record mit signals[]: pro Signal eine Beobachtung (won/lost)
  · Bayesian-Update der Weights in signal_weights.json

FIX 12.06.2026: Vorher las dieses Script wm_results.json — das ist aber der
TRADE-P&L der platzierten Polymarket-Bets (Key `bets`, ohne signals[], oft
PENDING), NICHT die aufgelösten Card-Picks. Ergebnis: 0 Beobachtungen, alle
Gewichte blieben ewig 1.0. Die Beobachtungs-Erfassung liegt jetzt in
build_signal_ledger.py; dieses Script konsumiert nur noch den Ledger.

Math (Beta-Binomial mit Prior α=β=2 für "vorsichtigen Start"):
  posterior_mean = (α + wins) / (α + β + n)
  weight = posterior_mean / 0.5   # 0.5 = neutrale Win-Rate-Annahme
  → weight > 1.0 = Signal predicted besser als Coin-Flip
  → weight < 1.0 = Signal ist schlechter als Coin-Flip → Signal-Score wird gedämpft

Smoothing-Idee:
  Erst ab n_observations ≥ MIN_OBSERVATIONS_FOR_TRUST aktualisiert das Update
  spürbar (vorher kleiner Schritt). So überreagiert die Engine nicht auf die
  ersten 3 Spiele.

Run:
  python3 update_signal_weights.py
  → Updates signal_weights.json (commit kommt vom Workflow)
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

# Prior-Parameter (Beta-Binomial)
PRIOR_ALPHA = 2.0
PRIOR_BETA  = 2.0
MIN_OBS_FOR_TRUST = 10  # davor: konservatives Update (50% weight zur Prior)

LEDGER_FILE  = BASE / "wm_signal_ledger.json"
WEIGHTS_FILE = BASE / "signal_weights.json"


def _load_results() -> list[dict]:
    """Lern-Beobachtungen aus dem Signal-Ledger (records[]). Jeder Record hat
    result (WIN/LOSS/VOID) + signals[] (name/score) — genau was update_weights braucht."""
    if not LEDGER_FILE.exists():
        return []
    try:
        d = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return d.get("records") or d.get("picks") or d.get("resolved") or []
    except Exception as e:
        print(f"⚠️  wm_signal_ledger.json laden fehlgeschlagen: {e}")
    return []


def _load_weights() -> dict:
    if not WEIGHTS_FILE.exists():
        return {"_meta": {}}
    try:
        return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"_meta": {}}


def _save_weights(weights: dict) -> None:
    tmp = WEIGHTS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(WEIGHTS_FILE)


def _result_is_win(pick: dict) -> bool | None:
    """True = Win, False = Loss, None = Push/Void/unresolved (kein Lern-Update)."""
    r = (pick.get("result") or "").lower()
    if r == "win":  return True
    if r == "loss": return False
    return None


def update_weights() -> dict:
    """Hauptlogik: Bayesian-Update aller Signal-Weights."""
    weights = _load_weights()
    picks   = _load_results()

    # Counts pro Signal — aus den resolved Picks aggregieren
    # Jedes Mal wenn ein Signal getriggered hat (score != 0), ist das eine
    # Beobachtung. Ob das Signal "richtig lag", entscheidet das pick-Outcome
    # GEWICHTET nach Signal-Direction:
    #   score > 0 = Signal sagte "guter Pick" → Win = predicted correctly
    #   score < 0 = Signal sagte "schlechter Pick" → Loss = predicted correctly
    counts: dict[str, dict] = {}
    for pick in picks:
        outcome = _result_is_win(pick)
        if outcome is None:
            continue
        for s in pick.get("signals") or []:
            name  = s.get("name")
            score = s.get("score", 0.0)
            if not name or score == 0.0:
                continue
            counts.setdefault(name, {"n": 0, "predicted_correctly": 0})
            counts[name]["n"] += 1
            # Signal-Korrektheit:
            #   score > 0 & Win  → korrekt
            #   score < 0 & Loss → korrekt
            #   sonst            → falsch
            predicted_win = score > 0
            if predicted_win == outcome:
                counts[name]["predicted_correctly"] += 1

    # Update jeder Signal-Entry
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for sig_name, c in counts.items():
        n           = c["n"]
        wins        = c["predicted_correctly"]
        losses      = n - wins
        # Posterior Mean mit Prior
        post_mean   = (PRIOR_ALPHA + wins) / (PRIOR_ALPHA + PRIOR_BETA + n)
        # Neutrale Erwartung = 0.5 → Weight relativ dazu
        raw_weight  = post_mean / 0.5

        # Sanity-Bound: weight ∈ [0.3, 1.7] damit ein einzelnes Signal das
        # System nie komplett dominiert oder neutralisiert
        clamped_weight = max(0.3, min(1.7, raw_weight))

        # Smoothing: bei wenig Daten näher zum Prior bleiben
        if n < MIN_OBS_FOR_TRUST:
            blend = n / MIN_OBS_FOR_TRUST   # 0..1
            clamped_weight = 1.0 * (1.0 - blend) + clamped_weight * blend

        prev = weights.get(sig_name) or {}
        weights[sig_name] = {
            "weight":              round(clamped_weight, 3),
            "n_observations":      n,
            "wins_when_triggered": wins,
            "losses_when_triggered": losses,
            "posterior_mean":      round(post_mean, 3),
            "last_updated":        now_iso,
            "notes":               prev.get("notes") or "",
        }

    _save_weights(weights)
    return weights


def main():
    print("📊 update_signal_weights.py")
    weights = update_weights()
    for name, entry in weights.items():
        if name.startswith("_"):
            continue
        if isinstance(entry, dict) and "weight" in entry:
            n = entry.get("n_observations", 0)
            w = entry.get("weight", 1.0)
            wr = entry.get("posterior_mean", 0.5)
            print(f"  · {name}: weight={w:.3f}  (n={n}, posterior={wr:.2f})")


if __name__ == "__main__":
    main()
