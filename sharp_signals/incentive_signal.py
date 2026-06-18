"""
sharp_signals/incentive_signal.py — Competitive Incentive Signal

Tier-4 — modelliert die ANREIZ-Struktur einer Begegnung.
Vier orthogonale Komponenten, alle rein computational (keine NLP, keine News):

  A. Qualifikations-Mathematik (MD2/MD3)
     - must-win / can-draw / qualified / eliminated
     - Dead-Rubber-Detection (beide Teams qualified ODER beide eliminated)
     - Volle Logik aus Liga-Code geportet (competitor-aware mit GD-Tiebreaker)

  B. Bracket-Asymmetrie (ab MD2, voll wirksam vor MD3)
     - Pro Gruppen-Position-Outcome (1./2.) projiziert auf wahrscheinlichen
       K.O.-Gegner via wm_bracket.json + best-third-Combinatorik.
     - Elo-Delta zwischen Bracket-Pfaden = Anreiz "lieber 2. als 1. werden".

  C. Venue-Distanz (ab MD2)
     - Welcher Bracket-Pfad führt zu welchem Venue? Distanz vom aktuellen
       Match-Venue + Höhen-Wechsel aus wm_venues.json.
     - Asymmetrisch grosse Reise zwischen "1." vs "2." → Anreiz auf näheren Slot.

  D. Rotation-Risk (K.O.-Phase, nach Round of 32)
     - Wenn nächste Runde wichtig ist UND <4 Tage Pause → Star-Rotation
       wahrscheinlich → xG-Discount für das rotierende Team.

Pre-Tournament (vor MD2) liefert das Signal None — nichts berechenbar.
Anti-Korrelations-Familie: "incentive" (siehe registry.py).

Konfig: cocobet_config.json → profiles.<profile>.incentive_signal
Liga-Profile-aware via COCOBET_PROFILE env oder profiles.active.
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Optional, Any
from sharp_signals.base import Signal, SignalResult


# ──────────────────────────────────────────────────────────────────────────
#  Defaults — werden via cocobet_config.json überschrieben
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_THRESHOLDS: dict = {
    # Komponente A — Qualifikations-Math
    "must_win_pp":               2.0,   # Team das gewinnen muss → +pp für Sieg-Markt
    "dead_rubber_under_pp":      1.0,   # Beide qualified/eliminated → +pp auf Unter-Picks
    "stake_asymmetry_pp":        1.5,   # Ein Team hi-stake, anderer lo-stake → +pp für hi-stake-Sieg
    # Komponente B — Bracket-Asymmetrie
    "bracket_elo_threshold":    50.0,   # Min Elo-Δ um als "echter Anreiz" zu zählen
    "bracket_elo_max_pp":        2.0,   # Max pp wenn 1./2. Bracket-Pfade extrem unterschiedlich
    "bracket_elo_scale":        150.0,  # Elo-Δ bei dem max pp erreicht wird
    # Komponente C — Venue-Distanz
    "venue_dist_threshold_km": 1000.0,  # Min Delta in km um als Anreiz zu zählen
    "venue_dist_max_pp":         1.5,   # Max pp bei extremem Distanz-Unterschied
    "venue_dist_scale_km":     3000.0,  # km-Delta bei dem max pp erreicht wird
    "venue_altitude_penalty_pp": 0.5,   # Zusatz-Penalty wenn Pfad nach Mexico City (>1500m)
    # Komponente D — Rotation-Risk
    "rotation_short_rest_days":  3,     # <= N Tage Pause → Rotation-Risk
    "rotation_pp":              -1.5,   # xG-Discount auf rotierendes Team
    # Threshold + Confidence
    "min_signal_pp":             0.4,   # Unter dieser Schwelle wird kein Signal erzeugt
    "confidence_md2":            0.55,  # MD2 — viele Konstellationen noch offen
    "confidence_md3":            0.75,  # MD3 — Bracket steht voll
    "confidence_ko":             0.65,  # K.O.-Phase Rotation
}


# ──────────────────────────────────────────────────────────────────────────
#  Config + Data Loaders
# ──────────────────────────────────────────────────────────────────────────
def _base_dir() -> Path:
    return Path(__file__).parent.parent


def _load_thresholds() -> dict:
    """Lädt incentive_signal-Config aus cocobet_config.json, Profile-aware."""
    try:
        import json, os
        raw = json.loads((_base_dir() / "cocobet_config.json").read_text(encoding="utf-8"))
        active = os.environ.get("COCOBET_PROFILE") or raw["profiles"].get("active", "wm2026")
        cfg = raw["profiles"].get(active, {}).get("incentive_signal") or {}
        return {**DEFAULT_THRESHOLDS, **cfg}
    except Exception:
        return DEFAULT_THRESHOLDS


def _load_bracket() -> Optional[dict]:
    """Lädt wm_bracket.json. Liefert None wenn nicht vorhanden (Liga-Profil)."""
    try:
        import json
        return json.loads((_base_dir() / "wm_bracket.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_venues() -> Optional[dict]:
    """Lädt wm_venues.json. Liefert None wenn nicht vorhanden (Liga-Profil)."""
    try:
        import json
        raw = json.loads((_base_dir() / "wm_venues.json").read_text(encoding="utf-8"))
        return raw.get("venues") or {}
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
#  Pick-Side-Mapping (analog zu pressure_index.py)
# ──────────────────────────────────────────────────────────────────────────
def _pick_side(market: str) -> int:
    """+1 = Home-Sieg-Pick, -1 = Auswärts-Sieg-Pick, 0 = neutral (Draw/O/U)."""
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


def _is_under_market(market: str) -> bool:
    return "unter" in (market or "").lower()


def _is_over_market(market: str) -> bool:
    m = (market or "").lower()
    return "über" in m or "uber" in m


# ──────────────────────────────────────────────────────────────────────────
#  Helpers — Group-Standings + Qualification-Math (Komponente A)
# ──────────────────────────────────────────────────────────────────────────
def _team_row_from_standings(team_id: str, standings: Any) -> Optional[dict]:
    """
    standings kann {"A":[{team:"MEX",points:4,...}],"B":[...]} oder ein flacher
    Lookup-Dict sein. Sucht den Eintrag für team_id.
    """
    if not isinstance(standings, dict):
        return None
    for _grp, rows in standings.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("team") == team_id or row.get("teamId") == team_id:
                return row
    return None


def _group_table(group_id: str, standings: dict) -> list[dict]:
    """Liefert die sortierte Tabelle einer Gruppe (höchste Punkte zuerst)."""
    rows = standings.get(group_id) if isinstance(standings, dict) else None
    if not isinstance(rows, list):
        return []
    # Sortiert nach (points, gd, gf) absteigend — FIFA-Standard-Tiebreaker
    def _sort_key(r):
        return (
            -int(r.get("points") or 0),
            -int(r.get("gd") or 0),
            -int(r.get("gf") or 0),
        )
    return sorted([r for r in rows if isinstance(r, dict)], key=_sort_key)


def _compute_qualification_state(team_id: str, group_id: str, matchday: int,
                                  standings: dict) -> dict:
    """
    Komponente A — was muss/kann das Team noch erreichen?

    Returns:
      {
        "matches_played":     int (0..3),
        "matches_remaining":  int,
        "current_position":   int (1..4),
        "must_win":           bool,
        "can_draw":           bool,
        "qualified":          bool,   # mathematisch sicher 1./2.
        "eliminated":         bool,   # mathematisch raus
        "third_realistic":    bool,   # noch in Reichweite der besten Drittplazierten
        "label":              str,    # "must_win" / "can_draw" / "qualified" / etc
      }
    """
    table = _group_table(group_id, standings)
    if not table:
        return {"label": "unknown"}

    # Position finden
    pos = None
    team_row = None
    for i, r in enumerate(table, 1):
        if r.get("team") == team_id or r.get("teamId") == team_id:
            pos = i
            team_row = r
            break
    if pos is None or team_row is None:
        return {"label": "unknown"}

    played = int(team_row.get("played") or 0)
    matches_remaining = max(0, 3 - played)   # WM-Gruppe = 3 Spiele
    pts = int(team_row.get("points") or 0)
    gd  = int(team_row.get("gd") or 0)
    max_gain = matches_remaining * 3

    # Wie viele Punkte haben die anderen — als (max_possible, current_pts) Tupel.
    # Achtung: kein Dict in Tupel sonst sort-crash bei Tie.
    others = [r for i, r in enumerate(table, 1) if i != pos]
    others_pts = []
    for r in others:
        o_played = int(r.get("played") or 0)
        o_remain = max(0, 3 - o_played)
        o_pts = int(r.get("points") or 0)
        others_pts.append((o_pts + o_remain * 3, o_pts))   # (max, current)

    own_max = pts + max_gain

    # ── Qualified (mathematisch sicher Top 2) ────────────────────────────
    # Sicher Top-2 wenn: zwei der anderen schon current_pts >= unsere worst-case (= pts)?
    # Strikter: unser pts > drittbestes max anderer Teams (Liga-Standard-Logik)
    others_max_sorted = sorted([m for m, _ in others_pts], reverse=True)
    if len(others_max_sorted) >= 2:
        third_max = others_max_sorted[1]
        qualified = pts > third_max          # strict — hard-qualified
    else:
        qualified = False
        third_max = 0

    # ── Eliminated (mathematisch raus aus Top 2) ──────────────────────────
    # Selbst wenn wir alles gewinnen: mind. 2 andere haben bereits mehr aktuelle pts
    # als unser bestmögliches Ende → wir können sie nicht mehr überholen.
    if len(others_pts) >= 2:
        better_than_us = sum(1 for _, o_cur in others_pts if o_cur > own_max)
        eliminated_top2 = better_than_us >= 2
    else:
        eliminated_top2 = False

    # Best-Third (typische Schwelle in WM-Praxis: 4pts gibt gute Chance, 3pts grenzwertig)
    # Wenn schon Top-2-eliminated UND own_max < 3pts → komplett raus
    third_realistic = (own_max >= 3) and not (eliminated_top2 and own_max < 4)

    # ── Must-Win Logik ───────────────────────────────────────────────────
    # "Hoffnungs-Tier" = niedrigere von (Top-2-Schwelle, Best-Third-Schwelle 4pts).
    # Team must_win wenn Sieg dieses Tier erreicht aber Draw garantiert nicht.
    # Beispiele:
    #   • Top-2 noch erreichbar:  hopeful_tier = third_max, classic must_win für 2. Platz
    #   • Nur Best-Third drin:    hopeful_tier = 4, Sieg liefert 4pts-Quali-Chance
    must_win = False
    can_draw = False
    if matches_remaining == 1 and not qualified:
        hopeful_tier = min(third_max, 4) if third_max > 0 else 4
        win_reaches_tier  = (pts + 3 >= hopeful_tier)
        draw_reaches_tier = (pts + 1 >= hopeful_tier)
        # must_win: Sieg könnte reichen, Draw garantiert nicht (strict <)
        must_win = win_reaches_tier and (pts + 1 < hopeful_tier)
        # can_draw: Draw übertrifft (Top-2-Logik streng — strikt > third_max für Sicherheit)
        if third_max > 0:
            can_draw = (pts + 1 > third_max)

    # Label
    if qualified:
        label = "qualified"
    elif eliminated_top2 and not third_realistic:
        label = "eliminated"
    elif must_win:
        label = "must_win"
    elif can_draw:
        label = "can_draw"
    elif third_realistic:
        label = "third_chase"
    else:
        label = "open"

    return {
        "matches_played":    played,
        "matches_remaining": matches_remaining,
        "current_position":  pos,
        "current_points":    pts,
        "current_gd":        gd,
        "must_win":          bool(must_win),
        "can_draw":          bool(can_draw),
        "qualified":         bool(qualified),
        "eliminated":        bool(eliminated_top2 and not third_realistic),
        "third_realistic":   bool(third_realistic),
        "label":             label,
    }


# ──────────────────────────────────────────────────────────────────────────
#  Helpers — Bracket-Projektion (Komponente B)
# ──────────────────────────────────────────────────────────────────────────
def _project_final_position(team_id: str, group_id: str, standings: dict,
                            home_id: str, away_id: str, outcome: str) -> Optional[int]:
    """
    Projiziert finale Tabellen-Position des Teams in seiner Gruppe nach MD3,
    gegeben das ausgewählte Outcome ('W'/'D'/'L') für das Match home_id vs away_id.

    Vereinfachung: alle ANDEREN Teams behalten ihre aktuellen Punkte (kein zweites
    MD3-Spiel projiziert). Damit ist die Projektion exakt für den (häufigen) Fall,
    dass das Team-Match das letzte der Gruppe ist; sonst eine grobe Schätzung.
    """
    table = _group_table(group_id, standings)
    if not table:
        return None
    # Neue Punkte/GD pro Team berechnen
    new_table = []
    for r in table:
        tid = r.get("team") or r.get("teamId")
        pts = int(r.get("points") or 0)
        gd  = int(r.get("gd") or 0)
        gf  = int(r.get("gf") or 0)
        if tid == home_id:
            if outcome == "W":     pts += 3; gd += 1; gf += 1
            elif outcome == "D":   pts += 1
            elif outcome == "L":   gd -= 1
        elif tid == away_id:
            if outcome == "W":     pts += 0; gd -= 1   # away verliert
            elif outcome == "D":   pts += 1
            elif outcome == "L":   pts += 3; gd += 1; gf += 1   # away gewinnt
        new_table.append({"team": tid, "points": pts, "gd": gd, "gf": gf})
    new_table.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"]))
    for i, r in enumerate(new_table, 1):
        if r["team"] == team_id:
            return i
    return None


def _avg_third_elo(from_groups: list, exclude_team: Optional[str], standings: dict,
                   team_elo: dict) -> Optional[float]:
    """
    Mittlere Elo der projizierten Drittplazierten aus den genannten Gruppen.
    Nutzt aktuellen 3.-Platz der jeweiligen Gruppe (oder skippt wenn unbekannt).
    """
    elos = []
    for grp in from_groups:
        tab = _group_table(grp, standings)
        if len(tab) >= 3:
            tid = tab[2].get("team") or tab[2].get("teamId")
            if tid and tid != exclude_team:
                e = team_elo.get(tid)
                if isinstance(e, (int, float)):
                    elos.append(float(e))
    if not elos:
        return None
    return sum(elos) / len(elos)


def _project_r32_venue_id(bracket: dict, group_id: str, position: int) -> Optional[str]:
    """Findet den R32-Venue-Slot für (group_id, position). None wenn best_third oder unbekannt."""
    if not bracket:
        return None
    for mk, m in bracket.get("round_of_32", {}).items():
        for own_side in ("side_a", "side_b"):
            os_ = m.get(own_side) or {}
            if (isinstance(os_, dict)
                    and os_.get("type") == "group_position"
                    and os_.get("group") == group_id
                    and int(os_.get("position") or 0) == position):
                return m.get("venue_id")
    return None


def _project_r32_opponent_elo(bracket: dict, group_id: str, position: int,
                              team_id: str, standings: dict,
                              team_elo: dict) -> Optional[float]:
    """
    Findet den R32-Slot für (group_id, position) und projiziert die Elo
    des Gegner-Teams (oder Mittel bei best_third).
    """
    if not bracket:
        return None
    r32 = bracket.get("round_of_32", {})
    # Suche den R32-Match in dem dieses (group, position) auftaucht
    for mk, m in r32.items():
        for own_side, opp_side in (("side_a", "side_b"), ("side_b", "side_a")):
            os_ = m.get(own_side) or {}
            if (isinstance(os_, dict)
                    and os_.get("type") == "group_position"
                    and os_.get("group") == group_id
                    and int(os_.get("position") or 0) == position):
                opp = m.get(opp_side) or {}
                if isinstance(opp, dict):
                    if opp.get("type") == "group_position":
                        # Gegner = aktuell-platziertes Team in (opp_group, opp_pos)
                        opp_group = opp.get("group")
                        opp_pos   = int(opp.get("position") or 0)
                        tab = _group_table(opp_group, standings)
                        if 1 <= opp_pos <= len(tab):
                            tid = tab[opp_pos - 1].get("team") or tab[opp_pos - 1].get("teamId")
                            e = team_elo.get(tid)
                            if isinstance(e, (int, float)):
                                return float(e)
                    elif opp.get("type") == "best_third":
                        return _avg_third_elo(opp.get("from_groups") or [],
                                              team_id, standings, team_elo)
                return None
    return None


# ──────────────────────────────────────────────────────────────────────────
#  Helper — Haversine (für Komponente C, hier weil global gebraucht)
# ──────────────────────────────────────────────────────────────────────────
def _haversine_km(v1: dict, v2: dict) -> float:
    """Great-circle distance zwischen zwei Venues in km."""
    if not v1 or not v2:
        return 0.0
    try:
        lat1, lon1 = math.radians(float(v1["lat"])), math.radians(float(v1["lon"]))
        lat2, lon2 = math.radians(float(v2["lat"])), math.radians(float(v2["lon"]))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return 2 * 6371.0 * math.asin(math.sqrt(a))
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────────
#  Signal-Klasse
# ──────────────────────────────────────────────────────────────────────────
class IncentiveSignal(Signal):
    """
    Competitive Incentive Signal — vier Komponenten je nach Phase.

    Context erwartet (alle optional, fehlende → Komponente liefert nichts):
      home_id, away_id       — Team-IDs
      group_id               — Gruppen-Buchstabe ("A".."L"), nur Gruppenphase
      matchday               — 1/2/3 oder "R32"/"R16"/"QF"/"SF"/"FINAL"
      standings              — { "A":[{team,points,played,gd,gf,...}], ... }
      team_elo               — { team_id: elo_int }
      current_venue_id       — Venue-Key des aktuellen Spiels (für Distanz)
      next_match_date        — ISO-Date des nächsten Matches (für Rotation-Risk)
      current_match_date     — ISO-Date des aktuellen Matches
    """

    def __init__(self):
        self._t = _load_thresholds()
        self._bracket = _load_bracket()
        self._venues  = _load_venues()

    def name(self) -> str:
        return "incentive_signal"

    # ── Komponenten-Stubs (B/C/D werden in den nächsten Schritten gefüllt) ──
    def _component_a(self, pick: dict, context: dict,
                     home_state: dict, away_state: dict) -> tuple[float, str, dict]:
        """
        Komponente A — Qualifikations-Math.
        Returns (score_pp, evidence_str, metadata_dict).
        """
        side  = _pick_side(pick.get("market", ""))
        is_under = _is_under_market(pick.get("market", ""))
        is_over  = _is_over_market(pick.get("market", ""))

        score = 0.0
        notes = []
        meta  = {"home_label": home_state.get("label"), "away_label": away_state.get("label")}

        # Dead-Rubber: beide Teams kämpfen nicht mehr aktiv (qualified, can_draw
        # ohne Sieg-Druck, oder eliminated). Ein Team das nur einen Draw braucht
        # rotiert in der Praxis auch — funktional dead rubber.
        def _not_fighting(s: dict) -> bool:
            return bool(s.get("qualified") or s.get("can_draw") or s.get("eliminated"))
        h_decided = _not_fighting(home_state)
        a_decided = _not_fighting(away_state)
        if h_decided and a_decided:
            meta["dead_rubber"] = True
            if is_under:
                score += self._t["dead_rubber_under_pp"]
                notes.append("Beide Teams bereits durch — Tor-Niveau sinkt typisch")
            elif is_over:
                score -= self._t["dead_rubber_under_pp"]
                notes.append("Beide Teams bereits durch — weniger Tore erwartet")
            return (score, " · ".join(notes), meta)

        # Must-Win-Asymmetrie: ein Team must_win, anderes nicht
        h_must_one_side = home_state.get("must_win") and not away_state.get("must_win")
        a_must_one_side = away_state.get("must_win") and not home_state.get("must_win")
        if h_must_one_side:
            if side == +1:
                score += self._t["must_win_pp"]
                notes.append("Heim muss gewinnen, Auswärts nicht — voller Druck pro Heim")
            elif side == -1:
                score -= self._t["must_win_pp"]
                notes.append("Heim muss gewinnen — wird voll attackieren")
            # FIX 09.06.2026 — O/U: Must-Win-Team spielt offensiv → mehr Tore
            elif is_over:
                score += self._t["must_win_pp"] * 0.5
                notes.append("Heim muss gewinnen — wird offensiv attackieren → mehr Tore wahrscheinlich")
            elif is_under:
                score -= self._t["must_win_pp"] * 0.5
                notes.append("Heim muss gewinnen — wird offensiv attackieren → Unter unwahrscheinlicher")
        elif a_must_one_side:
            if side == -1:
                score += self._t["must_win_pp"]
                notes.append("Auswärts muss gewinnen, Heim nicht — voller Druck pro Auswärts")
            elif side == +1:
                score -= self._t["must_win_pp"]
                notes.append("Auswärts muss gewinnen — wird voll attackieren")
            elif is_over:
                score += self._t["must_win_pp"] * 0.5
                notes.append("Auswärts muss gewinnen — wird offensiv attackieren → mehr Tore wahrscheinlich")
            elif is_under:
                score -= self._t["must_win_pp"] * 0.5
                notes.append("Auswärts muss gewinnen — wird offensiv attackieren → Unter unwahrscheinlicher")

        # BEIDE müssen gewinnen (symmetrisch, 17.06.2026 Lucas-Audit): kein Ergebnis-Edge,
        # aber offenes Spiel — beide attackieren → klassisches Tor-Fest. Bisher fehlte der
        # symmetrische Fall (nur die Asymmetrie war abgedeckt).
        if home_state.get("must_win") and away_state.get("must_win"):
            meta["both_must_win"] = True
            if is_over:
                score += self._t["must_win_pp"] * 0.6
                notes.append("Beide müssen gewinnen — offenes Spiel, beide attackieren → mehr Tore")
            elif is_under:
                score -= self._t["must_win_pp"] * 0.6
                notes.append("Beide müssen gewinnen — offenes Spiel → Unter unwahrscheinlicher")

        # Stake-Asymmetrie: ein Team hi-stake (must_win/third_chase), anderes qualified
        h_hi = home_state.get("must_win") or home_state.get("third_chase")
        a_hi = away_state.get("must_win") or away_state.get("third_chase")
        if h_hi and away_state.get("qualified"):
            if side == +1:
                score += self._t["stake_asymmetry_pp"]
                notes.append("Heim spielt um Aufstieg, Auswärts schon qualifiziert (rotiert)")
            # FIX 09.06.2026 — O/U: Stake-Asymmetrie → halbierter Stil-Konflikt → weniger Tore typisch
            elif is_under:
                score += self._t["stake_asymmetry_pp"] * 0.4
                notes.append("Heim kämpft, Auswärts rotiert (qualifiziert) — Spiel verläuft kontrolliert")
        elif a_hi and home_state.get("qualified"):
            if side == -1:
                score += self._t["stake_asymmetry_pp"]
                notes.append("Auswärts spielt um Aufstieg, Heim schon qualifiziert (rotiert)")
            elif is_under:
                score += self._t["stake_asymmetry_pp"] * 0.4
                notes.append("Auswärts kämpft, Heim rotiert (qualifiziert) — Spiel verläuft kontrolliert")

        return (score, " · ".join(notes), meta)

    def _component_b(self, pick: dict, context: dict,
                     home_id: str, away_id: str, group_id: str,
                     standings: dict) -> tuple[float, str, dict]:
        """
        Komponente B — Bracket-Asymmetrie.

        Pro Team: projiziert finale Position bei Sieg vs Niederlage,
        bestimmt R32-Gegner-Elo für beide Pfade, berechnet Delta.
        Wenn Delta gross genug, gibt Team-Anreiz "lieber 2. werden" (Tank-Anreiz)
        bzw "lieber 1. werden" (Top-Anreiz).
        """
        if not self._bracket:
            return (0.0, "", {})
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return (0.0, "", {})   # nur für 1X2-Picks

        team_elo = context.get("team_elo") or {}
        meta = {}

        def _team_bracket_delta(team_id: str) -> Optional[dict]:
            """
            Return: {pos_at_win, pos_at_loss, opp_elo_win, opp_elo_loss, delta_elo}.
            delta_elo > 0 = Gegner bei Sieg STÄRKER → Tank-Anreiz (2. werden lohnt).
            delta_elo < 0 = Gegner bei Sieg schwächer → Top-Anreiz.
            """
            pos_W = _project_final_position(team_id, group_id, standings,
                                            home_id, away_id, "W" if team_id == home_id else "L")
            pos_L = _project_final_position(team_id, group_id, standings,
                                            home_id, away_id, "L" if team_id == home_id else "W")
            if not pos_W or not pos_L or pos_W == pos_L:
                return None
            if pos_W > 2 or pos_L > 3:
                return None   # nur relevant wenn beide Outcomes weiterführen
            opp_W = _project_r32_opponent_elo(self._bracket, group_id, pos_W,
                                              team_id, standings, team_elo)
            opp_L = _project_r32_opponent_elo(self._bracket, group_id, pos_L,
                                              team_id, standings, team_elo)
            if opp_W is None or opp_L is None:
                return None
            return {
                "pos_W": pos_W, "pos_L": pos_L,
                "opp_elo_W": opp_W, "opp_elo_L": opp_L,
                "delta_elo": opp_W - opp_L,   # +ve = Sieg-Pfad gegen Stärkeren
            }

        # Für Pick-Side (home oder away) interessiert uns das jeweilige Team.
        team_id = home_id if side == +1 else away_id
        d = _team_bracket_delta(team_id)
        if not d:
            return (0.0, "", {})

        meta = d
        thr   = self._t["bracket_elo_threshold"]
        scale = self._t["bracket_elo_scale"]
        cap   = self._t["bracket_elo_max_pp"]

        delta = d["delta_elo"]
        if abs(delta) < thr:
            return (0.0, "", meta)

        # Linear zu cap clamped
        magnitude = min(abs(delta) / scale, 1.0) * cap

        if delta > 0:
            # Sieg-Pfad führt zu STÄRKEREM Gegner → Team hat Anreiz NICHT zu gewinnen
            # → Sieg-Pick (für unser Team) wird unwahrscheinlicher
            score = -magnitude
            evidence = (f"Bei Sieg wartet im Achtelfinale ein deutlich stärkerer Gegner "
                        f"(+{delta:.0f} Elo) — Anreiz, lieber 2. zu werden")
        else:
            score = magnitude
            evidence = (f"Bei Sieg wartet im Achtelfinale ein deutlich schwächerer Gegner "
                        f"({delta:.0f} Elo) — extra Motivation, 1. zu werden")

        return (round(score, 2), evidence, meta)

    def _component_c(self, pick: dict, context: dict,
                     home_id: str, away_id: str, group_id: str,
                     standings: dict) -> tuple[float, str, dict]:
        """
        Komponente C — Venue-Distanz + Höhen-Wechsel.

        Pro Team: projiziert R32-Venue bei Sieg vs Niederlage. Misst
        Distanz vom AKTUELLEN Match-Venue zum projizierten Venue.
        Großer Distanz-Unterschied = Reise-Burden-Anreiz auf den näheren Slot.

        Bonus: Mexico-City-Höhen-Penalty wenn ein Pfad ins Hochland führt
        (>1500m) und das andere im Tiefland bleibt.
        """
        if not self._bracket or not self._venues:
            return (0.0, "", {})
        side = _pick_side(pick.get("market", ""))
        if side == 0:
            return (0.0, "", {})

        current_venue_id = context.get("current_venue_id")
        current_v = self._venues.get(current_venue_id) if current_venue_id else None
        if not current_v:
            return (0.0, "", {})

        def _team_venue_delta(team_id: str) -> Optional[dict]:
            pos_W = _project_final_position(team_id, group_id, standings,
                                            home_id, away_id, "W" if team_id == home_id else "L")
            pos_L = _project_final_position(team_id, group_id, standings,
                                            home_id, away_id, "L" if team_id == home_id else "W")
            if not pos_W or not pos_L or pos_W == pos_L:
                return None
            if pos_W > 2 or pos_L > 3:
                return None
            ven_W = _project_r32_venue_id(self._bracket, group_id, pos_W)
            ven_L = _project_r32_venue_id(self._bracket, group_id, pos_L)
            if not ven_W or not ven_L or ven_W == ven_L:
                return None
            v_W = self._venues.get(ven_W)
            v_L = self._venues.get(ven_L)
            if not v_W or not v_L:
                return None
            d_W = _haversine_km(current_v, v_W)
            d_L = _haversine_km(current_v, v_L)
            # Höhe: Penalty wenn von Tiefland in Hochland muss (>1500m Differenz)
            alt_now = float(current_v.get("altitude_m") or 0)
            alt_W   = float(v_W.get("altitude_m") or 0)
            alt_L   = float(v_L.get("altitude_m") or 0)
            return {
                "venue_W": ven_W, "venue_L": ven_L,
                "dist_W_km": round(d_W, 0), "dist_L_km": round(d_L, 0),
                "delta_dist_km": round(d_W - d_L, 0),
                "alt_W": alt_W, "alt_L": alt_L, "alt_now": alt_now,
            }

        team_id = home_id if side == +1 else away_id
        d = _team_venue_delta(team_id)
        if not d:
            return (0.0, "", {})

        thr   = self._t["venue_dist_threshold_km"]
        scale = self._t["venue_dist_scale_km"]
        cap   = self._t["venue_dist_max_pp"]
        alt_pen = self._t["venue_altitude_penalty_pp"]

        delta_km = d["delta_dist_km"]
        score = 0.0
        notes = []

        if abs(delta_km) >= thr:
            magnitude = min(abs(delta_km) / scale, 1.0) * cap
            if delta_km > 0:
                # Sieg-Pfad WEITER weg → Reise-Burden auf Sieg-Outcome → Sieg-Pick -pp
                score -= magnitude
                notes.append(f"Bei Sieg geht's {int(delta_km)} km weiter zum Achtelfinale "
                             f"als bei Niederlage")
            else:
                score += magnitude
                notes.append(f"Bei Sieg bleibt das Achtelfinale am gleichen Ort statt "
                             f"{int(abs(delta_km))} km Reise — klarer Heimvorteil")

        # Höhen-Penalty: nur Sieg-Pfad führt in Hochland (>1500m), Niederlage-Pfad im Tiefland
        SIG_ALT = 1500.0
        if d["alt_W"] >= SIG_ALT and d["alt_L"] < SIG_ALT and d["alt_now"] < SIG_ALT:
            score -= alt_pen
            notes.append(f"Bei Sieg führt der Weg in {int(d['alt_W'])}m Höhe — "
                         f"Belastung für nicht-akklimatisierte Teams")
        elif d["alt_L"] >= SIG_ALT and d["alt_W"] < SIG_ALT and d["alt_now"] < SIG_ALT:
            score += alt_pen
            notes.append(f"Bei Sieg vermeidet das Team den Höhen-Trip "
                         f"({int(d['alt_L'])}m)")

        evidence = " · ".join(notes) if notes else ""
        d["delta_pp"] = round(score, 2)
        return (round(score, 2), evidence, d)

    def _component_d(self, pick: dict, context: dict) -> tuple[float, str, dict]:
        """
        Komponente D — Rotation-Risk in K.O.-Phase.

        Wenn die nächste Runde innerhalb von rotation_short_rest_days kommt,
        rotiert der klare Favorit wahrscheinlich Starspieler → weniger xG
        für den Favoriten. Wirkt auf:
          • Sieg-Picks des Favoriten → minus (weniger wahrscheinlich)
          • Über-Markt → minus (weniger Tore wegen Rotation)
        """
        from datetime import datetime
        current_iso = context.get("current_match_date")
        next_iso    = context.get("next_match_date")
        if not current_iso or not next_iso:
            return (0.0, "", {})

        try:
            cur_dt  = datetime.fromisoformat(str(current_iso)[:10])
            next_dt = datetime.fromisoformat(str(next_iso)[:10])
        except Exception:
            return (0.0, "", {})

        rest_days = (next_dt - cur_dt).days
        if rest_days < 0:
            return (0.0, "", {})  # nächstes Match liegt vor aktuellem? Daten-Fehler
        if rest_days > self._t["rotation_short_rest_days"]:
            return (0.0, "", {})

        # Klarer Favorit? Pinnacle-implied via pick.odds (Sieg-Markt)
        # Heuristisch: odds < 1.50 = sehr klarer Favorit (~67% implied)
        side = _pick_side(pick.get("market", ""))
        pick_odds = pick.get("odds")
        if not isinstance(pick_odds, (int, float)) or pick_odds <= 0:
            return (0.0, "", {})

        score = 0.0
        notes = []
        meta  = {"rest_days": rest_days}

        # Sieg-Pick auf klaren Favorit → Rotation-Discount
        if side != 0 and pick_odds <= 1.65:
            score += self._t["rotation_pp"]   # negativ (siehe Default -1.5)
            notes.append(f"Nur {rest_days} Tage Pause bis zur nächsten Runde — "
                         f"Favorit schont voraussichtlich Stammspieler")

        # Über-Pick → Rotation reduziert Tore
        if _is_over_market(pick.get("market", "")):
            score += self._t["rotation_pp"]   # auch negativ
            notes.append(f"Nur {rest_days} Tage Pause — Rotation, weniger Tor-Aktion")

        # Unter-Pick → Rotation hilft (umgekehrt)
        if _is_under_market(pick.get("market", "")):
            score -= self._t["rotation_pp"]   # also +1.5
            notes.append(f"Nur {rest_days} Tage Pause — Rotation drückt Tor-Erwartung")

        if abs(score) < 0.01:
            return (0.0, "", meta)

        return (round(score, 2), " · ".join(notes), meta)

    def evaluate(self, pick: dict, context: dict) -> Optional[SignalResult]:
        matchday  = context.get("matchday")
        home_id   = context.get("home_id")
        away_id   = context.get("away_id")
        group_id  = context.get("group_id")
        standings = context.get("standings") or {}

        if not (home_id and away_id):
            return None

        # ── Gruppenphase ─────────────────────────────────────────────────
        if isinstance(matchday, int) and matchday in (2, 3):
            if not group_id:
                return None
            home_state = _compute_qualification_state(home_id, group_id, matchday, standings)
            away_state = _compute_qualification_state(away_id, group_id, matchday, standings)
            if home_state.get("label") == "unknown" or away_state.get("label") == "unknown":
                return None  # Standings noch nicht da

            score_a, ev_a, meta_a = self._component_a(pick, context, home_state, away_state)
            # Bracket-Asymmetrie (B) + R32-Venue-Distanz (C) erst am LETZTEN Gruppenspiel
            # (MD3, 17.06.2026 Lucas-Check). Bei MD2 ist BEIDES Spekulation: die eigene
            # End-Position (MD3 kommt noch) UND der R32-Gegner (aus anderen Gruppen, die
            # erst MD1 gespielt haben → Tabelle ändert sich komplett). „+141 Elo stärker"
            # auf MD1-Tabellen ist Rauschen. Component A (Must-Win) bleibt für MD2+MD3.
            if matchday == 3:
                score_b, ev_b, meta_b = self._component_b(pick, context, home_id, away_id,
                                                          group_id, standings)
                score_c, ev_c, meta_c = self._component_c(pick, context, home_id, away_id,
                                                          group_id, standings)
            else:
                score_b, ev_b, meta_b = 0.0, "", {}
                score_c, ev_c, meta_c = 0.0, "", {}
            total = score_a + score_b + score_c
            evidences = [e for e in (ev_a, ev_b, ev_c) if e]
            confidence = (self._t["confidence_md3"] if matchday == 3
                          else self._t["confidence_md2"])

            if abs(total) < self._t["min_signal_pp"]:
                return None

            return SignalResult(
                score=round(total, 2),
                confidence=round(confidence, 2),
                evidence="🎯 " + " · ".join(evidences) if evidences else f"Incentive {total:+.1f}pp",
                metadata={
                    "matchday":   matchday,
                    "phase":      "group",
                    "components": {"A": meta_a, "B": meta_b, "C": meta_c},
                    "home_state": home_state,
                    "away_state": away_state,
                },
            )

        # ── K.O.-Phase ───────────────────────────────────────────────────
        if isinstance(matchday, str) and matchday.upper() in (
                "R32", "RO32", "R16", "RO16", "QF", "QUARTER", "SF", "SEMI"):
            score_d, ev_d, meta_d = self._component_d(pick, context)
            if abs(score_d) < self._t["min_signal_pp"]:
                return None
            return SignalResult(
                score=round(score_d, 2),
                confidence=round(self._t["confidence_ko"], 2),
                evidence="🎯 " + ev_d if ev_d else f"Incentive {score_d:+.1f}pp",
                metadata={"matchday": matchday, "phase": "ko",
                          "components": {"D": meta_d}},
            )

        # Pre-Tournament / MD1: nichts berechenbar
        return None
