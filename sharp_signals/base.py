"""
sharp_signals/base.py — Signal-Interface

Jedes Signal in sharp_signals/ implementiert dieses Interface:
  · name() → str (eindeutig, wird als Key in signal_weights.json verwendet)
  · evaluate(pick, context) → SignalResult oder None

SignalResult enthält den Score (positiv = "wir mögen den Pick", negativ = "Achtung"),
eine Confidence (0..1 wie sicher das Signal sich ist), und nachvollziehbare
Evidence (was hat zum Signal geführt — das wird auf der Card angezeigt).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from abc import ABC, abstractmethod
from typing import Optional, Any


def market_side(market: str) -> Optional[str]:
    """Pick-Markt → 'home' | 'away' | 'over' | 'under' | None. EINE Quelle für alle Signale
    (26.06.2026 Konsolidierung — vorher in jedem Signal kopiert). Kürzere Substrings ('1x'/'x2'/
    'ah ausw') decken auch die längeren Labels ('doppelte chance — 1x', 'ah auswärts') ab."""
    m = (market or "").lower()
    if "über" in m or "uber" in m or "over" in m:
        return "over"
    if "unter" in m or "under" in m:
        return "under"
    if "heimsieg" in m or "1x" in m or "ah heim" in m or ("dnb" in m and "heim" in m):
        return "home"
    if ("auswärtssieg" in m or "auswartssieg" in m or "x2" in m or "ah ausw" in m
            or ("dnb" in m and ("ausw" in m or "away" in m))):
        return "away"
    return None


@dataclass
class SignalResult:
    """
    Ergebnis eines Signals für einen Pick.

    score:        Empfehlung in pp gegen Pinnacle-implied. Positiv = ÜBER-pricing
                  vom Markt (für uns gut → besseres Edge). Negativ = das Signal
                  warnt vor dem Pick.
    confidence:   0.0 bis 1.0 — wie zuverlässig das Signal sich selbst einstuft
                  (basierend auf Sample-Size, Daten-Frische, etc.)
    evidence:     Lesbare Begründung — wird auf der Community-Card angezeigt:
                  "Pinnacle dropte 4pp Heim, William Hill noch nicht nachgezogen"
    metadata:     Beliebige Roh-Daten, vorrangig fürs Lern-Update (welche Quote
                  vor/nach, welche Bookies, etc.)
    """
    score:      float
    confidence: float
    evidence:   str
    metadata:   dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Signal(ABC):
    """Abstract base für alle Signal-Implementierungen."""

    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Signal-Name. Wird als Key in signal_weights.json verwendet."""
        ...

    @abstractmethod
    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        """
        Evaluiert das Signal für einen Pick.

        Args:
            pick: Der Pick aus generate_wm_picks (market, edgePP, modelOdds, odds, …)
            context: {
                "matchKey":        "MEX-ZAF",
                "homeId"/"awayId": "MEX"/"ZAF",
                "odds_history":    [{ts, hw, dr, aw, bk}, …],  # Pinnacle + Soft-Books
                "form":            { homeId: {…}, awayId: {…} },
                "travel":          { teamId: {…} },
                "injuries":        { teamId: [{…}, …] },
                "h2h":             { games, …},
                "snapshot_ts":     "2026-06-07T14:00:00Z"  # für Zeitfenster-Berechnungen
            }

        Returns:
            SignalResult wenn das Signal Anwendung findet, sonst None.
            Wichtig: None bedeutet "nicht auswertbar", nicht "neutral".
            Für neutrale Bewertung: SignalResult(score=0, confidence=…, evidence=…)
        """
        ...
