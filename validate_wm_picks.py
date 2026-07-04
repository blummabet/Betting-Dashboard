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
  E_HOMEAWAY_SWAP    — 1X2-Favorit widerspricht DC/Polymarket (Quoten vertauscht)
  W_UNDERDOG_LEAK    — Elo-Gap >200 und BET (Underdog-Filter sollte das fangen)
  W_DATAQ_OVERSTATED — dataQuality=full aber H2H/Form unvollständig
  W_NEGATIVE_CLV     — verdict=BET aber clvPP<-3 (Markt deutlich gegen uns)
  W_ODDS_OUTLIER     — Quote >12 (kein liquider Markt — sollte gefiltert sein)
  W_HUGE_EDGE        — edgePP>30 (verdächtig — inverted odds?)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path(__file__).parent
WM_FILE     = BASE / "wm2026-data.json"
REPORT_FILE = BASE / "pick_validation_report.json"

# Telegram-Alert (Push statt nur Banner). Ohne Token → Vorschau-Modus (Print).
TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
ALERT_CHAT_ID  = (os.environ.get("TELEGRAM_TRADES_CHAT_ID")
                  or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

UNDERDOG_ELO_SOFT = 100
UNDERDOG_ELO_HARD = 200
BET_MIN_EDGE      = 3        # BET sollte ≥3pp Edge haben (sonst durchgerutscht)
ODDS_OUTLIER_MIN  = 12.0     # >12 = vermutlich kein Markt
HUGE_EDGE_PP      = 30       # >30pp Edge = verdächtig (Quoten invertiert?)
NEG_CLV_THRESHOLD = -3       # <-3pp CLV bei BET = Markt deutlich gegen uns

# 22.06.2026 (Lucas, Live-Check-Fehlalarme): abgelaufene Spiele aus Fixture-Checks ausnehmen.
# Bei fertigen Spielen kollabieren die Polymarket-Preise auf den Endstand (poly_hw=poly_aw=0.0
# bei Remis) → der Swap-Check las das 0/0 als „Auswärts-Favorit" und meldete einen falschen
# Swap (BEL-IRN, Remis). Und der W_NEGATIVE_CLV „könnte falsch gepickt sein" ist gegenstandslos,
# wenn das Ergebnis schon feststeht (SCO-MAR Auswärtssieg-Steam-Pick GEWANN trotz −4pp CLV).
_FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}
_FIXTURE_INDEX: dict = {}     # 'HOME-AWAY' → fixture; einmal in main() gefüllt


def _build_fixture_index(wm: dict) -> dict:
    idx = {}
    for _g, gd in (wm.get("groups") or {}).items():
        for fx in (gd.get("fixtures") or []):
            h, a = fx.get("home"), fx.get("away")
            if h and a:
                idx[f"{h}-{a}"] = fx
    # 04.07.2026 (Lucas: „E_HOMEAWAY_SWAP-Push für BRA-JPN"): KO-Spiele leben in koFixtures,
    # nicht in groups. Ohne sie im Index gab _fx_for_key für jedes KO-Spiel None zurück →
    # _is_finished/_kickoff_passed sahen None → fertige KO-Spiele wurden NICHT ausgenommen →
    # der Swap-Check feuerte auf ein gespieltes Spiel mit veraltetem Post-Match-DC-Snapshot.
    for fx in (wm.get("koFixtures") or []):
        h, a = fx.get("home"), fx.get("away")
        if h and a:
            idx.setdefault(f"{h}-{a}", fx)
    return idx


def _fx_for_key(key: str):
    """Fixture zu einem Match-Key finden — akzeptiert 'HOME-AWAY' und 'GKEY-MD-HOME-AWAY'."""
    if not key:
        return None
    if key in _FIXTURE_INDEX:
        return _FIXTURE_INDEX[key]
    parts = key.split("-")
    if len(parts) >= 2:
        return _FIXTURE_INDEX.get(f"{parts[-2]}-{parts[-1]}")
    return None


