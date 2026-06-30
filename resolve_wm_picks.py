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
import re
import sys
from datetime import datetime, timezone


def _ah_result(market_lower: str, margin: int) -> tuple[str, float]:
    """Asian-Handicap-Auflösung. margin = home_score − away_score.
    Returns (result, stake_factor). stake_factor=0.5 bei Viertel-Linien-Halb-
    Ergebnissen (halber Einsatz gewinnt/verliert, andere Hälfte Push), sonst 1.0.
    Unterstützt ±0.5/0.75/1.0/1.5/2.0. Whole-Lines mit exaktem Deckungs-Gleichstand
    → VOID (Einsatz zurück)."""
    mm = market_lower.replace("−", "-").replace("–", "-").replace(",", ".")
    side = "heim" if ("heim" in mm or "home" in mm) else \
           ("aus" if ("auswärt" in mm or "auswarts" in mm or "away" in mm) else None)
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", mm)
    if side is None or not nums:
        return ("PENDING", 1.0)
    L = abs(float(nums[-1]))

    def leg(line: float) -> int:
        cm = (margin - line) if side == "heim" else (-margin + line)
        return 1 if cm > 0 else (-1 if cm < 0 else 0)

    if round(L * 4) % 2 == 1:           # Viertel-Linie (0.75, 1.25, …) → 2 Halb-Wetten
        s = leg(L - 0.25) + leg(L + 0.25)   # ∈ {-2,-1,0,1,2}
        if s == 2:  return ("WIN", 1.0)
        if s == 1:  return ("WIN", 0.5)     # Half-Win: halber Stake gewinnt, Rest Push
        if s == 0:  return ("VOID", 1.0)
        if s == -1: return ("LOSS", 0.5)    # Half-Loss: halber Stake verliert, Rest Push
        return ("LOSS", 1.0)
    r = leg(L)                          # Halb-/Ganz-Linie
    return ("WIN", 1.0) if r > 0 else (("LOSS", 1.0) if r < 0 else ("VOID", 1.0))


def _apply_ah_stake_factor(p: dict, hs: int, as_: int) -> None:
    """Hängt resultStakeFactor=0.5 an AH-Picks mit Viertel-Linien-Halb-Ergebnis
    (halber Einsatz gewinnt/verliert). P&L-Consumer multiplizieren damit. Sonst clean."""
    m = (p.get("market", "") or "").lower()
    is_ah = "ah" in m and any(k in m for k in ("heim", "auswärt", "auswarts", "home", "away"))
    if not is_ah or p.get("result") not in ("WIN", "LOSS"):
        p.pop("resultStakeFactor", None)
        return
    _, fac = _ah_result(m, hs - as_)
    if fac != 1.0:
        p["resultStakeFactor"] = fac
    else:
        p.pop("resultStakeFactor", None)

BASE     = os.path.dirname(os.path.abspath(__file__))
import cocobet_dataset as D
# Dataset-Modus (Single Source: cocobet_dataset): Liga → resolved die Card-Picks in liga-data.json.
WM_FILE  = str(D.data_file())


def parse_pick_key(pick_key: str):
    """'C-1-BRA-MAR' → ('C', 1, 'BRA', 'MAR'). KO: 'KO-R32-ZAF-CAN' → ('KO', 'R32', 'ZAF', 'CAN')
    (28.06.2026 Fix: KO-Keys haben einen Runden-Token statt Spieltag-Nummer → md bleibt String)."""
    parts = pick_key.split("-")
    if len(parts) < 4:
        return None
    gkey, home, away = parts[0], parts[2], parts[3]
    try:
        md = int(parts[1])
    except (ValueError, IndexError):
        md = parts[1]   # KO-Runden-Token (z.B. "R32") — kein Spieltag
    return gkey, md, home, away


def find_fixture(wm: dict, gkey: str, md, home: str, away: str) -> dict | None:
    """Findet Fixture-Objekt im wm2026-data.json-Schema. KO-Fixtures liegen in wm['koFixtures']
    (eigene Struktur ohne Gruppe/Spieltag) → über Team-Paar matchen (28.06.2026 Fix)."""
    if gkey == "KO":
        for fx in (wm.get("koFixtures") or []):
            if fx.get("home") == home and fx.get("away") == away:
                return fx
        return None
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

    # ── DNB (Draw No Bet) — ZUERST prüfen ────────────────────────────────────
    # FIX 13.06.2026: muss VOR den generischen 1X2-Checks stehen. „DNB:
    # Auswärtsteam" enthält den Substring „auswärt" → wurde sonst von der
    # Auswärtssieg-Regel abgefangen und ein Remis fälschlich als LOSS gewertet,
    # statt als VOID (Einsatz zurück = Cashback). Bei Remis IMMER VOID.
    if "dnb" in m or "draw no bet" in m or "no bet" in m:
        if draw:
            return "VOID"
        if "heim" in m or "home" in m:
            return "WIN" if home_win else "LOSS"
        if "auswärt" in m or "auswarts" in m or "away" in m:
            return "WIN" if away_win else "LOSS"
        return "PENDING"   # DNB ohne erkennbare Seite

    # ── Doppelte Chance ──────────────────────────────────────────────────────
    if "doppelte" in m or "double chance" in m or m in ("1x", "x2", "12"):
        if "1x" in m:
            return "WIN" if (home_win or draw) else "LOSS"
        if "x2" in m:
            return "WIN" if (away_win or draw) else "LOSS"
        if "12" in m:
            return "WIN" if (home_win or away_win) else "LOSS"
        return "PENDING"

    # ── Asian Handicap (13.06.2026) ──────────────────────────────────────────
    # „AH Heim −0.5", „AH Auswärts +1.5" etc. Wird VOR den 1X2-Checks geprüft —
    # enthält zwar „heim"/„auswärt", aber 1X2 nutzt Vollwörter (heimsieg/auswärtssieg),
    # daher keine Kollision. Vorher gab es gar keinen AH-Zweig → AH-Picks blieben PENDING.
    if ("ah" in m and ("heim" in m or "auswärt" in m or "auswarts" in m
                       or "home" in m or "away" in m)):
        return _ah_result(m, home_score - away_score)[0]

    # ── 1X2 / Match Result (präzise Vollwort-Checks) ─────────────────────────
    if "heimsieg" in m or m == "1":
        return "WIN" if home_win else "LOSS"
    if "auswärtssieg" in m or "auswaertssieg" in m or m == "2":
        return "WIN" if away_win else "LOSS"
    if "unentsch" in m or m == "x":
        return "WIN" if draw else "LOSS"

    # Over/Under
    if "über" in m or "uber" in m or "over" in m:
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

    # Unknown market — bleibt unaufgelöst
    return "PENDING"


