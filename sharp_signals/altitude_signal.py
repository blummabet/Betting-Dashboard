"""
sharp_signals/altitude_signal.py — Höhen-Vorteil-Signal

Konzept (Lucas 09.06.2026, Lücke aufgedeckt nach Wetter-Bug):
  travel_burden behandelt nur HÖHEN-DELTA (alt_shift) zwischen aufeinanderfolgenden
  Spielorten. Folge: MD1 ohne vorherigen Venue → alt_shift=0 → kein Signal.

  Aber: absolute Stadium-Höhe ist ein massiver echter Edge:
    · 2200m Mexico City: VO2max-Reduktion ~12-15% für Nicht-Akklimatisierte
    · 1550m Guadalajara: ~5-8% Reduktion
    · ≤500m: Meeresspiegel-Niveau, kein Effekt

  Akklimatisation:
    · Heimat-Höhe ≥1200m → gut akklimatisiert (Mexico, Ecuador, Bolivien)
    · Heimat-Höhe ≤500m → Niedrigland (Niederlande, England, Brasilien)
    · Zwischenwerte → moderat

  Direction:
    1X2: Heim-Bias wenn (venue >= 1500m AND home-team akklim. AND away-team Niedrigland)
    O/U-Über: leicht positiv (ermüdeter Auswärts kassiert mehr Gegentore)
    O/U-Unter: leicht negativ (analog)
    DC/AH: spiegelbildlich zu 1X2

  Kickoff-Modifier wie weather_signal:
    Mittag-Anpfiff = volle Hitze + volle Höhen-Belastung
    Abend           = Höhen-Belastung etwas reduziert (Körper weniger gestresst)

Context erwartet:
  home_id, away_id
  venue_altitude_m: int   (aus fixture, vom Caller gepiped)
  kickoff_time: "HH:MM" (Wien)
  venue: str (für Kickoff-Modifier-Berechnung, optional)
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "min_venue_altitude_m":  1200,   # Ab N Meter beginnt das Signal
    "full_effect_altitude_m": 2200,  # Bei N Meter voller Effekt
    "min_home_adv_altitude_m": 800,  # Heim-Team gilt als "akklimatisiert" ab N Meter Hauptstadt-Höhe
    "max_lowland_altitude_m":  500,  # Auswärts gilt als "Niedrigland" unter N Meter
    "score_home_1x2_pp":       2.5,  # Max-Score bei voller Höhe + voller Asymmetrie
    "score_ou_pp":             1.5,  # Max-Score O/U (Auswärts ermüdet → mehr Gegentore)
    "kickoff_modifier_midday":    1.00,
    "kickoff_modifier_afternoon": 0.85,
    "kickoff_modifier_evening":   0.65,
    "kickoff_modifier_night":     0.45,
    "min_signal_pp":           0.4,
    "confidence":              0.70,
}


# Hauptstadt-/Heimstadt-Höhe pro WM-Team (in Meter).
# Proxy für Akklimatisation: Spieler die in hohen Ligen spielen / aus hohen
# Ländern stammen sind tendenziell besser akklimatisiert.
TEAM_ALTITUDE = {
    # Hochland (≥1200m) — gut akklimatisiert
    "MEX":  2240,   # Mexico City
    "BOL":  3640,   # La Paz (nicht qualifiziert, für Vollständigkeit)
    "ECU":  2850,   # Quito
    "COL":  2640,   # Bogotá
    "PER":  3399,   # Cuzco / Lima ist Meeresspiegel — moderat
    "IRN":  1200,   # Tehran
    "JOR":  1170,   # Amman ~moderat
    "AUT":   170,   # Wien Niedrigland (Heimstadt nicht hoch trotz Alpen)
    "SUI":   408,   # Bern
    # Moderat (500-1200m) — leichte Akklimatisation
    "ZAF":  1750,   # Johannesburg
    "DZA":   424,   # Algier
    "TUR":   853,   # Ankara
    "SAU":   612,   # Riyadh
    "ESP":   667,   # Madrid
    "JPN":    40,   # Tokyo — Niedrigland
    "KOR":    38,   # Seoul — Niedrigland
    # Niedrigland (≤500m) — keine Akklimatisation
    "NED":     0,   "BEL":   28,  "ENG":   24,
    "FRA":    35,   "GER":   34,  "ITA":   21,
    "POR":   100,   "POL":  106,  "CZE":  237,
    "HUN":   106,   "DEN":    5,  "NOR":   23,
    "SWE":    28,   "FIN":    8,  "SCO":   47,
    "RUS":   124,   "UKR":  179,  "CRO":  157,
    "BIH":   500,   "SEN":    11, "MAR":   56,
    "EGY":    23,   "GHA":   61,  "CIV":   25,
    "COD":   240,   "TUN":    4,  "CPV":   35,
    "NZL":    20,   "URU":    43, "ARG":   25,
    "CHI":   520,   "AUS":    19, "BRA":   10,
    "USA":    10,   "CAN":   76,  "HTI":   98,
    "CUW":     8,   "QAT":   10,  "IRQ":   34,
    "UZB":   424,   "PAN":     2, "PRY":  125,
}


def _team_altitude(team_id: str) -> int:
    return TEAM_ALTITUDE.get(team_id, 200)   # default niedrig


def _kickoff_modifier(kickoff_time: str, venue: str, thresholds: dict) -> float:
    """Wie weather_signal: lokale Anpfiff-Stunde bestimmt Hitze/Höhen-Belastung."""
    if not kickoff_time:
        return thresholds["kickoff_modifier_afternoon"]
    try:
        h, _ = kickoff_time.split(":")
        wien_hour = int(h)
    except Exception:
        return thresholds["kickoff_modifier_afternoon"]

    venue_offset_h = _venue_offset_to_vienna(venue)
    local_hour = (wien_hour + venue_offset_h) % 24

    if 11 <= local_hour <= 15:
        return thresholds["kickoff_modifier_midday"]
    if 16 <= local_hour <= 18:
        return thresholds["kickoff_modifier_afternoon"]
    if 19 <= local_hour <= 21:
        return thresholds["kickoff_modifier_evening"]
    return thresholds["kickoff_modifier_night"]


def _venue_offset_to_vienna(venue: str) -> int:
    """Lokal vs CEST (UTC+2). Identisch zu weather_signal."""
    if not venue:
        return 0
    v = venue.lower()
    if any(x in v for x in ["new york", "metlife", "philadelphia", "boston",
                             "miami", "orlando", "atlanta", "toronto"]):
        return -6
    if any(x in v for x in ["dallas", "kansas city", "monterrey"]):
        return -7
    if "denver" in v:
        return -8
    if any(x in v for x in ["los angeles", "san francisco", "sofi", "rose bowl", "levi"]):
        return -9
    if "mexico city" in v or "azteca" in v or "guadalajara" in v:
        return -7
    return 0


def _outcome_side(market: str) -> str:
    m = (market or "").lower()
    if "tore" in m or "goals" in m:
        if "über" in m or "over" in m:   return "over"
        if "unter" in m or "under" in m: return "under"
    if "heimsieg" in m or "doppelte chance — 1x" in m: return "home"
    if "auswärtssieg" in m or "auswartssieg" in m or "doppelte chance — x2" in m: return "away"
    if "dnb" in m and ("heim" in m or "home" in m): return "home"
    if "dnb" in m and ("ausw" in m or "away" in m): return "away"
    if "ah heim" in m: return "home"
    if "ah auswärts" in m or "ah auswarts" in m: return "away"
    return "unknown"


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("altitude_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


class AltitudeSignal(Signal):
    """Heim-Vorteil bei Höhen-Stadien gegen Niedrigland-Auswärtsteams."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "altitude_signal"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        venue_alt = context.get("venue_altitude_m") or 0
        if venue_alt < self._t["min_venue_altitude_m"]:
            return None   # zu niedrig — kein Höhen-Effekt

        home_id = context.get("home_id")
        away_id = context.get("away_id")
        if not (home_id and away_id):
            return None

        home_alt = _team_altitude(home_id)
        away_alt = _team_altitude(away_id)

        # Intensität: wie "hoch" relativ zum max-effect-Punkt (2200m)
        alt_range = self._t["full_effect_altitude_m"] - self._t["min_venue_altitude_m"]
        intensity = min(1.0, max(0.0,
            (venue_alt - self._t["min_venue_altitude_m"]) / alt_range))

        # Akklimatisations-Asymmetrie: home-Vorteil nur wenn home_alt >= min_home_adv_altitude_m
        # UND away_alt <= max_lowland_altitude_m
        home_adapted = home_alt >= self._t["min_home_adv_altitude_m"]
        away_lowland = away_alt <= self._t["max_lowland_altitude_m"]

        if not (home_adapted and away_lowland):
            return None   # keine echte Asymmetrie

        # Kickoff-Modifier (Mittag = volle Belastung, Abend = halbiert)
        kickoff_mod = _kickoff_modifier(
            context.get("kickoff_time", ""), context.get("venue", ""), self._t)
        effective_intensity = intensity * kickoff_mod
        if effective_intensity <= 0.05:
            return None

        side = _outcome_side(pick.get("market", ""))
        if side == "unknown":
            return None

        max_1x2 = self._t["score_home_1x2_pp"]
        max_ou  = self._t["score_ou_pp"]

        score = 0.0
        if side == "home":
            score = +max_1x2 * effective_intensity
        elif side == "away":
            score = -max_1x2 * effective_intensity
        elif side == "over":
            score = +max_ou * effective_intensity   # Auswärts ermüdet → mehr Gegentore
        elif side == "under":
            score = -max_ou * effective_intensity

        if abs(score) < self._t["min_signal_pp"]:
            return None

        ko_label = ("Mittag" if kickoff_mod >= 0.95
                    else "Nachmittag" if kickoff_mod >= 0.80
                    else "Abend")
        evidence = (f"🏔 {venue_alt}m {ko_label}-Anpfiff · "
                    f"Heim {home_id} aus {home_alt}m (akklim.) · "
                    f"Auswärts {away_id} aus {away_alt}m (Niedrigland)")

        return SignalResult(
            score=round(score, 2),
            confidence=round(self._t["confidence"], 2),
            evidence=evidence,
            metadata={
                "venue_altitude_m":   venue_alt,
                "home_altitude_m":    home_alt,
                "away_altitude_m":    away_alt,
                "intensity_raw":      round(intensity, 2),
                "intensity_effective": round(effective_intensity, 2),
                "kickoff_mod":        kickoff_mod,
                "side":               side,
            },
        )
