"""
sharp_signals/weather_signal.py — Hitze/Wetter-Penalty

Konzept:
  Teams aus kühlen Klimazonen haben historisch schlechtere Performance
  in Hitze ≥30°C, mit signifikantem xG-Verlust ab ~32°C+.
  Beispiele:
    - Norwegen, Schweden, Schottland, Russland: kalt-temperate Klima
      → -2.5pp Goals-Erwartung in 35°C+ Spielen
    - Mexico, Brasilien, Saudi-Arabien: tropisch/heiß
      → tolerant, neutral oder leicht im Vorteil
    - England, Deutschland, Niederlande: temperate
      → moderate Penalty (-1pp) in 35°C+

  Lucas's Hinweis: Anpfiff-Zeit ist entscheidend.
    Mittag (11-15 lokal) = volle Hitze (tempMax-nah)
    Abend (19-22 lokal)  = gedämpfte Hitze (-5 bis -8°C effektiv)

  Direction:
    Pick auf Über X Tore:
      - Heim cold-climate + ≥32°C Mittagsspiel: stark negativ
      - Beide heat-tolerant: neutral
    Pick auf Heim-Sieg:
      - Auswärts cold-climate + ≥32°C: positiv (Auswärts schwächer)
      - Heim cold-climate + ≥32°C: negativ
    Pick auf Auswärts-Sieg: spiegelbildlich

  Wenn temp < heat_threshold (default 30°C): kein Signal (Rauschen).

Context erwartet:
  weather[match_slug]: { temp, condition, windKph, ... }   ODER
  fixture mit `weather` Feld (gepiped in generate_wm_picks)
  home_id, away_id
  venue: für Lokal-Anpfiff-Zeit (Timezone-Offset)
  kickoff_time: "HH:MM" lokale Wien-Zeit (CEST)
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "heat_threshold":      30.0,    # Ab N°C beginnt das Signal
    "extreme_threshold":   35.0,    # Über N°C maximale Penalty
    "cold_team_score":      2.5,    # Magnitude bei cold-climate vs hot
    "temperate_team_score": 1.0,    # Magnitude bei temperate vs hot
    "kickoff_modifier_midday":  1.00,   # 11-15 lokal = volle Hitze
    "kickoff_modifier_afternoon": 0.80, # 16-18 lokal
    "kickoff_modifier_evening": 0.55,   # 19-21 lokal
    "kickoff_modifier_night":   0.35,   # 22+ lokal
    "confidence":          0.65,
}


# ── Klima-Klassifikation pro WM-Team ─────────────────────────────────────
# Heuristik basierend auf Hauptklima-Zone der Hauptstadt/Spielzeit Juni.
# "cold": jährliche Mitteltemp deutlich unter Spielort-Temp im Juni
# "temperate": leicht unter
# "hot": vergleichbar oder darüber → kein Heat-Penalty
TEAM_CLIMATE = {
    # Cold (kalt-temperate, schwer mit ≥32°C)
    "NOR": "cold", "SWE": "cold", "SCO": "cold", "RUS": "cold",
    "DEN": "cold", "ISL": "cold", "FIN": "cold",
    # Temperate (moderate Penalty)
    "ENG": "temperate", "GER": "temperate", "NED": "temperate",
    "BEL": "temperate", "FRA": "temperate", "AUT": "temperate",
    "SUI": "temperate", "CZE": "temperate", "POL": "temperate",
    "HUN": "temperate", "POR": "temperate", "ESP": "temperate",
    "ITA": "temperate", "CRO": "temperate", "BIH": "temperate",
    "TUR": "temperate", "UKR": "temperate", "USA": "temperate",
    "CAN": "temperate", "JPN": "temperate", "KOR": "temperate",
    "NZL": "temperate", "URU": "temperate", "ARG": "temperate",
    "CHI": "temperate", "AUS": "temperate",
    # Hot (tropisch/heiß, kein Penalty)
    "MEX": "hot", "BRA": "hot", "COL": "hot", "ECU": "hot", "PRY": "hot",
    "VEN": "hot", "PAN": "hot", "HTI": "hot", "CUW": "hot", "CPV": "hot",
    "SEN": "hot", "MAR": "hot", "EGY": "hot", "GHA": "hot", "CIV": "hot",
    "COD": "hot", "DZA": "hot", "TUN": "hot", "ZAF": "hot",
    "SAU": "hot", "QAT": "hot", "UAE": "hot", "IRN": "hot", "IRQ": "hot",
    "JOR": "hot", "UZB": "hot",
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("weather_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _kickoff_modifier(kickoff_time: str, venue: str, thresholds: dict) -> float:
    """
    Schätzt wie heiß es zur Anpfiff-Zeit ist (relativ zur Tages-Maxtemp).
    Lokale Anpfiff-Stunde:
      11-15 → volle Hitze (Modifier 1.00)
      16-18 → afternoon (0.80)
      19-21 → evening (0.55)
      22+ / 0-10 → night/morning (0.35)

    Lokale Stunde wird aus kickoff_time (Wien CEST = UTC+2) + Venue-TZ berechnet.
    Vereinfacht: Venue-TZ-Mapping inline.
    """
    if not kickoff_time:
        return thresholds["kickoff_modifier_afternoon"]
    try:
        h, m = kickoff_time.split(":")
        wien_hour = int(h)
    except Exception:
        return thresholds["kickoff_modifier_afternoon"]

    # Venue → Offset zu Wien (Sommerzeit Juni 2026: CEST = UTC+2)
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
    """
    Stundenversatz Venue-LocalTime relativ zu Wien-Sommerzeit (CEST = UTC+2).
    Juni 2026: USA/Kanada in DST (UTC-4 bis -7), Mexiko teils ohne DST.
    """
    if not venue:
        return 0
    v = venue.lower()
    # Eastern (UTC-4 DST) → 6h hinter Wien
    if any(x in v for x in ["new york", "metlife", "philadelphia", "boston",
                             "miami", "orlando", "atlanta", "toronto"]):
        return -6
    # Central (UTC-5 DST) → 7h hinter
    if any(x in v for x in ["dallas", "kansas city", "monterrey"]):
        return -7
    # Mountain (UTC-6 DST) → 8h hinter
    if "denver" in v:
        return -8
    # Pacific (UTC-7 DST) → 9h hinter
    if any(x in v for x in ["los angeles", "san francisco", "sofi", "rose bowl", "levi"]):
        return -9
    # Mexico City (CST, kein DST) → 7h hinter
    if "mexico city" in v or "azteca" in v or "guadalajara" in v:
        return -7
    return 0   # default kein Offset


def _outcome_side(market: str) -> str:
    m = (market or "").lower()
    is_goals = "tore" in m or "goals" in m
    if is_goals:
        if "über" in m or "over" in m:   return "over"
        if "unter" in m or "under" in m: return "under"
    if "heimsieg" in m or "doppelte chance — 1x" in m: return "home"
    if "auswärtssieg" in m or "auswartssieg" in m or "doppelte chance — x2" in m: return "away"
    if "dnb" in m and ("heim" in m or "home" in m): return "home"
    if "dnb" in m and ("ausw" in m or "away" in m): return "away"
    return "unknown"


def _get_weather(context: dict) -> dict | None:
    """Holt Weather-Daten aus context, gematcht auf die ECHTE Venue des Fixtures.

    FIX 12.06.2026: Vorher wurde nur per home/away-Substring + forecastAvailable
    gematcht — Datum UND Venue ignoriert. Bei umverlegten Spielen (z.B. QAT-SUI:
    real Levi's SF, aber ein veralteter wm_weather-Eintrag stand auf MetLife NY
    36.9°C) griff das Signal die FALSCHE Stadt → bogus Hitze-Penalty. Jetzt: nur
    Forecast der tatsächlichen Venue; passt keiner → KEIN Signal (lieber nichts
    als falsche Stadt)."""
    home_id, away_id = context.get("home_id"), context.get("away_id")
    venue = (context.get("venue") or "").strip().lower()
    weather_dict = context.get("weather") or {}
    if not (home_id and away_id):
        return None
    fallback = None
    for k, v in weather_dict.items():
        if not (home_id.lower() in k and away_id.lower() in k):
            continue
        if not (isinstance(v, dict) and v.get("forecastAvailable")
                and v.get("tempMax") is not None):
            continue
        wv = (v.get("venue") or "").strip().lower()
        if venue and wv:
            if wv == venue:
                return v          # exakte Venue-Übereinstimmung → beste Wahl
            continue              # echter Venue-Mismatch (Stale wie QAT-SUI) → skip
        fallback = fallback or v  # keine Venue-Info → als Fallback akzeptieren
    return fallback


class WeatherSignal(Signal):
    """Hitze-Penalty für Cold/Temperate-Climate Teams bei ≥30°C Anpfiff-Hitze."""

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "weather_signal"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        weather = _get_weather(context)
        if not weather or weather.get("tempMax") is None:
            return None
        temp_max = float(weather["tempMax"])
        if temp_max < self._t["heat_threshold"]:
            return None

        side = _outcome_side(pick.get("market", ""))
        if side == "unknown":
            return None

        home_id, away_id = context.get("home_id"), context.get("away_id")
        home_climate = TEAM_CLIMATE.get(home_id, "temperate")
        away_climate = TEAM_CLIMATE.get(away_id, "temperate")

        kickoff_mod = _kickoff_modifier(
            context.get("kickoff_time", ""), context.get("venue", ""), self._t
        )
        # FIX 09.06.2026: heat_intensity korrekt berechnen.
        # ALT (bug): effective_temp = temp_max * kickoff_mod → 30°C*0.8 = 24°C
        # → heat_intensity wurde immer 0, Signal feuerte nie auf O/U-Märkte
        # bei "echten" WM-Hitze-Temperaturen (30-35°C).
        # NEU: heat_intensity zuerst aus raw tempMax (Skala wie weit über Schwelle),
        # dann gedämpft mit kickoff_mod (Abend = halbierte Penalty vs Mittag).
        heat_intensity_raw = min(1.0, max(0.0,
            (temp_max - self._t["heat_threshold"]) /
            (self._t["extreme_threshold"] - self._t["heat_threshold"])))
        heat_intensity = heat_intensity_raw * kickoff_mod
        effective_temp = temp_max   # nur fürs Logging
        if heat_intensity <= 0:
            return None

        def _team_penalty(climate: str) -> float:
            if climate == "cold":      return self._t["cold_team_score"]
            if climate == "temperate": return self._t["temperate_team_score"]
            return 0.0   # hot = keine Penalty

        home_pen = _team_penalty(home_climate) * heat_intensity
        away_pen = _team_penalty(away_climate) * heat_intensity

        score = 0.0
        evidence_parts = []

        if side == "over":
            # Hitze + cold/temperate Teams → weniger Goals erwartet → negativ
            total_pen = home_pen + away_pen
            if total_pen <= 0.3:
                return None  # zu klein für Signal
            score = -total_pen
            if home_pen > 0:
                evidence_parts.append(f"{home_id} {home_climate}")
            if away_pen > 0:
                evidence_parts.append(f"{away_id} {away_climate}")
        elif side == "under":
            total_pen = home_pen + away_pen
            if total_pen <= 0.3:
                return None
            score = total_pen   # positiv für Under
            if home_pen > 0:
                evidence_parts.append(f"{home_id} {home_climate}")
            if away_pen > 0:
                evidence_parts.append(f"{away_id} {away_climate}")
        elif side == "home":
            # Heim-Sieg-Pick: positiv wenn Auswärts cold-climate, negativ wenn Heim cold
            score = away_pen - home_pen
            if abs(score) < 0.3:
                return None
            if away_pen > home_pen:
                evidence_parts.append(f"Auswärts {away_id} ({away_climate}) leidet")
            else:
                evidence_parts.append(f"Heim {home_id} ({home_climate}) leidet")
        elif side == "away":
            score = home_pen - away_pen
            if abs(score) < 0.3:
                return None
            if home_pen > away_pen:
                evidence_parts.append(f"Heim {home_id} ({home_climate}) leidet")
            else:
                evidence_parts.append(f"Auswärts {away_id} ({away_climate}) leidet")

        if not evidence_parts or score == 0:
            return None

        ko_label = "Mittag" if kickoff_mod >= 0.95 else \
                   "Nachmittag" if kickoff_mod >= 0.75 else \
                   "Abend"
        evidence = (f"🌡 {temp_max:.0f}°C {ko_label}-Anpfiff · "
                    + " · ".join(evidence_parts))

        return SignalResult(
            score=round(score, 2),
            confidence=round(self._t["confidence"], 2),
            evidence=evidence,
            metadata={
                "temp_max":         temp_max,
                "effective_temp":   round(effective_temp, 1),
                "kickoff_mod":      kickoff_mod,
                "home_climate":     home_climate,
                "away_climate":     away_climate,
                "heat_intensity":   round(heat_intensity, 2),
                "side":             side,
            },
        )
