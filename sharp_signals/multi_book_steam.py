"""
sharp_signals/multi_book_steam.py — Multi-Book-Sharp-Korroboration

Ein Move/eine Fehlbepreisung ist nur echt, wenn sie über MEHRERE unabhängige scharfe Bücher
bestätigt ist — nicht bei einem einzelnen Pinnacle-Tick. Wir haben zwei scharfe Anker:
Pinnacle (Haupt) + Betfair-Exchange (bf_*, 2. Sharp-Anker, [[project_betfair_anchor]]). Wenn
BEIDE das Outcome höher bepreisen als der Softbook (Public), sind sich zwei unabhängige scharfe
Quellen einig, dass das Public es unterbepreist → starkes, korroboriertes Sharp-Signal.

Der korroborierte Edge = das SCHWÄCHERE der beiden Sharp-vs-Public-Gaps (beide müssen zustimmen).
Nur 1X2 (home/away) — Betfair liefern wir nur fürs 1X2. Sharp-Familie (Anti-Korr mit lead_lag/
public_static/steam).
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side

MIN_GAP_PP = 2.0    # beide Sharp-Gaps müssen mind. so groß sein
MAX_PP     = 3.0
SCALE      = 0.5


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def _devig3(hw, dr, aw, key):
    a, b, c = _imp(hw), _imp(dr), _imp(aw)
    if None in (a, b, c):
        return None
    tot = a + b + c
    return {"home": a / tot, "away": c / tot}.get(key)


class MultiBookSteamSignal(Signal):
    def name(self) -> str:
        return "multi_book_steam"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away"):
            return None
        s = context.get("odds_snapshot") or {}
        pinn = _devig3(s.get("hw"), s.get("dr"), s.get("aw"), side)
        betf = _devig3(s.get("bf_hw"), s.get("bf_dr"), s.get("bf_aw"), side)
        pub = _devig3(s.get("public_hw"), s.get("public_dr"), s.get("public_aw"), side)
        if pinn is None or betf is None or pub is None:
            return None

        gap_pinn = (pinn - pub) * 100.0    # >0 = Pinnacle hält Outcome für wahrscheinlicher als Public
        gap_betf = (betf - pub) * 100.0
        # Beide Sharps müssen in DERSELBEN Richtung zustimmen und je ≥ Schwelle.
        if gap_pinn >= MIN_GAP_PP and gap_betf >= MIN_GAP_PP:
            corr = min(gap_pinn, gap_betf)            # das schwächere Agreement zählt
            direction = 1.0
        elif gap_pinn <= -MIN_GAP_PP and gap_betf <= -MIN_GAP_PP:
            corr = min(abs(gap_pinn), abs(gap_betf))
            direction = -1.0
        else:
            return None   # keine Zwei-Buch-Einigkeit → kein korroboriertes Signal

        oc = "Heim" if side == "home" else "Auswärts"
        score = direction * min(MAX_PP, corr * SCALE)
        conf = min(0.8, 0.5 + corr * 0.03)
        if direction > 0:
            ev = (f"Zwei scharfe Bücher einig: Pinnacle (+{gap_pinn:.1f}pp) UND Betfair "
                  f"(+{gap_betf:.1f}pp) halten {oc} für wahrscheinlicher als der Softbook — "
                  f"korroborierte Fehlbepreisung.")
        else:
            ev = (f"Zwei scharfe Bücher warnen: Pinnacle ({gap_pinn:.1f}pp) UND Betfair "
                  f"({gap_betf:.1f}pp) bepreisen {oc} niedriger als der Softbook — Vorsicht.")
        return SignalResult(score=round(score, 2), confidence=round(conf, 2), evidence=ev,
                            metadata={"gap_pinnacle_pp": round(gap_pinn, 2),
                                      "gap_betfair_pp": round(gap_betf, 2), "outcome": side})
