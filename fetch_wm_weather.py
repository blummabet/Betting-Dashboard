#!/usr/bin/env python3
"""
fetch_wm_weather.py — WM 2026 Wetterdaten
==========================================
Holt Wettervorhersagen für alle WM-Spielorte via WeatherAPI.com.
WeatherAPI: 1M Calls/Monat gratis, 14-Tage-Forecast, deutlich stabiler als
das vorher genutzte Open-Meteo (das in unserer Umgebung 403 Forbidden gab).

API-Doku: https://www.weatherapi.com/docs/

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
        "weatherCode": 1063,
        "condition": "Leichter Regen",
        "icon": "🌧️",
        "forecastAvailable": true
      }
    }
  }

Umgebungsvariable:
  WEATHERAPI_KEY — Key von weatherapi.com (gratis registrieren)
"""

import json
import os
import glob
import urllib.request
import urllib.error
import urllib.parse
import time
from datetime import datetime, timezone, date, timedelta

BASE         = os.path.dirname(os.path.abspath(__file__))
WEATHER_FILE = os.path.join(BASE, "wm_weather.json")
MATCHES_GLOB = os.path.join(BASE, "matches", "data", "wm-*.json")

WEATHERAPI_KEY = (os.environ.get("WEATHERAPI_KEY") or "").strip()
WEATHERAPI_URL = "https://api.weatherapi.com/v1/forecast.json"
FORECAST_DAYS  = 14   # Free-Tier-Limit von WeatherAPI

# ── Venue → Koordinaten ──────────────────────────────────────────────────────
# Timezone-Info wird von WeatherAPI selbst geliefert, brauchen wir nicht mehr.
VENUE_COORDS = {
    "AT&T Stadium, Dallas":                   (32.7480, -97.0930),
    "Arrowhead Stadium, Kansas City":         (39.0489, -94.4839),
    "BMO Field, Toronto":                     (43.6332, -79.4186),
    "Estadio Akron, Guadalajara":             (20.7122, -103.4627),
    "Estadio Azteca, Mexico City":            (19.3032,  -99.1506),
    "Estadio BBVA, Monterrey":                (25.6690, -100.3120),
    "Gillette Stadium, Boston":               (42.0909,  -71.2643),
    "Hard Rock Stadium, Miami":               (25.9578,  -80.2388),
    "Levi's Stadium, San Francisco":          (37.4032, -121.9697),
    "Lincoln Financial Field, Philadelphia":  (39.9008,  -75.1675),
    "Mercedes-Benz Stadium, Atlanta":         (33.7554,  -84.4009),
    "MetLife Stadium, New York":              (40.8136,  -74.0744),
    "Rose Bowl, Los Angeles":                 (34.1613, -118.1676),
    "SoFi Stadium, Los Angeles":              (33.9535, -118.3392),
    # FIX 12.06.2026: fehlten komplett → diese 3 Host-Städte bekamen NIE Wetter.
    "BC Place, Vancouver":                    (49.2767, -123.1119),
    "Lumen Field, Seattle":                   (47.5952, -122.3316),
    "NRG Stadium, Houston":                   (29.6847,  -95.4107),
}


def _resolve_coords(venue: str):
    """Venue-String → (lat, lon), TOLERANT (FIX 12.06.2026). Die korrigierten
    Venues aus wm2026-data weichen leicht von den VENUE_COORDS-Keys ab
    ('Levi's Stadium, San Francisco Bay Area' vs '…San Francisco';
    'MetLife …, New York New Jersey' vs '…New York') → exakter Match scheiterte
    → kein Wetter für 23 umverlegte Spiele. Jetzt: Match per Stadion-Name."""
    if not venue:
        return None
    if venue in VENUE_COORDS:
        return VENUE_COORDS[venue]
    vlow = venue.lower()
    # Stadion-Name (Teil vor dem Komma) ist eindeutig → robustestes Kriterium
    for k, c in VENUE_COORDS.items():
        stadium = k.split(",")[0].strip().lower()
        if stadium and stadium in vlow:
            return c
    # Fallback: Stadt-Teil
    for k, c in VENUE_COORDS.items():
        city = k.split(",")[-1].strip().lower()
        if city and city in vlow:
            return c
    return None

