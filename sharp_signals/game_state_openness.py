"""
sharp_signals/game_state_openness.py — Spiel-Offenheit für Über/BTTS

O/U und BTTS entscheiden sich nicht an Team-QUALITÄT, sondern am Spiel-ZUSTAND: gehen beide
Teams auf Tore? Der schärfste, von Softbooks unter-modellierte Fall ist die ASYMMETRISCHE
Verzweiflung: EIN Team muss zwingend gewinnen (Tabellen-Druck, muss chasen → wirft Leute nach
vorn, öffnet sich), der Gegner hat NICHTS mehr zu spielen (dead) → kontert in die offenen Räume.
Das produziert historisch Tore + BTTS.

Bewusst NICHT „beide müssen gewinnen → Über" (Lucas: dann oft vorsichtig/verkrampft) und NICHT
„beide dead → Unter" (das macht schon league_pressure). Rein additiv: nur Über / BTTS-Ja, nur
bei asymmetrischer Verzweiflung. Nutzt die Tabellen-Druck-Rechnung von league_pressure →
selbst-skalierend (früh 0, spät voller Hebel). incentive-Familie (Anti-Korr mit league_pressure).
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side
from sharp_signals.league_pressure import LEAGUE_META, team_pressure

MAX_PP = 1.6


def _is_btts_yes(market: str) -> bool:
    m = (market or "").lower()
    return ("beide" in m or "btts" in m) and not ("nein" in m or "no" in m)


class GameStateOpennessSignal(Signal):
    def name(self) -> str:
        return "game_state_openness"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        market = pick.get("market", "")
        is_over = market_side(market) == "over"
        is_btts = _is_btts_yes(market)
        if not (is_over or is_btts):
            return None   # nur Über + BTTS-Ja

        league = context.get("group_id")
        meta = LEAGUE_META.get(league)
        if not meta:
            return None
        standings = (context.get("standings") or {}).get(league)
        if not standings:
            return None
        try:
            rounds_left = meta["rounds"] - int(context.get("matchday"))
        except (TypeError, ValueError):
            return None
        if rounds_left <= 0:
            return None

        home_id, away_id = context.get("home_id"), context.get("away_id")
        hrow = next((r for r in standings if r.get("team") == home_id), None)
        arow = next((r for r in standings if r.get("team") == away_id), None)
        if not hrow or not arow:
            return None
        hp, hm = team_pressure(hrow, standings, meta, rounds_left)
        ap, am = team_pressure(arow, standings, meta, rounds_left)

        # Asymmetrische Verzweiflung: genau EINER muss gewinnen (hoher Druck), der ANDERE ist dead.
        chaser_p = None
        if hm == "win" and am == "dead":
            chaser_p = hp
        elif am == "win" and hm == "dead":
            chaser_p = ap
        if chaser_p is None or chaser_p < 0.15:
            return None

        score = min(MAX_PP, chaser_p * MAX_PP * 1.3)
        conf = min(0.65, 0.35 + chaser_p * 0.5)
        lbl = "Über 2.5" if is_over else "BTTS"
        ev = (f"Offenes Spiel: Ein Team muss zwingend gewinnen (Druck {chaser_p:.0%}) und wirft "
              f"nach vorn, der Gegner hat nichts mehr zu spielen und kontert in die Räume — "
              f"spricht für {lbl}.")
        return SignalResult(score=round(score, 2), confidence=round(conf, 2), evidence=ev,
                            metadata={"chaserPressure": chaser_p, "homeMotive": hm,
                                      "awayMotive": am, "roundsLeft": rounds_left})
