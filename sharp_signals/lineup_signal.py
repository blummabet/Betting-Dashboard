"""
sharp_signals/lineup_signal.py — Aufstellungs-Signal (T-1h Killer)

Konzept:
  ~1h vor Anpfiff veröffentlichen die Verbände die Startaufstellungen.
  Das ist der späteste informationsreiche Datenpunkt vor dem Spiel.

  Zwei harte Signale:
    1) Top-Scorer fehlt komplett (nicht im Starting-11 UND nicht auf Bench)
       → starker negativer Score für Goals-Märkte (Über)
       → moderater positiver Score für defensive Markets (Unter, Heim/Auswärts-Underdog)
    2) Top-Scorer auf der Bank statt Starting-11
       → moderater negativer Score für Goals (Rotation/Schonung)
       → kann auch bedeuten: Trainer plant 60-min einsatz, weniger Wirkung

  Soft-Signal (Rotation-Detection):
    - Wenn formationen-shift (z.B. 4-3-3 → 5-4-1) → defensiv geplant
    - Wenn Backup-Keeper startet → defensives Risiko hoch

  Datenanbindung:
    context["lineups"][match_key] = {home: {starting, subs}, away: {starting, subs}, ...}
    context["squads"][team_id]    = {name, goals, assists, minutes}  # Top-Scorer

  Score-Direction:
    Pick auf "Über"  → top-scorer-fehlt = negativ (weniger goals erwartet)
    Pick auf "Unter" → top-scorer-fehlt = positiv
    Pick auf Heim-Win wenn Auswärts-Top-Scorer fehlt = positiv
    Pick auf Auswärts-Win wenn Heim-Top-Scorer fehlt = positiv
"""
from __future__ import annotations
from typing import Optional
from sharp_signals.base import Signal, SignalResult


DEFAULT_THRESHOLDS = {
    "missing_score":        2.5,    # Top-Scorer fehlt komplett (volle Wucht)
    "benched_score":        1.5,    # Top-Scorer auf Bank
    "missing_min_goals":      2,    # erst ab N Saison-Toren zählt der Spieler als Schlüsselspieler
    "confidence_full":     0.80,
    "confidence_partial":  0.60,
}


