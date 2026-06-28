#!/usr/bin/env python3
"""pick_staking.py — Edge-Staking für Card-Picks (28.06.2026, Lucas).

Ersetzt das flache €10/€5 durch fraktionales Kelly. Steam-Cards haben KEINEN Preis-Edge
(negative edge ist by design — [[feedback_two_surfaces_concept]]), darum ist die Conviction
unser Edge-Proxy: angenommener Edge = (Conviction − neutral) · edge_per_pt. Kelly macht die
Größe odds-bewusst (gleicher Edge auf Longshot → kleinerer Anteil). Viertel-Kelly + harte Caps.

    assumedEdge = max(0, (conviction − neutral)) · edge_per_conviction_pt
    stakeRaw    = bankroll · kelly_fraction · assumedEdge / (odds − 1)
    ABWÄGEN     → × abwaegen_factor
    stake       = clamp(stakeRaw, min_stake, max_stake)

EINE Quelle: schreibt pick["stake"] ins Datenfile (Tracking/Recap/Cards lesen nur). Config kommt
aus cocobet_config (profil-/dataset-bewusst). Reine Funktionen → testbar.
"""
from __future__ import annotations

from cocobet_config import CONFIG


def _cfg(cfg=None) -> dict:
    return cfg if cfg is not None else (CONFIG.get("staking") or {})


def compute_stake(pick: dict, cfg=None) -> float | None:
    """Stake (€, 1 Nachkommastelle) für einen Pick. None wenn Odds fehlen/ungültig."""
    c = _cfg(cfg)
    odds = pick.get("odds")
    if not isinstance(odds, (int, float)) or odds <= 1.0:
        return None
    neutral = c.get("conviction_neutral", 5.0)
    conv = pick.get("convictionScore")
    if not isinstance(conv, (int, float)):
        conv = neutral
    assumed_edge = max(0.0, (conv - neutral) * c.get("edge_per_conviction_pt", 0.006))
    b = odds - 1.0
    kelly_full = (assumed_edge / b) if b > 0 else 0.0
    stake = c.get("bankroll", 1000.0) * c.get("kelly_fraction", 0.25) * kelly_full
    if pick.get("verdict") == "ABWÄGEN":
        stake *= c.get("abwaegen_factor", 0.6)
    stake = max(c.get("min_stake", 2.0), min(c.get("max_stake", 25.0), stake))
    return round(stake, 1)


def apply(wm: dict, cfg=None) -> int:
    """Setzt pick['stake'] auf allen BET/ABWÄGEN-Picks (nicht-excluded). Gibt die Anzahl zurück."""
    c = _cfg(cfg)
    picks = wm.get("picks") or {}
    n = 0
    for plist in picks.values():
        if not isinstance(plist, list):
            continue
        for p in plist:
            if not isinstance(p, dict) or p.get("trackingExcluded"):
                continue
            if p.get("verdict") not in ("BET", "ABWÄGEN"):
                continue
            # Immutability: bereits aufgelöste/gepostete Picks NICHT rückwirkend umstaken
            # (sonst verschiebt sich die historische P&L). Nur offene Picks bekommen Edge-Stake.
            if p.get("result"):
                continue
            s = compute_stake(p, c)
            if s is not None:
                p["stake"] = s
                n += 1
    return n


if __name__ == "__main__":
    import json
    import cocobet_dataset as D
    wm = json.loads(D.data_file().read_text(encoding="utf-8"))
    n = apply(wm)
    D.data_file().write_text(json.dumps(wm, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Edge-Stake gesetzt für {n} Pick(s) ({D.active_dataset()})")
