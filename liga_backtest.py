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


def xg_entry(results: list) -> dict:
    """results = [(xgFor, xgAgainst)] eines Teams (bis VOR dem Spiel) → xg_strength-Format.
    source='apif_real' ab 3 Spielen → xg_strength nutzt ECHTES xG (sonst Form-Fallback, Phase 1)."""
    last = results[-10:]
    n = len(last)
    if n < 3:
        return {"games": n, "xgForAvg": None, "xgAgainstAvg": None, "xgGames": n, "source": "none"}
    return {"games": n, "xgGames": n, "source": "apif_real",
            "xgForAvg": round(sum(f for f, _ in last) / n, 3),
            "xgAgainstAvg": round(sum(a for _, a in last) / n, 3)}


def standings_rows(table: dict) -> list:
    """table = {teamId: {points, gf, ga}} → sortierte Tabellen-Zeilen mit pos (FIFA-Tiebreaker)."""
    rows = [{"team": t, "points": d["points"], "gd": d["gf"] - d["ga"], "gf": d["gf"]}
            for t, d in table.items()]
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(rows):
        r["pos"] = i + 1
    return rows


def _pnl(won: bool, odds) -> float | None:
    """1u-Einsatz auf die Pick-Seite zur (Closing-)Quote → P&L. None wenn keine Quote."""
    if not odds or odds <= 1.0:
        return None
    return round((odds - 1.0) if won else -1.0, 3)


def aggregate(ledger: list) -> dict:
    """ledger = [{signal, market, score, won, odds?}] → Richtungs-Trefferquote + ROI (Phase 2) pro
    Signal/Markt. ROI: jeder positive Richtungs-Call = 1u auf den Markt zur Closing-Quote."""
    per_sig = defaultdict(lambda: {"calls": 0, "correct": 0, "bets": 0, "pnl": 0.0, "stake": 0.0})
    per_sig_mkt = defaultdict(lambda: {"calls": 0, "correct": 0, "bets": 0, "pnl": 0.0, "stake": 0.0})
    for e in ledger:
        if abs(e["score"]) < 0.3:        # nur echte Richtungs-Calls
            continue
        correct = (e["score"] > 0 and e["won"]) or (e["score"] < 0 and not e["won"])
        # ROI nur bei POSITIVEM Call (= „wir würden den Markt spielen") + vorhandener Quote.
        pnl = _pnl(e["won"], e.get("odds")) if e["score"] > 0 else None
        for key, bucket in ((e["signal"], per_sig), ((e["signal"], e["market"]), per_sig_mkt)):
            b = bucket[key]
            b["calls"] += 1
            b["correct"] += 1 if correct else 0
            if pnl is not None:
                b["bets"] += 1
                b["pnl"] += pnl
                b["stake"] += 1.0
    def _row(v):
        roi = round(v["pnl"] / v["stake"] * 100, 1) if v["stake"] else None
        return {"calls": v["calls"], "correct": v["correct"],
                "hitRate": round(v["correct"] / v["calls"], 3) if v["calls"] else None,
                "bets": v["bets"], "roiPct": roi, "pnl": round(v["pnl"], 2)}
    return {
        "perSignal": {k: _row(v) for k, v in sorted(per_sig.items(), key=lambda kv: -kv[1]["calls"])},
        "perSignalMarket": {f"{k[0]}|{k[1]}": _row(v)
                            for k, v in sorted(per_sig_mkt.items(), key=lambda kv: -kv[1]["calls"])},
    }


