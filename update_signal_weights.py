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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import cocobet_dataset as D  # noqa: E402
# Dataset-Modus (Single Source: cocobet_dataset): Liga → eigene Liga-Gewichte/-Ledger.
_IS_LIGA = D.is_liga()

# Prior-Parameter (Beta-Binomial)
PRIOR_ALPHA = 2.0
PRIOR_BETA  = 2.0
MIN_OBS_FOR_TRUST = 10  # davor: konservatives Update (50% weight zur Prior)

# 23.06.2026 (Lucas): Runde 1 (alte Engine) aus dem Lern-Loop ausschließen — die ST1-Picks liefen
# teils auf alter Engine und würden die neuen Gewichte verwässern. Ledger behält die Historie
# (Audit), aber das Lernen startet ab Matchday 2. Höher setzen, um Slate weiter einzuschränken.
# Liga hat keine „alte Engine in Runde 1" → ab Spieltag 1 lernen. WM bleibt bei 2.
MIN_LEARN_MATCHDAY = 1 if _IS_LIGA else 2

LEDGER_FILE  = D.file("wm_signal_ledger.json", "liga_signal_ledger.json")
WEIGHTS_FILE = D.file("signal_weights.json", "liga_signal_weights.json")


def _matchday_of(pick: dict) -> int | None:
    """Matchday aus dem Record. Bevorzugt explizites Feld, sonst aus matchKey
    'GKEY-MD-HOME-AWAY' (2. Segment). None wenn nicht ableitbar."""
    md = pick.get("matchday")
    if isinstance(md, int):
        return md
    parts = str(pick.get("matchKey") or pick.get("key") or "").split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _load_results() -> list[dict]:
    """Lern-Beobachtungen aus dem Signal-Ledger (records[]). Jeder Record hat
    result (WIN/LOSS/VOID) + signals[] (name/score) — genau was update_weights braucht.
    Runde < MIN_LEARN_MATCHDAY (alte Engine) wird ausgefiltert."""
    if not LEDGER_FILE.exists():
        return []
    try:
        d = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        recs = d if isinstance(d, list) else (
            d.get("records") or d.get("picks") or d.get("resolved") or [])
    except Exception as e:
        print(f"⚠️  wm_signal_ledger.json laden fehlgeschlagen: {e}")
        return []
    kept, skipped = [], 0
    for r in recs:
        md = _matchday_of(r)
        if md is not None and md < MIN_LEARN_MATCHDAY:
            skipped += 1
            continue
        kept.append(r)
    if skipped:
        print(f"  ⏭️  {skipped} Records aus Runde < MD{MIN_LEARN_MATCHDAY} (alte Engine) übersprungen")
    return kept


def _load_weights() -> dict:
    if not WEIGHTS_FILE.exists():
        return {"_meta": {}}
    try:
        return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"_meta": {}}


PRIORS_FILE = D.file("signal_priors.json", "liga_signal_priors.json")  # dataset-aware (29.06.2026): mls liest mls_signal_priors statt liga (keine Kontamination)


def _load_priors() -> dict:
    """Backtest-als-Prior (nur Liga): {sig: {nPrior, winsPrior}}. Pseudo-Beobachtungen aus
    prime_liga_priors.py, die zu den Live-Counts addiert werden → informierter Start, verblasst mit
    wachsender Live-Stichprobe. Bei WM oder fehlender Datei leer (Verhalten unverändert)."""
    if not _IS_LIGA or not PRIORS_FILE.exists():
        return {}
    try:
        d = json.loads(PRIORS_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if not k.startswith("_")}
    except Exception:
        return {}


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


# Prozess-justierter Outcome ∈ [0,1] (FIX 14.06.2026): 1 = per xG verdient gewonnen,
# 0 = per xG verdient verloren. Trennt Können von Varianz — ein verlorener-aber-
# verdienter Pick (UNLUCKY, z.B. QAT-SUI Over) bestraft die Signale nur teilweise,
# ein glücklicher Win (LUCKY) belohnt sie nur teilweise.
PROCESS_OUTCOME = {
    "JUSTIFIED":     1.0,
    "LUCKY":         0.65,
    "UNLUCKY":       0.35,
    "DESERVED_LOSS": 0.0,
}


