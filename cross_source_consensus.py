"""
cross_source_consensus.py — Triple/Konsens (29.07.2026, Lucas): eine 1X2-Wette über mehrere
unabhängige Quellen. Übereinstimmen (Konsens) = die Wahrscheinlichkeit ist verlässlich → Konfidenz.
Ausscheren einer Quelle (Divergenz) = Value-Kandidat (jemand ist falsch bepreist).

Quellen je Ausgang (de-viggte Wahrscheinlichkeit, 0..1):
  · Pinnacle — fair_* aus poly_snapshot, sonst de-viggt aus dem odds_snapshot (hw/dr/aw)
  · Betfair  — betfair_snapshot.mo.fair (home/away)
  · Poly     — poly_snapshot.poly_* (nur wo Poly deckt: MLS/WM; Top-5 fehlt derzeit)
  · Soft     — 1/softNow des Picks (roh implied — die eine Quelle, die wir je Ausgang haben)

v1: nur 1X2 Heim/Auswärts (dort haben ALLE Quellen denselben Ausgang). Ü/U/BTTS später.
Baked von generate_wm_picks als pick["consensus"]; rein additiv (try/except) → kein Risiko.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import market_side

# side → (odds/fair-Suffix, Betfair-fair-Key, Poly-Key)
_K = {"home": ("hw", "home", "poly_hw"), "away": ("aw", "away", "poly_aw")}

CONSENSUS_MAX_SPREAD = 6.0   # ≤ so viel pp Spanne über ≥3 Quellen → „einig" (Konfidenz)
DIVERGENCE_MIN_GAP   = 8.0   # eine Quelle ≥ so viel pp vom Median → Ausreißer (Value-Kandidat)


def _p(x) -> Optional[float]:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if 0.0 < x < 1.0 else None


def _pinn_fair(odds: dict, side: str) -> Optional[float]:
    """De-viggte Pinnacle-1X2-Wkt aus dem odds_snapshot (hw/dr/aw)."""
    try:
        hw, dr, aw = float(odds.get("hw")), float(odds.get("dr")), float(odds.get("aw"))
    except (TypeError, ValueError):
        return None
    if min(hw, dr, aw) <= 1.0:
        return None
    inv = {"home": 1.0 / hw, "away": 1.0 / aw}
    s = 1.0 / hw + 1.0 / dr + 1.0 / aw
    return inv[side] / s if s > 0 else None


def _median(vals):
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def build_consensus(pick: dict, ctx: dict) -> Optional[dict]:
    side = market_side(pick.get("market", ""))
    if side not in ("home", "away"):
        return None
    suf, bfkey, polykey = _K[side]
    poly_snap = ctx.get("poly_snapshot") or {}
    odds_snap = ctx.get("odds_snapshot") or {}
    bf = ctx.get("betfair_snapshot")

    src = {}
    # Pinnacle: bevorzugt fertiges fair_* aus poly_snapshot, sonst selbst de-viggen
    pinn = _p(poly_snap.get("fair_" + suf))
    if pinn is None:
        pinn = _pinn_fair(odds_snap, side)
    if pinn is not None:
        src["pinnacle"] = pinn
    # Betfair
    if bf:
        b = _p(((bf.get("mo") or {}).get("fair") or {}).get(bfkey))
        if b is not None:
            src["betfair"] = b
    # Poly
    pv = _p(poly_snap.get(polykey))
    if pv is not None:
        src["poly"] = pv
    # Soft (roh implied)
    try:
        sn = float(pick.get("softNow"))
        if sn > 1.0:
            src["soft"] = 1.0 / sn
    except (TypeError, ValueError):
        pass

    if len(src) < 2:
        return None

    vals = list(src.values())
    spread = (max(vals) - min(vals)) * 100.0
    med = _median(vals)

    kind, outlier, gap = None, None, 0.0
    # größter Abstand einer Quelle zum Median
    for k, v in src.items():
        g = abs(v - med) * 100.0
        if g > gap:
            gap, outlier = g, k
    if len(src) >= 3 and spread <= CONSENSUS_MAX_SPREAD:
        kind = "konsens"
        outlier = None
    elif gap >= DIVERGENCE_MIN_GAP:
        kind = "divergenz"       # outlier = die ausscherende Quelle (Value dort, wenn sie güntiger ist)
    # sonst: neutral (weder eng genug noch klarer Ausreißer)

    return {
        "side": side,
        "sources": {k: round(v, 3) for k, v in src.items()},
        "n": len(src),
        "spreadPP": round(spread, 1),
        "medianPP": round(med * 100.0, 1),
        "kind": kind,
        "outlier": outlier,
        "outlierGapPP": round(gap, 1),
    }
