#!/usr/bin/env python3
"""
liga_backtest.py — Signal-Backtest auf Liga-Historie (26.06.2026, Lucas: „damit wir gute Wetten
kriegen"). PILOT: Premier League, letzte abgeschlossene Saison, Trefferquote OHNE Quoten.

Idee: Jedes vergangene Spiel chronologisch durchgehen, den Pre-Match-Zustand (Form/Tabelle/H2H zum
Spielzeitpunkt) rekonstruieren, durch die ECHTE Signal-Engine (evaluate_signals) schicken und
messen, wie oft jedes Signal richtig liegt. Validiert die Daten-Signale (form_trend, h2h_pattern,
league_pressure) gegen die Realität → primt später die Liga-Gewichte.

NICHT im Pilot: xG-Signale (brauchen pro Spiel /fixtures/statistics → schwer, Phase 2) und Steam
(historische Linienbewegung existiert nicht → nur vorwärts paper-tradebar). Quoten/ROI = Phase 2.

Reine Funktionen (Rekonstruktion + Aggregation) sind testbar; main() holt via API-Football.
"""
from __future__ import annotations

import http.client
import json
import os
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
APIF_HOST = "v3.football.api-sports.io"
APIF_KEY = os.environ.get("APISPORTS_KEY", "")
REPORT_FILE = os.path.join(BASE, "liga_backtest_report.json")

PL_LEAGUE_ID = 39
WARMUP_GAMES = 4          # erst werten, wenn beide Teams ≥4 Spiele Historie haben
FORM_N = 5                # Form über die letzten N Spiele
CANDIDATE_MARKETS = ["Heimsieg", "Auswärtssieg", "Über 2.5 Tore", "Unter 2.5 Tore"]


# ───────────────────────── Reine Rekonstruktion ─────────────────────────

def market_won(market: str, hs: int, as_: int) -> bool:
    total = hs + as_
    if market == "Heimsieg":        return hs > as_
    if market == "Auswärtssieg":    return as_ > hs
    if market == "Über 2.5 Tore":   return total > 2.5
    if market == "Unter 2.5 Tore":  return total < 2.5
    return False


def form_entry(results: list) -> dict:
    """results = Liste der letzten Spiele eines Teams als (gf, ga) → {games, avgScored, avgConceded}."""
    last = results[-FORM_N:]
    n = len(last)
    if n == 0:
        return {"games": 0, "avgScored": 0.0, "avgConceded": 0.0}
    return {"games": n,
            "avgScored": round(sum(g for g, _ in last) / n, 3),
            "avgConceded": round(sum(a for _, a in last) / n, 3)}


def standings_rows(table: dict) -> list:
    """table = {teamId: {points, gf, ga}} → sortierte Tabellen-Zeilen mit pos (FIFA-Tiebreaker)."""
    rows = [{"team": t, "points": d["points"], "gd": d["gf"] - d["ga"], "gf": d["gf"]}
            for t, d in table.items()]
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(rows):
        r["pos"] = i + 1
    return rows


def aggregate(ledger: list) -> dict:
    """ledger = [{signal, market, score, won}] → pro Signal Richtungs-Trefferquote + pro Markt."""
    per_sig = defaultdict(lambda: {"calls": 0, "correct": 0})
    per_sig_mkt = defaultdict(lambda: {"calls": 0, "correct": 0})
    for e in ledger:
        if abs(e["score"]) < 0.3:        # nur echte Richtungs-Calls
            continue
        correct = (e["score"] > 0 and e["won"]) or (e["score"] < 0 and not e["won"])
        for key, bucket in ((e["signal"], per_sig), ((e["signal"], e["market"]), per_sig_mkt)):
            bucket[key]["calls"] += 1
            bucket[key]["correct"] += 1 if correct else 0
    def _row(v):
        return {"calls": v["calls"], "correct": v["correct"],
                "hitRate": round(v["correct"] / v["calls"], 3) if v["calls"] else None}
    return {
        "perSignal": {k: _row(v) for k, v in sorted(per_sig.items(), key=lambda kv: -kv[1]["calls"])},
        "perSignalMarket": {f"{k[0]}|{k[1]}": _row(v)
                            for k, v in sorted(per_sig_mkt.items(), key=lambda kv: -kv[1]["calls"])},
    }


