"""
sharp_signals/injury_signal.py — Verletzungen / Sperren als Pick-Adjustment

Konzept (Lucas 08.06.2026):
  Nicht nur Top-Stürmer sondern auch wichtige Mittelfeldspieler, Verteidiger und
  TORWART berücksichtigen. Jede Position hat einen anderen Impact:

  · GK (Torwart):        kein gleichwertiger Backup → höchster Impact bei Top-GK
  · CB (Innenverteidiger): defensive Stabilität, Set-Pieces
  · CM/DM (Mittelfeld):   Spielaufbau + Ballgewinne
  · ST/FW (Stürmer):      Tore (asymmetrisch)
  · AM/LW/RW:             Kreativität + Geschwindigkeit
  · Backup:               geringer Impact

  Mehrere Ausfälle akkumulieren bis Cap. Wenn Heim verletzt → negativer Score
  für Heim-Picks, positiver für Auswärts-Picks (und umgekehrt).
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    # Position-Impact in pp pro starter-Ausfall
    "impact_GK":     2.0,
    "impact_DEF":    1.5,
    "impact_MID":    1.5,
    "impact_FWD":    2.5,
    "impact_BACKUP": 0.4,
    # Cap pro Team — keine 8pp Penalty selbst bei massiven Ausfällen
    "max_per_team_pp":   6.0,
    # Mindest-Netto-Impact damit das Signal feuert
    "min_signal_pp":     1.0,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("injury") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


# Position-Klassifikation — robust gegen verschiedene Notationen
POS_GK  = {"GK", "TW", "GOALKEEPER"}
POS_DEF = {"CB", "LB", "RB", "LWB", "RWB", "DEF", "DEFENDER",
           "IV", "AV", "LV", "RV"}
POS_MID = {"DM", "CM", "ZM", "DMF", "CDM", "CMF", "MID", "MIDFIELDER",
           "ZDM", "ZOM"}
POS_FWD = {"ST", "CF", "FW", "FORWARD", "STRIKER"}
POS_WIDE = {"LW", "RW", "AM", "CAM", "OM", "AMF", "WG"}   # AM zählen wir als FWD-Impact


def _classify_position(pos: str) -> str:
    """Returns 'GK', 'DEF', 'MID', 'FWD' oder 'UNKNOWN'."""
    if not pos:
        return "UNKNOWN"
    p = pos.upper().strip().replace(".", "").replace("-", "")
    if p in POS_GK:
        return "GK"
    if p in POS_DEF:
        return "DEF"
    if p in POS_MID:
        return "MID"
    if p in POS_FWD or p in POS_WIDE:
        return "FWD"
    return "UNKNOWN"


def _is_starter(player: dict) -> bool:
    """Ist der Spieler ein Starter? Defaults zu True wenn nicht angegeben."""
    importance = (player.get("importance") or player.get("role") or "").lower()
    if importance in ("backup", "reserve", "bench", "rotation"):
        return False
    return True


def _team_injury_impact_pp(team_injuries: dict, thr: dict) -> tuple[float, list[str]]:
    """
    Gesamt-Penalty in pp für ein Team + Liste der Ausgefallenen für Evidence.
    """
    if not team_injuries or not team_injuries.get("players"):
        return 0.0, []
    impact = 0.0
    notes  = []
    for p in team_injuries["players"]:
        if not isinstance(p, dict):
            continue
        pos_class = _classify_position(p.get("position") or "")
        is_starter = _is_starter(p)
        if not is_starter:
            penalty = thr["impact_BACKUP"]
        elif pos_class == "GK":
            penalty = thr["impact_GK"]
        elif pos_class == "DEF":
            penalty = thr["impact_DEF"]
        elif pos_class == "MID":
            penalty = thr["impact_MID"]
        elif pos_class == "FWD":
            penalty = thr["impact_FWD"]
        else:
            penalty = thr["impact_BACKUP"]   # Unknown → behandeln wie Backup
        impact += penalty
        name = p.get("name") or "Unbekannt"
        role_tag = f"{pos_class}" if pos_class != "UNKNOWN" else "?"
        notes.append(f"{name} ({role_tag})")
    # Cap
    impact = min(thr["max_per_team_pp"], impact)
    return impact, notes


def _pick_side(market: str) -> int:
    """+1 = Heim-Seite, -1 = Auswärts-Seite, 0 = nicht direkt."""
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


class InjurySignal(Signal):
    """
    Verletzungen + Sperren positionsbewusst aggregiert.

    Context erwartet:
      home_id, away_id
      injuries: { teamId: { players: [{name, position, importance, type}, ...] } }
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "injury"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return None  # O/U-Märkte: Effekt ambivalent — separates Signal später

        injuries = context.get("injuries") or {}
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None

        home_impact, home_notes = _team_injury_impact_pp(injuries.get(home_id), self._t)
        away_impact, away_notes = _team_injury_impact_pp(injuries.get(away_id), self._t)

        net = (away_impact - home_impact) if side == +1 else (home_impact - away_impact)
        if abs(net) < self._t["min_signal_pp"]:
            return None

        # Confidence — höher wenn klare Asymmetrie
        diff = abs(home_impact - away_impact)
        confidence = min(0.85, 0.50 + diff * 0.06)

        ev_parts = []
        if home_impact > 0:
            ev_parts.append(f"Heim {home_impact:.1f}pp ({', '.join(home_notes[:2])})")
        if away_impact > 0:
            ev_parts.append(f"Auswärts {away_impact:.1f}pp ({', '.join(away_notes[:2])})")
        evidence = "🩹 " + " · ".join(ev_parts) if ev_parts else f"Injury-Effekt {net:+.1f}pp"

        return SignalResult(
            score=round(net, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "home_impact_pp": round(home_impact, 2),
                "away_impact_pp": round(away_impact, 2),
                "pick_side":      "home" if side == 1 else "away",
                "home_players":   home_notes,
                "away_players":   away_notes,
            },
        )
