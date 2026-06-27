"""
sharp_signals/coach_change.py — Neue-Trainer-Bounce (26.06.2026, Lucas).

Ein frisch installierter Trainer bringt oft einen kurzfristigen Schub (neue Impulse, Spieler unter
Beobachtung). Boostet das Team mit dem frischen Trainer auf Sieg, leicht auf Über. Effekt zerfällt
linear über das Trainer-Fenster. Daten: liga-data.json["coachChange"] (fetch_liga_team_changes).
context-Familie (situativ).
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

MAX_PP = 1.0
WINDOW_DAYS = 75


def bounce(entry: dict) -> float:
    """coachChange-Eintrag → Bounce-Faktor 0..1, linear zerfallend über WINDOW_DAYS."""
    if not entry:
        return 0.0
    ds = entry.get("daysSince")
    if ds is None or ds < 0 or ds > WINDOW_DAYS:
        return 0.0
    return round(max(0.0, 1.0 - ds / WINDOW_DAYS), 3)


class CoachChangeSignal(Signal):
    def name(self) -> str:
        return "coach_change"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        cc = context.get("coach_change") or {}
        if not cc:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        hb, ab = bounce(cc.get(home_id)), bounce(cc.get(away_id))
        if hb == 0.0 and ab == 0.0:
            return None

        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over"):
            return None

        if side == "over":
            score = ((hb + ab) / 2.0) * MAX_PP * 0.5
            ev = "Frischer Trainer im Spiel → oft offensiver Auftakt"
        else:
            mine, theirs = (hb if side == "home" else ab), (ab if side == "home" else hb)
            score = (mine - 0.4 * theirs) * MAX_PP
            who = cc.get(home_id if side == "home" else away_id) or {}
            ev = (f"Neuer Trainer {who.get('name','?')} ({who.get('daysSince')}d) → "
                  f"{'Heim' if side=='home' else 'Auswärts'}-Bounce")

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:
            return None
        conf = round(min(0.55, 0.3 + max(hb, ab) * 0.25), 2)
        return SignalResult(score=score, confidence=conf, evidence=ev,
                            metadata={"homeBounce": hb, "awayBounce": ab})
