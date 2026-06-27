"""
sharp_signals/transfer_shift.py — Schlüsselspieler-Abgang (26.06.2026, Lucas).

Verliert ein Team jüngst einen Schlüsselspieler (Transfer WEG), ist es real geschwächt — der Markt
preist das früh in der Saison oft zu langsam ein. Dämpft den Sieg des geschwächten Teams; bei Abgang
des Top-Stürmers leichter Unter-Hebel (weniger Tor-Bedrohung). Daten: liga-data.json["keyDepartures"]
(fetch_liga_team_changes, bereits auf Schlüsselspieler gefiltert). context-Familie (Verfügbarkeit,
Anti-Korr mit injury/lineup — dauerhafter Verlust vs temporärer Ausfall).
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

MAX_PP = 1.2


def shift(departures: list) -> float:
    """keyDepartures-Liste → Schwächung 0..1 (1 Schlüssel-Abgang spürbar, 2+ stark)."""
    n = len(departures or [])
    if n <= 0:
        return 0.0
    return round(min(1.0, 0.6 + 0.4 * (n - 1)), 3)


class TransferShiftSignal(Signal):
    def name(self) -> str:
        return "transfer_shift"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        kd = context.get("key_departures") or {}
        if not kd:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        hs, as_ = shift(kd.get(home_id)), shift(kd.get(away_id))
        if hs == 0.0 and as_ == 0.0:
            return None

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        score, ev = 0.0, ""
        if side in ("home", "away"):
            mine, theirs = (hs if side == "home" else as_), (as_ if side == "home" else hs)
            # eigenes Team geschwächt → Sieg dämpfen; Gegner geschwächt → Boost
            score = (theirs - mine) * MAX_PP
            lbl = "Heim" if side == "home" else "Auswärts"
            ev = (f"Schlüssel-Abgang {lbl} {len(kd.get(home_id if side=='home' else away_id) or [])} / "
                  f"Gegner {len(kd.get(away_id if side=='home' else home_id) or [])}")
        elif side == "under":
            score = max(hs, as_) * MAX_PP * 0.5   # Schlüsselangreifer weg → weniger Tore
            ev = "Schlüsselspieler abgegeben → geringere Tor-Bedrohung"
        else:   # over: kein Boost
            return None

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:
            return None
        conf = round(min(0.55, 0.3 + max(hs, as_) * 0.25), 2)
        return SignalResult(score=score, confidence=conf, evidence=ev,
                            metadata={"homeShift": hs, "awayShift": as_})
