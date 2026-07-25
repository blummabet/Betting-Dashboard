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
    # 13.07.2026 (Lucas: „MLS startet Freitag"). MLS ist STRUKTURELL anders — deshalb nicht
    # einfach eine sechste Zeile mit europäischen Annahmen:
    #   · KEIN ABSTIEG (rel=0) → der übliche „Abstiegskampf"-Zweig darf gar nicht greifen,
    #     sonst erfinden wir Druck, den es nicht gibt (Tabellenletzter spielt trotzdem um nichts).
    #   · Das Rennen läuft JE CONFERENCE (East/West), nicht in der Gesamttabelle. Ein Team auf
    #     Gesamtrang 18 kann in seiner Conference locker Playoff-Platz 6 sein.
    #   · Playoff-Schnitt: Top 9 je Conference (15 Teams je Conference).
    #   · Unter dem Strich jagt JEDES Team die Playoffs (chase_window=all) — anders als in Europa,
    #     wo das Mittelfeld irgendwann wirklich um nichts mehr spielt.
    "MLS": {"total": 15, "rounds": 34, "europe_cut": 9, "rel": 0,
            "conference": True, "chase_all": True},
}

# Wie weit unter dem Qualifikations-Strich jagt ein Team noch aktiv? (Europa: 3 Plätze;
# MLS: alle — die Playoff-Jagd geht bis zum Tabellenende, weil es keinen Abstieg gibt.)
DEFAULT_CHASE_WINDOW = 3


def _conference_of(team_id: str) -> str | None:
    """East/West aus mls_conferences.json (lazy, gecacht). None → keine Conference-Liga."""
    global _CONF_CACHE
    if _CONF_CACHE is None:
        try:
            import json as _j
            from pathlib import Path as _P
            raw = _j.loads((_P(__file__).parent.parent / "mls_conferences.json").read_text("utf-8"))
            _CONF_CACHE = {k: v.get("conference") for k, v in (raw.get("teams") or {}).items()}
        except Exception:
            _CONF_CACHE = {}
    return _CONF_CACHE.get(str(team_id))


_CONF_CACHE: dict | None = None


def _conference_view(rows: list, team_id: str) -> tuple[list, dict | None]:
    """Tabelle auf die Conference des Teams zuschneiden und NEU durchnummerieren.

    Ohne das rechnet der Playoff-Druck gegen die falsche Grenze: Gesamtrang ≠ Conference-Rang.
    Gibt (conference_rows, row_des_teams) — beides None-sicher.
    """
    conf = _conference_of(team_id)
    if not conf:
        return [], None
    sub = [r for r in rows if _conference_of(r.get("team")) == conf]
    # Nach Punkten (dann Tordifferenz) sortieren und Conference-Position vergeben.
    sub = sorted(sub, key=lambda r: (-(r.get("points", r.get("pts")) or 0), -(r.get("gd") or 0)))
    out = []
    me = None
    for i, r in enumerate(sub, start=1):
        rr = dict(r)
        rr["pos"] = i
        out.append(rr)
        if str(rr.get("team")) == str(team_id):
            me = rr
    return out, me

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


