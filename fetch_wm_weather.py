#!/usr/bin/env python3
"""
fetch_wm_weather.py — WM 2026 Wetterdaten
==========================================
Holt Wettervorhersagen für alle WM-Spielorte via Open-Meteo API.
Open-Meteo: kostenlos, kein API-Key, bis 16 Tage im Voraus.

Output: wm_weather.json
  {
    "generatedAt": "...",
    "matches": {
      "wm-ger-vs-civ-2026-06-17": {
        "venue": "AT&T Stadium, Dallas",
        "date": "2026-06-17",
        "tempMax": 35, "tempMin": 26,
        "precipMm": 2.1,
        "windKmh": 18,
        "weatherCode": 61,
        "condition": "Leichter Regen",
        "icon": "🌧️",
        "forecastAvailable": true
      }
    }
  }
"""

import json
import os
import glob
import urllib.request
import urllib.error
from datetime import datetime, timezone, date, timedelta

BASE         = os.path.dirname(os.path.abspath(__file__))
WEATHER_FILE = os.path.join(BASE, "wm_weather.json")
MATCHES_GLOB = os.path.join(BASE, "matches", "data", "wm-*.json")

# ── Venue → Koordinaten + Timezone ───────────────────────────────────────────
VENUE_COORDS = {
    "AT&T Stadium, Dallas":                   (32.7480, -97.0930, "America/Chicago"),
    "Arrowhead Stadium, Kansas City":         (39.0489, -94.4839, "America/Chicago"),
    "BMO Field, Toronto":                     (43.6332, -79.4186, "America/Toronto"),
    "Camping World Stadium, Orlando":         (28.5392, -81.3890, "America/New_York"),
    "Empower Field, Denver":                  (39.7439, -105.0201, "America/Denver"),
    "Estadio Akron, Guadalajara":             (20.7122, -103.4627, "America/Mexico_City"),
    "Estadio Azteca, Mexico City":            (19.3032,  -99.1506, "America/Mexico_City"),
    "Estadio BBVA, Monterrey":                (25.6690, -100.3120, "America/Monterrey"),
    "Gillette Stadium, Boston":               (42.0909,  -71.2643, "America/New_York"),
    "Hard Rock Stadium, Miami":               (25.9578,  -80.2388, "America/New_York"),
    "Levi's Stadium, San Francisco":          (37.4032, -121.9697, "America/Los_Angeles"),
    "Lincoln Financial Field, Philadelphia":  (39.9008,  -75.1675, "America/New_York"),
    "Mercedes-Benz Stadium, Atlanta":         (33.7554,  -84.4009, "America/New_York"),
    "MetLife Stadium, New York":              (40.8136,  -74.0744, "America/New_York"),
    "Rose Bowl, Los Angeles":                 (34.1613, -118.1676, "America/Los_Angeles"),
    "SoFi Stadium, Los Angeles":              (33.9535, -118.3392, "America/Los_Angeles"),
}

# ── WMO Wetter-Codes → Klartext + Emoji ──────────────────────────────────────
def _decode_weather(code: int) -> tuple[str, str]:
    if code == 0:                    return "Sonnig",           "☀️"
    if code in (1, 2):               return "Teilweise bewölkt","🌤️"
    if code == 3:                    return "Bewölkt",          "☁️"
    if code in (45, 48):             return "Neblig",           "🌫️"
    if code in (51, 53, 55):         return "Nieselregen",      "🌦️"
    if code in (61, 63):             return "Leichter Regen",   "🌧️"
    if code == 65:                   return "Starker Regen",    "🌧️"
    if code in (71, 73, 75, 77):     return "Schnee",           "❄️"
    if code in (80, 81, 82):         return "Regenschauer",     "🌦️"
    if code in (85, 86):             return "Schneeschauer",    "🌨️"
    if code in (95, 96, 99):         return "Gewitter",         "⛈️"
    return "Unbekannt", "🌡️"