def _is_finished(fx) -> bool:
    r = (fx or {}).get("result") or {}
    return str(r.get("status") or "").upper() in _FINISHED_STATUSES


def _kickoff_passed(fx, now=None) -> bool:
    ko = (fx or {}).get("kickoff")
    if not ko:
        return False
    try:
        kt = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        return (now or datetime.now(timezone.utc)) >= kt
    except Exception:
        return False

# Edge-Recompute-Konstanten — müssen 1:1 mit compute_verdict() in
# generate_wm_picks.py übereinstimmen (Margin-Annahmen).
MODEL_MARGIN      = 0.96     # model_prob = MODEL_MARGIN / modelOdds
MARKET_DEVIG      = 1.03     # market_prob = MARKET_DEVIG / marketOdds (~Pinnacle-Vig)
EDGE_TOLERANCE_PP = 3.0      # erlaubte Abweichung gespeicherte vs. nachgerechnete Edge


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tg_send(text: str) -> bool:
    """Telegram-Alert an den Trades-/Ops-Channel. Ohne Token: Print-Vorschau."""
    if not (TELEGRAM_TOKEN and ALERT_CHAT_ID):
        print("⚠️  Kein TELEGRAM_TOKEN/CHAT_ID — Alert-Vorschau:")
        print(text)
        return True
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": ALERT_CHAT_ID, "text": text,
                       "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"❌ Telegram-Alert fehlgeschlagen: {e}")
        return False


def _poly_side(odds: dict, key: str, od: dict):
    """(poly_home, poly_away) für eine Fixture — auch unter umgekehrtem Key."""
    if od.get("poly_hw") is not None:
        return od.get("poly_hw"), od.get("poly_aw")
    if "-" in key:
        a, b = key.split("-")[:2]
        rev = odds.get(f"{b}-{a}", {})
        if rev.get("poly_hw") is not None:
            return rev.get("poly_aw"), rev.get("poly_hw")
    return None, None