def team_pressure(row: dict, rows: list, meta: dict, rounds_left: int) -> tuple[float, str, str]:
    """Gibt (pressure 0..1, motive 'win'|'dead'|'mid', branch) für ein Team zurück.
    pressure = wie sehr das Team Punkte BRAUCHT × Zeit-Faktor. dead = nichts mehr zu spielen.
    branch ∈ {title, hold, chase, releg, dead, mid} = WELCHE Tabellen-Situation den Druck erzeugt.
    25.07.2026 (Backtest, siehe evaluate): branch trennt die STARKE Seite (title/hold = am/über dem
    Schnitt) von der schwachen Jagd (chase/releg = unter dem Schnitt) — nur erstere darf einen
    Sieg-Boost geben, weil „braucht Punkte" von unten ≈ „ist schwächer" (Boost war anti-prädiktiv)."""
    # 13.07.2026 (MLS): Das Playoff-Rennen läuft JE CONFERENCE. Ohne diesen Zuschnitt würde gegen
    # die Gesamttabelle gerechnet — ein Team auf Gesamtrang 18 kann in seiner Conference bequem
    # Playoff-Platz 6 sein. Erst zuschneiden, dann rechnen.
    if meta.get("conference"):
        conf_rows, conf_row = _conference_view(rows, row.get("team"))
        if not conf_rows or not conf_row:
            return 0.0, "mid", "mid"   # keine Conference-Zuordnung → lieber schweigen als raten
        rows, row = conf_rows, conf_row

    pos = row.get("pos")
    pts = row.get("points", row.get("pts"))
    if pos is None or pts is None:
        return 0.0, "mid", "mid"
    total = meta["total"]
    euro_cut = meta["europe_cut"]      # Europa-Platz bzw. (MLS) Playoff-Schnitt
    has_rel = meta.get("rel", 0) > 0   # MLS: KEIN Abstieg → der Zweig darf nie greifen
    rel_start = total - meta["rel"] + 1 if has_rel else None
    chase_window = total if meta.get("chase_all") else DEFAULT_CHASE_WINDOW
    max_gain = rounds_left * 3
    tf = _time_factor(rounds_left, meta["rounds"])
    if max_gain <= 0 or tf <= 0:
        return 0.0, "mid", "mid"

    # Nächste relevante Grenze + benötigte Punkte + Zweig bestimmen.
    needed = None
    if pos <= 2:                       # Endspurt an der Spitze
        lead_pts = _pts_at(rows, 1)
        needed = max(0, (lead_pts - pts)) if lead_pts is not None else 0
        branch = "title"
    elif pos <= euro_cut:              # Quali-Platz halten — Druck = wie nah der erste Verfolger
        chaser = _pts_at(rows, euro_cut + 1)
        needed = max(0, max_gain - (pts - chaser)) if chaser is not None else 0
        branch = "hold"
    elif pos <= euro_cut + chase_window:   # Quali-Platz jagen (von UNTER dem Schnitt)
        cut_pts = _pts_at(rows, euro_cut)
        needed = (cut_pts - pts + 1) if cut_pts is not None else None
        branch = "chase"
    elif has_rel and pos >= rel_start - 1:   # Abstiegskampf (Drop-Zone + ein Platz darüber)
        safe_pts = _pts_at(rows, rel_start - 1)
        if pos >= rel_start:
            needed = (safe_pts - pts + 1) if safe_pts is not None else None
        else:                          # knapp über dem Strich → Vorsprung verteidigen
            below = _pts_at(rows, rel_start)
            needed = max(0, max_gain - (pts - below)) if below is not None else 0
        branch = "releg"
    else:
        return 0.0, "dead", "dead"     # gesichertes Mittelfeld → nichts zu spielen

    if needed is None:
        return 0.0, "mid", "mid"
    if needed > max_gain:              # mathematisch nicht erreichbar → raus → dead
        return 0.0, "dead", "dead"
    if needed <= 0:                    # bereits gesichert → dead (kein Wettbewerbs-Anreiz mehr)
        return 0.0, "dead", "dead"
    pressure = min(1.0, needed / max_gain) * tf
    return round(pressure, 3), ("win" if pressure > 0.12 else "mid"), branch


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

        hp, hm, hb = team_pressure(hrow, standings, meta, rounds_left)
        ap, am, ab = team_pressure(arow, standings, meta, rounds_left)

        side = market_side(pick.get("market", ""))
        if side is None:
            return None

        # 25.07.2026 (Backtest [[project_league_pressure_direction_bug]]): Der 'chase'-Zweig (Playoff-
        # Jagd von UNTER dem Schnitt) ist meist das schwächere Team → „braucht Punkte von unten" ≈
        # „ist schlechter", der alte Sieg-Boost war anti-prädiktiv (MLS-Backtest: Heimsieg 0.479 /
        # Auswärtssieg 0.444, beide <0.5). Deshalb BOOSTEN nur noch title/hold (stark, am/über dem
        # Schnitt) + releg (Abstiegskampf = extreme Stakes, domänen-belegt kämpferisch — und
        # NICHT von der MLS-Evidenz betroffen, da MLS keinen Abstieg hat). Der chase-Zweig gibt
        # keinen Sieg-Boost mehr und dämpft auch nicht als Gegner (schwacher Jäger = keine Bedrohung).
        # Dead-Rubber→Unter bleibt unangetastet (einziger klar positiver Zweig, 0.552).
        BOOST_BRANCHES = ("title", "hold", "releg")

        score = 0.0
        ev = ""
        if side in ("home", "away"):
            mine, theirs = (hp if side == "home" else ap), (ap if side == "home" else hp)
            mine_mot = hm if side == "home" else am
            theirs_mot = am if side == "home" else hm
            mine_branch = hb if side == "home" else ab
            theirs_branch = ab if side == "home" else hb
            # Eigener Sieg-Druck hebt NUR aus einem Boost-Zweig (nicht chase); Bonus wenn Gegner dead.
            if mine_mot == "win" and mine_branch in BOOST_BRANCHES:
                score += mine * MAX_PP
                if theirs_mot == "dead":
                    score += 0.5
            # Gegner-Druck dämpft NUR wenn der Gegner aus einem Boost-Zweig kommt (echte Bedrohung).
            if theirs_branch in BOOST_BRANCHES:
                score -= theirs * MAX_PP * 0.6
            ev = (f"{('Heim' if side=='home' else 'Auswärts')}-Team Tabellen-Druck "
                  f"{mine:.0%} ({mine_mot}/{mine_branch}), Gegner {theirs:.0%} ({theirs_mot}/{theirs_branch})")
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
                                      "homeBranch": hb, "awayBranch": ab,
                                      "roundsLeft": rounds_left})
