#!/usr/bin/env python3
"""signal_check.py — „Signal-Check" (06.07.2026, Lucas): eigenständiges CONTENT-Feature.

Idee: ein beliebiger fremder Tipp (Spiel + Markt, z.B. „Frankreich vs Irak · Heimsieg") wird gegen
ALLE verfügbaren Signale geprüft — OHNE Pinnacle-Move als Pflicht-Trigger. Output ist KEIN
BET/ABWÄGEN/SKIP-Verdict, sondern eine reine Signal-Bilanz: wie viele und welche Signale den Tipp
bestätigen (✅), widersprechen (❌) oder schweigen (⚪).

STRIKT ISOLIERT (Lucas-Vorgabe): darf sich NIRGENDS in die Picks/Cards einschleichen.
  · liest nur committete Daten, schreibt AUSSCHLIESSLICH {prefix}signal_check.json
  · nutzt NEUTRALE Gewichte (weights={}) → kein Zugriff auf den gelernten signal_weights-Loop
  · NICHT in generate_wm_picks registriert, kein Ledger-Eintrag, nie ein Verdict
  · Klassifikation rein aus dem Vorzeichen des ROH-Scores (nicht gewichtet, nicht Pinnacle-kalibriert)

Move-Signale (Steam/Lead-Lag/Freshness/Smart-Money/Poly) feuern nur, wenn für das Spiel eine
Quoten-Historie mit Bewegung vorliegt — sonst ⚪ (kein Markt-Move). Fundamentale Signale (Form,
xG, Reise, Höhe, Aufstellung, Pressure, H2H, Predictions …) feuern „kalt".

Run:  python3 signal_check.py --home FRA --away MAR --market "Heimsieg"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import cocobet_dataset as D
from sharp_signals.base import market_side
from sharp_signals.registry import ACTIVE_SIGNALS, evaluate_signals, _DISABLED_SIGNALS
from sharp_signals.apif_predictions import _devig_1x2
from sharp_signals.fixture_congestion import build_team_schedule

BASE = Path(__file__).parent
NEUTRAL_EPS = 0.05   # |score| darunter = neutral (⚪), sonst Vorzeichen entscheidet


def _load(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


# ── Context aus committeten Daten (read-only, gespiegelt aus generate_wm_picks) ──
_NT_XG_EXTRA = ("xgSimForAvg", "xgSimAgainstAvg", "shotsInsideForAvg", "sotForAvg",
                "savesForAvg", "blocksForAvg", "keyPassesForAvg", "ratingAvg")


def _find_fixture(wm: dict, home_id: str, away_id: str) -> dict:
    """Fixture (Gruppe oder KO) für das Paar finden — für matchday/round/venue/kickoff."""
    for gk, gd in (wm.get("groups") or {}).items():
        for fx in gd.get("fixtures", []):
            if fx.get("home") == home_id and fx.get("away") == away_id:
                return {**fx, "group_id": gk}
    for fx in (wm.get("koFixtures") or []):
        if fx.get("home") == home_id and fx.get("away") == away_id:
            return {**fx, "group_id": "KO"}
    return {}


def _pinnacle_snapshot(hist: list) -> dict:
    """Letzte Pinnacle-Quote als {hw,dr,aw} (für apif_predictions-Devig + Move-Signale)."""
    for e in reversed(hist or []):
        if e.get("bk") == "pinnacle" and e.get("hw"):
            return {"hw": e.get("hw"), "dr": e.get("dr"), "aw": e.get("aw")}
    return {}


def load_sources() -> dict:
    """Lädt alle separaten Signal-Files EINMAL (für den Batch — sonst 10 Reads je Markt). READ-ONLY."""
    streaks_idx: dict = {}
    for s in (_load(D.file("wm_streaks.json", "liga_streaks.json"), {}) or {}).get("streaks", []):
        streaks_idx.setdefault(str(s.get("teamId")), []).append(s)
    return {
        "odds_hist": _load(D.file("wm2026-odds-history.json", "liga-odds-history.json"), {}),
        "poly_hist": _load(D.file("wm2026-poly-history.json", "liga-poly-history.json"), {}),
        "smart_raw": _load(D.file("wm_poly_smartmoney.json", "liga_poly_smartmoney.json"), {}),
        "lineups":   _load(D.file("wm_lineups.json", "liga_lineups.json"), {}),
        "pform":     (_load(D.file("player_form.json", "liga_player_form.json"), {}) or {}).get("players", {}),
        "apif":      _load(D.file("wm_apif_predictions.json", "liga_apif_predictions.json"), {}),
        "weather":   (_load(D.file("wm_weather.json", "liga_weather.json"), {}) or {}).get("matches", {}),
        "travel":    _load(D.file("wm_travel_burden.json", "liga_travel_burden.json"), {}),
        "nt_xg":     _load(D.file("wm_nt_xg.json", "liga_nt_xg.json"), {}),
        "streaks_idx": streaks_idx,
    }


def build_context(wm: dict, home_id: str, away_id: str, sources: dict | None = None) -> dict:
    """Spiegelt den Signal-Context aus generate_wm_picks. READ-ONLY. `sources` = vorgeladene Files
    (load_sources) für den Batch; None → einmalig laden (Single-Call)."""
    src = sources if sources is not None else load_sources()
    ha_key = f"{home_id}-{away_id}"
    odds_hist, poly_hist, smart_raw = src["odds_hist"], src["poly_hist"], src["smart_raw"]
    lineups, pform, apif = src["lineups"], src["pform"], src["apif"]
    weather, travel, nt_xg = src["weather"], src["travel"], src["nt_xg"]
    streaks_idx = src["streaks_idx"]

    # xG-Stats + NT-xG-Zusatzfelder mergen (chance_creation/xg_strength/form_rating für alle Teams)
    xg_stats = dict(wm.get("xgStats", {}) or {})
    for tid, entry in (nt_xg or {}).items():
        if not isinstance(entry, dict):
            continue
        rec = dict(xg_stats.get(tid) or {})
        for k in _NT_XG_EXTRA:
            if entry.get(k) is not None:
                rec[k] = entry[k]
        for k in ("xgForAvg", "xgAgainstAvg", "games"):
            if rec.get(k) is None and entry.get(k) is not None:
                rec[k] = entry[k]
        xg_stats[tid] = rec

    team_elo = {}
    for gd in (wm.get("groups") or {}).values():
        for t in gd.get("teams", []):
            if t.get("id") and isinstance(t.get("elo"), (int, float)):
                team_elo[t["id"]] = float(t["elo"])

    smartmoney = smart_raw.get("matches", smart_raw) if isinstance(smart_raw, dict) else {}
    fx = _find_fixture(wm, home_id, away_id)
    hist = (odds_hist.get(ha_key) or []) if isinstance(odds_hist, dict) else []
    _poly = (poly_hist.get(ha_key) if isinstance(poly_hist, dict) else None) or {}
    if isinstance(_poly, list):          # Historie als Liste → jüngsten Snapshot (Dict) nehmen
        _poly = next((e for e in reversed(_poly) if isinstance(e, dict)), {})

    return {
        "matchKey":         ha_key,
        "home_id":          home_id,
        "away_id":          away_id,
        "matchday":         fx.get("matchday") or fx.get("round"),
        "group_id":         fx.get("group_id"),
        "venue":            fx.get("venue"),
        "kickoff_time":     fx.get("time"),
        "odds_snapshot":    _pinnacle_snapshot(hist),
        "odds_history":     hist,
        "poly_snapshot":    _poly,
        "smartmoney":       smartmoney,
        "travel":           travel,
        "injuries":         wm.get("injuries", {}),
        "form":             wm.get("form", {}),
        "h2h":              (wm.get("h2h") or {}).get(ha_key, {}),
        "xg_stats":         xg_stats,
        "streaks":          streaks_idx,
        "lineups":          lineups,
        "player_form":      pform,
        "squads":           wm.get("squads", {}),
        "topscorers":       wm.get("topScorers", {}),
        "coach_change":     wm.get("coachChange", {}),
        "key_departures":   wm.get("keyDepartures", {}),
        "apif_predictions": apif,
        "weather":          weather,
        "standings":        wm.get("standings") or {},
        "team_elo":         team_elo,
        # 13.07.2026: fixture_congestion braucht Spielplan + Spieldatum. Beides fehlte hier → das
        # Signal war im „Analyse"-Tab für JEDES Spiel still, obwohl die Engine es längst nutzt.
        # Gleiche Quelle wie generate_wm_picks (build_team_schedule) → kann nicht auseinanderlaufen.
        "team_schedule":      build_team_schedule(wm.get("groups") or {}),
        "current_match_date": fx.get("date"),
        "next_match_date":    fx.get("next_match_date"),
        "snapshot_ts":      None,
    }


def _classify(score: float) -> str:
    if score > NEUTRAL_EPS:
        return "confirm"
    if score < -NEUTRAL_EPS:
        return "contradict"
    return "neutral"


def _reason(tip: str, confirm: list, contradict: list, market: str) -> str:
    """Regelbasierte 1-2-Satz-Begründung (kein bezahlter KI-Key nötig)."""
    nc, nx = len(confirm), len(contradict)
    top_c = confirm[0]["label"] if confirm else None
    top_x = contradict[0]["label"] if contradict else None
    q = chr(0x201E)   # „
    p = chr(0x201C)   # "
    if nc and nc > nx:
        base = f'Unsere Signale stützen {q}{tip}{p} mehrheitlich'
        if top_c:
            base += f' — am deutlichsten {top_c}'
        if nx:
            base += f', auch wenn {nx} Signal(e) dagegenhalten'
        return base + "."
    if nx and nx > nc:
        base = f'Unsere Signale sehen {q}{tip}{p} kritisch'
        if top_x:
            base += f' — vor allem {top_x} spricht dagegen'
        if nc:
            base += f', {nc} Signal(e) stützen ihn dennoch'
        return base + "."
    if nc or nx:
        return f"Gemischtes Bild: {nc} Signal(e) dafür, {nx} dagegen — kein klares Signal-Übergewicht."
    return "Aktuell liefern unsere Signale zu diesem Tipp keine belastbare Aussage."


# Menschliche Labels je Signal (für die Card/den Text)
_SIGNAL_LABELS = {
    "betfair_money": "das Betfair-Geld", "betfair_coherence": "die Betfair-Kohärenz", "multi_book_steam": "der Sharp-Buch-Steam",
    "form_trend": "die Formkurve", "form_rating": "die Spieler-Ratings",
    "xg_strength": "die xG-Werte", "chance_creation": "die Chancenqualität",
    "travel_burden": "die Reisebelastung", "altitude_signal": "die Höhenlage",
    "lineup_signal": "die Aufstellung", "injury_signal": "Ausfälle/Sperren",
    "pressure_index": "der Tabellendruck", "incentive_signal": "die Anreizlage",
    "league_pressure": "der Ligadruck", "h2h_pattern": "der Direktvergleich",
    "apif_predictions": "das externe Prognosemodell", "weather_signal": "das Wetter",
    "streak_momentum": "die aktuelle Serie", "topscorer_momentum": "die Torjäger-Form",
    "coach_change": "der Trainerwechsel", "transfer_shift": "Kader-Abgänge",
    "fixture_congestion": "die Termindichte",
    "lead_lag_bias": "die Pinnacle-Bewegung", "steam_lag": "der Steam-Move",
    "freshness_leg": "die Frische der Bewegung", "smart_money": "das Smart Money",
    "polymarket_sharp": "der Polymarket-Fluss", "public_static_bias": "der Public-Bias",
}


def run_signal_check(wm: dict, home_id: str, away_id: str, market: str, ctx: dict | None = None) -> dict:
    """Kern: prüft den Tipp (home vs away, Markt) gegen alle Signale. Reine Funktion (testbar).
    `ctx` = vorgebauter Context (Batch reused ihn über mehrere Märkte); None → selbst bauen."""
    side = market_side(market)
    pick = {"market": market, "home": home_id, "away": away_id,
            "homeId": home_id, "awayId": away_id, "verdict": "SIGNAL_CHECK"}
    if ctx is None:
        ctx = build_context(wm, home_id, away_id)

    # modelOdds = de-viggte Pinnacle-Fair der Pick-Seite. Der echte Motor stempelt das pro Pick;
    # ohne es bleiben smart_money + apif_predictions still (brauchen die scharfe Baseline). So spiegelt
    # der Tab die volle Signal-Tiefe der Engine, statt sie zu unterzeichnen. (07.07.2026, Lucas)
    _snap = ctx.get("odds_snapshot") or {}
    if side in ("home", "away") and _snap.get("hw"):
        _dv = _devig_1x2(_snap.get("hw"), _snap.get("dr"), _snap.get("aw"))
        if _dv:
            _p = _dv[0] if side == "home" else _dv[2]
            if _p and _p > 0:
                pick["modelOdds"] = round(1.0 / _p, 3)

    out = evaluate_signals(pick, ctx, weights={})   # neutrale Gewichte → reine Signal-Sicht
    fired = out.get("signals") or []

    confirm, contradict, neutral = [], [], []
    for s in fired:
        item = {"name": s["name"], "label": _SIGNAL_LABELS.get(s["name"], s["name"]),
                "evidence": s.get("evidence", ""), "dir": _classify(s.get("score", 0.0))}
        {"confirm": confirm, "contradict": contradict, "neutral": neutral}[item["dir"]].append(item)

    fired_names = {s["name"] for s in fired}
    silent = [n for s in ACTIVE_SIGNALS if (n := s.name()) not in _DISABLED_SIGNALS
              and n not in fired_names]

    home_name = _team_name(wm, home_id)
    away_name = _team_name(wm, away_id)
    tip = f"{_side_label(side, home_name, away_name, market)}"
    n_decisive = len(confirm) + len(contradict)

    return {
        "home": home_name, "away": away_name, "homeId": home_id, "awayId": away_id,
        "market": market, "side": side, "tip": tip,
        "confirm": confirm, "contradict": contradict, "neutral": neutral,
        "silent": [{"name": n, "label": _SIGNAL_LABELS.get(n, n)} for n in silent],
        "score": {"confirm": len(confirm), "contradict": len(contradict),
                  "neutral": len(neutral), "decisive": n_decisive},
        "headline": f"{len(confirm)} von {n_decisive} klaren Signalen bestätigen den Tipp"
                    if n_decisive else "Keine klaren Signale für diesen Tipp",
        "reason": _reason(tip, confirm, contradict, market),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Reine Signal-Analyse — kein Wettaufruf, kein Tipp von uns. #cocobet",
    }


def _team_name(wm: dict, tid: str) -> str:
    for gd in (wm.get("groups") or {}).values():
        for t in gd.get("teams", []):
            if t.get("id") == tid:
                return t.get("name", tid)
    return tid


def _side_label(side, home, away, market) -> str:
    if side == "home":
        return f"{home} ({market})"
    if side == "away":
        return f"{away} ({market})"
    return market


DEFAULT_MARKETS = ["Heimsieg", "Auswärtssieg", "Über 2.5 Tore", "Unter 2.5 Tore"]


def _team_meta(wm: dict, tid: str) -> dict:
    for gd in (wm.get("groups") or {}).values():
        for t in gd.get("teams", []):
            if t.get("id") == tid:
                return {"name": t.get("name", tid), "flag": t.get("flag", "")}
    return {"name": tid, "flag": ""}


def _upcoming_fixtures(wm: dict):
    """(home, away, roundLabel, date) für anstehende + zuletzt gespielte Spiele (Content-Auswahl)."""
    from datetime import datetime as _dt
    now = datetime.now(timezone.utc)
    out = []
    for gk, gd in (wm.get("groups") or {}).items():
        for fx in gd.get("fixtures", []):
            if fx.get("home") and fx.get("away"):
                out.append((fx["home"], fx["away"], f"Gruppe {gk}", fx.get("date"), fx.get("kickoff")))
    for fx in (wm.get("koFixtures") or []):
        if fx.get("home") and fx.get("away"):
            out.append((fx["home"], fx["away"], fx.get("roundLabel") or "K.-o.", fx.get("date"), fx.get("kickoff")))
    return out


def batch_signal_check(wm: dict, markets=None, limit_upcoming=40) -> dict:
    """Rechnet Signal-Checks für alle Fixtures × Märkte vor → Frontend-freundliche Struktur.
    Das statische Pages-Frontend liest das (kein Python im Browser)."""
    markets = markets or DEFAULT_MARKETS
    sources = load_sources()   # Files EINMAL laden
    games = []
    for home, away, rnd, date, kickoff in _upcoming_fixtures(wm):
        hm, am = _team_meta(wm, home), _team_meta(wm, away)
        ctx = build_context(wm, home, away, sources)   # Context EINMAL pro Spiel
        by_market = {}
        for mkt in markets:
            r = run_signal_check(wm, home, away, mkt, ctx=ctx)
            by_market[mkt] = {
                "tip": r["tip"], "headline": r["headline"], "reason": r["reason"],
                "confirm": r["confirm"], "contradict": r["contradict"],
                "neutral": r["neutral"], "silent": r["silent"], "score": r["score"],
            }
        games.append({"key": f"{home}-{away}", "home": hm["name"], "away": am["name"],
                      "homeFlag": hm["flag"], "awayFlag": am["flag"], "homeId": home, "awayId": away,
                      "round": rnd, "date": date, "kickoff": kickoff, "markets": by_market})
    return {"_meta": {"dataset": D.active_dataset(),
                      "generatedAt": datetime.now(timezone.utc).isoformat(),
                      "games": len(games), "markets": markets,
                      "disclaimer": "Reine Signal-Analyse — kein Wettaufruf, kein Tipp von uns. #cocobet"},
            "games": games}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", help="Heim-Team-Code, z.B. FRA")
    ap.add_argument("--away", help="Auswärts-Team-Code, z.B. MAR")
    ap.add_argument("--market", help='Markt/Tipp, z.B. "Heimsieg", "Über 2.5 Tore"')
    ap.add_argument("--batch", action="store_true", help="Alle Fixtures × Standard-Märkte vorrechnen (fürs Frontend)")
    args = ap.parse_args()

    wm = _load(D.data_file(), {})
    if not wm:
        print("❌ Datenfile nicht lesbar"); return

    if args.batch:
        data = batch_signal_check(wm)
        dst = BASE / f"{D.prefix()}signal_check.json"
        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Signal-Check-Batch: {data['_meta']['games']} Spiele × {len(data['_meta']['markets'])} Märkte → {dst.name}")
        return

    if not (args.home and args.away and args.market):
        print("❌ Entweder --batch ODER --home/--away/--market angeben"); return
    result = run_signal_check(wm, args.home.upper(), args.away.upper(), args.market)

    dst = BASE / f"{D.prefix()}signal_check_single.json"
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n🔎 Signal-Check: {result['tip']}  ({result['home']} vs {result['away']})")
    print(f"   {result['headline']}")
    for s in result["confirm"]:
        print(f"   ✅ {s['label']}: {s['evidence']}")
    for s in result["contradict"]:
        print(f"   ❌ {s['label']}: {s['evidence']}")
    for s in result["neutral"]:
        print(f"   ⚪ {s['label']} (neutral)")
    print(f"   ⚪ stumm (kein Signal): {len(result['silent'])}")
    print(f"   → {result['reason']}")
    print(f"   {result['disclaimer']}")
    print(f"\n   geschrieben: {dst.name}")


if __name__ == "__main__":
    main()
