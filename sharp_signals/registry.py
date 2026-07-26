"""
sharp_signals/registry.py — Active-Signal-Registry + Weights

Alle aktiven Signale werden hier instanziert. Lern-Hook:
  signal_weights.json hält pro Signal aktuelle Vertrauenswürdigkeit.
  update_signal_weights.py aktualisiert das nach jedem resolved Pick.

Beim Hinzufügen neuer Signale:
  1. sharp_signals/<new>_signal.py mit Signal-Subclass
  2. Hier in ACTIVE_SIGNALS importieren + instanziieren
  3. signal_weights.json bekommt einen neuen Default-Eintrag (initial weight 1.0)
  4. Test in tests/test_<name>_signal.py
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from sharp_signals.base import Signal, SignalResult
from sharp_signals.lead_lag_bias import LeadLagBiasSignal
from sharp_signals.public_static_bias import PublicStaticBiasSignal
from sharp_signals.travel_burden import TravelBurdenSignal
from sharp_signals.injury_signal import InjurySignal
from sharp_signals.form_trend import FormTrendSignal
from sharp_signals.h2h_pattern import H2HPatternSignal
from sharp_signals.xg_strength import XGStrengthSignal
from sharp_signals.polymarket_sharp import PolymarketSharpSignal
from sharp_signals.steam_lag import SteamLagSignal
from sharp_signals.pressure_index import PressureIndexSignal
from sharp_signals.lineup_signal import LineupSignal
from sharp_signals.apif_predictions import ApifPredictionsSignal
from sharp_signals.weather_signal import WeatherSignal
from sharp_signals.incentive_signal import IncentiveSignal
from sharp_signals.altitude_signal import AltitudeSignal
from sharp_signals.chance_creation import ChanceCreationSignal
from sharp_signals.form_rating import FormRatingSignal
from sharp_signals.freshness_signal import FreshnessLegSignal
from sharp_signals.smart_money import SmartMoneySignal
from sharp_signals.league_pressure import LeaguePressureSignal
from sharp_signals.fixture_congestion import FixtureCongestionSignal
from sharp_signals.topscorer_momentum import TopscorerMomentumSignal
from sharp_signals.coach_change import CoachChangeSignal
from sharp_signals.transfer_shift import TransferShiftSignal
from sharp_signals.streak_momentum import StreakMomentumSignal
from sharp_signals.reverse_line_move import ReverseLineMoveSignal
from sharp_signals.opener_move import OpenerMoveSignal
from sharp_signals.multi_book_steam import MultiBookSteamSignal
from sharp_signals.game_state_openness import GameStateOpennessSignal
from sharp_signals.mls_travel import MLSTravelSignal
from sharp_signals.move_following import MoveFollowingSignal
from sharp_signals.venue_form import VenueFormSignal


# Pro-Profil deaktivierte Signale (25.06.2026, Lucas: Liga auf WM-Stack). Manche WM-only-Signale
# (incentive_signal liest Standings → würde Liga-Tabellenplatz fälschlich als Gruppen-Quali deuten;
# altitude/weather/travel/smart_money/polymarket_sharp) müssen für Liga HART aus — None-Fallback
# reicht nicht, weil z.B. Incentive auf der vorhandenen Liga-Tabelle Unsinn feuern würde.
# Liste kommt aus cocobet_config.json profiles.<active>.disabled_signals (env COCOBET_PROFILE).
def _load_disabled_signals() -> set:
    # RAW lesen (nicht cocobet_config.CONFIG): _resolve_active_profile behält nur bekannte
    # Sektionen → die flache disabled_signals-Liste würde sonst rausgefiltert.
    try:
        import json
        import os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        profiles = raw.get("profiles", {})
        active = os.environ.get("COCOBET_PROFILE") or profiles.get("active", "wm2026")
        return set((profiles.get(active) or {}).get("disabled_signals") or [])
    except Exception:
        return set()


_DISABLED_SIGNALS = _load_disabled_signals()


# Liste aller aktiv evaluierten Signale.
# Reihenfolge ist nur kosmetisch (Output-Reihenfolge auf der Card).
ACTIVE_SIGNALS: list[Signal] = [
    LeadLagBiasSignal(),
    PublicStaticBiasSignal(),
    TravelBurdenSignal(),
    InjurySignal(),
    FormTrendSignal(),
    H2HPatternSignal(),
    XGStrengthSignal(),
    PolymarketSharpSignal(),
    SteamLagSignal(),
    PressureIndexSignal(),
    LineupSignal(),
    ApifPredictionsSignal(),
    WeatherSignal(),
    IncentiveSignal(),
    AltitudeSignal(),
    ChanceCreationSignal(),
    FormRatingSignal(),
    FreshnessLegSignal(),
    SmartMoneySignal(),
    LeaguePressureSignal(),   # Liga-Pendant zu incentive (25.06.2026); no-op für WM (group_id A-L)
    FixtureCongestionSignal(),  # Erschöpfung/Spielstau aus Ruhetagen (26.06.2026); Schläfer bis englische Woche
    TopscorerMomentumSignal(),  # Top-Torjäger-Bedrohung (26.06.2026); form-Familie, früh ~neutral
    CoachChangeSignal(),        # Neue-Trainer-Bounce (26.06.2026); context-Familie, zerfällt über 75d
    TransferShiftSignal(),      # Schlüsselspieler-Abgang (26.06.2026); context-Familie
    StreakMomentumSignal(),     # Serien als Pick-Signal (29.06.2026, Lucas); form-Familie, klein+gelernt
    ReverseLineMoveSignal(),    # 09.07.2026: Linie bewegt gegen Public → Sharp-Seite (RLM-Proxy)
    OpenerMoveSignal(),         # 09.07.2026: schärfster früher Linien-Abschnitt (Sharp Window)
    MultiBookSteamSignal(),     # 09.07.2026: Pinnacle+Betfair korroborieren vs Public
    GameStateOpennessSignal(),  # 09.07.2026: asymmetrische Verzweiflung → Über/BTTS
    MLSTravelSignal(),          # 09.07.2026: MLS Reise/Höhe/Turf-Bürde; nur MLS (Venue-Tabelle)
    MoveFollowingSignal(),      # 25.07.2026: Move-Groesse + Zustands-Bestaetigung; nur liga_default (Top-5, backtest-validiert)
    VenueFormSignal(),          # 25.07.2026: Heim/Auswaerts-Split + Zuletzt-Ueber-Rate; liga+mls (Ortsform aus venueSeq)
]


def _weights_path() -> Path:
    # Dataset-Modus: jeder Datensatz lernt EIGENE Gewichte — WM signal_weights.json, Liga
    # liga_signal_weights.json, MLS mls_signal_weights.json. 29.06.2026: dataset-aware via
    # cocobet_dataset (vorher binär == "liga" → MLS hätte die WM-Gewichte kontaminiert).
    import cocobet_dataset as D
    return D.file("signal_weights.json", "liga_signal_weights.json")


def load_signal_weights() -> dict:
    """
    Lädt signal_weights.json. Falls nicht vorhanden oder ein Signal noch nicht
    drin ist, default = 1.0.

    Format:
      {
        "lead_lag_bias": {
          "weight": 1.0,
          "n_observations": 0,
          "wins_when_triggered": 0,
          "last_updated": "2026-06-07T..."
        },
        ...
      }
    """
    path = _weights_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_signal_weights(weights: dict) -> None:
    """Schreibt signal_weights.json atomar."""
    path = _weights_path()
    tmp  = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_weight(weights: dict, signal_name: str) -> float:
    """Aktuelles Vertrauen für ein Signal (default 1.0 wenn ungesehen)."""
    entry = weights.get(signal_name) or {}
    w = entry.get("weight")
    return float(w) if isinstance(w, (int, float)) else 1.0


# ── Anti-Korrelation: Signal-Gruppen die dasselbe messen ──────────────────
# Wenn mehrere Signale aus derselben Gruppe gleichzeitig triggern, ist das
# meist ein Effekt (nicht 3 unabhängige Beobachtungen). Wir nehmen nur das
# stärkste mit voller Gewichtung, der Rest wird mit CORRELATION_DISCOUNT
# gedämpft.
#
#   sharp_money_family:  alle Signale die auf Pinnacle/Polymarket-Move basieren
#   form_family:         alle Signale die auf Vergangenheits-Form basieren
#   public_family:       alle Signale die auf Public-vs-Sharp-Bias basieren
SIGNAL_GROUPS: dict[str, str] = {
    "lead_lag_bias":      "sharp_money",
    "steam_lag":          "sharp_money",
    "polymarket_sharp":   "sharp_money",
    # Neue Mikrostruktur-Signale (09.07.2026) — alle basieren auf Pinnacle-Linienbewegung / Sharp-vs-
    # Public → sharp_money-Familie, Anti-Korr-Discount verhindert Mehrfachzählung desselben Moves.
    "reverse_line_move":  "sharp_money",
    "opener_move":        "sharp_money",
    "multi_book_steam":   "sharp_money",
    # move_following (25.07.2026): Move-Groessen-Confirm + Zustands-Gate — basiert auf demselben
    # Pinnacle-Move → sharp_money-Familie, Anti-Korr-Discount verhindert Doppelzaehlung.
    "move_following":     "sharp_money",
    # venue_form (25.07.2026): Heim/Auswaerts-konditionierte Form — Angriffs-/Form-Info →
    # form-Familie, Anti-Korr-Discount gegen form_trend/xg_strength.
    "venue_form":         "form",
    # game_state_openness nutzt dieselbe Tabellen-Druck-Story wie league_pressure → incentive-Familie.
    "game_state_openness": "incentive",
    # mls_travel: Spielort-/Fitness-Faktor wie travel_burden/injury/congestion → context-Familie.
    "mls_travel":         "context",
    "form_trend":         "form",
    "xg_strength":        "form",
    "h2h_pattern":        "form",
    # chance_creation + form_rating: attackierende Qualität / Performance — stark
    # mit xg_strength korreliert (Schüsse→xG). Bewusst in dieselbe form-Familie →
    # Anti-Korr-Discount (0.4) verhindert Doppelzählung des Angriffs-Edges.
    "chance_creation":    "form",
    "form_rating":        "form",
    # topscorer_momentum: konzentrierte Angriffs-Bedrohung (Top-Torjäger) — gehört zur Angriffs-/
    # form-Familie (Anti-Korr mit xg_strength/chance_creation/form_trend → kein Doppel-Edge).
    "topscorer_momentum": "form",
    # streak_momentum: lange gestützte Serien = Vergangenheits-Form → form-Familie. Anti-Korr-Discount
    # gegen form_trend/xg/h2h verhindert, dass dieselbe Form-Info doppelt in die Conviction zählt.
    "streak_momentum":    "form",
    "public_static_bias": "public",
    "travel_burden":      "context",
    "injury":             "context",
    # fixture_congestion (Ruhetage/Erschöpfung) — auch ein Fitness-/Kontext-Faktor wie Reise/Injury.
    # Anti-Korr-Discount: müde + verletzt + lange Reise sollen nicht dreifach denselben Edge zählen.
    "fixture_congestion": "context",
    # coach_change (situativ) + transfer_shift (dauerhafter Spielerverlust, verwandt mit injury/lineup)
    # — beide in die context-Familie, Anti-Korr-Discount falls sie mit den anderen Kontext-Faktoren
    # zusammenfallen (z.B. Schlüsselabgang + Verletzung gleichzeitig).
    "coach_change":       "context",
    "transfer_shift":     "context",
    # pressure_index in dieselbe Familie wie incentive_signal (21.06.2026, Lucas):
    # beide modellieren am Spieltag 3 dieselbe Qualifikations-Asymmetrie (muss gewinnen /
    # schon durch → Gegenseite). Vorher in „context" + incentive in eigener Familie →
    # KEIN Discount → die Quali-Story zählte doppelt (MEX-CZE: Druck +2,1 UND Anreiz +3,5
    # = ~+5,6pp aus EINEM Fakt). Jetzt geteilte Familie → stärkstes Signal voll, das
    # zweite (die Echo-Wertung) auf 40% gedämpft. Greift nur wenn BEIDE feuern (MD3-Quali).
    "pressure_index":     "incentive",
    # league_pressure (Liga-Pendant) in dieselbe „incentive"-Familie — gleiche Tabellen-/Anreiz-Story,
    # Anti-Korr-Discount falls es je mit incentive/pressure_index zusammenfällt (25.06.2026).
    "league_pressure":    "incentive",
    # weather_signal in dieselbe context-Familie wie Travel-Burden + Injury —
    # alle drei sind venue/spielort-bedingte Faktoren. Anti-Korr-Discount sinnvoll
    # damit Travel + Heat zusammen nicht doppelt zählen (Bsp: lange Reise + Hitze
    # in Dallas würden sonst beide gleichzeitig voll greifen).
    "weather_signal":     "context",
    # altitude_signal ist auch context (Spielort-Faktor wie Wetter/Reise/Injury).
    # Anti-Korr-Discount mit weather sinnvoll: Mexico City 2200m + Hitze sollten
    # sich nicht doppelt addieren wenn beide Cold-Team-Effekt modellieren.
    "altitude_signal":    "context",
    # lineup_signal ist UNIQUE (kein Anti-Korrelations-Discount):
    # T-1h Aufstellungs-Info ist orthogonal zu allen anderen Signalen —
    # die anderen modellieren historische/statische Daten, lineup_signal
    # injiziert die spätestmögliche realtime Wahrheit. Volle Gewichtung.
    "lineup_signal":      "unique",
    # apif_predictions ist auch UNIQUE — ein externes Drittes-Modell
    # (API-Football's eigenes Pricing) vergleicht gegen Pinnacle. Liegt
    # orthogonal zu unserem Skellam+Elo und zu allen Signal-Familien.
    "apif_predictions":   "unique",
    # incentive_signal — eigene Familie. Anreiz-Strukturen (Bracket-Asymmetrie,
    # Venue-Distanz, Qualifikations-Math) sind orthogonal zu Sharp-Money/Form/
    # Public/Context. Kein Discount.
    "incentive_signal":   "incentive",
}
CORRELATION_DISCOUNT = 0.4   # zweites Signal aus selber Gruppe nur zu 40%


def _apply_anti_correlation(signal_outputs: list[dict]) -> list[dict]:
    """
    Gruppiert Signale nach Korrelations-Familie. Pro Gruppe: stärkster Score
    voll, alle weiteren auf CORRELATION_DISCOUNT × Score gedämpft.
    Mutiert die `weighted_score` Felder in-place und gibt die Liste zurück.
    """
    # Sortiere innerhalb jeder Gruppe nach |weighted_score| absteigend
    by_group: dict[str, list[dict]] = {}
    for s in signal_outputs:
        g = SIGNAL_GROUPS.get(s["name"], "unique")
        by_group.setdefault(g, []).append(s)

    for g, members in by_group.items():
        if g == "unique" or len(members) <= 1:
            continue
        members.sort(key=lambda x: abs(x["weighted_score"]), reverse=True)
        for idx, m in enumerate(members):
            if idx == 0:
                continue   # stärkster bleibt voll
            m["weighted_score"] = round(m["weighted_score"] * CORRELATION_DISCOUNT, 2)
            m["correlation_discount_applied"] = CORRELATION_DISCOUNT
    return signal_outputs


def evaluate_signals(pick: dict, context: dict,
                     weights: Optional[dict] = None) -> dict:
    """
    Ruft alle aktiven Signale auf, sammelt die Results, gewichtet sie.

    Anti-Korrelation: Signale aus derselben Gruppe (z.B. Sharp-Money) zählen
    nur das stärkste voll; weitere werden gedämpft (CORRELATION_DISCOUNT).

    Returns:
      {
        "signals": [
          {"name": "lead_lag_bias", "score": +2.5, "confidence": 0.7,
           "evidence": "...", "weight": 1.0, "weighted_score": +2.5,
           "correlation_discount_applied": null | 0.4},
          ...
        ],
        "combined_score_pp":  float,  # gewichteter Score (nach Anti-Korrelation)
        "n_positive_signals": int,    # für Min-Threshold-Logik
        "n_negative_signals": int,
        "highest_confidence": float,
        "evidence_lines":     [str, ...]
      }
    """
    if weights is None:
        weights = load_signal_weights()

    signal_outputs = []
    evidence_lines = []
    max_conf       = 0.0

    for signal in ACTIVE_SIGNALS:
        if signal.name() in _DISABLED_SIGNALS:
            continue   # pro-Profil deaktiviert (z.B. WM-only Signale im liga_default)
        try:
            result = signal.evaluate(pick, context)
        except Exception as e:
            result = None
            print(f"  ⚠️  Signal {signal.name()} crashed: {e}")
        if result is None:
            continue

        w = get_weight(weights, signal.name())
        weighted_score = result.score * w * result.confidence
        max_conf       = max(max_conf, result.confidence)
        evidence_lines.append(f"{signal.name()}: {result.evidence}")

        signal_outputs.append({
            "name":          signal.name(),
            "score":         result.score,
            "confidence":    result.confidence,
            "evidence":      result.evidence,
            "weight":        w,
            "weighted_score": round(weighted_score, 2),
            "metadata":      result.metadata,
        })

    # Anti-Korrelation anwenden (in-place auf weighted_score)
    signal_outputs = _apply_anti_correlation(signal_outputs)

    # Combined-Score: sum of weighted_score / sum of effective weights
    # (gewichtet by confidence × weight × discount-effective)
    weighted_sum = sum(s["weighted_score"] for s in signal_outputs)
    sum_of_w = 0.0
    for s in signal_outputs:
        eff_w = s["weight"] * s["confidence"]
        if s.get("correlation_discount_applied"):
            eff_w *= s["correlation_discount_applied"]
        sum_of_w += eff_w
    combined = weighted_sum / sum_of_w if sum_of_w > 0 else 0.0

    n_pos = sum(1 for s in signal_outputs if s["score"] > 0)
    n_neg = sum(1 for s in signal_outputs if s["score"] < 0)

    return {
        "signals":            signal_outputs,
        "combined_score_pp":  round(combined, 2),
        "n_positive_signals": n_pos,
        "n_negative_signals": n_neg,
        "highest_confidence": round(max_conf, 2),
        "evidence_lines":     evidence_lines,
    }
