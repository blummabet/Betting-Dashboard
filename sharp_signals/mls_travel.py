"""
sharp_signals/mls_travel.py — MLS Reise/Höhe/Rasen-Composite

In den kompakten europäischen Ligen ist Reise ~Rauschen — in der MLS ist sie ein ECHTER Edge:
Küste-zu-Küste-Red-Eyes (bis ~4000 km), 3 Zeitzonen, Höhe (Denver/Colorado ~1580 m, Real Salt
Lake ~1330 m) und Kunstrasen-Venues (Vancouver/Seattle/Portland/New England/Atlanta). Softbooks
bepreisen MLS-Reise faul → früh auf einem reise-getriebenen Pinnacle-Move zu sein ist echtes CLV.

Rechnet die BÜRDE des Auswärtsteams (Reise vom eigenen Stadion zum Spielort):
  · Distanz (Haversine)  · Zeitzonen-Sprung (aus Längengrad)  · Höhen-Gewinn (Spielort − Heimat;
    positiv = Auswärts spielt höher als gewohnt)  · Rasen-Mismatch (Auswärts-Heimrasen ≠ Spielort).
Bürde → Heim-Vorteil (Heim +, Auswärts −, Unter + weil müdes Auswärtsteam weniger Tempo).
Nur MLS (Venue-Tabelle nur MLS-Teams → für WM/Liga None). context-Familie (Anti-Korr mit
fixture_congestion/injury). Portiert die WM-travel/altitude-Idee data-aware.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Optional
from sharp_signals.base import Signal, SignalResult, market_side

_VENUES: Optional[dict] = None
MAX_PP = 1.8


def _load_venues() -> dict:
    global _VENUES
    if _VENUES is None:
        try:
            raw = json.loads((Path(__file__).parent.parent / "mls_venues.json").read_text(encoding="utf-8"))
            _VENUES = {k: v for k, v in raw.items() if k != "_meta"}
        except Exception:
            _VENUES = {}
    return _VENUES


def _haversine_km(a: dict, b: dict) -> float:
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class MLSTravelSignal(Signal):
    def name(self) -> str:
        return "mls_travel"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = market_side(pick.get("market", ""))
        if side not in ("home", "away", "over", "under"):
            return None
        venues = _load_venues()
        home_id, away_id = context.get("home_id"), context.get("away_id")
        hv, av = venues.get(str(home_id)), venues.get(str(away_id))
        if not hv or not av:
            return None   # keine MLS-Venue-Daten → Signal n/a (WM/Liga)

        dist = _haversine_km(av, hv)
        tz_delta = abs(round((hv["lon"] - av["lon"]) / 15.0))
        alt_gain = hv["alt_m"] - av["alt_m"]           # >0 = Auswärts spielt höher als gewohnt
        turf_mismatch = 1 if bool(hv["turf"]) != bool(av["turf"]) else 0

        # Bürde-Komponenten (0..~1)
        b_dist = min(1.0, max(0.0, (dist - 1200) / 2800))      # ab ~1200 km spürbar, voll bei ~4000
        b_tz = min(1.0, tz_delta / 3.0)                         # 3 Zeitzonen = voll
        b_alt = min(1.0, max(0.0, alt_gain - 700) / 900) if alt_gain > 700 else 0.0  # ab 700 m Gewinn
        b_turf = 0.35 * turf_mismatch
        burden = min(1.0, 0.45 * b_dist + 0.25 * b_tz + 0.4 * b_alt + b_turf)
        if burden < 0.2:
            return None   # Kurztrip, keine Zeitzone, kein Höhen/Rasen-Faktor → kein Edge

        reasons = []
        if b_dist > 0.25:
            reasons.append(f"{int(dist)} km Anreise")
        if tz_delta >= 1:
            reasons.append(f"{tz_delta} Zeitzone(n)")
        if b_alt > 0:
            reasons.append(f"+{int(alt_gain)} m Höhe")
        if turf_mismatch:
            reasons.append("Kunstrasen ungewohnt")
        why = ", ".join(reasons) or "Reisebelastung"

        if side == "home":
            score = burden * MAX_PP
            ev = f"Auswärts-Reisebürde ({why}) → Heim-Vorteil."
        elif side == "away":
            score = -burden * MAX_PP * 0.8
            ev = f"Auswärts belastet ({why}) → gegen den Auswärtssieg."
        elif side == "under":
            score = burden * MAX_PP * 0.4
            ev = f"Müdes Auswärtsteam ({why}) → weniger Tempo, eher Unter."
        else:  # over
            return None

        conf = min(0.65, 0.35 + burden * 0.4)
        return SignalResult(score=round(score, 2), confidence=round(conf, 2), evidence=ev,
                            metadata={"dist_km": round(dist), "tz_delta": tz_delta,
                                      "alt_gain_m": alt_gain, "turf_mismatch": turf_mismatch,
                                      "burden": round(burden, 2)})
