"""
sharp_signals/league_pressure.py — Liga-Druck-Signal (25.06.2026, Lucas).

Das Liga-Pendant zum WM-incentive_signal: modelliert, wie viel für ein Team in DIESEM Spiel auf dem
Spiel steht — Titelrennen, Europa-Plätze (CL/EL/ECL), Abstiegskampf, Dead-Rubber. Rein rechnerisch
auf der Tabelle (kein API-Call).

SELBST-SKALIEREND (Lucas' Punkt „früh 0, steigt zum Endspurt"): der Zeit-Faktor ist in der ersten
Saisonhälfte ~0 und rampt in den letzten Runden auf 1 — früh liefert das Signal also nichts (None),
spät den vollen Hebel. Ein Team „muss gewinnen", wenn es einen erreichbaren Grenzplatz noch braucht;
„dead rubber" = nichts mehr zu spielen (gesichert ODER raus). Bei BEIDEN-müssen NICHT automatisch
Über (Lucas: dann oft vorsichtig) — Tor-Märkte nur bei beидerseitigem Dead-Rubber (entspannt → Unter).
"""
from __future__ import annotations

from typing import Optional

from sharp_signals.base import Signal, SignalResult, market_side

# Top-5-Liga-Meta (aus update_dashboard.LEAGUES). europe_cut = CL+EL+ECL-Plätze; rel = Abstiegszone.
LEAGUE_META = {
    "ENG": {"total": 20, "rounds": 38, "europe_cut": 7, "rel": 3},
    "ESP": {"total": 20, "rounds": 38, "europe_cut": 7, "rel": 3},
    "ITA": {"total": 20, "rounds": 38, "europe_cut": 7, "rel": 3},
    "GER": {"total": 18, "rounds": 34, "europe_cut": 7, "rel": 3},  # inkl. Relegations-Platz
    "FRA": {"total": 18, "rounds": 34, "europe_cut": 6, "rel": 3},
}

MAX_PP = 2.0   # konservativer Deckel wie incentive


def _pts_at(rows: list, pos: int):
    """Punkte des Teams auf Tabellenplatz `pos` (1-basiert). None wenn außerhalb."""
    if 1 <= pos <= len(rows):
        return rows[pos - 1].get("points", rows[pos - 1].get("pts"))
    return None


def _time_factor(rounds_left: int, rounds_total: int) -> float:
    """0 in der ersten Saisonhälfte, rampt linear auf 1 in den letzten Runden (Endspurt-Hebel)."""
    if rounds_total <= 0:
        return 0.0
    frac_left = rounds_left / rounds_total
    # ab ~55% gespielt beginnt der Druck, voll in der Schlussrunde
    return max(0.0, min(1.0, (0.55 - frac_left) / 0.55))


