#!/usr/bin/env python3
"""
match_of_day.py — Angle: Spiel des Tages

Wählt aus heutigen Fixtures das spannendste Spiel basierend auf:
  · Edge-Stärke (höchster Verdict=BET Pick)
  · Konfidenz (dataQuality + #Daten-Signale)
  · Story-Appeal (Elo-Diff klein = enger; oder großer Underdog mit Quote = Drama)
  · H2H-Vorgeschichte (vorhanden + signifikant)

Funktioniert SOFORT (vor 11.6.) weil alle Datenquellen ständig befüllt sind.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from wm_story_engine import StoryProposal, Slot, s_from, s_static, s_derived, DATA


TEAM_NAMES = {
    "ARG": "Argentinien", "BRA": "Brasilien", "FRA": "Frankreich", "DEU": "Deutschland", "GER": "Deutschland",
    "ESP": "Spanien", "ITA": "Italien", "POR": "Portugal", "NLD": "Niederlande", "BEL": "Belgien",
    "ENG": "England", "URY": "Uruguay", "CRO": "Kroatien", "MAR": "Marokko", "MEX": "Mexiko",
    "USA": "USA", "CAN": "Kanada", "AUT": "Österreich", "DZA": "Algerien", "JOR": "Jordanien",
    "JPN": "Japan", "KOR": "Südkorea", "AUS": "Australien", "NOR": "Norwegen", "SEN": "Senegal",
    "EGY": "Ägypten", "CMR": "Kamerun", "TUN": "Tunesien", "GHA": "Ghana", "CIV": "Elfenbeinküste",
    "ECU": "Ecuador", "COL": "Kolumbien", "PER": "Peru", "PRY": "Paraguay", "VEN": "Venezuela",
    "CHL": "Chile", "BOL": "Bolivien", "IRQ": "Irak", "IRN": "Iran", "SAU": "Saudi-Arabien",
    "QAT": "Katar", "CHE": "Schweiz", "SUI": "Schweiz", "POL": "Polen", "CZE": "Tschechien",
    "TUR": "Türkei", "UKR": "Ukraine", "SCO": "Schottland", "WAL": "Wales", "DNK": "Dänemark",
    "SRB": "Serbien", "ZAF": "Südafrika", "NZL": "Neuseeland", "PAN": "Panama", "CRC": "Costa Rica",
    "HND": "Honduras", "SLV": "El Salvador", "CPV": "Kap Verde",
}

FLAG = {
    "ARG": "🇦🇷", "BRA": "🇧🇷", "FRA": "🇫🇷", "DEU": "🇩🇪", "GER": "🇩🇪", "ESP": "🇪🇸",
    "ITA": "🇮🇹", "POR": "🇵🇹", "NLD": "🇳🇱", "BEL": "🇧🇪", "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "URY": "🇺🇾",
    "CRO": "🇭🇷", "MAR": "🇲🇦", "MEX": "🇲🇽", "USA": "🇺🇸", "CAN": "🇨🇦", "AUT": "🇦🇹",
    "DZA": "🇩🇿", "JOR": "🇯🇴", "JPN": "🇯🇵", "KOR": "🇰🇷", "AUS": "🇦🇺", "NOR": "🇳🇴",
    "SEN": "🇸🇳", "EGY": "🇪🇬", "CMR": "🇨🇲", "TUN": "🇹🇳", "GHA": "🇬🇭", "CIV": "🇨🇮",
    "ECU": "🇪🇨", "COL": "🇨🇴", "PER": "🇵🇪", "PRY": "🇵🇾", "VEN": "🇻🇪", "CHL": "🇨🇱",
    "IRQ": "🇮🇶", "IRN": "🇮🇷", "SAU": "🇸🇦", "QAT": "🇶🇦", "CHE": "🇨🇭", "SUI": "🇨🇭",
    "POL": "🇵🇱", "TUR": "🇹🇷", "UKR": "🇺🇦", "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "WAL": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "DNK": "🇩🇰",
    "SRB": "🇷🇸", "ZAF": "🇿🇦", "NZL": "🇳🇿", "PAN": "🇵🇦", "CRC": "🇨🇷", "HND": "🇭🇳",
    "CPV": "🇨🇻",
}


def _team_name(tid: str) -> str:
    return TEAM_NAMES.get(tid, tid)


def _all_fixtures(wm: dict) -> list[tuple[str, dict, dict]]:
    """Returns [(gkey, fixture, group_dict), ...] für alle Fixtures."""
    out = []
    for gkey, gdata in (wm.get("groups") or {}).items():
        for fx in gdata.get("fixtures", []):
            out.append((gkey, fx, gdata))
    return out


def _todays_fixtures(wm: dict, today_iso: str) -> list[tuple[str, dict, int]]:
    """Returns [(gkey, fixture, fixture_index_in_group), ...] für heute kommende Spiele."""
    today_date = today_iso[:10]
    out = []
    for gkey, gdata in (wm.get("groups") or {}).items():
        for idx, fx in enumerate(gdata.get("fixtures", [])):
            ko = (fx.get("kickoff") or "")[:10]
            if ko == today_date:
                out.append((gkey, fx, idx))
    return out


def _fixture_picks(wm: dict, gkey: str, md: int, home: str, away: str) -> list[dict]:
    """Returns Picks für einen Match. Key-Format: 'C-1-BRA-MAR'."""
    pk = f"{gkey}-{md}-{home}-{away}"
    plist = (wm.get("picks") or {}).get(pk, [])
    return [p for p in plist if isinstance(p, dict)]


def _best_bet_pick(picks: list[dict]) -> dict | None:
    """Höchste Edge unter den BET/ABWÄGEN-Picks."""
    cands = [p for p in picks if p.get("verdict") in ("BET", "ABWÄGEN")]
    if not cands:
        return None
    return max(cands, key=lambda p: float(p.get("edgePP") or 0))


def _theme_for_pick(p: dict | None, elo_diff: float) -> str:
    """Theme-Auswahl basierend auf Pick-Stärke und Spielcharakter."""
    if p is None:
        return "hidden_gem"
    edge = float(p.get("edgePP") or 0)
    if edge >= 6:
        return "killer_stat"          # Großer Edge = Killer-Insight
    if abs(elo_diff) < 80:
        return "naechste_aera" if "Heim" in (p.get("market") or "") else "hidden_gem"
    if elo_diff < -80 and "Heim" in (p.get("market") or ""):
        return "hidden_gem"           # Heimsieg-Pick auf Underdog
    return "hidden_gem"


def _score_proposal(fx: dict, pick: dict | None, gdata: dict, wm: dict) -> tuple[float, str]:
    """0-1 Score + Begründung."""
    score = 0.0
    reasons = []

    # Edge-Komponente (0-0.5)
    if pick:
        edge = float(pick.get("edgePP") or 0)
        edge_score = min(edge / 12.0, 0.50)   # 12pp Edge = max
        score += edge_score
        reasons.append(f"Edge {edge:.1f}pp → {edge_score:.2f}")

        # Daten-Qualität-Bonus (0-0.15)
        dq = pick.get("dataQuality", "low")
        dq_score = {"full": 0.15, "partial": 0.08, "low": 0.02, "elo_only": 0.0}.get(dq, 0)
        score += dq_score
        if dq_score > 0:
            reasons.append(f"dataQ={dq} → +{dq_score:.2f}")

    # Story-Appeal: Elo-Diff klein = engeres Spiel = mehr Drama (0-0.2)
    teams = {t["id"]: t for t in gdata.get("teams", [])}
    home_id = fx.get("home")
    away_id = fx.get("away")
    elo_h = (teams.get(home_id) or {}).get("elo")
    elo_a = (teams.get(away_id) or {}).get("elo")
    elo_diff = 0
    if isinstance(elo_h, (int, float)) and isinstance(elo_a, (int, float)):
        elo_diff = elo_h - elo_a
        elo_appeal = max(0, 0.20 - abs(elo_diff) / 1000)
        score += elo_appeal
        if elo_appeal > 0.05:
            reasons.append(f"Elo-Diff {elo_diff:.0f} → drama +{elo_appeal:.2f}")

    # H2H-Bonus: vorhanden + ≥3 Spiele (0-0.1)
    h2h = (wm.get("h2h") or {})
    h2h_obj = h2h.get(f"{home_id}-{away_id}") or h2h.get(f"{away_id}-{home_id}") or {}
    h2h_games = h2h_obj.get("games", 0)
    if h2h_games >= 3:
        h2h_score = min(h2h_games / 50.0, 0.10)
        score += h2h_score
        reasons.append(f"H2H {h2h_games} Spiele → +{h2h_score:.2f}")

    return min(score, 1.0), " · ".join(reasons), elo_diff


def generate(today_iso: str | None = None) -> list[StoryProposal]:
    """Erzeugt Match-of-Day Proposals für heute. Returns leere Liste wenn keine Fixtures."""
    today_iso = today_iso or datetime.now(timezone.utc).isoformat()
    wm = DATA.get("wm2026-data.json")
    if not wm:
        return []

    todays = _todays_fixtures(wm, today_iso)
    # Falls heute keine Spiele: nimm nächsten Tag mit Fixtures (max 2 Tage voraus)
    if not todays:
        today_dt = datetime.fromisoformat(today_iso.replace("Z", "+00:00"))
        for d_ahead in (1, 2):
            target = (today_dt + timedelta(days=d_ahead)).date().isoformat()
            todays = _todays_fixtures(wm, target)
            if todays:
                break

    proposals: list[StoryProposal] = []

    for gkey, fx, _fx_idx in todays:
        home = fx.get("home")
        away = fx.get("away")
        md   = fx.get("matchday", 0)
        if not (home and away and md):
            continue

        picks = _fixture_picks(wm, gkey, md, home, away)
        best  = _best_bet_pick(picks)
        teams = {t["id"]: t for t in next(
            (g for k, g in wm["groups"].items() if k == gkey), {}
        ).get("teams", [])}
        gdata = wm["groups"][gkey]

        score, reason, elo_diff = _score_proposal(fx, best, gdata, wm)
        theme = _theme_for_pick(best, elo_diff)

        # ── Slot-Aufbau ──
        elo_h = (teams.get(home) or {}).get("elo") or 1500
        elo_a = (teams.get(away) or {}).get("elo") or 1500

        # Hook-Slots
        hook_slots: dict[str, Slot] = {
            "big_number":   s_static(f"{int(elo_h)}"),
            "sub_title":    s_static(f"Elo · {_team_name(home)}"),
            "hook_line_1":  s_static(f"{_team_name(home)} {FLAG.get(home,'')}"),
            "hook_line_2":  s_static(f'gegen <span class="acc">{_team_name(away)}</span> {FLAG.get(away,"")}'),
            "mystery_question": s_static(
                f"Wer setzt sich heute durch?" if abs(elo_diff) < 100
                else f"Schafft {_team_name(away)} die Überraschung?"
            ),
        }
        if best:
            edge_val = float(best.get("edgePP") or 0)
            hook_slots["highlight_fact"] = s_static(
                f"{best.get('market', '?')} · Edge {edge_val:+.1f}pp"
            )
        else:
            # H2H als Highlight wenn kein Pick
            h2h = (wm.get("h2h") or {})
            h2h_obj = h2h.get(f"{home}-{away}") or h2h.get(f"{away}-{home}") or {}
            if h2h_obj.get("games"):
                hook_slots["highlight_fact"] = s_from(
                    f"H2H: {h2h_obj.get('games')} Spiele · letzte: {h2h_obj.get('lastResult', '?')}",
                    source=f"h2h.{home}-{away}.games",
                    source_file="wm2026-data.json",
                    raw=h2h_obj.get("games"),
                )
            else:
                hook_slots["highlight_fact"] = s_static(f"Elo-Diff: {elo_diff:+.0f}")

        # Info-Slots
        kickoff = (fx.get("kickoff") or "")[:16].replace("T", " ")
        info_slots: dict[str, Slot] = {
            "flag":      s_static(FLAG.get(home, "🌍") + " vs " + FLAG.get(away, "🌍")),
            "name":      s_static(f"{_team_name(home)} vs {_team_name(away)}"),
            "role_line": s_static(f"Gruppe {gkey} · Anpfiff: {kickoff} UTC"),
            "stat1_val": s_from(
                f"{int(elo_h)}",
                source=f"groups.{gkey}.teams",   # Listen-Index unbestimmt, daher Plausibilität
                raw=int(elo_h),
            ),
            "stat1_lbl": s_static(f"Elo {home}"),
            "stat2_val": s_from(
                f"{int(elo_a)}",
                source=f"groups.{gkey}.teams",
                raw=int(elo_a),
            ),
            "stat2_lbl": s_static(f"Elo {away}"),
        }
        if best:
            edge_val = float(best.get("edgePP") or 0)
            info_slots["stat3_val"] = s_static(f"{edge_val:+.1f}pp")
            info_slots["stat3_lbl"] = s_static("Edge")
            info_slots["closing_line"] = s_static(
                f"<strong>Pick: {best.get('market', '?')}</strong> @ {best.get('odds', '?')} "
                f"— Modell sieht {best.get('modelOdds', '?')}."
            )
            info_slots["quote_line"] = s_static(
                f'Edge sitzt. <span class="acc">Heute Anpfiff.</span> ⚡'
            )
        else:
            info_slots["stat3_val"] = s_static("—")
            info_slots["stat3_lbl"] = s_static("kein Edge")
            info_slots["closing_line"] = s_static(
                f"Spannendes Gruppenspiel ohne klaren Pick — beide Teams in vergleichbarer Form."
            )
            info_slots["quote_line"] = s_static(
                f'<span class="acc">Heute Anpfiff.</span> ⚡'
            )

        info_slots["data_source"] = s_static("Daten: WM 2026 Live-Pipeline")

        proposals.append(StoryProposal(
            angle_id="matchOfDay",
            entity_key=f"{gkey}-{md}-{home}-{away}",
            theme=theme,
            score=score,
            hook_slots=hook_slots,
            info_slots=info_slots,
            reason=reason,
        ))

    return proposals
