"""
sharp_signals/reverse_line_move.py — Reverse Line Movement (Proxy)

Klassischer Sharp-Edge: Die Linie bewegt sich GEGEN die Public-Seite. Wenn das große
Publikum eine Seite überbettet, der scharfe Buchmacher (Pinnacle) die Linie aber in die
ANDERE Richtung zieht, dann liegt das scharfe Geld auf der unbeliebten Seite.

Wir haben keinen echten Ticket-%/Handle-Feed → Proxy aus Daten, die wir schon haben:
  · Public-Lean  = public-implied − Pinnacle-fair (aus odds_snapshot; wie public_static_bias)
                   > 0  → Public überbettet dieses Outcome (Public ist DRAUF).
  · Pinnacle-Move = implied(jetzt) − implied(Opening)  (aus odds_snapshot.odds_open)
                   > 0  → Pinnacle hat das Outcome verkürzt (Linie ZU diesem Outcome).

RLM-Logik für einen Pick AUF Outcome X:
  · Public DRAUF (lean>0) UND Pinnacle zieht WEG (move<0)  → Sharps faden das Public →
    unsere Seite (=Public-Seite) ist die falsche → NEGATIV (Warnung).
  · Public GEGEN X (lean<0, Public auf der Gegenseite) UND Pinnacle zieht ZU X (move>0) →
    RLM zu unseren Gunsten → scharfes Geld auf X, Public woanders → POSITIV.
Nur 1X2 (home/away) + O/U (over/under) — dort haben wir Public-Quoten. Draw/AH/BTTS → None.

Sharp-Familie (korreliert mit lead_lag/steam): Anti-Korr-Discount greift.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side

MIN_LEAN_PP = 2.0     # ab wann gilt Public als „drauf"/„dagegen"
MIN_MOVE_PP = 1.5     # ab wann gilt der Pinnacle-Move als relevant
MAX_PP      = 3.5     # Deckel Score
SCALE       = 0.35    # pp Score je pp (Move × Lean)/Referenz


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def _devig_1x2(hw, dr, aw):
    a, b, c = _imp(hw), _imp(dr), _imp(aw)
    if None in (a, b, c):
        return None
    s = a + b + c
    return {"home": a / s, "draw": b / s, "away": c / s}


def _devig_2(o, u):
    a, b = _imp(o), _imp(u)
    if None in (a, b):
        return None
    s = a + b
    return {"over": a / s, "under": b / s}


class ReverseLineMoveSignal(Signal):
    def name(self) -> str:
        return "reverse_line_move"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over", "under"):
            return None
        snap = context.get("odds_snapshot") or {}
        op = snap.get("odds_open") or {}

        # Aktuelle Pinnacle-Fair + Opening-Fair + Public-Fair für das Outcome
        if side in ("home", "away"):
            pf_now = _devig_1x2(snap.get("hw"), snap.get("dr"), snap.get("aw"))
            pf_open = _devig_1x2(op.get("hw"), op.get("dr"), op.get("aw"))
            pub = _devig_1x2(snap.get("public_hw"), snap.get("public_dr"), snap.get("public_aw"))
            key = side
        else:
            pf_now = _devig_2(snap.get("o25"), snap.get("u25"))
            pf_open = _devig_2(op.get("o25"), op.get("u25"))
            pub = _devig_2(snap.get("public_o25"), snap.get("public_u25"))
            key = side
        if not pf_now or not pf_open or not pub:
            return None

        pinn_move = (pf_now[key] - pf_open[key]) * 100.0     # >0 = Pinnacle verkürzt Outcome
        public_lean = (pub[key] - pf_now[key]) * 100.0        # >0 = Public überbettet Outcome

        # RLM nur wenn Bewegung UND Lean klar genug sind
        if abs(pinn_move) < MIN_MOVE_PP or abs(public_lean) < MIN_LEAN_PP:
            return None

        oc_lbl = {"home": "Heim", "away": "Auswärts", "over": "Über", "under": "Unter"}[side]
        # Fall A: Public drauf, Pinnacle zieht weg → Warnung (wir sind auf der Public-Seite)
        if public_lean > 0 and pinn_move < 0:
            score = -min(MAX_PP, (abs(pinn_move) * (public_lean / 2.0)) ** 0.5 * SCALE * 3)
            ev = (f"Reverse Line Move: Das Publikum überbettet {oc_lbl} ({public_lean:+.1f}pp), "
                  f"aber Pinnacle zieht die Linie weg ({pinn_move:.1f}pp) — das scharfe Geld fadet "
                  f"unsere Seite. Vorsicht.")
        # Fall B: Public gegen unser Outcome, Pinnacle zieht ZU uns → RLM in unsere Gunst
        elif public_lean < 0 and pinn_move > 0:
            score = min(MAX_PP, (pinn_move * (abs(public_lean) / 2.0)) ** 0.5 * SCALE * 3)
            ev = (f"Reverse Line Move: Das Publikum meidet {oc_lbl} ({public_lean:.1f}pp), "
                  f"aber Pinnacle zieht die Linie genau dorthin ({pinn_move:+.1f}pp) — scharfes "
                  f"Geld auf unserer unbeliebten Seite.")
        else:
            return None

        conf = min(0.75, 0.45 + (abs(pinn_move) + abs(public_lean)) * 0.02)
        return SignalResult(
            score=round(score, 2),
            confidence=round(conf, 2),
            evidence=ev,
            metadata={"pinn_move_pp": round(pinn_move, 2),
                      "public_lean_pp": round(public_lean, 2), "outcome": side},
        )
