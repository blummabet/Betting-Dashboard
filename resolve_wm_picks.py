#!/usr/bin/env python3
"""
resolve_wm_picks.py — WM 2026 Pick-Resolver für Confidence-Backtest
====================================================================

Liest jeden generierten Pick aus wm2026-data.json["picks"] und markiert
ihn als WIN/LOSS/VOID basierend auf dem Spielergebnis (fx.result).

Anders als resolve_wm_results.py (das nur platzierte Bets auflöst) trackt
das hier ALLE generierten Picks — auch unplatzierte "Schatten-Picks".

Diese Resolved-Picks füttern compute_pick_confidence.py das pro Cluster
(Edge-Range × dataQuality × Angle-Typ × Markt-Typ) historische Hit-Rates
berechnet.

Run: python3 resolve_wm_picks.py
Cron: integration in fetch-wm-data.yml nach generate_wm_picks.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

BASE     = os.path.dirname(os.path.abspath(__file__))
WM_FILE  = os.path.join(BASE, "wm2026-data.json")


def parse_pick_key(pick_key: str) -> tuple[str, int, str, str] | None:
    """'C-1-BRA-MAR' → ('C', 1, 'BRA', 'MAR')"""
    parts = pick_key.split("-")
    if len(parts) < 4:
        return None
    try:
        gkey = parts[0]
        md   = int(parts[1])
        home = parts[2]
        away = parts[3]
        return gkey, md, home, away
    except (ValueError, IndexError):
        return None


def find_fixture(wm: dict, gkey: str, md: int, home: str, away: str) -> dict | None:
    """Findet Fixture-Objekt im wm2026-data.json-Schema."""
    g = (wm.get("groups") or {}).get(gkey, {})
    for fx in g.get("fixtures", []):
        if fx.get("home") == home and fx.get("away") == away and fx.get("matchday") == md:
            return fx
    return None


def is_finished(fx: dict) -> bool:
    """Prüft ob Spiel komplett gespielt + Ergebnis verfügbar."""
    r = fx.get("result") or {}
    status = (r.get("status") or "").upper()
    if status not in ("FT", "AET", "PEN", "FINISHED", "FULL_TIME"):
        return False
    return r.get("home_score") is not None and r.get("away_score") is not None


def evaluate_pick(market: str, home_score: int, away_score: int) -> str:
    """
    Returns 'WIN' / 'LOSS' / 'VOID' für gegebene Markt-Label + Score.

    Unterstützte Märkte (alle deutsch wie generate_wm_picks.py sie schreibt):
      Heimsieg, Auswärtssieg, Unentschieden
      Über 2.5 Tore, Unter 2.5 Tore, Über 1.5 Tore, Unter 3.5 Tore
      Beide Teams treffen — Ja / Nein
      DNB: Heimteam, DNB: Auswärtsteam
      Doppelte Chance: 1X, X2, 12
    """
    total = home_score + away_score
    home_win = home_score > away_score
    away_win = away_score > home_score
    draw     = home_score == away_score
    btts     = home_score > 0 and away_score > 0

    m = (market or "").lower()

    # 1X2 / Match Result
    if "heimsieg" in m or m == "1":
        return "WIN" if home_win else "LOSS"
    if "auswärt" in m or m == "2":
        return "WIN" if away_win else "LOSS"
    if "unentsch" in m or m == "x":
        return "WIN" if draw else "LOSS"

    # Doppelte Chance
    if "1x" in m or "doppelte" in m and "1x" in m:
        return "WIN" if (home_win or draw) else "LOSS"
    if "x2" in m or ("doppelte" in m and "x2" in m):
        return "WIN" if (away_win or draw) else "LOSS"
    if "12" in m or ("doppelte" in m and "12" in m):
        return "WIN" if (home_win or away_win) else "LOSS"

    # Over/Under
    if "über" in m or "over" in m:
        for thr in (0.5, 1.5, 2.5, 3.5, 4.5):
            if str(thr) in m:
                return "WIN" if total > thr else "LOSS"
        if "2.5" in m or "2,5" in m:
            return "WIN" if total > 2.5 else "LOSS"
    if "unter" in m or "under" in m:
        for thr in (0.5, 1.5, 2.5, 3.5, 4.5):
            if str(thr) in m:
                return "WIN" if total < thr else "LOSS"

    # BTTS
    if "beide teams treffen" in m or "btts" in m:
        if "nein" in m or "no" in m:
            return "WIN" if not btts else "LOSS"
        return "WIN" if btts else "LOSS"

    # DNB
    if "dnb" in m:
        if "heim" in m:
            if draw:    return "VOID"
            if home_win: return "WIN"
            return "LOSS"
        if "auswärt" in m:
            if draw:    return "VOID"
            if away_win: return "WIN"
            return "LOSS"

    # Unknown market — bleibt unaufgelöst
    return "PENDING"


# AUDIT-Fix 06.06.2026: Cross-Market-Konflikt-Filter fürs Tracking
# Problem: Bei CAN-BIH werden DNB Aus + AH Heim −0.5 gleichzeitig getrackt.
# Wir wetten aber nur EINEN Pick — das andere "tracking" verfälscht die Stats.
# Lösung: Nur Hero-Pick (höchste Edge) zählt als "echter" Pick.
# Sekundäre Picks die DIREKTIONAL mit dem Hero im Konflikt stehen → VOID
# (mit explizitem reason). Stat-Engine zählt sie nicht als Win/Loss.
DIRECTION_MAP = {
    "Heimsieg":               "homeStrong",
    "Doppelte Chance — 1X":   "homeBias",
    "Doppelte Chance — 12":   "decisive",
    "AH Heim −0.5":           "homeStrong",
    "AH Heim −0.75":          "homeStrong",
    "AH Heim −1.0":           "homeStrong",
    "DNB: Heimteam":          "homeStrong",
    "Auswärtssieg":           "awayStrong",
    "Doppelte Chance — X2":   "awayBias",
    "AH Auswärts +0.5":       "awayStrong",
    "AH Auswärts +0.75":      "awayStrong",
    "AH Auswärts +1.0":       "awayStrong",
    "DNB: Auswärtsteam":      "awayStrong",
    "Unentschieden":          "drawOnly",
    "Über 1.5 Tore":          "over",
    "Über 2.5 Tore":          "over",
    "Über 3.5 Tore":          "over",
    "Unter 1.5 Tore":         "under",
    "Unter 2.5 Tore":         "under",
    "Unter 3.5 Tore":         "under",
    "Beide Teams treffen":    "over",
    "Beide Teams treffen — Ja": "over",
    "Beide Teams treffen — Nein": "under",
}
INCOMPATIBLE = {
    ("homeStrong", "awayStrong"), ("homeStrong", "awayBias"), ("homeStrong", "drawOnly"),
    ("homeBias",   "awayStrong"), ("awayStrong", "drawOnly"), ("awayBias",   "homeStrong"),
    ("decisive",   "drawOnly"),   ("over",       "under"),
}
def _is_incompatible(d1: str, d2: str) -> bool:
    return (d1, d2) in INCOMPATIBLE or (d2, d1) in INCOMPATIBLE


def _select_hero_and_mark_conflicts(pick_list: list) -> int:
    """Wählt Hero (höchste Edge unter BET/ABWÄGEN) + markiert konfliktige als VOID.

    Returns Anzahl der als VOID-Konflikt markierten Picks.
    Mutiert pick_list in-place (setzt result + trackingExcluded für Konflikt-Picks).
    """
    live = [p for p in pick_list if p.get("verdict") in ("BET", "ABWÄGEN")]
    # Sortierung: BET vor ABWÄGEN, dann Edge desc
    live.sort(key=lambda p: (
        0 if p.get("verdict") == "BET" else 1,
        -float(p.get("edgePP") or 0),
    ))
    if not live:
        return 0
    hero = live[0]
    hero_dir = DIRECTION_MAP.get(hero.get("market"))
    if not hero_dir:
        return 0   # unknown direction → kein Konflikt-Check möglich

    voids = 0
    for p in live[1:]:
        d = DIRECTION_MAP.get(p.get("market"))
        if not d:
            continue
        if _is_incompatible(hero_dir, d) and p.get("result") not in ("WIN", "LOSS", "VOID"):
            p["result"]            = "VOID"
            p["voidReason"]        = (
                f"Cross-Market-Konflikt mit Top-Pick '{hero.get('market')}' "
                f"({hero_dir} vs {d}) — wird nicht real gewettet, daher nicht getrackt"
            )
            p["trackingExcluded"]  = True
            voids += 1
    return voids


def main():
    if not os.path.exists(WM_FILE):
        print(f"❌ {WM_FILE} fehlt")
        sys.exit(1)

    with open(WM_FILE, encoding="utf-8") as f:
        wm = json.load(f)

    picks = wm.get("picks", {})
    if not picks:
        print("ℹ️  Keine Picks zu auflösen.")
        return

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolved = 0
    skipped_pending = 0
    skipped_unknown = 0
    win_count = loss_count = void_count = 0
    conflict_voids = 0   # Audit-Fix: getrennt zählen

    # ── Pass 1: Konflikt-VOIDs markieren (vor Spielende — sobald Picks generiert) ──
    for pick_key, pick_list in picks.items():
        if not isinstance(pick_list, list):
            continue
        conflict_voids += _select_hero_and_mark_conflicts(pick_list)

    # ── Pass 2: Spielergebnisse auflösen ──
    for pick_key, pick_list in picks.items():
        if not isinstance(pick_list, list):
            continue

        parsed = parse_pick_key(pick_key)
        if not parsed:
            continue
        gkey, md, home, away = parsed
        fx = find_fixture(wm, gkey, md, home, away)
        if not fx:
            continue

        if not is_finished(fx):
            continue  # Spiel noch nicht beendet

        r = fx["result"]
        hs, as_ = r["home_score"], r["away_score"]

        for p in pick_list:
            if p.get("result") in ("WIN", "LOSS", "VOID"):
                continue  # bereits aufgelöst (inkl. Konflikt-VOID)

            outcome = evaluate_pick(p.get("market", ""), hs, as_)
            if outcome == "PENDING":
                skipped_unknown += 1
                continue

            p["result"]      = outcome
            p["finalScore"]  = f"{hs}-{as_}"
            p["resolvedAt"]  = now_iso
            resolved += 1
            if outcome == "WIN":   win_count += 1
            elif outcome == "LOSS": loss_count += 1
            elif outcome == "VOID": void_count += 1

    # Zurückschreiben — auch wenn nur Konflikt-VOIDs ohne Result-Resolves
    if resolved > 0 or conflict_voids > 0:
        with open(WM_FILE, "w", encoding="utf-8") as f:
            json.dump(wm, f, ensure_ascii=False, indent=2)

    total_resolved_all = sum(
        1 for v in picks.values() if isinstance(v, list)
        for p in v if p.get("result") in ("WIN", "LOSS", "VOID")
    )
    total_picks_all = sum(1 for v in picks.values() if isinstance(v, list) for _ in v)
    excluded_count = sum(
        1 for v in picks.values() if isinstance(v, list)
        for p in v if p.get("trackingExcluded")
    )

    print(f"=== resolve_wm_picks.py ===")
    print(f"  Neu aufgelöst: {resolved} (Win {win_count} · Loss {loss_count} · Void {void_count})")
    print(f"  Konflikt-VOIDs neu markiert: {conflict_voids} (nicht real wettbar → von Tracking ausgeschlossen)")
    print(f"  Übersprungen (unbekannter Markt): {skipped_unknown}")
    print(f"  Gesamt aufgelöst: {total_resolved_all}/{total_picks_all}")
    print(f"  Davon Tracking-excluded: {excluded_count}")


if __name__ == "__main__":
    main()
