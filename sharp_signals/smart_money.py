"""
sharp_signals/smart_money.py — Polymarket Smart-Money-Verteilung (19.06.2026, Lucas)

Konzept (Lucas): nicht nur der Poly-PREIS (das macht polymarket_sharp), sondern WO das Geld
liegt und WER es setzt. Aus der Polymarket data-api (/holders, /trades) pro Outcome:
  · usd-Anteil je Seite (Geld-Split — „9 Mio von 10 auf Home")
  · Big-Wallet-Konzentration (topHolderShare) = Smart-Money-Proxy (wenige große vs viele kleine)

WICHTIG — gegen die „redundant zum Preis"-Falle: rohes Volumen ist schon im Preis. Das Signal
misst daher den ÜBERSCHUSS gegen die SCHARFE Pinnacle-Fair (nicht gegen 50/50), GEWICHTET mit
der Big-Wallet-Konzentration. Heißt: „mehr (smartes) Geld auf unserer Seite als Pinnacle
rechtfertigt" → milder Confirm. Reines Retail-Overload (kleine Wallets) bleibt klein.

NIEDRIG GEWICHTET (Lucas): Cap ~1.5pp + niedrige Confidence. WM-Sample reicht zum BERECHNEN,
aber nicht zum BEWEISEN → der Bayesian-Loop kalibriert über Liga (viele Resolves), dort
Schwellen nachjustieren. Datenfeld: context["smartmoney"][matchKey] (fetch_wm_poly_smartmoney.py).

Zwei Flächen: Poly-Markt-Info → Trade-Qualitäts-/Sentiment-Input, KEIN Real-Outcome-Modell.
Card-Anzeige violett (Split + Top-Trader). Vom Sandbox geoblockt → live nur am Mac-Runner.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "scale":            6.0,    # excess × smartness × scale → pp
    "max_signal_pp":    1.5,    # NIEDRIGER Cap (unbewiesen) — Liga nachjustieren
    "min_volume_usd":   500_000,  # darunter zu dünn → kein Signal
    "min_top_share":    0.10,   # darunter reines Retail → kaum smart
    "base_conf":        0.40,
    "max_conf":         0.6,
}


_OUTCOME = {
    "heimsieg": "home", "doppelte chance — 1x": "home", "ah heim": "home",
    "auswärtssieg": "away", "auswartssieg": "away", "doppelte chance — x2": "away", "ah auswärts": "away",
    "unentschieden": "draw",
}


def _outcome_key(market: str) -> Optional[str]:
    m = (market or "").lower()
    for frag, key in _OUTCOME.items():
        if m.startswith(frag) or frag in m:
            return key
    return None


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("smart_money") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


class SmartMoneySignal(Signal):
    """Polymarket-Geldverteilung relativ zur Pinnacle-Fair, big-wallet-gewichtet. Niedrig."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "smart_money"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        outcome = _outcome_key(pick.get("market", ""))
        if not outcome:
            return None
        data = (context.get("smartmoney") or {}).get(context.get("matchKey") or "")
        if not isinstance(data, dict):
            return None
        total = data.get("totalUsd") or 0
        if total < self._t["min_volume_usd"]:
            return None                       # zu dünn → kein Signal
        sm = (data.get("outcomes") or {}).get(outcome)
        if not isinstance(sm, dict):
            return None
        try:
            share = float(sm.get("share"))
            top_share = float(sm.get("topHolderShare") or 0.0)
        except (TypeError, ValueError):
            return None

        # Scharfe Baseline: Pinnacle-Fair-Wkt der Pick-Seite (de-viggt = 1/modelOdds).
        mo = pick.get("modelOdds")
        if not isinstance(mo, (int, float)) or mo <= 1.0:
            return None                       # ohne scharfe Baseline kein „Überschuss"
        fair_share = 1.0 / mo

        excess = share - fair_share           # + = mehr Geld als Pinnacle rechtfertigt
        smartness = max(0.0, top_share)
        if smartness < self._t["min_top_share"]:
            return None                       # reines Retail → nicht smart genug
        score = excess * smartness * self._t["scale"]
        cap = self._t["max_signal_pp"]
        score = max(-cap, min(cap, score))
        if abs(score) < 0.1:
            return None

        confidence = min(self._t["max_conf"],
                         self._t["base_conf"] + min(0.2, total / 20_000_000))
        side_lbl = {"home": "Heim", "draw": "X", "away": "Auswärts"}[outcome]
        ev = (f"💰 Smart Money: {round(share*100)}% auf {side_lbl} "
              f"(Top-Wallets {round(top_share*100)}%) vs Pinnacle-Fair {round(fair_share*100)}% "
              f"→ {'mehr' if excess > 0 else 'weniger'} als der Markt rechtfertigt")
        return SignalResult(
            score=round(float(score), 2),
            confidence=round(float(confidence), 2),
            evidence=ev,
            metadata={
                "outcome": outcome, "share": round(share, 3),
                "topHolderShare": round(top_share, 3), "fairShare": round(fair_share, 3),
                "excessPP": round(excess * 100, 1), "totalUsd": total,
                "topTraders": data.get("topTraders"),
            },
        )