# ── WeatherAPI Condition-Code → Klartext + Emoji ─────────────────────────────
# Codes: https://www.weatherapi.com/docs/weather_conditions.json
def _decode_weather(code: int) -> tuple[str, str]:
    if code == 1000:                                       return "Sonnig",            "☀️"
    if code in (1003,):                                    return "Teilweise bewölkt", "🌤️"
    if code in (1006, 1009):                               return "Bewölkt",           "☁️"
    if code in (1030, 1135, 1147):                         return "Neblig",            "🌫️"
    if code in (1063, 1150, 1153, 1180, 1183, 1240, 1249): return "Leichter Regen",    "🌧️"
    if code in (1186, 1189, 1192, 1195, 1243, 1246):       return "Starker Regen",     "🌧️"
    if code in (1066, 1069, 1114, 1117, 1210, 1213, 1216,
                1219, 1222, 1225, 1255, 1258):             return "Schnee",            "❄️"
    if code in (1072, 1168, 1171, 1198, 1201, 1204, 1207,
                1237, 1252, 1261, 1264):                   return "Eisregen/Graupel",  "🌨️"
    if code in (1087, 1273, 1276, 1279, 1282):             return "Gewitter",          "⛈️"
    return "Unbekannt", "🌡️"


# ── WeatherAPI Fetch ─────────────────────────────────────────────────────────
def fetch_venue_weather(lat: float, lon: float) -> dict | None:
    """
    Fetcht 14-Tage tägliche Vorhersage für einen Venue.
    Returns dict: {date_str → {tempMax, tempMin, precipMm, windKmh, weatherCode}}
    """
    if not WEATHERAPI_KEY:
        print("    ⚠️  WEATHERAPI_KEY nicht gesetzt — skip")
        return None

    params = urllib.parse.urlencode({
        "key":  WEATHERAPI_KEY,
        "q":    f"{lat},{lon}",
        "days": FORECAST_DAYS,
        "aqi":  "no",
        "alerts": "no",
    })
    url = f"{WEATHERAPI_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "CocoBet/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception: pass
        print(f"    ⚠️  WeatherAPI HTTP {e.code} ({lat},{lon}): {body}")
        return None
    except Exception as e:
        print(f"    ⚠️  WeatherAPI Fehler ({lat},{lon}): {e}")
        return None

    forecast_days = data.get("forecast", {}).get("forecastday", []) or []
    result = {}
    for fd in forecast_days:
        d_str = fd.get("date")
        day = fd.get("day", {})
        if not d_str: continue
        condition = day.get("condition", {}) or {}
        # Stündliche Temperaturen (FIX 13.06.2026) — für die echte Anpfiff-Temperatur
        # statt des Tagesmax. (epoch_utc, temp_c) je Stunde; Match per UTC-Epoch.
        hours = []
        for h in (fd.get("hour") or []):
            ep = h.get("time_epoch"); tc = h.get("temp_c")
            if ep is not None and tc is not None:
                hours.append([int(ep), round(tc, 1)])
        result[d_str] = {
            "tempMax":     round(day.get("maxtemp_c"), 1) if day.get("maxtemp_c") is not None else None,
            "tempMin":     round(day.get("mintemp_c"), 1) if day.get("mintemp_c") is not None else None,
            "precipMm":    round(day.get("totalprecip_mm", 0) or 0, 1),
            "windKmh":     round(day.get("maxwind_kph"), 1) if day.get("maxwind_kph") is not None else None,
            "weatherCode": int(condition.get("code", 0) or 0),
            "hours":       hours,
        }
    return result


# ── Hauptlogik ────────────────────────────────────────────────────────────────
def _group_fixtures(wm: dict):
    """Alle Gruppenspiel-Fixtures."""
    for g in (wm.get("groups") or {}).values():
        for fx in (g.get("fixtures") or []):
            yield fx


def _ko_fixtures(wm: dict):
    """bothResolved KO-Spiele (home+away gesetzt) — fürs Wetter genauso relevant wie Gruppenspiele.
    Offene Paarungen (TBD) haben kein Venue-relevantes Spiel → übersprungen."""
    for fx in (wm.get("koFixtures") or []):
        if fx.get("home") and fx.get("away"):
            yield fx