def team_pressure(row: dict, rows: list, meta: dict, rounds_left: int) -> tuple[float, str]:
    """Gibt (pressure 0..1, motive 'win'|'dead'|'mid') für ein Team zurück.
    pressure = wie sehr das Team Punkte BRAUCHT × Zeit-Faktor. dead = nichts mehr zu spielen."""
    pos = row.get("pos")
    pts = row.get("points", row.get("pts"))
    if pos is None or pts is None:
        return 0.0, "mid"
    total = meta["total"]
    euro_cut = meta["europe_cut"]
    rel_start = total - meta["rel"] + 1
    max_gain = rounds_left * 3
    tf = _time_factor(rounds_left, meta["rounds"])
    if max_gain <= 0 or tf <= 0:
        return 0.0, "mid"

    # Nächste relevante Grenze + benötigte Punkte bestimmen.
    needed = None
    if pos <= 2:                       # Titel-Endspurt: Platz 1 halten/erreichen
        lead_pts = _pts_at(rows, 1)
        needed = max(0, (lead_pts - pts)) if lead_pts is not None else 0
        race = "Titel"
    elif pos <= euro_cut:              # Europa-Platz halten — Druck = wie nah der erste Verfolger
        chaser = _pts_at(rows, euro_cut + 1)
        needed = max(0, max_gain - (pts - chaser)) if chaser is not None else 0
        race = "Europa halten"
    elif pos <= euro_cut + 3:          # Europa jagen
        cut_pts = _pts_at(rows, euro_cut)
        needed = (cut_pts - pts + 1) if cut_pts is not None else None
        race = "Europa-Jagd"
    elif pos >= rel_start - 1:         # Abstiegskampf (Drop-Zone + ein Platz darüber)
        safe_pts = _pts_at(rows, rel_start - 1)
        if pos >= rel_start:
            needed = (safe_pts - pts + 1) if safe_pts is not None else None
        else:                          # knapp über dem Strich → Vorsprung verteidigen
            below = _pts_at(rows, rel_start)
            needed = max(0, max_gain - (pts - below)) if below is not None else 0
        race = "Abstiegskampf"
    else:
        return 0.0, "dead"             # gesichertes Mittelfeld → nichts zu spielen

    if needed is None:
        return 0.0, "mid"
    if needed > max_gain:              # mathematisch nicht erreichbar → raus → dead
        return 0.0, "dead"
    if needed <= 0:                    # bereits gesichert → dead (kein Wettbewerbs-Anreiz mehr)
        return 0.0, "dead"
    pressure = min(1.0, needed / max_gain) * tf
    return round(pressure, 3), ("win" if pressure > 0.12 else "mid")


class LeaguePressureSignal(Signal):
    def name(self) -> str:
        return "league_pressure"

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        league = context.get("group_id")
        meta = LEAGUE_META.get(league)
        if not meta:
            return None
        standings = (context.get("standings") or {}).get(league)
        if not standings:
            return None
        md = context.get("matchday")
        try:
            rounds_left = meta["rounds"] - int(md)
        except (TypeError, ValueError):
            return None
        if rounds_left <= 0:
            return None

        home_id, away_id = context.get("home_id"), context.get("away_id")
        hrow = next((r for r in standings if r.get("team") == home_id), None)
        arow = next((r for r in standings if r.get("team") == away_id), None)
        if not hrow or not arow:
            return None

        hp, hm = team_pressure(hrow, standings, meta, rounds_left)
        ap, am = team_pressure(arow, standings, meta, rounds_left)

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        score = 0.0
        ev = ""
        if side in ("home", "away"):
            mine, theirs = (hp if side == "home" else ap), (ap if side == "home" else hp)
            mine_mot = hm if side == "home" else am
            theirs_mot = am if side == "home" else hm
            # Eigener Sieg-Druck hebt, Gegner-Druck dämpft. Bonus wenn Gegner indifferent (dead).
            if mine_mot == "win":
                score += mine * MAX_PP
                if theirs_mot == "dead":
                    score += 0.5
            score -= theirs * MAX_PP * 0.6
            ev = (f"{('Heim' if side=='home' else 'Auswärts')}-Team Tabellen-Druck "
                  f"{mine:.0%} ({mine_mot}), Gegner {theirs:.0%} ({theirs_mot})")
        elif side == "under":
            if hm == "dead" and am == "dead":   # beidseitig nichts zu spielen → entspannt
                score += MAX_PP * 0.6
                ev = "Beide Teams ohne Tabellen-Anreiz (Dead-Rubber) → ruhigeres Spiel"
            else:
                return None
        elif side == "over":
            # Lucas: beидerseitiger Muss-Sieg ≠ automatisch Über (oft vorsichtig) → kein Over-Boost.
            return None

        score = max(-MAX_PP, min(MAX_PP, round(score, 2)))
        if abs(score) < 0.3:            # früh in der Saison / kein echter Druck → Schläfer
            return None
        conf = min(0.7, 0.3 + max(hp, ap) * 0.5)
        return SignalResult(score=score, confidence=round(conf, 2), evidence=ev,
                            metadata={"homePressure": hp, "awayPressure": ap,
                                      "homeMotive": hm, "awayMotive": am,
                                      "roundsLeft": rounds_left})