def _process_outcome_score(pick: dict) -> float | None:
    """Kontinuierlicher Outcome-Score. Ohne processVerdict (keine Match-xG) Fallback
    aufs binäre Ergebnis (WIN=1.0, LOSS=0.0) → identisch zum alten Verhalten."""
    pv = pick.get("processVerdict")
    if pv in PROCESS_OUTCOME:
        return PROCESS_OUTCOME[pv]
    w = _result_is_win(pick)
    return None if w is None else (1.0 if w else 0.0)


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
        o = _process_outcome_score(pick)   # ∈ [0,1], prozess-justiert (FIX 14.06.2026)
        if o is None:
            continue
        for s in pick.get("signals") or []:
            name  = s.get("name")
            score = s.get("score", 0.0)
            if not name or score == 0.0:
                continue
            counts.setdefault(name, {"n": 0, "predicted_correctly": 0.0})
            counts[name]["n"] += 1
            # Signal-Korrektheit FRAKTIONAL: score>0 sagte „guter Pick" → Gutschrift =
            # wie verdient der Win war (o); score<0 sagte „schlechter Pick" →
            # Gutschrift = wie verdient der Loss war (1-o). Binär-Fallback (o∈{0,1})
            # reproduziert exakt das alte „predicted_win == outcome".
            predicted_win = score > 0
            counts[name]["predicted_correctly"] += o if predicted_win else (1.0 - o)

    # Backtest-Prior (nur Liga): Pseudo-Beobachtungen, die zu den Live-Counts addiert werden.
    # Signale ganz ohne Live-Trigger bekommen trotzdem ihren Prior-Vorsprung.
    priors = _load_priors()
    for sig_name, p in priors.items():
        counts.setdefault(sig_name, {"n": 0, "predicted_correctly": 0.0})

    # Update jeder Signal-Entry
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for sig_name, c in counts.items():
        n_live      = c["n"]
        wins_live   = c["predicted_correctly"]
        pr          = priors.get(sig_name) or {}
        n_prior     = float(pr.get("nPrior") or 0.0)
        wins_prior  = float(pr.get("winsPrior") or 0.0)
        # Prior + Live verschmolzen (Prior verblasst mit wachsendem n_live).
        n           = n_live + n_prior
        wins        = wins_live + wins_prior
        losses      = n - wins
        # Posterior Mean mit Prior
        post_mean   = (PRIOR_ALPHA + wins) / (PRIOR_ALPHA + PRIOR_BETA + n)
        # Neutrale Erwartung = 0.5 → Weight relativ dazu
        raw_weight  = post_mean / 0.5

        # Sanity-Bound: weight ∈ [0.3, 1.7] damit ein einzelnes Signal das
        # System nie komplett dominiert oder neutralisiert
        clamped_weight = max(0.3, min(1.7, raw_weight))

        # Smoothing: bei wenig Daten näher zum neutralen 1.0. Der Backtest-Prior zählt mit (n),
        # ein geprimtes Signal wird also von Anfang an vertraut.
        if n < MIN_OBS_FOR_TRUST:
            blend = n / MIN_OBS_FOR_TRUST   # 0..1
            clamped_weight = 1.0 * (1.0 - blend) + clamped_weight * blend

        prev = weights.get(sig_name) or {}
        weights[sig_name] = {
            "weight":              round(clamped_weight, 3),
            "n_observations":      round(n_live, 2),     # ECHTE Live-Beobachtungen
            "n_prior":             round(n_prior, 2),    # Backtest-Pseudo-Obs (verblassen)
            "wins_when_triggered": round(wins, 2),       # fraktional (Live + Prior)
            "losses_when_triggered": round(losses, 2),
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