def replay(matches: list, evaluate_fn) -> list:
    """matches = chronologisch sortierte [{home, away, hs, as_, matchday}]. evaluate_fn(pick, ctx)
    = registry.evaluate_signals (injizierbar → testbar). Gibt das Signal-Ledger zurück."""
    team_results: dict = defaultdict(list)         # teamId → [(gf, ga)]
    team_xg: dict = defaultdict(list)              # teamId → [(xgFor, xgAgainst)]  (Phase 2)
    table: dict = defaultdict(lambda: {"points": 0, "gf": 0, "ga": 0})
    h2h: dict = defaultdict(lambda: {"games": 0, "homeWins": 0, "draws": 0, "awayWins": 0})
    ledger = []
    for m in matches:
        h, a, hs, as_, md = m["home"], m["away"], m["hs"], m["as_"], m.get("matchday")
        m_odds = m.get("odds") or {}
        # ── Pre-Match-Zustand (VOR diesem Spiel) ──
        if len(team_results[h]) >= WARMUP_GAMES and len(team_results[a]) >= WARMUP_GAMES:
            pair = h2h[tuple(sorted((h, a)))]
            ctx = {
                "home_id": h, "away_id": a, "group_id": "ENG", "matchday": md,
                "form": {h: form_entry(team_results[h]), a: form_entry(team_results[a])},
                "h2h": dict(pair),
                "standings": {"ENG": standings_rows(table)},
                # Phase 2: echtes xG point-in-time (xg_strength nutzt es statt Form-Fallback).
                "xg_stats": {h: xg_entry(team_xg[h]), a: xg_entry(team_xg[a])},
            }
            for market in CANDIDATE_MARKETS:
                res = evaluate_fn({"market": market, "odds": m_odds.get(market, 2.0)}, ctx)
                for sig in (res.get("signals") or []):
                    ledger.append({"signal": sig["name"], "market": market,
                                   "score": sig.get("score", 0), "won": market_won(market, hs, as_),
                                   "odds": m_odds.get(market)})
        # ── Zustand NACH dem Spiel fortschreiben ──
        team_results[h].append((hs, as_))
        team_results[a].append((as_, hs))
        _xg = m.get("xg") or {}
        if _xg.get("home") is not None and _xg.get("away") is not None:
            team_xg[h].append((_xg["home"], _xg["away"]))
            team_xg[a].append((_xg["away"], _xg["home"]))
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
                    "homeName": h.get("name"), "awayName": a.get("name"),
                    "fid": (fx.get("id")),
                    "hs": int(gl["home"]), "as_": int(gl["away"]),
                    "matchday": _parse_round(lg.get("round")), "date": (fx.get("date") or "")})
    out.sort(key=lambda m: m["date"])
    return out


def fetch_fixture_xg(fid, cache: dict) -> dict | None:
    """Echtes xG pro Team aus /fixtures/statistics (gecacht je fixture-id). {home: xg, away: xg}
    bezogen auf die Heim/Auswärts-Seiten des Fixtures (per Team-ID gemappt im Aufrufer)."""
    key = str(fid)
    if key in cache:
        return cache[key]
    data = _api_get(f"/fixtures/statistics?fixture={fid}")
    out = {}
    for blk in ((data or {}).get("response") or []):
        tid = str(((blk.get("team") or {}).get("id")))
        xg = None
        for s in (blk.get("statistics") or []):
            if str(s.get("type", "")).lower() == "expected_goals" and s.get("value") not in (None, ""):
                try:
                    xg = float(str(s["value"]).replace(",", "."))
                except Exception:
                    xg = None
        if xg is not None:
            out[tid] = xg
    cache[key] = out
    return out


# ── Historische Closing-Quoten: football-data.co.uk (gratis CSV pro Liga/Saison) ──
FD_LEAGUE = {"ENG": "E0", "ESP": "SP1", "GER": "D1", "ITA": "I1", "FRA": "F1"}


def _fd_season_code(season: int) -> str:
    """2025 → '2526' (football-data Saison-Code Startjahr+Folgejahr, 2-stellig)."""
    return f"{season % 100:02d}{(season + 1) % 100:02d}"


def parse_fd_csv(text: str) -> list[dict]:
    """football-data-CSV → [{date, home, away, oddsH, oddsD, oddsA, o25, u25}] (reine Funktion)."""
    import csv
    import io
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            home, away = r.get("HomeTeam"), r.get("AwayTeam")
            if not home or not away:
                continue
            def _f(*keys):
                for k in keys:
                    v = r.get(k)
                    if v not in (None, ""):
                        try:
                            return float(v)
                        except Exception:
                            pass
                return None
            rows.append({"date": r.get("Date"), "home": home, "away": away,
                         "oddsH": _f("AvgH", "B365H", "PSH"), "oddsD": _f("AvgD", "B365D", "PSD"),
                         "oddsA": _f("AvgA", "B365A", "PSA"),
                         "o25": _f("Avg>2.5", "B365>2.5", "P>2.5"),
                         "u25": _f("Avg<2.5", "B365<2.5", "P<2.5")})
        except Exception:
            continue
    return rows


