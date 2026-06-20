"""
sharp_signals/pressure_index.py — Tournament Pressure & Motivation Signal

Tier-4 — Lucas's Killer-Differenzierung: kaum ein Bookie modelliert
psychologischen Druck systematisch.

Komponenten (alle aktivieren sich automatisch sobald Daten reichen):

  1. Tournament-Stage (sofort verfügbar)
     - Spieltag 1: Vorsicht, kein Team will Auftakt verlieren
     - Spieltag 2: Match-finder, Druck auf 0-Punkt-Teams
     - Spieltag 3: gemischt — qualifizierte Teams rotieren, bedrohte kämpfen
     - KO-Phase (ab 28.06.): erhöhter Vorsicht-Bias, niedrigere Tore-Erwartung

  2. Group-Standing-Tension (ab Matchday 2 resolved)
     - Team auf 0 Punkten nach 2 Spielen + 3. Gruppenspiel → Existenz-Druck
     - Team bereits qualifiziert + 3. Gruppenspiel → Rotation, Druck weg
     - Tie-breaker-Konstellationen: spezifische Tor-Differenz-Math

  3. KO-Phase-Spezifika (ab 28.06.)
     - Achtel: 90 Minuten → Verlängerung → Elfmeter — Risiko-Aversion erhöht
     - Halbfinale/Finale: maximaler Vorsicht-Bias

Pre-Tournament gibt das Signal nur Tournament-Stage zurück. Die spannenden
Komponenten (2, 3) kommen mit den Daten.
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    # Tournament-Stage-Modifikatoren (in pp)
    "md1_caution_pp":         0.6,   # leicht risikoavers
    "md3_qualified_rotation_pp": -1.2,  # qualifiziertes Team rotiert → schwächer (eigene Seite)
    "md3_coast_opponent_pp":   1.2,   # qualifiziert+gesichert → Gegenseite boosten (Schon-Risiko)
    "md3_must_win_pp":         1.5,   # Must-Win-Team (aus Quali-Mathe, nicht nur 0 Pkt)
    "home_wc_coast_damp":      0.5,   # Heim-WM-Host gibt sich vor eigenem Publikum nicht auf → Schon-Risiko gedämpft
    "host_teams":              ["MEX", "USA", "CAN"],   # WM-2026-Gastgeber (liga: leer)
    "ko_phase_caution_pp":     1.0,   # KO erhöht Vorsicht
    "ko_final_pp":             1.5,   # Halbfinale/Finale spezial
    # Threshold
    "min_signal_pp":           0.5,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("pressure_index") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _pick_side(market: str) -> int:
    m = (market or "").lower()
    if "heimsieg" in m: return +1
    if "dnb" in m and ("heim" in m or "home" in m): return +1
    if "ah heim" in m: return +1
    if "doppelte chance" in m and "— 1x" in m: return +1
    if "auswärtssieg" in m or "auswartssieg" in m: return -1
    if "dnb" in m and ("ausw" in m or "away" in m): return -1
    if "ah auswärts" in m or "ah auswarts" in m: return -1
    if "doppelte chance" in m and "— x2" in m: return -1
    return 0


def _is_ou_market(market: str) -> bool:
    m = (market or "").lower()
    return "über" in m or "unter" in m or "tore" in m


def _team_points_from_standings(team_id: str, standings: dict) -> Optional[int]:
    """
    Sucht das Team in standings und gibt Punkte zurück (None wenn unbekannt).
    standings-Format: { "A": [{ "team": "MEX", "points": 4, ...}, ...], ... }
    """
    if not isinstance(standings, dict):
        return None
    for group, rows in standings.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("team") == team_id or row.get("teamId") == team_id:
                p = row.get("points")
                if isinstance(p, (int, float)):
                    return int(p)
    return None


def _ko_phase_stage(matchday) -> Optional[str]:
    """Spielklasse in der KO-Phase — Strings damit später erweiterbar."""
    if isinstance(matchday, str):
        m = matchday.upper()
        if m in ("RO16", "R16"):      return "round_of_16"
        if m in ("QF", "QUARTER"):    return "quarter"
        if m in ("SF", "SEMI"):       return "semi"
        if m in ("FINAL", "F"):       return "final"
    return None


class PressureIndexSignal(Signal):
    """
    Tournament-Stage + Group-Standing-Tension + KO-Phase-Spezifika.

    Context erwartet:
      home_id, away_id
      matchday:     1/2/3 (Gruppe) oder "RO16"/"QF"/"SF"/"FINAL"
      standings:    optional aus wm2026-data.json (ab Matchday 2 sinnvoll)
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "pressure_index"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        matchday = context.get("matchday")
        home_id  = context.get("home_id")
        away_id  = context.get("away_id")
        if matchday is None or not (home_id and away_id):
            return None

        side = _pick_side(pick.get("market", ""))
        is_ou = _is_ou_market(pick.get("market", ""))
        # Beides — 1X2-Picks und O/U-Picks — können von Druck profitieren
        # (1X2: must-win-Team gewinnt eher; O/U: KO-Phase = weniger Tore)

        score   = 0.0
        notes   = []
        confidence = 0.55

        # ── KO-Phase ─────────────────────────────────────────────────────
        ko_stage = _ko_phase_stage(matchday)
        if ko_stage:
            if is_ou and ("über" in (pick.get("market") or "").lower()):
                # KO-Phase = risikoavers → eher unter, also gegen "Über"-Pick
                score -= self._t["ko_phase_caution_pp"]
                notes.append(f"KO-Vorsicht (gegen Über)")
            elif is_ou and ("unter" in (pick.get("market") or "").lower()):
                score += self._t["ko_phase_caution_pp"]
                notes.append(f"KO-Vorsicht (Unter wahrscheinlicher)")
            if ko_stage in ("semi", "final"):
                extra = self._t["ko_final_pp"]
                if is_ou and "unter" in (pick.get("market") or "").lower():
                    score += extra
                    notes.append(f"{ko_stage}-Stage extra-vorsichtig")
            confidence = 0.7

        # ── Group-Stage Modifikatoren ───────────────────────────────────
        elif isinstance(matchday, int) and matchday in (1, 2, 3):
            if matchday == 1:
                # Auftaktspiel: leicht risikoavers — Teams wollen nicht verlieren
                if is_ou and "über" in (pick.get("market") or "").lower():
                    score -= self._t["md1_caution_pp"]
                    notes.append("MD1-Auftakts-Vorsicht (gegen Über)")
                elif is_ou and "unter" in (pick.get("market") or "").lower():
                    score += self._t["md1_caution_pp"]
                    notes.append("MD1-Auftakts-Vorsicht (Unter)")
                confidence = 0.55

            elif matchday == 3:
                # Standings + Gruppe für die Qualifikations-Mathe (19.06.2026, Lucas):
                # Must-Win aus dem must_win-Flag (nicht nur points==0 → fängt z.B. CZE @1Pkt),
                # und ein qualifiziert+gesichertes Team ist Schon-Risiko → die GEGENSEITE wird
                # geboostet (nicht nur die eigene Seite gestraft). Heim-WM-Host gedämpft.
                standings = context.get("standings") or {}
                group_id  = context.get("group_id")
                try:
                    from sharp_signals.incentive_signal import _compute_qualification_state as _qs
                    hs = _qs(home_id, group_id, 3, standings) if group_id else {}
                    aw = _qs(away_id, group_id, 3, standings) if group_id else {}
                except Exception:
                    hs, aw = {}, {}

                # Must-Win → Sieg-Seite des verzweifelten Teams boosten
                if hs.get("must_win") and side == +1:
                    score += self._t["md3_must_win_pp"]
                    notes.append("Heim muss hier gewinnen, um weiterzukommen"); confidence = 0.75
                elif aw.get("must_win") and side == -1:
                    score += self._t["md3_must_win_pp"]
                    notes.append("Auswärts muss hier gewinnen, um weiterzukommen"); confidence = 0.75

                # Qualifiziert+gesichert = Schon-Risiko → schwächeres Team → Gegenseite boosten,
                # eigene Sieg-Seite dämpfen. Heim-Gastgeber: gedämpft (gibt sich daheim nicht auf).
                hosts = set(self._t.get("host_teams") or [])
                boost = self._t["md3_coast_opponent_pp"]
                rot   = self._t["md3_qualified_rotation_pp"]
                if hs.get("qualified"):
                    damp = self._t["home_wc_coast_damp"] if home_id in hosts else 1.0
                    if side == -1:
                        score += boost * damp
                        notes.append("Heim ist schon durch und könnte Kräfte sparen — spricht für Auswärts" + (" (als Gastgeber aber gedämpft)" if damp < 1 else ""))
                        confidence = max(confidence, 0.7)
                    elif side == +1:
                        score += rot * damp
                        notes.append("Heim ist schon durch — Rotation möglich")
                if aw.get("qualified"):
                    if side == +1:
                        score += boost
                        notes.append("Auswärts ist schon durch und könnte Kräfte sparen — spricht für Heim")
                        confidence = max(confidence, 0.7)
                    elif side == -1:
                        score += rot
                        notes.append("Auswärts ist schon durch — Rotation möglich")

        if abs(score) < self._t["min_signal_pp"]:
            return None

        ev = "🎯 " + " · ".join(notes) if notes else f"Pressure {score:+.1f}pp"

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=ev,
            metadata={
                "matchday":  matchday,
                "ko_stage":  ko_stage,
                "components": notes,
                "pick_side": "home" if side == +1 else ("away" if side == -1 else "neutral"),
            },
        )