def _load_thresholds() -> dict:
    try:
        import json, os
        from pathlib import Path
        raw = json.loads((Path(__file__).parent.parent / "cocobet_config.json")
                         .read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("lineup_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _normalize_name(s: str) -> str:
    """Normalisiert Namen für Vergleich: lowercase, kein Diakritischer Zeichen."""
    if not s:
        return ""
    s = s.lower().strip()
    repl = {
        # Vowels mit Akzenten
        "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a", "ā": "a", "å": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e", "ē": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i", "ī": "i", "ı": "i",
        "ó": "o", "ò": "o", "ô": "o", "ö": "o", "õ": "o", "ō": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u", "ū": "u",
        # Konsonanten
        "ñ": "n", "ç": "c", "ß": "ss",
        # Türkisch / slawische
        "ğ": "g", "ş": "s", "ž": "z", "š": "s", "č": "c", "ć": "c",
        "đ": "d", "ł": "l", "ń": "n", "ý": "y",
        # Apostrophe / Bindestriche raus
        "'": "", "'": "", "-": " ",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def _player_in_list(name: str, players: list) -> bool:
    """
    Prüft ob Spieler in der Liste ist — fuzzy match auf Last-Name.
    Last-Name ≥ 3 chars (z.B. "Tau", "Vaz") reicht, da Diakritika weggenommen.
    Bei Last-Name ≤ 2 chars: Vollname-Substring-Vergleich.
    """
    target = _normalize_name(name)
    if not target:
        return False
    target_last = target.split()[-1] if " " in target else target
    for p in players or []:
        pname = _normalize_name(p.get("name", ""))
        if not pname:
            continue
        # Substring-Match: target in pname (oder umgekehrt) bei langen Namen
        if len(target) >= 5 and (target in pname or pname in target):
            return True
        # Last-Name exakt-match (≥ 3 chars um falsche Treffer wie "de" zu vermeiden)
        pname_last = pname.split()[-1] if " " in pname else pname
        if target_last == pname_last and len(target_last) >= 3:
            return True
    return False


def _outcome_side_from_market(market: str) -> str:
    """
    Map Market → 'over' (Goals erwartet) | 'under' (no goals) | 'home' | 'away' | 'unknown'.

    WICHTIG: Über/Unter nur für TOR-Märkte triggern. "Über 9.5 Ecken" oder
    "Über 4.5 Karten" sind nicht goals-bezogen → unknown.
    """
    m = (market or "").lower()

    # Goals-Markets — Über/Unter nur wenn auf Tore bezogen
    is_goals = "tore" in m or "goals" in m
    if is_goals:
        if "über" in m or "over" in m:   return "over"
        if "unter" in m or "under" in m: return "under"

    # Outright
    if "heimsieg" in m or "doppelte chance — 1x" in m: return "home"
    if "auswärtssieg" in m or "auswartssieg" in m or "doppelte chance — x2" in m: return "away"
    if "dnb" in m and ("heim" in m or "home" in m):    return "home"
    if "dnb" in m and ("ausw" in m or "away" in m):    return "away"
    return "unknown"


class LineupSignal(Signal):
    """
    Aufstellungs-Signal — feuert nur wenn `lineups`-Daten im Context vorhanden.

    Context erwartet:
      lineups[match_key] = {
        "home": {"starting": [...], "subs": [...]},
        "away": {"starting": [...], "subs": [...]},
        "fetchedAt": iso8601,
      }
      squads[team_id] = {"name": ..., "goals": int, ...}  # Top-Scorer pro Team
    """

    def __init__(self):
        self._t = _load_thresholds()

    def name(self) -> str:
        return "lineup_signal"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        # Match-Key aus Context
        mk = context.get("matchKey")
        if not mk:
            return None
        lineups = context.get("lineups") or {}
        entry = lineups.get(mk)
        if not entry:
            return None

        squads = context.get("squads") or {}
        home_id = context.get("home_id")
        away_id = context.get("away_id")
        if not home_id or not away_id:
            return None

        side = _outcome_side_from_market(pick.get("market", ""))
        if side == "unknown":
            return None

        # Top-Scorer checken pro Team
        home_scorer = squads.get(home_id) or {}
        away_scorer = squads.get(away_id) or {}

        def _status(scorer: dict, team_lineup: dict) -> str:
            """missing | benched | starting | unknown"""
            if not scorer or not scorer.get("name"):
                return "unknown"
            if (scorer.get("goals") or 0) < self._t["missing_min_goals"]:
                return "unknown"   # nicht wichtig genug
            name = scorer["name"]
            if _player_in_list(name, team_lineup.get("starting") or []):
                return "starting"
            if _player_in_list(name, team_lineup.get("subs") or []):
                return "benched"
            return "missing"

        home_status = _status(home_scorer, entry.get("home", {}))
        away_status = _status(away_scorer, entry.get("away", {}))

        # Score-Logik (siehe Modul-Header)
        score = 0.0
        evidence_parts = []
        affected_teams = []

        for team_label, team_id, status, scorer in [
            ("Heim", home_id, home_status, home_scorer),
            ("Auswärts", away_id, away_status, away_scorer),
        ]:
            if status == "starting" or status == "unknown":
                continue
            magnitude = self._t["missing_score"] if status == "missing" else self._t["benched_score"]
            # Direction abhängig von Markt + welcher Team's Stürmer fehlt
            if side == "over":
                # weniger Stürmer-Power → over WENIGER wahrscheinlich → score negativ
                score -= magnitude
            elif side == "under":
                # weniger Stürmer-Power → under MEHR wahrscheinlich → score positiv
                score += magnitude
            elif side == "home" and team_label == "Auswärts":
                # Auswärts-Top-Scorer fehlt → Heim-Sieg wahrscheinlicher
                score += magnitude
            elif side == "away" and team_label == "Heim":
                # Heim-Top-Scorer fehlt → Auswärts-Sieg wahrscheinlicher
                score += magnitude
            elif side == "home" and team_label == "Heim":
                # Heim-Top-Scorer fehlt UND wir picken Heim → negativ
                score -= magnitude
            elif side == "away" and team_label == "Auswärts":
                # Auswärts-Top-Scorer fehlt UND wir picken Auswärts → negativ
                score -= magnitude
            else:
                continue
            status_label = "fehlt" if status == "missing" else "Bank"
            evidence_parts.append(f"{team_label} {scorer['name']} {status_label}")
            affected_teams.append({
                "team": team_label, "team_id": team_id,
                "scorer": scorer.get("name"), "goals": scorer.get("goals"),
                "status": status,
            })

        if not affected_teams:
            return None

        # Confidence: voll bei missing, partial bei nur bench
        any_missing = any(t["status"] == "missing" for t in affected_teams)
        confidence = self._t["confidence_full"] if any_missing else self._t["confidence_partial"]

        evidence = "🚨 " + " · ".join(evidence_parts)

        return SignalResult(
            score=round(score, 2),
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "side":      side,
                "affected":  affected_teams,
                "fetchedAt": entry.get("fetchedAt"),
            },
        )