def validate_homeaway_swap(wm: dict, issues: list) -> None:
    """E_HOMEAWAY_SWAP — 1X2-Favorit gegen identitäts-korrekte Referenz prüfen.

    Hintergrund: fetch_wm_odds.py hatte einen Heim/Auswärts-Swap-Bug (10.06.2026),
    der hw↔aw spiegelte. DC/AH/O-U waren nie betroffen → DC als Referenz, plus
    Polymarket (voll unabhängig). Wenn der 1X2-Favorit der Referenz widerspricht,
    ist die Fixture mit hoher Wahrscheinlichkeit spiegelverkehrt.
    """
    odds = wm.get("odds") or {}
    for key, od in odds.items():
        # 22.06.2026: fertige/laufende Spiele raus. Post-Anpfiff spiegelt Polymarket den (Zwischen-)
        # Stand, nicht die Markt-Sicht aufs Ergebnis → Swap-Detektion gegen Poly ist dann ungültig.
        fx = _fx_for_key(key)
        if _is_finished(fx) or _kickoff_passed(fx):
            continue
        hw, aw = od.get("hw"), od.get("aw")
        if not (isinstance(hw, (int, float)) and isinstance(aw, (int, float))):
            continue
        if abs(hw - aw) < 0.15:
            # Münzwurf — Richtung nicht aussagekräftig. Schwelle 0.15 IDENTISCH zum
            # Integritäts-Guard check_homeaway_consistent (21.06.2026, Lucas): vorher 0.05
            # → der Validator schrie „SWAP" bei knappen Spielen (CPV-SAU hw/aw 2.48/2.57,
            # Δ0.09), die der Guard korrekt als „sauber" durchließ → widersprüchliche Meldungen
            # + Telegram-Fehlalarm. Beide Swap-Detektoren nutzen jetzt dieselbe Schwelle.
            continue
        x2_home_fav = hw < aw

        # Referenz 1: Polymarket (primär, unabhängig)
        ph, pa = _poly_side(odds, key, od)
        # Poly-Tie (inkl. 0/0 nach Auflösung oder echter 50/50) gibt KEINE Richtung her → no-signal,
        # sonst läse das 0.0/0.0 als „Auswärts-Favorit".
        poly_ref = None
        if isinstance(ph, (int, float)) and isinstance(pa, (int, float)) and abs(ph - pa) > 0.02:
            poly_ref = ph > pa

        # Referenz 2: Doppelte Chance (sekundär; Gleichstand = kein Signal)
        dc1x, dcx2 = od.get("dc1X"), od.get("dcX2")
        dc_ref = None
        if isinstance(dc1x, (int, float)) and isinstance(dcx2, (int, float)) \
                and abs(dc1x - dcx2) > 0.02:
            dc_ref = dc1x < dcx2

        ref = poly_ref if poly_ref is not None else dc_ref
        if ref is None or ref == x2_home_fav:
            continue

        # Beide Referenzen (falls beide da) müssen widersprechen → kein Fehlalarm
        if poly_ref is not None and dc_ref is not None and poly_ref != dc_ref:
            continue

        ref_name = "Polymarket" if poly_ref is not None else "DC"
        _add(issues, key, "1X2", "error", "E_HOMEAWAY_SWAP",
             f"1X2 hw/aw {hw}/{aw} → {'Heim' if x2_home_fav else 'Auswärts'}-Favorit, "
             f"aber {ref_name} sieht {'Heim' if ref else 'Auswärts'}-Favorit "
             f"— Heim/Auswärts-Quoten vermutlich vertauscht", od)


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
    NON_ACTIVE_VERDICTS = {"WATCH", "STAT", "SKIP", "NOBET"}
    if verdict_raw in NON_ACTIVE_VERDICTS:
        # Light-Check: nur market + parse-key + orphan-match
        if not market or market == "?":
            _add(issues, mk, market, "warning", "W_WATCH_NO_MARKET",
                 f"{verdict_raw}-Pick ohne market-Feld", p)
        parts = mk.split("-", 3)
        if len(parts) >= 4:
            gkey, _, home, away = parts
            if gkey == "KO":   # KO-Picks leben in koFixtures, nicht in groups (26.06.2026)
                match_exists = any(kf.get("home") == home and kf.get("away") == away
                                   for kf in (wm.get("koFixtures") or []))
            else:
                gdata = (wm.get("groups") or {}).get(gkey) or {}
                match_exists = any(fx.get("home") == home and fx.get("away") == away
                                   for fx in gdata.get("fixtures", []))
            if not match_exists:
                # NOBET = informativer Schatten-Pick; ein verwaister NOBET (z.B. KO-Bracket hat sich
                # umgelöst, Paarung weg) ist harmlos → Warnung statt Error (26.06.2026, Lucas).
                lvl = "warning" if verdict_raw == "NOBET" else "error"
                _add(issues, mk, market, lvl, "E_ORPHAN_MATCH",
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
    # FIX 10.06.2026 (Audit): Der alte Check verglich modelOdds vs marketOdds
    # roh — das ignoriert die asymmetrischen Margins in compute_verdict
    # (model_prob = 0.96/modelOdds, market_prob = 1.03/marketOdds). Dadurch
    # gab es eine tote Zone nahe edge=0, in der modelOdds < marketOdds trotzdem
    # zu leicht negativer (korrekter!) Edge führt → falsche Errors.
    # Jetzt: Edge mit der EXAKTEN compute_verdict-Formel nachrechnen und nur
    # flaggen wenn der gespeicherte Wert signifikant abweicht (Vorzeichen-Bug
    # wie die invertierten Synth-DC/AH-Picks hätte das ebenfalls gefangen).
    if isinstance(modelOdds, (int, float)) and isinstance(odds, (int, float)) \
            and modelOdds > 1 and odds > 1:
        expected_edge = ((MODEL_MARGIN / modelOdds) - (MARKET_DEVIG / odds)) * 100
        if isinstance(edgePP, (int, float)) and abs(edgePP - expected_edge) > EDGE_TOLERANCE_PP:
            _add(issues, mk, market, "error", "E_EDGE_MATH",
                 f"edgePP {edgePP:+.1f} weicht von erwarteter Edge {expected_edge:+.1f}pp ab "
                 f"(modelOdds {modelOdds}, marketOdds {odds}) — Vorzeichen/Margin-Bug?", p)

    # ── E_VERDICT_NO_EDGE / Steam-Äquivalent ───────────────
    # Steam-Picks (Lucas' Modell) sind CONVICTION-/MOVE-getrieben, NICHT edge-getrieben:
    # edgePP ist by design ~0/negativ, weil wir Pinnacle nicht schlagen, sondern den Move
    # reiten. Daher gilt die Edge-Schwelle nur für Nicht-Steam. Für Steam-BET prüfen wir
    # stattdessen, dass der auslösende Move + die Conviction wirklich vorhanden sind.
    if p.get("source") == "steam":
        if verdict == "BET":
            if not isinstance(p.get("steamMovePP"), (int, float)):
                _add(issues, mk, market, "error", "E_STEAM_NO_MOVE",
                     "Steam-BET ohne steamMovePP — Trigger (Pinnacle-Move) fehlt", p)
            elif not isinstance(p.get("convictionScore"), (int, float)):
                _add(issues, mk, market, "error", "E_STEAM_NO_CONVICTION",
                     "Steam-BET ohne convictionScore — Bestätigungs-Stufe nicht gelaufen", p)
    elif verdict == "BET" and isinstance(edgePP, (int, float)) and edgePP < BET_MIN_EDGE:
        _add(issues, mk, market, "error", "E_VERDICT_NO_EDGE",
             f"BET-Pick mit nur {edgePP}pp Edge (Schwelle: ≥{BET_MIN_EDGE}pp) — "
             f"Filter durchgerutscht oder Edge nachträglich gefallen", p)

    # ── E_ORPHAN_MATCH ─────────────────────────────────────
    parts = mk.split("-", 3)
    if len(parts) >= 4:
        gkey, md, home, away = parts
        if gkey == "KO":
            # KO-Picks leben in koFixtures, nicht in groups (26.06.2026). Ein veröffentlichter
            # KO-Pick, dessen Paarung sich durch Bracket-Auflösung verschoben hat, ist KEIN
            # Generator-Bug (Picks immutable) → Warnung, nicht Error.
            match_exists = any(kf.get("home") == home and kf.get("away") == away
                               for kf in (wm.get("koFixtures") or []))
            lvl, where = "warning", "koFixtures"
        else:
            gdata = (wm.get("groups") or {}).get(gkey) or {}
            match_exists = any(
                fx.get("home") == home and fx.get("away") == away
                for fx in gdata.get("fixtures", [])
            )
            lvl, where = "error", f"Gruppe {gkey} fixtures"
        if not match_exists:
            _add(issues, mk, market, lvl, "E_ORPHAN_MATCH",
                 f"Pick existiert aber Match {home}-{away} nicht in {where}", p)

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
    # 22.06.2026: gegenstandslos bei fertigem Spiel (Ergebnis steht — SCO-MAR Auswärtssieg gewann
    # trotz −4pp CLV). Und für Steam ist neg. CLV by design möglich (move-/conviction-getrieben,
    # nicht edge-getrieben) → neutraleres Wording statt „falsch gepickt".
    if verdict == "BET" and isinstance(clvPP, (int, float)) and clvPP <= NEG_CLV_THRESHOLD \
            and not _is_finished(_fx_for_key(mk)):
        is_steam = p.get("source") == "steam" or dataQ == "steam"
        msg = (f"BET-Pick mit CLV {clvPP:+.1f}pp — der Move hielt nicht bis zum Close "
               f"(Steam ist move-/conviction-getrieben, nicht edge-getrieben)") if is_steam else \
              (f"BET-Pick mit CLV {clvPP:+.1f}pp — Markt deutlich gegen uns "
               f"(könnte falsch gepickt sein)")
        _add(issues, mk, market, "warning", "W_NEGATIVE_CLV", msg, p)

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
#  Richtungen sind. Verwendet pick_constants als Single Source of Truth.
#  Wenn das hier feuert, ist im Generator etwas durchgerutscht.
# ──────────────────────────────────────────────────────────────────────────────
try:
    from pick_constants import (
        get_pick_direction as _get_dir,
        are_directions_incompatible as _is_incompatible_dir,
    )
    from pick_helpers import is_legitimate_pick
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    def is_legitimate_pick(p): return p is not None


def validate_cross_market(mk: str, plist: list, issues: list) -> None:
    """E_CROSS_MARKET — feuert wenn zwei BETs in unvereinbaren Richtungen.

    Sollte NIE feuern wenn generate_wm_picks korrekt läuft. Wenn doch:
    Generator-Bug oder Race-Condition zwischen Generator und Validator.

    Ignoriert trackingExcluded-Picks (die sind bewusst vom Tracker rausgeworfen).
    """
    if not _HELPERS_AVAILABLE:
        return  # fail-safe — ohne helpers kein Check

    bets = [p for p in plist if p.get("verdict") == "BET" and is_legitimate_pick(p)]
    for i, a in enumerate(bets):
        d_a = _get_dir(a.get("market"))
        if not d_a:
            continue
        for b in bets[i+1:]:
            d_b = _get_dir(b.get("market"))
            if not d_b:
                continue
            if _is_incompatible_dir(d_a, d_b):
                _add(issues, mk, a.get("market", "?"), "error", "E_CROSS_MARKET",
                     f"BET '{a.get('market')}' ({d_a}) ⚔ BET '{b.get('market')}' ({d_b}) "
                     f"— logisch unvereinbar (Generator-Bug oder Race-Condition)", a)


def main():
    if not WM_FILE.exists():
        print("❌ wm2026-data.json fehlt")
        return

    wm = json.loads(WM_FILE.read_text(encoding="utf-8"))
    global _FIXTURE_INDEX
    _FIXTURE_INDEX = _build_fixture_index(wm)   # 'HOME-AWAY' → fixture (für finished/kickoff-Gate)
    picks_by_match = wm.get("picks") or {}

    issues: list = []
    total = 0
    for mk, plist in picks_by_match.items():
        for p in plist:
            total += 1
            validate_pick(mk, p, wm, issues)
        # Cross-Market-Check pro Match (nicht pro Pick)
        validate_cross_market(mk, plist, issues)

    # Fixture-Level: Heim/Auswärts-Swap (unabhängig von einzelnen Picks)
    validate_homeaway_swap(wm, issues)

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

    # ── Push-Alert bei Errors ────────────────────────────────────────────
    # Banner allein reicht nicht (man muss hinschauen). Bei Errors aktiv pingen.
    if errors:
        codes = {}
        for e in errors:
            codes[e["code"]] = codes.get(e["code"], 0) + 1
        code_line = ", ".join(f"{c}×{n}" for c, n in sorted(codes.items()))
        lines = [
            f"🚨 <b>Validator: {len(errors)} Error(s)</b> bei {total} Picks",
            f"<i>{code_line}</i>",
            "",
        ]
        for e in errors[:8]:
            lines.append(f"• [{e['code']}] {e['matchKey']} · {e['market']}")
        if len(errors) > 8:
            lines.append(f"… +{len(errors) - 8} weitere")
        tg_send("\n".join(lines))

    # Exit-Code: Step wird im Workflow rot (continue-on-error lässt Commit laufen,
    # also gehen gute Daten NICHT verloren — der rote Step macht es nur sichtbar).
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