def main():
    print("=== fetch_wm_weather.py (WeatherAPI) ===")
    if not WEATHERAPI_KEY:
        print("  ❌ WEATHERAPI_KEY nicht gesetzt — Abbruch (Secret in GitHub Actions setzen)")
        return
    now_ts   = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    today    = date.today()
    max_date = today + timedelta(days=FORECAST_DAYS)

    # 1. Fixtures aus wm2026-data.json (Single Source of Truth, KORRIGIERTE Venues/
    #    Daten) — FIX 12.06.2026: vorher aus matches/data/wm-*.json (stale, vom
    #    Venue-Fix nie angefasst) → Wetter für falsche Stadt (z.B. QAT-SUI NY statt SF).
    wm_path = os.path.join(BASE, "wm2026-data.json")
    try:
        wm = json.load(open(wm_path, encoding="utf-8"))
    except Exception as e:
        print(f"  ❌ wm2026-data.json nicht lesbar: {e}")
        return

    matches_info = []
    venue_coords: dict[str, tuple] = {}   # korrigierter Venue-String → (lat,lon)
    venues_needed = set()

    # Gruppenspiele + KO-Spiele (30.06.2026, Lucas: „Wetter fehlt"): in der KO-Phase liegen die Spiele
    # in koFixtures, nicht groups → der Fetcher holte NIE Wetter für R32+ (Datei enthielt nur die längst
    # gespielten Gruppenspiele → forecastAvailable überall False). KO-Venue ist nur die Stadt
    # („Monterrey", „Los Angeles (Inglewood)") → _resolve_coords' City-Fallback löst alle 15 auf.
    _fixtures = list(_group_fixtures(wm)) + list(_ko_fixtures(wm))
    for fx in _fixtures:
        h, a = fx.get("home"), fx.get("away")
        venue = (fx.get("venue") or "").strip()
        mdate = (fx.get("date") or "")[:10]
        if not (h and a and venue and mdate):
            continue
        slug = f"wm-{h.lower()}-vs-{a.lower()}-{mdate}"
        matches_info.append({"slug": slug, "venue": venue, "date": mdate,
                             "kickoff": fx.get("kickoff")})
        coords = _resolve_coords(venue)
        if coords:
            venue_coords[venue] = coords
            venues_needed.add(venue)
        else:
            print(f"  ⚠️  Keine Coords für Venue: {venue!r}")

    print(f"  📋 {len(matches_info)} Fixtures (Gruppen + KO) | 🏟️  {len(venues_needed)} Venues mit Coords")

    # 2. Wetter pro Venue fetchen
    venue_weather: dict[str, dict] = {}
    for i, venue in enumerate(sorted(venues_needed)):
        lat, lon = venue_coords[venue]
        print(f"  🌡️  {venue} ({lat:.2f}°N)…", end=" ", flush=True)
        weather = fetch_venue_weather(lat, lon)
        if weather:
            venue_weather[venue] = weather
            avail = sum(1 for d in weather if date.fromisoformat(d) <= max_date)
            print(f"✅ {len(weather)} Tage")
        else:
            print("❌ fehlgeschlagen")
        # Rate-Limit: WeatherAPI free ist 1M/Monat aber pro Sekunde nicht limitiert.
        # Trotzdem 0.2s zwischen Calls für Anstand.
        if i < len(venues_needed) - 1:
            time.sleep(0.2)

    # 3. Wetter pro Match zuordnen
    results = {}
    no_forecast = 0
    for m in matches_info:
        slug, venue, mdate = m["slug"], m["venue"], m["date"]
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
            # Echte Temperatur zur Anpfiff-Stunde (FIX 13.06.2026): nächste Stunde
            # zum Kickoff per UTC-Epoch. Tagesmax überschätzt Mittags-/Nacht-Spiele
            # massiv (z.B. QAT-SUI Mittag-Anpfiff: tempMax 33° vs real ~25-27° um 12h;
            # Nachtspiele: tempMax 33° vs real ~15°). Fallback tempMax wenn kein Match.
            # MAX über das Spiel-Fenster (Anpfiff −0.5h … +2.5h), nicht nur die
            # Anpfiff-Stunde: ein Mittags-Anpfiff heizt während des Spiels auf
            # (12:00 ~28° → 13:30 ~30°). Das Fenster-Max trifft die reale Hitze, die
            # die Spieler abbekommen. Matching per UTC-Epoch → findet die echte
            # LOKALE Stadion-Stunde (unabhängig von der Anzeige-Zeitzone). Fallback
            # nächste Stunde, sonst tempMax.
            temp_kick = None
            ko = m.get("kickoff")
            if ko and w.get("hours"):
                try:
                    ko_epoch = datetime.fromisoformat(str(ko).replace("Z", "+00:00")).timestamp()
                    window = [t for (ep, t) in w["hours"]
                              if ko_epoch - 1800 <= ep <= ko_epoch + 9000]   # −0.5h … +2.5h
                    if window:
                        temp_kick = max(window)
                    else:
                        best = min(w["hours"], key=lambda hp: abs(hp[0] - ko_epoch))
                        if abs(best[0] - ko_epoch) <= 5400:
                            temp_kick = best[1]
                except Exception:
                    temp_kick = None
            results[slug] = {
                "venue":             venue,
                "date":              mdate,
                "tempMax":           w["tempMax"],
                "tempMin":           w["tempMin"],
                "tempAtKickoff":     temp_kick,
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
        "generatedAt":    now_ts,
        "forecastWindow": f"bis {max_date.isoformat()}",
        "source":         "weatherapi.com",
        "matches":        results,
    }
    with open(WEATHER_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with_forecast = len(results) - no_forecast
    print(f"\n✅ wm_weather.json gespeichert (Quelle: WeatherAPI)")
    print(f"   Mit Vorhersage: {with_forecast}  |  Zu weit in Zukunft: {no_forecast}")


if __name__ == "__main__":
    main()
