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
from sharp_signals.base import Signal, SignalResult, match_eintrag


DEFAULT_THRESHOLDS = {
    "scale":            6.0,    # excess × smartness × scale → pp
    "max_signal_pp":    1.5,    # NIEDRIGER Cap (unbewiesen) — Liga nachjustieren
    "min_volume_usd":   100_000,  # darunter zu dünn → kein Signal (20.06.: 500k→100k, da wir
                                  # offenes Interesse der Top-200 messen, nicht kumuliertes Volumen)
    "min_top_share":    0.10,   # darunter reines Retail → kaum smart
    "base_conf":        0.40,
    "max_conf":         0.6,
    # Konsens-Cluster + Whale-Exit (22.06.2026, PolymarketScan-Idee). Window lebt im Fetcher
    # (cluster_window_h, single source) — hier nur die Entscheidungs-Schwellen.
    "cluster_window_h":   12,    # NUR Doku/Single-Source — Fetcher liest es zur Fetch-Zeit
    "cluster_min_wallets": 3,    # ≥N unabhängige BUY-Wallets im Fenster = echter Konsens
    "cluster_boost":      1.25,  # smartness-Faktor wenn Cluster erreicht (gedeckelt via max_pp)
    "exit_window_h":      24,    # SELLs erst so nah am Anpfiff als Conviction-Aufgabe werten
    "exit_min_usd":       2000,  # Net-Abfluss ab $ = Verkäufer dominieren unsere Pick-Seite
    "exit_penalty":       1.0,   # pp-Abzug Richtung Warnung bei Exit-Muster
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
        # 06.09.2026: der Liga-matchKey (ENG-1-45-33) passt nicht auf die Schluessel der
        # Smart-Money-Datei (45-33). Siehe base.match_eintrag — vorher: nie ein Treffer.
        data = match_eintrag(context.get("smartmoney"), context)
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

        # Konsens-Cluster: ≥N unabhängige große BUY-Wallets im Fenster verstärken die Konzentration
        cluster = int(sm.get("cluster") or 0)
        clustered = cluster >= self._t["cluster_min_wallets"]
        if clustered:
            smartness *= self._t["cluster_boost"]

        score = excess * smartness * self._t["scale"]

        # Whale-Exit: Verkäufer dominieren unsere Pick-Seite nah am Anpfiff → Conviction kippt.
        net = sm.get("netFlowUsd")
        hk = data.get("hoursToKickoff")
        exit_hit = (isinstance(net, (int, float)) and net <= -self._t["exit_min_usd"]
                    and isinstance(hk, (int, float)) and 0 <= hk <= self._t["exit_window_h"])
        if exit_hit:
            score -= self._t["exit_penalty"]   # Richtung Warnung drücken (kein Confirm)

        cap = self._t["max_signal_pp"]
        score = max(-cap, min(cap, score))
        if abs(score) < 0.1:
            return None

        confidence = min(self._t["max_conf"],
                         self._t["base_conf"] + min(0.2, total / 20_000_000))
        side_lbl = {"home": "Heim", "draw": "X", "away": "Auswärts"}[outcome]
        ev = (f"💰 Auf Polymarket liegen {round(share*100)}% des Geldes auf {side_lbl} — "
              f"{'mehr' if excess > 0 else 'weniger'} als der faire Preis hergibt "
              f"({round(fair_share*100)}%), und es sind echte Wale dahinter "
              f"(Top-Wallets {round(top_share*100)}%).")
        if clustered:
            ev += f" {cluster} große Wallets sammeln gerade unabhängig dieselbe Seite ein."
        if exit_hit:
            ev += (f" ⚠️ Aber kurz vor Anpfiff verkaufen Wale netto rund "
                   f"${abs(net)/1000:.0f}k auf dieser Seite — die Überzeugung kippt.")
        return SignalResult(
            score=round(float(score), 2),
            confidence=round(float(confidence), 2),
            evidence=ev,
            metadata={
                "outcome": outcome, "share": round(share, 3),
                "topHolderShare": round(top_share, 3), "fairShare": round(fair_share, 3),
                "excessPP": round(excess * 100, 1), "totalUsd": total,
                "topTraders": data.get("topTraders"),
                "cluster": cluster, "clustered": clustered,
                "netFlowUsd": net if isinstance(net, (int, float)) else None,
                "hoursToKickoff": hk if isinstance(hk, (int, float)) else None,
                "exitFlag": exit_hit,
            },
        )
