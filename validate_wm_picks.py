#!/usr/bin/env python3
"""
validate_wm_picks.py — Sanity-Checks für WM-Picks

Läuft nach generate_wm_picks.py im Workflow.
Schreibt pick_validation_report.json:
{
  "lastRun": ISO,
  "stats":   {"total": ..., "errors": ..., "warnings": ..., "ok": ...},
  "issues":  [{matchKey, market, level, code, message, pickSnapshot}, ...]
}

Severity-Level:
  • error   — Pick mathematisch unmöglich oder Datenintegrität verletzt
  • warning — Verdächtig, Pick sollte überprüft werden, aber kein definitiver Bug
  • info    — Hinweis, kein Eingriff nötig

Check-Codes:
  E_EDGE_MATH        — modelOdds > marketOdds aber edgePP>0 (Vorzeichen falsch)
  E_VERDICT_NO_EDGE  — verdict=BET aber edgePP<3 (Filter durchgerutscht)
  E_ORPHAN_MATCH     — Pick existiert aber Match nicht in fixtures
  E_MISSING_FIELD    — Pflichtfeld fehlt (market, odds, verdict, modelOdds)
  W_UNDERDOG_LEAK    — Elo-Gap >200 und BET (Underdog-Filter sollte das fangen)
  W_DATAQ_OVERSTATED — dataQuality=full aber H2H/Form unvollständig
  W_NEGATIVE_CLV     — verdict=BET aber clvPP<-3 (Markt deutlich gegen uns)
  W_ODDS_OUTLIER     — Quote >12 (kein liquider Markt — sollte gefiltert sein)
  W_HUGE_EDGE        — edgePP>30 (verdächtig — inverted odds?)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
REPORT_FILE = BASE / "pick_validation_report.json"

UNDERDOG_ELO_SOFT = 100
UNDERDOG_ELO_HARD = 200
BET_MIN_EDGE      = 3        # BET sollte ≥3pp Edge haben (sonst durchgerutscht)
ODDS_OUTLIER_MIN  = 12.0     # >12 = vermutlich kein Markt
HUGE_EDGE_PP      = 30       # >30pp Edge = verdächtig (Quoten invertiert?)
NEG_CLV_THRESHOLD = -3       # <-3pp CLV bei BET = Markt deutlich gegen uns


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add(issues, mk, market, level, code, message, snap):
    issues.append({
        "matchKey": mk,
        "market":   market,
        "level":    level,
        "code":     code,
        "message":  message,
        "pickSnapshot": {
            "verdict": snap.get("verdict"),
            "odds":    snap.get("odds"),
            "modelOdds": snap.get("modelOdds"),
            "edgePP":  snap.get("edgePP"),
            "clvPP":   snap.get("clvPP"),
            "dataQuality": snap.get("dataQuality"),
        },
    })


def validate_pick(mk: str, p: dict, wm: dict, issues: list) -> None:
    market = p.get("market", "?")

    # H5 Fix 05.06.2026 — WATCH/STAT-Picks aus Validation ausnehmen:
    # WATCH-Picks (Corner-Beobachter ohne Markt-Quote) und STAT-Picks (Player-
    # Info-Cards) haben absichtlich keine "odds" / "edgePP" / "clvPP" Felder.
    # Vorher: jeder WATCH-Pick warf E_MISSING_FIELD-Error → Tracking-Tab zeigte
    # rote Pill obwohl alles korrekt. Jetzt: für nicht-aktive Verdicts nur
    # Light-Check (market + verdict + parse-key).
    verdict_raw = p.get("verdict", "")
    NON_ACTIVE_VERDICTS = {"WATCH", "STAT", "SKIP"}
    if verdict_raw in NON_ACTIVE_VERDICTS:
        # Light-Check: nur market + parse-key + orphan-match
        if not market or market == "?":
            _add(issues, mk, market, "warning", "W_WATCH_NO_MARKET",
                 f"{verdict_raw}-Pick ohne market-Feld", p)
        parts = mk.split("-", 3)
        if len(parts) >= 4:
            gkey, _, home, away = parts
            gdata = (wm.get("groups") or {}).get(gkey) or {}
            match_exists = any(
                fx.get("home") == home and fx.get("away") == away
                for fx in gdata.get("fixtures", [])
            )
            if not match_exists:
                _add(issues, mk, market, "error", "E_ORPHAN_MATCH",
                     f"{verdict_raw}-Pick existiert aber Match {home}-{away} nicht in {gkey}", p)
        return  # Light-check fertig

    # ── E_MISSING_FIELD ────────────────────────────────────
    for field in ("market", "odds", "verdict"):
        if not p.get(field):
            _add(issues, mk, market, "error", "E_MISSING_FIELD",
                 f"Pflichtfeld '{field}' fehlt", p)
            return   # Abort: ohne diese Felder kein weiterer Check sinnvoll

    odds       = p.get("odds")
    modelOdds  = p.get("modelOdds")
    verdict    = p.get("verdict")
    edgePP     = p.get("edgePP", 0)
    clvPP      = p.get("clvPP")
    dataQ      = p.get("dataQuality")

    # ── E_EDGE_MATH ────────────────────────────────────────
    # Wenn modelOdds < marketOdds → Modell sieht höhere Wahrscheinlichkeit → positive Edge
    # Wenn modelOdds > marketOdds → negative Edge sollte rauskommen
    if isinstance(modelOdds, (int, float)) and isinstance(odds, (int, float)) and modelOdds > 0:
        if modelOdds > odds and edgePP > 1:
            _add(issues, mk, market, "error", "E_EDGE_MATH",
                 f"modelOdds {modelOdds} > marketOdds {odds} aber Edge {edgePP}pp positiv "
                 f"(Quoten invertiert?)", p)
        elif modelOdds < odds and edgePP < -1:
            _add(issues, mk, market, "error", "E_EDGE_MATH",
                 f"modelOdds {modelOdds} < marketOdds {odds} aber Edge {edgePP}pp negativ", p)

    # ── E_VERDICT_NO_EDGE ──────────────────────────────────
    if verdict == "BET" and isinstance(edgePP, (int, float)) and edgePP < BET_MIN_EDGE:
        _add(issues, mk, market, "error", "E_VERDICT_NO_EDGE",
             f"BET-Pick mit nur {edgePP}pp Edge (Schwelle: ≥{BET_MIN_EDGE}pp) — "
             f"Filter durchgerutscht oder Edge nachträglich gefallen", p)

    # ── E_ORPHAN_MATCH ─────────────────────────────────────
    parts = mk.split("-", 3)
    if len(parts) >= 4:
        gkey, md, home, away = parts
        gdata = (wm.get("groups") or {}).get(gkey) or {}
        match_exists = any(
            fx.get("home") == home and fx.get("away") == away
            for fx in gdata.get("fixtures", [])
        )
        if not match_exists:
            _add(issues, mk, market, "error", "E_ORPHAN_MATCH",
                 f"Pick existiert aber Match {home}-{away} nicht in Gruppe {gkey} fixtures", p)

    # ── W_UNDERDOG_LEAK ────────────────────────────────────
    # Heimsieg / Auswärtssieg / DNB-Picks: schwächeres Team mit Elo-Gap >200?
    if verdict in ("BET", "ABWÄGEN") and len(parts) >= 4:
        gkey, md, home, away = parts
        gdata = (wm.get("groups") or {}).get(gkey) or {}
        teams = {t["id"]: t for t in gdata.get("teams", [])}
        elo_h = (teams.get(home) or {}).get("elo")
        elo_a = (teams.get(away) or {}).get("elo")
        m_l = market.lower()
        if isinstance(elo_h, (int, float)) and isinstance(elo_a, (int, float)):
            elo_diff = elo_h - elo_a
            picked_home = "heim" in m_l or "dnb: heim" in m_l
            picked_away = "ausw" in m_l or "dnb: ausw" in m_l
            underdog_gap = 0
            if picked_home and elo_diff < 0:
                underdog_gap = -elo_diff
            elif picked_away and elo_diff > 0:
                underdog_gap = elo_diff
            if underdog_gap > UNDERDOG_ELO_HARD and verdict == "BET":
                _add(issues, mk, market, "warning", "W_UNDERDOG_LEAK",
                     f"BET auf Underdog mit Elo-Gap {underdog_gap:.0f} > {UNDERDOG_ELO_HARD} "
                     f"(Sanity-Filter sollte das fangen)", p)

    # ── W_DATAQ_OVERSTATED ─────────────────────────────────
    # dataQuality="full" verlangt Form ≥5 + H2H ≥3 + Odds present
    if dataQ == "full" and len(parts) >= 4:
        gkey, md, home, away = parts
        form = (wm.get("form") or {})
        form_h_games = (form.get(home) or {}).get("games", 0)
        form_a_games = (form.get(away) or {}).get("games", 0)
        h2h_raw = (wm.get("h2h") or {})
        h2h_obj = h2h_raw.get(f"{home}-{away}") or h2h_raw.get(f"{away}-{home}") or {}
        h2h_games = h2h_obj.get("games", 0)
        if form_h_games < 5 or form_a_games < 5 or h2h_games < 3:
            _add(issues, mk, market, "warning", "W_DATAQ_OVERSTATED",
                 f"dataQuality=full aber Form-Spiele ({form_h_games}/{form_a_games}) "
                 f"oder H2H ({h2h_games}) unter Schwelle", p)

    # ── W_NEGATIVE_CLV ─────────────────────────────────────
    if verdict == "BET" and isinstance(clvPP, (int, float)) and clvPP <= NEG_CLV_THRESHOLD:
        _add(issues, mk, market, "warning", "W_NEGATIVE_CLV",
             f"BET-Pick mit CLV {clvPP:+.1f}pp — Markt deutlich gegen uns "
             f"(könnte falsch gepickt sein)", p)

    # ── W_ODDS_OUTLIER ─────────────────────────────────────
    if isinstance(odds, (int, float)) and odds > ODDS_OUTLIER_MIN:
        _add(issues, mk, market, "warning", "W_ODDS_OUTLIER",
             f"Quote {odds} > {ODDS_OUTLIER_MIN} — vermutlich kein liquider Markt, "
             f"sollte gefiltert sein", p)

    # ── W_HUGE_EDGE ────────────────────────────────────────
    if isinstance(edgePP, (int, float)) and edgePP > HUGE_EDGE_PP:
        _add(issues, mk, market, "warning", "W_HUGE_EDGE",
             f"Edge {edgePP}pp > {HUGE_EDGE_PP}pp — verdächtig, evtl. invertierte Quoten "
             f"oder Modell-Bug", p)


# ──────────────────────────────────────────────────────────────────────────────
#  CROSS-MARKET KONFLIKT-CHECK
#  Zweite Sicherheits-Schicht: prüft per-Match ob zwei BETs in unvereinbaren
#  Richtungen sind. Spiegelt die Logik in generate_wm_picks.py:DIRECTION_MAP.
#  Wenn das hier feuert, ist im Generator etwas durchgerutscht.
# ──────────────────────────────────────────────────────────────────────────────
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
    "Beide Teams treffen: Nein": "under",
}
INCOMPATIBLE = {
    ("homeStrong", "awayStrong"), ("homeStrong", "awayBias"), ("homeStrong", "drawOnly"),
    ("homeBias",   "awayStrong"), ("awayStrong", "drawOnly"), ("awayBias",   "homeStrong"),
    ("decisive",   "drawOnly"),   ("over",       "under"),
}


def _incompatible(d1: str, d2: str) -> bool:
    return (d1, d2) in INCOMPATIBLE or (d2, d1) in INCOMPATIBLE


def validate_cross_market(mk: str, plist: list, issues: list) -> None:
    """E_CROSS_MARKET — feuert wenn zwei BETs in unvereinbaren Richtungen.

    Sollte NIE feuern wenn generate_wm_picks korrekt läuft. Wenn doch:
    Generator-Bug oder Race-Condition zwischen Generator und Validator.
    """
    bets = [p for p in plist if p.get("verdict") == "BET"]
    for i, a in enumerate(bets):
        d_a = DIRECTION_MAP.get(a.get("market"))
        if not d_a:
            continue
        for b in bets[i+1:]:
            d_b = DIRECTION_MAP.get(b.get("market"))
            if not d_b:
                continue
            if _incompatible(d_a, d_b):
                _add(issues, mk, a.get("market", "?"), "error", "E_CROSS_MARKET",
                     f"BET '{a.get('market')}' ({d_a}) ⚔ BET '{b.get('market')}' ({d_b}) "
                     f"— logisch unvereinbar (Generator-Bug oder Race-Condition)", a)


def main():
    if not WM_FILE.exists():
        print("❌ wm2026-data.json fehlt")
        return

    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    picks_by_match = wm.get("picks") or {}

    issues: list = []
    total = 0
    for mk, plist in picks_by_match.items():
        for p in plist:
            total += 1
            validate_pick(mk, p, wm, issues)
        # Cross-Market-Check pro Match (nicht pro Pick)
        validate_cross_market(mk, plist, issues)

    errors = [i for i in issues if i["level"] == "error"]
    warns  = [i for i in issues if i["level"] == "warning"]

    report = {
        "lastRun": _now_iso(),
        "stats": {
            "total":    total,
            "errors":   len(errors),
            "warnings": len(warns),
            "ok":       total - len(errors) - len(warns),
        },
        "issues": issues,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"🔍 Validation: {total} Picks geprüft")
    print(f"   ❌ {len(errors)} Errors")
    print(f"   ⚠️  {len(warns)} Warnings")
    print(f"   ✅ {total - len(errors) - len(warns)} OK")
    if errors:
        print("\n=== ERRORS ===")
        for e in errors[:10]:
            print(f"  [{e['code']}] {e['matchKey']} · {e['market']}: {e['message']}")
    if warns:
        print("\n=== WARNINGS (Top 5) ===")
        for w in warns[:5]:
            print(f"  [{w['code']}] {w['matchKey']} · {w['market']}: {w['message']}")


if __name__ == "__main__":
    main()
