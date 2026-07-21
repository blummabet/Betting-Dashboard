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
POS_FWD = {"ST", "CF", "FW", "FORWARD", "STRIKER", "ATTACKER"}   # ATTACKER = API-Football-Term (MLS/Liga)
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


def _unique_players(players: list) -> list:
    """21.07.2026 (Lucas, MLS Inter Miami: „S. Reguilon (?), S. Reguilon (?)"): derselbe Spieler
    stand doppelt in den Injury-Daten → doppelt gezählt (Impact aufgebläht) UND doppelt gelistet.
    Dedupe nach Spieler-Identität (id, sonst normalisierter Name). Robust, egal woher das Duplikat
    kommt — der Fetcher kann denselben Spieler unter zwei Verletzungs-Einträgen liefern."""
    seen, out = set(), []
    for p in (players or []):
        if not isinstance(p, dict):
            continue
        key = p.get("id") or p.get("player_id") or (p.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _team_injury_impact_pp(team_injuries: dict, thr: dict) -> tuple[float, list[str]]:
    """
    Gesamt-Penalty in pp für ein Team + Liste der Ausgefallenen für Evidence.
    """
    if not team_injuries or not team_injuries.get("players"):
        return 0.0, []
    impact = 0.0
    notes  = []
    for p in _unique_players(team_injuries["players"]):
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


def _team_injury_offense_defense(team_injuries: dict, thr: dict) -> tuple[float, float, list[str]]:
    """
    Splittet Injury-Impact in Offense-Impact (FWD/MID) vs Defense-Impact (GK/DEF).
    Wird für den O/U-Branch genutzt: FWD-Ausfall → weniger Tore, GK/DEF-Ausfall → mehr Gegentore.
    Returns (offense_pp, defense_pp, notes).
    """
    if not team_injuries or not team_injuries.get("players"):
        return 0.0, 0.0, []
    off_impact = 0.0
    def_impact = 0.0
    notes = []
    for p in _unique_players(team_injuries["players"]):
        if not isinstance(p, dict):
            continue
        pos_class = _classify_position(p.get("position") or "")
        is_starter = _is_starter(p)
        if not is_starter:
            continue   # Backups beeinflussen O/U-Tor-Erwartung kaum
        if pos_class == "FWD":
            off_impact += thr["impact_FWD"]
            notes.append(f"{p.get('name', '?')} (FWD)")
        elif pos_class == "MID":
            off_impact += thr["impact_MID"] * 0.5  # MF wirkt halb auf Offense
            notes.append(f"{p.get('name', '?')} (MID)")
        elif pos_class == "GK":
            def_impact += thr["impact_GK"]
            notes.append(f"{p.get('name', '?')} (GK)")
        elif pos_class == "DEF":
            def_impact += thr["impact_DEF"]
            notes.append(f"{p.get('name', '?')} (DEF)")
    cap = thr["max_per_team_pp"]
    return min(cap, off_impact), min(cap, def_impact), notes


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
        market = pick.get("market", "")
        side = _pick_side(market)
        injuries = context.get("injuries") or {}
        home_id, away_id = context.get("home_id"), context.get("away_id")
        if not (home_id and away_id):
            return None

        # ── O/U-Branch (NEU 09.06.2026): Offense-/Defense-Split ──────────────
        ml = market.lower()
        is_over  = "über" in ml or "uber" in ml or "over" in ml
        is_under = "unter" in ml or "under" in ml
        is_ou_total = ("tore" in ml or "goals" in ml) and (is_over or is_under)

        if is_ou_total:
            h_off, h_def, h_notes = _team_injury_offense_defense(injuries.get(home_id), self._t)
            a_off, a_def, a_notes = _team_injury_offense_defense(injuries.get(away_id), self._t)
            # Tor-Impact pro Team: Stürmer-Ausfall reduziert eigene Tore,
            # Defense-Ausfall erhöht Gegentore (= mehr Tore für anderes Team).
            # Netto-Tor-Effekt: -h_off (eigene Tore weg) +a_def (mehr Tore gegen Auswärts)
            # → analog für Auswärts. Gesamteffekt auf Tore in Spiel:
            goals_delta = (-h_off + a_def) + (-a_off + h_def)
            # NEGATIV = weniger Tore erwartet → Unter-Bias
            # POSITIV = mehr Tore erwartet → Über-Bias
            score = goals_delta if is_over else -goals_delta
            if abs(score) < self._t["min_signal_pp"]:
                return None
            confidence = min(0.75, 0.45 + (abs(score) * 0.05))
            ev_parts = []
            if h_off > 0 or a_off > 0:
                ev_parts.append(f"Offense-Ausfälle: Heim {h_off:.1f}pp · Auswärts {a_off:.1f}pp")
            if h_def > 0 or a_def > 0:
                ev_parts.append(f"Defense-Ausfälle: Heim {h_def:.1f}pp · Auswärts {a_def:.1f}pp")
            evidence = "🩹 " + " · ".join(ev_parts) if ev_parts else f"Injury O/U-Effekt {score:+.1f}pp"
            return SignalResult(
                score=round(score, 2),
                confidence=round(confidence, 2),
                evidence=evidence,
                metadata={
                    "home_off_pp": round(h_off, 2),
                    "home_def_pp": round(h_def, 2),
                    "away_off_pp": round(a_off, 2),
                    "away_def_pp": round(a_def, 2),
                    "goals_delta": round(goals_delta, 2),
                    "pick_side": "over" if is_over else "under",
                },
            )

        # ── 1X2-Branch (alte Logik) ──────────────────────────────────────────
        if side == 0:
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
