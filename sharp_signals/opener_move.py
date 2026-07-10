"""
sharp_signals/opener_move.py — Opener → Früh-Move (Sharp Window)

Pinnacle postet Eröffnungslinien mit niedrigen Limits, die eine Handvoll Sharps VOR dem
Public-Volumen hämmert. Der Opening→früh-Abschnitt ist der schärfste, informativste Move
der ganzen Woche — Softbooks schlafen dann noch. Ein Steam-Pick, dessen früheste Bewegung
schon ZU unserer Seite lief, folgt dem allerschärfsten Geld.

Aus der Pinnacle-Zeitreihe (odds_history, bk=='pinnacle', chronologisch): Move der Pick-Seite
vom Opening (erster Snap) bis ans Ende des frühen Fensters (SHARP_WINDOW_H). Verkürzung ZU
unserer Seite in diesem frühen Fenster → POSITIV. Nur bewertet, wenn ≥2 frühe Snaps existieren.

Sharp-Familie. Klein gedeckelt; ein Bestätiger, kein Origin-Signal.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side

SHARP_WINDOW_H = 12.0   # „frühes Fenster" nach dem Opening
MIN_MOVE_PP    = 1.5
MAX_PP         = 2.5
SCALE          = 0.28


def _imp(o):
    return (1.0 / o) if (o and o > 1.0) else None


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _devig_1x2(s, key):
    a, b, c = _imp(s.get("hw")), _imp(s.get("dr")), _imp(s.get("aw"))
    if None in (a, b, c):
        return None
    tot = a + b + c
    return {"home": a / tot, "away": c / tot}.get(key)


def _devig_ou(s, key):
    a, b = _imp(s.get("o25")), _imp(s.get("u25"))
    if None in (a, b):
        return None
    tot = a + b
    return {"over": a / tot, "under": b / tot}.get(key)


class OpenerMoveSignal(Signal):
    def name(self) -> str:
        return "opener_move"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over", "under"):
            return None
        hist = context.get("odds_history") or []
        pinn = [s for s in hist if isinstance(s, dict) and s.get("bk") == "pinnacle"]
        pinn = [s for s in pinn if _parse_ts(s.get("ts"))]
        pinn.sort(key=lambda s: s["ts"])
        if len(pinn) < 2:
            return None

        implied = _devig_1x2 if side in ("home", "away") else _devig_ou
        opener = pinn[0]
        t0 = _parse_ts(opener["ts"])
        p_open = implied(opener, side)
        if p_open is None:
            return None

        # Letzter Snap innerhalb des frühen Fensters (sonst der 2. Snap = frühestmögliche Bewegung)
        early = None
        for s in pinn[1:]:
            ts = _parse_ts(s["ts"])
            if ts and (ts - t0).total_seconds() <= SHARP_WINDOW_H * 3600:
                early = s
            else:
                break
        if early is None:
            early = pinn[1]
        p_early = implied(early, side)
        if p_early is None:
            return None

        move = (p_early - p_open) * 100.0   # >0 = Pinnacle verkürzt unsere Seite im frühen Fenster
        if move < MIN_MOVE_PP:
            return None   # kein früher Zug zu uns → kein Sharp-Window-Bonus

        oc = {"home": "Heim", "away": "Auswärts", "over": "Über", "under": "Unter"}[side]
        score = min(MAX_PP, move * SCALE)
        conf = min(0.7, 0.4 + move * 0.03)
        ev = (f"Sharp-Window: Schon im frühen Fenster nach der Eröffnung zog Pinnacle {oc} "
              f"um {move:+.1f}pp an — das ist die schärfste, früheste Geldbewegung, bevor das "
              f"Public-Volumen kam.")
        return SignalResult(score=round(score, 2), confidence=round(conf, 2), evidence=ev,
                            metadata={"early_move_pp": round(move, 2), "outcome": side,
                                      "opener_odds": opener.get("hw") if side == "home" else None})