# ── Open-Meteo API Fetch ──────────────────────────────────────────────────────
def fetch_venue_weather(lat: float, lon: float, tz: str) -> dict | None:
    """
    Fetcht tägliche Wettervorhersage für einen Venue.
    Gibt dict zurück: {date_str → {tempMax, tempMin, precipMm, windKmh, weatherCode}}
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        f"wind_speed_10m_max,weather_code"
        f"&timezone={tz}"
        f"&forecast_days=16"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "CocoBet/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  Open-Meteo Fehler ({lat},{lon}): {e}")
        return None

    daily = data.get("daily", {})
    dates     = daily.get("time", [])
    temp_max  = daily.get("temperature_2m_max", [])
    temp_min  = daily.get("temperature_2m_min", [])
    precip    = daily.get("precipitation_sum", [])
    wind      = daily.get("wind_speed_10m_max", [])
    codes     = daily.get("weather_code", [])

    result = {}
    for i, d in enumerate(dates):
        result[d] = {
            "tempMax":     round(temp_max[i], 1) if i < len(temp_max) and temp_max[i] is not None else None,
            "tempMin":     round(temp_min[i], 1) if i < len(temp_min) and temp_min[i] is not None else None,
            "precipMm":    round(precip[i], 1)   if i < len(precip)   and precip[i]   is not None else 0.0,
            "windKmh":     round(wind[i], 1)      if i < len(wind)     and wind[i]     is not None else None,
            "weatherCode": int(codes[i])           if i < len(codes)    and codes[i]    is not None else 0,
        }
    return result


# ── Hauptlogik ────────────────────────────────────────────────────────────────
def main():
    print("=== fetch_wm_weather.py ===")
    now_ts   = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    today    = date.today()
    max_date = today + timedelta(days=16)

    # 1. Alle Match-JSONs laden
    match_files = sorted(glob.glob(MATCHES_GLOB))
    print(f"  📋 {len(match_files)} Match-Dateien gefunden")

    matches_info = []
    venues_needed = set()
    for mf in match_files:
        try:
            d = json.load(open(mf, encoding="utf-8"))
        except Exception:
            continue
        slug  = d.get("slug", "")
        venue = d.get("venue", "")
        mdate = (d.get("date") or "")[:10]
        if not slug or not venue or not mdate:
            continue
        matches_info.append({"slug": slug, "venue": venue, "date": mdate})
        if venue in VENUE_COORDS:
            venues_needed.add(venue)

    print(f"  🏟️  {len(venues_needed)} einzigartige Venues")

    # 2. Wetter pro Venue fetchen (nur einmal pro Venue)
    venue_weather: dict[str, dict] = {}
    for venue in sorted(venues_needed):
        lat, lon, tz = VENUE_COORDS[venue]
        print(f"  🌡️  {venue} ({lat:.2f}°N)…", end=" ", flush=True)
        weather = fetch_venue_weather(lat, lon, tz)
        if weather:
            venue_weather[venue] = weather
            avail = sum(1 for d in weather if date.fromisoformat(d) <= max_date)
            print(f"✅ {len(weather)} Tage ({avail} im Vorhersage-Fenster)")
        else:
            print("❌ fehlgeschlagen")

    # 3. Wetter pro Match zuordnen
    results = {}
    no_forecast = 0
    for m in matches_info:
        slug  = m["slug"]
        venue = m["venue"]
        mdate = m["date"]

        try:
            match_date = date.fromisoformat(mdate)
        except Exception:
            continue

        in_window = match_date <= max_date
        w = None
        if in_window and venue in venue_weather:
            w = venue_weather[venue].get(mdate)

        if w:
            condition, icon = _decode_weather(w["weatherCode"])
            results[slug] = {
                "venue":             venue,
                "date":              mdate,
                "tempMax":           w["tempMax"],
                "tempMin":           w["tempMin"],
                "precipMm":          w["precipMm"],
                "windKmh":           w["windKmh"],
                "weatherCode":       w["weatherCode"],
                "condition":         condition,
                "icon":              icon,
                "forecastAvailable": True,
            }
        else:
            no_forecast += 1
            results[slug] = {
                "venue":             venue,
                "date":              mdate,
                "forecastAvailable": False,
            }

    # 4. Speichern
    output = {
        "generatedAt": now_ts,
        "forecastWindow": f"bis {max_date.isoformat()}",
        "matches": results,
    }
    with open(WEATHER_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with_forecast = len(results) - no_forecast
    print(f"\n✅ wm_weather.json gespeichert")
    print(f"   Mit Vorhersage: {with_forecast}  |  Zu weit in Zukunft: {no_forecast}")


if __name__ == "__main__":
    main()
