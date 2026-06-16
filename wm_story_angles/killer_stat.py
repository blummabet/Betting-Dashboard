#!/usr/bin/env python3
"""
killer_stat.py — Angle: Killer-Stat aus Quali- und Turnier-Daten

Aggregiert "harte Zahlen die zum Story-Hook taugen" aus form/xgStats/upsetScores.
Beispiele:
  · Höchster Ø-Tore-Wert (Belgien 2.8)
  · Niedrigste Gegen-Tor-Rate (Brasilien 0.4)
  · Höchster Travel-Burden-Discount (Marokko/Australien)
  · Größter Heim-vs-Auswärts-Elo-Gap (heutige Spiele)

Jeder Kandidat hat einen klaren Source-Pfad, Verifier prüft Live-Wert.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from wm_story_engine import StoryProposal, Slot, s_from, s_static, s_derived, DATA
from wm_story_angles.match_of_day import TEAM_NAMES, FLAG, _team_name


def _team_form(wm: dict, team_id: str) -> dict:
    return (wm.get("form") or {}).get(team_id, {})


def _all_team_ids(wm: dict) -> list[str]:
    ids = set()
    for gdata in (wm.get("groups") or {}).values():
        for t in gdata.get("teams", []):
            ids.add(t["id"])
    return sorted(ids)


def _generate_avg_scored_proposal(wm: dict) -> StoryProposal | None:
    """Killer-Stat: höchster Ø-Tore-Wert aller WM-Teams."""
    candidates = []
    for tid in _all_team_ids(wm):
        form = _team_form(wm, tid)
        scored = form.get("avgScored")
        games  = form.get("games", 0)
        if isinstance(scored, (int, float)) and games >= 8:
            candidates.append((tid, float(scored), games))
    if not candidates:
        return None
    # Top
    tid, scored, games = max(candidates, key=lambda c: c[1])
    if scored < 2.2:  # nichts beeindruckend genug
        return None
    name = _team_name(tid)
    flag = FLAG.get(tid, "🌍")
    form = _team_form(wm, tid)
    conceded = form.get("avgConceded", 0)

    # Score: 2.0 = 0.3, 2.8 = 0.65, 3.5+ = 0.85
    score = min(0.30 + (scored - 2.0) * 0.40, 0.85)

    return StoryProposal(
        angle_id="killerStat",
        entity_key=f"avgScored:{tid}",
        theme="killer_stat",
        score=score,
        hook_slots={
            "big_number":   s_from(
                f"{scored:.1f}", source=f"form.{tid}.avgScored",
                source_file="wm2026-data.json", raw=scored,
            ),
            "sub_title":    s_static(f"Tore pro Spiel · {name}"),
            "hook_line_1":  s_static(f'<span class="acc">{name}</span> {flag} trifft'),
            "hook_line_2":  s_static('<span class="yellow">jeden Gegner.</span>'),
            "mystery_question": s_static("Wer stoppt diese Maschine?"),
            "highlight_fact": s_derived(
                f"Ø {scored:.1f} Tore in {games} Spielen — Gegen Ø {conceded:.1f}",
                sources=[f"form.{tid}.avgScored", f"form.{tid}.games",
                         f"form.{tid}.avgConceded"],
            ),
        },
        info_slots={
            "flag":      s_static(flag),
            "name":      s_static(name),
            "role_line": s_static(f"Ø {scored:.1f} Tore/Spiel · {games} Spiele Datenbasis"),
            "stat1_val": s_from(f"{scored:.1f}", source=f"form.{tid}.avgScored", raw=scored),
            "stat1_lbl": s_static("Tore Ø"),
            "stat2_val": s_from(f"{conceded:.1f}", source=f"form.{tid}.avgConceded", raw=conceded),
            "stat2_lbl": s_static("Gegen Ø"),
            "stat3_val": s_from(f"{games}", source=f"form.{tid}.games", raw=games),
            "stat3_lbl": s_static("Spiele"),
            "closing_line": s_static(
                f"<strong>Höchster Tor-Schnitt</strong> aller {len(candidates)} qualifizierten WM-Teams. "
                f"Form-Datenbasis: {games} Spiele."
            ),
            "quote_line":   s_static(f'Tor-Maschine ohne <span class="acc">Stopper</span> in Sicht. ⚽'),
            "data_source":  s_static("Daten: WM-Quali + Tests 2024/25"),
        },
        reason=f"avgScored={scored:.1f} ({games} games) — höchster aller {len(candidates)} Teams",
    )


def _generate_defensive_wall(wm: dict) -> StoryProposal | None:
    """Killer-Stat: niedrigster avgConceded Wert (defensive Wall)."""
    candidates = []
    for tid in _all_team_ids(wm):
        form = _team_form(wm, tid)
        conceded = form.get("avgConceded")
        games    = form.get("games", 0)
        if isinstance(conceded, (int, float)) and games >= 8:
            candidates.append((tid, float(conceded), games))
    if not candidates:
        return None
    tid, conceded, games = min(candidates, key=lambda c: c[1])
    if conceded > 0.6:  # nicht beeindruckend genug
        return None

    name  = _team_name(tid)
    flag  = FLAG.get(tid, "🌍")
    form  = _team_form(wm, tid)
    scored = form.get("avgScored", 0)
    over25_rate = form.get("over25Rate", 0)

    # Score: 0.5 conceded → 0.4, 0.3 → 0.7, 0.1 → 0.9
    score = min(0.40 + (0.6 - conceded) * 1.0, 0.90)

    return StoryProposal(
        angle_id="killerStat",
        entity_key=f"defensiveWall:{tid}",
        theme="killer_stat",
        score=score,
        hook_slots={
            "big_number":   s_from(
                f"{conceded:.1f}", source=f"form.{tid}.avgConceded",
                source_file="wm2026-data.json", raw=conceded,
            ),
            "sub_title":    s_static(f"Gegentore pro Spiel · {name}"),
            "hook_line_1":  s_static(f'<span class="acc">{name}</span> {flag} kassiert'),
            "hook_line_2":  s_static('<span class="yellow">fast keine Tore.</span>'),
            "mystery_question": s_static("Wer durchbricht die Mauer?"),
            "highlight_fact": s_derived(
                f"{conceded:.1f} Tore/Spiel kassiert — Ø {scored:.1f} eigene",
                sources=[f"form.{tid}.avgConceded", f"form.{tid}.avgScored"],
            ),
        },
        info_slots={
            "flag":      s_static(flag),
            "name":      s_static(name),
            "role_line": s_static(f"Bestes Defensivteam laut Form · {games} Spiele Datenbasis"),
            "stat1_val": s_from(f"{conceded:.1f}", source=f"form.{tid}.avgConceded", raw=conceded),
            "stat1_lbl": s_static("Gegen Ø"),
            "stat2_val": s_from(f"{scored:.1f}", source=f"form.{tid}.avgScored", raw=scored),
            "stat2_lbl": s_static("Tore Ø"),
            "stat3_val": s_from(
                f"{int(round((over25_rate or 0)*100))}%",
                source=f"form.{tid}.over25Rate",
                raw=over25_rate,
            ),
            "stat3_lbl": s_static("3+ Tore"),
            "closing_line": s_static(
                f"<strong>Beste Defensive</strong> aller {len(candidates)} qualifizierten Teams. "
                f"Ø {conceded:.1f} Tore über {games} Spiele."
            ),
            "quote_line":   s_static(f'Wer hier <span class="acc">zwei Tore</span> macht, gewinnt. 🛡️'),
            "data_source":  s_static("Daten: WM-Quali + Tests 2024/25"),
        },
        reason=f"avgConceded={conceded:.1f} ({games} games) — niedrigster aller Teams",
    )


def _generate_xg_outlier(wm: dict) -> StoryProposal | None:
    """Killer-Stat: größter xG-Discount durch Travel-Burden (z.B. -18% Marokko)."""
    xg_stats = wm.get("xgStats") or {}
    candidates = []
    for tid, xg in xg_stats.items():
        if not isinstance(xg, dict):
            continue
        discount = xg.get("travelDiscount") or xg.get("travelXgMod")
        if isinstance(discount, (int, float)) and discount < -0.10:
            candidates.append((tid, float(discount)))
    if not candidates:
        return None
    tid, discount = min(candidates, key=lambda c: c[1])
    name = _team_name(tid)
    flag = FLAG.get(tid, "🌍")
    discount_pct = int(round(abs(discount) * 100))
    if discount_pct < 12:
        return None

    score = min(0.35 + (discount_pct - 10) * 0.03, 0.75)

    return StoryProposal(
        angle_id="killerStat",
        entity_key=f"travelXg:{tid}",
        theme="killer_stat",
        score=score,
        hook_slots={
            "big_number":   s_derived(
                f"-{discount_pct}%",
                sources=[f"xgStats.{tid}.travelDiscount"],
            ),
            "sub_title":    s_static(f"xG-Verlust durch Anreise · {name}"),
            "hook_line_1":  s_static(f'<span class="acc">{name}</span> {flag} verliert'),
            "hook_line_2":  s_static('vor jedem Spiel <span class="yellow">Energie.</span>'),
            "mystery_question": s_static("Was macht das mit den Beinen?"),
            "highlight_fact": s_derived(
                f"Reise-Last kostet {name} rund {discount_pct}% Tor-Gefahr",
                sources=[f"xgStats.{tid}.travelDiscount"],
            ),
        },
        info_slots={
            "flag":      s_static(flag),
            "name":      s_static(name),
            "role_line": s_static(f"WM-Reise belastet die Tor-Gefahr deutlich"),
            "stat1_val": s_derived(f"-{discount_pct}%", sources=[f"xgStats.{tid}.travelDiscount"]),
            "stat1_lbl": s_static("Tor-Gefahr"),
            "stat2_val": s_static("Anreise"),
            "stat2_lbl": s_static("Ursache"),
            "stat3_val": s_static("✈️"),
            "stat3_lbl": s_static("Reise-Faktor"),
            # TikTok-safe (16.06.2026): Bookie/Markt-Quoten/Edge raus → reine Reise-Story.
            "closing_line": s_static(
                f"<strong>Tausende Kilometer</strong> zwischen Trainingslager und Spielort "
                f"zehren an der Frische — und damit an den Toren."
            ),
            "quote_line":   s_static(f'Die Reise spielt <span class="acc">immer mit.</span> ✈️'),
            "data_source":  s_static("Daten: Reise-Analyse (Trainingslager → Spielort)"),
        },
        reason=f"travelDiscount={discount:.2f} ({discount_pct}%)",
    )


def generate(today_iso: str | None = None) -> list[StoryProposal]:
    """Erzeugt alle Killer-Stat-Kandidaten. Master-Selector wählt highest score."""
    today_iso = today_iso or datetime.now(timezone.utc).isoformat()
    wm = DATA.get("wm2026-data.json")
    if not wm:
        return []
    proposals: list[StoryProposal] = []
    for gen_fn in (_generate_avg_scored_proposal,
                   _generate_defensive_wall,
                   _generate_xg_outlier):
        try:
            p = gen_fn(wm)
            if p:
                proposals.append(p)
        except Exception as e:
            print(f"  ⚠️  killer_stat.{gen_fn.__name__} fehlgeschlagen: {e}")
    return proposals
