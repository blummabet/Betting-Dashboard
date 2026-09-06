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


def poly_volumen(poly_snapshot) -> float | None:
    """USD-Volumen hinter einem Polymarket-Snapshot. None = nicht bekannt, NICHT 0.

    06.09.2026 (Lucas: „wir haben Poly, wir haben Betfair, wir tracken Wallets — und sind mit
    schlechter Engine unterwegs"). Er hatte recht, und hier lag der Beweis.

    `polymarket_sharp` und `steam_lag` lasen beide `poly_snapshot.get("poly_vol", 0) or 0` und
    gaten dann auf 5.000 bzw. 3.000 USD. Die Fixtures in `*_poly_prices.json → allFixtures`
    tragen das Volumen aber unter **`vol`**. Von 104 Liga-Fixtures hatte KEINE EINZIGE ein Feld
    `poly_vol` — 104 hatten `poly_hw`, die erste allein 182.263 USD unter `vol`.

    Folge: `vol` war immer 0, das Gate schlug immer zu, und **beide Signale haben in 318
    abgerechneten Picks kein einziges Mal gefeuert.** Nicht weil zu wenig Geld da war, sondern
    weil nach einem Feldnamen gefragt wurde, den die Produktion nie schreibt. Die Tests dazu
    bauten ihre Fixture mit `poly_vol` und waren gruen — ein Test, der die erfundene Form prueft
    statt der echten, deckt genau nichts ab (dieselbe Klasse wie die erfundene
    Over/Under-Fixture am 05.09.).

    Der Default ist deshalb `None` und nicht 0: „kein Volumen bekannt" und „kein Geld da" sind
    verschiedene Aussagen, und nur eine davon darf ein Signal stumm schalten.
    """
    if not isinstance(poly_snapshot, dict):
        return None
    for feld in ("vol", "poly_vol", "volume"):
        v = poly_snapshot.get(feld)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if v >= 0:
            return float(v)
    return None


def match_eintrag(container, context):
    """Eintrag zu DIESEM Spiel aus einer nach Spiel geschluesselten Datei holen.

    06.09.2026 (Lucas: „die anderen Signale muessen funktionieren"). Zweiter Fund derselben
    Art wie `poly_volumen`: die Daten lagen da, gefragt wurde mit dem falschen Schluessel.

    `smart_money` las `smartmoney[context["matchKey"]]`. Der Liga-matchKey ist
    `ENG-1-45-33` (Gruppe-Spieltag-Heim-Gast), `liga_poly_smartmoney.json` schluesselt aber
    nach `45-33` (Heim-ID-Gast-ID). Kein einziger Treffer — und damit **$3,04 Mio. Polymarket-
    Holder-Geld ueber 39 Spiele, das nie in einen Liga-Pick eingeflossen ist**, darunter
    Everton–Manchester United mit 2,16 Mio.

    In der WM stimmten die Formate zufaellig ueberein; deshalb feuerte das Signal dort (35-mal)
    und hier nie. Ein Signal, das in einem Datensatz laeuft, gilt schnell als „funktioniert".

    Reihenfolge: exakter matchKey, dann Heim-Gast, dann Gast-Heim (fuer Dateien, die die
    Ansetzung andersherum fuehren). Nichts gefunden -> None.
    """
    if not isinstance(container, dict) or not container:
        return None
    ctx = context if isinstance(context, dict) else {}
    kandidaten = []
    mk = ctx.get("matchKey")
    if mk:
        kandidaten.append(str(mk))
    h, a = ctx.get("home_id"), ctx.get("away_id")
    if h is not None and a is not None:
        kandidaten.append(f"{h}-{a}")
        kandidaten.append(f"{a}-{h}")
    for k in kandidaten:
        v = container.get(k)
        if v is not None:
            return v
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