def replay(matches: list, evaluate_fn) -> list:
    """matches = chronologisch sortierte [{home, away, hs, as_, matchday}]. evaluate_fn(pick, ctx)
    = registry.evaluate_signals (injizierbar → testbar). Gibt das Signal-Ledger zurück."""
    team_results: dict = defaultdict(list)         # teamId → [(gf, ga)]
    table: dict = defaultdict(lambda: {"points": 0, "gf": 0, "ga": 0})
    h2h: dict = defaultdict(lambda: {"games": 0, "homeWins": 0, "draws": 0, "awayWins": 0})
    ledger = []
    for m in matches:
        h, a, hs, as_, md = m["home"], m["away"], m["hs"], m["as_"], m.get("matchday")
        # ── Pre-Match-Zustand (VOR diesem Spiel) ──
        if len(team_results[h]) >= WARMUP_GAMES and len(team_results[a]) >= WARMUP_GAMES:
            pair = h2h[tuple(sorted((h, a)))]
            ctx = {
                "home_id": h, "away_id": a, "group_id": "ENG", "matchday": md,
                "form": {h: form_entry(team_results[h]), a: form_entry(team_results[a])},
                "h2h": dict(pair),
                "standings": {"ENG": standings_rows(table)},
            }
            for market in CANDIDATE_MARKETS:
                res = evaluate_fn({"market": market, "odds": 2.0}, ctx)
                for sig in (res.get("signals") or []):
                    ledger.append({"signal": sig["name"], "market": market,
                                   "score": sig.get("score", 0), "won": market_won(market, hs, as_)})
        # ── Zustand NACH dem Spiel fortschreiben ──
        team_results[h].append((hs, as_))
        team_results[a].append((as_, hs))
        table[h]["gf"] += hs; table[h]["ga"] += as_
        table[a]["gf"] += as_; table[a]["ga"] += hs
        if hs > as_:   table[h]["points"] += 3
        elif as_ > hs: table[a]["points"] += 3
        else:          table[h]["points"] += 1; table[a]["points"] += 1
        pr = h2h[tuple(sorted((h, a)))]
        pr["games"] += 1
        if hs > as_:   pr["homeWins" if h < a else "awayWins"] += 1
        elif as_ > hs: pr["awayWins" if h < a else "homeWins"] += 1
        else:          pr["draws"] += 1
    return ledger


# ───────────────────────── Live-Fetch (API-Football) ─────────────────────────

def _api_get(path: str) -> dict | None:
    if not APIF_KEY:
        return None
    try:
        conn = http.client.HTTPSConnection(APIF_HOST, timeout=20)
        conn.request("GET", path, headers={"x-apisports-key": APIF_KEY})
        resp = conn.getresponse(); raw = resp.read().decode("utf-8", "replace"); conn.close()
        return json.loads(raw) if resp.status == 200 else None
    except Exception as e:
        print(f"  ⚠️  API {path}: {e}")
        return None


def _parse_round(s: str):
    import re
    m = re.search(r"(\d+)\s*$", str(s or ""))
    return int(m.group(1)) if m else None


def fetch_pl_matches(season: int) -> list:
    """Abgeschlossene PL-Spiele der Saison → chronologische Match-Liste für replay()."""
    data = _api_get(f"/fixtures?league={PL_LEAGUE_ID}&season={season}") or {}
    out = []
    for it in (data.get("response") or []):
        st = (((it.get("fixture") or {}).get("status") or {}).get("short")) or ""
        if st not in ("FT", "AET", "PEN"):
            continue
        tm, gl, lg, fx = it.get("teams") or {}, it.get("goals") or {}, it.get("league") or {}, it.get("fixture") or {}
        h, a = (tm.get("home") or {}), (tm.get("away") or {})
        if gl.get("home") is None or gl.get("away") is None:
            continue
        out.append({"home": str(h.get("id")), "away": str(a.get("id")),
                    "hs": int(gl["home"]), "as_": int(gl["away"]),
                    "matchday": _parse_round(lg.get("round")), "date": (fx.get("date") or "")})
    out.sort(key=lambda m: m["date"])
    return out


def main():
    season = int(os.environ.get("BACKTEST_SEASON") or (datetime.utcnow().year - 1))
    print(f"=== liga_backtest.py — Premier League Saison {season} (Pilot, Trefferquote) ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        return
    matches = fetch_pl_matches(season)
    print(f"  {len(matches)} abgeschlossene Spiele geladen")
    if not matches:
        return
    import sharp_signals.registry as R
    weights = R.load_signal_weights()
    ledger = replay(matches, lambda pick, ctx: R.evaluate_signals(pick, ctx, weights))
    report = aggregate(ledger)
    report["_meta"] = {"league": "ENG", "season": season, "matches": len(matches),
                       "ledgerEntries": len(ledger), "generatedAt": datetime.utcnow().isoformat()}
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Signal-Trefferquoten (Richtungs-Calls, |score|≥0.3):")
    for sig, d in report["perSignal"].items():
        print(f"    {sig:18} {d['hitRate']}  ({d['correct']}/{d['calls']})")
    print(f"\n  ✅ Report → {os.path.basename(REPORT_FILE)}")


if __name__ == "__main__":
    main()
