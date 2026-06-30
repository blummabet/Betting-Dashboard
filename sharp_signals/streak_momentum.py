"""
streak_momentum.py — Serien als Pick-Signal (29.06.2026, Lucas: Umkehrschluss zu „Signale
stärken den Streak"). Hat ein Team eine lange, von der EIGEN-Grundrate gestützte Serie in der
Markt-Richtung (z.B. 7× Über), ist das ein kleiner Zusatz-Hinweis für den Pick.

BEWUSST DISZIPLINIERT:
  · Nur O/U-2,5 + BTTS (die bepickten Märkte, für die compute_streaks Serien führt).
  · KLEIN gedeckelt (±MAX_PP) — eine Serie ≠ Edge (Pinnacle preist Form ein, Gambler's Fallacy).
  · form-Familie (registry SIGNAL_GROUPS) → Anti-Korr-Discount gegen form_trend/xg/h2h verhindert,
    dass dieselbe Form-Info doppelt zählt.
  · Nutzt die EIGEN-Tendenz (length + ratePct), NICHT den matchup/signal-adjustierten Status →
    kein Zirkel (Streak-Status hängt seinerseits an den Picks).
  · Der Bayesian-Loop kalibriert das Gewicht: ist es nur Fallacy, lernt er weight→niedrig.
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult

MIN_LENGTH   = 4      # kürzere Serien = Rauschen
MIN_RATE_PCT = 55     # Serie muss von der eigenen Grundrate gestützt sein
PER_STREAK   = 0.15   # pp pro gestützter Serie (× Länge-Faktor × Backed-Faktor)
MAX_PP       = 2.5    # harter Deckel (klein!)

# (Markt-Familie, Richtung) → (stützender Streak-Typ, gegenläufiger Streak-Typ)
_SUPPORT = {
    ("ou", +1):   ("over25", "under25"),
    ("ou", -1):   ("under25", "over25"),
    ("btts", +1): ("bttsYes", "bttsNo"),
    ("btts", -1): ("bttsNo", "bttsYes"),
}


def _market_family_dir(market: str):
    m = (market or "").lower()
    if "ecken" in m or "corner" in m or "karten" in m or "card" in m:
        return (None, None)
    if "über" in m or "uber" in m or "over" in m or "unter" in m or "under" in m:
        if "tore" not in m and "goal" not in m and not any(x in m for x in ["1.5", "2.5", "3.5", "1,5", "2,5", "3,5"]):
            return (None, None)
        is_under = "unter" in m or "under" in m
        return ("ou", -1 if is_under else +1)
    if "beide" in m or "btts" in m:
        return ("btts", -1 if ("nein" in m or " no" in m or m.endswith("no")) else +1)
    return (None, None)


def _pick_team_streak(streaks_for_team, stype, pref_venue):
    """Beste Serie eines Teams für einen Typ — venue-passend (Heim/Auswärts), sonst Gesamt."""
    best, best_score = None, -1
    for s in (streaks_for_team or []):
        if s.get("type") != stype:
            continue
        v = s.get("venue")
        score = 2 if v == pref_venue else (1 if v == "all" else 0)
        if score > best_score:
            best, best_score = s, score
    return best


class StreakMomentumSignal(Signal):
    """Lange, gestützte Serien beider Teams in der Markt-Richtung → kleiner Pick-Nudge."""

    def name(self) -> str:
        return "streak_momentum"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        fam, direction = _market_family_dir(pick.get("market", ""))
        if fam is None:
            return None
        idx = context.get("streaks") or {}
        if not idx:
            return None
        home_id, away_id = context.get("home_id"), context.get("away_id")
        sup_type, opp_type = _SUPPORT[(fam, direction)]

        score, parts = 0.0, []
        for tid, pref in ((str(home_id), "H"), (str(away_id), "A")):
            team_streaks = idx.get(tid) or []
            for stype, sign in ((sup_type, +1), (opp_type, -1)):
                s = _pick_team_streak(team_streaks, stype, pref)
                if not s:
                    continue
                length = s.get("length") or 0
                rate = s.get("ratePct")
                if length < MIN_LENGTH or rate is None or rate < MIN_RATE_PCT:
                    continue
                backed = max(0.0, min(1.0, (rate - 50) / 50.0))   # 50%→0, 100%→1
                contrib = sign * min(length, 8) * PER_STREAK * backed
                score += contrib
                if sign > 0:
                    parts.append(f"{s.get('team', tid)} {length}× {s.get('market', stype)}")

        if abs(score) < 0.25:   # zu schwach → nicht feuern
            return None
        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        # Confidence niedrig halten — bewusst ein leiser Zusatz, kein Hauptsignal.
        confidence = round(min(0.55, 0.35 + 0.05 * len(parts)), 2)
        if score > 0 and parts:
            ev = "🔥 Serien stützen: " + " · ".join(parts[:2])
        elif score < 0:
            ev = "🔥 Serien laufen gegen den Pick"
        else:
            ev = "🔥 Serien-Momentum neutral"
        return SignalResult(score=score, confidence=confidence, evidence=ev,
                            metadata={"family": fam, "direction": direction, "n_supporting": len(parts)})