def _http_get(url: str) -> str | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CocoBet/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  ⚠️  football-data {url}: {e}")
        return None


def _fd_date_iso(d: str) -> str:
    """football-data Datum DD/MM/YY(YY) → YYYY-MM-DD."""
    parts = (d or "").split("/")
    if len(parts) != 3:
        return ""
    dd, mm, yy = parts
    yy = ("20" + yy) if len(yy) == 2 else yy
    return f"{yy}-{int(mm):02d}-{int(dd):02d}"


def attach_odds(matches: list, fd_rows: list) -> int:
    """football-data-Zeilen per Datum + Teamname an die Matches hängen (m['odds']). Anzahl gematcht."""
    from fetch_liga_odds import _names_match
    n = 0
    for m in matches:
        md = (m.get("date") or "")[:10]
        hn, an = m.get("homeName"), m.get("awayName")
        for r in fd_rows:
            if _fd_date_iso(r["date"]) == md and _names_match(r["home"], hn) and _names_match(r["away"], an):
                m["odds"] = {"Heimsieg": r["oddsH"], "Auswärtssieg": r["oddsA"],
                             "Über 2.5 Tore": r["o25"], "Unter 2.5 Tore": r["u25"]}
                n += 1
                break
    return n


def main():
    season = int(os.environ.get("BACKTEST_SEASON") or (datetime.utcnow().year - 1))
    print(f"=== liga_backtest.py — Premier League Saison {season} (Phase 2: xG + ROI) ===")
    if not APIF_KEY:
        print("  ❌  APISPORTS_KEY nicht gesetzt — übersprungen.")
        return
    matches = fetch_pl_matches(season)
    print(f"  {len(matches)} abgeschlossene Spiele geladen")
    if not matches:
        return

    # Echtes xG je Spiel (gecacht → Re-Runs billig).
    CACHE = os.path.join(BASE, "liga_backtest_cache.json")
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
    import time
    xg_n = 0
    for m in matches:
        if not m.get("fid"):
            continue
        stats = fetch_fixture_xg(m["fid"], cache)
        if stats and m["home"] in stats and m["away"] in stats:
            m["xg"] = {"home": stats[m["home"]], "away": stats[m["away"]]}
            xg_n += 1
        time.sleep(0.25)
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    print(f"  xG für {xg_n}/{len(matches)} Spiele")

    # Historische Closing-Quoten (football-data.co.uk).
    fd_url = f"https://www.football-data.co.uk/mmz4281/{_fd_season_code(season)}/{FD_LEAGUE['ENG']}.csv"
    fd_text = _http_get(fd_url)
    odds_n = 0
    if fd_text:
        odds_n = attach_odds(matches, parse_fd_csv(fd_text))
    print(f"  Closing-Quoten für {odds_n}/{len(matches)} Spiele")

    import sharp_signals.registry as R
    weights = R.load_signal_weights()
    ledger = replay(matches, lambda pick, ctx: R.evaluate_signals(pick, ctx, weights))
    report = aggregate(ledger)
    report["_meta"] = {"league": "ENG", "season": season, "matches": len(matches),
                       "xgMatches": xg_n, "oddsMatches": odds_n,
                       "ledgerEntries": len(ledger), "generatedAt": datetime.utcnow().isoformat()}
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Signal: Trefferquote | ROI (1u/Call zur Closing-Quote):")
    for sig, d in report["perSignal"].items():
        roi = f"{d['roiPct']:+.1f}%" if d.get("roiPct") is not None else "—"
        print(f"    {sig:18} {d['hitRate']}  ({d['correct']}/{d['calls']})   ROI {roi}  ({d['bets']} Wetten)")
    print(f"\n  ✅ Report → {os.path.basename(REPORT_FILE)}")


if __name__ == "__main__":
    main()
