"""
sharp_signals/topscorer_momentum.py — Top-Torjäger-Bedrohung (26.06.2026, Lucas Spieler-Layer).

Ein Team mit einem treffsicheren Top-Torjäger (hohe Tore/Spiel) trägt eine konzentrierte Angriffs-
Bedrohung, die das Team-xG/-Form manchmal unterschätzt. Boostet den eigenen Sieg + Über; der Stürmer
des Gegners dämpft leicht. Daten: liga-data.json["topScorers"] (fetch_liga_topscorers).

In der „form"-Familie (Anti-Korr mit form_trend/xg_strength/chance_creation) → der Angriffs-Edge
zählt nicht doppelt. Konservativ gedeckelt; früh in der Saison (wenige Spiele) ~neutral.
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

MAX_PP = 1.2
MIN_APPS = 3          # darunter zu wenig Stichprobe (2 Tore in 1 Spiel ≠ Form)
ELITE_GPG = 0.7       # Tore/Spiel die als „elite" 1.0 zählen


def threat(entry: dict) -> float:
    """Top-Torjäger-Eintrag → Bedrohung 0..1 (Tore/Spiel, ab MIN_APPS, auf ELITE_GPG normiert)."""
    if not entry:
        return 0.0
    goals = entry.get("goals") or 0.0
    apps = entry.get("appearances") or 0.0
    if apps < MIN_APPS or goals <= 0:
        return 0.0
    return round(min(1.0, (goals / apps) / ELITE_GPG), 3)


class TopscorerMomentumSignal(Signal):
    def name(self) -> str:
        return "topscorer_momentum"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        ts = context.get("topscorers") or {}
        if not ts:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        ht, at = threat(ts.get(home_id)), threat(ts.get(away_id))
        if ht == 0.0 and at == 0.0:
            return None

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        score, ev = 0.0, ""
        if side in ("home", "away"):
            mine, theirs = (ht if side == "home" else at), (at if side == "home" else ht)
            score = (mine - 0.5 * theirs) * MAX_PP
            name = (ts.get(home_id if side == "home" else away_id) or {}).get("name", "?")
            ev = f"Top-Torjäger {name} (Bedrohung {mine:.0%}) stützt {'Heim' if side=='home' else 'Auswärts'}"
        elif side == "over":
            score = ((ht + at) / 2.0) * MAX_PP * 0.7
            ev = f"Treffsichere Stürmer auf dem Platz (Heim {ht:.0%} / Auswärts {at:.0%}) → Tor-Tendenz"
        else:   # under: kein Argument
            return None

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:
            return None
        conf = round(min(0.6, 0.35 + max(ht, at) * 0.25), 2)
        return SignalResult(score=score, confidence=conf, evidence=ev,
                            metadata={"homeThreat": ht, "awayThreat": at})