# ── Refactor 2026-06-06: Konflikt-Filter via pick_constants + pick_helpers ──
# Single Source of Truth für DIRECTION_MAP und Hero-Sort-Logik.
# Backwards-compatible Fallback wenn Module fehlen (zwingender Skip).
try:
    from pick_constants import (
        get_pick_direction as _get_dir,
        are_directions_incompatible as _is_incompatible_dir,
    )
    from pick_helpers import hero_sort_key as _hero_sort_key
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False


def _select_hero_and_mark_conflicts(pick_list: list) -> int:
    """Wählt Hero + markiert konfliktige als VOID + trackingExcluded.

    Konsistent mit UI: Hero-Sort = saferAlt > BET > Edge desc.
    Returns Anzahl der als VOID-Konflikt markierten Picks.
    Mutiert pick_list in-place.
    """
    if not _HELPERS_AVAILABLE:
        return 0   # ohne helpers kein Konflikt-Check (fail-safe)

    live = [p for p in pick_list if p.get("verdict") in ("BET", "ABWÄGEN")]
    if not live:
        return 0

    # Sortierung identisch mit Renderer/Event-Page: saferAlt → BET → Edge desc.
    # Wichtig: garantiert dass der gleiche Pick als Hero ausgewählt wird wie
    # in der UI sichtbar. Sonst würden andere Picks als Konflikt markiert.
    live.sort(key=_hero_sort_key)
    hero = live[0]
    hero_dir = _get_dir(hero.get("market"))
    if not hero_dir:
        return 0   # unknown direction → kein Konflikt-Check möglich

    voids = 0
    for p in live[1:]:
        d = _get_dir(p.get("market"))
        if not d:
            continue
        if _is_incompatible_dir(hero_dir, d) and p.get("result") not in ("WIN", "LOSS", "VOID"):
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
    corrected = 0        # Selbst-Heilung falsch aufgelöster Picks

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
            # NOBET (23.06.2026, Lucas): kein echter Bet → NIE p["result"] setzen (zählt nicht in
            # P&L/Win-Rate/Lernen). Stattdessen rein informatives Schatten-Ergebnis berechnen.
            if p.get("verdict") == "NOBET":
                if p.get("shadowResult") in ("WIN", "LOSS", "VOID"):
                    continue
                _sh = evaluate_pick(p.get("market", ""), hs, as_)
                if _sh in ("WIN", "LOSS", "VOID"):
                    p["shadowResult"] = _sh
                    p["finalScore"]   = f"{hs}-{as_}"
                    p["resolvedAt"]   = now_iso
                continue
            if p.get("result") in ("WIN", "LOSS", "VOID"):
                # Selbst-Heilung (13.06.2026): bereits aufgelöste Picks gegen das
                # finale Ergebnis re-prüfen und korrigieren, falls falsch (z.B. der
                # DNB-Remis→LOSS-Bug). Endstand ist deterministisch, also stabil —
                # kein Flapping. Konflikt-VOIDs (voidReason) bleiben unangetastet.
                if p.get("voidReason"):
                    continue
                fresh = evaluate_pick(p.get("market", ""), hs, as_)
                if fresh in ("WIN", "LOSS", "VOID") and fresh != p["result"]:
                    print(f"   🔧 Korrektur {pick_key} '{p.get('market')}': "
                          f"{p['result']} → {fresh}")
                    p["result"]         = fresh
                    p["finalScore"]     = f"{hs}-{as_}"
                    p["resolvedAt"]     = now_iso
                    p["resultCorrected"] = True
                    _apply_ah_stake_factor(p, hs, as_)
                    corrected += 1
                continue  # bereits aufgelöst

            outcome = evaluate_pick(p.get("market", ""), hs, as_)
            if outcome == "PENDING":
                skipped_unknown += 1
                continue

            p["result"]      = outcome
            p["finalScore"]  = f"{hs}-{as_}"
            p["resolvedAt"]  = now_iso
            _apply_ah_stake_factor(p, hs, as_)
            resolved += 1
            if outcome == "WIN":   win_count += 1
            elif outcome == "LOSS": loss_count += 1
            elif outcome == "VOID": void_count += 1

    # Zurückschreiben — auch wenn nur Konflikt-VOIDs oder Korrekturen
    if resolved > 0 or conflict_voids > 0 or corrected > 0:
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
